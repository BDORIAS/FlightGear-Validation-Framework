#include "flightgear_native.hpp"

#include <algorithm>
#include <cmath>

namespace flightgear_native {
namespace {

constexpr double kMetersPerDegree = 111320.0;
constexpr double kKnotsToMetersPerSecond = 0.514444;
constexpr double kPi = 3.141592653589793238462643383279502884;

double deg_to_rad(double degrees) {
    return degrees * kPi / 180.0;
}

double rad_to_deg(double radians) {
    return radians * 180.0 / kPi;
}

double normalize_360(double degrees) {
    double wrapped = std::fmod(degrees, 360.0);
    if (wrapped < 0.0) {
        wrapped += 360.0;
    }
    return wrapped;
}

double wrap_signed_180(double degrees) {
    double wrapped = std::fmod(degrees + 180.0, 360.0);
    if (wrapped < 0.0) {
        wrapped += 360.0;
    }
    return wrapped - 180.0;
}

}  // namespace

double clamp(double value, double min_value, double max_value) {
    return std::max(min_value, std::min(value, max_value));
}

double heading_error_deg(double target_deg, double current_deg) {
    return wrap_signed_180(target_deg - current_deg);
}

double heading_delta_deg(double previous_deg, double current_deg) {
    return wrap_signed_180(current_deg - previous_deg);
}

RunwayTrackingResult compute_runway_tracking(
    double latitude_deg,
    double longitude_deg,
    double reference_latitude_deg,
    double reference_longitude_deg,
    double runway_heading_deg,
    double heading_deg,
    double groundspeed_kts,
    double lookahead_time_s,
    double min_lookahead_m,
    double max_lookahead_m,
    double max_heading_correction_deg,
    double rudder_deadband_deg) {
    const double normalized_runway_heading = normalize_360(runway_heading_deg);
    const double reference_latitude_rad = deg_to_rad(reference_latitude_deg);

    const double north_m =
        (latitude_deg - reference_latitude_deg) * kMetersPerDegree;
    const double east_m =
        (longitude_deg - reference_longitude_deg) * kMetersPerDegree *
        std::cos(reference_latitude_rad);

    const double runway_rad = deg_to_rad(normalized_runway_heading);
    const double along_track_m =
        north_m * std::cos(runway_rad) + east_m * std::sin(runway_rad);

    // Positive means right of centerline when looking down the runway.
    const double cross_track_m =
        east_m * std::cos(runway_rad) - north_m * std::sin(runway_rad);

    const double groundspeed_mps =
        std::max(groundspeed_kts, 0.0) * kKnotsToMetersPerSecond;
    const double lookahead_m = clamp(
        groundspeed_mps * lookahead_time_s,
        min_lookahead_m,
        max_lookahead_m);

    const double raw_centerline_correction_deg =
        -rad_to_deg(std::atan2(cross_track_m, lookahead_m));
    const double centerline_correction_deg = clamp(
        raw_centerline_correction_deg,
        -max_heading_correction_deg,
        max_heading_correction_deg);
    const double desired_heading_deg =
        normalize_360(normalized_runway_heading + centerline_correction_deg);
    const double control_heading_error =
        heading_error_deg(desired_heading_deg, heading_deg);

    std::string runway_side = "center";
    if (cross_track_m > 0.5) {
        runway_side = "right";
    } else if (cross_track_m < -0.5) {
        runway_side = "left";
    }

    std::string expected_rudder_sign = "neutral";
    if (control_heading_error > rudder_deadband_deg) {
        expected_rudder_sign = "positive/right";
    } else if (control_heading_error < -rudder_deadband_deg) {
        expected_rudder_sign = "negative/left";
    }

    return RunwayTrackingResult{
        normalized_runway_heading,
        along_track_m,
        cross_track_m,
        lookahead_m,
        desired_heading_deg,
        centerline_correction_deg,
        control_heading_error,
        runway_side,
        expected_rudder_sign,
    };
}

}  // namespace flightgear_native
