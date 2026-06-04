"""Persistent history for console-launched test sessions."""

from __future__ import annotations

import json
import time
from pathlib import Path

from .profiles import TestProfile


class SessionStore:
    """Append and load recent console test sessions as JSON."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.path = project_root / "data" / "results" / "console_sessions.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(
        self,
        profile: TestProfile,
        started_at: float | None,
        ended_at: float | None,
        return_code: int | None,
    ) -> None:
        sessions = self.load()
        sessions.append(
            {
                "profile_id": profile.id,
                "profile_name": profile.name,
                "started_at": started_at,
                "ended_at": ended_at,
                "duration_s": (
                    round((ended_at or time.time()) - started_at, 3)
                    if started_at
                    else None
                ),
                "return_code": return_code,
                "csv": profile.output_csv,
                "logs": list(profile.logs),
            }
        )
        with open(self.path, "w", encoding="utf-8") as store_file:
            json.dump(sessions[-100:], store_file, indent=2)

    def load(self) -> list[dict]:
        if not self.path.is_file():
            return []
        try:
            with open(self.path, encoding="utf-8") as store_file:
                data = json.load(store_file)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []
