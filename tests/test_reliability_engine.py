import math

import pytest

from app.engines.reliability_engine import (
    ReliabilityMethodError,
    default_reliability_method_registry,
)
from app.schemas.reliability import ReliabilityExecutionCreate


def test_registry_is_bounded_versioned_and_rejects_unknown() -> None:
    registry = default_reliability_method_registry()
    codes = {item.metadata.method_code for item in registry.list()}
    assert {
        "BASIC_RELIABILITY_METRICS",
        "KAPLAN_MEIER",
        "WEIBULL_TWO_PARAMETER",
        "REPEAT_FAILURE",
        "BAD_ACTOR_COMPOSITE",
        "COMPOSITE_ASSET_HEALTH",
        "DOWNTIME_RISK",
    } <= codes
    with pytest.raises(ReliabilityMethodError, match="Unsupported"):
        registry.get("USER_SUPPLIED_CODE")


def test_basic_metrics_preserve_numerator_denominator_and_zero_failure_caution() -> None:
    method = default_reliability_method_registry().get("BASIC_RELIABILITY_METRICS")
    result = method.execute(
        [
            {
                "exposure": 1000,
                "downtime": 20,
                "repair_duration": 10,
                "failure_count": 2,
                "repair_count": 2,
            }
        ]
    )
    assert result.values["FAILURE_RATE"] == pytest.approx(0.002)
    assert result.values["MTBF"] == pytest.approx(490)
    assert result.values["MTTR"] == pytest.approx(5)
    assert result.values["OPERATIONAL_AVAILABILITY"] == pytest.approx(0.98)
    assert result.diagnostics == {
        "numerator_failure_count": 2,
        "denominator_exposure": 1000,
    }
    zero = method.execute([{"exposure": 100, "failure_count": 0}])
    assert zero.values["MTBF"] is None
    assert zero.limitations


@pytest.mark.parametrize(
    "observation",
    [
        {"exposure": -1},
        {"exposure": math.nan},
        {"exposure": math.inf},
        {"exposure": 1, "downtime": -1},
    ],
)
def test_basic_metrics_reject_unsafe_numbers(observation: dict[str, object]) -> None:
    method = default_reliability_method_registry().get("BASIC_RELIABILITY_METRICS")
    with pytest.raises(ReliabilityMethodError):
        method.execute([observation])


def test_kaplan_meier_handles_right_censoring_deterministically() -> None:
    method = default_reliability_method_registry().get("KAPLAN_MEIER")
    observations: list[dict[str, object]] = [
        {"duration": 5, "event_observed": True},
        {"duration": 8, "event_observed": False},
        {"duration": 10, "event_observed": True},
    ]
    first = method.execute(observations)
    second = method.execute(list(reversed(observations)))
    assert first == second
    assert first.values["FINAL_SURVIVAL"] == pytest.approx(0)
    points = first.diagnostics["survival_points"]
    assert isinstance(points, list)
    assert points[1]["censored"] == 1


def test_weibull_fit_is_positive_and_b10_precedes_b50() -> None:
    method = default_reliability_method_registry().get("WEIBULL_TWO_PARAMETER")
    result = method.execute(
        [
            {"duration": 10, "event_observed": True},
            {"duration": 20, "event_observed": True},
            {"duration": 40, "event_observed": True},
            {"duration": 50, "event_observed": False},
        ]
    )
    assert result.values["WEIBULL_SHAPE"] > 0  # type: ignore[operator]
    assert result.values["WEIBULL_SCALE"] > 0  # type: ignore[operator]
    assert result.values["B10"] < result.values["B50"]  # type: ignore[operator]
    assert result.diagnostics["censored_count"] == 1


def test_weibull_rejects_insufficient_and_constant_failures() -> None:
    method = default_reliability_method_registry().get("WEIBULL_TWO_PARAMETER")
    with pytest.raises(ReliabilityMethodError, match="Insufficient"):
        method.execute([{"duration": 10, "event_observed": True}])
    with pytest.raises(ReliabilityMethodError, match="non-constant"):
        method.execute([{"duration": 10, "event_observed": True} for _ in range(3)])


def test_composite_score_requires_bounded_normalized_weights() -> None:
    method = default_reliability_method_registry().get("COMPOSITE_ASSET_HEALTH")
    result = method.execute(
        [
            {"normalized_value": 0.8, "weight": 0.6},
            {"normalized_value": 0.2, "weight": 0.4},
        ]
    )
    assert result.values == {
        "RISK_SCORE": pytest.approx(56),
        "ASSET_HEALTH_SCORE": pytest.approx(44),
    }
    with pytest.raises(ReliabilityMethodError, match="sum to one"):
        method.execute([{"normalized_value": 0.5, "weight": 0.5}])


def test_execution_schema_enforces_censoring_window_and_asset_class() -> None:
    base = {
        "definition_code": "SHARED.RELIABILITY.BASIC_ASSET_RELIABILITY",
        "trust_assessment_id": "10000000-0000-0000-0000-000000000001",
        "readiness_assessment_id": "10000000-0000-0000-0000-000000000002",
        "dataset_reference": "dataset:test",
        "dataset_fingerprint": "a" * 64,
        "source_lineage_reference": "lineage:test",
        "asset_scope_reference": "fleet:test",
        "method_code": "BASIC_RELIABILITY_METRICS",
        "observation_window_start": "2026-01-01T00:00:00Z",
        "observation_window_end": "2026-02-01T00:00:00Z",
        "exposure_basis": "OPERATING_TIME",
        "exposure_unit": "hour",
        "failure_definition_code": "UNPLANNED_FUNCTIONAL_FAILURE",
        "observations": [
            {
                "asset_reference": "A-1",
                "asset_class": "pump",
                "failure_count": 1,
                "event_observed": True,
                "censoring_status": "FAILURE_OBSERVED",
            }
        ],
        "correlation_id": "corr-1",
    }
    assert ReliabilityExecutionCreate.model_validate(base).observations[0].event_observed
    invalid = dict(base)
    invalid["observations"] = [
        {
            "asset_reference": "A-1",
            "asset_class": "pump",
            "event_observed": False,
            "censoring_status": "FAILURE_OBSERVED",
        }
    ]
    with pytest.raises(ValueError, match="event_observed"):
        ReliabilityExecutionCreate.model_validate(invalid)
