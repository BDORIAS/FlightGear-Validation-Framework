"""Unit tests for console registry, environment, telemetry, and process helpers."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from flightgear_framework.console_app.env_manager import EnvManager
from flightgear_framework.console_app.process_manager import ProcessManager
from flightgear_framework.console_app.profiles import TestProfile
from flightgear_framework.console_app.registry import TestRegistry
from flightgear_framework.console_app.telemetry import TelemetryTailer
from flightgear_framework import native


def test_registry_contains_engine_failure_profile():
    registry = TestRegistry(PROJECT_ROOT)
    profile = registry.get("cruise_engine_failure")

    assert profile.requires_flightgear is True
    assert profile.output_csv == "data/results/cruise_engine_failure.csv"
    assert any(field.key == "engine_rpm" for field in profile.primary_fields)


def test_registry_only_lists_source_testing_profiles():
    registry = TestRegistry(PROJECT_ROOT)
    profiles = registry.profiles()

    assert profiles
    assert all(
        profile.module
        and profile.module.startswith("flightgear_framework.testing.")
        for profile in profiles
    )
    assert "sensor_failure_scenarios" not in {profile.id for profile in profiles}
    assert not any(profile.id.startswith("pytest:") for profile in profiles)


def test_env_manager_prepares_console_environment(monkeypatch):
    monkeypatch.delenv("FG_ROOT", raising=False)

    manager = EnvManager(PROJECT_ROOT)
    env = manager.prepare_env()

    assert env["PROJECT_ROOT"] == str(PROJECT_ROOT)
    assert str(PROJECT_ROOT / "src") in env["PYTHONPATH"]
    assert "FG_ROOT" not in env
    assert env["FG_AIRCRAFT"]
    assert env["FLIGHTGEAR_NATIVE_BACKEND"] in {"cpp", "python"}


def test_env_export_skips_empty_flightgear_root(monkeypatch, tmp_path):
    monkeypatch.delenv("FG_ROOT", raising=False)

    manager = EnvManager(PROJECT_ROOT)
    exported_path = manager.export_env_file(tmp_path / ".env.console")

    contents = exported_path.read_text(encoding="utf-8")
    assert "FG_ROOT=" not in contents
    assert "FG_AIRCRAFT=" in contents


def test_env_manager_can_attempt_native_backend(monkeypatch):
    calls = []

    def fake_ensure_native_backend(project_root, *, python_executable):
        calls.append((project_root, python_executable))
        return {"status": "built", "message": "ok", "error": ""}

    monkeypatch.setattr(native, "ensure_native_backend", fake_ensure_native_backend)

    manager = EnvManager(PROJECT_ROOT)
    result = manager.ensure_native_backend()
    env = manager.prepare_env()

    assert calls == [(PROJECT_ROOT, manager.venv_python)]
    assert result["status"] == "built"
    assert env["FLIGHTGEAR_NATIVE_BUILD_STATUS"] == "built"


def test_env_manager_applies_flightgear_environment_overrides(monkeypatch):
    monkeypatch.setenv("FGFS_EXECUTABLE", "custom-fgfs")
    monkeypatch.setenv("FG_ROOT", "D:/FlightGear/data")
    monkeypatch.setenv("FG_AIRCRAFT", "ufo")
    monkeypatch.setenv("FG_AIRPORT", "KSFO")
    monkeypatch.setenv("FG_RUNWAY", "28L")
    monkeypatch.setenv("FG_HOST", "127.0.0.1")
    monkeypatch.setenv("FG_TELNET_PORT", "5505")
    monkeypatch.setenv("FG_RESPONSE_TIMEOUT", "2.5")
    monkeypatch.setenv("FG_DISABLE_TERRASYNC", "true")

    manager = EnvManager(PROJECT_ROOT)
    env = manager.prepare_env()
    simulator = manager.flightgear_simulator()
    connection = manager.flightgear_connection()

    assert simulator["executable"] == "custom-fgfs"
    assert simulator["data_dir"] == "D:/FlightGear/data"
    assert simulator["default_aircraft"] == "ufo"
    assert simulator["default_airport"] == "KSFO"
    assert simulator["default_runway"] == "28L"
    assert simulator["disable_terrasync"] is True
    assert connection["host"] == "127.0.0.1"
    assert connection["port"] == 5505
    assert connection["response_timeout"] == 2.5
    assert env["FG_ROOT"] == "D:/FlightGear/data"
    assert env["FG_TELNET_PORT"] == "5505"


def test_telemetry_tailer_reads_latest_row_and_profile_fields(tmp_path):
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text(
        "timestamp,phase,engine_rpm,airspeed_kts\n"
        "1,start,0,10\n"
        "2,run,700,55\n",
        encoding="utf-8",
    )
    profile = TestRegistry(PROJECT_ROOT).get("cruise_engine_failure")
    tailer = TelemetryTailer()

    latest = tailer.latest_row(csv_path)
    fields = tailer.selected_fields(profile, latest)

    assert latest["phase"] == "run"
    assert latest["engine_rpm"] == "700"
    assert fields[0].key == "phase"


def test_process_manager_runs_independent_process():
    manager = ProcessManager()
    profile = TestProfile(
        id="unit_process",
        name="Unit process",
        description="Short process for tests",
        command_args=("-c", "print('ok')"),
        requires_flightgear=False,
    )
    command = profile.command(Path(sys.executable))

    assert manager.start(profile, command, PROJECT_ROOT, {})
    manager.process.wait(timeout=5)
    manager.poll()

    assert manager.status_text() == "finished (0)"
    assert "ok" in "\n".join(manager.stdout_lines)
