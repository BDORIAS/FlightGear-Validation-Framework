"""Command-line entrypoint for the local telemetry viewer."""

from __future__ import annotations

import argparse
from pathlib import Path

from .server import DEFAULT_VIEWER_HOST, DEFAULT_VIEWER_PORT, run_server


def build_parser() -> argparse.ArgumentParser:
    """Create the viewer CLI argument parser."""
    parser = argparse.ArgumentParser(description="FlightGear telemetry viewer")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--profile", default="cruise_engine_failure")
    parser.add_argument("--host", default=DEFAULT_VIEWER_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_VIEWER_PORT)
    parser.add_argument("--no-focus", action="store_true", help="Show the full CSV")
    parser.add_argument("--open-browser", action="store_true", help="Open the viewer URL")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Start the viewer server for a selected test profile."""
    args = build_parser().parse_args(argv)
    project_root = args.project_root or Path(__file__).resolve().parents[3]
    run_server(
        project_root,
        args.profile,
        host=args.host,
        port=args.port,
        focus=not args.no_focus,
        open_browser=args.open_browser,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
