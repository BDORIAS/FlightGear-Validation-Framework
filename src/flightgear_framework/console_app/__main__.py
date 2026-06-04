"""Command-line entrypoint for the visual test console."""

from __future__ import annotations

import argparse
from pathlib import Path

from .env_manager import EnvManager
from .registry import TestRegistry
from .ui import ConsoleApp


def build_parser() -> argparse.ArgumentParser:
    """Create the console CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="FlightGear Test Framework visual console"
    )
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--list", action="store_true", help="List available profiles")
    parser.add_argument("--status", action="store_true", help="Show environment status")
    parser.add_argument("--export-env", action="store_true", help="Write .env.console")
    parser.add_argument(
        "--dry-run",
        metavar="PROFILE_ID",
        help="Show command and relevant environment without executing",
    )
    parser.add_argument(
        "--viewer",
        metavar="PROFILE_ID",
        help="Open the local telemetry viewer for a profile",
    )
    parser.add_argument("--viewer-port", type=int, default=8765)
    parser.add_argument(
        "--viewer-full-csv",
        action="store_true",
        help="Show the full CSV instead of the focused event window",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run a console CLI command or launch the full-screen console."""
    args = build_parser().parse_args(argv)
    env_manager = EnvManager(args.project_root)
    env_manager.ensure_native_backend()
    registry = TestRegistry(env_manager.project_root)

    if args.list:
        for profile in registry.profiles(include_discovered=True):
            flag = "requires FG" if profile.requires_flightgear else "no FG"
            print(f"{profile.id}\t{profile.category}\t{flag}\t{profile.name}")
        return 0

    if args.status:
        for key, value in env_manager.summary().items():
            print(f"{key}: {value}")
        return 0

    if args.export_env:
        print(env_manager.export_env_file())
        return 0

    if args.dry_run:
        profile = registry.get(args.dry_run)
        print("Command:")
        print(" ".join(profile.command(env_manager.venv_python)))
        print("\nEnvironment:")
        prepared = env_manager.prepare_env()
        for key in sorted(prepared):
            if key.startswith("FG_") or key in {
                "PROJECT_ROOT",
                "PYTHONPATH",
                "VIRTUAL_ENV",
                "FLIGHTGEAR_NATIVE_BACKEND",
            }:
                print(f"{key}={prepared[key]}")
        return 0

    if args.viewer:
        from flightgear_framework.viewer.server import run_server

        run_server(
            env_manager.project_root,
            args.viewer,
            port=args.viewer_port,
            focus=not args.viewer_full_csv,
            open_browser=True,
        )
        return 0

    ConsoleApp(env_manager.project_root).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
