from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from conftest import IdentityState
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.models.entities import Finding
from app.models.findings import FindingEvidenceItem, FindingStatusHistory
from app.models.intelligence import IntelligenceExecution
from app.models.source_system import SourceSystem
from app.schemas.findings import CandidateFindingCreate
from app.services.finding_platform_service import (
    FindingPlatformError,
    finding_publication_service,
)


def create_execution(client: TestClient, slug: str) -> tuple[UUID, UUID]:
    organization = client.post(
        "/api/v1/organizations",
        json={
            "name": slug,
            "slug": slug,
            "country_code": "US",
            "default_currency": "USD",
            "timezone": "UTC",
        },
    )
    assert organization.status_code == 201
    organization_id = organization.json()["id"]
    source = client.post(
        f"/api/v1/organizations/{organization_id}/source-systems",
        json={
            "name": "ERP",
            "code": "erp",
            "system_type": "erp",
            "integration_method": "api",
        },
    )
    dataset = client.post(
        f"/api/v1/organizations/{organization_id}/datasets",
        json={
            "source_system_id": source.json()["id"],
            "name": "Quality events",
            "code": "quality-events",
            "domain": "quality",
            "dataset_type": "transactional",
            "default_currency": "USD",
        },
    )
    dataset_id = dataset.json()["id"]
    assessment = client.post(
        f"/api/v1/organizations/{organization_id}/datasets/{dataset_id}/trust-assessments",
        json={
            "records": [{"id": "Q1", "direct_cost": "125.50", "currency": "USD"}],
            "rule_configurations": {
                "required_field_completeness": {
                    "required_fields": ["id", "direct_cost", "currency"]
                },
                "numeric_range_validity": {"numeric_ranges": {"direct_cost": {"minimum": 0}}},
            },
        },
    )
    execution = client.post(
        f"/api/v1/organizations/{organization_id}/intelligence-executions",
        json={
            "dataset_id": dataset_id,
            "trust_assessment_id": assessment.json()["id"],
            "execution_type": "calculation",
            "definition_code": "SHARED.QUALITY.DIRECT_QUALITY_COST",
            "definition_version": "1.0.0",
            "records": [{"event_id": "Q1", "direct_cost": "125.50", "currency": "USD"}],
            "parameters": {"field": "direct_cost"},
            "currency": "USD",
            "exposure_value": "86500.00",
            "exposure_currency": "USD",
            "input_period_start": "2026-07-01T00:00:00Z",
            "input_period_end": "2026-07-31T23:59:59Z",
        },
    )
    assert execution.status_code == 201
    assert execution.json()["status"] == "completed"
    return UUID(organization_id), UUID(execution.json()["id"])


def candidate(execution_id: UUID, *, start_offset: int = 0) -> CandidateFindingCreate:
    start = datetime(2026, 7, 1, tzinfo=UTC) + timedelta(days=start_offset)
    return CandidateFindingCreate(
        execution_id=execution_id,
        result_id=execution_id,
        finding_type="leakage",
        title="Direct quality cost exposure",
        summary="Observed direct quality costs require review.",
        domain_code="quality",
        process_code="quality_cost_control",
        measured_value=Decimal("125.500000000000"),
        measured_value_type="currency",
        measured_currency="USD",
        exposure_value=Decimal("86500.000000000000"),
        exposure_value_type="currency",
        exposure_currency="USD",
        severity="high",
        severity_reason={"policy": "quality-cost-v1", "threshold": 50000},
        confidence_level="high",
        affected_record_count=14,
        occurrence_start=start,
        occurrence_end=start + timedelta(days=30),
        dataset_reference="quality-events@2026-07",
        evidence_policy_code="WP208-LEAKAGE",
        evidence_policy_version="1.0",
        evidence=[
            {
                "evidence_type": "affected_record",
                "reference_type": "canonical_record",
                "reference_id": "JOB-SYNTHETIC-001",
                "label": "Synthetic affected record",
                "canonical_entity": "QualityEvent",
                "canonical_record_reference": "JOB-SYNTHETIC-001",
                "metadata": {"synthetic": True},
            }
        ],
        calculation_traces=[
            {
                "operation_code": "sum",
                "input_reference_summary": {"dataset": "quality-events@2026-07"},
                "parameter_summary": {"field": "direct_cost"},
            }
        ],
        limitations=["Exposure is directional and supplied by the approved execution."],
    )


def publish(
    db_engine: Engine,
    organization_id: UUID,
    execution_id: UUID,
    actor_id: UUID,
    *,
    start_offset: int = 0,
) -> Finding:
    with Session(db_engine) as db:
        return finding_publication_service.publish_candidate_finding(
            db,
            organization_id,
            candidate(execution_id, start_offset=start_offset),
            actor_id,
        )


def test_publication_persists_governed_finding_evidence_trace_and_history(
    client: TestClient,
    db_engine: Engine,
    identity: IdentityState,
) -> None:
    organization_id, execution_id = create_execution(client, "finding-publication")
    finding = publish(
        db_engine,
        organization_id,
        execution_id,
        identity.user_id,  # type: ignore[arg-type]
    )

    assert finding.status == "published"
    assert finding.source_execution_id == execution_id
    assert finding.source_result_id == execution_id
    assert finding.definition_code == "SHARED.QUALITY.DIRECT_QUALITY_COST"
    assert finding.definition_version == "1.0.0"
    assert finding.measured_value == Decimal("125.500000000000")
    assert finding.exposure_value == Decimal("86500.000000000000")
    assert finding.content_fingerprint
    with Session(db_engine) as db:
        items = list(
            db.scalars(
                select(FindingEvidenceItem)
                .where(FindingEvidenceItem.organization_id == organization_id)
                .order_by(FindingEvidenceItem.sequence_number)
            ).all()
        )
        history = list(
            db.scalars(
                select(FindingStatusHistory).where(FindingStatusHistory.finding_id == finding.id)
            ).all()
        )
    assert [item.evidence_type for item in items[:5]] == [
        "execution",
        "oikb_definition",
        "trust_assessment",
        "readiness_decision",
        "dataset",
    ]
    assert all("payload" not in item.metadata_json for item in items)
    assert [(item.previous_status, item.new_status) for item in history] == [("draft", "published")]


def test_publication_is_idempotent_and_occurrence_period_changes_identity(
    client: TestClient,
    db_engine: Engine,
    identity: IdentityState,
) -> None:
    organization_id, execution_id = create_execution(client, "finding-dedup")
    actor_id = identity.user_id
    assert actor_id is not None
    first = publish(db_engine, organization_id, execution_id, actor_id)
    retry = publish(db_engine, organization_id, execution_id, actor_id)
    later = publish(
        db_engine,
        organization_id,
        execution_id,
        actor_id,
        start_offset=31,
    )

    assert retry.id == first.id
    assert later.id != first.id
    assert later.title == first.title


def test_blocked_failed_or_cross_tenant_execution_cannot_publish(
    client: TestClient,
    db_engine: Engine,
    identity: IdentityState,
) -> None:
    organization_id, execution_id = create_execution(client, "finding-blocked")
    other_id, _ = create_execution(client, "finding-other")
    actor_id = identity.user_id
    assert actor_id is not None
    with Session(db_engine) as db:
        execution = db.get(IntelligenceExecution, execution_id)
        assert execution is not None
        execution.status = "blocked"
        db.commit()
    with pytest.raises(FindingPlatformError, match="Only completed"):
        publish(db_engine, organization_id, execution_id, actor_id)
    with pytest.raises(FindingPlatformError, match="Eligible execution"):
        publish(db_engine, other_id, execution_id, actor_id)


def test_query_evidence_review_lifecycle_and_tenant_isolation(
    client: TestClient,
    db_engine: Engine,
    identity: IdentityState,
) -> None:
    organization_id, execution_id = create_execution(client, "finding-api")
    other_id, _ = create_execution(client, "finding-api-other")
    actor_id = identity.user_id
    assert actor_id is not None
    finding = publish(db_engine, organization_id, execution_id, actor_id)

    list_response = client.get(
        f"/api/v1/organizations/{organization_id}/findings",
        params={"severity": "high", "definition_code": finding.definition_code},
    )
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert list_response.json()["items"][0]["id"] == str(finding.id)
    assert client.get(f"/api/v1/organizations/{other_id}/findings/{finding.id}").status_code == 404
    evidence = client.get(f"/api/v1/organizations/{organization_id}/findings/{finding.id}/evidence")
    assert evidence.status_code == 200
    assert evidence.json()["bundle"]["status"] == "complete"
    trace = client.get(
        f"/api/v1/organizations/{organization_id}/findings/{finding.id}/calculation-trace"
    )
    assert trace.status_code == 200
    assert trace.json()[0]["operation_code"] == "sum"

    review = client.post(
        f"/api/v1/organizations/{organization_id}/findings/{finding.id}/reviews",
        json={
            "decision": "confirm",
            "reason_code": "evidence_verified",
            "comments": "Synthetic review completed.",
        },
    )
    assert review.status_code == 201
    detail = client.get(f"/api/v1/organizations/{organization_id}/findings/{finding.id}")
    assert detail.json()["status"] == "confirmed"
    resolved = client.post(
        f"/api/v1/organizations/{organization_id}/findings/{finding.id}/resolve",
        json={"reason_code": "operational_issue_addressed"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"
    invalid = client.post(
        f"/api/v1/organizations/{organization_id}/findings/{finding.id}/publish",
        json={"reason_code": "invalid_return"},
    )
    assert invalid.status_code == 409
    history = client.get(
        f"/api/v1/organizations/{organization_id}/findings/{finding.id}/status-history"
    ).json()
    assert [item["new_status"] for item in history] == [
        "published",
        "under_review",
        "confirmed",
        "resolved",
    ]


def test_finalized_evidence_is_immutable(
    client: TestClient,
    db_engine: Engine,
    identity: IdentityState,
) -> None:
    organization_id, execution_id = create_execution(client, "finding-immutable")
    actor_id = identity.user_id
    assert actor_id is not None
    publish(db_engine, organization_id, execution_id, actor_id)
    with Session(db_engine) as db:
        item = db.scalar(
            select(FindingEvidenceItem).where(
                FindingEvidenceItem.organization_id == organization_id
            )
        )
        assert item is not None
        item.label = "Unexpected mutation"
        with pytest.raises(ValueError, match="immutable"):
            db.commit()


def test_candidate_contract_rejects_untyped_currency_confidence_and_missing_trace(
    client: TestClient,
) -> None:
    _, execution_id = create_execution(client, "finding-contract")
    base = candidate(execution_id).model_dump()
    base["measured_currency"] = None
    with pytest.raises(ValueError, match="Measured currency"):
        CandidateFindingCreate.model_validate(base)
    base = candidate(execution_id).model_dump()
    base["confidence_score"] = Decimal("0.8")
    with pytest.raises(ValueError, match="complete methodology"):
        CandidateFindingCreate.model_validate(base)
    base = candidate(execution_id).model_dump()
    base["calculation_traces"] = []
    with pytest.raises(ValueError, match="At least one"):
        CandidateFindingCreate.model_validate(base)


def test_measurement_and_cross_tenant_evidence_references_are_rejected(
    client: TestClient,
    db_engine: Engine,
    identity: IdentityState,
) -> None:
    organization_id, execution_id = create_execution(client, "finding-reference")
    other_id, _ = create_execution(client, "finding-reference-other")
    actor_id = identity.user_id
    assert actor_id is not None
    mismatched = candidate(execution_id).model_copy(update={"measured_value": Decimal("126")})
    with Session(db_engine) as db:
        with pytest.raises(FindingPlatformError, match="Measured value"):
            finding_publication_service.publish_candidate_finding(
                db, organization_id, mismatched, actor_id
            )
        other_source_id = db.scalar(
            select(SourceSystem.id).where(SourceSystem.organization_id == other_id)
        )
    assert other_source_id is not None
    cross_tenant = candidate(execution_id)
    cross_tenant.evidence.append(
        cross_tenant.evidence[0].model_copy(
            update={
                "source_system_id": other_source_id,
                "reference_id": str(other_source_id),
            }
        )
    )
    with Session(db_engine) as db:
        with pytest.raises(FindingPlatformError, match="Evidence reference"):
            finding_publication_service.publish_candidate_finding(
                db, organization_id, cross_tenant, actor_id
            )


def test_supersession_archival_and_default_active_pagination(
    client: TestClient,
    db_engine: Engine,
    identity: IdentityState,
) -> None:
    organization_id, execution_id = create_execution(client, "finding-supersession")
    actor_id = identity.user_id
    assert actor_id is not None
    first = publish(db_engine, organization_id, execution_id, actor_id)
    replacement = publish(
        db_engine,
        organization_id,
        execution_id,
        actor_id,
        start_offset=31,
    )
    superseded = client.post(
        f"/api/v1/organizations/{organization_id}/findings/{first.id}/supersede",
        json={
            "reason_code": "new_period_replaces_prior",
            "superseding_finding_id": str(replacement.id),
        },
    )
    assert superseded.status_code == 200
    assert superseded.json()["superseded_by_finding_id"] == str(replacement.id)
    archived = client.post(
        f"/api/v1/organizations/{organization_id}/findings/{first.id}/archive",
        json={"reason_code": "history_retained"},
    )
    assert archived.status_code == 200
    active = client.get(
        f"/api/v1/organizations/{organization_id}/findings",
        params={"page": 1, "page_size": 1},
    ).json()
    assert active["total"] == 1
    assert active["items"][0]["id"] == str(replacement.id)
    archived_filter = client.get(
        f"/api/v1/organizations/{organization_id}/findings",
        params={"status": "archived"},
    ).json()
    assert archived_filter["total"] == 1


def test_viewer_can_read_but_cannot_review(
    client: TestClient,
    db_engine: Engine,
    identity: IdentityState,
) -> None:
    organization_id, execution_id = create_execution(client, "finding-review-auth")
    actor_id = identity.user_id
    assert actor_id is not None
    finding = publish(db_engine, organization_id, execution_id, actor_id)
    viewer_id = UUID("00000000-0000-4000-8000-000000000208")
    membership = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        json={"user_id": str(viewer_id), "role": "viewer", "status": "active"},
    )
    assert membership.status_code == 201
    identity.user_id = viewer_id
    identity.is_platform_admin = False
    assert (
        client.get(f"/api/v1/organizations/{organization_id}/findings/{finding.id}").status_code
        == 200
    )
    review = client.post(
        f"/api/v1/organizations/{organization_id}/findings/{finding.id}/reviews",
        json={"decision": "confirm", "reason_code": "unauthorized"},
    )
    assert review.status_code == 403
