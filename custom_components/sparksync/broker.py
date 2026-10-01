"""One MQTT connection, fanned out to one coordinator per device id.

Gateways and meters differ only in their topic shape and payload, so the
connection, the device registry and the staleness ticker live here once.
"""

from __future__ import annotations

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
    device_id_from_topic,
    is_fresh,
)

_LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT_S = 10
# CONNACK codes for bad credentials / not authorized, MQTT 3.1.1 and 5.
AUTH_FAILURE_CODES = frozenset({4, 5, 134, 135})
# How often availability is re-evaluated for a device that went quiet.
STALE_CHECK_S = 5


def build_client(conf: dict[str, Any], client_id: str) -> mqtt.Client:
    """Blocking: tls_set() reads the CA bundle off disk. Run in an executor."""
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
    client = build_client(conf, f"ha-sparksync-probe-{os.urandom(4).hex()}")

    def on_connect(_client, _userdata, _flags, reason_code, _props=None) -> None:
        codes.append(getattr(reason_code, "value", reason_code))
        done.set()

    client.on_connect = on_connect
    try:
        client.connect(conf[CONF_HOST], conf[CONF_PORT], keepalive=CONNECT_TIMEOUT_S)
        client.loop_start()
        if not done.wait(CONNECT_TIMEOUT_S):
            return "cannot_connect"
    except Exception as err:  # noqa: BLE001 - paho raises OSError, ssl and websocket errors
        _LOGGER.debug("MQTT probe failed: %s", err)
        return "cannot_connect"
    finally:
        client.loop_stop()
        client.disconnect()
    if codes[0] == 0:
        return None
    return "invalid_auth" if codes[0] in AUTH_FAILURE_CODES else "cannot_connect"


class PushCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """One device. Messages drive it; there is nothing to poll."""

    # Topic filters this kind of device publishes on, relative to the base topic.
    topics: tuple[str, ...] = ()
    stale_after: float = 30.0

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, device_id: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"SparkSync {device_id}",
            update_interval=None,
        )
        self.device_id = device_id
        self.online = True  # until a retained status/LWT says otherwise
        self.last_message: float | None = None
        self.was_fresh = False

    @property
    def data_is_fresh(self) -> bool:
        return is_fresh(self.online, self.last_message, time.monotonic(), self.stale_after)

    @callback
    def handle(self, topic: str, payload: bytes) -> None:
        """Fold one message into this device's state. Runs in the event loop."""
        raise NotImplementedError


class BrokerHub:
    """Owns the broker connection and the coordinators discovered under it."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator_class: type[PushCoordinator],
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.base = entry.data[CONF_BASE_TOPIC].rstrip("/")
        self.coordinator_class = coordinator_class
        self.coordinators: dict[str, PushCoordinator] = {}
        self.new_device_signal = f"{DOMAIN}_new_device_{entry.entry_id}"
        self._client: mqtt.Client | None = None

    async def async_start(self) -> None:
        self._client = await self.hass.async_add_executor_job(
            build_client, self.entry.data, f"ha-sparksync-{self.entry.entry_id[:8]}"
        )
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.connect_async(
            self.entry.data[CONF_HOST], self.entry.data[CONF_PORT], keepalive=60
        )
        self._client.loop_start()
        self.entry.async_on_unload(
            async_track_time_interval(
                self.hass, self._async_check_stale, timedelta(seconds=STALE_CHECK_S)
            )
        )

    async def async_stop(self) -> None:
        if self._client is None:
            return
        self._client.disconnect()
        await self.hass.async_add_executor_job(self._client.loop_stop)

    # -- paho callbacks run on the network thread -------------------------

    def _on_connect(self, client, _userdata, _flags, reason_code, _props=None) -> None:
        if getattr(reason_code, "value", reason_code) != 0:
            _LOGGER.error("MQTT connection refused: %s", reason_code)
            return
        # Subscribing here, not after connect, so a reconnect re-subscribes.
        client.subscribe([(f"{self.base}/{t}", 0) for t in self.coordinator_class.topics])

    def _on_message(self, _client, _userdata, msg: mqtt.MQTTMessage) -> None:
        self.hass.loop.call_soon_threadsafe(self._handle, msg.topic, msg.payload)

    # -- event loop -------------------------------------------------------

    @callback
    def _handle(self, topic: str, payload: bytes) -> None:
        device_id = device_id_from_topic(self.base, topic)
        if device_id is None:
            return
        coordinator = self.coordinators.get(device_id)
        if coordinator is None:
            coordinator = self.coordinator_class(self.hass, self.entry, device_id)
            self.coordinators[device_id] = coordinator
            async_dispatcher_send(self.hass, self.new_device_signal)
        coordinator.handle(topic, payload)

    @callback
    def _async_check_stale(self, _now) -> None:
        """A device that just goes quiet must not keep showing its last reading."""
        for coordinator in self.coordinators.values():
            fresh = coordinator.data_is_fresh
            if fresh != coordinator.was_fresh:
                coordinator.was_fresh = fresh
                coordinator.async_update_listeners()
