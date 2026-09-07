from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.models.agent_jobs import AgentJob, AgentJobRiskClass, AgentJobStatus, AgentWorkerProfile
from app.models.entities import Organization
from app.models.simulation_batch import SimulationBatch, SimulationBatchStatus
from app.schemas.contracts import OrganizationCreate
from app.schemas.governed_merge_release_promotion import GovernedMergeComplete
from app.services.agent_job_service import AgentJobService
from app.services.organization_service import OrganizationService
from app.storage.local_storage import LocalFileStorage
from app.validation_program.governed_merge_release_promotion import (
    GovernedMergeReleasePromotionError,
    GovernedMergeReleasePromotionService,
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
    authorized: bool = True,
) -> tuple[SimulationBatch, AgentJob]:
    batch = SimulationBatch(
        organization_id=org.id,
        name="AC-002G merge batch",
        status=SimulationBatchStatus.COMPLETE.value,
        created_by_user_id=uuid4(),
    )
    db.add(batch)
    db.flush()
    job = AgentJob(
        organization_id=org.id,
        job_type="CODEX_IMPLEMENTATION",
        risk_class=AgentJobRiskClass.R2.value,
        status=AgentJobStatus.SUCCEEDED.value,
        priority=0,
        evidence_plane="validation",
        requested_capability="bounded_implementation_from_approved_handoff_v1",
        assigned_worker=AgentWorkerProfile.CODEX_IMPLEMENTATION.value,
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
            "pull_request_number": 903,
            "pull_request_url": "https://github.com/intel4ops/intel4ops-core-platform/pull/903",
            "automatic_merge_performed": False,
            "automatic_deploy_performed": False,
        },
    )
    jobs._write_json(  # noqa: SLF001
        f"agent-jobs/{job.id}/release-authorization.json",
        {
            "schema_version": "ac002f-release-authorization-v1",
            "organization_id": str(org.id),
            "batch_id": str(batch.id),
            "implementation_job_id": str(job.id),
            "candidate_head_sha": "a" * 40,
            "pull_request_number": 903,
            "pull_request_url": "https://github.com/intel4ops/intel4ops-core-platform/pull/903",
            "branch_name": "agent/fix-gap",
            "decision": "APPROVED" if authorized else "REJECTED",
            "owner_user_id": str(uuid4()),
            "owner_note": "verified release",
            "merge_allowed": authorized,
            "deploy_allowed": False,
            "automatic_merge_performed": False,
            "automatic_deploy_performed": False,
        },
    )
    db.commit()
    return batch, job


def test_governed_merge_promotes_exact_authorized_candidate(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "ac002g-pass")
    storage = LocalFileStorage(str(tmp_path / "storage"))
    _batch, job = _scenario(db, storage, org)
    service = GovernedMergeReleasePromotionService(storage)

    lease = service.start(db, org.id, job.id, "github-merge-worker")
    manifest = AgentJobService(storage=storage)._read_json(lease.manifest_ref)  # noqa: SLF001
    assert manifest["expected_head_sha"] == "a" * 40
    assert manifest["pull_request_number"] == 903
    assert manifest["target_branch"] == "main"
    assert manifest["deploy_allowed"] is False

    decision = service.complete(
        db,
        org.id,
        job.id,
        GovernedMergeComplete(
            lease_id=lease.lease_id,
            outcome="merged",
            candidate_head_sha="a" * 40,
            pull_request_number=903,
            target_branch="main",
            merge_commit_sha="b" * 40,
            summary="verified candidate merged",
        ),
    )
    promotion = AgentJobService(storage=storage)._read_json(decision.promotion_ref)  # noqa: SLF001
    assert decision.decision == "MERGED_RELEASE_CANDIDATE"
    assert decision.deploy_allowed is False
    assert promotion["merge_commit_sha"] == "b" * 40
    assert promotion["release_stage"] == "MERGED_AWAITING_DEPLOYMENT_AUTHORIZATION"
    assert promotion["automatic_deploy_performed"] is False


def test_governed_merge_rejects_unapproved_authorization(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "ac002g-reject")
    storage = LocalFileStorage(str(tmp_path / "storage"))
    _batch, job = _scenario(db, storage, org, authorized=False)
    service = GovernedMergeReleasePromotionService(storage)

    with pytest.raises(GovernedMergeReleasePromotionError) as exc_info:
        service.start(db, org.id, job.id, "github-merge-worker")
    assert exc_info.value.code == "MERGE_NOT_AUTHORIZED"


def test_governed_merge_rejects_candidate_sha_mismatch(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "ac002g-sha")
    storage = LocalFileStorage(str(tmp_path / "storage"))
    _batch, job = _scenario(db, storage, org)
    service = GovernedMergeReleasePromotionService(storage)
    lease = service.start(db, org.id, job.id, "github-merge-worker")

    with pytest.raises(GovernedMergeReleasePromotionError) as exc_info:
        service.complete(
            db,
            org.id,
            job.id,
            GovernedMergeComplete(
                lease_id=lease.lease_id,
                outcome="merged",
                candidate_head_sha="c" * 40,
                pull_request_number=903,
                target_branch="main",
                merge_commit_sha="b" * 40,
                summary="wrong candidate",
            ),
        )
    assert exc_info.value.code == "CANDIDATE_SHA_MISMATCH"


def test_failed_merge_pauses_safety_gate(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "ac002g-fail")
    storage = LocalFileStorage(str(tmp_path / "storage"))
    batch, job = _scenario(db, storage, org)
    service = GovernedMergeReleasePromotionService(storage)
    lease = service.start(db, org.id, job.id, "github-merge-worker")

    decision = service.complete(
        db,
        org.id,
        job.id,
        GovernedMergeComplete(
            lease_id=lease.lease_id,
            outcome="failed",
            candidate_head_sha="a" * 40,
            pull_request_number=903,
            target_branch="main",
            summary="merge blocked by repository state",
        ),
    )
    db.refresh(batch)
    assert decision.decision == "MERGE_BLOCKED"
    assert batch.status == SimulationBatchStatus.PAUSED_SAFETY_GATE.value
