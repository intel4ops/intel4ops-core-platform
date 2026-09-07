from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent_jobs import (
    AgentJob,
    AgentJobEvent,
    AgentJobOwnerApprovalStatus,
    AgentJobRiskClass,
    AgentJobStatus,
    AgentWorkerProfile,
)
from app.models.entities import Organization
from app.schemas.agent_jobs import (
    EvidenceCodeContext,
    EvidenceControl,
    EvidenceEvidence,
    EvidenceImpact,
    EvidenceObservation,
    EvidencePackage,
    EvidenceSafety,
)
from app.schemas.contracts import OrganizationCreate
from app.schemas.premium_codex_execution import PremiumCodexExecutionComplete
from app.services.agent_job_service import AgentJobService
from app.services.organization_service import OrganizationService
from app.storage.local_storage import LocalFileStorage
from app.validation_program.premium_codex_execution import (
    PremiumCodexExecutionError,
    PremiumCodexExecutionService,
)


def _organization(db: Session, slug: str) -> Organization:
    return OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug.title(),
            slug=slug,
            country_code="US",
            default_currency="USD",
            timezone="UTC",
        ),
    )


def _approved_job(db: Session, storage: LocalFileStorage, org: Organization) -> AgentJob:
    job = AgentJob(
        organization_id=org.id,
        job_type="CODEX_IMPLEMENTATION",
        risk_class=AgentJobRiskClass.R2.value,
        status=AgentJobStatus.QUEUED.value,
        priority=0,
        evidence_plane="validation",
        requested_capability="bounded_implementation_from_approved_handoff_v1",
        assigned_worker=AgentWorkerProfile.CODEX_IMPLEMENTATION.value,
        prompt_template_version="ac002c-v1",
        owner_approval_required=True,
        owner_approval_status=AgentJobOwnerApprovalStatus.APPROVED.value,
        created_by_user_id=uuid4(),
        client_idempotency_key=f"ac002d-test:{uuid4()}",
    )
    db.add(job)
    db.flush()
    evidence = EvidencePackage(
        work_item_id=f"ac002d:{job.id}",
        evidence_plane="validation",
        simulation_ids=["SIM-AC002D-001"],
        risk_class=AgentJobRiskClass.R2.value,
        observation=EvidenceObservation(
            observed_behavior="Approved gap requires bounded implementation.",
            expected_capability_behavior="Implement only the approved gap fix.",
        ),
        impact=EvidenceImpact(affected_items=1, simulations_affected=1),
        evidence=EvidenceEvidence(source_artifact_refs=["simulation-batches/x/decision.json"]),
        control=EvidenceControl(existing_capabilities=["INTELLIGENCE_CAPABILITY_GAP"]),
        safety=EvidenceSafety(
            fp_exposure="unknown",
            truth_isolation_constraints="Never read hidden-truth simulation package files.",
        ),
        code_context=EvidenceCodeContext(),
        question="Prepare a bounded implementation and do not merge or deploy automatically.",
    )
    job.input_evidence_ref = AgentJobService(storage=storage)._write_json(  # noqa: SLF001
        f"agent-jobs/{job.id}/evidence.json", evidence.model_dump(mode="json")
    )
    db.commit()
    return job


def test_start_creates_bounded_execution_manifest(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "ac002d-start")
    storage = LocalFileStorage(str(tmp_path / "storage"))
    job = _approved_job(db, storage, org)

    lease = PremiumCodexExecutionService(storage).start(
        db,
        org.id,
        job.id,
        "premium-codex-worker-1",
    )

    db.refresh(job)
    assert job.status == AgentJobStatus.RUNNING.value
    assert job.execution_lease_id == lease.lease_id
    assert job.execution_worker_id == "premium-codex-worker-1"
    assert job.assigned_worker == AgentWorkerProfile.CODEX_IMPLEMENTATION.value

    manifest = AgentJobService(storage=storage)._read_json(lease.manifest_ref)  # noqa: SLF001
    assert manifest["target_worker_profile"] == "CODEX_IMPLEMENTATION"
    assert manifest["repository"] == "intel4ops/intel4ops-core-platform"
    assert manifest["base_branch"] == "main"
    assert manifest["result_contract"]["automatic_merge_allowed"] is False
    assert manifest["result_contract"]["automatic_deploy_allowed"] is False
    assert "write directly to main" in manifest["prohibited_activities"]
    assert "read hidden-truth simulation package files" in manifest["prohibited_activities"]

    events = list(
        db.scalars(
            select(AgentJobEvent)
            .where(AgentJobEvent.agent_job_id == job.id)
            .order_by(AgentJobEvent.created_at, AgentJobEvent.id)
        )
    )
    assert {event.event_type for event in events} == {"CLAIMED", "STARTED"}


def test_start_rejects_job_without_owner_approval(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "ac002d-no-approval")
    storage = LocalFileStorage(str(tmp_path / "storage"))
    job = _approved_job(db, storage, org)
    job.owner_approval_status = AgentJobOwnerApprovalStatus.PENDING.value
    db.commit()

    with pytest.raises(PremiumCodexExecutionError) as exc_info:
        PremiumCodexExecutionService(storage).start(db, org.id, job.id, "worker")

    assert exc_info.value.code == "OWNER_APPROVAL_MISSING"


def test_success_requires_pr_and_records_governed_result(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "ac002d-success")
    storage = LocalFileStorage(str(tmp_path / "storage"))
    job = _approved_job(db, storage, org)
    service = PremiumCodexExecutionService(storage)
    lease = service.start(db, org.id, job.id, "premium-codex-worker-2")

    with pytest.raises(PremiumCodexExecutionError) as exc_info:
        service.complete(
            db,
            org.id,
            job.id,
            PremiumCodexExecutionComplete(
                lease_id=lease.lease_id,
                outcome="succeeded",
                summary="implementation complete",
            ),
        )
    assert exc_info.value.code == "SUCCESS_RESULT_INCOMPLETE"

    completed = service.complete(
        db,
        org.id,
        job.id,
        PremiumCodexExecutionComplete(
            lease_id=lease.lease_id,
            outcome="succeeded",
            branch_name="agent/ac002d/example",
            head_sha="a" * 40,
            pull_request_number=999,
            pull_request_url="https://github.com/intel4ops/intel4ops-core-platform/pull/999",
            changed_files=["app/example.py", "tests/test_example.py"],
            tests_run=["ruff", "mypy", "pytest"],
            summary="bounded implementation prepared for review",
        ),
    )

    assert completed.status == AgentJobStatus.SUCCEEDED.value
    assert completed.result_ref is not None
    result = AgentJobService(storage=storage)._read_json(completed.result_ref)  # noqa: SLF001
    assert result["pull_request_number"] == 999
    assert result["automatic_merge_performed"] is False
    assert result["automatic_deploy_performed"] is False


def test_execution_can_escalate_without_claiming_success(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "ac002d-escalate")
    storage = LocalFileStorage(str(tmp_path / "storage"))
    job = _approved_job(db, storage, org)
    service = PremiumCodexExecutionService(storage)
    lease = service.start(db, org.id, job.id, "premium-codex-worker-3")

    completed = service.complete(
        db,
        org.id,
        job.id,
        PremiumCodexExecutionComplete(
            lease_id=lease.lease_id,
            outcome="escalated",
            summary="security boundary would need to change",
            escalation_reason="SECURITY_BOUNDARY_CHANGE",
        ),
    )

    assert completed.status == AgentJobStatus.ESCALATED.value
    assert completed.escalation_reason == "SECURITY_BOUNDARY_CHANGE"
