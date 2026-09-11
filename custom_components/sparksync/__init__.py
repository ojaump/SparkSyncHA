"""The SparkSync integration.

Telemetry arrives over MQTT straight from the gateway (1 Hz, retained). The REST
API is still used to log in and enumerate devices, but not for live data.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util.json import json_loads_object

from .api import SparkSyncApi, SparkSyncAuthError, SparkSyncError
<<<<<<< Updated upstream
from .const import CONF_MODE, DOMAIN, MODE_MQTT, is_fresh
from .meter import SparkSyncMeterHub
=======
from .const import DOMAIN, PUSH_INTERVAL_S, is_fresh, mqtt_device_id
from .normalize import normalize
>>>>>>> Stashed changes

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

type SparkSyncConfigEntry = ConfigEntry[
    list["SparkSyncCoordinator"] | SparkSyncMeterHub
]


class SparkSyncCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Assembles one device's telemetry sections from MQTT into the /info shape."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: SparkSyncConfigEntry,
        device: dict[str, Any],
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"SparkSync {device['name']}",
            update_interval=None,  # pushed by MQTT, never polled
        )
        self.device = device
        self.topic_id = mqtt_device_id(device["mac_address"])
        self._sections: dict[str, dict[str, Any]] = {}
        self._online = False  # until the retained LWT says otherwise
        self._controller_online = True
        self._last_ts = 0
        self._debouncer = Debouncer(
            hass,
            _LOGGER,
            cooldown=PUSH_INTERVAL_S,
            immediate=True,
            function=self._async_push,
        )

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.device["mac_address"])},
            name=self.device["name"],
            manufacturer="SparkSync",
        )

    @property
    def data_is_fresh(self) -> bool:
        """False when the retained frames outlived the gateway that published them."""
        return is_fresh((self.data or {}).get("_meta") or {}, time.time())

    async def async_subscribe(self) -> None:
        """Subscribe to this device's live topics.

        A single-level `+` deliberately does not match `<suffix>/backfill`, so the
        replay lane cannot overwrite live state.
        """
        unsub = await mqtt.async_subscribe(
            self.hass, f"devices/{self.topic_id}/+", self._async_message, qos=1
        )
        self.config_entry.async_on_unload(unsub)

    async def _async_message(self, msg: mqtt.ReceiveMessage) -> None:
        suffix = msg.topic.rpartition("/")[2]
        try:
            payload = json_loads_object(msg.payload)
        except ValueError:
            _LOGGER.debug("%s: unparseable payload on %s", self.name, msg.topic)
            return
        # Belt and braces: the wildcard already excludes the replay lane.
        if payload.get("_backfill") or (payload.get("_meta") or {}).get("is_backfill"):
            return

        if suffix == "lwt":
            self._online = bool(payload.get("online"))
        elif suffix == "health":
            return  # gateway's own telemetry, not the generator's
        else:
            self._sections[suffix] = normalize(suffix, payload)
            self._controller_online = bool(payload.get("controller_online", True))
            self._last_ts = payload.get("ts") or self._last_ts
        await self._debouncer.async_call()

    async def _async_push(self) -> None:
        self.async_set_updated_data(self._build())

    async def _async_update_data(self) -> dict[str, Any]:
        # Only reached if something forces a refresh; there is nothing to poll.
        return self._build()

    def _build(self) -> dict[str, Any]:
        """The merged sections, shaped like a GET /info body."""
        data: dict[str, Any] = dict(self._sections)
        data["_meta"] = {
            "is_online": self._online,
            "controller_online": self._controller_online,
            "last_seen": self._last_ts,
        }
        return data


async def async_setup_entry(hass: HomeAssistant, entry: SparkSyncConfigEntry) -> bool:
<<<<<<< Updated upstream
    if entry.data.get(CONF_MODE) == MODE_MQTT:
        hub = SparkSyncMeterHub(hass, entry)
        await hub.async_start()
        entry.async_on_unload(hub.async_stop)
        entry.runtime_data = hub
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        return True
=======
    if not await mqtt.async_wait_for_mqtt_client(hass):
        raise ConfigEntryNotReady("MQTT integration is not available")
>>>>>>> Stashed changes

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
        coordinator = SparkSyncCoordinator(hass, entry, device)
        await coordinator.async_subscribe()
        coordinators.append(coordinator)

    entry.runtime_data = coordinators
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SparkSyncConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
