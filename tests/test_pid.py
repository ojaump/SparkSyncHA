"""Export PID: the loop that steers a real generator, so it gets checked."""

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


# pid.py does `from .const import ...`; give it a package without the HA-importing __init__.
pkg = types.ModuleType("sparksync")
pkg.__path__ = [str(ROOT)]
sys.modules["sparksync"] = pkg
const = _load("sparksync.const", ROOT / "const.py")
pid_mod = _load("sparksync.pid", ROOT / "pid.py")
ExportPID = pid_mod.ExportPID

T = 1000.0  # epoch base


def armed(**kw):
    p = ExportPID(enabled=True, target_kw=100.0, **kw)
    p.start(50.0)  # generator already at 50 %
    return p


def test_off_by_default():
    assert not ExportPID().enabled
    assert ExportPID().step(0.0, T) is None


def test_bumpless_first_command():
    # At target, the first command equals where the generator already was.
    p = armed(kp=0.1, ki=0.0)
    assert p.step(100.0, T) == 50


def test_under_target_raises_load():
    # Exporting 80 kW against a 100 kW target => error +20 => +2 % at Kp 0.1.
    p = armed(kp=0.1, ki=0.0)
    assert p.step(80.0, T) == 52


def test_over_target_lowers_load():
    p = armed(kp=0.1, ki=0.0)
    assert p.step(130.0, T) == 47


def test_integral_accumulates_toward_target():
    p = armed(kp=0.0, ki=0.01)
    p.step(90.0, T)  # dt == 0 on the first step, integral untouched
    assert p.step(90.0, T + 20) == 52  # 50 + 0.01 * 10 * 20


def test_clamped_to_max_percent():
    p = armed(kp=1.0, ki=0.0, max_percent=60.0)
    assert p.step(0.0, T) == 60


def test_no_windup_while_saturated():
    p = armed(kp=0.0, ki=0.1, max_percent=55.0)
    for i in range(1, 20):
        p.step(0.0, T + i * 20)
    assert p.integral <= 55.0
    # Once the error reverses the loop comes straight back down, rather than
    # sitting at the ceiling while a huge integral unwinds.
    assert p.step(300.0, T + 400) == 0


def test_rate_limited_and_deadbanded():
    p = armed(kp=0.1, ki=0.0)
    assert p.step(80.0, T) == 52
    assert p.step(60.0, T + 5) is None  # inside the 15 s write window
    assert p.step(80.0, T + 30) is None  # window open but the command did not move
    assert p.step(60.0, T + 30) == 54


def test_holds_at_ceiling_without_winding_up():
    # Export far below target and the ceiling set to 70 %: the loop pins there.
    p = armed(kp=0.5, ki=0.05, max_percent=70.0)
    for i in range(1, 30):
        p.step(0.0, T + i * 20)
    assert p.integral <= 70.0
    assert p.last_written == 70
    assert p.at_max
    # Load frees up: off the ceiling on the very next step, no unwind lag.
    assert p.step(200.0, T + 600) < 70
    assert not p.at_max


def test_reasserts_command_periodically():
    p = armed(kp=0.1, ki=0.0)
    assert p.step(80.0, T) == 52
    assert p.step(80.0, T + 60) is None
    # The ceiling could have been changed from the SparkSync app meanwhile.
    assert p.step(80.0, T + 200) == 52


def test_stop_disarms():
    p = armed(kp=0.1, ki=0.0)
    p.stop()
    assert not p.running
    assert p.step(0.0, T + 100) is None


def test_custom_meter_units():
    # A more precise meter can report in W, kW or MW.
    assert const.sensor_export_kw("101500", "W", 2) == 101.5
    assert const.sensor_export_kw("101.5", "kW", 2) == 101.5
    assert const.sensor_export_kw("0.1015", "MW", 2) == 101.5


def test_custom_meter_unusable_readings_hold_the_loop():
    # Every one of these must be None so the caller holds instead of steering.
    assert const.sensor_export_kw("unavailable", "kW", 2) is None
    assert const.sensor_export_kw("unknown", "kW", 2) is None
    assert const.sensor_export_kw(None, "kW", 2) is None
    assert const.sensor_export_kw("101.5", "A", 2) is None       # not a power unit
    assert const.sensor_export_kw("101.5", None, 2) is None
    assert const.sensor_export_kw("not a number", "kW", 2) is None
    # Meter integration died but HA kept the last state — same trap as the gateway.
    assert const.sensor_export_kw("101.5", "kW", const.STALE_AFTER_S + 1) is None


def test_export_sign():
    # /info reports mains import-positive: -48141 W is 48 kW leaving the site.
    assert const.export_kw({"total_power_w": -48141}) == 48.141
    assert const.export_kw({"total_power_w": None}) is None


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
