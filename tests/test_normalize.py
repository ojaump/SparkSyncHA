"""MQTT is raw per-controller; these pin the mapping onto /info's vocabulary.

Field names come from SparkS-Gate: src/iot/telemetry_builder.cpp (DSE) and
src/easygen/easygen_driver.cpp (EasyGen).
"""

import importlib.util
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).parent.parent / "custom_components/sparksync"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


pkg = types.ModuleType("sparksync")
pkg.__path__ = [str(ROOT)]
sys.modules["sparksync"] = pkg
const = _load("sparksync.const", ROOT / "const.py")
normalize = _load("sparksync.normalize", ROOT / "normalize.py").normalize

# Every field the sensor platform reads, by section.
SENSOR_FIELDS = {
    "generator": [
        "total_power_w", "frequency_hz", "av_wye_voltage_v",
        "av_current_a", "power_factor", "percent_full_power",
    ],
    "mains": ["total_power_w"],
    "engine": [
        "engine_speed_rpm", "oil_pressure_kpa", "coolant_temperature_c",
        "oil_temperature_c", "oil_level_percent", "coolant_level_percent",
        "battery_voltage_v", "fuel_consumption_lph",
    ],
    "accumulated": [
        "gen_positive_kwh", "engine_run_time_seconds", "number_of_starts",
    ],
    "status": ["control_mode"],
}


def test_dse_renames():
    gen = normalize("generator", {"total_watts_w": 144799, "pf_average": 0.962,
                                  "percent_full_power": 72.4})
    assert gen["total_power_w"] == 144799
    assert gen["power_factor"] == 0.962
    # DSE mains uses pf_l1: its pf_average is pf_l1/3 on a single-CT install.
    assert normalize("mains", {"total_watts_w": -48141, "pf_l1": 0.854})["power_factor"] == 0.854
    assert normalize("engine", {"battery_voltage": 28.1})["battery_voltage_v"] == 28.1


def test_easygen_renames_and_unit_conversions():
    eng = normalize("engine", {"fuel_rate_lph": 31.5, "battery_voltage_v": 28.1})
    assert eng["fuel_consumption_lph"] == 31.5
    acc = normalize("accumulated", {
        "engine_starts": 11858,
        "gen_real_energy_mwh": 2287.86987,      # MWh -> kWh
        "gen_hours_of_operation_h": 26720.75,   # h  -> s
    })
    assert acc["number_of_starts"] == 11858
    assert round(acc["gen_positive_kwh"], 2) == 2287869.87
    assert acc["engine_run_time_seconds"] == 26720.75 * 3600


def test_easygen_percent_full_power_is_derived():
    # EasyGen has no load-percent register; /info derives it from rated power.
    gen = normalize("generator", {"total_power_w": 144799, "rated_active_power_kw": 200})
    assert gen["percent_full_power"] == 72.4


def test_canonical_payload_is_left_alone():
    # EasyGen already speaks canonical; an alias must never clobber a real value.
    gen = normalize("generator", {"total_power_w": 1000, "total_watts_w": 9999})
    assert gen["total_power_w"] == 1000


def test_null_is_never_coerced_to_zero():
    # The gateway emits null for "no reading" -- charting it as 0 invents data.
    assert normalize("engine", {"battery_voltage": None}).get("battery_voltage_v") is None
    assert normalize("accumulated", {"gen_real_energy_mwh": None}).get("gen_positive_kwh") is None
    gen = normalize("generator", {"total_power_w": None, "rated_active_power_kw": 200})
    assert gen.get("percent_full_power") is None
    # Rated power of 0 must not divide by zero.
    assert normalize("generator", {"total_power_w": 500, "rated_active_power_kw": 0}) \
        .get("percent_full_power") is None


def test_junk_payload_does_not_crash():
    assert normalize("accumulated", {"gen_real_energy_mwh": "N/A"}).get("gen_positive_kwh") is None
    assert normalize("generator", {}) == {}
    assert normalize("unknown-section", {"a": 1}) == {"a": 1}


def test_every_sensor_field_is_reachable_from_both_controllers():
    """The real contract: each sensor must resolve on DSE and on EasyGen."""
    dse = {
        "generator": {"total_watts_w": 1, "frequency_hz": 1, "av_wye_voltage_v": 1,
                      "av_current_a": 1, "pf_average": 1, "percent_full_power": 1},
        "mains": {"total_watts_w": 1},
        "engine": {"engine_speed_rpm": 1, "oil_pressure_kpa": 1, "coolant_temperature_c": 1,
                   "oil_temperature_c": 1, "oil_level_percent": 1, "coolant_level_percent": 1,
                   "battery_voltage": 1, "fuel_consumption_lph": 1},
        "accumulated": {"gen_positive_kwh": 1, "engine_run_time_seconds": 1,
                        "number_of_starts": 1},
        "status": {"control_mode": "Auto"},
    }
    easygen = {
        "generator": {"total_power_w": 1, "frequency_hz": 1, "av_wye_voltage_v": 1,
                      "av_current_a": 1, "pf_average": 1, "rated_active_power_kw": 1},
        "mains": {"total_power_w": 1},
        "engine": {"engine_speed_rpm": 1, "oil_pressure_kpa": 1, "coolant_temperature_c": 1,
                   "oil_temperature_c": 1, "oil_level_percent": 1, "coolant_level_percent": 1,
                   "battery_voltage_v": 1, "fuel_rate_lph": 1},
        "accumulated": {"gen_real_energy_mwh": 1, "gen_hours_of_operation_h": 1,
                        "engine_starts": 1},
        "status": {"control_mode": "AUTO"},
    }
    for label, raw in (("dse", dse), ("easygen", easygen)):
        for section, fields in SENSOR_FIELDS.items():
            out = normalize(section, raw[section])
            for field in fields:
                assert out.get(field) is not None, f"{label}: {section}.{field} unresolved"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
