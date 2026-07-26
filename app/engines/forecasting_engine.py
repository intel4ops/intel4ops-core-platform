from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import fmean, median
from typing import Protocol, cast


class ForecastingMethodError(ValueError):
    pass


@dataclass(frozen=True)
class ForecastingMethodMetadata:
    method_code: str
    method_name: str
    method_version: str
    capability_class: str
    minimum_history: int
    minimum_seasonal_cycles: int = 0
    supports_trend: bool = False
    supports_seasonality: bool = False
    supports_exogenous: bool = False
    supports_intervals: bool = True
    supports_negative_values: bool = True
    supports_zero_values: bool = True
    supports_intermittent_demand: bool = False
    complexity_rank: int = 1
    supported: bool = True


@dataclass(frozen=True)
class ForecastResult:
    values: list[float]
    fitted_values: list[float]
    residuals: list[float]
    diagnostics: dict[str, object]


class ForecastingMethod(Protocol):
    metadata: ForecastingMethodMetadata

    def forecast(
        self, values: list[float], horizon: int, parameters: dict[str, object]
    ) -> ForecastResult: ...


def _finite(values: list[float]) -> None:
    if not values or any(not math.isfinite(value) for value in values):
        raise ForecastingMethodError("Series must contain finite numeric observations")


def _linear(values: list[float]) -> tuple[float, float]:
    count = len(values)
    x_mean = (count - 1) / 2
    y_mean = fmean(values)
    denominator = sum((index - x_mean) ** 2 for index in range(count))
    slope = (
        sum((index - x_mean) * (value - y_mean) for index, value in enumerate(values)) / denominator
        if denominator
        else 0.0
    )
    return y_mean - slope * x_mean, slope


def _quadratic(values: list[float]) -> tuple[float, float, float]:
    count = len(values)
    xs = [float(index) for index in range(count)]
    matrix = [
        [float(count), sum(xs), sum(x**2 for x in xs), sum(values)],
        [
            sum(xs),
            sum(x**2 for x in xs),
            sum(x**3 for x in xs),
            sum(x * y for x, y in zip(xs, values, strict=True)),
        ],
        [
            sum(x**2 for x in xs),
            sum(x**3 for x in xs),
            sum(x**4 for x in xs),
            sum(x**2 * y for x, y in zip(xs, values, strict=True)),
        ],
    ]
    for column in range(3):
        pivot = max(range(column, 3), key=lambda row: abs(matrix[row][column]))
        if abs(matrix[pivot][column]) < 1e-12:
            raise ForecastingMethodError("SINGULAR_QUADRATIC_FIT")
        matrix[column], matrix[pivot] = matrix[pivot], matrix[column]
        divisor = matrix[column][column]
        matrix[column] = [value / divisor for value in matrix[column]]
        for row in range(3):
            if row == column:
                continue
            factor = matrix[row][column]
            matrix[row] = [
                value - factor * pivot_value
                for value, pivot_value in zip(matrix[row], matrix[column], strict=True)
            ]
    return matrix[0][3], matrix[1][3], matrix[2][3]


def _residuals(values: list[float], fitted: list[float]) -> list[float]:
    return [actual - estimate for actual, estimate in zip(values, fitted, strict=True)]


def _number(parameters: dict[str, object], name: str, default: float) -> float:
    value = parameters.get(name, default)
    if not isinstance(value, (int, float, str)):
        raise ForecastingMethodError(f"INVALID_{name.upper()}")
    return float(value)


class BoundedForecastingMethod:
    def __init__(self, metadata: ForecastingMethodMetadata) -> None:
        self.metadata = metadata

    def forecast(
        self, values: list[float], horizon: int, parameters: dict[str, object]
    ) -> ForecastResult:
        _finite(values)
        if len(values) < self.metadata.minimum_history:
            raise ForecastingMethodError("INSUFFICIENT_HISTORY")
        if horizon < 1 or horizon > 120:
            raise ForecastingMethodError("INVALID_HORIZON")
        code = self.metadata.method_code
        season = int(_number(parameters, "seasonal_period", 12))
        if self.metadata.supports_seasonality and len(values) < season * 2:
            raise ForecastingMethodError("INSUFFICIENT_SEASONAL_CYCLES")
        fitted: list[float]
        forecasts: list[float]
        if code == "NAIVE":
            fitted = [values[0], *values[:-1]]
            forecasts = [values[-1]] * horizon
        elif code == "SEASONAL_NAIVE":
            fitted = [
                values[index - season] if index >= season else values[index]
                for index in range(len(values))
            ]
            forecasts = [values[len(values) - season + (step % season)] for step in range(horizon)]
        elif code in {"HISTORICAL_MEAN", "EXPANDING_MEAN"}:
            fitted = [fmean(values[: index + 1]) for index in range(len(values))]
            forecasts = [fmean(values)] * horizon
        elif code == "HISTORICAL_MEDIAN":
            fitted = [float(median(values[: index + 1])) for index in range(len(values))]
            forecasts = [float(median(values))] * horizon
        elif code in {"SIMPLE_MOVING_AVERAGE", "WEIGHTED_MOVING_AVERAGE"}:
            window = max(2, min(int(_number(parameters, "window", 3)), len(values)))
            fitted = []
            for index in range(len(values)):
                sample = values[max(0, index - window + 1) : index + 1]
                if code == "WEIGHTED_MOVING_AVERAGE":
                    weights = list(range(1, len(sample) + 1))
                    fitted.append(
                        sum(value * weight for value, weight in zip(sample, weights, strict=True))
                        / sum(weights)
                    )
                else:
                    fitted.append(fmean(sample))
            forecasts = [fitted[-1]] * horizon
        elif code == "SIMPLE_EXPONENTIAL_SMOOTHING":
            alpha = _number(parameters, "alpha", 0.3)
            if not 0 < alpha <= 1:
                raise ForecastingMethodError("INVALID_ALPHA")
            level = values[0]
            fitted = [level]
            for value in values[1:]:
                level = alpha * value + (1 - alpha) * level
                fitted.append(level)
            forecasts = [level] * horizon
        elif code == "DRIFT":
            slope = (values[-1] - values[0]) / (len(values) - 1)
            fitted = [values[0] + slope * index for index in range(len(values))]
            forecasts = [values[-1] + slope * (step + 1) for step in range(horizon)]
        elif code == "LINEAR_TIME_TREND":
            intercept, slope = _linear(values)
            fitted = [intercept + slope * index for index in range(len(values))]
            forecasts = [intercept + slope * (len(values) + step) for step in range(horizon)]
        elif code == "POLYNOMIAL_TIME_TREND_DEGREE_2":
            intercept, linear_coefficient, quadratic_coefficient = _quadratic(values)
            fitted = [
                intercept + linear_coefficient * index + quadratic_coefficient * index**2
                for index in range(len(values))
            ]
            forecasts = [
                intercept
                + linear_coefficient * (len(values) + step)
                + quadratic_coefficient * (len(values) + step) ** 2
                for step in range(horizon)
            ]
        elif code in {"HOLT_LINEAR_TREND", "HOLT_DAMPED_TREND"}:
            alpha = _number(parameters, "alpha", 0.4)
            beta = _number(parameters, "beta", 0.2)
            damping = _number(parameters, "damping", 0.9 if code.endswith("DAMPED_TREND") else 1)
            if not all(0 < item <= 1 for item in (alpha, beta, damping)):
                raise ForecastingMethodError("INVALID_SMOOTHING_PARAMETER")
            level, trend = values[0], values[1] - values[0]
            fitted = [level]
            for value in values[1:]:
                previous_level = level
                level = alpha * value + (1 - alpha) * (level + damping * trend)
                trend = beta * (level - previous_level) + (1 - beta) * damping * trend
                fitted.append(level + damping * trend)
            forecasts = [
                level + sum(damping**power for power in range(1, step + 2)) * trend
                for step in range(horizon)
            ]
        elif code in {"HOLT_WINTERS_ADDITIVE", "SEASONAL_DUMMY_REGRESSION"}:
            intercept, slope = _linear(values)
            seasonal = [
                fmean(
                    [
                        value - (intercept + slope * index)
                        for index, value in enumerate(values)
                        if index % season == position
                    ]
                )
                for position in range(season)
            ]
            fitted = [
                intercept + slope * index + seasonal[index % season] for index in range(len(values))
            ]
            forecasts = [
                intercept + slope * (len(values) + step) + seasonal[(len(values) + step) % season]
                for step in range(horizon)
            ]
        elif code in {"CROSTON", "SBA_CROSTON"}:
            nonzero = [(index, value) for index, value in enumerate(values) if value != 0]
            if not nonzero:
                estimate = 0.0
            else:
                demand = fmean(value for _, value in nonzero)
                intervals = [
                    right[0] - left[0] for left, right in zip(nonzero, nonzero[1:], strict=False)
                ]
                interval = fmean(intervals) if intervals else len(values) / len(nonzero)
                estimate = demand / max(interval, 1)
                if code == "SBA_CROSTON":
                    estimate *= 0.95
            fitted = [estimate] * len(values)
            forecasts = [estimate] * horizon
        elif code == "WEIGHTED_FORECAST_ENSEMBLE":
            components = parameters.get("component_forecasts")
            ensemble_weights = parameters.get("weights")
            if not isinstance(components, list) or not isinstance(ensemble_weights, list):
                raise ForecastingMethodError("INVALID_ENSEMBLE")
            numeric_weights = [
                float(item) for item in cast(list[int | float | str], ensemble_weights)
            ]
            if len(components) != len(numeric_weights) or not math.isclose(
                sum(numeric_weights), 1.0, abs_tol=1e-9
            ):
                raise ForecastingMethodError("INVALID_ENSEMBLE_WEIGHTS")
            component_values = [
                [float(value) for value in item]
                for item in cast(list[list[int | float | str]], components)
            ]
            if any(len(item) != horizon for item in component_values):
                raise ForecastingMethodError("INVALID_ENSEMBLE_HORIZON")
            forecasts = [
                sum(
                    component[step] * weight
                    for component, weight in zip(component_values, numeric_weights, strict=True)
                )
                for step in range(horizon)
            ]
            fitted = [fmean(values)] * len(values)
        elif code == "BOUNDED_MULTIVARIATE_LINEAR_REGRESSION":
            raise ForecastingMethodError("UNSUPPORTED_EXOGENOUS_CONFIGURATION")
        else:
            raise ForecastingMethodError("UNSUPPORTED")
        return ForecastResult(
            values=forecasts,
            fitted_values=fitted,
            residuals=_residuals(values, fitted),
            diagnostics={
                "method": code,
                "history_count": len(values),
                "horizon": horizon,
                "deterministic": True,
            },
        )


class ForecastingMethodRegistry:
    def __init__(self) -> None:
        self._methods: dict[tuple[str, str], ForecastingMethod] = {}

    def register(self, method: ForecastingMethod) -> None:
        key = (method.metadata.method_code, method.metadata.method_version)
        if key in self._methods:
            raise ForecastingMethodError(f"Duplicate forecasting method {key[0]} {key[1]}")
        self._methods[key] = method

    def get(self, method_code: str, method_version: str = "1.0") -> ForecastingMethod:
        try:
            return self._methods[(method_code.upper(), method_version)]
        except KeyError as exc:
            raise ForecastingMethodError("UNSUPPORTED") from exc

    def list(self) -> list[ForecastingMethod]:
        return [self._methods[key] for key in sorted(self._methods)]


def default_forecasting_method_registry() -> ForecastingMethodRegistry:
    registry = ForecastingMethodRegistry()
    definitions = [
        ("NAIVE", "Naive", "POINT_FORECAST", 2, 1, False, False, False),
        ("SEASONAL_NAIVE", "Seasonal naive", "SEASONAL_FORECAST", 4, 1, False, True, False),
        ("DRIFT", "Drift", "TREND_FORECAST", 2, 2, True, False, False),
        ("HISTORICAL_MEAN", "Historical mean", "POINT_FORECAST", 2, 1, False, False, False),
        ("HISTORICAL_MEDIAN", "Historical median", "POINT_FORECAST", 2, 1, False, False, False),
        (
            "SIMPLE_MOVING_AVERAGE",
            "Simple moving average",
            "ROLLING_FORECAST",
            3,
            2,
            False,
            False,
            False,
        ),
        (
            "WEIGHTED_MOVING_AVERAGE",
            "Weighted moving average",
            "ROLLING_FORECAST",
            3,
            2,
            False,
            False,
            False,
        ),
        ("EXPANDING_MEAN", "Expanding mean", "ROLLING_FORECAST", 2, 1, False, False, False),
        (
            "SIMPLE_EXPONENTIAL_SMOOTHING",
            "Simple exponential smoothing",
            "POINT_FORECAST",
            3,
            2,
            False,
            False,
            False,
        ),
        ("HOLT_LINEAR_TREND", "Holt linear trend", "TREND_FORECAST", 4, 3, True, False, False),
        ("HOLT_DAMPED_TREND", "Holt damped trend", "TREND_FORECAST", 4, 4, True, False, False),
        (
            "HOLT_WINTERS_ADDITIVE",
            "Holt-Winters additive",
            "SEASONAL_FORECAST",
            8,
            5,
            True,
            True,
            False,
        ),
        ("LINEAR_TIME_TREND", "Linear time trend", "TREND_FORECAST", 3, 3, True, False, False),
        (
            "POLYNOMIAL_TIME_TREND_DEGREE_2",
            "Polynomial time trend degree 2",
            "TREND_FORECAST",
            5,
            5,
            True,
            False,
            False,
        ),
        (
            "SEASONAL_DUMMY_REGRESSION",
            "Seasonal dummy regression",
            "SEASONAL_FORECAST",
            8,
            5,
            True,
            True,
            False,
        ),
        (
            "BOUNDED_MULTIVARIATE_LINEAR_REGRESSION",
            "Bounded multivariate linear regression",
            "MULTI_HORIZON_FORECAST",
            8,
            6,
            True,
            False,
            True,
        ),
        ("CROSTON", "Croston", "POINT_FORECAST", 5, 3, False, False, False),
        ("SBA_CROSTON", "SBA Croston", "POINT_FORECAST", 5, 3, False, False, False),
        (
            "WEIGHTED_FORECAST_ENSEMBLE",
            "Weighted forecast ensemble",
            "FORECAST_MODEL_SELECTION",
            3,
            7,
            False,
            False,
            False,
        ),
    ]
    intermittent = {"CROSTON", "SBA_CROSTON"}
    for code, name, capability, minimum, complexity, trend, seasonal, exogenous in definitions:
        registry.register(
            BoundedForecastingMethod(
                ForecastingMethodMetadata(
                    method_code=code,
                    method_name=name,
                    method_version="1.0",
                    capability_class=capability,
                    minimum_history=minimum,
                    minimum_seasonal_cycles=2 if seasonal else 0,
                    supports_trend=trend,
                    supports_seasonality=seasonal,
                    supports_exogenous=exogenous,
                    supports_intermittent_demand=code in intermittent,
                    complexity_rank=complexity,
                    supported=code != "BOUNDED_MULTIVARIATE_LINEAR_REGRESSION",
                )
            )
        )
    return registry
