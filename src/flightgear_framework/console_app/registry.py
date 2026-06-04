"""Registry for built-in and auto-discovered test profiles."""

from __future__ import annotations

from pathlib import Path

from .profiles import EventWindow, PlotGroup, PlotSeries, TelemetryField, TestProfile


class TestRegistry:
    """Load test profiles from the framework testing package."""

    __test__ = False

    TESTING_PACKAGE = "flightgear_framework.testing"
    TESTING_DIR = Path("src") / "flightgear_framework" / "testing"

    def __init__(self, project_root: Path):
        self.project_root = project_root

    def profiles(self, include_discovered: bool = True) -> list[TestProfile]:
        profiles = [
            profile
            for profile in self._builtin_profiles()
            if self._is_testing_profile(profile)
        ]
        if include_discovered:
            profiles.extend(self._discover_testing_profiles(profiles))
        return profiles

    def get(self, profile_id: str) -> TestProfile:
        for profile in self.profiles(include_discovered=True):
            if profile.id == profile_id:
                return profile
        raise KeyError(f"Unknown test profile: {profile_id}")

    def _is_testing_profile(self, profile: TestProfile) -> bool:
        return bool(
            profile.module
            and profile.module.startswith(f"{self.TESTING_PACKAGE}.")
        )

    def _builtin_profiles(self) -> list[TestProfile]:
        return [
            TestProfile(
                id="cruise_engine_failure",
                name="Cruise engine failure",
                description=(
                    "Starts the C172P, takes off, stabilizes cruise, turns "
                    "magnetos off, and monitors glide behavior."
                ),
                module="flightgear_framework.testing.test_cruise_engine_failure",
                category="flightgear",
                phases=(
                    "startup",
                    "telnet_ready",
                    "loading_properties",
                    "ground_contact_check",
                    "engine_start",
                    "ground_roll",
                    "takeoff_roll",
                    "initial_climb",
                    "cruise_pre_failure",
                    "engine_failure_glide",
                    "complete",
                ),
                primary_fields=(
                    TelemetryField("phase", "Phase", widget="status"),
                    TelemetryField("altitude_agl_ft", "Alt AGL", "ft", "gauge"),
                    TelemetryField("airspeed_kts", "IAS", "kt", "chart"),
                    TelemetryField("vertical_speed_fpm", "VSI", "fpm", "chart"),
                    TelemetryField("engine_rpm", "RPM", "rpm", "chart"),
                    TelemetryField("engine_running", "Engine", widget="boolean"),
                    TelemetryField("magnetos", "Magnetos", widget="status"),
                    TelemetryField("throttle_norm", "Throttle", widget="gauge"),
                    TelemetryField("runway_cross_track_m", "XTrack", "m", "chart"),
                    TelemetryField("glide_airspeed_error_kts", "Glide IAS err", "kt"),
                ),
                secondary_fields=(
                    "altitude_ft",
                    "groundspeed_kts",
                    "pitch_deg",
                    "roll_deg",
                    "heading_deg",
                    "heading_error_deg",
                    "control_heading_error_deg",
                    "elevator_norm",
                    "aileron_norm",
                    "rudder_norm",
                    "brake_parking",
                    "brake_left",
                    "brake_right",
                    "wow0",
                    "wow1",
                    "wow2",
                    "freeze_master",
                    "freeze_clock",
                    "freeze_position",
                ),
                output_csv="data/results/cruise_engine_failure.csv",
                logs=(
                    "data/results/engine_start_debug.txt",
                    "data/results/flightgear_process_debug.txt",
                ),
                plot_groups=(
                    PlotGroup(
                        id="overview",
                        title="Overview",
                        description="Core flight and engine signals around the failure.",
                        series=(
                            PlotSeries("altitude_agl_ft", "Altitude AGL", "ft"),
                            PlotSeries("airspeed_kts", "Airspeed", "kt"),
                            PlotSeries("vertical_speed_fpm", "Vertical speed", "fpm"),
                            PlotSeries("engine_rpm", "Engine RPM", "rpm"),
                            PlotSeries("engine_running", "Engine running"),
                            PlotSeries("magnetos", "Magnetos"),
                        ),
                    ),
                    PlotGroup(
                        id="engine",
                        title="Engine Failure",
                        description="Failure injection, RPM decay, power state, and throttle command.",
                        series=(
                            PlotSeries("engine_failure_elapsed_s", "Failure elapsed", "s"),
                            PlotSeries("engine_rpm", "Engine RPM", "rpm"),
                            PlotSeries("engine_running", "Engine running"),
                            PlotSeries("magnetos", "Magnetos"),
                            PlotSeries("throttle_norm", "Throttle"),
                            PlotSeries("throttle_guard_reason", "Throttle reason"),
                        ),
                    ),
                    PlotGroup(
                        id="aerodynamics",
                        title="Aerodynamics / Glide",
                        description="Best-glide behavior and pitch/airspeed tracking.",
                        series=(
                            PlotSeries("airspeed_kts", "Airspeed", "kt"),
                            PlotSeries("glide_target_airspeed_kts", "Target glide IAS", "kt"),
                            PlotSeries("glide_airspeed_error_kts", "Glide IAS error", "kt"),
                            PlotSeries("vertical_speed_fpm", "Vertical speed", "fpm"),
                            PlotSeries("pitch_deg", "Pitch", "deg"),
                            PlotSeries("glide_target_pitch_deg", "Target pitch", "deg"),
                            PlotSeries("glide_pitch_error_deg", "Pitch error", "deg"),
                            PlotSeries("glide_descent_guard_norm", "Descent guard"),
                        ),
                    ),
                    PlotGroup(
                        id="attitude",
                        title="Attitude / Heading",
                        description="Aircraft attitude, heading stability, and rate guards.",
                        series=(
                            PlotSeries("pitch_deg", "Pitch", "deg"),
                            PlotSeries("roll_deg", "Roll", "deg"),
                            PlotSeries("heading_deg", "Heading", "deg"),
                            PlotSeries("heading_error_deg", "Heading error", "deg"),
                            PlotSeries("heading_rate_deg_s", "Heading rate", "deg/s"),
                            PlotSeries("control_heading_error_deg", "Control heading error", "deg"),
                            PlotSeries("rate_guard_active", "Rate guard active"),
                        ),
                    ),
                    PlotGroup(
                        id="controls",
                        title="Controls",
                        description="Pilot/control-loop commands sent during takeoff, cruise, and glide.",
                        series=(
                            PlotSeries("throttle_norm", "Throttle"),
                            PlotSeries("elevator_norm", "Elevator"),
                            PlotSeries("aileron_norm", "Aileron"),
                            PlotSeries("rudder_norm", "Rudder"),
                            PlotSeries("rudder_raw_norm", "Raw rudder"),
                            PlotSeries("rudder_saturated_norm", "Saturated rudder"),
                            PlotSeries("elevator_trim_norm", "Elevator trim"),
                            PlotSeries("flaps_norm", "Flaps"),
                            PlotSeries("brake_left", "Left brake"),
                            PlotSeries("brake_right", "Right brake"),
                        ),
                    ),
                    PlotGroup(
                        id="runway",
                        title="Runway / Trajectory",
                        description="Runway-relative geometry and tracking corrections.",
                        series=(
                            PlotSeries("runway_along_track_m", "Along track", "m"),
                            PlotSeries("runway_cross_track_m", "Cross track", "m"),
                            PlotSeries("runway_cross_track_rate_mps", "Cross-track rate", "m/s"),
                            PlotSeries("runway_desired_heading_deg", "Desired heading", "deg"),
                            PlotSeries("centerline_correction_deg", "Centerline correction", "deg"),
                            PlotSeries("control_heading_error_deg", "Control heading error", "deg"),
                            PlotSeries("expected_rudder_sign", "Expected rudder sign"),
                        ),
                    ),
                    PlotGroup(
                        id="ground_contact",
                        title="Ground Contact",
                        description="WOW, gear compression, brakes, chocks, hitch, and freeze flags.",
                        series=(
                            PlotSeries("wow0", "WOW 0"),
                            PlotSeries("wow1", "WOW 1"),
                            PlotSeries("wow2", "WOW 2"),
                            PlotSeries("jsbsim_gear_wow0", "JSBSim WOW 0"),
                            PlotSeries("jsbsim_gear_wow1", "JSBSim WOW 1"),
                            PlotSeries("jsbsim_gear_wow2", "JSBSim WOW 2"),
                            PlotSeries("gear_compression0_ft", "Gear compression 0", "ft"),
                            PlotSeries("gear_compression1_ft", "Gear compression 1", "ft"),
                            PlotSeries("gear_compression2_ft", "Gear compression 2", "ft"),
                            PlotSeries("freeze_master", "Freeze master"),
                            PlotSeries("freeze_clock", "Freeze clock"),
                            PlotSeries("freeze_position", "Freeze position"),
                        ),
                    ),
                    PlotGroup(
                        id="telemetry",
                        title="Telemetry Health",
                        description="CSV quality, received values, missing fields, and phase context.",
                        series=(
                            PlotSeries("telemetry_valid", "Telemetry valid"),
                            PlotSeries("telemetry_values_received", "Values received"),
                            PlotSeries("telemetry_values_expected", "Values expected"),
                            PlotSeries("telemetry_missing_fields", "Missing fields"),
                            PlotSeries("phase", "Phase"),
                            PlotSeries("phase_reason", "Phase reason"),
                        ),
                    ),
                ),
                event_window=EventWindow(
                    id="engine_failure_window",
                    title="Engine failure focus window",
                    trigger_field="engine_failure_elapsed_s",
                    pre_seconds=10.0,
                    post_seconds=30.0,
                    phase_values=("engine_failure_glide", "engine_failure"),
                ),
                validation_metric_ids=(
                    "telemetry_completeness",
                    "failure_duration",
                    "rpm_decay",
                    "engine_stop_time",
                    "glide_ias_error",
                    "glide_pitch_error",
                    "vertical_speed",
                    "cross_track_drift",
                ),
                requires_flightgear=True,
            ),
            TestProfile(
                id="simple_connect",
                name="Simple connection diagnostic",
                description=(
                    "Starts FlightGear, connects through telnet, reads altitude, "
                    "and sets throttle. Useful for quick diagnostics."
                ),
                module="flightgear_framework.testing.test_runner",
                category="diagnostic",
                phases=("startup", "telnet_connect", "read_altitude", "set_throttle"),
                primary_fields=(
                    TelemetryField("altitude_ft", "Altitude", "ft"),
                    TelemetryField("throttle_norm", "Throttle"),
                ),
                logs=(
                    "data/results/simple_connect_debug.txt",
                    "data/results/flightgear_process_simple_connect.txt",
                ),
                requires_flightgear=True,
            ),
        ]

    def _discover_testing_profiles(self, existing: list[TestProfile]) -> list[TestProfile]:
        testing_dir = self.project_root / self.TESTING_DIR
        if not testing_dir.is_dir():
            return []

        known_modules = {profile.module for profile in existing if profile.module}
        known_ids = {profile.id for profile in existing}
        discovered: list[TestProfile] = []
        for path in sorted(testing_dir.glob("test_*.py")):
            if "__pycache__" in path.parts:
                continue
            module = f"{self.TESTING_PACKAGE}.{path.stem}"
            if module in known_modules:
                continue
            profile_id = path.stem.removeprefix("test_")
            if profile_id in known_ids:
                continue
            discovered.append(
                TestProfile(
                    id=profile_id,
                    name=profile_id.replace("_", " ").title(),
                    description=(
                        "Test discovered automatically from "
                        f"{self.TESTING_DIR.as_posix()}/{path.name}."
                    ),
                    module=module,
                    category="flightgear",
                    requires_flightgear=True,
                )
            )
        return discovered
