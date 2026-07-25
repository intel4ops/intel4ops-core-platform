import math

import pytest

from app.engines.statistical_engine import (
    BoundedStatisticalMethod,
    InsufficientStatisticalDataError,
    StatisticalMethodError,
    StatisticalMethodMetadata,
    UnsupportedStatisticalMethodError,
    default_statistical_method_registry,
)
from app.schemas.statistics import StatisticalEvaluateRequest
from app.services.statistical_service import statistical_execution_service


def test_registry_is_bounded_versioned_and_consistent() -> None:
    registry = default_statistical_method_registry()
    registry.validate()
    assert len(registry.list()) == 40
    assert registry.get("MODIFIED_Z_SCORE").metadata.method_version == "1.0"
    with pytest.raises(UnsupportedStatisticalMethodError):
        registry.get("ARBITRARY_PYTHON")
    with pytest.raises(StatisticalMethodError):
        registry.register(registry.get("MEAN"))


@pytest.mark.parametrize(
    ("method", "expected"),
    [
        ("MEAN", 3.0),
        ("MEDIAN", 3.0),
        ("VARIANCE", 2.5),
        ("STANDARD_DEVIATION", math.sqrt(2.5)),
        ("PERCENTILE", 4.8),
        ("INTERQUARTILE_RANGE", 2.0),
        ("COEFFICIENT_OF_VARIATION", math.sqrt(2.5) / 3),
        ("MINIMUM", 1.0),
        ("MAXIMUM", 5.0),
        ("RANGE", 4.0),
    ],
)
def test_descriptive_statistics(method: str, expected: float) -> None:
    result = (
        default_statistical_method_registry()
        .get(method)
        .execute([1, 2, 3, 4, 5], {"percentile": 0.95})
    )
    assert result.observed_value == pytest.approx(expected)
    assert not result.is_anomaly


@pytest.mark.parametrize(
    "method",
    [
        "Z_SCORE",
        "MODIFIED_Z_SCORE",
        "IQR_RULE",
        "PERCENTILE_THRESHOLD",
        "STANDARD_DEVIATION_BAND",
    ],
)
def test_classical_and_robust_outlier_detection(method: str) -> None:
    result = (
        default_statistical_method_registry()
        .get(method)
        .execute(
            [10, 11, 9, 10, 10, 100],
            {
                "deviation_threshold": 2,
                "relative_threshold": 0.2,
                "percentile": 0.9,
            },
        )
    )
    assert result.is_anomaly
    assert result.observed_value == 100


def test_constant_population_and_numerical_safety() -> None:
    constant = default_statistical_method_registry().get("Z_SCORE").execute([5, 5, 5, 5], {})
    assert constant.normalized_deviation == 0
    assert not constant.is_anomaly
    with pytest.raises(StatisticalMethodError):
        default_statistical_method_registry().get("MEAN").execute([1, float("nan")], {})
    with pytest.raises(InsufficientStatisticalDataError):
        default_statistical_method_registry().get("IQR_RULE").execute([1, 2], {})


def test_peer_rolling_trend_and_change_detection() -> None:
    registry = default_statistical_method_registry()
    peer = registry.get("PEER_MODIFIED_Z_SCORE").execute([10, 11, 9, 10, 50], {})
    rolling = registry.get("ROLLING_Z_SCORE").execute([10, 11, 9, 10, 50], {})
    trend = registry.get("LINEAR_TREND").execute([1, 2, 3, 4, 5], {"slope_threshold": 0.5})
    shift = registry.get("LEVEL_SHIFT").execute(
        [10, 10, 10, 20, 20, 20],
        {"minimum_segment": 3, "relative_threshold": 0.5},
    )
    assert peer.is_anomaly
    assert rolling.is_anomaly
    assert trend.summary["slope"] == pytest.approx(1)
    assert shift.summary["change_point_index"] == 3
    assert shift.is_anomaly


def test_explainable_composite_scoring_and_invalid_weights() -> None:
    method = default_statistical_method_registry().get("WEIGHTED_COMPONENT_SCORE")
    result = method.execute(
        [0.2, 0.8],
        {
            "components": [0.2, 0.8],
            "weights": [0.25, 0.75],
            "deviation_threshold": 0.5,
        },
    )
    assert result.observed_value == pytest.approx(0.65)
    assert result.summary["components"] == [0.2, 0.8]
    with pytest.raises(StatisticalMethodError):
        method.execute(
            [0.2],
            {"components": [0.2], "weights": [-1], "deviation_threshold": 0.5},
        )


def test_structured_non_success_evaluation_statuses() -> None:
    insufficient = statistical_execution_service.evaluate(
        StatisticalEvaluateRequest(method_code="IQR_RULE", values=[1, 2])
    )
    unsupported = statistical_execution_service.evaluate(
        StatisticalEvaluateRequest(method_code="NOT_REGISTERED", values=[1, 2])
    )
    assert insufficient.status == "insufficient_data"
    assert insufficient.error_code == "INSUFFICIENT_DATA"
    assert unsupported.status == "unsupported"
    assert unsupported.error_code == "UNSUPPORTED_METHOD"


def test_registry_accepts_explicit_new_bounded_method_only() -> None:
    registry = default_statistical_method_registry()
    method = BoundedStatisticalMethod(
        StatisticalMethodMetadata(
            "CUSTOM_BOUNDED",
            "Custom Bounded",
            "1.0",
            "DESCRIPTIVE_STATISTICS",
            1,
        )
    )
    registry.register(method)
    with pytest.raises(UnsupportedStatisticalMethodError):
        method.execute([1], {})
