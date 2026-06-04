"""Data structures used to describe runnable tests and viewer plots."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class TelemetryField:
    """Single telemetry value shown in the console dashboard."""

    key: str
    label: str | None = None
    unit: str = ""
    widget: str = "value"

    @property
    def display_label(self) -> str:
        return self.label or self.key


@dataclass(frozen=True)
class PlotSeries:
    """Single CSV column plotted by the viewer."""

    key: str
    label: str | None = None
    unit: str = ""
    kind: str = "line"

    @property
    def display_label(self) -> str:
        return self.label or self.key


@dataclass(frozen=True)
class PlotGroup:
    """Named group of related viewer plots."""

    id: str
    title: str
    description: str = ""
    series: tuple[PlotSeries, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class EventWindow:
    """Focused time window around a test event in the telemetry CSV."""

    id: str
    title: str
    trigger_field: str
    pre_seconds: float = 10.0
    post_seconds: float | None = None
    phase_values: tuple[str, ...] = field(default_factory=tuple)
    fallback_post_seconds: float = 30.0


@dataclass(frozen=True)
class TestProfile:
    """Runnable test definition used by the console and viewer."""

    __test__ = False

    id: str
    name: str
    description: str
    module: str | None = None
    command_args: tuple[str, ...] = field(default_factory=tuple)
    category: str = "simulator"
    phases: tuple[str, ...] = field(default_factory=tuple)
    primary_fields: tuple[TelemetryField, ...] = field(default_factory=tuple)
    secondary_fields: tuple[str, ...] = field(default_factory=tuple)
    output_csv: str | None = None
    logs: tuple[str, ...] = field(default_factory=tuple)
    plot_groups: tuple[PlotGroup, ...] = field(default_factory=tuple)
    event_window: EventWindow | None = None
    validation_metric_ids: tuple[str, ...] = field(default_factory=tuple)
    requires_flightgear: bool = True
    enabled: bool = True

    def command(self, python_executable: Path) -> list[str]:
        if self.command_args:
            return [str(python_executable), *self.command_args]
        if not self.module:
            raise ValueError(f"Profile {self.id!r} has no module or command_args")
        return [str(python_executable), "-m", self.module]

    def csv_path(self, project_root: Path) -> Path | None:
        if not self.output_csv:
            return None
        return project_root / self.output_csv

    def log_paths(self, project_root: Path) -> list[Path]:
        return [project_root / log_path for log_path in self.logs]
