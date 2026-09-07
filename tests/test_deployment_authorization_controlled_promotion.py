from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.models.agent_jobs import AgentJob, AgentJobRiskClass, AgentJobStatus, AgentWorkerProfile
from app.models.entities import Organization
from app.models.simulation_batch import SimulationBatch, SimulationBatchStatus
from app.schemas.contracts import OrganizationCreate
from app.schemas.deployment_authorization_controlled_promotion import (
    ControlledPromotionComplete,
    DeploymentAuthorizationRequest,
)
from app.services.agent_job_service import AgentJobService
from app.services.organization_service import OrganizationService
from app.storage.local_storage import LocalFileStorage
from app.validation_program.deployment_authorization_controlled_promotion import (
    DeploymentAuthorizationControlledPromotionError,
    DeploymentAuthorizationControlledPromotionService,
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
    db: Session, storage: LocalFileStorage, org: Organization
) -> tuple[SimulationBatch, AgentJob]:
    batch = SimulationBatch(
        organization_id=org.id,
        name="AC-002H deployment batch",
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
    AgentJobService(storage=storage)._write_json(  # noqa: SLF001
        f"agent-jobs/{job.id}/release-promotion.json",
        {
            "schema_version": "ac002g-release-promotion-v1",
            "organization_id": str(org.id),
            "batch_id": str(batch.id),
            "implementation_job_id": str(job.id),
            "decision": "MERGED_RELEASE_CANDIDATE",
            "outcome": "merged",
            "candidate_head_sha": "a" * 40,
            "pull_request_number": 903,
            "target_branch": "main",
            "merge_commit_sha": "b" * 40,
            "release_stage": "MERGED_AWAITING_DEPLOYMENT_AUTHORIZATION",
            "deploy_allowed": False,
            "automatic_deploy_performed": False,
        },
    )
    db.commit()
    return batch, job


def test_owner_authorizes_exact_commit_for_one_environment(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "ac002h-auth")
    storage = LocalFileStorage(str(tmp_path / "storage"))
    _batch, job = _scenario(db, storage, org)
    service = DeploymentAuthorizationControlledPromotionService(storage)
    owner_id = uuid4()

    decision = service.authorize(
        db,
        org.id,
        job.id,
        owner_id,
        DeploymentAuthorizationRequest(
            approve=True,
            environment="staging",
            expected_merge_commit_sha="b" * 40,
            note="promote verified candidate",
        ),
    )
    artifact = AgentJobService(storage=storage)._read_json(decision.authorization_ref)  # noqa: SLF001
    assert decision.decision == "APPROVED"
    assert decision.deploy_allowed is True
    assert artifact["environment"] == "staging"
    assert artifact["merge_commit_sha"] == "b" * 40
    assert artifact["cross_environment_deploy_allowed"] is False


def test_authorization_rejects_stale_merge_commit(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "ac002h-stale")
    storage = LocalFileStorage(str(tmp_path / "storage"))
    _batch, job = _scenario(db, storage, org)
    service = DeploymentAuthorizationControlledPromotionService(storage)

    with pytest.raises(DeploymentAuthorizationControlledPromotionError) as exc_info:
        service.authorize(
            db,
            org.id,
            job.id,
            uuid4(),
            DeploymentAuthorizationRequest(
                approve=True,
                environment="staging",
                expected_merge_commit_sha="c" * 40,
            ),
        )
    assert exc_info.value.code == "MERGE_COMMIT_MISMATCH"


def test_controlled_promotion_requires_same_environment_authorization(
    db: Session, tmp_path: Path
) -> None:
    org = _organization(db, "ac002h-env")
    storage = LocalFileStorage(str(tmp_path / "storage"))
    _batch, job = _scenario(db, storage, org)
    service = DeploymentAuthorizationControlledPromotionService(storage)
    service.authorize(
        db,
        org.id,
        job.id,
        uuid4(),
        DeploymentAuthorizationRequest(
            approve=True,
            environment="staging",
            expected_merge_commit_sha="b" * 40,
        ),
    )

    with pytest.raises(DeploymentAuthorizationControlledPromotionError) as exc_info:
        service.start(db, org.id, job.id, "production", "b" * 40, "deploy-worker")
    assert exc_info.value.code == "DEPLOYMENT_AUTHORIZATION_MISSING"


def test_successful_controlled_promotion_records_exact_commit(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "ac002h-deploy")
    storage = LocalFileStorage(str(tmp_path / "storage"))
    batch, job = _scenario(db, storage, org)
    service = DeploymentAuthorizationControlledPromotionService(storage)
    service.authorize(
        db,
        org.id,
        job.id,
        uuid4(),
        DeploymentAuthorizationRequest(
            approve=True,
            environment="staging",
            expected_merge_commit_sha="b" * 40,
        ),
    )
    lease = service.start(db, org.id, job.id, "staging", "b" * 40, "deploy-worker")
    decision = service.complete(
        db,
        org.id,
        job.id,
        ControlledPromotionComplete(
            lease_id=lease.lease_id,
            outcome="deployed",
            environment="staging",
            deployed_commit_sha="b" * 40,
            deployment_reference="deployment-123",
            summary="staging deployment healthy",
        ),
    )
    result = AgentJobService(storage=storage)._read_json(decision.result_ref)  # noqa: SLF001
    db.refresh(batch)
    assert decision.decision == "DEPLOYED"
    assert result["deployed_commit_sha"] == "b" * 40
    assert result["cross_environment_promotion_performed"] is False
    assert batch.status == SimulationBatchStatus.COMPLETE.value


def test_failed_controlled_promotion_pauses_safety_gate(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "ac002h-fail")
    storage = LocalFileStorage(str(tmp_path / "storage"))
    batch, job = _scenario(db, storage, org)
    service = DeploymentAuthorizationControlledPromotionService(storage)
    service.authorize(
        db,
        org.id,
        job.id,
        uuid4(),
        DeploymentAuthorizationRequest(
            approve=True,
            environment="production",
            expected_merge_commit_sha="b" * 40,
        ),
    )
    lease = service.start(db, org.id, job.id, "production", "b" * 40, "deploy-worker")
    decision = service.complete(
        db,
        org.id,
        job.id,
        ControlledPromotionComplete(
            lease_id=lease.lease_id,
            outcome="failed",
            environment="production",
            deployed_commit_sha="b" * 40,
            summary="health check failed",
        ),
    )
    db.refresh(batch)
    assert decision.decision == "DEPLOYMENT_BLOCKED"
    assert batch.status == SimulationBatchStatus.PAUSED_SAFETY_GATE.value
