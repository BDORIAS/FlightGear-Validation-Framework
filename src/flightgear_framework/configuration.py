"""Configuration helpers shared by the console and test runners.

The YAML file carries portable defaults. Environment variables override those
defaults at runtime so users can install the framework in any directory without
editing source files.
"""

from __future__ import annotations

import os
from typing import Any


def _env_value(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _first_env_value(*names: str) -> str | None:
    for name in names:
        value = _env_value(name)
        if value is not None:
            return value
    return None


def _to_int(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _normalize_optional_path(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def flightgear_connection_settings(config: dict[str, Any]) -> dict[str, Any]:
    """Return effective telnet connection settings for FlightGear."""
    fg_config = config.get("flightgear", {})
    connection = fg_config.get("connection", {}).copy()
    connection["port"] = _to_int(connection.get("port"), 5401)
    connection["response_timeout"] = _to_float(connection.get("response_timeout"), 1.2)

    host = _first_env_value("FG_HOST")
    port = _first_env_value("FG_TELNET_PORT", "FG_PORT")
    response_timeout = _first_env_value("FG_RESPONSE_TIMEOUT")

    if host is not None:
        connection["host"] = host
    if port is not None:
        connection["port"] = _to_int(port, connection["port"])
    if response_timeout is not None:
        connection["response_timeout"] = _to_float(
            response_timeout,
            connection["response_timeout"],
        )

    return connection


def flightgear_simulator_settings(config: dict[str, Any]) -> dict[str, Any]:
    """Return effective simulator launch settings for FlightGear."""
    fg_config = config.get("flightgear", {})
    simulator = fg_config.get("simulator", {}).copy()

    env_to_config_key = {
        "FGFS_EXECUTABLE": "executable",
        "FG_ROOT": "data_dir",
        "FG_AIRCRAFT": "default_aircraft",
        "FG_AIRPORT": "default_airport",
        "FG_RUNWAY": "default_runway",
    }
    for env_name, config_key in env_to_config_key.items():
        value = _env_value(env_name)
        if value is not None:
            simulator[config_key] = value

    disable_terrasync = _env_value("FG_DISABLE_TERRASYNC")
    if disable_terrasync is not None:
        simulator["disable_terrasync"] = _to_bool(disable_terrasync)

    simulator["disable_terrasync"] = _to_bool(simulator.get("disable_terrasync", False))
    simulator["data_dir"] = _normalize_optional_path(simulator.get("data_dir"))
    return simulator
