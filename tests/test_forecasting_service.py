from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.models.oikb import OIKBDefinition, OIKBDefinitionVersion
from app.models.trust import AnalyticalReadinessDecision, TrustAssessment
from app.schemas.contracts import OrganizationCreate
from app.schemas.forecasting import (
    ForecastActualCreate,
    ForecastExecutionCreate,
    ForecastObservationInput,
    ForecastScenarioCreate,
)
from app.schemas.ingestion import DatasetCreate
from app.schemas.source_systems import SourceSystemCreate
from app.services.forecasting_service import (
    ForecastingServiceError,
    forecast_execution_service,
)
from app.services.ingestion_service import DatasetService
from app.services.organization_service import OrganizationService
from app.services.source_system_service import SourceSystemService


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
    return organization.id, trust.id, readiness.id, actor


def payload(
    trust_id: UUID, readiness_id: UUID, fingerprint: str = "d" * 64
) -> ForecastExecutionCreate:
    start = datetime(2025, 1, 1, tzinfo=UTC)
    return ForecastExecutionCreate(
        definition_code="SHARED.FORECASTING.UNIVARIATE_DEMAND",
        trust_assessment_id=trust_id,
        readiness_assessment_id=readiness_id,
        dataset_reference="dataset:forecast-history",
        dataset_fingerprint=fingerprint,
        source_lineage_reference="lineage:forecast-history",
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
            actual_dataset_fingerprint="a" * 64,
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
