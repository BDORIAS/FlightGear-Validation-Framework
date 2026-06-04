"""Diagnostic FlightGear runner used by the console for connection checks."""

import logging
import os
from pathlib import Path
import time

from ..communication.protocol import FlightGearProtocol
from ..configuration import flightgear_connection_settings, flightgear_simulator_settings
from ..core.simulator import FlightGearSimulator

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class TestRunner:
    """
    Orchestrates automated test execution against FlightGear.
    """

    __test__ = False

    STARTUP_WAIT_SECONDS = 70
    ALTITUDE_PROPERTY = "/position/altitude-ft"
    THROTTLE_PROPERTY = "/controls/engines/current-engine/throttle"
    THROTTLE_TARGET_NORM = 0.30
    THROTTLE_TOLERANCE_NORM = 0.02

    def __init__(self, config: dict):
        sim_conf = flightgear_simulator_settings(config)
        conn_conf = flightgear_connection_settings(config)
        project_root = Path(__file__).resolve().parents[3]
        results_dir = Path(os.environ.get("FG_RESULTS_DIR", project_root / "data" / "results"))
        results_dir.mkdir(parents=True, exist_ok=True)
        self.debug_txt_path = results_dir / "simple_connect_debug.txt"
        self.fg_process_log_path = results_dir / "flightgear_process_simple_connect.txt"
        self.runway = sim_conf.get("default_runway", "29")
        self.disable_terrasync = bool(sim_conf.get("disable_terrasync", False))

        self.simulator = FlightGearSimulator(
            executable=sim_conf.get("executable", "fgfs"),
            data_dir=sim_conf.get("data_dir", None),
            aircraft=sim_conf.get("default_aircraft", "c172p"),
            airport=sim_conf.get("default_airport", "BIKF"),
            process_log_path=str(self.fg_process_log_path),
        )
        self.protocol = FlightGearProtocol(
            host=conn_conf.get("host", "localhost"),
            port=conn_conf.get("port", 5401),
            response_timeout=conn_conf.get("response_timeout", 1.2),
            command_log_path=str(self.debug_txt_path),
            use_data_mode=True,
        )

    def _reset_logs(self) -> None:
        self.debug_txt_path.write_text("=== Simple connection debug log ===\n", encoding="utf-8")
        self.fg_process_log_path.write_text(
            "=== FlightGear simple connection process log ===\n",
            encoding="utf-8",
        )

    @staticmethod
    def _parse_float(raw_value: str | None) -> float | None:
        if raw_value is None:
            return None
        try:
            return float(str(raw_value).strip())
        except (TypeError, ValueError):
            return None

    def _get_float_property(self, property_path: str) -> float | None:
        raw_value = self.protocol.get_property(property_path)
        value = self._parse_float(raw_value)
        if value is None:
            logger.error(
                "Property %s did not return a numeric value. Raw response: %r",
                property_path,
                raw_value,
            )
        return value

    def _build_flightgear_args(self) -> list[str]:
        args = [
            f"--telnet={self.protocol.port}",
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
            args.append("--disable-terrasync")
        if self.runway:
            args.append(f"--runway={self.runway}")
        return args

    def _verify_throttle(self, expected_value: float) -> bool:
        actual_value = self._get_float_property(self.THROTTLE_PROPERTY)
        if actual_value is None:
            return False
        if abs(actual_value - expected_value) > self.THROTTLE_TOLERANCE_NORM:
            logger.error(
                "Throttle verification failed: expected %.3f, got %.3f",
                expected_value,
                actual_value,
            )
            return False
        logger.info("Throttle readback verified: %.3f", actual_value)
        return True

    def run_simple_connect_test(self) -> bool:
        self._reset_logs()
        fg_args = self._build_flightgear_args()
        logger.info("Starting FlightGear with: %s", " ".join(fg_args))

        try:
            started = self.simulator.start(custom_args=fg_args, wait_for_start=True, timeout=60)
            if not started:
                logger.error(
                    "Could not start FlightGear. Detail: %s. Process log: %s",
                    self.simulator.last_startup_error,
                    self.fg_process_log_path,
                )
                return False

            if not self.protocol.connect(timeout=10):
                logger.error("Could not connect to FlightGear through telnet")
                return False

            logger.info(
                "Waiting %s seconds for FlightGear properties to load...",
                self.STARTUP_WAIT_SECONDS,
            )
            time.sleep(self.STARTUP_WAIT_SECONDS)

            altitude_ft = self._get_float_property(self.ALTITUDE_PROPERTY)
            if altitude_ft is None:
                return False
            logger.info("Initial altitude: %.2f ft", altitude_ft)

            if not self.protocol.set_property(
                self.THROTTLE_PROPERTY,
                self.THROTTLE_TARGET_NORM,
            ):
                logger.error("Could not set throttle")
                return False
            logger.info("Throttle command sent: %.2f", self.THROTTLE_TARGET_NORM)

            return self._verify_throttle(self.THROTTLE_TARGET_NORM)

        finally:
            self.protocol.disconnect()
            self.simulator.stop()


if __name__ == "__main__":
    import sys

    import yaml

    project_root = Path(__file__).resolve().parents[3]
    conf_path = project_root / "config" / "framework_config.yaml"
    if not conf_path.is_file():
        print(f"Could not find {conf_path}")
        sys.exit(1)

    with open(conf_path, encoding="utf-8") as config_file:
        full_conf = yaml.safe_load(config_file)
    runner = TestRunner(full_conf)
    result = runner.run_simple_connect_test()
    print("Connection test finished:", "Success" if result else "Failure")
