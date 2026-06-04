"""Unit tests for telemetry focusing, viewer payloads, and validation metrics."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from flightgear_framework.console_app.profiles import (  # noqa: E402
    EventWindow,
    PlotGroup,
    PlotSeries,
    TestProfile,
)
from flightgear_framework.console_app.registry import TestRegistry  # noqa: E402
from flightgear_framework.viewer.dataset import build_payload, load_dataset  # noqa: E402
from flightgear_framework.viewer.server import build_viewer_payload  # noqa: E402
from flightgear_framework.viewer.validation import compute_validation_metrics  # noqa: E402


def _write_engine_failure_csv(project_root: Path, filename: str = "sample.csv") -> None:
    results_dir = project_root / "data" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    csv_path = results_dir / filename
    start = datetime(2026, 1, 1, 12, 0, 0)
    rows = [
        (
            start + timedelta(seconds=second),
            "engine_failure_glide" if second >= 20 else "cruise_pre_failure",
            "" if second < 20 else str(second - 20),
            1800 - max(0, second - 20) * 60,
            "False" if second >= 28 else "True",
            70 - max(0, second - 20) * 0.2,
            0.5,
            "True",
            0.75 if second < 20 else 0.0,
            -0.03,
            0.02,
            0.01,
            0.0,
            1000 - max(0, second - 20) * 15,
            -500 if second >= 20 else 0,
        )
        for second in range(0, 61)
    ]
    csv_path.write_text(
        "timestamp,phase,engine_failure_elapsed_s,engine_rpm,engine_running,"
        "airspeed_kts,glide_airspeed_error_kts,telemetry_valid,"
        "throttle_norm,elevator_norm,aileron_norm,rudder_norm,flaps_norm,"
        "altitude_agl_ft,vertical_speed_fpm\n"
        + "\n".join(
            ",".join(str(value) for value in row)
            for row in rows
        ),
        encoding="utf-8",
    )


def _sample_profile() -> TestProfile:
    return TestProfile(
        id="sample_engine_failure",
        name="Sample engine failure",
        description="Synthetic profile for viewer tests",
        output_csv="data/results/sample.csv",
        plot_groups=(
            PlotGroup(
                id="engine",
                title="Engine",
                series=(
                    PlotSeries("engine_rpm", "RPM", "rpm"),
                    PlotSeries("engine_running", "Engine running"),
                ),
            ),
        ),
        event_window=EventWindow(
            id="failure",
            title="Failure",
            trigger_field="engine_failure_elapsed_s",
            pre_seconds=10.0,
            post_seconds=30.0,
            phase_values=("engine_failure_glide",),
        ),
    )


def test_dataset_focuses_ten_seconds_before_failure_and_thirty_after(tmp_path):
    _write_engine_failure_csv(tmp_path)
    bundle = load_dataset(tmp_path, _sample_profile())

    assert bundle.focus_window.enabled is True
    assert bundle.focus_window.event_start_elapsed_s == 20.0
    assert bundle.focus_window.start_elapsed_s == 10.0
    assert bundle.focus_window.end_elapsed_s == 50.0
    assert bundle.focused_frame["event_time_s"].min() == -10.0
    assert bundle.focused_frame["event_time_s"].max() == 30.0


def test_payload_exposes_groups_raw_numeric_columns_and_validation_metrics(tmp_path):
    _write_engine_failure_csv(tmp_path)
    bundle = load_dataset(tmp_path, _sample_profile())
    payload = build_payload(bundle)
    metrics = compute_validation_metrics(bundle)

    assert payload["focus_window"]["x_key"] == "event_time_s"
    assert payload["csv"]["name"] == "sample.csv"
    assert payload["plot_groups"][0]["id"] == "engine"
    assert "engine_rpm" in payload["columns"]["numeric"]
    assert payload["data"]["event_time_s"][0] == -10.0
    assert any(metric["id"] == "telemetry_completeness" for metric in metrics)


def test_real_engine_failure_profile_defines_viewer_schema():
    profile = TestRegistry(PROJECT_ROOT).get("cruise_engine_failure")

    assert profile.event_window is not None
    assert profile.event_window.pre_seconds == 10.0
    assert profile.event_window.post_seconds == 30.0
    assert any(group.id == "aerodynamics" for group in profile.plot_groups)
    assert "glide_ias_error" in profile.validation_metric_ids


def test_build_viewer_payload_for_existing_results(tmp_path):
    _write_engine_failure_csv(tmp_path, "cruise_engine_failure.csv")

    payload = build_viewer_payload(tmp_path, "cruise_engine_failure")

    assert payload["profile"]["id"] == "cruise_engine_failure"
    assert payload["focus_window"]["enabled"] is True
    assert payload["focus_window"]["x_key"] == "event_time_s"
    assert payload["csv"]["focused_rows"] < payload["csv"]["full_rows"]
    assert payload["validation_metrics"]
    assert payload["report_summary"]["aircraft"] == "c172p"
    assert payload["report_summary"]["test_name"] == "Cruise engine failure"
    assert any(
        item["key"] == "throttle_norm"
        for item in payload["report_summary"]["control_surfaces"]
    )
    assert any(
        item["key"] == "altitude_agl_ft"
        for item in payload["report_summary"]["key_signals"]
    )
