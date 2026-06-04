"""Load telemetry CSV files and convert them into viewer-ready payloads."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from pathlib import Path
from typing import Any

import pandas as pd

from flightgear_framework.console_app.profiles import PlotGroup, PlotSeries, TestProfile


@dataclass(frozen=True)
class FocusWindow:
    enabled: bool
    title: str
    x_key: str
    x_label: str
    start_elapsed_s: float | None = None
    end_elapsed_s: float | None = None
    event_start_elapsed_s: float | None = None
    pre_seconds: float | None = None
    post_seconds: float | None = None
    source: str = "full_dataset"


@dataclass(frozen=True)
class DatasetBundle:
    profile: TestProfile
    csv_path: Path
    full_frame: pd.DataFrame
    focused_frame: pd.DataFrame
    focus_window: FocusWindow
    numeric_columns: tuple[str, ...]
    boolean_columns: tuple[str, ...]
    categorical_columns: tuple[str, ...]


DEFAULT_EXCLUDED_PLOT_COLUMNS = {
    "timestamp",
    "phase",
    "phase_reason",
    "telemetry_missing_fields",
    "expected_rudder_sign",
    "glide_command_reason",
    "throttle_guard_reason",
    "runway_side",
}


def load_dataset(
    project_root: Path,
    profile: TestProfile,
    *,
    focus: bool = True,
) -> DatasetBundle:
    """Load a profile CSV and apply its configured focus window."""
    csv_path = profile.csv_path(project_root)
    if csv_path is None:
        raise ValueError(f"Profile {profile.id!r} does not define an output CSV")
    if not csv_path.is_file():
        raise FileNotFoundError(f"Telemetry CSV not found: {csv_path}")

    frame = pd.read_csv(csv_path)
    frame = _normalize_frame(frame)
    numeric_columns, boolean_columns, categorical_columns = _classify_columns(frame)
    focus_window = _build_focus_window(frame, profile, focus=focus)
    focused = _apply_focus_window(frame, focus_window)

    return DatasetBundle(
        profile=profile,
        csv_path=csv_path,
        full_frame=frame,
        focused_frame=focused,
        focus_window=focus_window,
        numeric_columns=tuple(numeric_columns),
        boolean_columns=tuple(boolean_columns),
        categorical_columns=tuple(categorical_columns),
    )


def build_payload(bundle: DatasetBundle) -> dict[str, Any]:
    """Serialize a dataset bundle for the browser viewer."""
    frame = bundle.focused_frame
    profile = bundle.profile
    groups = _serializable_plot_groups(profile.plot_groups, frame.columns)
    auto_group = _build_auto_numeric_group(bundle.numeric_columns)
    if auto_group["series"]:
        groups.append(auto_group)

    return {
        "profile": {
            "id": profile.id,
            "name": profile.name,
            "description": profile.description,
            "category": profile.category,
            "requires_flightgear": profile.requires_flightgear,
            "phases": list(profile.phases),
        },
        "csv": {
            "name": bundle.csv_path.name,
            "path": str(bundle.csv_path),
            "full_rows": int(len(bundle.full_frame)),
            "focused_rows": int(len(frame)),
        },
        "focus_window": asdict(bundle.focus_window),
        "columns": {
            "all": list(frame.columns),
            "numeric": [column for column in bundle.numeric_columns if column in frame.columns],
            "boolean": [column for column in bundle.boolean_columns if column in frame.columns],
            "categorical": [
                column for column in bundle.categorical_columns if column in frame.columns
            ],
        },
        "plot_groups": groups,
        "data": _frame_to_json_columns(frame),
    }


def _normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    if "timestamp" in frame.columns:
        parsed = pd.to_datetime(frame["timestamp"], errors="coerce")
        if parsed.notna().any():
            first_timestamp = parsed.dropna().iloc[0]
            frame["elapsed_s"] = (parsed - first_timestamp).dt.total_seconds()
        else:
            frame["elapsed_s"] = frame.index.astype(float)
    else:
        frame["elapsed_s"] = frame.index.astype(float)

    for column in frame.columns:
        if column in {"timestamp", "phase", "phase_reason", "telemetry_missing_fields"}:
            continue
        if frame[column].dtype == object:
            numeric = pd.to_numeric(frame[column], errors="coerce")
            non_empty_count = frame[column].notna().sum()
            numeric_count = numeric.notna().sum()
            if non_empty_count and numeric_count / non_empty_count >= 0.85:
                frame[column] = numeric

    return frame


def _classify_columns(frame: pd.DataFrame) -> tuple[list[str], list[str], list[str]]:
    numeric_columns: list[str] = []
    boolean_columns: list[str] = []
    categorical_columns: list[str] = []

    for column in frame.columns:
        series = frame[column].dropna()
        if column == "elapsed_s":
            numeric_columns.append(column)
            continue
        if series.empty:
            categorical_columns.append(column)
            continue
        if pd.api.types.is_bool_dtype(series):
            boolean_columns.append(column)
            numeric_columns.append(column)
            continue
        unique_values = set(str(value).lower() for value in series.unique())
        if unique_values <= {"true", "false"}:
            boolean_columns.append(column)
            numeric_columns.append(column)
            continue
        if pd.api.types.is_numeric_dtype(series):
            numeric_columns.append(column)
        else:
            categorical_columns.append(column)

    return numeric_columns, boolean_columns, categorical_columns


def _build_focus_window(frame: pd.DataFrame, profile: TestProfile, *, focus: bool) -> FocusWindow:
    event_window = profile.event_window
    if not focus or event_window is None or frame.empty:
        return FocusWindow(
            enabled=False,
            title="Full dataset",
            x_key="elapsed_s",
            x_label="Elapsed time (s)",
        )

    event_start = _event_start_from_counter(frame, event_window.trigger_field)
    source = event_window.trigger_field
    if event_start is None and event_window.phase_values:
        event_start = _event_start_from_phase(frame, event_window.phase_values)
        source = "phase"

    if event_start is None:
        return FocusWindow(
            enabled=False,
            title="Full dataset",
            x_key="elapsed_s",
            x_label="Elapsed time (s)",
            source="event_not_found",
        )

    data_min = _safe_float(frame["elapsed_s"].min())
    data_max = _safe_float(frame["elapsed_s"].max())
    post_seconds = (
        event_window.post_seconds
        if event_window.post_seconds is not None
        else _duration_from_counter(frame, event_window.trigger_field)
    )
    if post_seconds is None:
        post_seconds = event_window.fallback_post_seconds

    start = max(data_min, event_start - event_window.pre_seconds)
    end = min(data_max, event_start + post_seconds)
    frame["event_time_s"] = frame["elapsed_s"] - event_start

    return FocusWindow(
        enabled=True,
        title=event_window.title,
        x_key="event_time_s",
        x_label="Time from failure start (s)",
        start_elapsed_s=start,
        end_elapsed_s=end,
        event_start_elapsed_s=event_start,
        pre_seconds=event_window.pre_seconds,
        post_seconds=post_seconds,
        source=source,
    )


def _event_start_from_counter(frame: pd.DataFrame, trigger_field: str) -> float | None:
    if trigger_field not in frame.columns or "elapsed_s" not in frame.columns:
        return None
    counter = pd.to_numeric(frame[trigger_field], errors="coerce")
    valid = counter.dropna()
    if valid.empty:
        return None
    candidates = frame.loc[valid.index, "elapsed_s"] - valid
    candidates = candidates.dropna()
    if candidates.empty:
        return None
    return _safe_float(candidates.median())


def _duration_from_counter(frame: pd.DataFrame, trigger_field: str) -> float | None:
    if trigger_field not in frame.columns:
        return None
    values = pd.to_numeric(frame[trigger_field], errors="coerce").dropna()
    if values.empty:
        return None
    return _safe_float(values.max())


def _event_start_from_phase(frame: pd.DataFrame, phase_values: tuple[str, ...]) -> float | None:
    if "phase" not in frame.columns:
        return None
    mask = frame["phase"].isin(phase_values)
    if not mask.any():
        return None
    return _safe_float(frame.loc[mask, "elapsed_s"].iloc[0])


def _apply_focus_window(frame: pd.DataFrame, window: FocusWindow) -> pd.DataFrame:
    if not window.enabled or window.start_elapsed_s is None or window.end_elapsed_s is None:
        return frame.copy()
    mask = (
        (frame["elapsed_s"] >= window.start_elapsed_s)
        & (frame["elapsed_s"] <= window.end_elapsed_s)
    )
    focused = frame.loc[mask].copy()
    if focused.empty:
        return frame.copy()
    return focused


def _serializable_plot_groups(
    groups: tuple[PlotGroup, ...],
    available_columns: pd.Index,
) -> list[dict[str, Any]]:
    payload_groups: list[dict[str, Any]] = []
    for group in groups:
        series = [
            {
                "key": item.key,
                "label": item.display_label,
                "unit": item.unit,
                "kind": item.kind,
            }
            for item in group.series
            if item.key in available_columns
        ]
        if not series:
            continue
        payload_groups.append(
            {
                "id": group.id,
                "title": group.title,
                "description": group.description,
                "series": series,
            }
        )
    return payload_groups


def _build_auto_numeric_group(numeric_columns: tuple[str, ...]) -> dict[str, Any]:
    series = [
        {
            "key": column,
            "label": column,
            "unit": "",
            "kind": "line",
        }
        for column in numeric_columns
        if column not in DEFAULT_EXCLUDED_PLOT_COLUMNS and column != "elapsed_s"
    ]
    return {
        "id": "all_numeric",
        "title": "All Numeric Variables",
        "description": "Every numeric signal available in the focused telemetry window.",
        "series": series,
    }


def _frame_to_json_columns(frame: pd.DataFrame) -> dict[str, list[Any]]:
    clean = frame.copy()
    for column in clean.columns:
        if pd.api.types.is_bool_dtype(clean[column]):
            clean[column] = clean[column].map(lambda value: bool(value) if pd.notna(value) else None)
    clean = clean.astype(object).where(pd.notna(clean), None)
    return {
        column: [_json_safe_value(value) for value in clean[column].tolist()]
        for column in clean.columns
    }


def _json_safe_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, str)):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if hasattr(value, "item"):
        return _json_safe_value(value.item())
    return str(value)


def _safe_float(value: Any) -> float:
    numeric = float(value)
    if math.isnan(numeric) or math.isinf(numeric):
        raise ValueError(f"Invalid numeric value: {value!r}")
    return numeric
