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


# --- Export regulation (PID) -------------------------------------------------

# `mains.total_power_w` is import-positive: the /info example pairs a generator
# producing +144799 W with mains at -48141 W, i.e. 48 kW flowing out to the grid.
# Flip to 1 if your site reports export as positive.
MAINS_EXPORT_SIGN = -1

DEFAULT_TARGET_KW = 100.0
DEFAULT_MAX_PERCENT = 100.0
# Conservative: %-of-load-level per kW of error. Rated power is not known here,
# so these are meant to be tuned in the field from the number entities.
DEFAULT_KP = 0.02
DEFAULT_KI = 0.005
DEFAULT_KD = 0.0  # ponytail: D on a noisy power reading usually hurts; left off.

# POST /load-level-max is rate-limited to 10/min, so the write cadence is
# decoupled from the 5 s poll: one write per 3 polls = 4/min, well under it.
# Do not drop below 6 s, and less if several generators share the limit.
MIN_WRITE_INTERVAL_S = 15
DEADBAND_PERCENT = 1.0  # the API takes whole percent
# Re-send the unchanged command this often, so a ceiling changed from the
# SparkSync app (or lost to a gateway reboot) does not sit there uncorrected.
RESYNC_INTERVAL_S = 120
MAX_DT_S = 60  # cap the integration step if HA was suspended or a poll was late


CONF_EXPORT_SENSORS = "export_sensors"

# A power meter reports one of these; anything else is refused rather than guessed.
POWER_TO_KW = {"W": 0.001, "kW": 1.0, "MW": 1000.0}


def sensor_export_kw(state: str | None, unit: str | None, age_s: float) -> float | None:
    """An external meter's reading in kW, positive when exporting.

    None means unusable — unknown, wrong unit, or stale — and the caller must then
    hold the loop rather than steer a generator on a reading that stopped moving.
    """
    if state in (None, "unknown", "unavailable") or age_s > STALE_AFTER_S:
        return None
    scale = POWER_TO_KW.get(unit)
    if scale is None:
        return None
    try:
        return float(state) * scale
    except (TypeError, ValueError):
        return None


def export_kw(mains: dict[str, Any]) -> float | None:
    """Grid export in kW, positive when exporting. None if not reported."""
    watts = mains.get("total_power_w")
    return None if watts is None else MAINS_EXPORT_SIGN * watts / 1000.0
