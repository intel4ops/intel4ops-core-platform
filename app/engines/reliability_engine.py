from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import fmean
from typing import Protocol


class ReliabilityMethodError(ValueError):
    pass


@dataclass(frozen=True)
class ReliabilityMethodMetadata:
    method_code: str
    method_name: str
    method_version: str
    capability_class: str
    supported_exposure_bases: tuple[str, ...]
    supports_censoring: bool
    supports_grouped_assets: bool
    supports_condition_inputs: bool
    supports_uncertainty: bool
    minimum_failure_count: int = 0
    minimum_asset_count: int = 1
    minimum_exposure: float = 0.0
    supported: bool = True
    deprecated: bool = False
    known_limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReliabilityResult:
    values: dict[str, float | None]
    diagnostics: dict[str, object]
    limitations: tuple[str, ...] = ()


class ReliabilityMethod(Protocol):
    @property
    def metadata(self) -> ReliabilityMethodMetadata: ...

    def execute(self, observations: list[dict[str, object]]) -> ReliabilityResult: ...


def _finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReliabilityMethodError(f"{field} must be finite")
    if not math.isfinite(float(value)):
        raise ReliabilityMethodError(f"{field} must be finite")
    return float(value)


def _discrete_count(value: object, field: str) -> int:
    numeric = _finite(value, field)
    if not numeric.is_integer():
        raise ReliabilityMethodError(f"{field} must be an integral count")
    return int(numeric)


def _strict_boolean(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise ReliabilityMethodError(f"{field} must be boolean")
    return value


@dataclass(frozen=True)
class BasicReliabilityMethod:
    metadata: ReliabilityMethodMetadata

    def execute(self, observations: list[dict[str, object]]) -> ReliabilityResult:
        exposure = sum(_finite(item.get("exposure", 0), "exposure") for item in observations)
        downtime = sum(_finite(item.get("downtime", 0), "downtime") for item in observations)
        repair = sum(
            _finite(item.get("repair_duration", 0), "repair_duration") for item in observations
        )
        failures = sum(
            _discrete_count(item.get("failure_count", 0), "failure_count") for item in observations
        )
        repairs = sum(
            _discrete_count(item.get("repair_count", item.get("failure_count", 0)), "repair_count")
            for item in observations
        )
        if exposure < 0 or downtime < 0 or repair < 0 or failures < 0 or repairs < 0:
            raise ReliabilityMethodError("Reliability inputs cannot be negative")
        if downtime > exposure:
            raise ReliabilityMethodError("downtime cannot exceed exposure")
        effective_exposure = exposure - downtime
        values: dict[str, float | None] = {
            "FAILURE_COUNT": float(failures),
            "EXPOSURE": exposure,
            "DOWNTIME": downtime,
            "FAILURE_RATE": failures / exposure if exposure > 0 else None,
            "REPAIR_RATE": repairs / repair if repair > 0 else None,
            "MTBF": effective_exposure / failures if failures and effective_exposure >= 0 else None,
            "MTTF": exposure / failures if failures else None,
            "MTTR": repair / repairs if repairs else None,
            "OPERATIONAL_AVAILABILITY": (
                max(0.0, min(1.0, effective_exposure / exposure)) if exposure > 0 else None
            ),
            "UNPLANNED_DOWNTIME_RATIO": downtime / exposure if exposure > 0 else None,
        }
        return ReliabilityResult(
            values,
            {"numerator_failure_count": failures, "denominator_exposure": exposure},
            ("Zero failures do not establish zero future risk.",) if failures == 0 else (),
        )


@dataclass(frozen=True)
class KaplanMeierMethod:
    metadata: ReliabilityMethodMetadata

    def execute(self, observations: list[dict[str, object]]) -> ReliabilityResult:
        prepared: list[tuple[float, bool]] = []
        for item in observations:
            duration = _finite(item.get("duration"), "duration")
            if duration < 0:
                raise ReliabilityMethodError("duration cannot be negative")
            prepared.append(
                (duration, _strict_boolean(item.get("event_observed"), "event_observed"))
            )
        if not prepared:
            raise ReliabilityMethodError("At least one survival observation is required")
        at_risk = len(prepared)
        survival = 1.0
        points: list[dict[str, object]] = []
        for time in sorted({item[0] for item in prepared}):
            events = sum(duration == time and event for duration, event in prepared)
            censored = sum(duration == time and not event for duration, event in prepared)
            if events:
                survival *= 1 - events / at_risk
            points.append(
                {
                    "time": time,
                    "at_risk": at_risk,
                    "events": events,
                    "censored": censored,
                    "survival_probability": survival,
                }
            )
            at_risk -= events + censored
        median_time: float | None = None
        for point in points:
            probability = point["survival_probability"]
            point_time = point["time"]
            if isinstance(probability, (int, float)) and probability <= 0.5:
                if isinstance(point_time, (int, float)):
                    median_time = float(point_time)
                break
        return ReliabilityResult(
            {"MEDIAN_SURVIVAL": median_time, "FINAL_SURVIVAL": survival},
            {"survival_points": points, "censoring_supported": True},
        )


@dataclass(frozen=True)
class WeibullTwoParameterMethod:
    metadata: ReliabilityMethodMetadata

    def execute(self, observations: list[dict[str, object]]) -> ReliabilityResult:
        if any(
            not _strict_boolean(item.get("event_observed"), "event_observed")
            for item in observations
        ):
            raise ReliabilityMethodError(
                "WEIBULL_TWO_PARAMETER does not support censored observations"
            )
        failures = sorted(_finite(item.get("duration"), "duration") for item in observations)
        if len(failures) < self.metadata.minimum_failure_count:
            raise ReliabilityMethodError("Insufficient failures for Weibull fit")
        if failures[0] <= 0 or failures[0] == failures[-1]:
            raise ReliabilityMethodError("Positive non-constant failure times are required")
        # Deterministic Weibull probability-plot least-squares fit.
        xs = [math.log(value) for value in failures]
        ys = [
            math.log(-math.log(1 - (index - 0.3) / (len(failures) + 0.4)))
            for index in range(1, len(failures) + 1)
        ]
        x_mean, y_mean = fmean(xs), fmean(ys)
        denominator = sum((value - x_mean) ** 2 for value in xs)
        shape = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys, strict=True)) / denominator
        if not math.isfinite(shape) or shape <= 0:
            raise ReliabilityMethodError("Invalid Weibull shape")
        intercept = y_mean - shape * x_mean
        scale = math.exp(-intercept / shape)
        b10 = scale * (-math.log(0.9)) ** (1 / shape)
        b50 = scale * math.log(2) ** (1 / shape)
        return ReliabilityResult(
            {"WEIBULL_SHAPE": shape, "WEIBULL_SCALE": scale, "B10": b10, "B50": b50},
            {
                "fit": "probability_plot_least_squares",
                "failure_count": len(failures),
                "censored_count": 0,
                "censoring_supported": False,
            },
            ("This bounded probability-plot fit supports uncensored failure observations only.",),
        )


@dataclass(frozen=True)
class CompositeScoreMethod:
    metadata: ReliabilityMethodMetadata

    def execute(self, observations: list[dict[str, object]]) -> ReliabilityResult:
        if not observations:
            raise ReliabilityMethodError("At least one component is required")
        contributions = []
        for item in observations:
            value = _finite(item.get("normalized_value"), "normalized_value")
            weight = _finite(item.get("weight"), "weight")
            if not 0 <= value <= 1 or weight < 0:
                raise ReliabilityMethodError("Components and weights must be bounded")
            contributions.append(value * weight)
        weight_sum = sum(_finite(item.get("weight"), "weight") for item in observations)
        if not math.isclose(weight_sum, 1.0, abs_tol=1e-6):
            raise ReliabilityMethodError("Component weights must sum to one")
        risk = max(0.0, min(100.0, sum(contributions) * 100))
        return ReliabilityResult(
            {"RISK_SCORE": risk, "ASSET_HEALTH_SCORE": 100 - risk},
            {"component_contributions": contributions},
        )


class ReliabilityMethodRegistry:
    def __init__(self) -> None:
        self._methods: dict[tuple[str, str], ReliabilityMethod] = {}

    def register(self, method: ReliabilityMethod) -> None:
        key = (method.metadata.method_code, method.metadata.method_version)
        if key in self._methods:
            raise ReliabilityMethodError(
                f"Reliability method {key[0]} {key[1]} is already registered"
            )
        self._methods[key] = method

    def get(self, code: str, version: str = "1.0") -> ReliabilityMethod:
        try:
            method = self._methods[(code, version)]
        except KeyError as exc:
            raise ReliabilityMethodError(
                f"Unsupported reliability method {code} {version}"
            ) from exc
        if not method.metadata.supported or method.metadata.deprecated:
            raise ReliabilityMethodError(f"Reliability method {code} {version} is unavailable")
        return method

    def list(self) -> list[ReliabilityMethod]:
        return [self._methods[key] for key in sorted(self._methods)]


def default_reliability_method_registry() -> ReliabilityMethodRegistry:
    registry = ReliabilityMethodRegistry()
    exposure_bases = ("CALENDAR_TIME", "OPERATING_TIME", "CYCLES", "DISTANCE")
    registry.register(
        BasicReliabilityMethod(
            ReliabilityMethodMetadata(
                method_code="BASIC_RELIABILITY_METRICS",
                method_name="Basic reliability metrics",
                capability_class="RELIABILITY_METRICS",
                supports_censoring=False,
                supports_grouped_assets=True,
                supports_condition_inputs=False,
                supports_uncertainty=False,
                method_version="1.0",
                supported_exposure_bases=exposure_bases,
            )
        )
    )
    for code, name, capability in (
        ("BASIC_AVAILABILITY", "Basic availability", "AVAILABILITY_ANALYSIS"),
        ("FAILURE_RATE", "Failure rate", "FAILURE_RATE_ANALYSIS"),
        ("REPAIR_RATE", "Repair rate", "REPAIRABILITY_ANALYSIS"),
        ("REPEAT_FAILURE", "Repeat failure", "REPEAT_FAILURE_ANALYSIS"),
        ("MAINTENANCE_EFFECTIVENESS", "Maintenance effectiveness", "MAINTENANCE_EFFECTIVENESS"),
        (
            "PM_INTERVAL_EVALUATION",
            "PM interval evaluation",
            "PREVENTIVE_MAINTENANCE_INTERVAL_EVALUATION",
        ),
    ):
        registry.register(
            BasicReliabilityMethod(
                ReliabilityMethodMetadata(
                    method_code=code,
                    method_name=name,
                    method_version="1.0",
                    capability_class=capability,
                    supported_exposure_bases=exposure_bases,
                    supports_censoring=False,
                    supports_grouped_assets=True,
                    supports_condition_inputs=False,
                    supports_uncertainty=False,
                )
            )
        )
    registry.register(
        KaplanMeierMethod(
            ReliabilityMethodMetadata(
                method_code="KAPLAN_MEIER",
                method_name="Kaplan-Meier survival",
                capability_class="SURVIVAL_ANALYSIS",
                supports_censoring=True,
                supports_grouped_assets=True,
                supports_condition_inputs=False,
                supports_uncertainty=True,
                method_version="1.0",
                supported_exposure_bases=exposure_bases,
            )
        )
    )
    registry.register(
        WeibullTwoParameterMethod(
            ReliabilityMethodMetadata(
                method_code="WEIBULL_TWO_PARAMETER",
                method_name="Two-parameter Weibull",
                capability_class="WEIBULL_RELIABILITY",
                supports_censoring=False,
                supports_grouped_assets=True,
                supports_condition_inputs=False,
                supports_uncertainty=False,
                minimum_failure_count=3,
                known_limitations=(
                    "Uncensored failure observations only; censored Weibull fitting is "
                    "unsupported.",
                ),
                method_version="1.0",
                supported_exposure_bases=exposure_bases,
            )
        )
    )
    for code, name, capability in (
        ("BAD_ACTOR_COMPOSITE", "Bad actor composite", "BAD_ACTOR_IDENTIFICATION"),
        ("COMPOSITE_ASSET_HEALTH", "Composite asset health", "ASSET_HEALTH_SCORING"),
        ("DOWNTIME_RISK", "Downtime risk", "DOWNTIME_RISK"),
        ("EMPIRICAL_HAZARD", "Empirical hazard", "FAILURE_RISK_ESTIMATION"),
        ("CONDITION_DETERIORATION", "Condition deterioration", "CONDITION_DETERIORATION"),
        ("CONDITION_THRESHOLD_RUL", "Condition threshold RUL", "REMAINING_USEFUL_LIFE"),
        ("WEIBULL_CONDITIONAL_RISK", "Weibull conditional risk", "FAILURE_RISK_ESTIMATION"),
    ):
        registry.register(
            CompositeScoreMethod(
                ReliabilityMethodMetadata(
                    method_code=code,
                    method_name=name,
                    capability_class=capability,
                    supports_censoring=False,
                    supports_grouped_assets=True,
                    supports_condition_inputs=code != "DOWNTIME_RISK",
                    supports_uncertainty=False,
                    method_version="1.0",
                    supported_exposure_bases=exposure_bases,
                )
            )
        )
    return registry
