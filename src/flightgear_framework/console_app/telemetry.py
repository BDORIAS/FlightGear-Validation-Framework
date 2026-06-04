"""Helpers for reading the latest telemetry row and log tails."""

from __future__ import annotations

import csv
from collections import deque
from pathlib import Path

from .profiles import TelemetryField, TestProfile


class TelemetryTailer:
    """Read small, display-friendly slices of CSV and text logs."""

    def latest_row(self, csv_path: Path | None) -> dict[str, str]:
        if not csv_path or not csv_path.is_file():
            return {}

        last_row: dict[str, str] = {}
        with open(csv_path, newline="", encoding="utf-8") as csv_file:
            reader = csv.DictReader(csv_file)
            for row in reader:
                last_row = dict(row)
        return last_row

    def selected_fields(
        self,
        profile: TestProfile,
        latest_row: dict[str, str],
        max_fields: int = 14,
    ) -> list[TelemetryField]:
        if profile.primary_fields:
            fields = list(profile.primary_fields)
            fields.extend(
                TelemetryField(key)
                for key in profile.secondary_fields
                if key not in {field.key for field in fields}
            )
            return fields[:max_fields]

        common_prefixes = (
            "phase",
            "status",
            "altitude",
            "airspeed",
            "groundspeed",
            "vertical_speed",
            "engine",
            "rpm",
            "heading",
            "pitch",
            "roll",
        )
        preferred = [
            TelemetryField(key)
            for key in latest_row.keys()
            if key.startswith(common_prefixes)
        ]
        remaining = [
            TelemetryField(key)
            for key in latest_row.keys()
            if key not in {field.key for field in preferred}
        ]
        return (preferred + remaining)[:max_fields]

    def tail_lines(self, path: Path, max_lines: int = 12) -> list[str]:
        if not path.is_file():
            return []
        lines: deque[str] = deque(maxlen=max_lines)
        with open(path, encoding="utf-8", errors="replace") as log_file:
            for line in log_file:
                lines.append(line.rstrip())
        return list(lines)

    @staticmethod
    def format_value(value: str | None, unit: str = "") -> str:
        if value is None or value == "":
            return "-"
        text = str(value)
        try:
            number = float(text)
        except ValueError:
            return text
        if abs(number) >= 100:
            rendered = f"{number:.0f}"
        elif abs(number) >= 10:
            rendered = f"{number:.1f}"
        else:
            rendered = f"{number:.2f}"
        return f"{rendered} {unit}".rstrip()
