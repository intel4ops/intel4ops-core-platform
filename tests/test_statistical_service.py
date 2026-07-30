from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from conftest import IdentityState
from fastapi.testclient import TestClient
from governed_provenance_helpers import add_eligible_dataset_version
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.oikb import (
    OIKBDefinition,
    OIKBDefinitionVersion,
    OIKBEvidenceRequirement,
    OIKBInputRequirement,
)
from app.models.statistics import StatisticalObservation
from app.models.trust import AnalyticalReadinessDecision, TrustAssessment
from app.schemas.contracts import OrganizationCreate
from app.schemas.ingestion import DatasetCreate
from app.schemas.source_systems import SourceSystemCreate
from app.schemas.statistics import (
    StatisticalExecutionCreate,
    StatisticalObservationInput,
)
from app.services.ingestion_service import DatasetService
from app.services.organization_service import OrganizationService
from app.services.source_system_service import SourceSystemService
from app.services.statistical_service import statistical_execution_service

_GOVERNED_DATASETS: dict[UUID, tuple[UUID, UUID]] = {}


def statistical_foundation(
    db: Session, slug: str = "statistical-service"
) -> tuple[UUID, UUID, UUID, UUID, UUID]:
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
            name="Statistical ERP",
            code=f"statistical-erp-{slug.replace('-', '')[-8:]}",
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
            name="Governed statistical observations",
            code=f"statistical-observations-{slug.replace('-', '')[-8:]}",
            domain="operations",
            dataset_type="transactional",
            default_currency="USD",
        ),
        actor,
    )
    dataset_version = add_eligible_dataset_version(
        db, organization.id, source.id, dataset.id, actor, checksum="b" * 64
    )
    trust = TrustAssessment(
        organization_id=organization.id,
        dataset_id=dataset.id,
        status="completed",
        overall_score=95,
        lineage_score=100,
        assessed_row_count=10,
        passed_rule_count=2,
    )
    db.add(trust)
    db.flush()
    readiness = AnalyticalReadinessDecision(
        organization_id=organization.id,
        trust_assessment_id=trust.id,
        analytical_level="statistical",
        readiness_status="ready",
        blocking_rule_codes=[],
        warning_rule_codes=[],
        explanation="Explicitly eligible for governed statistical execution.",
    )
    db.add(readiness)
    definition = OIKBDefinition(
        stable_code="SHARED.STATISTICS.ROBUST_OUTLIER",
        name="Robust outlier",
        description="Test governed statistical definition.",
        knowledge_class="statistical_method",
        analytical_level="statistical",
        domain="statistics",
        subdomain="outlier",
        owner_organization_id=organization.id,
        scope_type="organization",
        scope_key=f"organization:{organization.id}",
        is_system_definition=False,
        created_by=actor,
    )
    db.add(definition)
    db.flush()
    version = OIKBDefinitionVersion(
        definition_id=definition.id,
        semantic_version="1.0.0",
        lifecycle_status="active",
        quality_level="provisional",
        effective_from=datetime.now(UTC) - timedelta(days=1),
        expression_schema={
            "operation": "MODIFIED_Z_SCORE",
            "method_version": "1.0",
            "baseline_type": "historical_self",
        },
        output_type="anomaly_assessment",
        output_unit="score",
        rounding_policy={"decimal_places": 5},
        null_policy="exclude_with_threshold",
        zero_denominator_policy="structured_null",
        trust_requirement={"minimum_status": "completed"},
        readiness_requirement={
            "analytical_level": "statistical",
            "maximum_missing_percentage": 10,
        },
        fingerprint="a" * 64,
        validation_satisfied=True,
        created_by=actor,
        activated_by=actor,
        activated_at=datetime.now(UTC),
    )
    db.add(version)
    db.flush()
    db.add(
        OIKBInputRequirement(
            definition_version_id=version.id,
            input_code="observed_value",
            canonical_entity="observation",
            canonical_field="value",
            expected_type="decimal",
            expected_unit="USD",
            minimum_record_count=5,
            allowed_null_percentage=10,
        )
    )
    db.add(
        OIKBEvidenceRequirement(
            definition_version_id=version.id,
            evidence_type="statistical_execution_trace",
            requirement_code="STATISTICAL_TRACE",
            description="Aggregate statistical trace.",
            minimum_count=1,
            retention_class="governed_reference",
        )
    )
    db.commit()
    _GOVERNED_DATASETS[trust.id] = (dataset.id, dataset_version.id)
    return organization.id, dataset.id, trust.id, readiness.id, actor


def execution_payload(
    trust_id: UUID,
    readiness_id: UUID,
    *,
    key: str,
    known_event: bool = False,
) -> StatisticalExecutionCreate:
    dataset_id, dataset_version_id = _GOVERNED_DATASETS[trust_id]
    return StatisticalExecutionCreate(
        definition_code="SHARED.STATISTICS.ROBUST_OUTLIER",
        definition_version="1.0.0",
        trust_assessment_id=trust_id,
        readiness_assessment_id=readiness_id,
        dataset_id=dataset_id,
        dataset_version_id=dataset_version_id,
        observations=[
            StatisticalObservationInput(
                value=value,
                entity_reference=f"entity-{index}",
                period_reference=f"period-{index}",
                unit="USD",
                currency="USD",
                known_event=known_event and index == 5,
                materiality=0.8,
            )
            for index, value in enumerate([10, 11, 9, 10, 10, 100])
        ],
        parameters={
            "deviation_threshold": 3.5,
            "minimum_confidence": 0.1,
            "persistence_count": 3,
            "recurrence_count": 2,
        },
        correlation_id=f"correlation-{key}",
        idempotency_key=key,
    )


def test_statistical_execution_is_explainable_reproducible_and_suppressible(
    db: Session,
) -> None:
    organization_id, _, trust_id, readiness_id, actor = statistical_foundation(db)
    payload = execution_payload(trust_id, readiness_id, key="statistical-execution")
    execution = statistical_execution_service.execute(db, organization_id, payload, actor)
    repeated = statistical_execution_service.execute(db, organization_id, payload, actor)
    assert execution.status == "succeeded"
    assert repeated.id == execution.id
    baselines = statistical_execution_service.baselines_for(db, organization_id, execution.id)
    observations = statistical_execution_service.observations_for(db, organization_id, execution.id)
    assert len(baselines) == 1
    assert baselines[0].baseline_fingerprint
    assert len(observations) == 1
    observation = observations[0]
    assert observation.is_anomaly
    assert 0 <= float(observation.statistical_score) <= 1
    assert float(observation.confidence_score) != float(observation.materiality_score)
    assert len(observation.score_components) == 6
    assert observation.evidence_references[0]["aggregate_only"] is True
    assert "alternative_explanations" in observation.explanation
    explanation = str(observation.explanation).lower()
    assert "theft occurred" not in explanation
    assert "fraud occurred" not in explanation
    assert "not causation" in explanation


def test_false_positive_known_event_and_explicit_statistical_readiness(
    db: Session,
) -> None:
    organization_id, _, trust_id, readiness_id, actor = statistical_foundation(
        db, "statistical-controls"
    )
    suppressed = statistical_execution_service.execute(
        db,
        organization_id,
        execution_payload(trust_id, readiness_id, key="known-event", known_event=True),
        actor,
    )
    observation = statistical_execution_service.observations_for(
        db, organization_id, suppressed.id
    )[0]
    assert not observation.is_anomaly
    suppression_reasons = observation.explanation["suppression_reasons"]
    assert isinstance(suppression_reasons, list)
    assert "known_event_exclusion" in suppression_reasons

    readiness = db.get(AnalyticalReadinessDecision, readiness_id)
    assert readiness is not None
    readiness.analytical_level = "arithmetic"
    db.commit()
    not_ready = statistical_execution_service.execute(
        db,
        organization_id,
        execution_payload(trust_id, readiness_id, key="wrong-readiness"),
        actor,
    )
    assert not_ready.status == "not_ready"
    assert not_ready.blocked_reason == "Explicit statistical readiness is required"


def test_statistical_api_tenant_scope_review_and_suppression(
    db: Session, client: TestClient, identity: IdentityState
) -> None:
    organization_id, _, trust_id, readiness_id, _ = statistical_foundation(db, "statistical-api")
    other_id, _, _, _, _ = statistical_foundation(db, "statistical-other")
    identity.is_platform_admin = True
    payload = execution_payload(trust_id, readiness_id, key="api-execution")
    created = client.post(
        f"/api/v1/organizations/{organization_id}/statistics/executions",
        json=payload.model_dump(mode="json"),
    )
    assert created.status_code == 201
    execution_id = created.json()["id"]
    detail = client.get(
        f"/api/v1/organizations/{organization_id}/statistics/executions/{execution_id}"
    )
    assert detail.status_code == 200
    observation_id = detail.json()["observations"][0]["id"]
    assert (
        client.get(
            f"/api/v1/organizations/{other_id}/statistics/executions/{execution_id}"
        ).status_code
        == 404
    )
    review = client.post(
        f"/api/v1/organizations/{organization_id}/statistics/observations/{observation_id}/review",
        json={
            "review_status": "completed",
            "classification": "operational_variation",
            "was_actionable": True,
            "was_false_positive": False,
            "notes": "Reviewed with source lineage.",
        },
    )
    assert review.status_code == 201
    suppression = client.post(
        f"/api/v1/organizations/{organization_id}/statistics/"
        f"observations/{observation_id}/suppress",
        json={
            "suppression_reason": "Approved business event",
            "suppression_scope": {"event": "planned"},
            "effective_from": datetime.now(UTC).isoformat(),
            "effective_to": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        },
    )
    assert suppression.status_code == 201
    methods = client.get(f"/api/v1/organizations/{organization_id}/statistics/methods")
    assert methods.status_code == 200
    assert len(methods.json()) == 40


def test_observation_queries_are_always_organization_scoped(db: Session) -> None:
    first, _, trust_id, readiness_id, actor = statistical_foundation(db, "statistical-first")
    second, _, _, _, _ = statistical_foundation(db, "statistical-second")
    execution = statistical_execution_service.execute(
        db,
        first,
        execution_payload(trust_id, readiness_id, key="scope"),
        actor,
    )
    observation_id = db.scalar(
        select(StatisticalObservation.id).where(
            StatisticalObservation.statistical_execution_id == execution.id
        )
    )
    assert observation_id is not None
    try:
        statistical_execution_service.observation(db, second, observation_id)
    except ValueError as exc:
        assert "not found" in str(exc).lower()
    else:
        raise AssertionError("Cross-tenant observation lookup unexpectedly succeeded")
