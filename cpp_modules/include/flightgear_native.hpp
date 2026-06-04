#pragma once

#include <string>

namespace flightgear_native {

// Runway-relative geometry used by Python steering and telemetry code.
struct RunwayTrackingResult {
    double runway_heading_deg;
    double runway_along_track_m;
    double runway_cross_track_m;
    double runway_lookahead_m;
    double runway_desired_heading_deg;
    double centerline_correction_deg;
    double control_heading_error_deg;
    std::string runway_side;
    std::string expected_rudder_sign;
};

double clamp(double value, double min_value, double max_value);
double heading_error_deg(double target_deg, double current_deg);
double heading_delta_deg(double previous_deg, double current_deg);

// Mirrors flightgear_framework.native._fallback.compute_runway_tracking.
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
    double rudder_deadband_deg);

}  // namespace flightgear_native
