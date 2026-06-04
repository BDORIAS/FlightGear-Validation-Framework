#include "flightgear_native.hpp"

#include <pybind11/pybind11.h>

namespace py = pybind11;
using namespace pybind11::literals;

PYBIND11_MODULE(_flightgear_native, module) {
    module.doc() = "Native C++ helpers for FlightGear Test Framework";

    module.def("clamp", &flightgear_native::clamp);
    module.def("heading_error_deg", &flightgear_native::heading_error_deg);
    module.def("heading_delta_deg", &flightgear_native::heading_delta_deg);

    module.def(
        "compute_runway_tracking",
        [](double latitude_deg,
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
            const auto result = flightgear_native::compute_runway_tracking(
                latitude_deg,
                longitude_deg,
                reference_latitude_deg,
                reference_longitude_deg,
                runway_heading_deg,
                heading_deg,
                groundspeed_kts,
                lookahead_time_s,
                min_lookahead_m,
                max_lookahead_m,
                max_heading_correction_deg,
                rudder_deadband_deg);

            return py::dict(
                "runway_heading_deg"_a = result.runway_heading_deg,
                "runway_along_track_m"_a = result.runway_along_track_m,
                "runway_cross_track_m"_a = result.runway_cross_track_m,
                "runway_cross_track_rate_mps"_a = py::none(),
                "runway_side"_a = result.runway_side,
                "runway_lookahead_m"_a = result.runway_lookahead_m,
                "runway_desired_heading_deg"_a =
                    result.runway_desired_heading_deg,
                "centerline_correction_deg"_a =
                    result.centerline_correction_deg,
                "control_heading_error_deg"_a =
                    result.control_heading_error_deg,
                "expected_rudder_sign"_a = result.expected_rudder_sign);
        },
        py::arg("latitude_deg"),
        py::arg("longitude_deg"),
        py::arg("reference_latitude_deg"),
        py::arg("reference_longitude_deg"),
        py::arg("runway_heading_deg"),
        py::arg("heading_deg"),
        py::arg("groundspeed_kts"),
        py::arg("lookahead_time_s"),
        py::arg("min_lookahead_m"),
        py::arg("max_lookahead_m"),
        py::arg("max_heading_correction_deg"),
        py::arg("rudder_deadband_deg"));
}
