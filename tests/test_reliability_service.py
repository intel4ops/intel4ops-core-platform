from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.oikb import OIKBDefinition, OIKBDefinitionVersion
from app.models.reliability import ReliabilityExecution
from app.models.trust import AnalyticalReadinessDecision, TrustAssessment
from app.schemas.contracts import OrganizationCreate
from app.schemas.ingestion import DatasetCreate
from app.schemas.reliability import (
    CensoringStatus,
    ReliabilityExecutionCreate,
    ReliabilityObservationInput,
)
from app.schemas.source_systems import SourceSystemCreate
from app.services.ingestion_service import DatasetService
from app.services.organization_service import OrganizationService
from app.services.reliability_service import (
    ReliabilityServiceError,
    reliability_execution_service,
)
from app.services.source_system_service import SourceSystemService


def reliability_foundation(
    db: Session, slug: str = "reliability-service"
) -> tuple[UUID, UUID, UUID, UUID]:
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
            name="Reliability EAM",
            code=f"rel-{slug.replace('-', '')[-8:]}",
            system_type="eam",
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
            name="Reliability history",
            code=f"rel-history-{slug.replace('-', '')[-8:]}",
            domain="maintenance",
            dataset_type="time_series",
        ),
        actor,
    )
    trust = TrustAssessment(
        organization_id=organization.id,
        dataset_id=dataset.id,
        status="completed",
        overall_score=95,
        assessed_row_count=10,
        passed_rule_count=3,
    )
    db.add(trust)
    db.flush()
    readiness = AnalyticalReadinessDecision(
        organization_id=organization.id,
        trust_assessment_id=trust.id,
        analytical_level="reliability",
        readiness_status="ready",
        blocking_rule_codes=[],
        warning_rule_codes=[],
        explanation="Reliability-ready evidence.",
    )
    db.add(readiness)
    definition = OIKBDefinition(
        stable_code="SHARED.RELIABILITY.BASIC_ASSET_RELIABILITY",
        name="Basic asset reliability",
        description="Test reliability definition.",
        knowledge_class="reliability_method",
        analytical_level="reliability",
        domain="reliability",
        subdomain="asset",
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
            expression_schema={"operation": "reliability"},
            output_type="reliability_metrics",
            output_unit="hour",
            rounding_policy={"decimal_places": 6},
            null_policy="structured_null",
            zero_denominator_policy="structured_null",
            trust_requirement={"minimum_status": "completed"},
            readiness_requirement={"analytical_level": "reliability"},
            fingerprint="r" * 64,
            validation_satisfied=True,
            created_by=actor,
            activated_by=actor,
            activated_at=datetime.now(UTC),
        )
    )
    db.commit()
    return organization.id, trust.id, readiness.id, actor


def reliability_payload(
    trust_id: UUID,
    readiness_id: UUID,
    *,
    method_code: str = "BASIC_RELIABILITY_METRICS",
    dataset_fingerprint: str = "d" * 64,
) -> ReliabilityExecutionCreate:
    observed = method_code == "WEIBULL_TWO_PARAMETER"
    return ReliabilityExecutionCreate(
        definition_code="SHARED.RELIABILITY.BASIC_ASSET_RELIABILITY",
        trust_assessment_id=trust_id,
        readiness_assessment_id=readiness_id,
        dataset_reference="dataset:reliability-history",
        dataset_fingerprint=dataset_fingerprint,
        source_lineage_reference="lineage:reliability-history",
        asset_scope_reference="fleet:pumps",
        method_code=method_code,
        observation_window_start=datetime(2026, 1, 1, tzinfo=UTC),
        observation_window_end=datetime(2026, 2, 1, tzinfo=UTC),
        exposure_basis="OPERATING_TIME",
        exposure_unit="hour",
        failure_definition_code="UNPLANNED_FUNCTIONAL_FAILURE",
        observations=[
            ReliabilityObservationInput(
                asset_reference=f"PUMP-{index}",
                asset_class="pump",
                duration=float(10 * index) if observed else None,
                exposure=100,
                downtime=2,
                repair_duration=4,
                failure_count=1,
                repair_count=1,
                event_observed=observed,
                censoring_status=(
                    CensoringStatus.FAILURE_OBSERVED if observed else CensoringStatus.RIGHT_CENSORED
                ),
            )
            for index in range(1, 4)
        ],
        correlation_id=f"rel-{dataset_fingerprint[:8]}",
    )


def test_execution_is_reproducible_tenant_scoped_and_requires_human_review(
    db: Session,
) -> None:
    organization_id, trust_id, readiness_id, actor = reliability_foundation(db)
    request = reliability_payload(trust_id, readiness_id)

    execution = reliability_execution_service.execute(db, organization_id, request, actor)
    repeated = reliability_execution_service.execute(db, organization_id, request, actor)

    assert execution.status == "succeeded"
    assert repeated.id == execution.id
    assert execution.explanation["human_review_required"] is True
    assert execution.explanation["recommended_action_category"] == "HUMAN_REVIEW"
    with pytest.raises(ReliabilityServiceError, match="not found"):
        reliability_execution_service.get(db, uuid4(), execution.id)


def test_readiness_level_status_and_tenant_are_enforced(db: Session) -> None:
    organization_id, trust_id, readiness_id, actor = reliability_foundation(
        db, "reliability-readiness"
    )
    request = reliability_payload(trust_id, readiness_id, dataset_fingerprint="e" * 64)
    readiness = db.get(AnalyticalReadinessDecision, readiness_id)
    assert readiness is not None
    readiness.analytical_level = "forecasting"
    db.commit()
    with pytest.raises(ReliabilityServiceError, match="readiness not found"):
        reliability_execution_service.execute(db, organization_id, request, actor)

    readiness.analytical_level = "reliability"
    readiness.readiness_status = "blocked"
    readiness.explanation = "Critical lineage defect."
    db.commit()
    with pytest.raises(ReliabilityServiceError, match="Critical lineage defect"):
        reliability_execution_service.execute(db, organization_id, request, actor)

    with pytest.raises(ReliabilityServiceError, match="trust assessment"):
        reliability_execution_service.execute(db, uuid4(), request, actor)


def test_censored_weibull_fails_closed_and_records_failed_execution(db: Session) -> None:
    organization_id, trust_id, readiness_id, actor = reliability_foundation(
        db, "reliability-weibull"
    )
    request = reliability_payload(
        trust_id,
        readiness_id,
        method_code="WEIBULL_TWO_PARAMETER",
        dataset_fingerprint="f" * 64,
    )
    request.observations[-1].event_observed = False
    request.observations[-1].censoring_status = CensoringStatus.RIGHT_CENSORED

    with pytest.raises(ReliabilityServiceError, match="does not support censored"):
        reliability_execution_service.execute(db, organization_id, request, actor)

    failed = db.scalar(
        select(ReliabilityExecution).where(
            ReliabilityExecution.organization_id == organization_id,
            ReliabilityExecution.reliability_method_code == "WEIBULL_TWO_PARAMETER",
        )
    )
    assert failed is not None
    assert failed.status == "failed"
    assert failed.failure_code == "METHOD_REJECTED"


def test_changed_lineage_context_does_not_replay_prior_execution(db: Session) -> None:
    organization_id, trust_id, readiness_id, actor = reliability_foundation(
        db, "reliability-fingerprint"
    )
    baseline = reliability_payload(trust_id, readiness_id, dataset_fingerprint="a" * 64)
    first = reliability_execution_service.execute(db, organization_id, baseline, actor)
    changed = reliability_payload(trust_id, readiness_id, dataset_fingerprint="a" * 64)
    changed.source_lineage_reference = "lineage:corrected-history"

    second = reliability_execution_service.execute(db, organization_id, changed, actor)

    assert second.id != first.id
