"""Subprocess lifecycle management for the visual console."""

from __future__ import annotations

import subprocess
import threading
import time
from collections import deque
from pathlib import Path

from .profiles import TestProfile


class ProcessManager:
    """Run one test process at a time while keeping recent output in memory."""

    def __init__(self):
        self.profile: TestProfile | None = None
        self.process: subprocess.Popen[str] | None = None
        self.started_at: float | None = None
        self.ended_at: float | None = None
        self.stdout_lines: deque[str] = deque(maxlen=250)
        self.last_error: str | None = None
        self._reader_thread: threading.Thread | None = None

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(
        self,
        profile: TestProfile,
        command: list[str],
        cwd: Path,
        env: dict[str, str],
    ) -> bool:
        if self.is_running():
            self.last_error = "A process is already running."
            return False

        self.profile = profile
        self.started_at = time.time()
        self.ended_at = None
        self.last_error = None
        self.stdout_lines.clear()
        self.stdout_lines.append("$ " + " ".join(command))

        try:
            self.process = subprocess.Popen(
                command,
                cwd=str(cwd),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except Exception as exc:
            self.process = None
            self.ended_at = time.time()
            self.last_error = str(exc)
            self.stdout_lines.append(f"ERROR: {exc}")
            return False

        self._reader_thread = threading.Thread(
            target=self._read_stdout,
            name="fg-console-process-reader",
            daemon=True,
        )
        self._reader_thread.start()
        return True

    def _read_stdout(self) -> None:
        if not self.process or not self.process.stdout:
            return
        try:
            for line in self.process.stdout:
                self.stdout_lines.append(line.rstrip())
        finally:
            if self.process:
                self.process.wait()
                self.ended_at = time.time()

    def stop(self, kill_after_seconds: float = 5.0) -> None:
        if not self.process:
            return
        if self.process.poll() is not None:
            self.ended_at = self.ended_at or time.time()
            return

        self.stdout_lines.append("Requesting process termination...")
        self.process.terminate()
        try:
            self.process.wait(timeout=kill_after_seconds)
        except subprocess.TimeoutExpired:
            self.stdout_lines.append("Forcing process shutdown...")
            self.process.kill()
            self.process.wait()
        self.ended_at = time.time()

    def poll(self) -> int | None:
        if not self.process:
            return None
        code = self.process.poll()
        if code is not None and self.ended_at is None:
            self.ended_at = time.time()
        return code

    def elapsed_seconds(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.ended_at or time.time()
        return max(0.0, end - self.started_at)

    def status_text(self) -> str:
        if not self.process:
            return "idle"
        code = self.poll()
        if code is None:
            return "running"
        return f"finished ({code})"

    def return_code(self) -> int | None:
        if not self.process:
            return None
        return self.process.poll()
