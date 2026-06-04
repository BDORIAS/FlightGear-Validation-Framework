"""Validation metrics computed from focused telemetry windows."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from .dataset import DatasetBundle


@dataclass(frozen=True)
class ValidationMetric:
    id: str
    label: str
    value: float | str | None
    unit: str = ""
    status: str = "info"
    details: str = ""


def compute_validation_metrics(bundle: DatasetBundle) -> list[dict[str, Any]]:
    """Compute profile-specific metrics for the viewer summary."""
    if bundle.profile.id == "cruise_engine_failure":
        return [asdict(metric) for metric in _cruise_engine_failure_metrics(bundle)]
    return [asdict(metric) for metric in _generic_metrics(bundle)]


def _cruise_engine_failure_metrics(bundle: DatasetBundle) -> list[ValidationMetric]:
    frame = bundle.focused_frame
    focus = bundle.focus_window
    failure = _failure_frame(frame)
    pre_failure = _pre_failure_frame(frame)
    metrics: list[ValidationMetric] = []

    metrics.append(_telemetry_completeness(frame))

    duration = _numeric_max(failure, "engine_failure_elapsed_s")
    metrics.append(
        ValidationMetric(
            id="failure_duration",
            label="Failure window duration",
            value=_round(duration),
            unit="s",
            status=_threshold_status(duration, pass_min=25.0, warn_min=10.0),
            details="Measured from engine_failure_elapsed_s inside the focused window.",
        )
    )

    rpm_before = _window_median(pre_failure, "engine_rpm")
    rpm_min = _numeric_min(failure, "engine_rpm")
    rpm_drop_pct = None
    if rpm_before is not None and rpm_before > 0 and rpm_min is not None:
        rpm_drop_pct = max(0.0, (rpm_before - rpm_min) / rpm_before * 100.0)
    metrics.append(
        ValidationMetric(
            id="rpm_decay",
            label="RPM decay",
            value=_round(rpm_drop_pct),
            unit="%",
            status=_threshold_status(rpm_drop_pct, pass_min=90.0, warn_min=60.0),
            details=(
                f"Median pre-failure RPM {rpm_before:.1f}, minimum failure RPM {rpm_min:.1f}."
                if rpm_before is not None and rpm_min is not None
                else "RPM data was not available."
            ),
        )
    )

    stop_time = _first_engine_stop_time(failure)
    metrics.append(
        ValidationMetric(
            id="engine_stop_time",
            label="Engine stop time",
            value=_round(stop_time),
            unit="s",
            status=_max_status(stop_time, pass_max=15.0, warn_max=25.0),
            details="First failure timestamp where engine_running is false or RPM is below 50.",
        )
    )

    mean_ias_error = _abs_mean(failure, "glide_airspeed_error_kts")
    max_ias_error = _abs_max(failure, "glide_airspeed_error_kts")
    metrics.append(
        ValidationMetric(
            id="glide_ias_error",
            label="Glide IAS error",
            value=_round(mean_ias_error),
            unit="kt mean abs",
            status=_max_status(mean_ias_error, pass_max=8.0, warn_max=14.0),
            details=(
                f"Maximum absolute IAS error {_round(max_ias_error)} kt."
                if max_ias_error is not None
                else "Glide IAS error was not available."
            ),
        )
    )

    mean_pitch_error = _abs_mean(failure, "glide_pitch_error_deg")
    max_pitch_error = _abs_max(failure, "glide_pitch_error_deg")
    metrics.append(
        ValidationMetric(
            id="glide_pitch_error",
            label="Glide pitch error",
            value=_round(mean_pitch_error),
            unit="deg mean abs",
            status=_max_status(mean_pitch_error, pass_max=4.0, warn_max=8.0),
            details=(
                f"Maximum absolute pitch error {_round(max_pitch_error)} deg."
                if max_pitch_error is not None
                else "Glide pitch error was not available."
            ),
        )
    )

    vsi_mean = _numeric_mean(failure, "vertical_speed_fpm")
    metrics.append(
        ValidationMetric(
            id="vertical_speed",
            label="Mean failure VSI",
            value=_round(vsi_mean),
            unit="fpm",
            status="info" if vsi_mean is not None else "warn",
            details="Average vertical speed during the failure/glide segment.",
        )
    )

    drift = _delta(failure, "runway_cross_track_m")
    metrics.append(
        ValidationMetric(
            id="cross_track_drift",
            label="Cross-track drift",
            value=_round(drift),
            unit="m",
            status=_max_status(abs(drift) if drift is not None else None, pass_max=250.0, warn_max=500.0),
            details="Difference between first and last cross-track value during the failure.",
        )
    )

    visible_duration = None
    if focus.start_elapsed_s is not None and focus.end_elapsed_s is not None:
        visible_duration = focus.end_elapsed_s - focus.start_elapsed_s
    metrics.append(
        ValidationMetric(
            id="visible_duration",
            label="Visible focused duration",
            value=_round(visible_duration),
            unit="s",
            status="info",
            details="Viewer window: pre-failure context plus failure duration.",
        )
    )

    return metrics


def _generic_metrics(bundle: DatasetBundle) -> list[ValidationMetric]:
    frame = bundle.focused_frame
    return [
        ValidationMetric(
            id="row_count",
            label="Focused rows",
            value=len(frame),
            status="info",
            details="Rows available to the viewer after applying any focus window.",
        ),
        _telemetry_completeness(frame),
    ]


def _failure_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if "engine_failure_elapsed_s" in frame.columns:
        failure = frame[pd.to_numeric(frame["engine_failure_elapsed_s"], errors="coerce").notna()]
        if not failure.empty:
            return failure
    if "phase" in frame.columns:
        failure = frame[frame["phase"].astype(str).str.contains("failure", case=False, na=False)]
        if not failure.empty:
            return failure
    return frame.iloc[0:0]


def _pre_failure_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if "event_time_s" in frame.columns:
        pre = frame[pd.to_numeric(frame["event_time_s"], errors="coerce") < 0]
        if not pre.empty:
            return pre
    if "engine_failure_elapsed_s" in frame.columns:
        pre = frame[pd.to_numeric(frame["engine_failure_elapsed_s"], errors="coerce").isna()]
        if not pre.empty:
            return pre
    return frame.iloc[0:0]


def _telemetry_completeness(frame: pd.DataFrame) -> ValidationMetric:
    if "telemetry_valid" not in frame.columns or frame.empty:
        return ValidationMetric(
            id="telemetry_completeness",
            label="Telemetry completeness",
            value=None,
            unit="%",
            status="warn",
            details="telemetry_valid is not available.",
        )
    values = frame["telemetry_valid"].map(_boolish)
    valid_count = values.sum()
    completeness = valid_count / len(values) * 100.0 if len(values) else None
    return ValidationMetric(
        id="telemetry_completeness",
        label="Telemetry completeness",
        value=_round(completeness),
        unit="%",
        status=_threshold_status(completeness, pass_min=95.0, warn_min=80.0),
        details=f"{int(valid_count)} of {len(values)} focused samples are marked valid.",
    )


def _first_engine_stop_time(frame: pd.DataFrame) -> float | None:
    if frame.empty:
        return None
    elapsed = _numeric_series(frame, "engine_failure_elapsed_s")
    if elapsed.empty:
        elapsed = _numeric_series(frame, "event_time_s")
    if elapsed.empty:
        return None

    stop_mask = pd.Series(False, index=frame.index)
    if "engine_running" in frame.columns:
        stop_mask |= frame["engine_running"].map(_boolish) == 0
    rpm = _numeric_series(frame, "engine_rpm")
    if not rpm.empty:
        stop_mask |= rpm.reindex(frame.index) < 50.0

    stopped = elapsed.reindex(frame.index)[stop_mask]
    stopped = stopped.dropna()
    if stopped.empty:
        return None
    return float(stopped.iloc[0])


def _boolish(value: Any) -> int:
    if value is True:
        return 1
    if value is False or value is None:
        return 0
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "on"}:
        return 1
    return 0


def _numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").dropna()


def _numeric_min(frame: pd.DataFrame, column: str) -> float | None:
    values = _numeric_series(frame, column)
    return None if values.empty else float(values.min())


def _numeric_max(frame: pd.DataFrame, column: str) -> float | None:
    values = _numeric_series(frame, column)
    return None if values.empty else float(values.max())


def _numeric_mean(frame: pd.DataFrame, column: str) -> float | None:
    values = _numeric_series(frame, column)
    return None if values.empty else float(values.mean())


def _window_median(frame: pd.DataFrame, column: str) -> float | None:
    values = _numeric_series(frame, column)
    return None if values.empty else float(values.median())


def _abs_mean(frame: pd.DataFrame, column: str) -> float | None:
    values = _numeric_series(frame, column)
    return None if values.empty else float(values.abs().mean())


def _abs_max(frame: pd.DataFrame, column: str) -> float | None:
    values = _numeric_series(frame, column)
    return None if values.empty else float(values.abs().max())


def _delta(frame: pd.DataFrame, column: str) -> float | None:
    values = _numeric_series(frame, column)
    if values.empty:
        return None
    return float(values.iloc[-1] - values.iloc[0])


def _threshold_status(value: float | None, *, pass_min: float, warn_min: float) -> str:
    if value is None:
        return "warn"
    if value >= pass_min:
        return "pass"
    if value >= warn_min:
        return "warn"
    return "fail"


def _max_status(value: float | None, *, pass_max: float, warn_max: float) -> str:
    if value is None:
        return "warn"
    if value <= pass_max:
        return "pass"
    if value <= warn_max:
        return "warn"
    return "fail"


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(float(value), digits)
