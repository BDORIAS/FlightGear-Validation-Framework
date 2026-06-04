"""Optional native helpers for FlightGear Test Framework.

The public functions in this module are safe to import even when the C++
extension has not been built. In that case, the pure-Python fallback is used.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from typing import Any


_BUILD_ATTEMPTED = False
_BUILD_STATUS: dict[str, Any] = {
    "status": "not_attempted",
    "message": "",
    "error": "",
}


def _load_backend() -> str:
    global _backend
    try:
        _backend = importlib.import_module(f"{__name__}._flightgear_native")
        return "cpp"
    except ImportError:
        _backend = importlib.import_module(f"{__name__}._fallback")
        return "python"


BACKEND = _load_backend()


def is_native_available() -> bool:
    return BACKEND == "cpp"


def build_status() -> dict[str, Any]:
    """Return the last native build attempt status."""
    return dict(_BUILD_STATUS)


def ensure_native_backend(
    project_root: Path | None = None,
    *,
    python_executable: Path | str | None = None,
) -> dict[str, Any]:
    """Build and load the C++ backend when automatic native builds are enabled."""
    global BACKEND, _BUILD_ATTEMPTED, _BUILD_STATUS

    if BACKEND == "cpp":
        _BUILD_STATUS = {
            "status": "available",
            "message": "C++ backend is already available.",
            "error": "",
        }
        return build_status()

    if _BUILD_ATTEMPTED:
        return build_status()

    if os.environ.get("FG_NATIVE_AUTO_BUILD", "1").lower() in {"0", "false", "no", "off"}:
        _BUILD_STATUS = {
            "status": "disabled",
            "message": "Automatic native build is disabled by FG_NATIVE_AUTO_BUILD.",
            "error": "",
        }
        return build_status()

    if platform.system() != "Windows" and os.environ.get("FG_NATIVE_AUTO_BUILD") != "1":
        _BUILD_STATUS = {
            "status": "skipped",
            "message": "Automatic native build is enabled by default only on Windows.",
            "error": "",
        }
        return build_status()

    _BUILD_ATTEMPTED = True
    root = project_root or Path(__file__).resolve().parents[3]
    setup_path = root / "cpp_modules" / "setup.py"
    if not setup_path.is_file():
        _BUILD_STATUS = {
            "status": "missing_setup",
            "message": f"Native build script was not found: {setup_path}",
            "error": "",
        }
        return build_status()

    python = str(python_executable or sys.executable)
    env = os.environ.copy()
    src_dir = str(root / "src")
    env["PYTHONPATH"] = (
        src_dir
        if not env.get("PYTHONPATH")
        else src_dir + os.pathsep + env["PYTHONPATH"]
    )

    command = [python, str(setup_path), "build_ext", "--inplace"]
    try:
        result = subprocess.run(
            command,
            cwd=str(root),
            env=env,
            text=True,
            capture_output=True,
            timeout=180,
            check=False,
        )
    except Exception as exc:
        _BUILD_STATUS = {
            "status": "failed",
            "message": "Native build command could not be executed.",
            "error": str(exc),
        }
        return build_status()

    if result.returncode != 0:
        output = "\n".join(
            line
            for line in (result.stderr + "\n" + result.stdout).splitlines()[-12:]
            if line.strip()
        )
        _BUILD_STATUS = {
            "status": "failed",
            "message": "Native build failed; using Python fallback.",
            "error": output,
        }
        return build_status()

    importlib.invalidate_caches()
    BACKEND = _load_backend()
    if BACKEND == "cpp":
        shutil.rmtree(root / "build", ignore_errors=True)
        _BUILD_STATUS = {
            "status": "built",
            "message": "C++ backend built and loaded.",
            "error": "",
        }
    else:
        _BUILD_STATUS = {
            "status": "failed",
            "message": "Native build completed, but the C++ backend could not be imported.",
            "error": "",
        }
    return build_status()


def clamp(value: float, min_value: float, max_value: float) -> float:
    return _backend.clamp(value, min_value, max_value)


def heading_error_deg(target_deg: float, current_deg: float) -> float:
    return _backend.heading_error_deg(target_deg, current_deg)


def heading_delta_deg(previous_deg: float, current_deg: float) -> float:
    return _backend.heading_delta_deg(previous_deg, current_deg)


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
    return dict(
        _backend.compute_runway_tracking(
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
            rudder_deadband_deg,
        )
    )


__all__ = [
    "BACKEND",
    "is_native_available",
    "build_status",
    "ensure_native_backend",
    "clamp",
    "heading_error_deg",
    "heading_delta_deg",
    "compute_runway_tracking",
]
