"""Topic parsing and the rule that silence means stale, for both device kinds."""

import importlib.util
import pathlib

# Import const.py directly - the package __init__ needs homeassistant installed.
_spec = importlib.util.spec_from_file_location(
    "sparksync_const",
    pathlib.Path(__file__).parent.parent / "custom_components/sparksync/const.py",
)
const = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(const)

METER = "SparkSync/Meter"
MAC = "10bda3b04dbc"
GATEWAY = "devices"
NODE = "esp32-0070077e744c"
NOW = 1783365156.0


def test_meter_topics():
    assert const.device_id_from_topic(METER, f"{METER}/{MAC}") == MAC
    assert const.device_id_from_topic(METER, f"{METER}/{MAC}/status") == MAC


def test_gateway_topics():
    assert const.device_id_from_topic(GATEWAY, f"{GATEWAY}/{NODE}/generator") == NODE
    assert const.device_id_from_topic(GATEWAY, f"{GATEWAY}/{NODE}/lwt") == NODE


def test_foreign_topics_ignored():
    # A wildcard subscriber can be handed anything; never invent a device from it.
    assert const.device_id_from_topic(METER, "Other/Meter/abc") is None
    assert const.device_id_from_topic(METER, METER) is None
    assert const.device_id_from_topic(METER, f"{METER}/") is None
    assert const.device_id_from_topic(METER, f"{METER}//status") is None
    # The replay lane: `+/+` excludes it, and so does this.
    assert const.device_id_from_topic(GATEWAY, f"{GATEWAY}/{NODE}/generator/backfill") is None


def test_fresh_while_publishing():
    assert const.is_fresh(True, NOW - 5, NOW, const.METER_STALE_AFTER_S)


def test_silent_device_is_stale_even_though_status_says_online():
    # RS-485 dies, Wi-Fi stays up: `online` is retained but no reading arrives.
    stale = NOW - const.METER_STALE_AFTER_S - 1
    assert not const.is_fresh(True, stale, NOW, const.METER_STALE_AFTER_S)
    # The gateway gets a longer rope: 30 missed 1 Hz frames.
    assert const.is_fresh(True, stale, NOW, const.GATEWAY_STALE_AFTER_S)


def test_offline_and_never_seen():
    assert not const.is_fresh(False, NOW, NOW, const.METER_STALE_AFTER_S)
    assert not const.is_fresh(True, None, NOW, const.METER_STALE_AFTER_S)


def test_retained_frame_keeps_its_own_timestamp():
    # A dead gateway's last words replay on reconnect; `ts` is what exposes them.
    assert const.seen_at(NOW - 600, NOW) == NOW - 600
    assert not const.is_fresh(True, const.seen_at(NOW - 600, NOW), NOW, const.GATEWAY_STALE_AFTER_S)


def test_unusable_ts_falls_back_to_arrival():
    # Millis, uptime seconds, an unset clock, or no ts at all: use arrival time
    # rather than reading a wrong unit as a timestamp.
    for ts in (None, "now", True, NOW * 1000, 12345, 0):
        assert const.seen_at(ts, NOW) == NOW


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
