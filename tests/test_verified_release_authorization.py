from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.models.agent_jobs import (
    AgentJob,
    AgentJobOwnerApprovalStatus,
    AgentJobRiskClass,
    AgentJobStatus,
    AgentWorkerProfile,
)
from app.models.entities import Organization
from app.models.simulation_batch import (
    SimulationBatch,
    SimulationBatchItem,
    SimulationBatchItemState,
    SimulationBatchStatus,
)
from app.schemas.contracts import OrganizationCreate
from app.schemas.verified_release_authorization import VerifiedReleaseAuthorizationRequest
from app.services.agent_job_service import AgentJobService
from app.services.organization_service import OrganizationService
from app.storage.local_storage import LocalFileStorage
from app.validation_program.verified_release_authorization import (
    VerifiedReleaseAuthorizationError,
    VerifiedReleaseAuthorizationService,
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


def _scenario(
    db: Session,
    storage: LocalFileStorage,
    org: Organization,
    *,
    verification_decision: str = "VERIFIED_IMPROVEMENT",
) -> tuple[SimulationBatch, AgentJob]:
    batch = SimulationBatch(
        organization_id=org.id,
        name="AC-002F release batch",
        status=SimulationBatchStatus.OWNER_REVIEW_REQUIRED.value,
        created_by_user_id=uuid4(),
    )
    db.add(batch)
    db.flush()
    db.add(
        SimulationBatchItem(
            batch_id=batch.id,
            organization_id=org.id,
            simulation_id="SIM-AC002F-001",
            state=SimulationBatchItemState.GRADUATED.value,
            true_positive_count=4,
            false_positive_count=0,
            false_negative_count=0,
        )
    )
    job = AgentJob(
        organization_id=org.id,
        job_type="CODEX_IMPLEMENTATION",
        risk_class=AgentJobRiskClass.R2.value,
        status=AgentJobStatus.SUCCEEDED.value,
        priority=0,
        evidence_plane="validation",
        requested_capability="bounded_implementation_from_approved_handoff_v1",
        assigned_worker=AgentWorkerProfile.CODEX_IMPLEMENTATION.value,
        owner_approval_required=True,
        owner_approval_status=AgentJobOwnerApprovalStatus.APPROVED.value,
        client_idempotency_key=f"ac002c:{batch.id}:codex",
    )
    db.add(job)
    db.flush()
    jobs = AgentJobService(storage=storage)
    job.result_ref = jobs._write_json(  # noqa: SLF001
        f"agent-jobs/{job.id}/result.json",
        {
            "schema_version": "ac002d-premium-codex-result-v1",
            "branch_name": "agent/fix-gap",
            "head_sha": "a" * 40,
            "pull_request_number": 902,
            "pull_request_url": "https://github.com/intel4ops/intel4ops-core-platform/pull/902",
            "automatic_merge_performed": False,
            "automatic_deploy_performed": False,
        },
    )
    jobs._write_json(  # noqa: SLF001
        f"agent-jobs/{job.id}/verification-retest-result.json",
        {
            "schema_version": "ac002e-verification-result-v1",
            "organization_id": str(org.id),
            "batch_id": str(batch.id),
            "implementation_job_id": str(job.id),
            "candidate_head_sha": "a" * 40,
            "pull_request_number": 902,
            "outcome": "scored",
            "decision": verification_decision,
            "summary": "verification complete",
            "escalation_reason": None,
            "results": [],
            "owner_review_required": verification_decision == "VERIFIED_IMPROVEMENT",
            "automatic_merge_performed": False,
            "automatic_deploy_performed": False,
        },
    )
    db.commit()
    return batch, job


def test_owner_can_authorize_exact_verified_candidate(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "ac002f-approve")
    storage = LocalFileStorage(str(tmp_path / "storage"))
    batch, job = _scenario(db, storage, org)
    service = VerifiedReleaseAuthorizationService(storage)
    owner_id = uuid4()

    decision = service.authorize(
        db,
        org.id,
        job.id,
        owner_id,
        VerifiedReleaseAuthorizationRequest(
            approve=True,
            expected_head_sha="a" * 40,
            pull_request_number=902,
            note="approve verified release",
        ),
    )

    db.refresh(batch)
    artifact = AgentJobService(storage=storage)._read_json(decision.authorization_ref)  # noqa: SLF001
    assert decision.decision == "APPROVED"
    assert decision.merge_allowed is True
    assert decision.deploy_allowed is False
    assert artifact["owner_user_id"] == str(owner_id)
    assert artifact["candidate_head_sha"] == "a" * 40
    assert artifact["automatic_merge_performed"] is False
    assert artifact["automatic_deploy_performed"] is False
    assert batch.status == SimulationBatchStatus.COMPLETE.value


def test_owner_rejection_pauses_release(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "ac002f-reject")
    storage = LocalFileStorage(str(tmp_path / "storage"))
    batch, job = _scenario(db, storage, org)
    service = VerifiedReleaseAuthorizationService(storage)

    decision = service.authorize(
        db,
        org.id,
        job.id,
        uuid4(),
        VerifiedReleaseAuthorizationRequest(
            approve=False,
            expected_head_sha="a" * 40,
            pull_request_number=902,
            note="do not release",
        ),
    )

    db.refresh(batch)
    assert decision.decision == "REJECTED"
    assert decision.merge_allowed is False
    assert batch.status == SimulationBatchStatus.PAUSED_SAFETY_GATE.value


def test_non_improvement_cannot_be_authorized(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "ac002f-block")
    storage = LocalFileStorage(str(tmp_path / "storage"))
    _batch, job = _scenario(db, storage, org, verification_decision="NO_IMPROVEMENT")
    service = VerifiedReleaseAuthorizationService(storage)

    with pytest.raises(VerifiedReleaseAuthorizationError) as exc_info:
        service.authorize(
            db,
            org.id,
            job.id,
            uuid4(),
            VerifiedReleaseAuthorizationRequest(
                approve=True,
                expected_head_sha="a" * 40,
                pull_request_number=902,
            ),
        )
    assert exc_info.value.code == "VERIFICATION_NOT_APPROVABLE"


def test_candidate_sha_must_match_verified_candidate(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "ac002f-sha")
    storage = LocalFileStorage(str(tmp_path / "storage"))
    _batch, job = _scenario(db, storage, org)
    service = VerifiedReleaseAuthorizationService(storage)

    with pytest.raises(VerifiedReleaseAuthorizationError) as exc_info:
        service.authorize(
            db,
            org.id,
            job.id,
            uuid4(),
            VerifiedReleaseAuthorizationRequest(
                approve=True,
                expected_head_sha="b" * 40,
                pull_request_number=902,
            ),
        )
    assert exc_info.value.code == "CANDIDATE_SHA_MISMATCH"
