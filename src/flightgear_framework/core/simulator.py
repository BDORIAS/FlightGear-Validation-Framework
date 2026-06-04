"""FlightGear process launcher and lifecycle controller."""

import logging
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, TextIO

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class FlightGearSimulator:
    """
    Class for controlling a FlightGear instance from Python.

    This class handles the full simulator lifecycle:
    - Initialization with custom parameters
    - Process monitoring
    - Real telnet availability wait
    - Cleanup and termination
    """

    def __init__(
        self,
        executable: str = "fgfs",
        data_dir: Optional[str] = None,
        aircraft: str = "c172p",
        airport: str = "BIKF",
        startup_host: str = "127.0.0.1",
        process_log_path: Optional[str] = None,
    ):
        """
        Initialize the FlightGear controller.

        Args:
            executable: Path to the FlightGear executable.
            data_dir: FlightGear data directory.
            aircraft: Default aircraft to load.
            airport: Startup airport.
            startup_host: Host used to probe telnet port availability.
            process_log_path: Optional TXT path for FG stdout/stderr.
        """
        self.executable = executable
        self.data_dir = data_dir
        self.aircraft = aircraft
        self.airport = airport
        self.startup_host = startup_host

        self.process: Optional[subprocess.Popen] = None
        self._process_log_handle: Optional[TextIO] = None

        self.process_log_path = Path(process_log_path) if process_log_path else None
        self.expected_telnet_port: Optional[int] = None
        self.last_startup_error: Optional[str] = None

        self.is_running = False

        # Keep default launches lightweight and deterministic for automated runs.
        self.default_args = [
            "--disable-sound",
            "--disable-random-objects",
            "--prop:/sim/rendering/shaders/quality-level=0",
            "--geometry=800x600",
        ]

    def _append_process_log(self, message: str) -> None:
        """Write internal messages to the process log if it exists."""
        if not self._process_log_handle:
            return

        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        self._process_log_handle.write(f"[{timestamp}] {message}\n")
        self._process_log_handle.flush()

    @staticmethod
    def _extract_telnet_port(args: Optional[List[str]]) -> Optional[int]:
        """Extract the port from --telnet=XXXX or --telnet XXXX."""
        if not args:
            return None

        for index, arg in enumerate(args):
            if arg.startswith("--telnet="):
                try:
                    return int(arg.split("=", 1)[1])
                except ValueError:
                    return None

            if arg == "--telnet" and index + 1 < len(args):
                try:
                    return int(args[index + 1])
                except ValueError:
                    return None

        return None

    def _prepare_process_log(self) -> None:
        """Open the process log file if configured."""
        if not self.process_log_path:
            return

        self.process_log_path.parent.mkdir(parents=True, exist_ok=True)
        self._process_log_handle = open(self.process_log_path, "a", encoding="utf-8")
        self._append_process_log("--- New FlightGearSimulator session ---")

    def _close_process_log(self) -> None:
        """Close the process log file descriptor."""
        if self._process_log_handle:
            try:
                self._process_log_handle.flush()
                self._process_log_handle.close()
            finally:
                self._process_log_handle = None

    def _is_telnet_ready(self, port: int) -> bool:
        """Check whether the telnet port is listening."""
        try:
            with socket.create_connection((self.startup_host, port), timeout=1.0):
                return True
        except OSError as exc:
            self.last_startup_error = str(exc)
            return False

    def start(
        self,
        custom_args: Optional[List[str]] = None,
        wait_for_start: bool = True,
        timeout: int = 60,
    ) -> bool:
        """
        Start FlightGear with the specified parameters.

        Args:
            custom_args: Additional FlightGear arguments.
            wait_for_start: Wait until FlightGear is ready.
            timeout: Maximum wait time in seconds.

        Returns:
            True if startup succeeds, False otherwise.
        """
        if self.is_running:
            logger.warning("FlightGear is already running")
            return True

        self.last_startup_error = None
        self.expected_telnet_port = self._extract_telnet_port(custom_args)

        # Build command arguments.
        cmd_args = [self.executable]
        cmd_args.extend(self.default_args)
        cmd_args.extend([
            f"--aircraft={self.aircraft}",
            f"--airport={self.airport}",
        ])

        if self.data_dir:
            cmd_args.append(f"--fg-root={self.data_dir}")

        if custom_args:
            cmd_args.extend(custom_args)

        try:
            self._prepare_process_log()
            logger.info(f"Starting FlightGear with command: {' '.join(cmd_args)}")
            self._append_process_log(f"Command: {' '.join(cmd_args)}")

            stdout_target = self._process_log_handle if self._process_log_handle else subprocess.PIPE
            stderr_target = subprocess.STDOUT if self._process_log_handle else subprocess.PIPE

            self.process = subprocess.Popen(
                cmd_args,
                stdout=stdout_target,
                stderr=stderr_target,
                text=True,
            )

            if wait_for_start:
                if self._wait_for_startup(timeout, self.expected_telnet_port):
                    self.is_running = True
                    logger.info("FlightGear started successfully")
                    return True

                logger.error("FlightGear could not start within the expected time")
                self.stop()
                return False

            self.is_running = True
            return True

        except Exception as exc:
            logger.error(f"Error starting FlightGear: {exc}")
            self._append_process_log(f"START ERROR: {exc}")
            self._close_process_log()
            return False

    def _wait_for_startup(self, timeout: int, expected_telnet_port: Optional[int]) -> bool:
        """
        Wait until FlightGear is fully started.

        If a telnet port is detected in the arguments, validate that it is
        actually listening before marking the simulator as ready.
        """
        start_time = time.time()
        grace_seconds_without_telnet_probe = 5

        while time.time() - start_time < timeout:
            if self.process and self.process.poll() is not None:
                exit_code = self.process.returncode
                self.last_startup_error = f"FlightGear exited during startup (exit code {exit_code})"
                self._append_process_log(self.last_startup_error)
                logger.error(self.last_startup_error)
                return False

            # Real check: telnet port available.
            if expected_telnet_port is not None:
                if self._is_telnet_ready(expected_telnet_port):
                    self._append_process_log(
                        f"Telnet port ready at {self.startup_host}:{expected_telnet_port}"
                    )
                    return True

            else:
                # Compatibility path when no --telnet argument is present.
                if time.time() - start_time > grace_seconds_without_telnet_probe:
                    return True

            time.sleep(1)

        if expected_telnet_port is not None:
            self.last_startup_error = (
                "Timeout waiting for telnet port "
                f"{self.startup_host}:{expected_telnet_port}. "
                "Check whether FlightGear started with --telnet and the port is not occupied."
            )
            self._append_process_log(self.last_startup_error)
            logger.error(self.last_startup_error)
        return False

    def stop(self) -> bool:
        """
        Stop FlightGear in a controlled way.

        Returns:
            True if it stopped successfully.
        """
        if not self.process:
            logger.info("FlightGear is not running")
            self.is_running = False
            self._close_process_log()
            return True

        try:
            logger.info("Stopping FlightGear...")
            self._append_process_log("Stopping FlightGear process")

            # Try graceful termination.
            self.process.terminate()

            # Wait for clean termination.
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning("FlightGear did not respond to terminate(); forcing kill()")
                self._append_process_log("Process did not respond to terminate(); kill()")
                self.process.kill()
                self.process.wait()

            self.is_running = False
            self.process = None
            self._append_process_log("FlightGear stopped successfully")
            logger.info("FlightGear stopped successfully")
            return True

        except Exception as exc:
            logger.error(f"Error stopping FlightGear: {exc}")
            self._append_process_log(f"Error stopping FlightGear: {exc}")
            return False

        finally:
            self._close_process_log()

    def is_alive(self) -> bool:
        """
        Check whether FlightGear is still running.

        Returns:
            True if active, False otherwise.
        """
        if not self.process:
            return False

        poll_result = self.process.poll()
        if poll_result is not None:
            self.is_running = False
            return False

        return self.is_running

    def get_status(self) -> Dict[str, Any]:
        """
        Get simulator status information.

        Returns:
            Dictionary with status information.
        """
        return {
            "is_running": self.is_running,
            "is_alive": self.is_alive(),
            "aircraft": self.aircraft,
            "airport": self.airport,
            "pid": self.process.pid if self.process else None,
            "executable": self.executable,
            "expected_telnet_port": self.expected_telnet_port,
            "last_startup_error": self.last_startup_error,
            "process_log_path": str(self.process_log_path) if self.process_log_path else None,
        }

    def __enter__(self):
        """Context manager support."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Automatic cleanup when leaving the context manager."""
        self.stop()
