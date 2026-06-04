"""Unit tests for the simple FlightGear connection runner."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from flightgear_framework.testing.test_runner import TestRunner  # noqa: E402


class FakeSimulator:
    def __init__(self, start_result: bool = True):
        self.start_result = start_result
        self.last_startup_error = None
        self.started_with: dict | None = None
        self.stopped = False

    def start(self, custom_args, wait_for_start, timeout):
        self.started_with = {
            "custom_args": custom_args,
            "wait_for_start": wait_for_start,
            "timeout": timeout,
        }
        return self.start_result

    def stop(self):
        self.stopped = True
        return True


class FakeProtocol:
    def __init__(self, values: dict[str, list[str | None]], connect_result: bool = True):
        self.port = 5401
        self.values = values
        self.connect_result = connect_result
        self.connected_with_timeout: int | None = None
        self.disconnected = False
        self.set_calls: list[tuple[str, float]] = []

    def connect(self, timeout):
        self.connected_with_timeout = timeout
        return self.connect_result

    def disconnect(self):
        self.disconnected = True

    def get_property(self, property_path):
        values = self.values.get(property_path, [])
        if not values:
            return None
        return values.pop(0)

    def set_property(self, property_path, value):
        self.set_calls.append((property_path, value))
        return True


def _runner(tmp_path: Path, monkeypatch) -> TestRunner:
    monkeypatch.setenv("FG_RESULTS_DIR", str(tmp_path))
    runner = TestRunner(
        {
            "flightgear": {
                "connection": {"response_timeout": 1.2},
                "simulator": {"default_runway": "29", "disable_terrasync": False},
            }
        }
    )
    runner.debug_txt_path = tmp_path / "debug.txt"
    runner.fg_process_log_path = tmp_path / "process.txt"
    return runner


def test_simple_runner_waits_70_seconds_and_verifies_throttle(monkeypatch, tmp_path):
    runner = _runner(tmp_path, monkeypatch)
    simulator = FakeSimulator()
    protocol = FakeProtocol(
        {
            runner.ALTITUDE_PROPERTY: ["157.5"],
            runner.THROTTLE_PROPERTY: ["0.301"],
        }
    )
    runner.simulator = simulator
    runner.protocol = protocol
    slept: list[float] = []
    monkeypatch.setattr("flightgear_framework.testing.test_runner.time.sleep", slept.append)

    assert runner.run_simple_connect_test() is True

    assert slept == [70]
    assert simulator.started_with is not None
    assert "--runway=29" in simulator.started_with["custom_args"]
    assert "--disable-terrasync" not in simulator.started_with["custom_args"]
    assert protocol.set_calls == [(runner.THROTTLE_PROPERTY, runner.THROTTLE_TARGET_NORM)]
    assert protocol.disconnected is True
    assert simulator.stopped is True


def test_simple_runner_applies_flightgear_environment_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("FG_RESULTS_DIR", str(tmp_path))
    monkeypatch.setenv("FGFS_EXECUTABLE", "custom-fgfs")
    monkeypatch.setenv("FG_ROOT", "D:/FlightGear/data")
    monkeypatch.setenv("FG_AIRCRAFT", "ufo")
    monkeypatch.setenv("FG_AIRPORT", "KSFO")
    monkeypatch.setenv("FG_RUNWAY", "28L")
    monkeypatch.setenv("FG_TELNET_PORT", "5505")
    monkeypatch.setenv("FG_DISABLE_TERRASYNC", "true")

    runner = TestRunner(
        {
            "flightgear": {
                "connection": {"port": 5401},
                "simulator": {
                    "executable": "fgfs",
                    "data_dir": "",
                    "default_aircraft": "c172p",
                    "default_airport": "BIKF",
                    "default_runway": "29",
                    "disable_terrasync": False,
                },
            }
        }
    )

    assert runner.simulator.executable == "custom-fgfs"
    assert runner.simulator.data_dir == "D:/FlightGear/data"
    assert runner.simulator.aircraft == "ufo"
    assert runner.simulator.airport == "KSFO"
    assert runner.protocol.port == 5505
    assert "--runway=28L" in runner._build_flightgear_args()
    assert "--disable-terrasync" in runner._build_flightgear_args()


def test_simple_runner_rejects_empty_altitude_and_still_cleans_up(monkeypatch, tmp_path):
    runner = _runner(tmp_path, monkeypatch)
    simulator = FakeSimulator()
    protocol = FakeProtocol({runner.ALTITUDE_PROPERTY: [""]})
    runner.simulator = simulator
    runner.protocol = protocol
    monkeypatch.setattr("flightgear_framework.testing.test_runner.time.sleep", lambda _seconds: None)

    assert runner.run_simple_connect_test() is False

    assert protocol.set_calls == []
    assert protocol.disconnected is True
    assert simulator.stopped is True


def test_simple_runner_rejects_bad_throttle_readback(monkeypatch, tmp_path):
    runner = _runner(tmp_path, monkeypatch)
    simulator = FakeSimulator()
    protocol = FakeProtocol(
        {
            runner.ALTITUDE_PROPERTY: ["157.5"],
            runner.THROTTLE_PROPERTY: ["0.0"],
        }
    )
    runner.simulator = simulator
    runner.protocol = protocol
    monkeypatch.setattr("flightgear_framework.testing.test_runner.time.sleep", lambda _seconds: None)

    assert runner.run_simple_connect_test() is False

    assert protocol.set_calls == [(runner.THROTTLE_PROPERTY, runner.THROTTLE_TARGET_NORM)]
    assert protocol.disconnected is True
    assert simulator.stopped is True
