"""
FlightGear communication protocols.
"""

import logging
import socket
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class FlightGearProtocol:
    """
    Class for handling communication with FlightGear via telnet/TCP.

    FlightGear exposes a telnet port that allows reading and writing simulator
    properties in real time.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5401,
        response_timeout: float = 5.0,
        command_log_path: Optional[str] = None,
        use_data_mode: bool = True,
    ):
        """
        Initialize the communication protocol.

        Args:
            host: FlightGear server address.
            port: Telnet connection port.
            response_timeout: Timeout for receiving each command response.
            command_log_path: Optional TXT path for command/response logs.
            use_data_mode: If True, switches telnet to "data" mode on connect.
        """
        self.host = host
        self.port = port
        self.response_timeout = response_timeout
        self.use_data_mode = use_data_mode
        self.socket: Optional[socket.socket] = None
        self.connected = False
        self.command_log_path = Path(command_log_path) if command_log_path else None

        if self.command_log_path:
            self.command_log_path.parent.mkdir(parents=True, exist_ok=True)
            self._append_command_log(
                f"--- New FlightGearProtocol session -> {self.host}:{self.port} ---"
            )

    def _append_command_log(self, message: str) -> None:
        """Write a message to the TXT command log file."""
        if not self.command_log_path:
            return
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        try:
            with open(self.command_log_path, "a", encoding="utf-8") as log_file:
                log_file.write(f"[{timestamp}] {message}\n")
        except Exception as exc:
            logger.debug(f"Could not write command log: {exc}")

    @staticmethod
    def _normalize_property_path(property_path: str) -> str:
        """Ensure that the property path is absolute."""
        path = property_path.strip()
        if not path.startswith("/"):
            path = "/" + path
        return path

    @staticmethod
    def _clean_response(raw_response: str) -> str:
        """
        Clean common telnet noise:
        - empty lines
        - prompts like '/>' or '/path>'
        """
        lines = [
            line.strip()
            for line in raw_response.replace("\r", "\n").split("\n")
            if line.strip()
        ]
        filtered = [line for line in lines if not line.endswith(">")]
        if not filtered:
            return raw_response.strip()
        return "\n".join(filtered).strip()

    def _drain_pending_data(self) -> None:
        """Discard delayed responses that could desynchronize the next command."""
        if not self.socket:
            return

        previous_timeout = self.socket.gettimeout()
        drained = b""
        try:
            self.socket.settimeout(0.0)
            while True:
                try:
                    chunk = self.socket.recv(4096)
                except (BlockingIOError, socket.timeout):
                    break
                if not chunk:
                    break
                drained += chunk
        finally:
            self.socket.settimeout(previous_timeout)

        if drained:
            self._append_command_log(
                f"<<< <drained stale> {drained.decode('utf-8', errors='ignore').strip()}"
            )

    def connect(self, timeout: int = 10) -> bool:
        """
        Establish a connection with FlightGear.

        Args:
            timeout: Maximum wait time for the initial connection.

        Returns:
            True if the connection succeeds.
        """
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(timeout)
            self.socket.connect((self.host, self.port))
            self.connected = True
            logger.info(f"Connected to FlightGear at {self.host}:{self.port}")
            self._append_command_log("TCP connection established.")

            # Read and discard the initial banner/prompt without blocking.
            try:
                self.socket.settimeout(1.0)
                initial_data = b""
                while True:
                    chunk = self.socket.recv(1024)
                    if not chunk:
                        break
                    initial_data += chunk
                    if b"\n" in chunk:
                        break
                if initial_data:
                    self._append_command_log(
                        f"Initial banner: {initial_data.decode(errors='ignore').strip()}"
                    )
            except socket.timeout:
                pass
            finally:
                self.socket.settimeout(self.response_timeout)

            if self.use_data_mode:
                self.send_command("data", expect_response=False)
                self._append_command_log("'data' command applied.")

            return True

        except Exception as exc:
            logger.error(
                "Error connecting to FlightGear at %s:%s: %s. "
                "If this is WinError 10061, the telnet server is not listening.",
                self.host,
                self.port,
                exc,
            )
            self._append_command_log(f"Connection error: {exc}")
            self.connected = False
            return False

    def disconnect(self) -> None:
        """Close the FlightGear connection."""
        if self.socket:
            try:
                self.socket.close()
                logger.info("Disconnected from FlightGear")
                self._append_command_log("Connection closed.")
            except Exception as exc:
                logger.error(f"Error while disconnecting: {exc}")
                self._append_command_log(f"Disconnect error: {exc}")
            finally:
                self.socket = None
                self.connected = False

    def send_command(self, command: str, expect_response: bool = True) -> Optional[str]:
        """
        Send a command to FlightGear and return its response.

        Args:
            command: Command to send.
            expect_response: If False, do not wait for a socket response.

        Returns:
            Server response, or None on error.
        """
        if not self.connected or not self.socket:
            logger.error("No active FlightGear connection")
            self._append_command_log(f"SEND ERROR (no connection): {command}")
            return None

        try:
            self._drain_pending_data()
            full_command = command.strip() + "\r\n"
            self.socket.sendall(full_command.encode("utf-8"))
            self._append_command_log(f">>> {command.strip()}")

            if not expect_response:
                self._append_command_log("<<< <not waited>")
                return ""

            data = b""
            while True:
                try:
                    chunk = self.socket.recv(1024)
                except socket.timeout:
                    break

                if not chunk:
                    break

                data += chunk
                if b"\n" in chunk:
                    # Sometimes FlightGear appends a delayed response to the
                    # current one. In data mode, read a tiny extra window so
                    # the parser can keep the last useful line without
                    # desynchronizing the next command.
                    if self.use_data_mode:
                        previous_timeout = self.socket.gettimeout()
                        try:
                            self.socket.settimeout(0.03)
                            while True:
                                try:
                                    extra = self.socket.recv(1024)
                                except socket.timeout:
                                    break
                                if not extra:
                                    break
                                data += extra
                        finally:
                            self.socket.settimeout(previous_timeout)
                    break

            raw_response = data.decode("utf-8", errors="ignore").strip()
            response = self._clean_response(raw_response)
            self._append_command_log(f"<<< {response if response else '<empty>'}")
            return response
        except Exception as exc:
            logger.error(f"Error sending command '{command}': {exc}")
            self._append_command_log(f"SEND EXCEPTION {command}: {exc}")
            return None

    def get_property(self, property_path: str) -> Optional[str]:
        """
        Get the value of a FlightGear property.

        Args:
            property_path: Property path, for example "/sim/aircraft".

        Returns:
            Property value as a string.
        """
        normalized_path = self._normalize_property_path(property_path)
        command = f"get {normalized_path}"
        return self.send_command(command)

    def get_properties(self, property_paths: list[str]) -> dict[str, Optional[str]]:
        """
        Get multiple properties in a single TCP round trip.

        FlightGear telnet responds in order in data mode. Sending all `get`
        commands together greatly reduces runway control-loop latency.
        """
        normalized_paths = [
            self._normalize_property_path(path)
            for path in property_paths
        ]
        results = {path: None for path in normalized_paths}
        if not normalized_paths:
            return results

        if not self.connected or not self.socket:
            logger.error("No active FlightGear connection")
            self._append_command_log(
                f"BATCH GET ERROR (no connection): {len(normalized_paths)} properties"
            )
            return results

        try:
            self._drain_pending_data()
            commands = "".join(f"get {path}\r\n" for path in normalized_paths)
            self.socket.sendall(commands.encode("utf-8"))
            self._append_command_log(
                ">>> batch get "
                + ", ".join(normalized_paths)
            )

            previous_timeout = self.socket.gettimeout()
            raw_data = b""
            deadline = time.time() + self.response_timeout
            lines: list[str] = []

            try:
                self.socket.settimeout(0.03)
                while time.time() < deadline and len(lines) < len(normalized_paths):
                    try:
                        chunk = self.socket.recv(4096)
                    except socket.timeout:
                        continue

                    if not chunk:
                        break

                    raw_data += chunk
                    text = raw_data.decode("utf-8", errors="ignore")
                    lines = [
                        line.strip()
                        for line in text.replace("\r", "\n").split("\n")
                        if line.strip() and not line.strip().endswith(">")
                    ]
            finally:
                self.socket.settimeout(previous_timeout)

            for path, line in zip(normalized_paths, lines):
                results[path] = line

            if len(lines) < len(normalized_paths):
                self._append_command_log(
                    f"<<< batch incomplete {len(lines)}/{len(normalized_paths)}: "
                    f"{raw_data.decode('utf-8', errors='ignore').strip()}"
                )
            else:
                self._append_command_log("<<< batch " + " | ".join(lines))

            return results
        except Exception as exc:
            logger.error(f"Error getting batch properties: {exc}")
            self._append_command_log(f"BATCH GET EXCEPTION: {exc}")
            return results

    def set_property(self, property_path: str, value: Any) -> bool:
        """
        Set the value of a FlightGear property.

        Args:
            property_path: Property path.
            value: New value.

        Returns:
            True if the property was set successfully.
        """
        normalized_path = self._normalize_property_path(property_path)
        command = f"set {normalized_path} {value}"
        response = self.send_command(command, expect_response=False)
        if response is None:
            return False
        if response.startswith("-ERR"):
            logger.error(f"FlightGear rejected command: {command} -> {response}")
            return False
        return True

    def __enter__(self):
        """Context manager support."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Automatic cleanup."""
        self.disconnect()
