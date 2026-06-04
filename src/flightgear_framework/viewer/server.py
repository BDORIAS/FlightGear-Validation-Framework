"""Local HTTP server for the interactive telemetry viewer."""

from __future__ import annotations

from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import socket
from typing import Any
from urllib.parse import urlparse
import webbrowser

import pandas as pd
import plotly
import yaml

from flightgear_framework import native
from flightgear_framework.configuration import flightgear_simulator_settings
from flightgear_framework.console_app.registry import TestRegistry

from .dataset import DatasetBundle
from .dataset import build_payload, load_dataset
from .validation import compute_validation_metrics


DEFAULT_VIEWER_HOST = "127.0.0.1"
DEFAULT_VIEWER_PORT = 8765
CONTROL_SURFACE_COLUMNS = (
    ("throttle_norm", "Throttle"),
    ("elevator_norm", "Elevator"),
    ("elevator_trim_norm", "Elevator trim"),
    ("aileron_norm", "Aileron"),
    ("rudder_norm", "Rudder"),
    ("rudder_raw_norm", "Raw rudder"),
    ("rudder_saturated_norm", "Saturated rudder"),
    ("flaps_norm", "Flaps"),
    ("brake_left", "Left brake"),
    ("brake_right", "Right brake"),
    ("brake_parking", "Parking brake"),
)
KEY_SIGNAL_COLUMNS = (
    ("altitude_agl_ft", "Altitude AGL", "ft"),
    ("airspeed_kts", "Airspeed", "kt"),
    ("groundspeed_kts", "Groundspeed", "kt"),
    ("vertical_speed_fpm", "Vertical speed", "fpm"),
    ("pitch_deg", "Pitch", "deg"),
    ("roll_deg", "Roll", "deg"),
    ("heading_deg", "Heading", "deg"),
    ("engine_rpm", "Engine RPM", "rpm"),
)


class ViewerServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        *,
        payload: dict[str, Any],
        template_dir: Path,
        static_dir: Path,
        plotly_js_path: Path,
    ):
        super().__init__(server_address, handler_class)
        self.payload = payload
        self.template_dir = template_dir
        self.static_dir = static_dir
        self.plotly_js_path = plotly_js_path


class ViewerRequestHandler(BaseHTTPRequestHandler):
    server: ViewerServer

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path in {"", "/"}:
            self._serve_file(self.server.template_dir / "index.html", "text/html")
            return
        if path == "/api/dataset":
            self._serve_json(self.server.payload)
            return
        if path == "/api/health":
            self._serve_json({"status": "ok"})
            return
        if path == "/static/plotly.min.js":
            self._serve_file(self.server.plotly_js_path, "application/javascript")
            return
        if path.startswith("/static/"):
            relative = path.removeprefix("/static/")
            self._serve_file(self.server.static_dir / relative)
            return
        self.send_error(404, "Not found")

    def log_message(self, format: str, *args: object) -> None:
        return

    def _serve_json(self, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=True, allow_nan=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_file(self, path: Path, content_type: str | None = None) -> None:
        if not path.is_file():
            self.send_error(404, "File not found")
            return
        data = path.read_bytes()
        mime = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def build_viewer_payload(
    project_root: Path,
    profile_id: str,
    *,
    focus: bool = True,
) -> dict[str, Any]:
    """Build the JSON payload served to the browser."""
    registry = TestRegistry(project_root)
    profile = registry.get(profile_id)
    bundle = load_dataset(project_root, profile, focus=focus)
    payload = build_payload(bundle)
    payload["validation_metrics"] = compute_validation_metrics(bundle)
    payload["native_backend"] = {
        "backend": native.BACKEND,
        "available": native.is_native_available(),
    }
    payload["logs"] = _read_log_tails(project_root, profile.logs)
    payload["report_summary"] = _build_report_summary(project_root, bundle)
    return payload


def create_server(
    project_root: Path,
    profile_id: str,
    *,
    host: str = DEFAULT_VIEWER_HOST,
    port: int = DEFAULT_VIEWER_PORT,
    focus: bool = True,
) -> ViewerServer:
    payload = build_viewer_payload(project_root, profile_id, focus=focus)
    module_dir = Path(__file__).resolve().parent
    template_dir = module_dir / "templates"
    static_dir = module_dir / "static"
    plotly_js_path = _plotly_js_path()
    selected_port = _available_port(host, port)
    return ViewerServer(
        (host, selected_port),
        ViewerRequestHandler,
        payload=payload,
        template_dir=template_dir,
        static_dir=static_dir,
        plotly_js_path=plotly_js_path,
    )


def run_server(
    project_root: Path,
    profile_id: str,
    *,
    host: str = DEFAULT_VIEWER_HOST,
    port: int = DEFAULT_VIEWER_PORT,
    focus: bool = True,
    open_browser: bool = False,
) -> str:
    """Start the viewer server and optionally open it in a browser."""
    server = create_server(
        project_root,
        profile_id,
        host=host,
        port=port,
        focus=focus,
    )
    actual_host, actual_port = server.server_address
    url = f"http://{actual_host}:{actual_port}/"
    print(f"Telemetry viewer ready: {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return url


def _plotly_js_path() -> Path:
    path = Path(plotly.__file__).resolve().parent / "package_data" / "plotly.min.js"
    if not path.is_file():
        raise FileNotFoundError(f"Plotly JavaScript bundle not found: {path}")
    return path


def _available_port(host: str, preferred_port: int) -> int:
    if preferred_port == 0:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind((host, 0))
            return int(probe.getsockname()[1])

    for port in range(preferred_port, preferred_port + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind((host, port))
            except OSError:
                continue
            return port
    raise OSError(f"No available port found from {preferred_port} to {preferred_port + 49}")


def _read_log_tails(project_root: Path, logs: tuple[str, ...]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for relative in logs:
        path = project_root / relative
        if not path.is_file():
            items.append({"name": Path(relative).name, "path": str(path), "lines": []})
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-80:]
        except OSError:
            lines = []
        items.append({"name": path.name, "path": str(path), "lines": lines})
    return items


def _build_report_summary(project_root: Path, bundle: DatasetBundle) -> dict[str, Any]:
    sim = flightgear_simulator_settings(_load_config(project_root))
    focus = bundle.focus_window
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "test_name": bundle.profile.name,
        "test_id": bundle.profile.id,
        "aircraft": sim.get("default_aircraft", "c172p"),
        "airport": sim.get("default_airport", "BIKF"),
        "runway": sim.get("default_runway", "29"),
        "csv_name": bundle.csv_path.name,
        "full_rows": int(len(bundle.full_frame)),
        "focused_rows": int(len(bundle.focused_frame)),
        "focus_window": {
            "enabled": focus.enabled,
            "source": focus.source,
            "x_label": focus.x_label,
            "pre_seconds": focus.pre_seconds,
            "post_seconds": focus.post_seconds,
            "start_elapsed_s": focus.start_elapsed_s,
            "end_elapsed_s": focus.end_elapsed_s,
            "event_start_elapsed_s": focus.event_start_elapsed_s,
        },
        "control_surfaces": _column_stats(
            bundle.focused_frame,
            CONTROL_SURFACE_COLUMNS,
            default_unit="norm",
        ),
        "key_signals": _column_stats(bundle.focused_frame, KEY_SIGNAL_COLUMNS),
    }


def _load_config(project_root: Path) -> dict[str, Any]:
    path = project_root / "config" / "framework_config.yaml"
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as config_file:
        return yaml.safe_load(config_file) or {}


def _column_stats(
    frame: pd.DataFrame,
    columns: tuple[tuple[str, str] | tuple[str, str, str], ...],
    *,
    default_unit: str = "",
) -> list[dict[str, Any]]:
    stats: list[dict[str, Any]] = []
    for item in columns:
        key = item[0]
        label = item[1]
        unit = item[2] if len(item) > 2 else default_unit
        if key not in frame.columns:
            continue
        series = pd.to_numeric(frame[key], errors="coerce").dropna()
        if series.empty:
            continue
        stats.append(
            {
                "key": key,
                "label": label,
                "unit": unit,
                "min": _round_stat(series.min()),
                "max": _round_stat(series.max()),
                "mean": _round_stat(series.mean()),
                "final": _round_stat(series.iloc[-1]),
            }
        )
    return stats


def _round_stat(value: Any) -> float:
    return round(float(value), 3)
