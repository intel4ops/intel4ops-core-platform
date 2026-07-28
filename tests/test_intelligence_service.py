from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.intelligence import IntelligenceExecutionEvidence
from app.models.trust import AnalyticalLevel, AnalyticalReadinessDecision, ReadinessStatus
from app.schemas.contracts import OrganizationCreate
from app.schemas.ingestion import DatasetCreate
from app.schemas.intelligence import IntelligenceExecutionCreate
from app.schemas.source_systems import SourceSystemCreate
from app.schemas.trust import TrustAssessmentCreate
from app.services.ingestion_service import DatasetService
from app.services.intelligence_service import (
    IntelligenceExecutionService,
    IntelligenceNotFoundError,
)
from app.services.organization_service import OrganizationService
from app.services.source_system_service import SourceSystemService
from app.services.trust_service import TrustAssessmentService


def foundation(db: Session, slug: str) -> tuple[UUID, UUID, UUID]:
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
        SourceSystemCreate(name="ERP", code="erp", system_type="erp", integration_method="api"),
        actor,
    )
    source.status = "active"
    db.commit()
    dataset = DatasetService().create(
        db,
        organization.id,
        DatasetCreate(
            source_system_id=source.id,
            name="Canonical invoices",
            code="canonical-invoices",
            domain="finance",
            dataset_type="transactional",
            default_currency="USD",
        ),
        actor,
    )
    assessment = TrustAssessmentService().create_and_execute(
        db,
        organization.id,
        dataset.id,
        TrustAssessmentCreate(
            records=[{"id": "1", "amount": "10.25"}],
            rule_configurations={
                "required_field_completeness": {"required_fields": ["id", "amount"]},
                "numeric_range_validity": {"numeric_ranges": {"amount": {"minimum": 0}}},
            },
        ),
    )
    return organization.id, dataset.id, assessment.id


def test_execution_is_reproducible_decimal_safe_and_does_not_store_records(
    db: Session,
) -> None:
    organization_id, dataset_id, assessment_id = foundation(db, "intelligence-service")
    service = IntelligenceExecutionService()
    payload = IntelligenceExecutionCreate(
        dataset_id=dataset_id,
        trust_assessment_id=assessment_id,
        execution_type="calculation",
        definition_code="sum",
        records=[{"id": "a", "amount": "0.10"}, {"id": "b", "amount": "0.20"}],
        parameters={"field": "amount"},
        currency="USD",
        idempotency_key="sum-1",
        evidence=[
            {
                "canonical_record_identifier": "invoice:a",
                "contributing_record_count": 2,
            }
        ],
    )
    execution = service.execute(db, organization_id, payload, uuid4())
    duplicate = service.execute(db, organization_id, payload, uuid4())

    assert str(execution.result_value) == "0.300000000000"
    assert execution.status == "completed"
    assert duplicate.id == execution.id
    assert "records" not in execution.parameters_json
    assert len(execution.input_fingerprint) == 64
    evidence = db.scalar(
        select(IntelligenceExecutionEvidence).where(
            IntelligenceExecutionEvidence.execution_id == execution.id
        )
    )
    assert evidence is not None
    assert evidence.organization_id == organization_id


def test_blocked_attempt_is_persisted_without_executing(db: Session) -> None:
    organization_id, dataset_id, assessment_id = foundation(db, "intelligence-blocked")
    readiness = db.scalar(
        select(AnalyticalReadinessDecision).where(
            AnalyticalReadinessDecision.trust_assessment_id == assessment_id,
            AnalyticalReadinessDecision.analytical_level == AnalyticalLevel.ARITHMETIC.value,
        )
    )
    assert readiness is not None
    readiness.readiness_status = ReadinessStatus.BLOCKED.value
    readiness.blocking_rule_codes = ["required_field_completeness"]
    readiness.explanation = "required canonical field is missing"
    db.commit()

    execution = IntelligenceExecutionService().execute(
        db,
        organization_id,
        IntelligenceExecutionCreate(
            dataset_id=dataset_id,
            trust_assessment_id=assessment_id,
            execution_type="calculation",
            definition_code="record_count",
            records=[{"id": "secret-record"}],
        ),
        uuid4(),
    )

    assert execution.status == "blocked"
    assert execution.result_value is None
    assert execution.blocking_rule_codes == ["required_field_completeness"]
    assert execution.non_execution_reason == "required canonical field is missing"


def test_advanced_readiness_does_not_block_valid_arithmetic(db: Session) -> None:
    organization_id, dataset_id, assessment_id = foundation(db, "intelligence-progressive")
    advanced = db.scalar(
        select(AnalyticalReadinessDecision).where(
            AnalyticalReadinessDecision.trust_assessment_id == assessment_id,
            AnalyticalReadinessDecision.analytical_level == AnalyticalLevel.PREDICTIVE.value,
        )
    )
    assert advanced is not None
    advanced.readiness_status = ReadinessStatus.BLOCKED.value
    db.commit()

    execution = IntelligenceExecutionService().execute(
        db,
        organization_id,
        IntelligenceExecutionCreate(
            dataset_id=dataset_id,
            trust_assessment_id=assessment_id,
            execution_type="calculation",
            definition_code="record_count",
            records=[{"id": "1"}],
        ),
        uuid4(),
    )
    assert execution.status == "completed"
    assert str(execution.result_value) == "1.000000000000"


def test_execution_queries_and_references_are_tenant_scoped(db: Session) -> None:
    first_org, first_dataset, first_assessment = foundation(db, "intelligence-first")
    second_org, _, _ = foundation(db, "intelligence-second")
    service = IntelligenceExecutionService()
    execution = service.execute(
        db,
        first_org,
        IntelligenceExecutionCreate(
            dataset_id=first_dataset,
            trust_assessment_id=first_assessment,
            execution_type="rule",
            definition_code="threshold_exceeded",
            parameters={"value": 12, "threshold": 10},
        ),
        uuid4(),
    )

    assert service.list(db, first_org) == [execution]
    assert service.list(db, second_org) == []
    try:
        service.get(db, second_org, execution.id)
    except IntelligenceNotFoundError:
        pass
    else:
        raise AssertionError("Cross-tenant execution lookup was not hidden")
