"""Prompt-toolkit user interface for selecting and running test profiles."""

from __future__ import annotations

from pathlib import Path
import subprocess

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Frame

from .env_manager import EnvManager
from .process_manager import ProcessManager
from .profiles import TestProfile
from .registry import TestRegistry
from .session_store import SessionStore
from .telemetry import TelemetryTailer


class ConsoleApp:
    """Full-screen console that controls tests, logs, telemetry, and the viewer."""

    def __init__(self, project_root: Path | None = None):
        self.env_manager = EnvManager(project_root)
        native_build = self.env_manager.ensure_native_backend()
        self.registry = TestRegistry(self.env_manager.project_root)
        self.profiles = self.registry.profiles(include_discovered=True)
        self.process_manager = ProcessManager()
        self.telemetry = TelemetryTailer()
        self.sessions = SessionStore(self.env_manager.project_root)
        self.selected_index = 0
        self.message = (
            "Ready. Arrows: select | r: run | v: viewer | s: stop | e: export env | q: quit"
        )
        if native_build.get("status") == "failed":
            self.message = "Native build failed; using Python fallback. Run --status for details."
        self._recorded_process_token: tuple[str, float | None] | None = None

    @property
    def selected_profile(self) -> TestProfile:
        return self.profiles[self.selected_index]

    def run(self) -> None:
        bindings = self._key_bindings()
        root = HSplit(
            [
                Window(
                    FormattedTextControl(self._render_header),
                    height=Dimension.exact(4),
                ),
                VSplit(
                    [
                        Frame(
                            Window(
                                FormattedTextControl(self._render_tests),
                                width=Dimension(preferred=36),
                                wrap_lines=False,
                            ),
                            title="Tests",
                        ),
                        HSplit(
                            [
                                Frame(
                                    Window(
                                        FormattedTextControl(self._render_dashboard),
                                        height=Dimension(weight=1),
                                    ),
                                    title="Dashboard",
                                ),
                                Frame(
                                    Window(
                                        FormattedTextControl(self._render_logs),
                                        height=Dimension(weight=1),
                                    ),
                                    title="Logs",
                                ),
                            ],
                            width=Dimension(weight=2),
                        ),
                    ],
                    height=Dimension(weight=1),
                ),
                Window(
                    FormattedTextControl(self._render_footer),
                    height=Dimension.exact(2),
                ),
            ]
        )
        app = Application(
            layout=Layout(root),
            key_bindings=bindings,
            full_screen=True,
            refresh_interval=1.0,
            style=Style.from_dict(
                {
                    "header": "bold reverse",
                    "ok": "ansigreen",
                    "warn": "ansiyellow",
                    "error": "ansired",
                    "selected": "reverse",
                    "muted": "ansibrightblack",
                }
            ),
        )
        app.run()

    def _key_bindings(self) -> KeyBindings:
        bindings = KeyBindings()

        @bindings.add("q")
        def _(event):
            event.app.exit()

        @bindings.add("up")
        def _(event):
            self.selected_index = max(0, self.selected_index - 1)
            event.app.invalidate()

        @bindings.add("down")
        def _(event):
            self.selected_index = min(len(self.profiles) - 1, self.selected_index + 1)
            event.app.invalidate()

        @bindings.add("r")
        def _(event):
            self._run_selected()
            event.app.invalidate()

        @bindings.add("s")
        def _(event):
            self.process_manager.stop()
            self.message = "Process stopped."
            event.app.invalidate()

        @bindings.add("e")
        def _(event):
            path = self.env_manager.export_env_file()
            self.message = f"Environment variables exported to {path}"
            event.app.invalidate()

        @bindings.add("c")
        def _(event):
            self.process_manager.stdout_lines.clear()
            self.message = "Process output cleared."
            event.app.invalidate()

        @bindings.add("v")
        def _(event):
            self._open_viewer_selected()
            event.app.invalidate()

        return bindings

    def _run_selected(self) -> None:
        profile = self.selected_profile
        command = profile.command(self.env_manager.venv_python)
        env = self.env_manager.prepare_env()
        started = self.process_manager.start(
            profile,
            command,
            self.env_manager.project_root,
            env,
        )
        self._recorded_process_token = None
        self.message = (
            f"Running {profile.name}"
            if started
            else f"Could not run: {self.process_manager.last_error}"
        )

    def _record_finished_session_if_needed(self) -> None:
        manager = self.process_manager
        profile = manager.profile
        if not profile or not manager.process:
            return
        code = manager.poll()
        if code is None:
            return
        token = (profile.id, manager.started_at)
        if self._recorded_process_token == token:
            return
        self.sessions.append(profile, manager.started_at, manager.ended_at, code)
        self._recorded_process_token = token

    def _open_viewer_selected(self) -> None:
        profile = self.selected_profile
        if not profile.output_csv:
            self.message = f"{profile.name} does not define a telemetry CSV."
            return
        csv_path = profile.csv_path(self.env_manager.project_root)
        if csv_path is None or not csv_path.is_file():
            self.message = f"Telemetry CSV not found for {profile.name}."
            return
        command = [
            str(self.env_manager.venv_python),
            "-m",
            "flightgear_framework.viewer",
            "--project-root",
            str(self.env_manager.project_root),
            "--profile",
            profile.id,
            "--open-browser",
        ]
        subprocess.Popen(
            command,
            cwd=self.env_manager.project_root,
            env=self.env_manager.prepare_env(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.message = f"Opening telemetry viewer for {profile.name}."

    def _render_header(self):
        self._record_finished_session_if_needed()
        summary = self.env_manager.summary()
        status_style = "ok" if summary["telnet_port"] == "open" else "warn"
        native_style = "ok" if summary["native_backend"] == "cpp" else "warn"
        return [
            ("class:header", " FlightGear Test Framework Console \n"),
            (
                "",
                f" FG: {summary['fgfs']} | root: {summary['fg_root'] or '-'}\n",
            ),
            (
                "",
                f" Aircraft: {summary['aircraft']} | Airport: {summary['airport']} | "
                f"Runway: {summary['runway']} | Telnet: {summary['host']}:{summary['port']} ",
            ),
            (f"class:{status_style}", f"({summary['telnet_port']}) "),
            ("", "| Native: "),
            (f"class:{native_style}", summary["native_backend"]),
        ]

    def _render_tests(self):
        chunks = []
        for index, profile in enumerate(self.profiles):
            prefix = "> " if index == self.selected_index else "  "
            style = "selected" if index == self.selected_index else ""
            fg_flag = "FG" if profile.requires_flightgear else "--"
            chunks.append((f"class:{style}", f"{prefix}{profile.name}\n"))
            chunks.append(("class:muted", f"   {profile.category} | {fg_flag} | {profile.id}\n"))
        return chunks

    def _render_dashboard(self):
        profile = self.selected_profile
        csv_path = profile.csv_path(self.env_manager.project_root)
        latest = self.telemetry.latest_row(csv_path)
        fields = self.telemetry.selected_fields(profile, latest)
        manager = self.process_manager

        lines = [
            ("", f"Profile: {profile.name}\n"),
            ("class:muted", f"{profile.description}\n\n"),
            ("", f"Process: {manager.status_text()} | Duration: {manager.elapsed_seconds():.1f}s\n"),
        ]
        if csv_path:
            lines.append(("class:muted", f"CSV: {csv_path}\n"))
        if manager.last_error:
            lines.append(("class:error", f"Error: {manager.last_error}\n"))
        lines.append(("", "\nExpected phases:\n"))
        phase = latest.get("phase")
        for expected_phase in profile.phases[:12]:
            marker = "*" if phase == expected_phase else "-"
            style = "ok" if marker == "*" else "muted"
            lines.append((f"class:{style}", f" {marker} {expected_phase}\n"))

        lines.append(("", "\nTelemetry:\n"))
        if latest:
            for field in fields:
                value = self.telemetry.format_value(latest.get(field.key), field.unit)
                lines.append(("", f" {field.display_label:<24} {value}\n"))
        else:
            lines.append(("class:muted", " No telemetry available yet.\n"))
            if profile.requires_flightgear:
                lines.append(("class:muted", " Run the profile or check whether the CSV exists.\n"))

        return lines

    def _render_logs(self):
        profile = self.selected_profile
        lines = [("", "Process output:\n")]
        stdout = list(self.process_manager.stdout_lines)[-10:]
        if stdout:
            for line in stdout:
                lines.append(("", f" {line[:140]}\n"))
        else:
            lines.append(("class:muted", " No captured output.\n"))

        for log_path in profile.log_paths(self.env_manager.project_root):
            lines.append(("", f"\n{log_path.name}:\n"))
            tail = self.telemetry.tail_lines(log_path, max_lines=8)
            if not tail:
                lines.append(("class:muted", " Missing or empty.\n"))
                continue
            for line in tail:
                style = "error" if "ERROR" in line or "Failure" in line else ""
                lines.append((f"class:{style}", f" {line[:140]}\n"))
        return lines

    def _render_footer(self):
        return [
            ("class:header", " r run | v viewer | s stop | e export env | c clear output | q quit \n"),
            ("", self.message),
        ]
