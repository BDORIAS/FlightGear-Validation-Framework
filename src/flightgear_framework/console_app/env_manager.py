"""Environment preparation for console-launched framework processes."""

from __future__ import annotations

import os
import socket
from pathlib import Path
from typing import Any

import yaml

from flightgear_framework import native
from flightgear_framework.configuration import (
    flightgear_connection_settings,
    flightgear_simulator_settings,
)


class EnvManager:
    """Resolve project paths, config values, and process environment variables."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path(__file__).resolve().parents[3]
        self.src_dir = self.project_root / "src"
        self.venv_dir = self.project_root / "venv_flightgear"
        self.config_path = self.project_root / "config" / "framework_config.yaml"
        self.config = self.load_config()
        self.native_build = native.build_status()

    def load_config(self) -> dict[str, Any]:
        if not self.config_path.is_file():
            return {}
        with open(self.config_path, encoding="utf-8") as config_file:
            return yaml.safe_load(config_file) or {}

    @property
    def venv_python(self) -> Path:
        windows_python = self.venv_dir / "Scripts" / "python.exe"
        if windows_python.is_file():
            return windows_python
        return self.venv_dir / "bin" / "python"

    @property
    def venv_scripts_dir(self) -> Path:
        scripts = self.venv_dir / "Scripts"
        if scripts.is_dir():
            return scripts
        return self.venv_dir / "bin"

    def flightgear_connection(self) -> dict[str, Any]:
        return flightgear_connection_settings(self.config)

    def flightgear_simulator(self) -> dict[str, Any]:
        return flightgear_simulator_settings(self.config)

    def ensure_native_backend(self) -> dict[str, Any]:
        """Attempt to build and load the optional C++ backend."""
        self.native_build = native.ensure_native_backend(
            self.project_root,
            python_executable=self.venv_python,
        )
        return self.native_build

    def prepare_env(self) -> dict[str, str]:
        """Build the environment used by tests, viewers, and child processes."""
        env = os.environ.copy()
        conn = self.flightgear_connection()
        sim = self.flightgear_simulator()

        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            str(self.src_dir)
            if not existing_pythonpath
            else str(self.src_dir) + os.pathsep + existing_pythonpath
        )
        env["VIRTUAL_ENV"] = str(self.venv_dir)
        env["PATH"] = str(self.venv_scripts_dir) + os.pathsep + env.get("PATH", "")
        env["PROJECT_ROOT"] = str(self.project_root)
        env["FGFS_EXECUTABLE"] = str(sim.get("executable", "fgfs"))
        data_dir = sim.get("data_dir")
        if data_dir:
            env["FG_ROOT"] = str(data_dir)
        else:
            env.pop("FG_ROOT", None)
        env["FG_HOST"] = str(conn.get("host", "localhost"))
        env["FG_TELNET_PORT"] = str(conn.get("port", 5401))
        env["FG_AIRCRAFT"] = str(sim.get("default_aircraft", "c172p"))
        env["FG_AIRPORT"] = str(sim.get("default_airport", "BIKF"))
        env["FG_RUNWAY"] = str(sim.get("default_runway", "29"))
        env["FG_RESPONSE_TIMEOUT"] = str(conn.get("response_timeout", 1.2))
        env["FG_DISABLE_TERRASYNC"] = str(sim.get("disable_terrasync", False)).lower()
        env["FG_RESULTS_DIR"] = str(self.project_root / "data" / "results")
        env["FLIGHTGEAR_NATIVE_BACKEND"] = native.BACKEND
        env["FLIGHTGEAR_NATIVE_BUILD_STATUS"] = str(self.native_build.get("status", ""))
        return env

    def export_env_file(self, path: Path | None = None) -> Path:
        """Write the effective framework environment to a dotenv-style file."""
        target = path or (self.project_root / ".env.console")
        exported = self.prepare_env()
        keys = [
            "PROJECT_ROOT",
            "PYTHONPATH",
            "VIRTUAL_ENV",
            "FGFS_EXECUTABLE",
            "FG_ROOT",
            "FG_HOST",
            "FG_TELNET_PORT",
            "FG_AIRCRAFT",
            "FG_AIRPORT",
            "FG_RUNWAY",
            "FG_RESPONSE_TIMEOUT",
            "FG_DISABLE_TERRASYNC",
            "FG_RESULTS_DIR",
            "FLIGHTGEAR_NATIVE_BACKEND",
            "FLIGHTGEAR_NATIVE_BUILD_STATUS",
        ]
        with open(target, "w", encoding="utf-8") as env_file:
            for key in keys:
                if key in exported:
                    env_file.write(f"{key}={exported[key]}\n")
        return target

    def telnet_port_status(self) -> str:
        conn = self.flightgear_connection()
        host = str(conn.get("host", "localhost"))
        port = int(conn.get("port", 5401))
        try:
            with socket.create_connection((host, port), timeout=0.25):
                return "open"
        except OSError:
            return "closed"

    def summary(self) -> dict[str, str]:
        """Return concise status information for CLI and console headers."""
        conn = self.flightgear_connection()
        sim = self.flightgear_simulator()
        return {
            "project": str(self.project_root),
            "python": str(self.venv_python),
            "native_backend": native.BACKEND,
            "native_available": str(native.is_native_available()),
            "native_build": str(self.native_build.get("status", "")),
            "native_build_message": str(self.native_build.get("message", "")),
            "fgfs": str(sim.get("executable", "fgfs")),
            "fg_root": str(sim.get("data_dir") or ""),
            "aircraft": str(sim.get("default_aircraft", "c172p")),
            "airport": str(sim.get("default_airport", "BIKF")),
            "runway": str(sim.get("default_runway", "29")),
            "host": str(conn.get("host", "localhost")),
            "port": str(conn.get("port", 5401)),
            "telnet_port": self.telnet_port_status(),
        }
