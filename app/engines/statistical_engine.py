from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


class StatisticalMethodError(ValueError):
    pass


class InsufficientStatisticalDataError(StatisticalMethodError):
    pass


class UnsupportedStatisticalMethodError(StatisticalMethodError):
    pass


@dataclass(frozen=True)
class StatisticalMethodMetadata:
    method_code: str
    method_name: str
    method_version: str
    capability_class: str
    minimum_sample_size: int
    supports_time_series: bool = False
    supports_peer_group: bool = False
    supports_grouping: bool = False
    supports_weights: bool = False


@dataclass(frozen=True)
class StatisticalMethodResult:
    observed_value: float
    expected_value: float | None
    normalized_deviation: float | None
    is_anomaly: bool
    threshold: float | None
    summary: dict[str, object]


class StatisticalMethod(Protocol):
    metadata: StatisticalMethodMetadata

    def execute(
        self, values: list[float], parameters: dict[str, object]
    ) -> StatisticalMethodResult: ...


def _finite(value: object) -> float:
    if isinstance(value, bool):
        raise StatisticalMethodError("Boolean values are not numeric observations")
    try:
        number = float(str(value))
    except (TypeError, ValueError, OverflowError) as exc:
        raise StatisticalMethodError("All observations must be finite numeric values") from exc
    if not math.isfinite(number):
        raise StatisticalMethodError("NaN and infinity are not supported")
    return number


def finite_values(values: Sequence[object]) -> list[float]:
    return [_finite(value) for value in values if value is not None]


def numeric_parameter(parameters: dict[str, object], key: str, default: float) -> float:
    return _finite(parameters.get(key, default))


def integer_parameter(parameters: dict[str, object], key: str, default: int) -> int:
    value = numeric_parameter(parameters, key, float(default))
    if not value.is_integer():
        raise StatisticalMethodError(f"{key} must be an integer")
    return int(value)


def sequence_parameter(
    parameters: dict[str, object], key: str, default: Sequence[object]
) -> Sequence[object]:
    value = parameters.get(key, default)
    if not isinstance(value, (list, tuple)):
        raise StatisticalMethodError(f"{key} must be a list")
    return value


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        raise InsufficientStatisticalDataError("At least one observation is required")
    if not 0 <= quantile <= 1:
        raise StatisticalMethodError("Percentile must be between 0 and 1")
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def median_absolute_deviation(values: list[float]) -> float:
    center = statistics.median(values)
    return statistics.median(abs(value - center) for value in values)


class BoundedStatisticalMethod:
    def __init__(self, metadata: StatisticalMethodMetadata) -> None:
        self.metadata = metadata

    def execute(
        self, values: list[float], parameters: dict[str, object]
    ) -> StatisticalMethodResult:
        values = finite_values(values)
        if len(values) < self.metadata.minimum_sample_size:
            raise InsufficientStatisticalDataError(
                f"{self.metadata.method_code} requires at least "
                f"{self.metadata.minimum_sample_size} observations"
            )
        code = self.metadata.method_code
        observed = values[-1]
        threshold = numeric_parameter(parameters, "deviation_threshold", 3.0)
        if not 0 < threshold <= 20:
            raise StatisticalMethodError(
                "deviation_threshold must be greater than 0 and at most 20"
            )
        if code in DESCRIPTIVE_METHODS:
            value = self._descriptive(code, values, parameters)
            return StatisticalMethodResult(value, None, None, False, None, {"value": value})
        if code in {"Z_SCORE", "STANDARD_DEVIATION_BAND", "PEER_Z_SCORE"}:
            baseline = values[:-1] or values
            expected = statistics.mean(baseline)
            dispersion = statistics.stdev(baseline) if len(baseline) > 1 else 0.0
            score = (
                0.0
                if dispersion == 0 and observed == expected
                else math.copysign(threshold + 1, observed - expected)
                if dispersion == 0
                else (observed - expected) / dispersion
            )
        elif code in {
            "MODIFIED_Z_SCORE",
            "PEER_MODIFIED_Z_SCORE",
            "ROLLING_MODIFIED_Z_SCORE",
            "ROBUST_NORMALIZED_SCORE",
        }:
            baseline = self._window(values, parameters)
            expected = statistics.median(baseline)
            dispersion = median_absolute_deviation(baseline)
            score = (
                0.0
                if dispersion == 0 and observed == expected
                else math.copysign(threshold + 1, observed - expected)
                if dispersion == 0
                else 0.6745 * (observed - expected) / dispersion
            )
        elif code in {"IQR_RULE", "ROLLING_IQR"}:
            baseline = self._window(values, parameters)
            q1, q3 = percentile(baseline, 0.25), percentile(baseline, 0.75)
            expected = statistics.median(baseline)
            dispersion = q3 - q1
            multiplier = numeric_parameter(parameters, "iqr_multiplier", 1.5)
            score = (
                0.0
                if dispersion == 0 and observed == expected
                else math.copysign(threshold + 1, observed - expected)
                if dispersion == 0
                else (observed - expected) / dispersion
            )
            threshold = multiplier
        elif code in {"PERCENTILE_THRESHOLD", "PEER_PERCENTILE"}:
            baseline = values[:-1] or values
            quantile = numeric_parameter(parameters, "percentile", 0.95)
            expected = percentile(baseline, quantile)
            score = 0.0 if expected == 0 else (observed - expected) / abs(expected)
            threshold = numeric_parameter(parameters, "relative_threshold", 0.0)
        elif code == "PEER_RATIO_DEVIATION":
            baseline = values[:-1]
            expected = statistics.median(baseline)
            score = 0.0 if expected == 0 else (observed - expected) / abs(expected)
            threshold = numeric_parameter(parameters, "relative_threshold", 0.2)
        elif code in {"ROLLING_Z_SCORE", "EWMA_DEVIATION"}:
            baseline = self._window(values, parameters)
            if code == "EWMA_DEVIATION":
                alpha = numeric_parameter(parameters, "alpha", 0.3)
                if not 0 < alpha <= 1:
                    raise StatisticalMethodError("alpha must be greater than 0 and at most 1")
                expected = baseline[0]
                for value in baseline[1:]:
                    expected = alpha * value + (1 - alpha) * expected
            else:
                expected = statistics.mean(baseline)
            dispersion = statistics.stdev(baseline) if len(baseline) > 1 else 0.0
            score = 0.0 if dispersion == 0 else (observed - expected) / dispersion
        elif code in {"MEDIAN_BASELINE", "ROLLING_MEDIAN"}:
            baseline = self._window(values, parameters)
            expected = statistics.median(baseline)
            score = 0.0 if expected == 0 else (observed - expected) / abs(expected)
            threshold = numeric_parameter(parameters, "relative_threshold", 0.2)
        elif code in {"TRIMMED_MEAN_BASELINE", "WINSORIZED_MEAN_BASELINE"}:
            baseline = sorted(values[:-1] or values)
            proportion = numeric_parameter(parameters, "trim_proportion", 0.1)
            if not 0 <= proportion < 0.5:
                raise StatisticalMethodError("trim_proportion must be between 0 and 0.5")
            count = int(len(baseline) * proportion)
            if code == "TRIMMED_MEAN_BASELINE" and count:
                adjusted = baseline[count:-count]
            elif code == "WINSORIZED_MEAN_BASELINE" and count:
                adjusted = (
                    [baseline[count]] * count
                    + baseline[count:-count]
                    + [baseline[-count - 1]] * count
                )
            else:
                adjusted = baseline
            expected = statistics.mean(adjusted)
            score = 0.0 if expected == 0 else (observed - expected) / abs(expected)
            threshold = numeric_parameter(parameters, "relative_threshold", 0.2)
        elif code == "ROLLING_MAD":
            baseline = self._window(values, parameters)
            expected = statistics.median(baseline)
            dispersion = median_absolute_deviation(baseline)
            score = 0.0 if dispersion == 0 else abs(observed - expected) / dispersion
        elif code == "LINEAR_TREND":
            return self._linear_trend(values, parameters)
        elif code in {"CUSUM_CHANGE_DETECTION", "LEVEL_SHIFT", "SLOPE_CHANGE"}:
            return self._change(values, parameters, code)
        elif code in {"WEIGHTED_COMPONENT_SCORE", "MAX_COMPONENT_SCORE"}:
            components = finite_values(sequence_parameter(parameters, "components", values))
            if not components:
                raise InsufficientStatisticalDataError("Composite components are required")
            bounded = [max(0.0, min(1.0, item)) for item in components]
            if code == "MAX_COMPONENT_SCORE":
                value = max(bounded)
            else:
                weights = finite_values(
                    sequence_parameter(parameters, "weights", [1.0] * len(bounded))
                )
                if len(weights) != len(bounded) or any(weight < 0 for weight in weights):
                    raise StatisticalMethodError(
                        "Composite weights must be non-negative and aligned"
                    )
                total = sum(weights)
                if total <= 0:
                    raise StatisticalMethodError("Composite weights must have a positive total")
                value = (
                    sum(item * weight for item, weight in zip(bounded, weights, strict=True))
                    / total
                )
            return StatisticalMethodResult(
                value, None, value, value >= threshold, threshold, {"components": bounded}
            )
        else:
            raise UnsupportedStatisticalMethodError(f"{code} is not implemented")
        return StatisticalMethodResult(
            observed,
            expected,
            score,
            abs(score) >= threshold,
            threshold,
            {"dispersion": locals().get("dispersion"), "sample_size": len(values)},
        )

    @staticmethod
    def _window(values: list[float], parameters: dict[str, object]) -> list[float]:
        window = integer_parameter(parameters, "window_size", min(12, len(values) - 1))
        if window < 2 or window > 365:
            raise StatisticalMethodError("window_size must be between 2 and 365")
        baseline = values[:-1][-window:]
        if len(baseline) < 2:
            raise InsufficientStatisticalDataError(
                "Rolling methods require historical observations"
            )
        return baseline

    @staticmethod
    def _descriptive(code: str, values: list[float], parameters: dict[str, object]) -> float:
        if code == "COUNT":
            return float(len(values))
        if code == "MISSING_COUNT":
            return numeric_parameter(parameters, "missing_count", 0)
        if code == "MEAN":
            return statistics.mean(values)
        if code == "MEDIAN":
            return statistics.median(values)
        if code == "MODE":
            modes = statistics.multimode(values)
            return min(modes)
        if code == "MINIMUM":
            return min(values)
        if code == "MAXIMUM":
            return max(values)
        if code == "RANGE":
            return max(values) - min(values)
        if code == "VARIANCE":
            return statistics.variance(values)
        if code == "STANDARD_DEVIATION":
            return statistics.stdev(values)
        if code == "COEFFICIENT_OF_VARIATION":
            mean = statistics.mean(values)
            return 0.0 if mean == 0 else statistics.stdev(values) / abs(mean)
        if code == "QUARTILES":
            return percentile(values, numeric_parameter(parameters, "quartile", 0.5))
        if code == "INTERQUARTILE_RANGE":
            return percentile(values, 0.75) - percentile(values, 0.25)
        if code == "PERCENTILE":
            return percentile(values, numeric_parameter(parameters, "percentile", 0.95))
        if code == "SKEWNESS":
            mean = statistics.mean(values)
            standard_deviation = statistics.pstdev(values)
            return (
                0.0
                if standard_deviation == 0
                else sum(((value - mean) / standard_deviation) ** 3 for value in values)
                / len(values)
            )
        raise UnsupportedStatisticalMethodError(code)

    @staticmethod
    def _linear_trend(
        values: list[float], parameters: dict[str, object]
    ) -> StatisticalMethodResult:
        count = len(values)
        x_mean = (count - 1) / 2
        y_mean = statistics.mean(values)
        denominator = sum((index - x_mean) ** 2 for index in range(count))
        slope = (
            sum((index - x_mean) * (value - y_mean) for index, value in enumerate(values))
            / denominator
        )
        fitted = [y_mean + slope * (index - x_mean) for index in range(count)]
        total = sum((value - y_mean) ** 2 for value in values)
        residual = sum((value - fit) ** 2 for value, fit in zip(values, fitted, strict=True))
        fit_quality = 1.0 if total == 0 else max(0.0, 1 - residual / total)
        threshold = numeric_parameter(parameters, "slope_threshold", 0.0)
        normalized = 0.0 if y_mean == 0 else slope / abs(y_mean)
        return StatisticalMethodResult(
            values[-1],
            fitted[-1],
            normalized,
            abs(slope) > threshold,
            threshold,
            {
                "slope": slope,
                "fit_quality": fit_quality,
                "starting_value": values[0],
                "ending_value": values[-1],
                "period_count": count,
            },
        )

    @staticmethod
    def _change(
        values: list[float], parameters: dict[str, object], code: str
    ) -> StatisticalMethodResult:
        minimum_segment = integer_parameter(parameters, "minimum_segment", 3)
        if len(values) < minimum_segment * 2:
            raise InsufficientStatisticalDataError("Change detection requires two stable segments")
        best_index, best_shift = minimum_segment, 0.0
        for index in range(minimum_segment, len(values) - minimum_segment + 1):
            shift = statistics.mean(values[index:]) - statistics.mean(values[:index])
            if abs(shift) > abs(best_shift):
                best_index, best_shift = index, shift
        previous = statistics.mean(values[:best_index])
        current = statistics.mean(values[best_index:])
        relative = 0.0 if previous == 0 else best_shift / abs(previous)
        threshold = numeric_parameter(parameters, "relative_threshold", 0.2)
        return StatisticalMethodResult(
            current,
            previous,
            relative,
            abs(relative) >= threshold,
            threshold,
            {
                "change_point_index": best_index,
                "previous_level": previous,
                "new_level": current,
                "absolute_shift": best_shift,
                "duration": len(values) - best_index,
                "method": code,
            },
        )


DESCRIPTIVE_METHODS = {
    "COUNT",
    "MISSING_COUNT",
    "MEAN",
    "MEDIAN",
    "MODE",
    "MINIMUM",
    "MAXIMUM",
    "RANGE",
    "VARIANCE",
    "STANDARD_DEVIATION",
    "COEFFICIENT_OF_VARIATION",
    "QUARTILES",
    "INTERQUARTILE_RANGE",
    "PERCENTILE",
    "SKEWNESS",
}


class StatisticalMethodRegistry:
    def __init__(self) -> None:
        self._methods: dict[tuple[str, str], StatisticalMethod] = {}

    def register(self, method: StatisticalMethod) -> None:
        key = (method.metadata.method_code, method.metadata.method_version)
        if key in self._methods:
            raise StatisticalMethodError(f"Method {key[0]} {key[1]} is already registered")
        self._methods[key] = method

    def get(self, method_code: str, method_version: str = "1.0") -> StatisticalMethod:
        try:
            return self._methods[(method_code, method_version)]
        except KeyError as exc:
            raise UnsupportedStatisticalMethodError(
                f"Method {method_code} {method_version} is unsupported"
            ) from exc

    def list(self) -> list[StatisticalMethod]:
        return [self._methods[key] for key in sorted(self._methods)]

    def validate(self) -> None:
        if not self._methods:
            raise StatisticalMethodError("Statistical method registry is empty")


METHOD_SPECS = {
    **{code: ("DESCRIPTIVE_STATISTICS", 1, False, False) for code in DESCRIPTIVE_METHODS},
    "Z_SCORE": ("OUTLIER_DETECTION", 3, False, False),
    "MODIFIED_Z_SCORE": ("ROBUST_OUTLIER_DETECTION", 3, False, False),
    "IQR_RULE": ("ROBUST_OUTLIER_DETECTION", 5, False, False),
    "PERCENTILE_THRESHOLD": ("OUTLIER_DETECTION", 5, False, False),
    "STANDARD_DEVIATION_BAND": ("VARIABILITY_ANALYSIS", 3, False, False),
    "MEDIAN_BASELINE": ("BASELINE_ESTIMATION", 3, False, False),
    "TRIMMED_MEAN_BASELINE": ("BASELINE_ESTIMATION", 5, False, False),
    "WINSORIZED_MEAN_BASELINE": ("BASELINE_ESTIMATION", 5, False, False),
    "ROLLING_MEDIAN": ("BASELINE_ESTIMATION", 4, True, False),
    "ROLLING_MAD": ("VARIABILITY_ANALYSIS", 4, True, False),
    "PEER_Z_SCORE": ("PEER_GROUP_DEVIATION", 4, False, True),
    "PEER_MODIFIED_Z_SCORE": ("PEER_GROUP_DEVIATION", 4, False, True),
    "PEER_PERCENTILE": ("PEER_GROUP_DEVIATION", 5, False, True),
    "PEER_RATIO_DEVIATION": ("PEER_GROUP_DEVIATION", 4, False, True),
    "ROLLING_Z_SCORE": ("TIME_SERIES_DEVIATION", 4, True, False),
    "ROLLING_MODIFIED_Z_SCORE": ("TIME_SERIES_DEVIATION", 4, True, False),
    "ROLLING_IQR": ("TIME_SERIES_DEVIATION", 6, True, False),
    "EWMA_DEVIATION": ("TIME_SERIES_DEVIATION", 4, True, False),
    "CUSUM_CHANGE_DETECTION": ("CHANGE_POINT_DETECTION", 6, True, False),
    "LINEAR_TREND": ("TREND_DETECTION", 3, True, False),
    "SLOPE_CHANGE": ("CHANGE_POINT_DETECTION", 6, True, False),
    "LEVEL_SHIFT": ("CHANGE_POINT_DETECTION", 6, True, False),
    "WEIGHTED_COMPONENT_SCORE": ("COMPOSITE_ANOMALY_SCORING", 1, False, False),
    "MAX_COMPONENT_SCORE": ("COMPOSITE_ANOMALY_SCORING", 1, False, False),
    "ROBUST_NORMALIZED_SCORE": ("COMPOSITE_ANOMALY_SCORING", 3, False, False),
}


def default_statistical_method_registry() -> StatisticalMethodRegistry:
    registry = StatisticalMethodRegistry()
    for code, (capability, minimum, time_series, peer_group) in METHOD_SPECS.items():
        registry.register(
            BoundedStatisticalMethod(
                StatisticalMethodMetadata(
                    method_code=code,
                    method_name=code.replace("_", " ").title(),
                    method_version="1.0",
                    capability_class=capability,
                    minimum_sample_size=minimum,
                    supports_time_series=time_series,
                    supports_peer_group=peer_group,
                    supports_grouping=peer_group,
                    supports_weights=code == "WEIGHTED_COMPONENT_SCORE",
                )
            )
        )
    registry.validate()
    return registry
