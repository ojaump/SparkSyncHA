"""Map raw gateway MQTT payloads onto the canonical vocabulary /info speaks.

The REST API normalizes DSE and EasyGen payloads at ingest; MQTT is raw, so the
same mapping has to happen here instead. This mirrors the canonical field table
in ROUTES.md -- when the backend gains a controller variant, this table needs
the matching entries or those sensors go quiet.

Pure, no Home Assistant imports, so it is testable on its own.
"""

from __future__ import annotations

from typing import Any

# (raw field published by the gateway, canonical field, scale)
_ALIASES: dict[str, tuple[tuple[str, str, float], ...]] = {
    "generator": (
        ("total_watts_w", "total_power_w", 1.0),  # DSE
        ("pf_average", "power_factor", 1.0),  # DSE + EasyGen
    ),
    "mains": (
        ("total_watts_w", "total_power_w", 1.0),  # DSE
        # DSE mains has a single CT, so the controller's pf_average is pf_l1/3.
        ("pf_l1", "power_factor", 1.0),
        ("pf_average", "power_factor", 1.0),  # EasyGen
    ),
    "engine": (
        ("battery_voltage", "battery_voltage_v", 1.0),  # DSE
        ("fuel_rate_lph", "fuel_consumption_lph", 1.0),  # EasyGen
    ),
    "accumulated": (
        ("engine_starts", "number_of_starts", 1.0),  # EasyGen
        ("gen_real_energy_mwh", "gen_positive_kwh", 1000.0),  # EasyGen, MWh -> kWh
        ("gen_hours_of_operation_h", "engine_run_time_seconds", 3600.0),  # h -> s
    ),
}


def normalize(section: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Add canonical keys to one raw section payload. Raw keys are kept."""
    out = dict(payload)
    for raw, canonical, scale in _ALIASES.get(section, ()):
        if out.get(canonical) is not None:
            continue  # this controller already speaks canonical
        value = out.get(raw)
        if value is None:
            continue  # null means "no reading" -- never coerce it to 0
        if scale != 1.0:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue  # payloads come off the wire; do not multiply junk
            value = value * scale
        out[canonical] = value
    if section == "generator":
        _derive_percent_full_power(out)
    return out


def _derive_percent_full_power(gen: dict[str, Any]) -> None:
    """EasyGen has no load-percent register; /info derives it from rated power."""
    if gen.get("percent_full_power") is not None:
        return
    rated_kw = gen.get("rated_active_power_kw")
    watts = gen.get("total_power_w")
    if not rated_kw or watts is None:
        return
    if not isinstance(rated_kw, (int, float)) or not isinstance(watts, (int, float)):
        return
    gen["percent_full_power"] = round(watts / (rated_kw * 1000.0) * 100.0, 1)
