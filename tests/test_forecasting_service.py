from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from governed_provenance_helpers import add_eligible_dataset_version
from sqlalchemy.orm import Session

from app.models.oikb import OIKBDefinition, OIKBDefinitionVersion
from app.models.trust import AnalyticalReadinessDecision, TrustAssessment
from app.schemas.contracts import OrganizationCreate
from app.schemas.forecasting import (
    ForecastActualCreate,
    ForecastExecutionCreate,
    ForecastObservationInput,
    ForecastPeriodStatus,
    ForecastScenarioCreate,
)
from app.schemas.ingestion import DatasetCreate
from app.schemas.source_systems import SourceSystemCreate
from app.services.forecasting_service import (
    ForecastingServiceError,
    TimeSeriesPreparationService,
    forecast_execution_service,
)
from app.services.ingestion_service import DatasetService
from app.services.organization_service import OrganizationService
from app.services.source_system_service import SourceSystemService

_GOVERNED_DATASETS: dict[UUID, tuple[UUID, UUID]] = {}


def foundation(db: Session, slug: str = "forecast-service") -> tuple[UUID, UUID, UUID, UUID]:
    actor = uuid4()
    organization = OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug,
            slug=slug,
            country_code="US",
            default_currency="USD",
            timezone="UTC",
        ),
    )
    source = SourceSystemService().create(
        db,
        organization.id,
        SourceSystemCreate(
            name="Forecast ERP",
            code=f"forecast-{slug.replace('-', '')[-8:]}",
            system_type="erp",
            integration_method="api",
        ),
        actor,
    )
    source.status = "active"
    db.commit()
    dataset = DatasetService().create(
        db,
        organization.id,
        DatasetCreate(
            source_system_id=source.id,
            name="Forecast history",
            code=f"forecast-history-{slug.replace('-', '')[-8:]}",
            domain="operations",
            dataset_type="time_series",
            default_currency="USD",
        ),
        actor,
    )
    version = add_eligible_dataset_version(
        db, organization.id, source.id, dataset.id, actor, checksum="d" * 64
    )
    trust = TrustAssessment(
        organization_id=organization.id,
        dataset_id=dataset.id,
        status="completed",
        overall_score=95,
        assessed_row_count=24,
        passed_rule_count=3,
    )
    db.add(trust)
    db.flush()
    readiness = AnalyticalReadinessDecision(
        organization_id=organization.id,
        trust_assessment_id=trust.id,
        analytical_level="forecasting",
        readiness_status="ready",
        blocking_rule_codes=[],
        warning_rule_codes=[],
        explanation="Forecast-ready history.",
    )
    db.add(readiness)
    definition = OIKBDefinition(
        stable_code="SHARED.FORECASTING.UNIVARIATE_DEMAND",
        name="Univariate demand",
        description="Test forecast definition.",
        knowledge_class="forecasting_method",
        analytical_level="forecasting",
        domain="forecasting",
        subdomain="demand",
        owner_organization_id=organization.id,
        scope_type="organization",
        scope_key=f"organization:{organization.id}",
        is_system_definition=False,
        created_by=actor,
    )
    db.add(definition)
    db.flush()
    db.add(
        OIKBDefinitionVersion(
            definition_id=definition.id,
            semantic_version="1.0.0",
            lifecycle_status="active",
            quality_level="provisional",
            effective_from=datetime.now(UTC) - timedelta(days=1),
            expression_schema={"operation": "forecast", "candidate_methods": ["NAIVE"]},
            output_type="forecast_series",
            output_unit="count",
            rounding_policy={"decimal_places": 4},
            null_policy="structured_null",
            zero_denominator_policy="structured_null",
            trust_requirement={"minimum_status": "completed"},
            readiness_requirement={"analytical_level": "forecasting"},
            fingerprint="f" * 64,
            validation_satisfied=True,
            created_by=actor,
            activated_by=actor,
            activated_at=datetime.now(UTC),
        )
    )
    db.commit()
    _GOVERNED_DATASETS[trust.id] = (dataset.id, version.id)
    return organization.id, trust.id, readiness.id, actor


def payload(
    trust_id: UUID, readiness_id: UUID, fingerprint: str = "d" * 64
) -> ForecastExecutionCreate:
    start = datetime(2025, 1, 1, tzinfo=UTC)
    dataset_id, dataset_version_id = _GOVERNED_DATASETS.get(trust_id, (uuid4(), uuid4()))
    return ForecastExecutionCreate(
        definition_code="SHARED.FORECASTING.UNIVARIATE_DEMAND",
        trust_assessment_id=trust_id,
        readiness_assessment_id=readiness_id,
        dataset_id=dataset_id,
        dataset_version_id=dataset_version_id,
        target_code="completed_jobs",
        forecast_horizon=3,
        candidate_methods=["NAIVE", "HOLT_LINEAR_TREND"],
        primary_metric="WAPE",
        backtest_folds=3,
        observations=[
            ForecastObservationInput(
                timestamp=start + timedelta(days=30 * index),
                value=100 + index * 5,
                unit="count",
            )
            for index in range(12)
        ],
        correlation_id=f"forecast-{fingerprint[:8]}",
    )


def test_execution_is_reproducible_explainable_and_tenant_scoped(db: Session) -> None:
    organization_id, trust_id, readiness_id, actor = foundation(db)
    request = payload(trust_id, readiness_id)
    execution = forecast_execution_service.execute(db, organization_id, request, actor)
    repeated = forecast_execution_service.execute(db, organization_id, request, actor)
    assert execution.status == "succeeded"
    assert repeated.id == execution.id
    assert execution.selected_method_code in {"NAIVE", "HOLT_LINEAR_TREND"}
    assert len(execution.points) == 3
    assert execution.explanation["naive_benchmark"] is not None
    assert execution.prepared_series_fingerprint
    with pytest.raises(ForecastingServiceError, match="not found"):
        forecast_execution_service.get(db, uuid4(), execution.id)


def test_scenario_preserves_baseline_and_actuals_are_auditable(db: Session) -> None:
    organization_id, trust_id, readiness_id, actor = foundation(db, "forecast-scenario")
    execution = forecast_execution_service.execute(
        db, organization_id, payload(trust_id, readiness_id, "e" * 64), actor
    )
    baseline = [float(point.point_forecast) for point in execution.points]
    scenario = forecast_execution_service.create_scenario(
        db,
        organization_id,
        execution.id,
        ForecastScenarioCreate(
            scenario_code="HIGH",
            name="High demand",
            description="Demand is ten percent higher.",
            adjustment_type="PERCENTAGE",
            adjustment_amount=10,
            effective_from=execution.forecast_start,
            effective_to=execution.forecast_end,
        ),
        actor,
    )
    assert scenario.scenario_code == "HIGH"
    db.refresh(execution)
    assert [
        float(point.point_forecast) for point in execution.points if point.scenario_code == "BASE"
    ] == baseline
    point = next(point for point in execution.points if point.scenario_code == "BASE")
    actual = forecast_execution_service.register_actual(
        db,
        organization_id,
        point.id,
        ForecastActualCreate(
            actual_reference="dataset:actuals:period-1",
            actual_value=float(point.point_forecast) + 2,
            dataset_id=execution.dataset_id,
            dataset_version_id=execution.dataset_version_id,
        ),
    )
    assert actual.actual_status == "evaluated"


def test_missing_duplicate_partial_and_history_readiness_are_explicit(db: Session) -> None:
    organization_id, trust_id, readiness_id, actor = foundation(db, "forecast-readiness")
    request = payload(trust_id, readiness_id, "c" * 64)
    request.observations[2].value = None
    with pytest.raises(ForecastingServiceError, match="Missing periods"):
        forecast_execution_service.execute(db, organization_id, request, actor)
    request = payload(trust_id, readiness_id, "b" * 64)
    request.observations[2].timestamp = request.observations[1].timestamp
    with pytest.raises(ForecastingServiceError, match="Duplicate"):
        forecast_execution_service.execute(db, organization_id, request, actor)


def test_preparation_preserves_timestamps_when_interior_rows_are_excluded() -> None:
    trust_id, readiness_id = uuid4(), uuid4()
    request = payload(trust_id, readiness_id)
    expected_timestamps = [item.timestamp for item in request.observations]
    request.observations[2].status = ForecastPeriodStatus.PARTIAL
    request.observations[6].confirmed_data_error = True
    request.partial_period_policy = "EXCLUDE"
    request.outlier_policy = "EXCLUDE_CONFIRMED_ERROR"

    prepared = TimeSeriesPreparationService().prepare(request)

    assert prepared.timestamps == [
        timestamp for index, timestamp in enumerate(expected_timestamps) if index not in {2, 6}
    ]
    assert prepared.values == [
        float(100 + index * 5) for index in range(len(request.observations)) if index not in {2, 6}
    ]
    assert len(prepared.timestamps) == len(prepared.values)


def test_forecasting_rejects_readiness_for_another_analytical_level(db: Session) -> None:
    organization_id, trust_id, readiness_id, actor = foundation(db, "forecast-level")
    readiness = db.get(AnalyticalReadinessDecision, readiness_id)
    assert readiness is not None
    readiness.analytical_level = "statistical"
    db.commit()

    with pytest.raises(ForecastingServiceError, match="readiness"):
        forecast_execution_service.execute(
            db,
            organization_id,
            payload(trust_id, readiness_id, "1" * 64),
            actor,
        )


@pytest.mark.parametrize(
    ("start", "grain", "steps", "expected"),
    [
        (
            datetime(2024, 1, 31, tzinfo=UTC),
            "MONTHLY",
            1,
            datetime(2024, 2, 29, tzinfo=UTC),
        ),
        (
            datetime(2025, 11, 30, tzinfo=UTC),
            "QUARTERLY",
            1,
            datetime(2026, 2, 28, tzinfo=UTC),
        ),
        (
            datetime(2024, 2, 29, tzinfo=UTC),
            "ANNUAL",
            1,
            datetime(2025, 2, 28, tzinfo=UTC),
        ),
    ],
)
def test_calendar_period_advancement(
    start: datetime, grain: str, steps: int, expected: datetime
) -> None:
    assert forecast_execution_service._advance_period(start, grain, steps) == expected


def test_calendar_period_advancement_preserves_local_time_across_dst() -> None:
    chicago = ZoneInfo("America/Chicago")
    start = datetime(2026, 2, 15, 8, 30, tzinfo=chicago)

    advanced = forecast_execution_service._advance_period(start, "MONTHLY", 1)

    assert advanced == datetime(2026, 3, 15, 8, 30, tzinfo=chicago)
    assert advanced.utcoffset() != start.utcoffset()


def test_prepared_fingerprint_covers_measurement_and_status_context() -> None:
    trust_id, readiness_id = uuid4(), uuid4()
    baseline = payload(trust_id, readiness_id)
    exact_retry = payload(trust_id, readiness_id)
    changed_unit = payload(trust_id, readiness_id)
    changed_currency = payload(trust_id, readiness_id)
    changed_status = payload(trust_id, readiness_id)
    for item in changed_unit.observations:
        item.unit = "hours"
    for item in changed_currency.observations:
        item.currency_code = "EUR"
    changed_status.observations[4].status = ForecastPeriodStatus.LATE
    preparation = TimeSeriesPreparationService()

    baseline_fingerprint = preparation.prepare(baseline).fingerprint

    assert preparation.prepare(exact_retry).fingerprint == baseline_fingerprint
    assert preparation.prepare(changed_unit).fingerprint != baseline_fingerprint
    assert preparation.prepare(changed_currency).fingerprint != baseline_fingerprint
    assert preparation.prepare(changed_status).fingerprint != baseline_fingerprint


def test_execution_replay_requires_exact_measurement_and_status_context(db: Session) -> None:
    organization_id, trust_id, readiness_id, actor = foundation(db, "forecast-fingerprint")
    baseline = payload(trust_id, readiness_id, "3" * 64)
    first = forecast_execution_service.execute(db, organization_id, baseline, actor)
    exact_retry = forecast_execution_service.execute(
        db, organization_id, payload(trust_id, readiness_id, "3" * 64), actor
    )

    changed_requests = [
        payload(trust_id, readiness_id, "3" * 64),
        payload(trust_id, readiness_id, "3" * 64),
        payload(trust_id, readiness_id, "3" * 64),
    ]
    for item in changed_requests[0].observations:
        item.unit = "hours"
    for item in changed_requests[1].observations:
        item.currency_code = "EUR"
    changed_requests[2].observations[4].status = ForecastPeriodStatus.LATE
    changed = [
        forecast_execution_service.execute(db, organization_id, request, actor)
        for request in changed_requests
    ]

    assert exact_retry.id == first.id
    assert all(item.id != first.id for item in changed)
    assert len({item.id for item in changed}) == 3


def test_persisted_forecast_marks_uncalibrated_intervals_as_insufficient(
    db: Session,
) -> None:
    organization_id, trust_id, readiness_id, actor = foundation(db, "forecast-calibration")
    request = payload(trust_id, readiness_id, "2" * 64)
    start = datetime(2024, 1, 1, tzinfo=UTC)
    request.candidate_methods = ["SEASONAL_NAIVE"]
    request.parameters = {"seasonal_period": 12}
    request.backtest_folds = 1
    request.observations = [
        ForecastObservationInput(
            timestamp=forecast_execution_service._advance_period(start, "MONTHLY", index),
            value=100 + index,
            unit="count",
        )
        for index in range(25)
    ]

    execution = forecast_execution_service.execute(db, organization_id, request, actor)

    assert execution.status == "succeeded"
    assert execution.explanation["interval_status"] == "insufficient_data"
    assert execution.explanation["interval_calibration_size"] == 1
    assert all(point.lower_bound is None for point in execution.points)
    assert all(point.upper_bound is None for point in execution.points)
    assert all(point.interval_level is None for point in execution.points)
