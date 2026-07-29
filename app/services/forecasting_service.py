from __future__ import annotations

import hashlib
import json
import math
from calendar import monthrange
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from statistics import fmean, median
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.engines.forecasting_engine import (
    ForecastingMethodError,
    ForecastingMethodRegistry,
    default_forecasting_method_registry,
)
from app.models.forecasting import (
    ForecastAccuracyResult,
    ForecastActual,
    ForecastBacktest,
    ForecastCandidate,
    ForecastExecution,
    ForecastExecutionStatus,
    ForecastExecutionStep,
    ForecastMetric,
    ForecastPoint,
    ForecastRevision,
    ForecastScenario,
)
from app.models.oikb import OIKBDefinition, OIKBDefinitionVersion
from app.models.trust import (
    AnalyticalLevel,
    AnalyticalReadinessDecision,
    ReadinessStatus,
    TrustAssessment,
    TrustAssessmentStatus,
)
from app.schemas.forecasting import (
    ForecastActualCreate,
    ForecastEvaluateRequest,
    ForecastEvaluationRead,
    ForecastExecutionCreate,
    ForecastRevisionCreate,
    ForecastScenarioCreate,
)


class ForecastingServiceError(ValueError):
    def __init__(self, code: str, message: str, http_status: int = 422) -> None:
        self.code = code
        self.http_status = http_status
        super().__init__(message)


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _metrics(
    actuals: list[float], forecasts: list[float], scale: float | None = None
) -> dict[str, float | None]:
    if len(actuals) != len(forecasts) or not actuals:
        raise ForecastingServiceError("INVALID_METRIC_INPUT", "Metrics require aligned values")
    errors = [forecast - actual for actual, forecast in zip(actuals, forecasts, strict=True)]
    absolute = [abs(value) for value in errors]
    mae = fmean(absolute)
    denominator = sum(abs(value) for value in actuals)
    smape_terms = [
        2 * abs(error) / (abs(actual) + abs(forecast))
        for actual, forecast, error in zip(actuals, forecasts, errors, strict=True)
        if abs(actual) + abs(forecast) > 1e-12
    ]
    mape_terms = [
        abs(error / actual)
        for actual, error in zip(actuals, errors, strict=True)
        if abs(actual) > 1e-12
    ]
    return {
        "MAE": mae,
        "MEDIAN_ABSOLUTE_ERROR": float(median(absolute)),
        "RMSE": math.sqrt(fmean([value**2 for value in errors])),
        "MAPE": fmean(mape_terms) * 100 if len(mape_terms) == len(actuals) else None,
        "SMAPE": fmean(smape_terms) * 100 if smape_terms else None,
        "WAPE": sum(absolute) / denominator * 100 if denominator > 1e-12 else None,
        "MASE": mae / scale if scale is not None and scale > 1e-12 else None,
        "MEAN_ERROR": fmean(errors),
        "BIAS_PERCENTAGE": sum(errors) / denominator * 100 if denominator > 1e-12 else None,
    }


@dataclass(frozen=True)
class PreparedSeries:
    timestamps: list[datetime]
    values: list[float]
    fingerprint: str
    imputed_count: int
    partial_count: int
    late_count: int
    warnings: list[str]


class TimeSeriesPreparationService:
    def prepare(self, payload: ForecastExecutionCreate) -> PreparedSeries:
        ordered = sorted(payload.observations, key=lambda item: item.timestamp)
        original_timestamps = [item.timestamp for item in ordered]
        if len(set(original_timestamps)) != len(original_timestamps) or any(
            item.status.value == "duplicate" for item in ordered
        ):
            raise ForecastingServiceError("INVALID_TIME_SERIES", "Duplicate periods are blocked")
        partial = [item for item in ordered if item.status.value == "partial"]
        if partial and payload.partial_period_policy == "REQUIRE_MANUAL_APPROVAL":
            raise ForecastingServiceError("NOT_READY", "Partial periods require approval")
        if payload.partial_period_policy == "EXCLUDE":
            ordered = [item for item in ordered if item.status.value != "partial"]
        timestamps = [item.timestamp for item in ordered]
        missing = [
            index
            for index, item in enumerate(ordered)
            if item.value is None or item.status.value == "missing"
        ]
        if missing and payload.missing_period_policy == "BLOCK":
            raise ForecastingServiceError("INVALID_TIME_SERIES", "Missing periods are blocked")
        values: list[float] = []
        imputed = 0
        available = [float(item.value) for item in ordered if item.value is not None]
        for index, item in enumerate(ordered):
            if item.value is not None:
                values.append(float(item.value))
                continue
            imputed += 1
            if payload.missing_period_policy == "ZERO_FILL":
                values.append(0.0)
            elif payload.missing_period_policy == "FORWARD_FILL" and values:
                values.append(values[-1])
            elif payload.missing_period_policy == "HISTORICAL_MEDIAN_FILL" and available:
                values.append(float(median(available)))
            elif payload.missing_period_policy == "LINEAR_INTERPOLATION" and values:
                future = next(
                    (
                        float(candidate.value)
                        for candidate in ordered[index + 1 :]
                        if candidate.value is not None
                    ),
                    values[-1],
                )
                values.append((values[-1] + future) / 2)
            else:
                raise ForecastingServiceError(
                    "INVALID_TIME_SERIES", "Configured imputation cannot resolve the gap"
                )
        if imputed / max(len(ordered), 1) * 100 > payload.maximum_imputed_percentage:
            raise ForecastingServiceError("NOT_READY", "Imputation threshold exceeded")
        if payload.outlier_policy == "EXCLUDE_CONFIRMED_ERROR":
            retained = [
                (timestamp, value)
                for timestamp, value, item in zip(timestamps, values, ordered, strict=True)
                if not item.confirmed_data_error
            ]
            timestamps = [item[0] for item in retained]
            values = [item[1] for item in retained]
        if any(not math.isfinite(value) for value in values):
            raise ForecastingServiceError("INVALID_TIME_SERIES", "Non-finite values are blocked")
        return PreparedSeries(
            timestamps=timestamps,
            values=values,
            fingerprint=_hash(
                {
                    "periods": [item.isoformat() for item in timestamps],
                    "values": values,
                    "policies": [
                        payload.missing_period_policy,
                        payload.partial_period_policy,
                        payload.outlier_policy,
                    ],
                }
            ),
            imputed_count=imputed,
            partial_count=len(partial),
            late_count=sum(item.status.value == "late" for item in ordered),
            warnings=["Imputed periods are excluded from accuracy evaluation"] if imputed else [],
        )


class ForecastReadinessService:
    def assess(
        self,
        series: PreparedSeries,
        payload: ForecastExecutionCreate,
        registry: ForecastingMethodRegistry,
    ) -> dict[str, object]:
        eligible: list[str] = []
        ineligible: dict[str, str] = {}
        season_value = payload.parameters.get("seasonal_period", 12)
        if not isinstance(season_value, (int, float, str)):
            raise ForecastingServiceError("INVALID_SEASONAL_PERIOD", "Seasonal period is invalid")
        season = int(season_value)
        for code in payload.candidate_methods:
            try:
                method = registry.get(code)
            except ForecastingMethodError:
                ineligible[code] = "UNSUPPORTED"
                continue
            if not method.metadata.supported:
                ineligible[code] = "UNSUPPORTED"
            elif len(series.values) < method.metadata.minimum_history:
                ineligible[code] = "INSUFFICIENT_HISTORY"
            elif method.metadata.supports_seasonality and len(series.values) < season * 2:
                ineligible[code] = "INSUFFICIENT_SEASONAL_CYCLES"
            else:
                eligible.append(code)
        status = "ready" if eligible else "insufficient_data"
        return {
            "readiness_status": status,
            "readiness_score": round(len(eligible) / len(payload.candidate_methods) * 100, 2),
            "eligible_methods": eligible,
            "ineligible_methods": ineligible,
            "blocking_reasons": [] if eligible else sorted(set(ineligible.values())),
            "warnings": series.warnings,
            "minimum_history_required": min(
                (registry.get(code).metadata.minimum_history for code in eligible), default=0
            ),
            "available_history": len(series.values),
            "seasonal_cycles_available": len(series.values) // max(season, 1),
            "missing_period_rate": series.imputed_count / max(len(series.values), 1),
            "partial_period_count": series.partial_count,
            "late_period_count": series.late_count,
            "unit_status": "stable",
            "currency_status": "stable",
            "grain_status": "stable",
        }


class ForecastReconciliationService:
    def reconcile(
        self,
        child_forecasts: dict[str, float],
        *,
        method: str,
        parent_forecast: float | None = None,
    ) -> dict[str, object]:
        if not child_forecasts or any(
            not math.isfinite(value) for value in child_forecasts.values()
        ):
            raise ForecastingServiceError(
                "INVALID_RECONCILIATION", "Finite child forecasts are required"
            )
        if method == "BOTTOM_UP":
            total = sum(child_forecasts.values())
            return {
                "method": method,
                "parent_forecast": total,
                "children": dict(sorted(child_forecasts.items())),
                "residual": 0.0,
            }
        if method == "TOP_DOWN_PROPORTIONAL":
            if parent_forecast is None or not math.isfinite(parent_forecast):
                raise ForecastingServiceError(
                    "INVALID_RECONCILIATION", "Finite parent forecast is required"
                )
            base = sum(child_forecasts.values())
            if abs(base) <= 1e-12:
                raise ForecastingServiceError(
                    "INVALID_RECONCILIATION", "Historical proportions are undefined"
                )
            children = {
                code: parent_forecast * value / base
                for code, value in sorted(child_forecasts.items())
            }
            return {
                "method": method,
                "parent_forecast": parent_forecast,
                "children": children,
                "residual": parent_forecast - sum(children.values()),
            }
        raise ForecastingServiceError("UNSUPPORTED", "Reconciliation method is unsupported")


class ForecastExecutionService:
    engine_version = "1.0"
    interval_method_code = "ROLLING_ORIGIN_ABSOLUTE_RESIDUAL_QUANTILE"
    interval_method_version = "2.0"
    minimum_interval_calibration_size = 3

    def __init__(self, registry: ForecastingMethodRegistry | None = None) -> None:
        self.registry = registry or default_forecasting_method_registry()
        self.preparation = TimeSeriesPreparationService()
        self.readiness = ForecastReadinessService()

    def evaluate(self, payload: ForecastEvaluateRequest) -> ForecastEvaluationRead:
        try:
            method = self.registry.get(payload.method_code, payload.method_version)
            result = method.forecast(payload.values, payload.horizon, payload.parameters)
            calibration_residuals = self._one_step_ahead_residuals(
                method, payload.values, payload.parameters
            )
            intervals = self._intervals(result.values, calibration_residuals, 0.8)
            interval_status = (
                "available"
                if len(calibration_residuals) >= self.minimum_interval_calibration_size
                else "insufficient_data"
            )
            return ForecastEvaluationRead(
                status="succeeded",
                method_code=method.metadata.method_code,
                method_version=method.metadata.method_version,
                values=result.values,
                intervals=intervals,
                diagnostics={
                    **result.diagnostics,
                    "interval_method": self.interval_method_code,
                    "interval_method_version": self.interval_method_version,
                    "interval_calibration_size": len(calibration_residuals),
                    "interval_status": interval_status,
                },
            )
        except ForecastingMethodError as exc:
            return ForecastEvaluationRead(
                status="unsupported" if str(exc).startswith("UNSUPPORTED") else "failed",
                method_code=payload.method_code,
                method_version=payload.method_version,
                values=[],
                intervals=[],
                diagnostics={},
                error_code=str(exc),
            )

    def execute(
        self, db: Session, organization_id: UUID, payload: ForecastExecutionCreate, actor: UUID
    ) -> ForecastExecution:
        definition, version = self._governance(db, organization_id, payload)
        self._trust(db, organization_id, payload)
        prepared = self.preparation.prepare(payload)
        readiness = self.readiness.assess(prepared, payload, self.registry)
        if readiness["readiness_status"] != "ready":
            raise ForecastingServiceError("NOT_READY", "No eligible forecast method")
        fingerprint = _hash(
            {
                "organization": organization_id,
                "trust_assessment": payload.trust_assessment_id,
                "readiness_assessment": payload.readiness_assessment_id,
                "orchestration_request": payload.orchestration_request_id,
                "dataset_reference": payload.dataset_reference,
                "dataset": payload.dataset_fingerprint,
                "source_lineage_reference": payload.source_lineage_reference,
                "prepared": prepared.fingerprint,
                "definition": version.fingerprint,
                "target_code": payload.target_code,
                "source_time_grain": payload.source_time_grain,
                "forecast_time_grain": payload.forecast_time_grain,
                "methods": payload.candidate_methods,
                "horizon": payload.forecast_horizon,
                "interval_level": payload.interval_level,
                "backtest_type": payload.backtest_type,
                "backtest_folds": payload.backtest_folds,
                "parameters": payload.parameters,
                "engine": self.engine_version,
            }
        )
        existing = db.scalar(
            select(ForecastExecution).where(
                ForecastExecution.organization_id == organization_id,
                ForecastExecution.reproducibility_fingerprint == fingerprint,
            )
        )
        if existing is not None:
            return existing
        now = datetime.now(UTC)
        forecast_start = self._advance_period(
            prepared.timestamps[-1], payload.forecast_time_grain, 1
        )
        forecast_end = self._advance_period(
            prepared.timestamps[-1], payload.forecast_time_grain, payload.forecast_horizon
        )
        execution = ForecastExecution(
            organization_id=organization_id,
            orchestration_request_id=payload.orchestration_request_id,
            oikb_definition_id=definition.id,
            oikb_definition_version_id=version.id,
            trust_assessment_id=payload.trust_assessment_id,
            readiness_assessment_id=payload.readiness_assessment_id,
            execution_package_fingerprint=version.fingerprint,
            reproducibility_fingerprint=fingerprint,
            target_code=payload.target_code,
            target_unit=payload.observations[0].unit,
            currency_code=payload.observations[0].currency_code,
            source_time_grain=payload.source_time_grain,
            forecast_time_grain=payload.forecast_time_grain,
            status=ForecastExecutionStatus.RUNNING.value,
            requested_by=actor,
            started_at=now,
            dataset_reference=payload.dataset_reference,
            dataset_fingerprint=payload.dataset_fingerprint,
            prepared_series_fingerprint=prepared.fingerprint,
            source_lineage_reference=payload.source_lineage_reference,
            training_window_start=prepared.timestamps[0],
            training_window_end=prepared.timestamps[-1],
            forecast_start=forecast_start,
            forecast_end=forecast_end,
            forecast_horizon=payload.forecast_horizon,
            engine_version=self.engine_version,
            correlation_id=payload.correlation_id,
            readiness_snapshot=readiness,
            explanation={},
            warnings=prepared.warnings,
            limitations=[
                "Forecast intervals are calibrated from rolling-origin one-step-ahead errors "
                "and are not guaranteed outcomes.",
                "Custom fiscal calendars and deep hierarchy reconciliation are deferred.",
            ],
        )
        db.add(execution)
        db.flush()
        candidate_rows: list[ForecastCandidate] = []
        results: dict[str, tuple[list[float], list[float], dict[str, float | None]]] = {}
        for code in payload.candidate_methods:
            method = self.registry.get(code)
            eligible = code in cast(list[str], readiness["eligible_methods"])
            row = ForecastCandidate(
                forecast_execution_id=execution.id,
                method_code=code,
                method_version=method.metadata.method_version,
                parameter_snapshot=payload.parameters,
                status="eligible" if eligible else "rejected",
                eligible=eligible,
                rejection_reason=(
                    None
                    if eligible
                    else str(cast(dict[str, str], readiness["ineligible_methods"]).get(code))
                ),
                primary_metric_code=payload.primary_metric,
                primary_metric_value=None,
                secondary_metrics={},
                complexity_rank=method.metadata.complexity_rank,
                selected=False,
            )
            db.add(row)
            db.flush()
            candidate_rows.append(row)
            if not eligible:
                continue
            actuals, forecasts = self._backtest(db, execution, row, method, prepared, payload)
            metric_values = _metrics(
                actuals,
                forecasts,
                fmean(
                    [
                        abs(right - left)
                        for left, right in zip(prepared.values, prepared.values[1:], strict=False)
                    ]
                )
                if len(prepared.values) > 1
                else None,
            )
            primary = metric_values.get(payload.primary_metric)
            row.primary_metric_value = primary
            row.secondary_metrics = cast(dict[str, object], metric_values)
            row.bias_value = metric_values["BIAS_PERCENTAGE"]
            final = method.forecast(prepared.values, payload.forecast_horizon, payload.parameters)
            calibration_residuals = [
                forecast - actual for actual, forecast in zip(actuals, forecasts, strict=True)
            ]
            results[code] = (final.values, calibration_residuals, metric_values)
            for metric_code, value in metric_values.items():
                db.add(
                    ForecastMetric(
                        forecast_execution_id=execution.id,
                        forecast_candidate_id=row.id,
                        metric_code=metric_code,
                        metric_value=value,
                        valid=value is not None,
                        invalid_reason=None if value is not None else "MATHEMATICALLY_UNDEFINED",
                    )
                )
        eligible_rows = [
            row for row in candidate_rows if row.eligible and row.primary_metric_value is not None
        ]
        if not eligible_rows:
            execution.status = ForecastExecutionStatus.MODEL_SELECTION_FAILED.value
            execution.failure_code = "MODEL_SELECTION_FAILED"
            db.commit()
            return execution
        eligible_rows.sort(
            key=lambda row: (
                float(row.primary_metric_value or 0),
                row.complexity_rank,
                row.method_code,
            )
        )
        best_score = float(eligible_rows[0].primary_metric_value or 0)
        adequate = [
            row
            for row in eligible_rows
            if float(row.primary_metric_value or 0) <= best_score * 1.05 + 1e-12
        ]
        selected = min(adequate, key=lambda row: (row.complexity_rank, row.method_code))
        for rank, row in enumerate(eligible_rows, 1):
            row.selection_rank = rank
            row.selected = row.id == selected.id
            row.selection_rationale = (
                "Simplest method within 5% of best governed score"
                if row.selected
                else "Higher error or complexity than selected method"
            )
        forecasts, residuals, selected_metrics = results[selected.method_code]
        intervals = self._intervals(forecasts, residuals, payload.interval_level)
        interval_status = (
            "available"
            if len(residuals) >= self.minimum_interval_calibration_size
            else "insufficient_data"
        )
        for step, (forecast, bounds) in enumerate(zip(forecasts, intervals, strict=True), 1):
            start = self._advance_period(prepared.timestamps[-1], payload.forecast_time_grain, step)
            end = self._advance_period(
                prepared.timestamps[-1], payload.forecast_time_grain, step + 1
            )
            db.add(
                ForecastPoint(
                    organization_id=organization_id,
                    forecast_execution_id=execution.id,
                    scenario_code="BASE",
                    forecast_period_start=start,
                    forecast_period_end=end,
                    horizon_step=step,
                    point_forecast=forecast,
                    lower_bound=bounds["lower_bound"],
                    upper_bound=bounds["upper_bound"],
                    interval_level=payload.interval_level,
                    output_unit=execution.target_unit,
                    currency_code=execution.currency_code,
                    is_partial_period=False,
                    assumptions=["Historical operating relationships remain broadly stable."],
                )
            )
        execution.selected_method_code = selected.method_code
        execution.selected_method_version = selected.method_version
        execution.status = ForecastExecutionStatus.SUCCEEDED.value
        execution.completed_at = datetime.now(UTC)
        execution.explanation = {
            "forecast_target": payload.target_code,
            "forecast_grain": payload.forecast_time_grain,
            "training_window": [
                prepared.timestamps[0].isoformat(),
                prepared.timestamps[-1].isoformat(),
            ],
            "history_periods": len(prepared.values),
            "forecast_horizon": payload.forecast_horizon,
            "selected_method": selected.method_code,
            "candidate_methods": payload.candidate_methods,
            "selection_rationale": selected.selection_rationale,
            "naive_benchmark": next(
                (row.secondary_metrics for row in candidate_rows if row.method_code == "NAIVE"),
                None,
            ),
            "primary_error_metric": payload.primary_metric,
            "primary_error_value": selected_metrics.get(payload.primary_metric),
            "bias": selected_metrics.get("BIAS_PERCENTAGE"),
            "interval_method": self.interval_method_code,
            "interval_method_version": self.interval_method_version,
            "interval_level": payload.interval_level,
            "interval_calibration_size": len(residuals),
            "interval_status": interval_status,
            "missing_period_policy": payload.missing_period_policy,
            "partial_period_policy": payload.partial_period_policy,
            "outlier_policy": payload.outlier_policy,
            "known_limitations": execution.limitations,
            "recommended_business_use": "Planning support with human review.",
            "recommended_verification": "Compare with actuals and operational constraints.",
        }
        self._step(db, execution.id, 1, "FORECAST_PIPELINE", "succeeded", readiness)
        db.commit()
        db.refresh(execution)
        return execution

    def get(self, db: Session, organization_id: UUID, execution_id: UUID) -> ForecastExecution:
        row = db.scalar(
            select(ForecastExecution).where(
                ForecastExecution.id == execution_id,
                ForecastExecution.organization_id == organization_id,
            )
        )
        if row is None:
            raise ForecastingServiceError("NOT_FOUND", "Forecast execution not found", 404)
        return row

    def list_executions(
        self, db: Session, organization_id: UUID, page: int, page_size: int
    ) -> tuple[list[ForecastExecution], int]:
        where = ForecastExecution.organization_id == organization_id
        total = db.scalar(select(func.count()).select_from(ForecastExecution).where(where)) or 0
        items = list(
            db.scalars(
                select(ForecastExecution)
                .where(where)
                .order_by(ForecastExecution.created_at.desc(), ForecastExecution.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return items, total

    def children(
        self, db: Session, organization_id: UUID, execution_id: UUID, model: Any
    ) -> list[object]:
        self.get(db, organization_id, execution_id)
        return list(
            db.scalars(
                select(model)
                .where(model.forecast_execution_id == execution_id)
                .order_by(getattr(model, "created_at", model.id), model.id)
            )
        )

    def create_scenario(
        self,
        db: Session,
        organization_id: UUID,
        execution_id: UUID,
        payload: ForecastScenarioCreate,
        actor: UUID,
    ) -> ForecastScenario:
        self.get(db, organization_id, execution_id)
        if payload.effective_to <= payload.effective_from:
            raise ForecastingServiceError("INVALID_SCENARIO", "Scenario end must follow start")
        scenario = ForecastScenario(
            organization_id=organization_id,
            forecast_execution_id=execution_id,
            scenario_code=payload.scenario_code,
            name=payload.name,
            description=payload.description,
            adjustment_type=payload.adjustment_type,
            adjustment_parameters={"amount": payload.adjustment_amount},
            effective_from=payload.effective_from,
            effective_to=payload.effective_to,
            created_by=actor,
        )
        db.add(scenario)
        db.flush()
        baseline = cast(
            list[ForecastPoint],
            self.children(db, organization_id, execution_id, ForecastPoint),
        )
        for point in baseline:
            if point.scenario_code != "BASE":
                continue
            value = float(point.point_forecast)
            adjusted = (
                value * (1 + payload.adjustment_amount / 100)
                if payload.adjustment_type == "PERCENTAGE"
                else value + payload.adjustment_amount
            )
            db.add(
                ForecastPoint(
                    organization_id=organization_id,
                    forecast_execution_id=execution_id,
                    entity_reference=point.entity_reference,
                    scenario_code=payload.scenario_code,
                    forecast_period_start=point.forecast_period_start,
                    forecast_period_end=point.forecast_period_end,
                    horizon_step=point.horizon_step,
                    point_forecast=adjusted,
                    lower_bound=None,
                    upper_bound=None,
                    output_unit=point.output_unit,
                    currency_code=point.currency_code,
                    is_partial_period=False,
                    assumptions=[payload.description],
                )
            )
        db.commit()
        db.refresh(scenario)
        return scenario

    def register_actual(
        self, db: Session, organization_id: UUID, point_id: UUID, payload: ForecastActualCreate
    ) -> ForecastActual:
        point = db.scalar(
            select(ForecastPoint).where(
                ForecastPoint.id == point_id, ForecastPoint.organization_id == organization_id
            )
        )
        if point is None:
            raise ForecastingServiceError("NOT_FOUND", "Forecast point not found", 404)
        now = datetime.now(UTC)
        actual = db.scalar(
            select(ForecastActual).where(
                ForecastActual.organization_id == organization_id,
                ForecastActual.forecast_point_id == point_id,
            )
        )
        status = "actual_revised" if actual else "evaluated"
        if actual is None:
            actual = ForecastActual(
                organization_id=organization_id,
                forecast_point_id=point_id,
                actual_reference=payload.actual_reference,
                actual_value=payload.actual_value,
                actual_status=status,
                actual_period_start=point.forecast_period_start,
                actual_period_end=point.forecast_period_end,
                actual_dataset_fingerprint=payload.actual_dataset_fingerprint,
                evaluated_at=now,
            )
            db.add(actual)
        else:
            actual.actual_reference = payload.actual_reference
            actual.actual_value = payload.actual_value
            actual.actual_status = status
            actual.actual_dataset_fingerprint = payload.actual_dataset_fingerprint
            actual.evaluated_at = now
        error = payload.actual_value - float(point.point_forecast)
        db.add(
            ForecastAccuracyResult(
                organization_id=organization_id,
                forecast_execution_id=point.forecast_execution_id,
                forecast_point_id=point.id,
                metric_code="ABSOLUTE_ERROR",
                metric_value=abs(error),
                horizon_step=point.horizon_step,
                entity_reference=point.entity_reference,
                evaluation_status=status,
                evaluated_at=now,
            )
        )
        db.commit()
        db.refresh(actual)
        return actual

    def revise(
        self,
        db: Session,
        organization_id: UUID,
        execution_id: UUID,
        payload: ForecastRevisionCreate,
        actor: UUID,
    ) -> ForecastRevision:
        prior = self.get(db, organization_id, execution_id)
        revised = self.get(db, organization_id, payload.revised_execution_id)
        prior_total = sum(
            float(point.point_forecast) for point in prior.points if point.scenario_code == "BASE"
        )
        revised_total = sum(
            float(point.point_forecast) for point in revised.points if point.scenario_code == "BASE"
        )
        delta = revised_total - prior_total
        row = ForecastRevision(
            organization_id=organization_id,
            prior_forecast_execution_id=prior.id,
            revised_forecast_execution_id=revised.id,
            revision_reason=payload.revision_reason,
            revision_type=payload.revision_type,
            absolute_revision=delta,
            percentage_revision=delta / prior_total * 100 if abs(prior_total) > 1e-12 else None,
            method_changed=prior.selected_method_code != revised.selected_method_code,
            parameters_changed=False,
            data_changed=prior.dataset_fingerprint != revised.dataset_fingerprint,
            readiness_changed=prior.readiness_assessment_id != revised.readiness_assessment_id,
            scenario_changed=False,
            created_by=actor,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @classmethod
    def _intervals(
        cls, values: list[float], residuals: list[float], level: float
    ) -> list[dict[str, float | None]]:
        if len(residuals) < cls.minimum_interval_calibration_size:
            return [
                {"lower_bound": None, "upper_bound": None, "interval_level": None} for _ in values
            ]
        ordered = sorted(abs(value) for value in residuals)
        width = ordered[min(len(ordered) - 1, max(0, math.ceil(level * len(ordered)) - 1))]
        return [
            {"lower_bound": value - width, "upper_bound": value + width, "interval_level": level}
            for value in values
        ]

    @staticmethod
    def _advance_period(value: datetime, grain: str, steps: int) -> datetime:
        if steps < 0:
            raise ForecastingServiceError("INVALID_TIME_GRAIN", "Period steps cannot be negative")
        fixed = {
            "HOURLY": timedelta(hours=1),
            "DAILY": timedelta(days=1),
            "WEEKLY": timedelta(days=7),
        }
        if grain in fixed:
            return value + fixed[grain] * steps
        months_per_step = {"MONTHLY": 1, "QUARTERLY": 3, "ANNUAL": 12}.get(grain)
        if months_per_step is None:
            raise ForecastingServiceError(
                "INVALID_TIME_GRAIN", f"Unsupported forecast time grain: {grain}"
            )
        month_index = value.year * 12 + value.month - 1 + months_per_step * steps
        year, zero_based_month = divmod(month_index, 12)
        month = zero_based_month + 1
        day = min(value.day, monthrange(year, month)[1])
        return value.replace(year=year, month=month, day=day)

    def _one_step_ahead_residuals(
        self, method: Any, values: list[float], parameters: dict[str, object]
    ) -> list[float]:
        residuals: list[float] = []
        for split in range(method.metadata.minimum_history, len(values)):
            result = method.forecast(values[:split], 1, parameters)
            residuals.append(result.values[0] - values[split])
        return residuals

    def _backtest(
        self,
        db: Session,
        execution: ForecastExecution,
        candidate: ForecastCandidate,
        method: Any,
        series: PreparedSeries,
        payload: ForecastExecutionCreate,
    ) -> tuple[list[float], list[float]]:
        minimum = method.metadata.minimum_history
        folds = min(payload.backtest_folds, len(series.values) - minimum)
        if folds < 1:
            raise ForecastingServiceError("BACKTEST_FAILED", "Insufficient backtest folds")
        actuals: list[float] = []
        forecasts: list[float] = []
        for fold in range(folds):
            split = len(series.values) - folds + fold
            training = series.values[:split]
            result = method.forecast(training, 1, payload.parameters)
            actual, forecast = series.values[split], result.values[0]
            actuals.append(actual)
            forecasts.append(forecast)
            db.add(
                ForecastBacktest(
                    forecast_execution_id=execution.id,
                    forecast_candidate_id=candidate.id,
                    backtest_type=payload.backtest_type,
                    fold_number=fold + 1,
                    train_start=series.timestamps[0],
                    train_end=series.timestamps[split - 1],
                    forecast_origin=series.timestamps[split - 1],
                    forecast_period=series.timestamps[split],
                    horizon_step=1,
                    actual_value=actual,
                    forecast_value=forecast,
                    error_value=forecast - actual,
                    absolute_error=abs(forecast - actual),
                    percentage_error=(forecast - actual) / actual * 100
                    if abs(actual) > 1e-12
                    else None,
                )
            )
        return actuals, forecasts

    @staticmethod
    def _governance(
        db: Session, organization_id: UUID, payload: ForecastExecutionCreate
    ) -> tuple[OIKBDefinition, OIKBDefinitionVersion]:
        row = db.execute(
            select(OIKBDefinition, OIKBDefinitionVersion)
            .join(OIKBDefinitionVersion)
            .where(
                OIKBDefinition.stable_code == payload.definition_code,
                OIKBDefinition.analytical_level == "forecasting",
                OIKBDefinitionVersion.semantic_version == payload.definition_version,
                OIKBDefinitionVersion.lifecycle_status == "active",
            )
        ).first()
        if row is None:
            raise ForecastingServiceError(
                "OIKB_DEFINITION_NOT_ACTIVE", "Active forecasting definition required"
            )
        definition, version = row
        if definition.owner_organization_id not in {None, organization_id}:
            raise ForecastingServiceError("BLOCKED", "Definition is outside tenant scope", 403)
        return definition, version

    @staticmethod
    def _trust(db: Session, organization_id: UUID, payload: ForecastExecutionCreate) -> None:
        trust = db.scalar(
            select(TrustAssessment).where(
                TrustAssessment.id == payload.trust_assessment_id,
                TrustAssessment.organization_id == organization_id,
            )
        )
        readiness = db.scalar(
            select(AnalyticalReadinessDecision).where(
                AnalyticalReadinessDecision.id == payload.readiness_assessment_id,
                AnalyticalReadinessDecision.organization_id == organization_id,
                AnalyticalReadinessDecision.trust_assessment_id == payload.trust_assessment_id,
                AnalyticalReadinessDecision.analytical_level == AnalyticalLevel.FORECASTING.value,
            )
        )
        if trust is None or trust.status not in {
            TrustAssessmentStatus.COMPLETED.value,
            TrustAssessmentStatus.COMPLETED_WITH_WARNINGS.value,
        }:
            raise ForecastingServiceError("BLOCKED", "Completed trust assessment required")
        if readiness is None or readiness.readiness_status not in {
            ReadinessStatus.READY.value,
            ReadinessStatus.READY_WITH_WARNINGS.value,
        }:
            raise ForecastingServiceError(
                "NOT_READY", "Analytical readiness did not permit execution"
            )

    @staticmethod
    def _step(
        db: Session,
        execution_id: UUID,
        sequence: int,
        code: str,
        status: str,
        output: dict[str, object],
    ) -> None:
        now = datetime.now(UTC)
        db.add(
            ForecastExecutionStep(
                forecast_execution_id=execution_id,
                sequence_number=sequence,
                step_code=code,
                status=status,
                started_at=now,
                completed_at=now,
                input_summary={"raw_values_persisted": False},
                output_summary=output,
                explanation="Governed forecasting pipeline completed deterministically.",
            )
        )


forecast_execution_service = ForecastExecutionService()
forecast_reconciliation_service = ForecastReconciliationService()
