"""AGENTIC-CONTROL-001 Phase L/M: cost telemetry aggregation and the
Learning Transfer Rate KPI -- both read-only over already-persisted
AgentJob data, no new capture mechanism introduced."""

from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.entities import Organization
from app.schemas.agent_jobs import (
    AgentJobCreate,
    EvidenceCodeContext,
    EvidenceControl,
    EvidenceEvidence,
    EvidenceImpact,
    EvidenceObservation,
    EvidencePackage,
    EvidenceSafety,
)
from app.schemas.contracts import OrganizationCreate
from app.services.agent_cost_telemetry_service import learning_transfer_rate, summarize
from app.services.agent_job_service import AgentJobService
from app.services.organization_service import OrganizationService
from app.storage.local_storage import LocalFileStorage


def _organization(db: Session, slug: str) -> Organization:
    return OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug.title(), slug=slug, country_code="US", default_currency="USD", timezone="UTC"
        ),
    )


def _evidence_package() -> EvidencePackage:
    return EvidencePackage(
        work_item_id="telemetry-1",
        evidence_plane="validation",
        risk_class="R0",
        observation=EvidenceObservation(observed_behavior="x"),
        impact=EvidenceImpact(),
        evidence=EvidenceEvidence(),
        control=EvidenceControl(),
        safety=EvidenceSafety(),
        code_context=EvidenceCodeContext(),
        question="q",
    )


def test_summarize_reports_zero_for_an_empty_organization(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "telemetry-empty")
    summary = summarize(db, org.id)
    assert summary.total_jobs == 0
    assert summary.qwen_acceptance_rate == 0.0


def test_summarize_counts_qwen_accept_and_escalate(db: Session, tmp_path: Path) -> None:
    from app.models.agent_jobs import AgentWorkerCredential

    org = _organization(db, "telemetry-qwen")
    storage = LocalFileStorage(str(tmp_path))
    service = AgentJobService(storage=storage)
    credential = AgentWorkerCredential(
        organization_id=org.id,
        worker_id=f"w-{uuid4()}",
        token_hash="x",
        allowed_risk_classes=["R0", "R1"],
    )
    db.add(credential)
    db.commit()

    for confidence in (95, 50):
        service.create_job(
            db,
            org.id,
            AgentJobCreate(
                job_type="MISS_CLASSIFICATION",
                risk_class="R0",
                requested_capability="gap_classification_v1",
                evidence_plane="validation",
                evidence_package=_evidence_package(),
            ),
            uuid4(),
        )
        claim = service.claim_next(db, credential)
        assert claim is not None
        service.submit_result(
            db,
            claim,
            {
                "primary_gap_class": "SEMANTIC_GAP",
                "secondary_gap_classes": [],
                "confidence": confidence,
                "summary": "x",
                "evidence_refs": [],
                "fp_risk": "low",
                "architecture_impact": False,
                "policy_dependency": False,
                "data_contract_dependency": False,
                "recommended_action": "x",
                "escalate": confidence < 90,
                "escalation_reason": "low confidence" if confidence < 90 else None,
            },
            execution_time_ms=500,
            input_tokens=100,
            output_tokens=50,
            reasoning_tokens=0,
            model_identifier="qwen/qwen3.5-9b",
        )

    summary = summarize(db, org.id)
    assert summary.qwen_jobs == 2
    assert summary.qwen_accepted == 1
    assert summary.qwen_escalated == 1
    assert summary.qwen_acceptance_rate == 0.5
    assert summary.local_jobs == 2
    assert summary.local_workload_pct == 100.0


def test_learning_transfer_rate_counts_encountered_and_handled(db: Session, tmp_path: Path) -> None:
    from app.models.agent_jobs import AgentWorkerCredential

    org = _organization(db, "telemetry-ltr")
    storage = LocalFileStorage(str(tmp_path))
    service = AgentJobService(storage=storage)
    credential = AgentWorkerCredential(
        organization_id=org.id,
        worker_id=f"w-{uuid4()}",
        token_hash="x",
        allowed_risk_classes=["R0", "R1"],
    )
    db.add(credential)
    db.commit()

    service.create_job(
        db,
        org.id,
        AgentJobCreate(
            job_type="MISS_CLASSIFICATION",
            risk_class="R0",
            requested_capability="gap_classification_v1",
            evidence_plane="validation",
            evidence_package=_evidence_package(),
        ),
        uuid4(),
    )
    claim = service.claim_next(db, credential)
    assert claim is not None
    service.submit_result(
        db,
        claim,
        {
            "primary_gap_class": "GOVERNED_POLICY_GAP",
            "secondary_gap_classes": [],
            "confidence": 96,
            "summary": "x",
            "evidence_refs": [],
            "fp_risk": "low",
            "architecture_impact": False,
            "policy_dependency": False,
            "data_contract_dependency": False,
            "recommended_action": "x",
            "escalate": False,
            "escalation_reason": None,
        },
        execution_time_ms=500,
        input_tokens=100,
        output_tokens=50,
        reasoning_tokens=0,
        model_identifier="qwen/qwen3.5-9b",
    )

    ltr = learning_transfer_rate(db, org.id, storage, frozenset({"GOVERNED_POLICY_GAP"}))
    assert ltr.encountered == 1
    assert ltr.handled_without_new_code == 1
    assert ltr.rate == 1.0

    ltr_unrelated = learning_transfer_rate(
        db, org.id, storage, frozenset({"ORCHESTRATION_RUNTIME_GAP"})
    )
    assert ltr_unrelated.encountered == 0
