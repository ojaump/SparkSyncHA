"""Constants for the SparkSync integration."""

from __future__ import annotations

from typing import Any

DOMAIN = "sparksync"

# Gateway publishes to MQTT continuously; the backend's own `_meta.is_online`
# uses a 120 s window. Match it. Lower this to fail over faster.
STALE_AFTER_S = 120


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
