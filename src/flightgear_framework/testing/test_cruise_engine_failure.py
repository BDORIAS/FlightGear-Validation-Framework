"""Cruise engine-failure profile for the C172P in FlightGear."""

import csv
import logging
import os
import re
import time
from pathlib import Path

import yaml

from ..communication.protocol import FlightGearProtocol
from ..configuration import flightgear_connection_settings, flightgear_simulator_settings
from ..core.simulator import FlightGearSimulator
from ..native import (
    clamp as native_clamp,
    compute_runway_tracking as native_compute_runway_tracking,
    heading_delta_deg as native_heading_delta_deg,
    heading_error_deg as native_heading_error_deg,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class CruiseEngineFailureTest:
    """
    Puts the aircraft into cruise, simulates an engine failure, and collects telemetry.
    """

    STARTUP_WAIT_SECONDS = 70
    GROUND_CONTACT_TIMEOUT_SECONDS = 25.0
    ENGINE_START_TIMEOUT_SECONDS = 20
    MIN_STARTER_SECONDS = 5.0
    ENGINE_MIN_RUNNING_RPM = 650.0
    ENGINE_STABLE_SECONDS = 1.5
    POST_START_MONITOR_SECONDS = 5.0
    TAKEOFF_POWER = 1.0
    TAKEOFF_INITIAL_THROTTLE = 0.34
    TAKEOFF_THROTTLE_RAMP_SECONDS = 55.0
    CRUISE_THROTTLE = 0.75
    GROUND_ROLL_TIMEOUT_SECONDS = 75.0
    GROUND_ROLL_MIN_GROUNDSPEED_KT = 3.0
    GROUND_ROLL_MIN_AIRSPEED_KT = 20.0
    TAXI_THROTTLE_INITIAL = 0.22
    TAXI_THROTTLE_MAX = 0.27
    TAXI_THROTTLE_RAMP_SECONDS = 22.0
    TAXI_TARGET_GROUNDSPEED_KT = 5.5
    TAXI_CORRECTION_THROTTLE_MAX = 0.24
    TAXI_RATE_CORRECTION_THROTTLE_MAX = 0.20
    TAXI_HEADING_STABLE_DEG = 3.0
    TAXI_HEADING_ACCEPTABLE_DEG = 5.5
    TAXI_HEADING_ABORT_DEG = 30.0
    TAXI_HEADING_RATE_STABLE_DEG_S = 0.20
    TAXI_HEADING_RATE_THROTTLE_CAP_DEG_S = 0.8
    TAXI_STABLE_SECONDS = 4.0
    TAXI_ACCEPTABLE_STABLE_SECONDS = 3.0
    TAXI_MAX_GROUNDSPEED_KT = 8.5
    TAXI_CROSSTRACK_STABLE_M = 2.5
    TAXI_CROSSTRACK_ACCEPTABLE_M = 5.0
    TAXI_DIFF_BRAKE_START_DEG = 22.0
    TAXI_DIFF_BRAKE_FULL_DEG = 40.0
    TAXI_DIFF_BRAKE_MAX = 0.0
    TAXI_DIFF_BRAKE_MAX_GROUNDSPEED_KT = 10.0
    # C172 rotation speed. In this sim 55 KIAS was too late: the aircraft
    # reached the runway edge before the rotation gate opened.
    V1_ROTATION_AIRSPEED_KT = 54.0
    ROTATION_AIRSPEED_KT = V1_ROTATION_AIRSPEED_KT
    LIFTOFF_MIN_AGL_FT = 6.0
    AIRBORNE_MIN_AGL_FT = 30.0
    CRUISE_TIMEOUT_SECONDS = 240.0
    CRUISE_MIN_AGL_FT = 1000.0
    CRUISE_TARGET_AGL_FT = 1000.0
    CRUISE_CAPTURE_BAND_FT = 150.0
    CRUISE_MIN_AIRSPEED_KT = 75.0
    CRUISE_MAX_ALTITUDE_ERROR_FT = 80.0
    CRUISE_MAX_ABS_VERTICAL_SPEED_FPM = 120.0
    CRUISE_MAX_ABS_ROLL_DEG = 8.0
    CRUISE_MAX_ABS_PITCH_DEG = 6.0
    CRUISE_MAX_HEADING_ERROR_DEG = 10.0
    CRUISE_STABLE_SECONDS = 8.0
    FAILURE_ARM_DELAY_SECONDS = 15.0
    # Max time to find a continuous stable-cruise window before injecting.
    FAILURE_OBSERVATION_SECONDS = 30.0
    POST_FAILURE_OBSERVATION_SECONDS = 30.0
    TELEMETRY_RETRY_ATTEMPTS = 3
    TELEMETRY_RETRY_DELAY_SECONDS = 0.25
    TAKEOFF_RUDDER_HEADING_GAIN = 0.022
    TAKEOFF_RUDDER_RIGHT_BIAS = 0.0
    TAKEOFF_RUDDER_POWER_FEED_FORWARD = 0.18
    TAKEOFF_MAX_RUDDER_LOW_SPEED = 0.85
    TAKEOFF_MAX_RUDDER_HIGH_SPEED = 0.45
    TAKEOFF_MAX_RUDDER_GROUND = 0.85
    TAKEOFF_MAX_RUDDER_AIRBORNE = 0.12
    TAKEOFF_RUDDER_DEADBAND_DEG = 0.5
    TAKEOFF_RUDDER_RATE_GAIN = 0.016
    TAKEOFF_RUDDER_RATE_COMPONENT_LIMIT = 0.14
    TAKEOFF_RUDDER_MAX_STEP = 0.08
    TAKEOFF_HEADING_RATE_MIN_GROUNDSPEED_KT = 1.0
    TAKEOFF_HEADING_THROTTLE_CAP_DEG = 8.0
    TAKEOFF_HEADING_THROTTLE_CAP = 0.75
    TAKEOFF_HEADING_RATE_THROTTLE_CAP_DEG_S = 2.5
    TAKEOFF_HEADING_RATE_THROTTLE_CAP = 0.72
    TAKEOFF_HEADING_RATE_HARD_CAP_DEG_S = 6.0
    TAKEOFF_HEADING_RATE_HARD_CAP = 0.62
    TAKEOFF_HEADING_RATE_GUARD_MIN_HEADING_ERROR_DEG = 6.0
    TAKEOFF_HEADING_RATE_GUARD_CROSSTRACK_M = 5.0
    TAKEOFF_RUNWAY_GUARD_HEADING_DEG = 5.0
    TAKEOFF_RUNWAY_GUARD_THROTTLE = 0.62
    TAKEOFF_RUNWAY_GUARD_HARD_HEADING_DEG = 9.0
    TAKEOFF_RUNWAY_GUARD_HARD_THROTTLE = 0.45
    TAKEOFF_LOW_SPEED_POWER_CAP_AIRSPEED_KT = 45.0
    TAKEOFF_LOW_SPEED_POWER_CAP = 0.72
    TAKEOFF_HIGH_SPEED_CROSSTRACK_AIRSPEED_KT = 45.0
    TAKEOFF_CROSSTRACK_HIGH_SPEED_GUARD_THROTTLE = 0.75
    TAKEOFF_CROSSTRACK_HIGH_SPEED_HARD_GUARD_THROTTLE = 0.62
    TAKEOFF_ROTATION_MAX_HEADING_ERROR_DEG = 6.0
    TAKEOFF_ROTATION_MAX_CONTROL_HEADING_ERROR_DEG = 16.0
    TAKEOFF_ROTATION_MAX_HEADING_RATE_DEG_S = 3.0
    TAKEOFF_ROTATION_ELEVATOR = -0.055
    TAKEOFF_DIFF_BRAKE_START_DEG = 18.0
    TAKEOFF_DIFF_BRAKE_FULL_DEG = 35.0
    TAKEOFF_DIFF_BRAKE_MAX = 0.0
    TAKEOFF_DIFF_BRAKE_MAX_GROUNDSPEED_KT = 16.0
    CLIMB_TARGET_PITCH_DEG = 8.0
    CLIMB_MAX_PITCH_DEG = 12.0
    CLIMB_MIN_AIRSPEED_KT = 65.0
    CLIMB_POWER = 0.90
    AIRBORNE_MAX_BANK_DEG = 15.0
    AIRBORNE_MAX_AILERON = 0.25
    AIRBORNE_AILERON_ROLL_GAIN = 0.025
    AIRBORNE_HEADING_TO_BANK_GAIN = 0.45
    AIRBORNE_MAX_RUDDER = 0.08
    AIRBORNE_RUDDER_HEADING_GAIN = 0.004
    AIRBORNE_RUDDER_RATE_GAIN = 0.010
    AIRBORNE_ELEVATOR_PITCH_GAIN = 0.014
    AIRBORNE_ELEVATOR_VSI_GAIN = 0.000060
    AIRBORNE_ALTITUDE_TO_VSI_GAIN = 2.5
    AIRBORNE_ALTITUDE_CAPTURE_LEAD_TIME_S = 6.0
    AIRBORNE_MAX_CLIMB_CAPTURE_VSI_FPM = 260.0
    AIRBORNE_MAX_DESCENT_CAPTURE_VSI_FPM = 420.0
    AIRBORNE_CRUISE_HOLD_MAX_CLIMB_VSI_FPM = 80.0
    AIRBORNE_CRUISE_HOLD_MAX_DESCENT_VSI_FPM = 80.0
    AIRBORNE_CRUISE_DESCENT_ARREST_VSI_FPM = 90.0
    AIRBORNE_LEVEL_PITCH_DEG = 2.0
    AIRBORNE_TARGET_VSI_TO_PITCH_GAIN = 0.004
    AIRBORNE_CAPTURE_MIN_PITCH_DEG = 0.4
    AIRBORNE_CAPTURE_MAX_PITCH_DEG = 4.0
    AIRBORNE_CAPTURE_POWER = 0.66
    AIRBORNE_STRONG_CAPTURE_POWER = 0.58
    AIRBORNE_DESCENT_ARREST_POWER = 0.78
    ENGINE_FAILURE_BEST_GLIDE_KT = 65.0
    ENGINE_FAILURE_INITIAL_FLAPS = 0.0
    ENGINE_FAILURE_POWER = 0.0
    ENGINE_FAILURE_BASE_PITCH_DEG = 1.0
    ENGINE_FAILURE_AIRSPEED_TO_PITCH_GAIN = 0.12
    ENGINE_FAILURE_MIN_TARGET_PITCH_DEG = -2.0
    ENGINE_FAILURE_MAX_TARGET_PITCH_DEG = 5.0
    ENGINE_FAILURE_ELEVATOR_PITCH_GAIN = 0.016
    ENGINE_FAILURE_ELEVATOR_AIRSPEED_GAIN = 0.0026
    ENGINE_FAILURE_ELEVATOR_VSI_GUARD_GAIN = 0.000035
    ENGINE_FAILURE_DESCENT_GUARD_START_FPM = -850.0
    ENGINE_FAILURE_DESCENT_GUARD_MIN_IAS_KT = 67.0
    ENGINE_FAILURE_MAX_NOSE_UP_ELEVATOR = -0.12
    ENGINE_FAILURE_MAX_NOSE_DOWN_ELEVATOR = 0.10
    ENGINE_FAILURE_MAX_BANK_DEG = 10.0
    ENGINE_FAILURE_HEADING_TO_BANK_GAIN = 0.35
    ENGINE_FAILURE_MAX_AILERON = 0.22
    ENGINE_FAILURE_AILERON_ROLL_GAIN = 0.025
    ENGINE_FAILURE_MAX_RUDDER = 0.06
    ENGINE_FAILURE_RUDDER_HEADING_GAIN = 0.0025
    ENGINE_FAILURE_RUDDER_RATE_GAIN = 0.012
    TAXI_RUDDER_HEADING_GAIN = 0.035
    TAXI_RUDDER_POWER_FEED_FORWARD = 0.02
    TAXI_MAX_RUDDER = 0.35
    TAXI_RUDDER_MAX_STEP = 0.05
    RUNWAY_CENTERLINE_MIN_LOOKAHEAD_M = 45.0
    RUNWAY_CENTERLINE_MAX_LOOKAHEAD_M = 160.0
    RUNWAY_CENTERLINE_LOOKAHEAD_TIME_S = 2.8
    RUNWAY_CENTERLINE_MAX_HEADING_CORRECTION_DEG = 12.0
    TAKEOFF_ROTATION_MAX_CROSSTRACK_M = 9.0
    TAKEOFF_ROTATION_MAX_CROSSTRACK_HIGH_SPEED_M = 18.0
    TAKEOFF_ROTATION_MAX_AWAY_CROSSTRACK_RATE_MPS = 0.35
    TAKEOFF_CROSSTRACK_GUARD_M = 9.0
    TAKEOFF_CROSSTRACK_GUARD_THROTTLE = 0.62
    TAKEOFF_CROSSTRACK_HARD_GUARD_M = 16.0
    TAKEOFF_CROSSTRACK_HARD_GUARD_THROTTLE = 0.35
    TAKEOFF_CROSSTRACK_ABORT_M = 25.0
    TAKEOFF_ABORT_HEADING_ERROR_DEG = 12.0
    TAKEOFF_ABORT_HEADING_CROSSTRACK_M = 8.0
    TAKEOFF_ABORT_HARD_HEADING_ERROR_DEG = 24.0
    TAKEOFF_ABORT_CONTROL_HEADING_ERROR_DEG = 18.0
    TAKEOFF_ABORT_CONTROL_CROSSTRACK_M = 18.0
    TAKEOFF_ABORT_CONTROL_CROSSTRACK_RATE_MPS = 1.2
    TAKEOFF_HIGH_SPEED_EDGE_RUDDER_CAP = 0.30
    TAKEOFF_HIGH_SPEED_EDGE_RUDDER_HEADING_DEG = 5.0
    TAKEOFF_HIGH_SPEED_EDGE_RUDDER_RATE_DEG_S = 1.0
    TAKEOFF_NOSE_DOWN_ELEVATOR = 0.08

    GROUND_ROLL_SAMPLE_FIELDS = {
        "latitude_deg",
        "longitude_deg",
        "groundspeed_kts",
        "heading_deg",
        "steer_pos_deg",
        "nose_wheel_steer_cmd_deg",
        "nose_wheel_steer_adjusted_cmd_deg",
        "engine_running",
    }
    TAKEOFF_SAMPLE_FIELDS = {
        "latitude_deg",
        "longitude_deg",
        "altitude_ft",
        "altitude_agl_ft",
        "airspeed_kts",
        "groundspeed_kts",
        "vertical_speed_fpm",
        "pitch_deg",
        "heading_deg",
        "roll_deg",
        "steer_pos_deg",
        "nose_wheel_steer_cmd_deg",
        "nose_wheel_steer_adjusted_cmd_deg",
        "wow0",
        "wow1",
        "wow2",
        "jsbsim_gear_wow0",
        "jsbsim_gear_wow1",
        "jsbsim_gear_wow2",
        "gear_compression0_ft",
        "gear_compression1_ft",
        "gear_compression2_ft",
        "engine_running",
        "engine_rpm",
    }
    TAKEOFF_ROLL_SAMPLE_FIELDS = {
        "latitude_deg",
        "longitude_deg",
        "altitude_ft",
        "altitude_agl_ft",
        "airspeed_kts",
        "groundspeed_kts",
        "vertical_speed_fpm",
        "pitch_deg",
        "heading_deg",
        "roll_deg",
        "steer_pos_deg",
        "nose_wheel_steer_cmd_deg",
        "nose_wheel_steer_adjusted_cmd_deg",
        "wow0",
        "wow1",
        "wow2",
        "jsbsim_gear_wow0",
        "jsbsim_gear_wow1",
        "jsbsim_gear_wow2",
        "gear_compression0_ft",
        "gear_compression1_ft",
        "gear_compression2_ft",
        "engine_running",
        "engine_rpm",
    }

    CSV_COLUMNS = [
        "timestamp",
        "phase",
        "phase_reason",
        "telemetry_valid",
        "telemetry_values_received",
        "telemetry_values_expected",
        "telemetry_missing_fields",
        "on_ground_detected",
        "airborne_detected",
        "rotation_latched",
        "latitude_deg",
        "longitude_deg",
        "altitude_ft",
        "altitude_agl_ft",
        "airspeed_kts",
        "groundspeed_kts",
        "vertical_speed_fpm",
        "runway_heading_deg",
        "runway_along_track_m",
        "runway_cross_track_m",
        "runway_cross_track_rate_mps",
        "runway_side",
        "runway_lookahead_m",
        "runway_desired_heading_deg",
        "centerline_correction_deg",
        "control_heading_error_deg",
        "expected_rudder_sign",
        "pitch_deg",
        "heading_deg",
        "heading_error_deg",
        "heading_rate_deg_s",
        "heading_rate_diverging",
        "rate_guard_active",
        "steer_pos_deg",
        "nose_wheel_steer_cmd_deg",
        "nose_wheel_steer_adjusted_cmd_deg",
        "roll_deg",
        "airborne_desired_roll_deg",
        "airborne_roll_error_deg",
        "airborne_altitude_error_ft",
        "airborne_capture_error_ft",
        "airborne_target_vsi_fpm",
        "airborne_target_pitch_deg",
        "airborne_pitch_error_deg",
        "engine_failure_elapsed_s",
        "glide_target_airspeed_kts",
        "glide_airspeed_error_kts",
        "glide_target_pitch_deg",
        "glide_pitch_error_deg",
        "glide_descent_guard_norm",
        "glide_target_heading_deg",
        "glide_heading_error_deg",
        "glide_command_reason",
        "throttle_norm",
        "throttle_guard_reason",
        "aileron_norm",
        "rudder_norm",
        "rudder_raw_norm",
        "rudder_saturated_norm",
        "rudder_target_norm",
        "rudder_heading_component",
        "rudder_rate_component",
        "rudder_power_component",
        "elevator_norm",
        "elevator_trim_norm",
        "flaps_norm",
        "brake_parking",
        "brake_left",
        "brake_right",
        "chock",
        "aerotow_open",
        "hitch_force_lbs",
        "wow0",
        "wow1",
        "wow2",
        "jsbsim_gear_wow0",
        "jsbsim_gear_wow1",
        "jsbsim_gear_wow2",
        "contact_wow3",
        "contact_wow6",
        "contact_wow7",
        "contact_wow8",
        "gear_compression0_ft",
        "gear_compression1_ft",
        "gear_compression2_ft",
        "freeze_master",
        "freeze_clock",
        "freeze_position",
        "magnetos",
        "engine_running",
        "engine_rpm",
    ]

    def __init__(self, config: dict):
        sim = flightgear_simulator_settings(config)
        conn = flightgear_connection_settings(config)

        project_root = Path(__file__).resolve().parents[3]
        self.output_dir = Path(os.environ.get("FG_RESULTS_DIR", project_root / "data" / "results"))
        os.makedirs(self.output_dir, exist_ok=True)
        self.airport = sim.get("default_airport", "BIKF")
        self.runway = sim.get("default_runway", "29")
        self.disable_terrasync = bool(sim.get("disable_terrasync", False))
        self.takeoff_heading_deg: float | None = None
        self.takeoff_roll_started_at: float | None = None
        self.rotation_started_at: float | None = None
        self.engine_failure_started_at: float | None = None
        self.runway_reference_lat_deg: float | None = None
        self.runway_reference_lon_deg: float | None = None
        self.runway_heading_deg: float | None = None
        self.last_cross_track_sample_m: float | None = None
        self.last_cross_track_sample_time: float | None = None
        self.last_rudder_command = self.TAKEOFF_RUDDER_RIGHT_BIAS
        self.last_heading_sample_deg: float | None = None
        self.last_heading_sample_time: float | None = None
        self.last_control_commands: dict[str, object] = {}

        self.csv_path = self.output_dir / "cruise_engine_failure.csv"
        self.debug_txt_path = self.output_dir / "engine_start_debug.txt"
        self.fg_process_log_path = self.output_dir / "flightgear_process_debug.txt"
        self._reset_debug_log()

        self.sim = FlightGearSimulator(
            executable=sim.get("executable", "fgfs"),
            data_dir=sim.get("data_dir", None),
            aircraft=sim.get("default_aircraft", "c172p"),
            airport=self.airport,
            process_log_path=str(self.fg_process_log_path),
        )

        self.proto = FlightGearProtocol(
            host=conn.get("host", "localhost"),
            port=conn.get("port", 5401),
            response_timeout=conn.get("response_timeout", 1.2),
            command_log_path=str(self.debug_txt_path),
            use_data_mode=True,
        )

    def _reset_debug_log(self) -> None:
        with open(self.debug_txt_path, "w", encoding="utf-8") as debug_file:
            debug_file.write("=== CruiseEngineFailureTest debug log ===\n")
        with open(self.fg_process_log_path, "w", encoding="utf-8") as process_file:
            process_file.write("=== FlightGear process debug log ===\n")
        with open(self.csv_path, "w", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(self.CSV_COLUMNS)

    def _debug(self, message: str) -> None:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        line = f"[{timestamp}] {message}"
        logger.info(message)
        with open(self.debug_txt_path, "a", encoding="utf-8") as debug_file:
            debug_file.write(line + "\n")

    @staticmethod
    def _extract_value(raw_response: str | None) -> str | None:
        if raw_response is None:
            return None

        text = raw_response.strip()
        if not text:
            return None

        lines = [
            line.strip()
            for line in text.replace("\r", "\n").split("\n")
            if line.strip() and not line.strip().endswith(">")
        ]

        for line in reversed(lines or [text]):
            quoted = re.search(r"=\s*'([^']*)'", line)
            if quoted:
                return quoted.group(1)

            plain = re.search(r"=\s*([^\s]+)", line)
            if plain:
                return plain.group(1).strip("'\"")

            token = line.strip().strip("'\"")
            if token:
                return token

        return None

    def _get_bool_property(self, property_path: str) -> bool | None:
        raw = self.proto.get_property(property_path)
        value = self._extract_value(raw)
        self._debug(f"GET {property_path} -> raw='{raw}' parsed='{value}'")

        if value is None:
            return None

        lowered = value.lower()
        if lowered in {"true", "on", "yes"}:
            return True
        if lowered in {"false", "off", "no"}:
            return False

        try:
            return float(value) != 0.0
        except ValueError:
            return None

    def _get_float_property(self, property_path: str) -> float | None:
        raw = self.proto.get_property(property_path)
        value = self._extract_value(raw)
        self._debug(f"GET {property_path} -> raw='{raw}' parsed='{value}'")
        if value is None:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    def _set_and_log(self, property_path: str, value) -> bool:
        ok = self.proto.set_property(property_path, value)
        self._debug(f"SET {property_path}={value} -> {'OK' if ok else 'FAIL'}")
        return ok

    def _set_if_changed_and_log(
        self,
        property_path: str,
        value,
        tolerance: float = 1e-3,
    ) -> bool:
        previous = self.last_control_commands.get(property_path)
        if previous is not None:
            try:
                if abs(float(previous) - float(value)) <= tolerance:
                    return True
            except (TypeError, ValueError):
                if previous == value:
                    return True

        ok = self._set_and_log(property_path, value)
        if ok:
            self.last_control_commands[property_path] = value
        return ok

    def start_engine(self) -> bool:
        """
        Engine startup sequence adapted for the C172P:
        - master battery + alternator
        - magnetos BOTH
        - throttle 20%
        - rich mixture
        - primer
        - starter
        """
        self._debug("Starting C172P engine startup sequence")

        sequence_ok = True
        sequence_ok &= self._set_and_log("/controls/gear/brake-parking", 1)
        sequence_ok &= self._set_and_log("/controls/gear/brake-left", 0)
        sequence_ok &= self._set_and_log("/controls/gear/brake-right", 0)
        sequence_ok &= self._set_and_log("/sim/model/c172p/cockpit/control-lock-placed", 0)
        sequence_ok &= self._set_and_log("/sim/model/c172p/securing/chock", 0)
        sequence_ok &= self._set_and_log("/sim/model/c172p/securing/cowl-plugs-visible", 0)
        sequence_ok &= self._set_and_log("/sim/model/c172p/securing/pitot-cover-visible", 0)
        sequence_ok &= self._set_and_log("/sim/model/c172p/securing/tiedownL-visible", 0)
        sequence_ok &= self._set_and_log("/sim/model/c172p/securing/tiedownR-visible", 0)
        sequence_ok &= self._set_and_log("/sim/model/c172p/securing/tiedownT-visible", 0)
        sequence_ok &= self._set_and_log("/consumables/fuel/tank[0]/selected", 1)
        sequence_ok &= self._set_and_log("/consumables/fuel/tank[1]/selected", 1)
        sequence_ok &= self._set_and_log("/consumables/fuel/tank[0]/level-norm", 0.5)
        sequence_ok &= self._set_and_log("/consumables/fuel/tank[1]/level-norm", 0.5)
        sequence_ok &= self._set_and_log("/controls/switches/master-bat", 1)
        sequence_ok &= self._set_and_log("/controls/switches/master-alt", 1)
        sequence_ok &= self._set_and_log("/controls/switches/magnetos", 3)
        sequence_ok &= self._set_and_log("/controls/engines/current-engine/throttle", 0.2)
        sequence_ok &= self._set_and_log("/controls/engines/current-engine/mixture", 1.0)
        sequence_ok &= self._set_and_log("/controls/engines/engine/primer", 3)
        sequence_ok &= self._set_and_log("/engines/active-engine/auto-start", 1)

        if not sequence_ok:
            self._debug("One or more writes failed during the pre-starter sequence")
            return False

        if not self._set_and_log("/controls/switches/starter", 1):
            return False

        start_time = time.time()
        engine_running = False
        stable_since = None
        while time.time() - start_time < self.ENGINE_START_TIMEOUT_SECONDS:
            elapsed = time.time() - start_time
            running = self._get_bool_property("/engines/active-engine/running")
            rpm = self._get_float_property("/engines/active-engine/rpm")
            ready = self._get_float_property("/engines/active-engine/ready-oil-press-checker")
            self._debug(
                "Engine startup state -> "
                f"elapsed={elapsed:.1f}s, running={running}, rpm={rpm}, ready={ready}"
            )

            rpm_ready = rpm is not None and rpm >= self.ENGINE_MIN_RUNNING_RPM
            oil_pressure_ready = ready is not None and ready >= 2.0
            minimum_starter_time_done = elapsed >= self.MIN_STARTER_SECONDS
            if running and rpm_ready and oil_pressure_ready and minimum_starter_time_done:
                if stable_since is None:
                    stable_since = time.time()
                elif time.time() - stable_since >= self.ENGINE_STABLE_SECONDS:
                    engine_running = True
                    break
            else:
                stable_since = None

            time.sleep(0.5)

        self._set_and_log("/controls/switches/starter", 0)
        self._set_and_log("/engines/active-engine/auto-start", 0)

        if engine_running and self._wait_for_engine_stable_after_start():
            self._debug("Engine started successfully and remained stable after releasing starter")
            return True

        # Final diagnostics for the TXT log.
        self._debug("Could not start or stabilize the engine within the timeout")
        self._get_bool_property("/controls/switches/master-bat")
        self._get_bool_property("/controls/switches/master-alt")
        self._get_float_property("/controls/switches/magnetos")
        self._get_float_property("/controls/engines/current-engine/throttle")
        self._get_float_property("/controls/engines/current-engine/mixture")
        self._get_float_property("/controls/engines/engine/primer")
        self._get_float_property("/engines/active-engine/rpm")

        return False

    def _wait_for_engine_stable_after_start(self) -> bool:
        """Verify that the engine remains alive after releasing the starter."""
        start_time = time.time()
        while time.time() - start_time < self.POST_START_MONITOR_SECONDS:
            running = self._get_bool_property("/engines/active-engine/running")
            rpm = self._get_float_property("/engines/active-engine/rpm")
            self._debug(f"Post-start -> running={running}, rpm={rpm}")

            if not running or rpm is None or rpm < self.ENGINE_MIN_RUNNING_RPM:
                return False

            time.sleep(0.5)

        return True

    @staticmethod
    def _coerce_float(value: str | None) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _coerce_bool(value: str | None) -> bool | None:
        if value is None:
            return None

        lowered = value.lower()
        if lowered in {"true", "on", "yes"}:
            return True
        if lowered in {"false", "off", "no"}:
            return False

        try:
            return float(value) != 0.0
        except ValueError:
            return None

    @staticmethod
    def _fmt(value, decimals: int = 1) -> str:
        if value is None:
            return "None"
        if isinstance(value, float):
            return f"{value:.{decimals}f}"
        return str(value)

    @staticmethod
    def _clamp(value: float, min_value: float, max_value: float) -> float:
        return native_clamp(value, min_value, max_value)

    @staticmethod
    def _heading_error_deg(target_deg: float, current_deg: float) -> float:
        return native_heading_error_deg(target_deg, current_deg)

    @staticmethod
    def _heading_delta_deg(previous_deg: float, current_deg: float) -> float:
        return native_heading_delta_deg(previous_deg, current_deg)

    def _set_runway_reference(
        self,
        latitude_deg: float | None,
        longitude_deg: float | None,
        heading_deg: float | None,
        reason: str,
    ) -> bool:
        if latitude_deg is None or longitude_deg is None or heading_deg is None:
            return False

        self.runway_reference_lat_deg = latitude_deg
        self.runway_reference_lon_deg = longitude_deg
        self.runway_heading_deg = heading_deg % 360.0
        self._debug(
            "Centerline reference captured "
            f"({reason}) -> lat={latitude_deg:.8f}, lon={longitude_deg:.8f}, "
            f"runway_hdg={self.runway_heading_deg:.1f} deg"
        )
        return True

    def _ensure_runway_reference_from_sample(self, sample: dict, reason: str) -> bool:
        if (
            self.runway_reference_lat_deg is not None
            and self.runway_reference_lon_deg is not None
            and self.runway_heading_deg is not None
        ):
            return True

        heading = self.takeoff_heading_deg or sample.get("heading_deg")
        return self._set_runway_reference(
            sample.get("latitude_deg"),
            sample.get("longitude_deg"),
            heading,
            reason,
        )

    def _annotate_runway_tracking(self, sample: dict) -> None:
        latitude = sample.get("latitude_deg")
        longitude = sample.get("longitude_deg")
        heading = sample.get("heading_deg")
        if (
            latitude is None
            or longitude is None
            or heading is None
            or self.runway_reference_lat_deg is None
            or self.runway_reference_lon_deg is None
            or self.runway_heading_deg is None
        ):
            sample.update(
                runway_heading_deg=self.runway_heading_deg,
                runway_along_track_m=None,
                runway_cross_track_m=None,
                runway_cross_track_rate_mps=None,
                runway_side=None,
                runway_lookahead_m=None,
                runway_desired_heading_deg=None,
                centerline_correction_deg=None,
                control_heading_error_deg=sample.get("heading_error_deg"),
                expected_rudder_sign=None,
            )
            return

        sample.update(
            native_compute_runway_tracking(
                latitude,
                longitude,
                self.runway_reference_lat_deg,
                self.runway_reference_lon_deg,
                self.runway_heading_deg,
                heading,
                sample.get("groundspeed_kts") or 0.0,
                self.RUNWAY_CENTERLINE_LOOKAHEAD_TIME_S,
                self.RUNWAY_CENTERLINE_MIN_LOOKAHEAD_M,
                self.RUNWAY_CENTERLINE_MAX_LOOKAHEAD_M,
                self.RUNWAY_CENTERLINE_MAX_HEADING_CORRECTION_DEG,
                self.TAKEOFF_RUDDER_DEADBAND_DEG,
            )
        )

    def _takeoff_throttle_for_elapsed(self, elapsed_seconds: float) -> float:
        ramp_fraction = self._clamp(
            elapsed_seconds / self.TAKEOFF_THROTTLE_RAMP_SECONDS,
            0.0,
            1.0,
        )
        return (
            self.TAKEOFF_INITIAL_THROTTLE
            + (self.TAKEOFF_POWER - self.TAKEOFF_INITIAL_THROTTLE) * ramp_fraction
        )

    def _taxi_throttle_for_elapsed(self, elapsed_seconds: float) -> float:
        ramp_fraction = self._clamp(
            elapsed_seconds / self.TAXI_THROTTLE_RAMP_SECONDS,
            0.0,
            1.0,
        )
        return (
            self.TAXI_THROTTLE_INITIAL
            + (self.TAXI_THROTTLE_MAX - self.TAXI_THROTTLE_INITIAL) * ramp_fraction
        )

    def _taxi_throttle_command(self, elapsed_seconds: float, sample: dict) -> float:
        throttle = self._taxi_throttle_for_elapsed(elapsed_seconds)
        heading_error = self._takeoff_heading_error_abs(sample)
        control_heading_error = abs(sample.get("control_heading_error_deg") or 0.0)
        guard_heading_error = max(heading_error or 0.0, control_heading_error)
        cross_track_error = abs(sample.get("runway_cross_track_m") or 0.0)
        groundspeed = sample.get("groundspeed_kts") or 0.0
        heading_rate = abs(sample.get("heading_rate_deg_s") or 0.0)

        if (
            guard_heading_error > self.TAXI_HEADING_STABLE_DEG
        ):
            throttle = min(throttle, self.TAXI_CORRECTION_THROTTLE_MAX)

        if cross_track_error > self.TAXI_CROSSTRACK_STABLE_M:
            throttle = min(throttle, self.TAXI_CORRECTION_THROTTLE_MAX)

        if (
            groundspeed >= self.TAKEOFF_HEADING_RATE_MIN_GROUNDSPEED_KT
            and heading_rate > self.TAXI_HEADING_RATE_THROTTLE_CAP_DEG_S
        ):
            throttle = min(throttle, self.TAXI_RATE_CORRECTION_THROTTLE_MAX)

        if groundspeed > self.TAXI_TARGET_GROUNDSPEED_KT:
            throttle = min(throttle, self.TAXI_CORRECTION_THROTTLE_MAX)

        return throttle

    def _taxi_brake_commands(self, sample: dict) -> tuple[float, float]:
        heading = sample.get("heading_deg")
        groundspeed = sample.get("groundspeed_kts") or 0.0
        if (
            self.takeoff_heading_deg is None
            or heading is None
            or groundspeed > self.TAXI_DIFF_BRAKE_MAX_GROUNDSPEED_KT
        ):
            return 0.0, 0.0

        heading_error = sample.get("control_heading_error_deg")
        if heading_error is None:
            heading_error = self._heading_error_deg(self.takeoff_heading_deg, heading)
        abs_error = abs(heading_error)
        if abs_error <= self.TAXI_DIFF_BRAKE_START_DEG:
            return 0.0, 0.0

        brake_fraction = self._clamp(
            (abs_error - self.TAXI_DIFF_BRAKE_START_DEG)
            / (self.TAXI_DIFF_BRAKE_FULL_DEG - self.TAXI_DIFF_BRAKE_START_DEG),
            0.0,
            1.0,
        )
        brake = brake_fraction * self.TAXI_DIFF_BRAKE_MAX

        # Positive heading error means the aircraft must yaw right; if
        # differential braking is enabled, the right brake helps pivot.
        if heading_error > 0.0:
            return 0.0, brake
        return brake, 0.0

    def _taxi_rudder_command(self, sample: dict, power_norm: float | None = None) -> float:
        heading = sample.get("heading_deg")
        if self.takeoff_heading_deg is None or heading is None:
            target_rudder = self.TAKEOFF_RUDDER_RIGHT_BIAS
            sample.update(
                rudder_target_norm=target_rudder,
                rudder_heading_component=None,
                rudder_rate_component=None,
                rudder_power_component=None,
            )
        else:
            heading_error = sample.get("control_heading_error_deg")
            if heading_error is None:
                heading_error = self._heading_error_deg(self.takeoff_heading_deg, heading)
            if abs(heading_error) <= self.TAKEOFF_RUDDER_DEADBAND_DEG:
                heading_error = 0.0

            power_bias = 0.0
            if power_norm is not None:
                power_bias = (
                    self._clamp(power_norm, 0.0, 1.0)
                    * self.TAXI_RUDDER_POWER_FEED_FORWARD
                )

            heading_component = heading_error * self.TAXI_RUDDER_HEADING_GAIN
            raw_rudder = (
                self.TAKEOFF_RUDDER_RIGHT_BIAS
                + power_bias
                + heading_component
            )
            sample.update(
                rudder_raw_norm=raw_rudder,
                rudder_heading_component=heading_component,
                rudder_rate_component=0.0,
                rudder_power_component=power_bias,
            )

        if "rudder_raw_norm" not in sample:
            sample["rudder_raw_norm"] = target_rudder

        target_rudder = self._clamp(
            sample["rudder_raw_norm"],
            -self.TAXI_MAX_RUDDER,
            self.TAXI_MAX_RUDDER,
        )
        sample["rudder_saturated_norm"] = target_rudder
        sample["rudder_target_norm"] = target_rudder
        limited_rudder = self._clamp(
            target_rudder,
            self.last_rudder_command - self.TAXI_RUDDER_MAX_STEP,
            self.last_rudder_command + self.TAXI_RUDDER_MAX_STEP,
        )
        self.last_rudder_command = limited_rudder
        return limited_rudder

    def _takeoff_brake_commands(self, sample: dict) -> tuple[float, float]:
        heading = sample.get("heading_deg")
        groundspeed = sample.get("groundspeed_kts") or 0.0
        if (
            self.takeoff_heading_deg is None
            or heading is None
            or groundspeed > self.TAKEOFF_DIFF_BRAKE_MAX_GROUNDSPEED_KT
        ):
            return 0.0, 0.0

        heading_error = sample.get("control_heading_error_deg")
        if heading_error is None:
            heading_error = self._heading_error_deg(self.takeoff_heading_deg, heading)
        abs_error = abs(heading_error)
        if abs_error <= self.TAKEOFF_DIFF_BRAKE_START_DEG:
            return 0.0, 0.0

        brake_fraction = self._clamp(
            (abs_error - self.TAKEOFF_DIFF_BRAKE_START_DEG)
            / (self.TAKEOFF_DIFF_BRAKE_FULL_DEG - self.TAKEOFF_DIFF_BRAKE_START_DEG),
            0.0,
            1.0,
        )
        brake = brake_fraction * self.TAKEOFF_DIFF_BRAKE_MAX

        if heading_error > 0.0:
            return 0.0, brake
        return brake, 0.0

    def _takeoff_rudder_command(
        self,
        sample: dict,
        max_rudder_override: float | None = None,
        max_step: float | None = None,
        power_norm: float | None = None,
    ) -> float:
        heading = sample.get("heading_deg")
        airspeed = sample.get("airspeed_kts") or 0.0
        if max_rudder_override is not None:
            max_rudder = max_rudder_override
        else:
            max_rudder = (
                self.TAKEOFF_MAX_RUDDER_HIGH_SPEED
                if airspeed >= 45.0
                else self.TAKEOFF_MAX_RUDDER_LOW_SPEED
            )
        groundspeed = sample.get("groundspeed_kts") or 0.0
        actual_heading_error = abs(sample.get("heading_error_deg") or 0.0)
        if (
            sample.get("heading_error_deg") is None
            and self.takeoff_heading_deg is not None
            and heading is not None
        ):
            actual_heading_error = abs(
                self._heading_error_deg(self.takeoff_heading_deg, heading)
            )
        cross_track_error = abs(sample.get("runway_cross_track_m") or 0.0)
        heading_rate_abs = abs(sample.get("heading_rate_deg_s") or 0.0)
        edge_stable = (
            cross_track_error >= self.TAKEOFF_CROSSTRACK_HARD_GUARD_M
            and actual_heading_error
            <= self.TAKEOFF_HIGH_SPEED_EDGE_RUDDER_HEADING_DEG
            and heading_rate_abs
            <= self.TAKEOFF_HIGH_SPEED_EDGE_RUDDER_RATE_DEG_S
        )
        if airspeed >= 55.0:
            speed_rudder_cap = (
                self.TAKEOFF_HIGH_SPEED_EDGE_RUDDER_CAP
                if edge_stable
                else 0.22
            )
        elif airspeed >= 45.0:
            speed_rudder_cap = 0.30
        elif airspeed >= 35.0:
            speed_rudder_cap = 0.38
        elif groundspeed >= 8.0:
            speed_rudder_cap = 0.45
        elif groundspeed >= 5.0:
            speed_rudder_cap = 0.35
        else:
            speed_rudder_cap = self.TAKEOFF_MAX_RUDDER_LOW_SPEED
        max_rudder = min(max_rudder, speed_rudder_cap)

        if self.takeoff_heading_deg is None or heading is None:
            target_rudder = self.TAKEOFF_RUDDER_RIGHT_BIAS
            sample.update(
                rudder_target_norm=target_rudder,
                rudder_heading_component=None,
                rudder_rate_component=None,
                rudder_power_component=None,
            )
        else:
            heading_error = sample.get("control_heading_error_deg")
            if heading_error is None:
                heading_error = self._heading_error_deg(self.takeoff_heading_deg, heading)
            if abs(heading_error) <= self.TAKEOFF_RUDDER_DEADBAND_DEG:
                heading_error = 0.0
            power_bias = 0.0
            if power_norm is not None:
                low_speed_factor = 1.0 - self._clamp(
                    airspeed / self.ROTATION_AIRSPEED_KT,
                    0.0,
                    1.0,
                )
                power_bias = (
                    self._clamp(power_norm, 0.0, 1.0)
                    * self.TAKEOFF_RUDDER_POWER_FEED_FORWARD
                    * low_speed_factor
                )
            heading_rate = sample.get("heading_rate_deg_s") or 0.0
            if groundspeed < self.TAKEOFF_HEADING_RATE_MIN_GROUNDSPEED_KT:
                heading_rate = 0.0
            heading_component = heading_error * self.TAKEOFF_RUDDER_HEADING_GAIN
            rate_component = self._clamp(
                -heading_rate * self.TAKEOFF_RUDDER_RATE_GAIN,
                -self.TAKEOFF_RUDDER_RATE_COMPONENT_LIMIT,
                self.TAKEOFF_RUDDER_RATE_COMPONENT_LIMIT,
            )
            raw_rudder = (
                self.TAKEOFF_RUDDER_RIGHT_BIAS
                + power_bias
                + heading_component
                + rate_component
            )
            sample.update(
                rudder_raw_norm=raw_rudder,
                rudder_heading_component=heading_component,
                rudder_rate_component=rate_component,
                rudder_power_component=power_bias,
            )

        if "rudder_raw_norm" not in sample:
            sample["rudder_raw_norm"] = target_rudder

        target_rudder = self._clamp(sample["rudder_raw_norm"], -max_rudder, max_rudder)
        sample["rudder_saturated_norm"] = target_rudder
        sample["rudder_target_norm"] = target_rudder
        if max_step is None:
            self.last_rudder_command = target_rudder
            return target_rudder

        limited_rudder = self._clamp(
            target_rudder,
            self.last_rudder_command - max_step,
            self.last_rudder_command + max_step,
        )
        self.last_rudder_command = limited_rudder
        return limited_rudder

    def _takeoff_heading_error_abs(self, sample: dict) -> float | None:
        heading = sample.get("heading_deg")
        if self.takeoff_heading_deg is None or heading is None:
            return None
        return abs(self._heading_error_deg(self.takeoff_heading_deg, heading))

    def _airborne_lateral_commands(self, sample: dict) -> tuple[float, float]:
        heading = sample.get("heading_deg")
        roll = sample.get("roll_deg") or 0.0
        heading_rate = sample.get("heading_rate_deg_s") or 0.0

        if self.takeoff_heading_deg is None or heading is None:
            sample.update(
                airborne_desired_roll_deg=0.0,
                airborne_roll_error_deg=-roll,
            )
            aileron = self._clamp(
                -roll * self.AIRBORNE_AILERON_ROLL_GAIN,
                -self.AIRBORNE_MAX_AILERON,
                self.AIRBORNE_MAX_AILERON,
            )
            return aileron, 0.0

        heading_error = self._heading_error_deg(self.takeoff_heading_deg, heading)
        if abs(heading_error) <= self.TAKEOFF_RUDDER_DEADBAND_DEG:
            heading_error = 0.0

        desired_roll = self._clamp(
            heading_error * self.AIRBORNE_HEADING_TO_BANK_GAIN,
            -self.AIRBORNE_MAX_BANK_DEG,
            self.AIRBORNE_MAX_BANK_DEG,
        )
        roll_error = desired_roll - roll
        aileron = self._clamp(
            roll_error * self.AIRBORNE_AILERON_ROLL_GAIN,
            -self.AIRBORNE_MAX_AILERON,
            self.AIRBORNE_MAX_AILERON,
        )
        rudder = self._clamp(
            heading_error * self.AIRBORNE_RUDDER_HEADING_GAIN
            - heading_rate * self.AIRBORNE_RUDDER_RATE_GAIN,
            -self.AIRBORNE_MAX_RUDDER,
            self.AIRBORNE_MAX_RUDDER,
        )
        sample.update(
            airborne_desired_roll_deg=desired_roll,
            airborne_roll_error_deg=roll_error,
        )
        return aileron, rudder

    def _airborne_pitch_and_power_commands(self, sample: dict) -> tuple[float, float]:
        altitude_agl = sample.get("altitude_agl_ft") or 0.0
        airspeed = sample.get("airspeed_kts") or 0.0
        vertical_speed = sample.get("vertical_speed_fpm") or 0.0
        pitch = sample.get("pitch_deg") or 0.0

        altitude_error = self.CRUISE_TARGET_AGL_FT - altitude_agl
        in_cruise_hold_band = (
            abs(altitude_error) <= self.CRUISE_MAX_ALTITUDE_ERROR_FT
        )
        if altitude_agl < self.CRUISE_TARGET_AGL_FT - self.CRUISE_CAPTURE_BAND_FT:
            throttle = self.CLIMB_POWER
            target_pitch = self.CLIMB_TARGET_PITCH_DEG
            target_vsi = 650.0
            capture_error = altitude_error
            throttle_reason = "climb_power"
        else:
            # Lead the altitude loop with current VSI so capture starts before
            # crossing the target instead of reacting after the overshoot.
            capture_error = altitude_error - (
                vertical_speed * self.AIRBORNE_ALTITUDE_CAPTURE_LEAD_TIME_S / 60.0
            )
            target_vsi = self._clamp(
                capture_error * self.AIRBORNE_ALTITUDE_TO_VSI_GAIN,
                -self.AIRBORNE_MAX_DESCENT_CAPTURE_VSI_FPM,
                self.AIRBORNE_MAX_CLIMB_CAPTURE_VSI_FPM,
            )
            if in_cruise_hold_band:
                target_vsi = self._clamp(
                    target_vsi,
                    -self.AIRBORNE_CRUISE_HOLD_MAX_DESCENT_VSI_FPM,
                    self.AIRBORNE_CRUISE_HOLD_MAX_CLIMB_VSI_FPM,
                )
                if vertical_speed < -self.AIRBORNE_CRUISE_DESCENT_ARREST_VSI_FPM:
                    target_vsi = max(target_vsi, 0.0)
            target_pitch = self._clamp(
                self.AIRBORNE_LEVEL_PITCH_DEG
                + target_vsi * self.AIRBORNE_TARGET_VSI_TO_PITCH_GAIN,
                self.AIRBORNE_CAPTURE_MIN_PITCH_DEG,
                self.AIRBORNE_CAPTURE_MAX_PITCH_DEG,
            )
            throttle = self.CRUISE_THROTTLE
            throttle_reason = "cruise_power"
            if altitude_error > 70.0 and capture_error > 25.0:
                throttle = 0.82
                throttle_reason = "below_target_capture_power"
            elif altitude_error > 35.0 and capture_error > 10.0:
                throttle = 0.78
                throttle_reason = "below_target_soft_capture_power"
            elif altitude_error < -95.0 or capture_error < -115.0:
                throttle = self.AIRBORNE_STRONG_CAPTURE_POWER
                throttle_reason = "strong_altitude_capture_power"
            elif (
                altitude_error < -40.0
                or capture_error < -55.0
                or (altitude_error < -20.0 and vertical_speed > 40.0)
            ):
                throttle = self.AIRBORNE_CAPTURE_POWER
                throttle_reason = "altitude_capture_power"
            if in_cruise_hold_band and vertical_speed < -self.CRUISE_MAX_ABS_VERTICAL_SPEED_FPM:
                throttle = max(throttle, self.AIRBORNE_DESCENT_ARREST_POWER)
                throttle_reason = "cruise_descent_arrest_power"
            elif (
                in_cruise_hold_band
                and vertical_speed < -self.AIRBORNE_CRUISE_DESCENT_ARREST_VSI_FPM
            ):
                throttle = max(throttle, self.CRUISE_THROTTLE)
                throttle_reason = "cruise_hold_descent_power"

        if airspeed < self.CLIMB_MIN_AIRSPEED_KT:
            throttle = max(throttle, 0.90)
            target_pitch = min(target_pitch, 4.0)
            target_vsi = min(target_vsi, 150.0)
            throttle_reason = "low_airspeed_climb_power"
        elif airspeed < self.CRUISE_MIN_AIRSPEED_KT:
            throttle = max(throttle, 0.85)
            target_pitch = min(target_pitch, 5.0)
            throttle_reason = "low_airspeed_cruise_power"

        pitch_error = target_pitch - pitch
        vsi_error = target_vsi - vertical_speed
        elevator = self._clamp(
            -pitch_error * self.AIRBORNE_ELEVATOR_PITCH_GAIN
            - vsi_error * self.AIRBORNE_ELEVATOR_VSI_GAIN,
            -0.09,
            0.09,
        )
        sample.update(
            airborne_altitude_error_ft=altitude_error,
            airborne_capture_error_ft=capture_error,
            airborne_target_vsi_fpm=target_vsi,
            airborne_target_pitch_deg=target_pitch,
            airborne_pitch_error_deg=pitch_error,
            throttle_guard_reason=throttle_reason,
        )
        return elevator, throttle

    def _command_engine_failure_glide_controls(self, sample: dict) -> None:
        airspeed_raw = sample.get("airspeed_kts")
        airspeed = (
            airspeed_raw
            if airspeed_raw is not None
            else self.ENGINE_FAILURE_BEST_GLIDE_KT
        )
        vertical_speed = sample.get("vertical_speed_fpm") or 0.0
        pitch = sample.get("pitch_deg") or 0.0
        roll = sample.get("roll_deg") or 0.0
        heading = sample.get("heading_deg")
        heading_rate = sample.get("heading_rate_deg_s") or 0.0
        on_ground_detected = self._is_on_ground_sample(sample)
        airborne_detected = self._is_airborne_sample(sample)

        target_airspeed = self.ENGINE_FAILURE_BEST_GLIDE_KT
        # Positive means the aircraft is fast and can trade speed for pitch.
        airspeed_error = airspeed - target_airspeed
        target_pitch = self._clamp(
            self.ENGINE_FAILURE_BASE_PITCH_DEG
            + airspeed_error * self.ENGINE_FAILURE_AIRSPEED_TO_PITCH_GAIN,
            self.ENGINE_FAILURE_MIN_TARGET_PITCH_DEG,
            self.ENGINE_FAILURE_MAX_TARGET_PITCH_DEG,
        )

        reasons = ["best_glide_65_kias"]
        if airspeed_error > 8.0:
            reasons.append("fast_pitch_up")
        elif airspeed_error < -5.0:
            reasons.append("slow_pitch_down")

        descent_guard = 0.0
        if (
            vertical_speed < self.ENGINE_FAILURE_DESCENT_GUARD_START_FPM
            and airspeed >= self.ENGINE_FAILURE_DESCENT_GUARD_MIN_IAS_KT
        ):
            descent_guard = -self._clamp(
                (
                    self.ENGINE_FAILURE_DESCENT_GUARD_START_FPM
                    - vertical_speed
                )
                * self.ENGINE_FAILURE_ELEVATOR_VSI_GUARD_GAIN,
                0.0,
                0.035,
            )
            reasons.append("descent_guard")

        pitch_error = target_pitch - pitch
        elevator = self._clamp(
            -pitch_error * self.ENGINE_FAILURE_ELEVATOR_PITCH_GAIN
            - airspeed_error * self.ENGINE_FAILURE_ELEVATOR_AIRSPEED_GAIN
            + descent_guard,
            self.ENGINE_FAILURE_MAX_NOSE_UP_ELEVATOR,
            self.ENGINE_FAILURE_MAX_NOSE_DOWN_ELEVATOR,
        )

        if self.takeoff_heading_deg is not None and heading is not None:
            target_heading = self.takeoff_heading_deg
            heading_error = self._heading_error_deg(target_heading, heading)
            desired_roll = self._clamp(
                heading_error * self.ENGINE_FAILURE_HEADING_TO_BANK_GAIN,
                -self.ENGINE_FAILURE_MAX_BANK_DEG,
                self.ENGINE_FAILURE_MAX_BANK_DEG,
            )
            rudder_heading_component = (
                heading_error * self.ENGINE_FAILURE_RUDDER_HEADING_GAIN
            )
            rudder_rate_component = (
                -heading_rate * self.ENGINE_FAILURE_RUDDER_RATE_GAIN
            )
            rudder = self._clamp(
                rudder_heading_component + rudder_rate_component,
                -self.ENGINE_FAILURE_MAX_RUDDER,
                self.ENGINE_FAILURE_MAX_RUDDER,
            )
        else:
            target_heading = heading
            heading_error = 0.0
            desired_roll = 0.0
            rudder_heading_component = 0.0
            rudder_rate_component = 0.0
            rudder = 0.0

        roll_error = desired_roll - roll
        aileron = self._clamp(
            roll_error * self.ENGINE_FAILURE_AILERON_ROLL_GAIN,
            -self.ENGINE_FAILURE_MAX_AILERON,
            self.ENGINE_FAILURE_MAX_AILERON,
        )

        throttle = self.ENGINE_FAILURE_POWER
        trim = 0.0
        flaps = self.ENGINE_FAILURE_INITIAL_FLAPS
        brake_left = 0.0
        brake_right = 0.0
        failure_elapsed = (
            time.time() - self.engine_failure_started_at
            if self.engine_failure_started_at is not None
            else None
        )
        command_reason = "|".join(reasons)

        self._set_if_changed_and_log("/controls/flight/elevator", elevator)
        self._set_if_changed_and_log("/controls/flight/elevator-trim", trim)
        self._set_if_changed_and_log("/controls/flight/rudder", rudder)
        self._set_if_changed_and_log("/controls/flight/aileron", aileron)
        self._set_if_changed_and_log("/controls/flight/flaps", flaps)
        self._set_if_changed_and_log("/controls/gear/brake-left", brake_left)
        self._set_if_changed_and_log("/controls/gear/brake-right", brake_right)
        self._set_if_changed_and_log(
            "/controls/engines/current-engine/throttle",
            throttle,
        )

        sample.update(
            phase="engine_failure_glide",
            phase_reason="engine failed; best-glide control active",
            on_ground_detected=on_ground_detected,
            airborne_detected=airborne_detected,
            rotation_latched=False,
            heading_rate_diverging=None,
            rate_guard_active=None,
            airborne_desired_roll_deg=desired_roll,
            airborne_roll_error_deg=roll_error,
            airborne_altitude_error_ft=None,
            airborne_capture_error_ft=None,
            airborne_target_vsi_fpm=None,
            airborne_target_pitch_deg=target_pitch,
            airborne_pitch_error_deg=pitch_error,
            engine_failure_elapsed_s=failure_elapsed,
            glide_target_airspeed_kts=target_airspeed,
            glide_airspeed_error_kts=airspeed_error,
            glide_target_pitch_deg=target_pitch,
            glide_pitch_error_deg=pitch_error,
            glide_descent_guard_norm=descent_guard,
            glide_target_heading_deg=target_heading,
            glide_heading_error_deg=heading_error,
            glide_command_reason=command_reason,
            throttle_norm=throttle,
            throttle_guard_reason="engine_failure_power_off",
            aileron_norm=aileron,
            rudder_norm=rudder,
            rudder_raw_norm=rudder_heading_component + rudder_rate_component,
            rudder_saturated_norm=rudder,
            rudder_target_norm=rudder,
            rudder_heading_component=rudder_heading_component,
            rudder_rate_component=rudder_rate_component,
            rudder_power_component=0.0,
            elevator_norm=elevator,
            elevator_trim_norm=trim,
            flaps_norm=flaps,
            brake_left=brake_left,
            brake_right=brake_right,
        )

    def _raw_property_value(self, property_path: str) -> str | None:
        raw = self.proto.get_property(property_path)
        return self._extract_value(raw)

    def _sample_flight_state(
        self,
        phase: str,
        ground_altitude_ft: float | None = None,
        fast: bool = False,
        fields: set[str] | None = None,
    ) -> dict:
        property_paths = {
            "latitude_deg": "/position/latitude-deg",
            "longitude_deg": "/position/longitude-deg",
            "altitude_ft": "/position/altitude-ft",
            "altitude_agl_ft": "/position/altitude-agl-ft",
            "airspeed_kts": "/velocities/airspeed-kt",
            "groundspeed_kts": "/velocities/groundspeed-kt",
            "vertical_speed_fpm": "/instrumentation/vertical-speed-indicator/indicated-speed-fpm",
            "pitch_deg": "/orientation/pitch-deg",
            "heading_deg": "/orientation/heading-deg",
            "steer_pos_deg": "/fdm/jsbsim/fcs/steer-pos-deg",
            "nose_wheel_steer_cmd_deg": "/fdm/jsbsim/fcs/nws-cmd-deg",
            "nose_wheel_steer_adjusted_cmd_deg": "/fdm/jsbsim/fcs/nws-cmd-deg-adjusted",
            "roll_deg": "/orientation/roll-deg",
            "throttle_norm": "/controls/engines/current-engine/throttle",
            "aileron_norm": "/controls/flight/aileron",
            "rudder_norm": "/controls/flight/rudder",
            "elevator_norm": "/controls/flight/elevator",
            "elevator_trim_norm": "/controls/flight/elevator-trim",
            "flaps_norm": "/controls/flight/flaps",
            "brake_parking": "/controls/gear/brake-parking",
            "brake_left": "/controls/gear/brake-left",
            "brake_right": "/controls/gear/brake-right",
            "chock": "/sim/model/c172p/securing/chock",
            "aerotow_open": "/sim/hitches/aerotow/open",
            "hitch_force_lbs": "/fdm/jsbsim/external_reactions/hitch/magnitude",
            "wow0": "/gear/gear[0]/wow",
            "wow1": "/gear/gear[1]/wow",
            "wow2": "/gear/gear[2]/wow",
            "jsbsim_gear_wow0": "/fdm/jsbsim/gear/unit[0]/WOW",
            "jsbsim_gear_wow1": "/fdm/jsbsim/gear/unit[1]/WOW",
            "jsbsim_gear_wow2": "/fdm/jsbsim/gear/unit[2]/WOW",
            "contact_wow3": "/fdm/jsbsim/contact/unit[3]/WOW",
            "contact_wow6": "/fdm/jsbsim/contact/unit[6]/WOW",
            "contact_wow7": "/fdm/jsbsim/contact/unit[7]/WOW",
            "contact_wow8": "/fdm/jsbsim/contact/unit[8]/WOW",
            "gear_compression0_ft": "/fdm/jsbsim/gear/unit[0]/compression-ft",
            "gear_compression1_ft": "/fdm/jsbsim/gear/unit[1]/compression-ft",
            "gear_compression2_ft": "/fdm/jsbsim/gear/unit[2]/compression-ft",
            "freeze_master": "/sim/freeze/master",
            "freeze_clock": "/sim/freeze/clock",
            "freeze_position": "/sim/freeze/position",
            "magnetos": "/controls/switches/magnetos",
            "engine_running": "/engines/active-engine/running",
            "engine_rpm": "/engines/active-engine/rpm",
        }

        if fields is not None:
            property_paths = {
                name: path
                for name, path in property_paths.items()
                if name in fields
            }
        elif fast:
            fast_fields = {
                "latitude_deg",
                "longitude_deg",
                "altitude_ft",
                "airspeed_kts",
                "groundspeed_kts",
                "vertical_speed_fpm",
                "pitch_deg",
                "heading_deg",
                "roll_deg",
                "engine_running",
                "engine_rpm",
            }
            property_paths = {
                name: path
                for name, path in property_paths.items()
                if name in fast_fields
            }

        if hasattr(self.proto, "get_properties"):
            raw_by_path = self.proto.get_properties(list(property_paths.values()))
            raw_values = {
                name: self._extract_value(raw_by_path.get(path))
                for name, path in property_paths.items()
            }
        else:
            raw_values = {
                name: self._raw_property_value(path)
                for name, path in property_paths.items()
            }

        received_names = [
            name
            for name, value in raw_values.items()
            if value is not None
        ]
        missing_names = [
            name
            for name, value in raw_values.items()
            if value is None
        ]

        sample = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "phase": phase,
            "telemetry_valid": bool(received_names),
            "telemetry_values_received": len(received_names),
            "telemetry_values_expected": len(property_paths),
            "telemetry_missing_fields": ";".join(missing_names),
        }

        float_fields = {
            "latitude_deg",
            "longitude_deg",
            "altitude_ft",
            "altitude_agl_ft",
            "airspeed_kts",
            "groundspeed_kts",
            "vertical_speed_fpm",
            "pitch_deg",
            "heading_deg",
            "steer_pos_deg",
            "nose_wheel_steer_cmd_deg",
            "nose_wheel_steer_adjusted_cmd_deg",
            "roll_deg",
            "throttle_norm",
            "aileron_norm",
            "rudder_norm",
            "elevator_norm",
            "elevator_trim_norm",
            "flaps_norm",
            "brake_left",
            "brake_right",
            "hitch_force_lbs",
            "gear_compression0_ft",
            "gear_compression1_ft",
            "gear_compression2_ft",
            "magnetos",
            "engine_rpm",
            "runway_heading_deg",
            "runway_along_track_m",
            "runway_cross_track_m",
            "runway_cross_track_rate_mps",
            "runway_lookahead_m",
            "runway_desired_heading_deg",
            "centerline_correction_deg",
            "control_heading_error_deg",
            "rudder_raw_norm",
            "rudder_saturated_norm",
            "airborne_desired_roll_deg",
            "airborne_roll_error_deg",
            "airborne_altitude_error_ft",
            "airborne_capture_error_ft",
            "airborne_target_vsi_fpm",
            "airborne_target_pitch_deg",
            "airborne_pitch_error_deg",
            "engine_failure_elapsed_s",
            "glide_target_airspeed_kts",
            "glide_airspeed_error_kts",
            "glide_target_pitch_deg",
            "glide_pitch_error_deg",
            "glide_descent_guard_norm",
            "glide_target_heading_deg",
            "glide_heading_error_deg",
        }
        bool_fields = {
            "brake_parking",
            "chock",
            "aerotow_open",
            "wow0",
            "wow1",
            "wow2",
            "jsbsim_gear_wow0",
            "jsbsim_gear_wow1",
            "jsbsim_gear_wow2",
            "contact_wow3",
            "contact_wow6",
            "contact_wow7",
            "contact_wow8",
            "freeze_master",
            "freeze_clock",
            "freeze_position",
            "engine_running",
        }

        for name, value in raw_values.items():
            if name in float_fields:
                sample[name] = self._coerce_float(value)
            elif name in bool_fields:
                sample[name] = self._coerce_bool(value)
            else:
                sample[name] = value

        altitude_ft = sample.get("altitude_ft")
        direct_agl_ft = sample.get("altitude_agl_ft")
        if direct_agl_ft is None and altitude_ft is not None and ground_altitude_ft is not None:
            sample["altitude_agl_ft"] = altitude_ft - ground_altitude_ft
        elif direct_agl_ft is None:
            sample["altitude_agl_ft"] = None

        heading = sample.get("heading_deg")
        if self.takeoff_heading_deg is not None and heading is not None:
            sample["heading_error_deg"] = self._heading_error_deg(
                self.takeoff_heading_deg,
                heading,
            )
        else:
            sample["heading_error_deg"] = None

        self._ensure_runway_reference_from_sample(sample, f"sample {phase}")
        self._annotate_runway_tracking(sample)

        now = time.time()
        cross_track = sample.get("runway_cross_track_m")
        if (
            cross_track is not None
            and self.last_cross_track_sample_m is not None
            and self.last_cross_track_sample_time is not None
        ):
            elapsed = max(now - self.last_cross_track_sample_time, 1e-6)
            sample["runway_cross_track_rate_mps"] = (
                (cross_track - self.last_cross_track_sample_m) / elapsed
            )

        if cross_track is not None:
            self.last_cross_track_sample_m = cross_track
            self.last_cross_track_sample_time = now

        if (
            heading is not None
            and self.last_heading_sample_deg is not None
            and self.last_heading_sample_time is not None
        ):
            elapsed = max(now - self.last_heading_sample_time, 1e-6)
            sample["heading_rate_deg_s"] = (
                self._heading_delta_deg(self.last_heading_sample_deg, heading)
                / elapsed
            )
        else:
            sample["heading_rate_deg_s"] = None

        if heading is not None:
            self.last_heading_sample_deg = heading
            self.last_heading_sample_time = now

        return sample

    def _telemetry_missing_required_fields(
        self,
        sample: dict,
        required_fields: set[str] | None = None,
    ) -> list[str]:
        if (sample.get("telemetry_values_received") or 0) <= 0:
            return sorted(required_fields or {"<all>"})
        if not required_fields:
            return []
        return sorted(
            field
            for field in required_fields
            if sample.get(field) is None
        )

    def _sample_has_required_telemetry(
        self,
        sample: dict,
        required_fields: set[str] | None = None,
    ) -> bool:
        return not self._telemetry_missing_required_fields(sample, required_fields)

    def _sample_flight_state_with_retries(
        self,
        phase: str,
        ground_altitude_ft: float | None = None,
        fast: bool = False,
        fields: set[str] | None = None,
        required_fields: set[str] | None = None,
    ) -> dict:
        attempts = max(1, self.TELEMETRY_RETRY_ATTEMPTS)
        last_sample: dict | None = None

        for attempt in range(1, attempts + 1):
            sample = self._sample_flight_state(
                phase,
                ground_altitude_ft,
                fast=fast,
                fields=fields,
            )
            missing_required = self._telemetry_missing_required_fields(
                sample,
                required_fields,
            )
            if not missing_required:
                return sample

            sample["telemetry_valid"] = False
            sample["phase_reason"] = (
                "telemetry incomplete; retrying"
                if attempt < attempts
                else "telemetry incomplete after retries"
            )
            last_sample = sample
            if attempt < attempts:
                self._debug(
                    "Incomplete telemetry in "
                    f"{phase} attempt {attempt}/{attempts}: "
                    f"missing {', '.join(missing_required)}. Retrying."
                )
                time.sleep(self.TELEMETRY_RETRY_DELAY_SECONDS)

        return last_sample or {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "phase": phase,
            "phase_reason": "telemetry unavailable",
            "telemetry_valid": False,
            "telemetry_values_received": 0,
            "telemetry_values_expected": 0,
            "telemetry_missing_fields": "",
        }

    def _skip_invalid_telemetry_tick(
        self,
        sample: dict,
        context: str,
    ) -> bool:
        if sample.get("telemetry_valid") is not False:
            return False

        self._append_telemetry_row(sample)
        self._debug(
            f"{context}: incomplete telemetry after retries; "
            "keeping the last command and skipping engine/phase evaluation for this tick."
        )
        return True

    def _append_telemetry_row(self, sample: dict) -> None:
        row = [
            "" if sample.get(column) is None else sample.get(column)
            for column in self.CSV_COLUMNS
        ]

        with open(self.csv_path, "a", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(row)

    def _write_telemetry_sample(
        self,
        phase: str,
        ground_altitude_ft: float | None = None,
        fast: bool = False,
    ) -> dict:
        sample = self._sample_flight_state_with_retries(
            phase,
            ground_altitude_ft,
            fast=fast,
        )
        self._append_telemetry_row(sample)
        return sample

    def _release_ground_constraints(self) -> bool:
        ok = True
        release_commands = [
            ("/sim/freeze/master", 0),
            ("/sim/freeze/clock", 0),
            ("/sim/freeze/position", 0),
            ("/sim/freeze/fuel", 0),
            ("/sim/freeze/replay-state", 0),
            ("/controls/gear/brake-parking", 0),
            ("/controls/gear/brake-left", 0),
            ("/controls/gear/brake-right", 0),
            ("/sim/model/c172p/cockpit/control-lock-placed", 0),
            ("/sim/model/c172p/cockpit/control-lock-visible", 0),
            ("/sim/model/c172p/securing/chock", 0),
            ("/sim/model/c172p/securing/chock-visible", 0),
            ("/sim/model/c172p/securing/cowl-plugs-visible", 0),
            ("/sim/model/c172p/securing/pitot-cover-visible", 0),
            ("/sim/model/c172p/securing/tiedownL-visible", 0),
            ("/sim/model/c172p/securing/tiedownR-visible", 0),
            ("/sim/model/c172p/securing/tiedownT-visible", 0),
            ("/sim/hitches/aerotow/open", 1),
            ("/sim/hitches/aerotow/tow/dist", -1),
            ("/fdm/jsbsim/external_reactions/hitch/magnitude", 0),
            ("/fdm/jsbsim/external_reactions/hitch/x", 0),
            ("/fdm/jsbsim/external_reactions/hitch/y", 0),
            ("/fdm/jsbsim/external_reactions/hitch/z", 0),
        ]

        for property_path, value in release_commands:
            ok &= self._set_and_log(property_path, value)

        return ok

    def _clear_simulation_freezes(self) -> bool:
        ok = True
        freeze_commands = [
            ("/sim/freeze/master", 0),
            ("/sim/freeze/clock", 0),
            ("/sim/freeze/position", 0),
            ("/sim/freeze/fuel", 0),
            ("/sim/freeze/replay-state", 0),
            ("/sim/time/paused", 0),
        ]

        for property_path, value in freeze_commands:
            ok &= self._set_and_log(property_path, value)

        return ok

    def _prepare_for_ground_roll(self) -> bool:
        self._debug("Preparing aircraft for taxi/takeoff from the ground")
        self.last_rudder_command = self.TAKEOFF_RUDDER_RIGHT_BIAS
        self.last_heading_sample_deg = None
        self.last_heading_sample_time = None
        self.last_cross_track_sample_m = None
        self.last_cross_track_sample_time = None
        self.rotation_started_at = None
        self.last_control_commands.clear()
        ok = self._release_ground_constraints()
        takeoff_commands = [
            ("/controls/flight/auto-coordination", 0),
            ("/controls/flight/aileron", 0.0),
            ("/controls/flight/rudder", self.TAKEOFF_RUDDER_RIGHT_BIAS),
            ("/controls/flight/elevator", self.TAKEOFF_NOSE_DOWN_ELEVATOR),
            ("/controls/flight/elevator-trim", 0.0),
            ("/controls/flight/flaps", 0.0),
            ("/controls/engines/current-engine/mixture", 1.0),
            ("/controls/engines/current-engine/throttle", self.TAXI_THROTTLE_INITIAL),
        ]

        for property_path, value in takeoff_commands:
            ok &= self._set_and_log(property_path, value)

        return ok

    def _engine_alive_in_sample(self, sample: dict) -> bool:
        running = sample.get("engine_running")
        rpm = sample.get("engine_rpm")
        if running is False:
            return False
        if running is None:
            # Missing telemetry is not evidence of an engine failure. Critical
            # loops retry/skip invalid samples before reaching this check.
            return True
        if rpm is None:
            # Telnet occasionally returns an empty value while the sim is busy;
            # keep moving if the explicit running flag still says the engine is alive.
            return True
        return rpm >= self.ENGINE_MIN_RUNNING_RPM

    def _is_ground_roll_started(self, sample: dict) -> bool:
        groundspeed = sample.get("groundspeed_kts")
        airspeed = sample.get("airspeed_kts") or 0.0
        if groundspeed is not None:
            return groundspeed >= self.GROUND_ROLL_MIN_GROUNDSPEED_KT
        return airspeed >= self.GROUND_ROLL_MIN_AIRSPEED_KT

    def _is_on_ground_sample(self, sample: dict) -> bool | None:
        wow_values = [
            sample.get("wow0"),
            sample.get("wow1"),
            sample.get("wow2"),
            sample.get("jsbsim_gear_wow0"),
            sample.get("jsbsim_gear_wow1"),
            sample.get("jsbsim_gear_wow2"),
        ]
        known_wow_values = [value for value in wow_values if value is not None]
        if any(known_wow_values):
            return True

        compression_values = [
            sample.get("gear_compression0_ft"),
            sample.get("gear_compression1_ft"),
            sample.get("gear_compression2_ft"),
        ]
        known_compressions = [
            value for value in compression_values if value is not None
        ]
        if known_compressions:
            return any(value > 0.001 for value in known_compressions)

        if known_wow_values:
            return False

        return None

    def _is_airborne_sample(self, sample: dict) -> bool:
        on_ground = self._is_on_ground_sample(sample)
        altitude_agl = sample.get("altitude_agl_ft") or 0.0
        if on_ground is False:
            return True
        if on_ground is True:
            return altitude_agl >= self.AIRBORNE_MIN_AGL_FT
        return altitude_agl >= self.LIFTOFF_MIN_AGL_FT

    def _is_cruise_sample(self, sample: dict) -> bool:
        altitude_agl = sample.get("altitude_agl_ft") or 0.0
        airspeed = sample.get("airspeed_kts") or 0.0
        vertical_speed = sample.get("vertical_speed_fpm")
        pitch = sample.get("pitch_deg")
        roll = sample.get("roll_deg")
        heading_error = sample.get("heading_error_deg")
        on_ground = self._is_on_ground_sample(sample)
        altitude_error = self.CRUISE_TARGET_AGL_FT - altitude_agl

        stable_altitude = abs(altitude_error) <= self.CRUISE_MAX_ALTITUDE_ERROR_FT
        stable_vertical_speed = (
            vertical_speed is None
            or abs(vertical_speed) <= self.CRUISE_MAX_ABS_VERTICAL_SPEED_FPM
        )
        stable_pitch = (
            pitch is None
            or abs(pitch) <= self.CRUISE_MAX_ABS_PITCH_DEG
        )
        stable_roll = (
            roll is None
            or abs(roll) <= self.CRUISE_MAX_ABS_ROLL_DEG
        )
        stable_heading = (
            heading_error is None
            or abs(heading_error) <= self.CRUISE_MAX_HEADING_ERROR_DEG
        )

        return (
            self._engine_alive_in_sample(sample)
            and altitude_agl >= self.CRUISE_MIN_AGL_FT
            and stable_altitude
            and airspeed >= self.CRUISE_MIN_AIRSPEED_KT
            and on_ground is not True
            and stable_vertical_speed
            and stable_pitch
            and stable_roll
            and stable_heading
        )

    def _summarize_sample(self, sample: dict) -> str:
        return (
            f"phase={sample.get('phase')}, "
            f"reason={sample.get('phase_reason')}, "
            f"tel_ok={sample.get('telemetry_valid')}, "
            f"tel_rx={sample.get('telemetry_values_received')}/"
            f"{sample.get('telemetry_values_expected')}, "
            f"tel_missing={sample.get('telemetry_missing_fields')}, "
            f"on_ground={sample.get('on_ground_detected')}, "
            f"airborne={sample.get('airborne_detected')}, "
            f"rot_latched={sample.get('rotation_latched')}, "
            f"lat={self._fmt(sample.get('latitude_deg'), 6)}, "
            f"lon={self._fmt(sample.get('longitude_deg'), 6)}, "
            f"agl={self._fmt(sample.get('altitude_agl_ft'))}ft, "
            f"ias={self._fmt(sample.get('airspeed_kts'))}kt, "
            f"gs={self._fmt(sample.get('groundspeed_kts'))}kt, "
            f"rwy_hdg={self._fmt(sample.get('runway_heading_deg'))}deg, "
            f"along={self._fmt(sample.get('runway_along_track_m'))}m, "
            f"xtrack={self._fmt(sample.get('runway_cross_track_m'))}m, "
            f"xtrack_rate={self._fmt(sample.get('runway_cross_track_rate_mps'))}m/s, "
            f"side={sample.get('runway_side')}, "
            f"lookahead={self._fmt(sample.get('runway_lookahead_m'))}m, "
            f"rwy_des_hdg={self._fmt(sample.get('runway_desired_heading_deg'))}deg, "
            f"ctr_corr={self._fmt(sample.get('centerline_correction_deg'))}deg, "
            f"ctrl_hdg_err={self._fmt(sample.get('control_heading_error_deg'))}deg, "
            f"exp_rud={sample.get('expected_rudder_sign')}, "
            f"vsi={self._fmt(sample.get('vertical_speed_fpm'), 0)}fpm, "
            f"pitch={self._fmt(sample.get('pitch_deg'))}deg, "
            f"hdg={self._fmt(sample.get('heading_deg'))}deg, "
            f"hdg_err={self._fmt(sample.get('heading_error_deg'))}deg, "
            f"hdg_rate={self._fmt(sample.get('heading_rate_deg_s'))}deg/s, "
            f"hdg_rate_div={sample.get('heading_rate_diverging')}, "
            f"rate_guard={sample.get('rate_guard_active')}, "
            f"steer={self._fmt(sample.get('steer_pos_deg'))}deg, "
            f"nws_cmd={self._fmt(sample.get('nose_wheel_steer_cmd_deg'))}deg, "
            f"nws_adj={self._fmt(sample.get('nose_wheel_steer_adjusted_cmd_deg'))}deg, "
            f"roll={self._fmt(sample.get('roll_deg'))}deg, "
            f"air_roll_tgt={self._fmt(sample.get('airborne_desired_roll_deg'))}deg, "
            f"air_roll_err={self._fmt(sample.get('airborne_roll_error_deg'))}deg, "
            f"air_alt_err={self._fmt(sample.get('airborne_altitude_error_ft'))}ft, "
            f"air_cap_err={self._fmt(sample.get('airborne_capture_error_ft'))}ft, "
            f"air_vsi_tgt={self._fmt(sample.get('airborne_target_vsi_fpm'), 0)}fpm, "
            f"air_pitch_tgt={self._fmt(sample.get('airborne_target_pitch_deg'))}deg, "
            f"air_pitch_err={self._fmt(sample.get('airborne_pitch_error_deg'))}deg, "
            f"glide_t={self._fmt(sample.get('engine_failure_elapsed_s'))}s, "
            f"glide_ias_tgt={self._fmt(sample.get('glide_target_airspeed_kts'))}kt, "
            f"glide_ias_err={self._fmt(sample.get('glide_airspeed_error_kts'))}kt, "
            f"glide_pitch_tgt={self._fmt(sample.get('glide_target_pitch_deg'))}deg, "
            f"glide_pitch_err={self._fmt(sample.get('glide_pitch_error_deg'))}deg, "
            f"glide_vsi_guard={self._fmt(sample.get('glide_descent_guard_norm'), 3)}, "
            f"glide_hdg_tgt={self._fmt(sample.get('glide_target_heading_deg'))}deg, "
            f"glide_hdg_err={self._fmt(sample.get('glide_heading_error_deg'))}deg, "
            f"glide_reason={sample.get('glide_command_reason')}, "
            f"thr={self._fmt(sample.get('throttle_norm'), 2)}, "
            f"thr_reason={sample.get('throttle_guard_reason')}, "
            f"ail={self._fmt(sample.get('aileron_norm'), 2)}, "
            f"rud={self._fmt(sample.get('rudder_norm'), 2)}, "
            f"rud_raw={self._fmt(sample.get('rudder_raw_norm'), 2)}, "
            f"rud_sat={self._fmt(sample.get('rudder_saturated_norm'), 2)}, "
            f"rud_tgt={self._fmt(sample.get('rudder_target_norm'), 2)}, "
            "rud_comp=("
            f"{self._fmt(sample.get('rudder_heading_component'), 2)},"
            f"{self._fmt(sample.get('rudder_rate_component'), 2)},"
            f"{self._fmt(sample.get('rudder_power_component'), 2)}), "
            f"elev={self._fmt(sample.get('elevator_norm'), 2)}, "
            f"trim={self._fmt(sample.get('elevator_trim_norm'), 2)}, "
            f"brakes=({sample.get('brake_parking')},"
            f"{self._fmt(sample.get('brake_left'), 2)},"
            f"{self._fmt(sample.get('brake_right'), 2)}), "
            f"chock={sample.get('chock')}, "
            f"hitch_open={sample.get('aerotow_open')}, "
            f"hitch_force={self._fmt(sample.get('hitch_force_lbs'))}, "
            f"wow=({sample.get('wow0')},{sample.get('wow1')},{sample.get('wow2')}), "
            "jsbsim_wow=("
            f"{sample.get('jsbsim_gear_wow0')},"
            f"{sample.get('jsbsim_gear_wow1')},"
            f"{sample.get('jsbsim_gear_wow2')}), "
            "contact_wow=("
            f"{sample.get('contact_wow3')},"
            f"{sample.get('contact_wow6')},"
            f"{sample.get('contact_wow7')},"
            f"{sample.get('contact_wow8')}), "
            "comp_ft=("
            f"{self._fmt(sample.get('gear_compression0_ft'), 3)},"
            f"{self._fmt(sample.get('gear_compression1_ft'), 3)},"
            f"{self._fmt(sample.get('gear_compression2_ft'), 3)}), "
            "freeze=("
            f"{sample.get('freeze_master')},"
            f"{sample.get('freeze_clock')},"
            f"{sample.get('freeze_position')}), "
            f"running={sample.get('engine_running')}, "
            f"rpm={self._fmt(sample.get('engine_rpm'), 0)}"
        )

    def _log_ground_blockers(self) -> None:
        self._debug("Final ground-blocker diagnostics:")
        diagnostic_paths = [
            "/controls/gear/brake-parking",
            "/controls/gear/brake-left",
            "/controls/gear/brake-right",
            "/sim/model/c172p/securing/chock",
            "/sim/model/c172p/securing/chock-visible",
            "/sim/hitches/aerotow/open",
            "/sim/hitches/aerotow/tow/dist",
            "/fdm/jsbsim/external_reactions/hitch/magnitude",
            "/gear/gear[0]/wow",
            "/gear/gear[1]/wow",
            "/gear/gear[2]/wow",
            "/fdm/jsbsim/gear/unit[0]/WOW",
            "/fdm/jsbsim/gear/unit[1]/WOW",
            "/fdm/jsbsim/gear/unit[2]/WOW",
            "/fdm/jsbsim/contact/unit[3]/WOW",
            "/fdm/jsbsim/contact/unit[6]/WOW",
            "/fdm/jsbsim/contact/unit[7]/WOW",
            "/fdm/jsbsim/contact/unit[8]/WOW",
            "/fdm/jsbsim/gear/unit[0]/compression-ft",
            "/fdm/jsbsim/gear/unit[1]/compression-ft",
            "/fdm/jsbsim/gear/unit[2]/compression-ft",
            "/gear/gear[0]/rollspeed-ms",
            "/gear/gear[1]/rollspeed-ms",
            "/gear/gear[2]/rollspeed-ms",
            "/sim/freeze/master",
            "/sim/freeze/clock",
            "/sim/freeze/position",
            "/sim/freeze/replay-state",
            "/velocities/groundspeed-kt",
            "/velocities/airspeed-kt",
            "/orientation/heading-deg",
            "/orientation/roll-deg",
            "/controls/flight/rudder",
            "/fdm/jsbsim/fcs/steer-pos-deg",
            "/fdm/jsbsim/fcs/nws-cmd-deg",
            "/fdm/jsbsim/fcs/nws-cmd-deg-adjusted",
            "/controls/flight/elevator-trim",
            "/engines/active-engine/rpm",
        ]

        for property_path in diagnostic_paths:
            value = self._raw_property_value(property_path)
            self._debug(f"DIAG {property_path} -> {value}")

    def _wait_for_ground_roll(self, ground_altitude_ft: float) -> bool:
        self._debug(
            "Validating straight taxi before takeoff: "
            f"groundspeed >= {self.GROUND_ROLL_MIN_GROUNDSPEED_KT} kt, "
            f"heading <= {self.TAXI_HEADING_STABLE_DEG} deg, "
            f"cross-track <= {self.TAXI_CROSSTRACK_STABLE_M} m, "
            f"heading_rate <= {self.TAXI_HEADING_RATE_STABLE_DEG_S} deg/s por "
            f"{self.TAXI_STABLE_SECONDS}s"
        )
        start_time = time.time()
        stable_since = None
        acceptable_since = None
        self.takeoff_roll_started_at = None

        while time.time() - start_time < self.GROUND_ROLL_TIMEOUT_SECONDS:
            elapsed = time.time() - start_time
            sample = self._sample_flight_state_with_retries(
                "ground_roll",
                ground_altitude_ft,
                fields=self.GROUND_ROLL_SAMPLE_FIELDS,
                required_fields={
                    "latitude_deg",
                    "longitude_deg",
                    "groundspeed_kts",
                    "heading_deg",
                    "engine_running",
                },
            )
            if self._skip_invalid_telemetry_tick(sample, f"Taxi t={elapsed:.1f}s"):
                time.sleep(0.5)
                continue

            if self.takeoff_heading_deg is None and sample.get("heading_deg") is not None:
                self.takeoff_heading_deg = sample["heading_deg"]
                self._debug(
                    "Takeoff target heading set from initial position: "
                    f"{self.takeoff_heading_deg:.1f} deg"
            )

            throttle = self._taxi_throttle_command(elapsed, sample)
            rudder = self._taxi_rudder_command(sample, power_norm=throttle)
            brake_left, brake_right = self._taxi_brake_commands(sample)
            self._set_if_changed_and_log("/controls/flight/rudder", rudder)
            self._set_if_changed_and_log("/controls/flight/aileron", 0.0)
            self._set_if_changed_and_log(
                "/controls/flight/elevator",
                self.TAKEOFF_NOSE_DOWN_ELEVATOR,
            )
            self._set_if_changed_and_log("/controls/gear/brake-left", brake_left)
            self._set_if_changed_and_log("/controls/gear/brake-right", brake_right)
            self._set_if_changed_and_log(
                "/controls/engines/current-engine/throttle",
                throttle,
            )
            sample.update(
                throttle_norm=throttle,
                aileron_norm=0.0,
                rudder_norm=rudder,
                elevator_norm=self.TAKEOFF_NOSE_DOWN_ELEVATOR,
                elevator_trim_norm=0.0,
                flaps_norm=0.0,
                brake_left=brake_left,
                brake_right=brake_right,
            )
            self._append_telemetry_row(sample)
            self._debug(f"Taxi t={elapsed:.1f}s -> {self._summarize_sample(sample)}")

            if not self._engine_alive_in_sample(sample):
                self._debug(
                    "Engine is not stable during taxi. "
                    "Aborting before attempting takeoff."
                )
                self._abort_takeoff_roll()
                return False

            heading_error = self._takeoff_heading_error_abs(sample)
            control_heading_error = abs(sample.get("control_heading_error_deg") or 0.0)
            guard_heading_error = max(heading_error or 0.0, control_heading_error)
            taxi_cross_track = abs(sample.get("runway_cross_track_m") or 0.0)
            heading_rate = abs(sample.get("heading_rate_deg_s") or 0.0)
            groundspeed = sample.get("groundspeed_kts") or 0.0
            moving = self._is_ground_roll_started(sample)

            if (
                moving
                and groundspeed >= self.GROUND_ROLL_MIN_GROUNDSPEED_KT
                and guard_heading_error >= self.TAXI_HEADING_ABORT_DEG
            ):
                self._debug(
                    "Excessive heading deviation during taxi "
                    f"(hdg={heading_error}, control={control_heading_error:.1f} deg). "
                    "Cutting power to avoid a crash."
                )
                self._abort_takeoff_roll()
                return False

            if (
                moving
                and groundspeed >= self.TAXI_MAX_GROUNDSPEED_KT
                and (
                    heading_error is None
                    or guard_heading_error > self.TAXI_HEADING_STABLE_DEG
                    or taxi_cross_track > self.TAXI_CROSSTRACK_STABLE_M
                )
            ):
                self._debug(
                    "Taxi is already too fast without being aligned "
                    f"(gs={groundspeed:.1f} kt, heading_error={heading_error}, "
                    f"control_heading_error={control_heading_error:.1f}, "
                    f"xtrack={taxi_cross_track:.1f} m). "
                    "Aborting before attempting takeoff."
                )
                self._abort_takeoff_roll()
                return False

            taxi_is_stable = (
                moving
                and heading_error is not None
                and guard_heading_error <= self.TAXI_HEADING_STABLE_DEG
                and taxi_cross_track <= self.TAXI_CROSSTRACK_STABLE_M
                and heading_rate <= self.TAXI_HEADING_RATE_STABLE_DEG_S
                and groundspeed <= self.TAXI_MAX_GROUNDSPEED_KT
            )
            taxi_is_acceptably_straight = (
                moving
                and heading_error is not None
                and guard_heading_error <= self.TAXI_HEADING_ACCEPTABLE_DEG
                and taxi_cross_track <= self.TAXI_CROSSTRACK_ACCEPTABLE_M
                and heading_rate <= self.TAXI_HEADING_RATE_STABLE_DEG_S
                and groundspeed <= self.TAXI_MAX_GROUNDSPEED_KT
            )
            if taxi_is_stable:
                if stable_since is None:
                    stable_since = time.time()
                    self._debug(
                        "Straight taxi detected; waiting for stability before takeoff"
                    )
                elif time.time() - stable_since >= self.TAXI_STABLE_SECONDS:
                    self._debug(
                        "Straight taxi confirmed: aircraft is moving and holding runway centerline"
                    )
                    self._set_and_log("/controls/gear/brake-left", 0.0)
                    self._set_and_log("/controls/gear/brake-right", 0.0)
                    return True
            else:
                stable_since = None

            if taxi_is_acceptably_straight:
                if acceptable_since is None:
                    acceptable_since = time.time()
                    self._debug(
                        "Taxi is stable with moderate deviation; "
                        "accepting if it holds without increasing turn rate"
                    )
                elif time.time() - acceptable_since >= self.TAXI_ACCEPTABLE_STABLE_SECONDS:
                    self._debug(
                        "Acceptable taxi confirmed: aircraft is moving straight without "
                        "strong oscillation; continuing to takeoff roll"
                    )
                    self._set_and_log("/controls/gear/brake-left", 0.0)
                    self._set_and_log("/controls/gear/brake-right", 0.0)
                    return True
            else:
                acceptable_since = None

            time.sleep(0.5)

        self._debug(
            "Could not achieve straight, controlled taxi within the timeout. "
            "Takeoff will not be attempted and the failure will not be injected."
        )
        self._abort_takeoff_roll()
        self._log_ground_blockers()
        return False

    def _wait_for_ground_contact_ready(self) -> bool:
        self._debug("Validating real landing-gear ground contact before engine start")
        start_time = time.time()
        contact_only_warned = False

        while time.time() - start_time < self.GROUND_CONTACT_TIMEOUT_SECONDS:
            elapsed = time.time() - start_time
            sample = self._write_telemetry_sample("ground_contact_check")
            self._debug(
                f"Ground contact t={elapsed:.1f}s -> "
                f"{self._summarize_sample(sample)}"
            )

            on_ground = self._is_on_ground_sample(sample)
            if on_ground is True:
                self._debug("Real landing-gear ground contact confirmed before engine start")
                return True

            if (
                not contact_only_warned
                and any(
                    sample.get(name)
                    for name in (
                        "contact_wow3",
                        "contact_wow6",
                        "contact_wow7",
                        "contact_wow8",
                    )
                )
            ):
                self._debug(
                    "contact_wow was detected, but it is not accepted as landing gear contact. "
                    "Waiting for real main/nose gear WOW/compression."
                )
                contact_only_warned = True

            if elapsed >= 5.0:
                self._clear_simulation_freezes()

            time.sleep(1.0)

        self._debug(
            "Ground contact was not confirmed before engine start. "
            "Aborting to avoid an invalid test."
        )
        self._log_ground_blockers()
        return False

    def _abort_takeoff_roll(self) -> None:
        self.last_rudder_command = 0.0
        self.rotation_started_at = None
        self.last_control_commands.clear()
        self._set_and_log("/controls/engines/current-engine/throttle", 0.0)
        self._set_and_log("/controls/flight/rudder", 0.0)
        self._set_and_log("/controls/flight/aileron", 0.0)
        self._set_and_log("/controls/flight/elevator", 0.0)
        self._set_and_log("/controls/flight/elevator-trim", 0.0)
        self._set_and_log("/controls/gear/brake-left", 0.2)
        self._set_and_log("/controls/gear/brake-right", 0.2)

    def _command_takeoff_or_cruise_controls(
        self,
        sample: dict,
        takeoff_elapsed: float | None = None,
    ) -> None:
        altitude_agl = sample.get("altitude_agl_ft") or 0.0
        airspeed = sample.get("airspeed_kts") or 0.0
        vertical_speed = sample.get("vertical_speed_fpm") or 0.0
        pitch = sample.get("pitch_deg") or 0.0
        on_ground_detected = self._is_on_ground_sample(sample)
        airborne_detected = self._is_airborne_sample(sample)
        if airborne_detected and self.rotation_started_at is not None:
            self.rotation_started_at = None
            sample["phase"] = "initial_climb"
            sample["phase_reason"] = "liftoff detected; switching to climbout control"

        heading_error = self._takeoff_heading_error_abs(sample)
        signed_control_heading_error = sample.get("control_heading_error_deg") or 0.0
        control_heading_error = abs(signed_control_heading_error)
        signed_cross_track = sample.get("runway_cross_track_m") or 0.0
        cross_track_error = abs(signed_cross_track)
        cross_track_rate = sample.get("runway_cross_track_rate_mps") or 0.0
        runway_guard_error = heading_error or 0.0
        signed_heading_rate = sample.get("heading_rate_deg_s") or 0.0
        heading_rate_abs = abs(signed_heading_rate)
        moving_away_from_centerline = signed_cross_track * cross_track_rate > 0.0
        cross_track_rate_safe_for_rotation = (
            not moving_away_from_centerline
            or abs(cross_track_rate)
            <= self.TAKEOFF_ROTATION_MAX_AWAY_CROSSTRACK_RATE_MPS
        )
        heading_rate_diverging = (
            abs(signed_control_heading_error) > self.TAKEOFF_RUDDER_DEADBAND_DEG
            and signed_control_heading_error * signed_heading_rate < 0.0
        )
        rate_guard_active = (
            (
                heading_rate_diverging
                and (
                    control_heading_error
                    >= self.TAKEOFF_HEADING_RATE_GUARD_MIN_HEADING_ERROR_DEG
                    or cross_track_error
                    >= self.TAKEOFF_HEADING_RATE_GUARD_CROSSTRACK_M
                )
            )
            or cross_track_error > self.TAKEOFF_CROSSTRACK_GUARD_M
        )
        throttle_guard_reasons: list[str] = []
        rudder = self.TAKEOFF_RUDDER_RIGHT_BIAS
        aileron = 0.0
        brake_left = 0.0
        brake_right = 0.0
        rudder_max = self.TAKEOFF_MAX_RUDDER_GROUND

        def cap_throttle(max_throttle: float, reason: str) -> None:
            nonlocal throttle
            if throttle > max_throttle:
                throttle = max_throttle
                throttle_guard_reasons.append(reason)

        if not airborne_detected:
            if takeoff_elapsed is None:
                throttle = self.TAKEOFF_POWER
            else:
                throttle = self._takeoff_throttle_for_elapsed(takeoff_elapsed)
            trim = 0.0
            rotation_cross_track_limit = (
                self.TAKEOFF_ROTATION_MAX_CROSSTRACK_HIGH_SPEED_M
                if (
                    airspeed >= self.TAKEOFF_HIGH_SPEED_CROSSTRACK_AIRSPEED_KT
                    and runway_guard_error <= self.TAKEOFF_RUNWAY_GUARD_HEADING_DEG
                    and heading_rate_abs
                    <= self.TAKEOFF_ROTATION_MAX_HEADING_RATE_DEG_S
                    and cross_track_rate_safe_for_rotation
                )
                else self.TAKEOFF_ROTATION_MAX_CROSSTRACK_M
            )
            can_start_rotation = (
                airspeed >= self.ROTATION_AIRSPEED_KT
                and heading_rate_abs <= self.TAKEOFF_ROTATION_MAX_HEADING_RATE_DEG_S
                and cross_track_error <= rotation_cross_track_limit
                and cross_track_rate_safe_for_rotation
                and control_heading_error
                <= self.TAKEOFF_ROTATION_MAX_CONTROL_HEADING_ERROR_DEG
                and (
                    heading_error is None
                    or heading_error <= self.TAKEOFF_ROTATION_MAX_HEADING_ERROR_DEG
                )
            )
            rotation_active = self.rotation_started_at is not None
            if not rotation_active and can_start_rotation:
                self.rotation_started_at = time.time()
                rotation_active = True
                self._debug(
                    "Rotacion iniciada y latcheada hasta liftoff "
                    f"(ias={airspeed:.1f} kt, xtrack={cross_track_error:.1f} m, "
                    f"xtrack_rate={cross_track_rate:.2f} m/s, "
                    f"hdg={runway_guard_error:.1f} deg, "
                    f"ctrl_hdg={control_heading_error:.1f} deg, "
                    f"hdg_rate={heading_rate_abs:.1f} deg/s)"
                )

            if rotation_active:
                sample["phase"] = "rotation"
                sample["phase_reason"] = (
                    "rotation latched until liftoff/WOW-clear detection"
                )
                throttle = self.TAKEOFF_POWER

            if (
                airspeed < self.TAKEOFF_LOW_SPEED_POWER_CAP_AIRSPEED_KT
                and not rotation_active
            ):
                cap_throttle(
                    self.TAKEOFF_LOW_SPEED_POWER_CAP,
                    "low_speed_power_cap",
                )
            if (
                runway_guard_error > self.TAKEOFF_HEADING_THROTTLE_CAP_DEG
                and not rotation_active
            ):
                cap_throttle(
                    self.TAKEOFF_HEADING_THROTTLE_CAP,
                    "actual_heading_guard",
                )
            if (
                runway_guard_error > self.TAKEOFF_RUNWAY_GUARD_HEADING_DEG
                and not rotation_active
            ):
                cap_throttle(
                    self.TAKEOFF_RUNWAY_GUARD_THROTTLE,
                    "actual_runway_heading_guard",
                )
            if (
                runway_guard_error > self.TAKEOFF_RUNWAY_GUARD_HARD_HEADING_DEG
                and cross_track_error
                >= self.TAKEOFF_HEADING_RATE_GUARD_CROSSTRACK_M
                and not rotation_active
            ):
                cap_throttle(
                    self.TAKEOFF_RUNWAY_GUARD_HARD_THROTTLE,
                    "actual_runway_heading_hard_guard",
                )
            if (
                cross_track_error > self.TAKEOFF_CROSSTRACK_GUARD_M
                and not rotation_active
            ):
                cross_track_guard_throttle = self.TAKEOFF_CROSSTRACK_GUARD_THROTTLE
                if (
                    airspeed >= self.TAKEOFF_HIGH_SPEED_CROSSTRACK_AIRSPEED_KT
                    and runway_guard_error <= self.TAKEOFF_RUNWAY_GUARD_HEADING_DEG
                    and heading_rate_abs
                    <= self.TAKEOFF_ROTATION_MAX_HEADING_RATE_DEG_S
                    and cross_track_rate_safe_for_rotation
                ):
                    cross_track_guard_throttle = (
                        self.TAKEOFF_CROSSTRACK_HIGH_SPEED_GUARD_THROTTLE
                    )
                cap_throttle(
                    cross_track_guard_throttle,
                    (
                        "cross_track_high_speed_guard"
                        if cross_track_guard_throttle
                        > self.TAKEOFF_CROSSTRACK_GUARD_THROTTLE
                        else "cross_track_guard"
                    ),
                )
            if (
                cross_track_error > self.TAKEOFF_CROSSTRACK_HARD_GUARD_M
                and not rotation_active
            ):
                cross_track_hard_guard_throttle = (
                    self.TAKEOFF_CROSSTRACK_HARD_GUARD_THROTTLE
                )
                if (
                    airspeed >= self.TAKEOFF_HIGH_SPEED_CROSSTRACK_AIRSPEED_KT
                    and runway_guard_error <= self.TAKEOFF_RUNWAY_GUARD_HEADING_DEG
                    and heading_rate_abs
                    <= self.TAKEOFF_ROTATION_MAX_HEADING_RATE_DEG_S
                    and cross_track_rate_safe_for_rotation
                ):
                    cross_track_hard_guard_throttle = (
                        self.TAKEOFF_CROSSTRACK_HIGH_SPEED_HARD_GUARD_THROTTLE
                    )
                cap_throttle(
                    cross_track_hard_guard_throttle,
                    (
                        "cross_track_high_speed_hard_guard"
                        if cross_track_hard_guard_throttle
                        > self.TAKEOFF_CROSSTRACK_HARD_GUARD_THROTTLE
                        else "cross_track_hard_guard"
                    ),
                )
            if (
                heading_rate_abs > self.TAKEOFF_HEADING_RATE_THROTTLE_CAP_DEG_S
                and rate_guard_active
                and not rotation_active
            ):
                cap_throttle(
                    self.TAKEOFF_HEADING_RATE_THROTTLE_CAP,
                    "heading_rate_guard",
                )
            if (
                heading_rate_abs > self.TAKEOFF_HEADING_RATE_HARD_CAP_DEG_S
                and rate_guard_active
                and not rotation_active
            ):
                cap_throttle(
                    self.TAKEOFF_HEADING_RATE_HARD_CAP,
                    "heading_rate_hard_guard",
                )
            if not rotation_active:
                brake_left, brake_right = self._takeoff_brake_commands(sample)
            elevator = (
                self.TAKEOFF_ROTATION_ELEVATOR
                if rotation_active
                else self.TAKEOFF_NOSE_DOWN_ELEVATOR
            )
        elif altitude_agl < self.CRUISE_MIN_AGL_FT:
            sample["phase"] = "initial_climb"
            sample.setdefault("phase_reason", "airborne detected; climbout control")
            trim = 0.0
            elevator, throttle = self._airborne_pitch_and_power_commands(sample)
            aileron, rudder = self._airborne_lateral_commands(sample)
        else:
            trim = 0.0
            elevator, throttle = self._airborne_pitch_and_power_commands(sample)
            aileron, rudder = self._airborne_lateral_commands(sample)

        if not airborne_detected:
            rudder = self._takeoff_rudder_command(
                sample,
                max_rudder_override=rudder_max,
                max_step=self.TAKEOFF_RUDDER_MAX_STEP,
                power_norm=throttle,
            )

        self._set_if_changed_and_log("/controls/flight/elevator", elevator)
        self._set_if_changed_and_log("/controls/flight/elevator-trim", trim)
        self._set_if_changed_and_log("/controls/flight/rudder", rudder)
        self._set_if_changed_and_log("/controls/flight/aileron", aileron)
        self._set_if_changed_and_log("/controls/flight/flaps", 0.0)
        self._set_if_changed_and_log("/controls/gear/brake-left", brake_left)
        self._set_if_changed_and_log("/controls/gear/brake-right", brake_right)
        self._set_if_changed_and_log(
            "/controls/engines/current-engine/throttle",
            throttle,
        )
        throttle_reason = (
            "|".join(throttle_guard_reasons)
            or sample.get("throttle_guard_reason")
        )
        sample.update(
            on_ground_detected=on_ground_detected,
            airborne_detected=airborne_detected,
            rotation_latched=(
                self.rotation_started_at is not None and not airborne_detected
            ),
            heading_rate_diverging=heading_rate_diverging,
            rate_guard_active=rate_guard_active,
            throttle_norm=throttle,
            throttle_guard_reason=throttle_reason,
            aileron_norm=aileron,
            rudder_norm=rudder,
            elevator_norm=elevator,
            elevator_trim_norm=trim,
            flaps_norm=0.0,
            brake_left=brake_left,
            brake_right=brake_right,
        )

    def _wait_for_cruise_from_ground(self, ground_altitude_ft: float) -> bool:
        if not self._wait_for_ground_roll(ground_altitude_ft):
            return False

        self._debug(
            "Taxi confirmed. Looking for takeoff, climb, and real cruise "
            "before arming the failure."
        )
        start_time = time.time()
        self.takeoff_roll_started_at = start_time
        self._set_and_log("/controls/gear/brake-left", 0.0)
        self._set_and_log("/controls/gear/brake-right", 0.0)
        self._debug(
            "Takeoff roll started while preserving taxi rudder state"
        )
        airborne_announced = False
        cruise_candidate_since = None

        while time.time() - start_time < self.CRUISE_TIMEOUT_SECONDS:
            elapsed = time.time() - start_time
            phase = "climb_or_cruise_gate" if airborne_announced else "takeoff_roll"
            sample_fields = (
                self.TAKEOFF_SAMPLE_FIELDS
                if airborne_announced
                else self.TAKEOFF_ROLL_SAMPLE_FIELDS
            )
            required_fields = {
                "latitude_deg",
                "longitude_deg",
                "altitude_agl_ft",
                "airspeed_kts",
                "groundspeed_kts",
                "pitch_deg",
                "heading_deg",
                "roll_deg",
                "engine_running",
            }
            sample = self._sample_flight_state_with_retries(
                phase,
                ground_altitude_ft,
                fields=sample_fields,
                required_fields=required_fields,
            )
            if self._skip_invalid_telemetry_tick(
                sample,
                f"Cruise gate t={elapsed:.1f}s",
            ):
                time.sleep(0.5)
                continue

            if not self._engine_alive_in_sample(sample):
                self._append_telemetry_row(sample)
                self._debug(f"Cruise gate t={elapsed:.1f}s -> {self._summarize_sample(sample)}")
                self._debug(
                    "Engine stopped before reaching cruise. "
                    "Aborting; failure will not be injected."
                )
                return False

            takeoff_elapsed = (
                time.time() - self.takeoff_roll_started_at
                if self.takeoff_roll_started_at is not None
                else None
            )
            self._command_takeoff_or_cruise_controls(
                sample,
                takeoff_elapsed=takeoff_elapsed,
            )
            self._append_telemetry_row(sample)
            self._debug(f"Cruise gate t={elapsed:.1f}s -> {self._summarize_sample(sample)}")

            if not airborne_announced and self._is_airborne_sample(sample):
                airborne_announced = True
                self._debug("Takeoff confirmed: WOW released or AGL is sufficient")

            heading_error = self._takeoff_heading_error_abs(sample)
            signed_cross_track = sample.get("runway_cross_track_m") or 0.0
            cross_track_error = abs(signed_cross_track)
            cross_track_rate = sample.get("runway_cross_track_rate_mps") or 0.0
            moving_away_from_centerline = signed_cross_track * cross_track_rate > 0.0
            control_heading_error = abs(sample.get("control_heading_error_deg") or 0.0)
            actual_heading_error = heading_error or 0.0
            actual_heading_abort_required = (
                actual_heading_error >= self.TAKEOFF_ABORT_HARD_HEADING_ERROR_DEG
                or (
                    actual_heading_error >= self.TAKEOFF_ABORT_HEADING_ERROR_DEG
                    and cross_track_error
                    >= self.TAKEOFF_ABORT_HEADING_CROSSTRACK_M
                )
            )
            control_heading_abort_required = (
                control_heading_error >= self.TAKEOFF_ABORT_CONTROL_HEADING_ERROR_DEG
                and cross_track_error >= self.TAKEOFF_ABORT_CONTROL_CROSSTRACK_M
                and (
                    moving_away_from_centerline
                    or abs(cross_track_rate)
                    >= self.TAKEOFF_ABORT_CONTROL_CROSSTRACK_RATE_MPS
                )
            )
            if (
                not airborne_announced
                and heading_error is not None
                and (
                    actual_heading_abort_required
                    or control_heading_abort_required
                )
            ):
                abort_reason = (
                    "actual_heading"
                    if actual_heading_abort_required
                    else "control_heading_plus_crosstrack"
                )
                self._debug(
                    "Excessive heading deviation before takeoff "
                    f"({abort_reason}; "
                    f"hdg={heading_error:.1f} deg, "
                    f"control={control_heading_error:.1f} deg, "
                    f"xtrack={cross_track_error:.1f} m, "
                    f"xtrack_rate={cross_track_rate:.1f} m/s). "
                    "Aborting to avoid runway excursion."
                )
                self._abort_takeoff_roll()
                return False

            if (
                not airborne_announced
                and cross_track_error >= self.TAKEOFF_CROSSTRACK_ABORT_M
            ):
                self._debug(
                    "Excessive cross-track before takeoff "
                    f"({cross_track_error:.1f} m). Aborting to avoid leaving the runway."
                )
                self._abort_takeoff_roll()
                return False

            if self._is_cruise_sample(sample):
                if cruise_candidate_since is None:
                    cruise_candidate_since = time.time()
                    self._debug(
                        "Cruise condition detected; waiting for stability "
                        f"{self.CRUISE_STABLE_SECONDS}s"
                    )
                elif time.time() - cruise_candidate_since >= self.CRUISE_STABLE_SECONDS:
                    self._debug("Real cruise confirmed. Engine failure is now armed.")
                    return True
            else:
                cruise_candidate_since = None

            time.sleep(0.2 if not airborne_announced else 0.5)

        self._debug(
            "Could not reach a real cruise condition within the timeout. "
            "Failure will not be injected."
        )
        return False

    def run(self):
        fg_args = [
            f"--telnet={self.proto.port}",
            "--prop:/sim/rendering/visible=off",
            "--on-ground",
            "--prop:/sim/presets/on-ground=1",
            "--prop:/sim/presets/airport-requested=true",
            "--prop:/sim/presets/runway-requested=true",
            "--prop:/sim/presets/parking-requested=false",
            "--prop:/sim/freeze/master=false",
            "--prop:/sim/freeze/clock=false",
        ]
        if self.disable_terrasync:
            fg_args.append("--disable-terrasync")
        if self.runway:
            fg_args.append(f"--runway={self.runway}")

        self._debug(f"Starting FlightGear with args: {' '.join(fg_args)}")
        if not self.sim.start(custom_args=fg_args, wait_for_start=True, timeout=60):
            self._debug(
                "FlightGear could not start. "
                f"Detail: {self.sim.last_startup_error}. "
                f"Process log: {self.fg_process_log_path}"
            )
            return

        try:
            if not self.proto.connect(timeout=10):
                self._debug(
                    "Could not connect through telnet even though the process started. "
                    "Verify that --telnet is active and the port is not occupied."
                )
                return

            self._debug(
                f"Waiting {self.STARTUP_WAIT_SECONDS}s for properties to load..."
            )
            time.sleep(self.STARTUP_WAIT_SECONDS)

            self._clear_simulation_freezes()
            if not self._wait_for_ground_contact_ready():
                return

            if not self.start_engine():
                self._debug("Engine startup failed. Aborting test.")
                return

            ground_altitude_ft = self._get_float_property("/position/altitude-ft")
            if ground_altitude_ft is None:
                self._debug(
                    "Could not read initial altitude to compute AGL. Aborting scenario."
                )
                return

            self.takeoff_heading_deg = self._get_float_property("/orientation/heading-deg")
            if self.takeoff_heading_deg is not None:
                self._debug(
                    "Takeoff target heading captured before releasing brakes: "
                    f"{self.takeoff_heading_deg:.1f} deg"
                )
            self._set_runway_reference(
                self._get_float_property("/position/latitude-deg"),
                self._get_float_property("/position/longitude-deg"),
                self.takeoff_heading_deg,
                "before releasing brakes",
            )
            self.takeoff_roll_started_at = None
            if not self._prepare_for_ground_roll():
                self._debug("Taxi/takeoff preparation failed. Aborting.")
                return

            if not self._wait_for_cruise_from_ground(ground_altitude_ft):
                self._debug(
                    "The aircraft did not reach real cruise. "
                    "Scenario aborted without injecting failure."
                )
                return

            start = time.time()
            failure_injected = False
            self.engine_failure_started_at = None
            pre_failure_stable_since = None
            pre_failure_was_stable = None
            self._debug(
                "Cruise confirmed. Observing continuous stability before "
                f"injecting failure for {self.FAILURE_ARM_DELAY_SECONDS}s "
                f"(pre-failure timeout {self.FAILURE_OBSERVATION_SECONDS}s, "
                f"post-failure observation {self.POST_FAILURE_OBSERVATION_SECONDS}s)."
            )

            post_failure_observation_complete = False
            while True:
                now = time.time()
                elapsed = now - start
                if failure_injected:
                    failure_elapsed = (
                        now - self.engine_failure_started_at
                        if self.engine_failure_started_at is not None
                        else 0.0
                    )
                    if failure_elapsed >= self.POST_FAILURE_OBSERVATION_SECONDS:
                        post_failure_observation_complete = True
                        self._debug(
                            "Post-failure observation completed after "
                            f"{failure_elapsed:.1f}s of controlled glide."
                        )
                        break
                elif elapsed >= self.FAILURE_OBSERVATION_SECONDS:
                    break

                phase = "engine_failure" if failure_injected else "cruise_pre_failure"
                sample = self._sample_flight_state_with_retries(
                    phase,
                    ground_altitude_ft,
                    required_fields={
                        "latitude_deg",
                        "longitude_deg",
                        "altitude_agl_ft",
                        "airspeed_kts",
                        "vertical_speed_fpm",
                        "pitch_deg",
                        "heading_deg",
                        "roll_deg",
                        "engine_running",
                    },
                )
                if self._skip_invalid_telemetry_tick(
                    sample,
                    f"Failure gate t={elapsed:.1f}s",
                ):
                    time.sleep(1.0)
                    continue

                if failure_injected:
                    self._command_engine_failure_glide_controls(sample)
                else:
                    self._command_takeoff_or_cruise_controls(sample)
                self._append_telemetry_row(sample)
                self._debug(f"Failure gate t={elapsed:.1f}s -> {self._summarize_sample(sample)}")

                if not failure_injected:
                    if not self._engine_alive_in_sample(sample):
                        self._debug(
                            "Engine stopped before injecting the failure. "
                            "Magnetos will not be turned off because the scenario is already invalid."
                        )
                        break

                    cruise_stable_now = self._is_cruise_sample(sample)
                    if cruise_stable_now:
                        if pre_failure_stable_since is None:
                            pre_failure_stable_since = time.time()
                            if pre_failure_was_stable is not True:
                                self._debug(
                                    "Level cruise in pre-failure; "
                                    "starting continuous stability timer."
                                )
                        pre_failure_was_stable = True
                    else:
                        if (
                            pre_failure_stable_since is not None
                            or pre_failure_was_stable is not False
                        ):
                            self._debug(
                                "Cruise is not level enough for failure injection yet; "
                                "restarting stability timer."
                            )
                        pre_failure_stable_since = None
                        pre_failure_was_stable = False

                if not failure_injected and pre_failure_stable_since is not None:
                    stable_elapsed = time.time() - pre_failure_stable_since
                    if stable_elapsed >= self.FAILURE_ARM_DELAY_SECONDS:
                        self._debug(
                            "Injecting engine failure: magnetos OFF "
                            f"after {stable_elapsed:.1f}s of stable cruise."
                        )
                        self._set_and_log("/controls/switches/magnetos", 0)
                        failure_injected = True
                        self.engine_failure_started_at = time.time()

                time.sleep(1.0)

            if not failure_injected:
                self._debug(
                    "Failure was not injected: there was no continuous level-cruise "
                    "window before the observation ended."
                )
            elif not post_failure_observation_complete:
                self._debug(
                    "The failure was injected, but post-failure observation ended "
                    "before the planned window completed."
                )
            self._debug(f"Telemetry saved to {self.csv_path}")

            # Restore ignition so the simulator is left in a consistent state.
            self._set_and_log("/controls/switches/magnetos", 3)

        finally:
            self.proto.disconnect()
            self.sim.stop()


if __name__ == "__main__":
    import sys

    project_root = Path(__file__).resolve().parents[3]
    conf_path = project_root / "config" / "framework_config.yaml"

    if not conf_path.is_file():
        print(f"Could not find {conf_path}")
        sys.exit(1)

    with open(conf_path, encoding="utf-8") as yml_file:
        config = yaml.safe_load(yml_file)

    test = CruiseEngineFailureTest(config)
    test.run()
