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
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SparkSyncApi, SparkSyncAuthError, SparkSyncError
from .const import is_fresh

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]
SCAN_INTERVAL = timedelta(seconds=15)

type SparkSyncConfigEntry = ConfigEntry[list["SparkSyncCoordinator"]]


class SparkSyncCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls /info for one device."""

    def __init__(
        self, hass: HomeAssistant, api: SparkSyncApi, device: dict[str, Any]
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"SparkSync {device['name']}",
            update_interval=SCAN_INTERVAL,
        )
        self.api = api
        self.device = device

    @property
    def data_is_fresh(self) -> bool:
        """False when /info is replaying the last value from before a dropout."""
        return is_fresh((self.data or {}).get("_meta") or {}, time.time())

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.api.async_get_info(self.device["id"])
        except SparkSyncAuthError as err:
            raise ConfigEntryAuthFailed(err) from err
        except SparkSyncError as err:
            raise UpdateFailed(err) from err


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
        coordinator = SparkSyncCoordinator(hass, api, device)
        # ponytail: tolerate first-refresh failure (503 = no telemetry yet) so one
        # offline generator does not block the whole entry; entities show unavailable.
        await coordinator.async_refresh()
        coordinators.append(coordinator)

    entry.runtime_data = coordinators
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SparkSyncConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
