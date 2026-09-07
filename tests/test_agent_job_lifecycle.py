"""AGENTIC-CONTROL-001 Phase B/E/O/P: AgentJob lifecycle -- create
(idempotent), claim (CAS, no duplicate claim), heartbeat (lease-checked),
stale-lease recovery (retry then terminal timeout), and structured-result
submission (accept / escalate / malformed-output failure)."""

from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.agent_jobs import (
    AgentJobOwnerApprovalStatus,
    AgentJobStatus,
    AgentWorkerCredential,
)
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
from app.services.agent_job_service import AgentJobLeaseLost, AgentJobService
from app.services.organization_service import OrganizationService
from app.storage.local_storage import LocalFileStorage


def _organization(db: Session, slug: str) -> Organization:
    return OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug.title(), slug=slug, country_code="US", default_currency="USD", timezone="UTC"
        ),
    )


def _evidence_package(risk_class: str = "R0") -> EvidencePackage:
    return EvidencePackage(
        work_item_id="test-item-1",
        evidence_plane="production",
        risk_class=risk_class,
        observation=EvidenceObservation(observed_behavior="observed X"),
        impact=EvidenceImpact(),
        evidence=EvidenceEvidence(),
        control=EvidenceControl(),
        safety=EvidenceSafety(),
        code_context=EvidenceCodeContext(),
        question="Classify this.",
    )


def _service(tmp_path: Path) -> AgentJobService:
    return AgentJobService(storage=LocalFileStorage(str(tmp_path)))


def _credential(
    db: Session, org_id, risk_classes: list[str] | None = None
) -> AgentWorkerCredential:
    credential = AgentWorkerCredential(
        organization_id=org_id,
        worker_id=f"worker-{uuid4()}",
        token_hash="irrelevant-for-service-level-tests",
        allowed_risk_classes=risk_classes or ["R0", "R1"],
    )
    db.add(credential)
    db.commit()
    return credential


def test_create_job_is_idempotent_on_client_key(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "aj-idempotent")
    service = _service(tmp_path)
    payload = AgentJobCreate(
        job_type="MISS_CLASSIFICATION",
        risk_class="R0",
        requested_capability="gap_classification_v1",
        evidence_package=_evidence_package(),
        client_idempotency_key="fixed-key-1",
    )
    first = service.create_job(db, org.id, payload, uuid4())
    second = service.create_job(db, org.id, payload, uuid4())
    assert first.id == second.id


def test_r0_job_is_queued_not_owner_gated(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "aj-r0-queued")
    service = _service(tmp_path)
    job = service.create_job(
        db,
        org.id,
        AgentJobCreate(
            job_type="MISS_CLASSIFICATION",
            risk_class="R0",
            requested_capability="gap_classification_v1",
            evidence_package=_evidence_package(),
        ),
        uuid4(),
    )
    assert job.status == AgentJobStatus.QUEUED.value
    assert job.owner_approval_required is False


def test_r2_job_is_owner_review_required_immediately(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "aj-r2-gate")
    service = _service(tmp_path)
    job = service.create_job(
        db,
        org.id,
        AgentJobCreate(
            job_type="PLATFORM_CHANGE",
            risk_class="R2",
            requested_capability="platform_review_v1",
            evidence_package=_evidence_package(risk_class="R2"),
        ),
        uuid4(),
    )
    assert job.status == AgentJobStatus.OWNER_REVIEW_REQUIRED.value
    assert job.owner_approval_required is True
    assert job.owner_approval_status == AgentJobOwnerApprovalStatus.PENDING.value


def test_claim_returns_none_when_no_eligible_job(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "aj-claim-empty")
    service = _service(tmp_path)
    credential = _credential(db, org.id)
    assert service.claim_next(db, credential) is None


def test_claim_then_second_claim_gets_nothing_else(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "aj-claim-once")
    service = _service(tmp_path)
    service.create_job(
        db,
        org.id,
        AgentJobCreate(
            job_type="MISS_CLASSIFICATION",
            risk_class="R0",
            requested_capability="gap_classification_v1",
            evidence_package=_evidence_package(),
        ),
        uuid4(),
    )
    credential = _credential(db, org.id)
    first_claim = service.claim_next(db, credential)
    assert first_claim is not None
    second_claim = service.claim_next(db, credential)
    assert second_claim is None

    job = service.get(db, org.id, first_claim.job_id)
    assert job.status == AgentJobStatus.RUNNING.value
    assert job.execution_lease_id == first_claim.lease_id


def test_worker_credential_cannot_claim_r2_job(db: Session, tmp_path: Path) -> None:
    """Phase N: a local worker credential is structurally scoped to
    R0/R1 -- it can never claim (and therefore never self-promote) an
    R2/R3 job, regardless of what the worker script requests."""
    org = _organization(db, "aj-r2-unclaimable")
    service = _service(tmp_path)
    service.create_job(
        db,
        org.id,
        AgentJobCreate(
            job_type="PLATFORM_CHANGE",
            risk_class="R2",
            requested_capability="platform_review_v1",
            evidence_package=_evidence_package(risk_class="R2"),
        ),
        uuid4(),
    )
    credential = _credential(db, org.id, risk_classes=["R0", "R1"])
    assert service.claim_next(db, credential) is None


def test_heartbeat_succeeds_with_valid_lease_and_fails_after_lease_lost(
    db: Session, tmp_path: Path
) -> None:
    org = _organization(db, "aj-heartbeat")
    service = _service(tmp_path)
    service.create_job(
        db,
        org.id,
        AgentJobCreate(
            job_type="MISS_CLASSIFICATION",
            risk_class="R0",
            requested_capability="gap_classification_v1",
            evidence_package=_evidence_package(),
        ),
        uuid4(),
    )
    credential = _credential(db, org.id)
    claim = service.claim_next(db, credential)
    assert service.heartbeat(db, claim) is True

    # Recover the job as stale (simulating a lost worker), which clears
    # the lease -- a heartbeat against the old lease must now fail.
    recovered = service.recover_stale(db, timedelta(seconds=-1))
    assert claim.job_id in recovered
    assert service.heartbeat(db, claim) is False


def test_stale_job_is_requeued_then_eventually_times_out(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "aj-stale-retry")
    service = _service(tmp_path)
    service.create_job(
        db,
        org.id,
        AgentJobCreate(
            job_type="MISS_CLASSIFICATION",
            risk_class="R0",
            requested_capability="gap_classification_v1",
            evidence_package=_evidence_package(),
        ),
        uuid4(),
    )
    credential = _credential(db, org.id)

    job_id = None
    for attempt in range(4):
        claim = service.claim_next(db, credential)
        assert claim is not None, f"expected a claimable job on attempt {attempt}"
        job_id = claim.job_id
        service.recover_stale(db, timedelta(seconds=-1))

    job = service.get(db, org.id, job_id)
    assert job.status == AgentJobStatus.TIMED_OUT.value
    assert job.retry_count == 3
    assert job.error_code == "WORKER_LEASE_STALE"
    # A terminal job is never claimable again.
    assert service.claim_next(db, credential) is None


def test_submit_result_accepted_marks_job_succeeded(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "aj-submit-ok")
    service = _service(tmp_path)
    service.create_job(
        db,
        org.id,
        AgentJobCreate(
            job_type="MISS_CLASSIFICATION",
            risk_class="R0",
            requested_capability="gap_classification_v1",
            evidence_package=_evidence_package(),
        ),
        uuid4(),
    )
    credential = _credential(db, org.id)
    claim = service.claim_next(db, credential)
    job = service.submit_result(
        db,
        claim,
        {
            "primary_gap_class": "DATA_CONTRACT_GAP",
            "secondary_gap_classes": [],
            "confidence": 96,
            "summary": "no evidence for currency",
            "evidence_refs": [],
            "fp_risk": "low",
            "architecture_impact": False,
            "policy_dependency": False,
            "data_contract_dependency": True,
            "recommended_action": "none",
            "escalate": False,
            "escalation_reason": None,
        },
        execution_time_ms=850,
        input_tokens=400,
        output_tokens=120,
        reasoning_tokens=0,
        model_identifier="qwen/qwen3.5-9b",
    )
    assert job.status == AgentJobStatus.SUCCEEDED.value
    assert job.confidence == 96
    assert job.result_ref is not None


def test_submit_result_low_confidence_escalates_not_accepted(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "aj-submit-escalate")
    service = _service(tmp_path)
    service.create_job(
        db,
        org.id,
        AgentJobCreate(
            job_type="MISS_CLASSIFICATION",
            risk_class="R0",
            requested_capability="gap_classification_v1",
            evidence_package=_evidence_package(),
        ),
        uuid4(),
    )
    credential = _credential(db, org.id)
    claim = service.claim_next(db, credential)
    job = service.submit_result(
        db,
        claim,
        {
            "primary_gap_class": "DATA_CONTRACT_GAP",
            "secondary_gap_classes": [],
            "confidence": 55,
            "summary": "unsure",
            "evidence_refs": [],
            "fp_risk": "medium",
            "architecture_impact": False,
            "policy_dependency": False,
            "data_contract_dependency": True,
            "recommended_action": "escalate",
            "escalate": True,
            "escalation_reason": "low confidence",
        },
        execution_time_ms=900,
        input_tokens=400,
        output_tokens=120,
        reasoning_tokens=0,
        model_identifier="qwen/qwen3.5-9b",
    )
    assert job.status == AgentJobStatus.ESCALATED.value


def test_submit_malformed_result_fails_never_silently_accepted(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "aj-submit-malformed")
    service = _service(tmp_path)
    service.create_job(
        db,
        org.id,
        AgentJobCreate(
            job_type="MISS_CLASSIFICATION",
            risk_class="R0",
            requested_capability="gap_classification_v1",
            evidence_package=_evidence_package(),
        ),
        uuid4(),
    )
    credential = _credential(db, org.id)
    claim = service.claim_next(db, credential)
    job = service.submit_result(
        db,
        claim,
        {"garbage": "not a structured result"},
        execution_time_ms=100,
        input_tokens=10,
        output_tokens=1,
        reasoning_tokens=0,
        model_identifier="qwen/qwen3.5-9b",
    )
    assert job.status == AgentJobStatus.FAILED.value
    assert job.error_code == "MALFORMED_WORKER_OUTPUT"


def test_submit_result_with_stale_lease_raises_lease_lost(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "aj-submit-lease-lost")
    service = _service(tmp_path)
    service.create_job(
        db,
        org.id,
        AgentJobCreate(
            job_type="MISS_CLASSIFICATION",
            risk_class="R0",
            requested_capability="gap_classification_v1",
            evidence_package=_evidence_package(),
        ),
        uuid4(),
    )
    credential = _credential(db, org.id)
    claim = service.claim_next(db, credential)
    service.recover_stale(db, timedelta(seconds=-1))
    try:
        service.submit_result(
            db,
            claim,
            {},
            execution_time_ms=1,
            input_tokens=1,
            output_tokens=1,
            reasoning_tokens=0,
            model_identifier="qwen/qwen3.5-9b",
        )
        raise AssertionError("expected AgentJobLeaseLost")
    except AgentJobLeaseLost:
        pass
