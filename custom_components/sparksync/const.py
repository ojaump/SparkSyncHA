"""Constants for the SparkSync integration."""

from __future__ import annotations

import re
from typing import Any

DOMAIN = "sparksync"

# The gateway publishes every telemetry section once per second, so 30 missed
# frames is decisively dead. Retained MQTT frames outlive the device, which is
# exactly what this guards against. Raise it if the link is flaky.
STALE_AFTER_S = 30

# Sections arrive on 8 topics at 1 Hz; coalesce one poll tick into one push
# rather than writing entity states eight times a second.
PUSH_INTERVAL_S = 1.0


def mqtt_device_id(mac: str) -> str:
    """The gateway's MQTT topic id for a device: `esp32-<12 hex, lowercase>`.

    `/devices` may report the MAC colon-separated, bare, or already prefixed.
    """
    mac = mac.strip().lower()
    if mac.startswith("esp32-"):
        return mac
    return "esp32-" + re.sub(r"[^0-9a-f]", "", mac)


def is_fresh(meta: dict[str, Any], now: float) -> bool:
    """True if the /info snapshot is live, not the last value before a dropout.

    `meta` is the top-level `_meta` of a /info response, `now` epoch seconds.
    """
    # ponytail: no HA imports here so this stays testable without homeassistant.
    if not meta.get("controller_online", True):
        return False
    last_seen = meta.get("last_seen")
    if last_seen is None:
        return bool(meta.get("is_online", True))
    return now - last_seen < STALE_AFTER_S


# --- MQTT meter mode -------------------------------------------------------

CONF_MODE = "mode"
MODE_API = "api"
MODE_MQTT = "mqtt"

CONF_WEBSOCKET = "websocket"
CONF_WS_PATH = "ws_path"
CONF_TLS = "tls"
CONF_BASE_TOPIC = "base_topic"

DEFAULT_BASE_TOPIC = "SparkSync/Meter"
DEFAULT_WS_PATH = "/mqtt"

# A node publishes every 5 s and only when the Modbus read succeeded: RS-485 can
# die while Wi-Fi stays up, so silence is a fault. Three cadences.
METER_STALE_AFTER_S = 15


def parse_meter_topic(base: str, topic: str) -> tuple[str, bool] | None:
    """Split `<base>/<mac>[/status]` into (mac, is_status), or None if foreign."""
    if not topic.startswith(f"{base}/"):
        return None
    parts = topic[len(base) + 1 :].split("/")
    if len(parts) == 1 and parts[0]:
        return parts[0], False
    if len(parts) == 2 and parts[1] == "status" and parts[0]:
        return parts[0], True
    return None


def meter_is_fresh(online: bool, last_message: float | None, now: float) -> bool:
    """True only if the node says it is up *and* data actually arrived recently."""
    if not online or last_message is None:
        return False
    return now - last_message < METER_STALE_AFTER_S
