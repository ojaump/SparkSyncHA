"""MQTT meter mode: one broker connection, one coordinator per node MAC."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import timedelta
from typing import Any

import paho.mqtt.client as mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo, format_mac
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_BASE_TOPIC,
    CONF_TLS,
    CONF_WEBSOCKET,
    CONF_WS_PATH,
    DEFAULT_WS_PATH,
    DOMAIN,
    meter_is_fresh,
    parse_meter_topic,
)

_LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT_S = 10
# CONNACK codes for bad credentials / not authorized, MQTT 3.1.1 and 5.
AUTH_FAILURE_CODES = frozenset({4, 5, 134, 135})
STALE_CHECK = 5


def _build_client(conf: dict[str, Any], client_id: str) -> mqtt.Client:
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=client_id,
        transport="websockets" if conf.get(CONF_WEBSOCKET) else "tcp",
    )
    if conf.get(CONF_WEBSOCKET):
        client.ws_set_options(path=conf.get(CONF_WS_PATH) or DEFAULT_WS_PATH)
    if conf.get(CONF_TLS):
        client.tls_set()
    if conf.get(CONF_USERNAME):
        client.username_pw_set(conf[CONF_USERNAME], conf.get(CONF_PASSWORD) or "")
    return client


def validate(conf: dict[str, Any]) -> str | None:
    """Blocking connect probe. Returns an error key or None. Run in an executor."""
    codes: list[int] = []
    done = threading.Event()
    client = _build_client(conf, f"ha-sparksync-probe-{os.urandom(4).hex()}")

    def on_connect(_client, _userdata, _flags, reason_code, _props=None) -> None:
        codes.append(getattr(reason_code, "value", reason_code))
        done.set()

    client.on_connect = on_connect
    try:
        client.connect(conf[CONF_HOST], conf[CONF_PORT], keepalive=CONNECT_TIMEOUT_S)
        client.loop_start()
        if not done.wait(CONNECT_TIMEOUT_S):
            return "cannot_connect"
    except Exception as err:  # noqa: BLE001 - paho raises OSError, ssl, websocket errors
        _LOGGER.debug("MQTT probe failed: %s", err)
        return "cannot_connect"
    finally:
        client.loop_stop()
        client.disconnect()
    if codes[0] == 0:
        return None
    return "invalid_auth" if codes[0] in AUTH_FAILURE_CODES else "cannot_connect"


class SparkSyncMeterCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Push coordinator for one meter node. No polling: messages drive it."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, mac: str) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=f"SparkSync Meter {mac}")
        self.mac = mac
        self.online = True
        self.last_message: float | None = None
        self.was_fresh = False

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.mac)},
            connections={(CONNECTION_NETWORK_MAC, format_mac(self.mac))},
            name=f"SparkSync Meter {self.mac[-6:]}",
            manufacturer="SparkSync",
            model="3-phase meter",
        )

    @property
    def data_is_fresh(self) -> bool:
        return meter_is_fresh(self.online, self.last_message, time.monotonic())


class SparkSyncMeterHub:
    """Owns the broker connection and the per-node coordinators."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.base = entry.data[CONF_BASE_TOPIC].rstrip("/")
        self.coordinators: dict[str, SparkSyncMeterCoordinator] = {}
        self.new_node_signal = f"{DOMAIN}_new_meter_{entry.entry_id}"
        self._client: mqtt.Client | None = None

    async def async_start(self) -> None:
        # tls_set() reads the CA bundle off disk - keep it out of the event loop.
        self._client = await self.hass.async_add_executor_job(
            _build_client, self.entry.data, f"ha-sparksync-{self.entry.entry_id[:8]}"
        )
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.connect_async(
            self.entry.data[CONF_HOST], self.entry.data[CONF_PORT], keepalive=60
        )
        self._client.loop_start()
        self.entry.async_on_unload(
            async_track_time_interval(
                self.hass, self._async_check_stale, timedelta(seconds=STALE_CHECK)
            )
        )

    async def async_stop(self) -> None:
        self._client.disconnect()
        await self.hass.async_add_executor_job(self._client.loop_stop)

    # -- paho callbacks run on the network thread -------------------------

    def _on_connect(self, client, _userdata, _flags, reason_code, _props=None) -> None:
        if getattr(reason_code, "value", reason_code) != 0:
            _LOGGER.error("MQTT connection refused: %s", reason_code)
            return
        client.subscribe([(f"{self.base}/+", 0), (f"{self.base}/+/status", 0)])

    def _on_message(self, _client, _userdata, msg: mqtt.MQTTMessage) -> None:
        parsed = parse_meter_topic(self.base, msg.topic)
        if parsed is None:
            return
        mac, is_status = parsed
        if is_status:
            payload: Any = msg.payload.decode(errors="replace").strip().lower() == "online"
        else:
            try:
                payload = json.loads(msg.payload)
            except ValueError:
                _LOGGER.warning("Bad JSON on %s", msg.topic)
                return
            if not isinstance(payload, dict):
                return
        self.hass.loop.call_soon_threadsafe(self._handle, mac, is_status, payload)

    # -- event loop -------------------------------------------------------

    @callback
    def _handle(self, mac: str, is_status: bool, payload: Any) -> None:
        coordinator = self.coordinators.get(mac)
        if coordinator is None:
            coordinator = SparkSyncMeterCoordinator(self.hass, self.entry, mac)
            self.coordinators[mac] = coordinator
            async_dispatcher_send(self.hass, self.new_node_signal)
        if is_status:
            coordinator.online = payload
            coordinator.was_fresh = coordinator.data_is_fresh
            coordinator.async_update_listeners()
            return
        coordinator.last_message = time.monotonic()
        coordinator.was_fresh = True
        coordinator.async_set_updated_data(payload)

    @callback
    def _async_check_stale(self, _now) -> None:
        """A node that just goes quiet must not keep showing its last reading."""
        for coordinator in self.coordinators.values():
            fresh = coordinator.data_is_fresh
            if fresh != coordinator.was_fresh:
                coordinator.was_fresh = fresh
                coordinator.async_update_listeners()
