"""Unit tests for the optional native backend and Python fallback contract."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from flightgear_framework import native
from flightgear_framework.native import _fallback
from flightgear_framework.testing.test_cruise_engine_failure import (
    CruiseEngineFailureTest,
)


def assert_tracking_matches(left: dict, right: dict) -> None:
    for key, value in right.items():
        if isinstance(value, float):
            assert left[key] == pytest.approx(value)
        else:
            assert left[key] == value


def test_native_bridge_imports_with_or_without_cpp_extension():
    assert native.BACKEND in {"cpp", "python"}
    assert isinstance(native.is_native_available(), bool)
    assert {"status", "message", "error"} <= set(native.build_status())


def test_heading_helpers_preserve_existing_wrapping_behavior():
    assert native.heading_error_deg(10.0, 350.0) == pytest.approx(20.0)
    assert native.heading_error_deg(350.0, 10.0) == pytest.approx(-20.0)
    assert native.heading_delta_deg(350.0, 10.0) == pytest.approx(20.0)
    assert native.heading_delta_deg(10.0, 350.0) == pytest.approx(-20.0)


def test_runway_tracking_matches_python_fallback_contract():
    args = {
        "latitude_deg": 63.98640968394732,
        "longitude_deg": -22.7345013167298,
        "reference_latitude_deg": 63.98504455498328,
        "reference_longitude_deg": -22.59248586819118,
        "runway_heading_deg": 270.021398280628,
        "heading_deg": 270.3972276668235,
        "groundspeed_kts": 72.71648929894545,
        "lookahead_time_s": 2.8,
        "min_lookahead_m": 45.0,
        "max_lookahead_m": 160.0,
        "max_heading_correction_deg": 12.0,
        "rudder_deadband_deg": 0.5,
    }

    assert_tracking_matches(
        native.compute_runway_tracking(**args),
        _fallback.compute_runway_tracking(**args),
    )


def test_cruise_engine_failure_helpers_use_native_contract():
    assert CruiseEngineFailureTest._clamp(2.0, 0.0, 1.0) == pytest.approx(1.0)
    assert CruiseEngineFailureTest._heading_error_deg(10.0, 350.0) == pytest.approx(
        20.0
    )
    assert CruiseEngineFailureTest._heading_delta_deg(350.0, 10.0) == pytest.approx(
        20.0
    )
