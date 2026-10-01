"""Generator gateways: `<base>/<device id>/<section>`, one JSON section per topic."""

from __future__ import annotations

import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
    format_mac,
)
from homeassistant.util.json import json_loads_object

from .broker import PushCoordinator
from .const import DOMAIN, GATEWAY_STALE_AFTER_S, PUSH_INTERVAL_S, is_fresh, seen_at
from .normalize import normalize

_LOGGER = logging.getLogger(__name__)


class SparkSyncGatewayCoordinator(PushCoordinator):
    """Assembles one generator's telemetry sections into the /info shape."""

    # A single-level `+` deliberately does not match `<section>/backfill`, so the
    # replay lane cannot overwrite live state.
    topics = ("+/+",)
    stale_after = GATEWAY_STALE_AFTER_S

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, device_id: str) -> None:
        super().__init__(hass, entry, device_id)
        self.online = False  # until the retained LWT says otherwise
        self.controller_online = True
        self._sections: dict[str, dict[str, Any]] = {}
        self._debouncer = Debouncer(
            hass,
            _LOGGER,
            cooldown=PUSH_INTERVAL_S,
            immediate=True,
            function=self._async_push,
        )

    @property
    def device_info(self) -> DeviceInfo:
        info = DeviceInfo(
            identifiers={(DOMAIN, self.device_id)},
            name=self.device_id,
            manufacturer="SparkSync",
            model="Generator gateway",
        )
        mac = self.device_id.rpartition("-")[2]
        if len(mac) == 12:
            info["connections"] = {(CONNECTION_NETWORK_MAC, format_mac(mac))}
        return info

    @property
    def data_is_fresh(self) -> bool:
        # Wall clock, because `last_message` is the publisher's own timestamp.
        return self.controller_online and is_fresh(
            self.online, self.last_message, time.time(), self.stale_after
        )

    @callback
    def handle(self, topic: str, payload: bytes) -> None:
        section = topic.rpartition("/")[2]
        try:
            data = json_loads_object(payload)
        except ValueError:
            _LOGGER.debug("%s: unparseable payload on %s", self.name, topic)
            return
        # Belt and braces: the wildcard already excludes the replay lane.
        if data.get("_backfill") or (data.get("_meta") or {}).get("is_backfill"):
            return

        if section == "lwt":
            self.online = bool(data.get("online"))
        elif section == "health":
            return  # the gateway's own telemetry, not the generator's
        else:
            self._sections[section] = normalize(section, data)
            self.controller_online = bool(data.get("controller_online", True))
            self.last_message = seen_at(data.get("ts"), time.time())
        self._debouncer.async_schedule_call()

    async def _async_push(self) -> None:
        self.was_fresh = self.data_is_fresh
        self.async_set_updated_data(dict(self._sections))
