"""The SparkSync integration."""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import SparkSyncApi, SparkSyncAuthError, SparkSyncError
from .const import CONF_EXPORT_SENSORS, DOMAIN, export_kw, is_fresh, sensor_export_kw
from .pid import ExportPID

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.NUMBER, Platform.SENSOR, Platform.SWITCH]
# GET /info allows 250/min; 5 s is 12 polls/min per generator.
SCAN_INTERVAL = timedelta(seconds=5)

type SparkSyncConfigEntry = ConfigEntry[list["SparkSyncCoordinator"]]


class SparkSyncCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls /info for one device."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: SparkSyncConfigEntry,
        api: SparkSyncApi,
        device: dict[str, Any],
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"SparkSync {device['name']}",
            update_interval=SCAN_INTERVAL,
        )
        self.api = api
        self.device = device
        self.pid = ExportPID()

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.device["mac_address"])},
            name=self.device["name"],
            manufacturer="SparkSync",
        )

    @property
    def data_is_fresh(self) -> bool:
        """False when /info is replaying the last value from before a dropout."""
        return is_fresh((self.data or {}).get("_meta") or {}, time.time())

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data = await self.api.async_get_info(self.device["id"])
        except SparkSyncAuthError as err:
            raise ConfigEntryAuthFailed(err) from err
        except SparkSyncError as err:
            raise UpdateFailed(err) from err
        await self._async_regulate(data)
        return data

    def measured_export_kw(self, data: dict[str, Any] | None = None) -> float | None:
        """Export power in kW: the configured meter if there is one, else /info mains.

        The options are read live, so changing the meter takes effect next poll.
        """
        data = self.data if data is None else data
        entity_id = (self.config_entry.options.get(CONF_EXPORT_SENSORS) or {}).get(
            str(self.device["id"])
        )
        if not entity_id:
            return export_kw((data or {}).get("mains") or {})
        if (state := self.hass.states.get(entity_id)) is None:
            return None
        age = (dt_util.utcnow() - state.last_updated).total_seconds()
        return sensor_export_kw(
            state.state, state.attributes.get("unit_of_measurement"), age
        )

    async def _async_current_ceiling(self, generator: dict[str, Any]) -> float:
        """The load-level-max the controller is actually holding, for a bumpless start.

        Seeding from `percent_full_power` instead would drag the ceiling down to
        whatever the generator happened to be producing when the loop was armed.
        """
        try:
            value = (await self.api.async_get_load_level_max(self.device["id"]))["value_percent"]
            return float(value)
        except (SparkSyncError, KeyError, TypeError, ValueError):
            # 503 = never reported; current load is the next best anchor.
            return float(generator.get("percent_full_power") or 0.0)

    async def _async_regulate(self, data: dict[str, Any]) -> None:
        """Hold grid export at the target by trimming the generator load-level-max."""
        pid = self.pid
        generator = data.get("generator") or {}
        engine = data.get("engine") or {}
        running = (engine.get("engine_speed_rpm") or 0) > 0

        # Never steer on a stale snapshot or a stopped engine — freeze instead, and
        # re-seed from the real load level when the generator comes back.
        if not pid.enabled or not running or not is_fresh(data.get("_meta") or {}, time.time()):
            pid.stop()
            return
        if not pid.running:
            pid.start(await self._async_current_ceiling(generator))

        measured = self.measured_export_kw(data)
        if measured is None:
            # No usable reading (meter unknown, wrong unit, or stale) — hold.
            _LOGGER.debug("%s: no export reading, holding load-level-max", self.name)
            return
        command = pid.step(measured, time.time())
        if command is None:
            return
        try:
            await self.api.async_set_load_level_max(self.device["id"], command)
        except SparkSyncError as err:
            # A rejected write must not fail the poll; the next tick retries.
            pid.last_written = None
            _LOGGER.warning("Export regulation write failed for %s: %s", self.name, err)
        else:
            _LOGGER.debug(
                "%s: export %.1f kW vs target %.1f kW -> load-level-max %d%%",
                self.name,
                measured,
                pid.target_kw,
                command,
            )


async def async_setup_entry(hass: HomeAssistant, entry: SparkSyncConfigEntry) -> bool:
    api = SparkSyncApi(
        async_get_clientsession(hass),
        entry.data[CONF_URL],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )
    try:
        await api.async_login()
        devices = await api.async_get_devices()
    except SparkSyncAuthError as err:
        raise ConfigEntryAuthFailed(err) from err
    except SparkSyncError as err:
        raise ConfigEntryNotReady(err) from err

    coordinators = []
    for device in devices:
        coordinator = SparkSyncCoordinator(hass, entry, api, device)
        # ponytail: tolerate first-refresh failure (503 = no telemetry yet) so one
        # offline generator does not block the whole entry; entities show unavailable.
        await coordinator.async_refresh()
        coordinators.append(coordinator)

    entry.runtime_data = coordinators
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SparkSyncConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
