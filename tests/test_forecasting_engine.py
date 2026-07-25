import math

import pytest

from app.engines.forecasting_engine import (
    ForecastingMethodError,
    default_forecasting_method_registry,
)
from app.schemas.forecasting import ForecastEvaluateRequest
from app.services.forecasting_service import (
    forecast_execution_service,
    forecast_reconciliation_service,
)


def test_registry_is_bounded_versioned_and_rejects_duplicates() -> None:
    registry = default_forecasting_method_registry()
    assert len(registry.list()) == 19
    assert registry.get("NAIVE").metadata.method_version == "1.0"
    assert registry.get("BOUNDED_MULTIVARIATE_LINEAR_REGRESSION").metadata.supported is False
    with pytest.raises(ForecastingMethodError, match="Duplicate"):
        registry.register(registry.get("NAIVE"))
    with pytest.raises(ForecastingMethodError, match="UNSUPPORTED"):
        registry.get("ARIMA")


@pytest.mark.parametrize(
    "method,parameters",
    [
        ("NAIVE", {}),
        ("SEASONAL_NAIVE", {"seasonal_period": 3}),
        ("DRIFT", {}),
        ("HISTORICAL_MEAN", {}),
        ("HISTORICAL_MEDIAN", {}),
        ("SIMPLE_MOVING_AVERAGE", {"window": 3}),
        ("WEIGHTED_MOVING_AVERAGE", {"window": 3}),
        ("EXPANDING_MEAN", {}),
        ("SIMPLE_EXPONENTIAL_SMOOTHING", {"alpha": 0.4}),
        ("HOLT_LINEAR_TREND", {}),
        ("HOLT_DAMPED_TREND", {}),
        ("HOLT_WINTERS_ADDITIVE", {"seasonal_period": 3}),
        ("LINEAR_TIME_TREND", {}),
        ("POLYNOMIAL_TIME_TREND_DEGREE_2", {}),
        ("SEASONAL_DUMMY_REGRESSION", {"seasonal_period": 3}),
        ("CROSTON", {}),
        ("SBA_CROSTON", {}),
    ],
)
def test_supported_methods_are_deterministic_and_finite(
    method: str, parameters: dict[str, object]
) -> None:
    values = [10.0, 12.0, 11.0, 14.0, 16.0, 15.0, 18.0, 20.0, 19.0, 22.0, 24.0, 23.0]
    implementation = default_forecasting_method_registry().get(method)
    first = implementation.forecast(values, 3, parameters)
    second = implementation.forecast(values, 3, parameters)
    assert first == second
    assert len(first.values) == 3
    assert all(math.isfinite(value) for value in first.values)


def test_intervals_and_undefined_configuration_have_structured_results() -> None:
    result = forecast_execution_service.evaluate(
        ForecastEvaluateRequest(method_code="NAIVE", values=[1, 2, 3, 4], horizon=2)
    )
    assert result.status == "succeeded"
    assert len(result.intervals) == 2
    unsupported = forecast_execution_service.evaluate(
        ForecastEvaluateRequest(method_code="ARIMA", values=[1, 2, 3, 4])
    )
    assert unsupported.status == "unsupported"
    assert unsupported.error_code == "UNSUPPORTED"


def test_ensemble_requires_governed_weights() -> None:
    method = default_forecasting_method_registry().get("WEIGHTED_FORECAST_ENSEMBLE")
    result = method.forecast(
        [1, 2, 3],
        2,
        {"component_forecasts": [[4, 5], [6, 7]], "weights": [0.25, 0.75]},
    )
    assert result.values == [5.5, 6.5]
    with pytest.raises(ForecastingMethodError, match="WEIGHTS"):
        method.forecast(
            [1, 2, 3],
            2,
            {"component_forecasts": [[4, 5], [6, 7]], "weights": [0.5, 0.6]},
        )


def test_bounded_parent_child_reconciliation() -> None:
    bottom_up = forecast_reconciliation_service.reconcile(
        {"branch-a": 60, "branch-b": 40}, method="BOTTOM_UP"
    )
    assert bottom_up["parent_forecast"] == 100
    top_down = forecast_reconciliation_service.reconcile(
        {"branch-a": 60, "branch-b": 40},
        method="TOP_DOWN_PROPORTIONAL",
        parent_forecast=120,
    )
    assert top_down["children"] == {"branch-a": 72, "branch-b": 48}
