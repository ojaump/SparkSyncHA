"""Meter topic parsing and the silence-is-a-fault rule."""

import importlib.util
import pathlib

_spec = importlib.util.spec_from_file_location(
    "sparksync_const",
    pathlib.Path(__file__).parent.parent / "custom_components/sparksync/const.py",
)
const = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(const)

BASE = "SparkSync/Meter"
MAC = "10bda3b04dbc"
NOW = 1783365156.0


def test_data_topic():
    assert const.parse_meter_topic(BASE, f"{BASE}/{MAC}") == (MAC, False)


def test_status_topic():
    assert const.parse_meter_topic(BASE, f"{BASE}/{MAC}/status") == (MAC, True)


def test_foreign_topics_ignored():
    # `+` does not match /status, but a wildcard subscriber can still be handed
    # anything — never treat a stray topic as a node.
    assert const.parse_meter_topic(BASE, "Other/Meter/abc") is None
    assert const.parse_meter_topic(BASE, BASE) is None
    assert const.parse_meter_topic(BASE, f"{BASE}/{MAC}/status/extra") is None
    assert const.parse_meter_topic(BASE, f"{BASE}/") is None


def test_fresh_while_publishing():
    assert const.meter_is_fresh(True, NOW - 5, NOW)


def test_silent_node_is_stale_even_though_status_says_online():
    # RS-485 dies, Wi-Fi stays up: `online` is retained but no data arrives.
    assert not const.meter_is_fresh(True, NOW - const.METER_STALE_AFTER_S - 1, NOW)


def test_offline_and_never_seen():
    assert not const.meter_is_fresh(False, NOW, NOW)
    assert not const.meter_is_fresh(True, None, NOW)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
