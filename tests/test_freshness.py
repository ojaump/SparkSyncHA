"""Freshness gate: /info keeps serving the last snapshot after a gateway dropout."""

import importlib.util
import pathlib

# Import const.py directly — the package __init__ needs homeassistant installed.
_spec = importlib.util.spec_from_file_location(
    "sparksync_const",
    pathlib.Path(__file__).parent.parent / "custom_components/sparksync/const.py",
)
const = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(const)

NOW = 1783365156.0


def test_fresh():
    assert const.is_fresh({"is_online": True, "controller_online": True, "last_seen": NOW - 5}, NOW)


def test_gateway_dropout():
    # Gateway silent past the window: kW must go unavailable, not hold its last value.
    meta = {"is_online": True, "controller_online": True, "last_seen": NOW - const.STALE_AFTER_S - 1}
    assert not const.is_fresh(meta, NOW)


def test_controller_unreachable():
    # Gateway online but Modbus dead — values are stale too.
    assert not const.is_fresh({"controller_online": False, "last_seen": NOW}, NOW)


def test_falls_back_to_server_flag_without_last_seen():
    assert const.is_fresh({"is_online": True}, NOW)
    assert not const.is_fresh({"is_online": False}, NOW)


def test_empty_meta_is_not_stale():
    # No _meta (older backend) must not make every entity unavailable.
    assert const.is_fresh({}, NOW)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
