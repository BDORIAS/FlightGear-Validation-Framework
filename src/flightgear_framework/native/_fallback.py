"""Pure-Python implementation of the optional native math helpers."""

from __future__ import annotations

import math


def clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(value, max_value))


def heading_error_deg(target_deg: float, current_deg: float) -> float:
    return (target_deg - current_deg + 180.0) % 360.0 - 180.0


def heading_delta_deg(previous_deg: float, current_deg: float) -> float:
    return (current_deg - previous_deg + 180.0) % 360.0 - 180.0


def compute_runway_tracking(
    latitude_deg: float,
    longitude_deg: float,
    reference_latitude_deg: float,
    reference_longitude_deg: float,
    runway_heading_deg: float,
    heading_deg: float,
    groundspeed_kts: float,
    lookahead_time_s: float,
    min_lookahead_m: float,
    max_lookahead_m: float,
    max_heading_correction_deg: float,
    rudder_deadband_deg: float,
) -> dict:
    """Compute runway-relative geometry used by takeoff steering logic."""
    normalized_runway_heading = runway_heading_deg % 360.0
    reference_latitude_rad = math.radians(reference_latitude_deg)

    north_m = (latitude_deg - reference_latitude_deg) * 111_320.0
    east_m = (
        (longitude_deg - reference_longitude_deg)
        * 111_320.0
        * math.cos(reference_latitude_rad)
    )

    runway_rad = math.radians(normalized_runway_heading)
    along_m = north_m * math.cos(runway_rad) + east_m * math.sin(runway_rad)
    cross_track_m = east_m * math.cos(runway_rad) - north_m * math.sin(runway_rad)

    groundspeed_mps = max(groundspeed_kts, 0.0) * 0.514444
    lookahead_m = clamp(
        groundspeed_mps * lookahead_time_s,
        min_lookahead_m,
        max_lookahead_m,
    )

    raw_centerline_correction = -math.degrees(
        math.atan2(cross_track_m, lookahead_m)
    )
    centerline_correction_deg = clamp(
        raw_centerline_correction,
        -max_heading_correction_deg,
        max_heading_correction_deg,
    )
    desired_heading = (normalized_runway_heading + centerline_correction_deg) % 360.0
    control_heading_error = heading_error_deg(desired_heading, heading_deg)

    if cross_track_m > 0.5:
        runway_side = "right"
    elif cross_track_m < -0.5:
        runway_side = "left"
    else:
        runway_side = "center"

    if control_heading_error > rudder_deadband_deg:
        expected_rudder_sign = "positive/right"
    elif control_heading_error < -rudder_deadband_deg:
        expected_rudder_sign = "negative/left"
    else:
        expected_rudder_sign = "neutral"

    return {
        "runway_heading_deg": normalized_runway_heading,
        "runway_along_track_m": along_m,
        "runway_cross_track_m": cross_track_m,
        "runway_cross_track_rate_mps": None,
        "runway_side": runway_side,
        "runway_lookahead_m": lookahead_m,
        "runway_desired_heading_deg": desired_heading,
        "centerline_correction_deg": centerline_correction_deg,
        "control_heading_error_deg": control_heading_error,
        "expected_rudder_sign": expected_rudder_sign,
    }
