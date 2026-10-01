"""Constants for the SparkSync integration.

Pure helpers only -- no Home Assistant imports, so they stay testable on their own.
"""

from __future__ import annotations

from typing import Any

DOMAIN = "sparksync"

CONF_MODE = "mode"
MODE_GATEWAY = "gateway"
MODE_METER = "meter"

CONF_WEBSOCKET = "websocket"
CONF_WS_PATH = "ws_path"
CONF_TLS = "tls"
CONF_BASE_TOPIC = "base_topic"

DEFAULT_WS_PATH = "/mqtt"
DEFAULT_GATEWAY_TOPIC = "devices"
DEFAULT_METER_TOPIC = "SparkSync/Meter"

# The gateway publishes every telemetry section once per second, so 30 missed
# frames is decisively dead. Retained frames outlive the gateway, which is
# exactly what this guards against. Raise it if the link is flaky.
GATEWAY_STALE_AFTER_S = 30

# A meter node publishes every 5 s and only when the Modbus read succeeded:
# RS-485 can die while Wi-Fi stays up, so silence is a fault. Three cadences.
METER_STALE_AFTER_S = 15

# Sections arrive on 8 topics at 1 Hz; coalesce one tick into one push rather
# than writing entity states eight times a second.
PUSH_INTERVAL_S = 1.0

# A `ts` further than this from our clock is a different unit or a bad clock,
# not a timestamp.
TS_SANITY_S = 86400


def device_id_from_topic(base: str, topic: str) -> str | None:
    """The device segment of `<base>/<id>/...`, or None if the topic isn't ours.

    Both shapes land here: `devices/<id>/<section>` and `<base>/<mac>[/status]`.
    """
    if not topic.startswith(f"{base}/"):
        return None
    parts = topic[len(base) + 1 :].split("/")
    if len(parts) not in (1, 2) or not all(parts):
        return None
    return parts[0]


def seen_at(ts: Any, now: float) -> float:
    """When a frame was published: its own `ts` if sane, else arrival time.

    A retained frame carries the publisher's clock, and that is the only way a
    restart can tell a live gateway from a dead one replaying its last words.
    """
    if isinstance(ts, bool) or not isinstance(ts, (int, float)):
        return now
    return float(ts) if abs(now - ts) < TS_SANITY_S else now


def is_fresh(online: bool, last_message: float | None, now: float, stale_after: float) -> bool:
    """True only if the device says it is up *and* data actually arrived recently."""
    if not online or last_message is None:
        return False
    return now - last_message < stale_after
