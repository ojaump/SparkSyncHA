"""Meter nodes: `<base>/<mac>` carries the whole flat payload. See MQTT.md."""

from __future__ import annotations

import logging
import json
import time

from homeassistant.core import callback
from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
    format_mac,
)

from .broker import PushCoordinator
from .const import DOMAIN, METER_STALE_AFTER_S

_LOGGER = logging.getLogger(__name__)


class SparkSyncMeterCoordinator(PushCoordinator):
    """One meter node. Every message is a complete reading."""

    topics = ("+", "+/status")
    stale_after = METER_STALE_AFTER_S

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.device_id)},
            connections={(CONNECTION_NETWORK_MAC, format_mac(self.device_id))},
            name=f"SparkSync Meter {self.device_id[-6:]}",
            manufacturer="SparkSync",
            model="3-phase meter",
        )

    @callback
    def handle(self, topic: str, payload: bytes) -> None:
        # The status topic is retained and says only that Wi-Fi is up; arrival of
        # a reading is the only proof the Modbus side is alive.
        if topic.endswith("/status"):
            self.online = payload.decode(errors="replace").strip().lower() == "online"
            self.was_fresh = self.data_is_fresh
            self.async_update_listeners()
            return
        try:
            data = json.loads(payload)
        except ValueError:
            _LOGGER.warning("Bad JSON on %s", topic)
            return
        if not isinstance(data, dict):
            return
        self.last_message = time.monotonic()
        self.was_fresh = True
        self.async_set_updated_data(data)
