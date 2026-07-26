from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.schemas.contracts import OrganizationCreate
from app.schemas.ingestion import DatasetCreate, IngestionBatchCreate
from app.schemas.source_systems import SourceSystemCreate
from app.schemas.trust import TrustAssessmentCreate
from app.services.ingestion_service import DatasetService, IngestionBatchService
from app.services.organization_service import OrganizationService
from app.services.source_system_service import SourceSystemService
from app.services.trust_service import (
    NoApplicableTrustRulesError,
    TrustAssessmentService,
    TrustNotFoundError,
    TrustTenantMismatchError,
)


def trust_foundation(db: Session, slug: str) -> tuple[UUID, UUID, UUID]:
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
            name="Source",
            code="source",
            system_type="erp",
            integration_method="api",
        ),
        actor,
    )
    batch = IngestionBatchService().create(
        db,
        organization.id,
        IngestionBatchCreate(
            source_system_id=source.id,
            batch_number="batch-001",
            ingestion_method="api",
            trigger_type="manual",
        ),
        actor,
    )
    dataset = DatasetService().create(
        db,
        organization.id,
        DatasetCreate(
            source_system_id=source.id,
            name="Shared transactions",
            code="transactions",
            domain="operations",
            dataset_type="transactional",
        ),
        actor,
    )
    return organization.id, batch.id, dataset.id


def assessment_payload() -> TrustAssessmentCreate:
    return TrustAssessmentCreate(
        evaluation_time=datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
        records=[
            {
                "id": "1",
                "amount": 10,
                "currency": "USD",
                "source_id": "source-1",
            },
            {
                "id": "2",
                "amount": None,
                "currency": "USD",
                "source_id": "source-2",
            },
        ],
        rule_configurations={
            "required_field_completeness": {
                "required_fields": ["id", "amount"],
                "identifier_field": "id",
            },
            "primary_identifier_uniqueness": {"identifier_field": "id"},
            "numeric_range_validity": {
                "numeric_ranges": {"amount": {"minimum": 0, "maximum": 100}},
                "identifier_field": "id",
            },
            "currency_code_validity": {
                "currency_fields": ["currency"],
                "identifier_field": "id",
            },
            "lineage_completeness": {
                "lineage_fields": ["source_id"],
                "identifier_field": "id",
            },
        },
    )


def test_assessment_orchestration_scores_evidence_and_readiness(db: Session) -> None:
    organization_id, batch_id, dataset_id = trust_foundation(db, "trust-service")
    payload = assessment_payload().model_copy(update={"ingestion_batch_id": batch_id})
    service = TrustAssessmentService()
    assessment = service.create_and_execute(db, organization_id, dataset_id, payload)
    assert assessment.status == "completed_with_warnings"
    assert assessment.assessed_row_count == 2
    assert assessment.overall_score is not None
    assert 0 <= assessment.overall_score <= 100
    assert assessment.failed_rule_count == 1
    results = service.rule_results(db, organization_id, assessment.id)
    assert len(results) == 5
    assert {result.rule_code for result in results} == set(payload.rule_configurations)
    evidence, total = service.evidence(db, organization_id, assessment.id)
    assert total == 1
    assert evidence[0].field_name == "amount"
    decisions = service.readiness(db, organization_id, assessment.id)
    assert len(decisions) == 7
    assert service.latest(db, organization_id, dataset_id).id == assessment.id


def test_no_applicable_rules_and_cross_tenant_dataset_are_rejected(
    db: Session,
) -> None:
    first_id, _, first_dataset = trust_foundation(db, "trust-tenant-first")
    second_id, _, _ = trust_foundation(db, "trust-tenant-second")
    service = TrustAssessmentService()
    with pytest.raises(NoApplicableTrustRulesError):
        service.create_and_execute(
            db,
            first_id,
            first_dataset,
            TrustAssessmentCreate(
                records=[],
                rule_configurations={"unknown_rule": {"field": "id"}},
            ),
        )
    with pytest.raises(TrustNotFoundError):
        service.create_and_execute(db, second_id, first_dataset, assessment_payload())


def test_assessment_resources_are_strictly_tenant_scoped(db: Session) -> None:
    first_id, _, dataset_id = trust_foundation(db, "trust-scope-first")
    second_id, _, _ = trust_foundation(db, "trust-scope-second")
    service = TrustAssessmentService()
    assessment = service.create_and_execute(db, first_id, dataset_id, assessment_payload())
    for operation in (
        lambda: service.get(db, second_id, assessment.id),
        lambda: service.rule_results(db, second_id, assessment.id),
        lambda: service.evidence(db, second_id, assessment.id),
        lambda: service.readiness(db, second_id, assessment.id),
    ):
        with pytest.raises(TrustNotFoundError):
            operation()


def test_cross_tenant_ingestion_batch_is_rejected(db: Session) -> None:
    first_id, _, dataset_id = trust_foundation(db, "trust-batch-first")
    _, second_batch, _ = trust_foundation(db, "trust-batch-second")
    payload = assessment_payload().model_copy(update={"ingestion_batch_id": second_batch})
    with pytest.raises(TrustTenantMismatchError):
        TrustAssessmentService().create_and_execute(db, first_id, dataset_id, payload)
