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
from app.schemas.autonomous_verification_retest import (
    VerificationRetestComplete,
    VerificationSimulationResult,
)
from app.schemas.contracts import OrganizationCreate
from app.services.agent_job_service import AgentJobService
from app.services.organization_service import OrganizationService
from app.storage.local_storage import LocalFileStorage
from app.validation_program.autonomous_verification_retest import (
    AutonomousVerificationRetestError,
    AutonomousVerificationRetestService,
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
) -> tuple[SimulationBatch, list[SimulationBatchItem], AgentJob]:
    batch = SimulationBatch(
        organization_id=org.id,
        name="AC-002E verification batch",
        status=SimulationBatchStatus.ACTIVE.value,
        created_by_user_id=uuid4(),
    )
    db.add(batch)
    db.flush()
    items = [
        SimulationBatchItem(
            batch_id=batch.id,
            organization_id=org.id,
            simulation_id="SIM-AC002E-001",
            state=SimulationBatchItemState.REMEDIATION_REVIEW.value,
            true_positive_count=3,
            false_positive_count=1,
            false_negative_count=2,
        ),
        SimulationBatchItem(
            batch_id=batch.id,
            organization_id=org.id,
            simulation_id="SIM-AC002E-002",
            state=SimulationBatchItemState.REMEDIATION_REVIEW.value,
            true_positive_count=2,
            false_positive_count=0,
            false_negative_count=1,
        ),
    ]
    db.add_all(items)
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
    job.result_ref = AgentJobService(storage=storage)._write_json(  # noqa: SLF001
        f"agent-jobs/{job.id}/result.json",
        {
            "schema_version": "ac002d-premium-codex-result-v1",
            "branch_name": "agent/fix-gap",
            "head_sha": "a" * 40,
            "pull_request_number": 901,
            "pull_request_url": "https://github.com/intel4ops/intel4ops-core-platform/pull/901",
            "automatic_merge_performed": False,
            "automatic_deploy_performed": False,
        },
    )
    db.commit()
    return batch, items, job


def test_verified_improvement_moves_to_owner_review(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "ac002e-pass")
    storage = LocalFileStorage(str(tmp_path / "storage"))
    batch, items, job = _scenario(db, storage, org)
    service = AutonomousVerificationRetestService(storage)

    lease = service.start(db, org.id, job.id, "verification-worker")
    manifest = AgentJobService(storage=storage)._read_json(lease.manifest_ref)  # noqa: SLF001
    assert manifest["candidate"]["head_sha"] == "a" * 40
    assert manifest["simulation_ids"] == ["SIM-AC002E-001", "SIM-AC002E-002"]
    assert manifest["automatic_merge_allowed"] is False
    assert manifest["automatic_deploy_allowed"] is False
    assert all(item.state == SimulationBatchItemState.RETEST.value for item in items)

    decision = service.complete(
        db,
        org.id,
        job.id,
        VerificationRetestComplete(
            lease_id=lease.lease_id,
            outcome="scored",
            candidate_head_sha="a" * 40,
            pull_request_number=901,
            results=[
                VerificationSimulationResult(
                    simulation_id="SIM-AC002E-001",
                    true_positive_count=4,
                    false_positive_count=1,
                    false_negative_count=1,
                ),
                VerificationSimulationResult(
                    simulation_id="SIM-AC002E-002",
                    true_positive_count=2,
                    false_positive_count=0,
                    false_negative_count=0,
                ),
            ],
            summary="targeted misses reduced with no regression",
        ),
    )

    db.refresh(batch)
    assert decision.decision == "VERIFIED_IMPROVEMENT"
    assert decision.owner_review_required is True
    assert batch.status == SimulationBatchStatus.OWNER_REVIEW_REQUIRED.value
    assert all(item.state == SimulationBatchItemState.GRADUATED.value for item in items)


def test_regression_pauses_safety_gate(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "ac002e-regression")
    storage = LocalFileStorage(str(tmp_path / "storage"))
    batch, items, job = _scenario(db, storage, org)
    service = AutonomousVerificationRetestService(storage)
    lease = service.start(db, org.id, job.id, "verification-worker")

    decision = service.complete(
        db,
        org.id,
        job.id,
        VerificationRetestComplete(
            lease_id=lease.lease_id,
            outcome="scored",
            candidate_head_sha="a" * 40,
            pull_request_number=901,
            results=[
                VerificationSimulationResult(
                    simulation_id="SIM-AC002E-001",
                    true_positive_count=3,
                    false_positive_count=2,
                    false_negative_count=1,
                ),
                VerificationSimulationResult(
                    simulation_id="SIM-AC002E-002",
                    true_positive_count=2,
                    false_positive_count=0,
                    false_negative_count=0,
                ),
            ],
            summary="false positives increased",
        ),
    )

    db.refresh(batch)
    assert decision.decision == "REGRESSION"
    assert decision.owner_review_required is False
    assert batch.status == SimulationBatchStatus.PAUSED_SAFETY_GATE.value
    assert all(item.state == SimulationBatchItemState.REGRESSION.value for item in items)


def test_retest_rejects_candidate_mismatch(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "ac002e-mismatch")
    storage = LocalFileStorage(str(tmp_path / "storage"))
    _batch, _items, job = _scenario(db, storage, org)
    service = AutonomousVerificationRetestService(storage)
    lease = service.start(db, org.id, job.id, "verification-worker")

    with pytest.raises(AutonomousVerificationRetestError) as exc_info:
        service.complete(
            db,
            org.id,
            job.id,
            VerificationRetestComplete(
                lease_id=lease.lease_id,
                outcome="scored",
                candidate_head_sha="b" * 40,
                pull_request_number=901,
                results=[],
                summary="wrong candidate",
            ),
        )

    assert exc_info.value.code == "CANDIDATE_SHA_MISMATCH"


def test_retest_requires_exact_simulation_set(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "ac002e-set")
    storage = LocalFileStorage(str(tmp_path / "storage"))
    _batch, _items, job = _scenario(db, storage, org)
    service = AutonomousVerificationRetestService(storage)
    lease = service.start(db, org.id, job.id, "verification-worker")

    with pytest.raises(AutonomousVerificationRetestError) as exc_info:
        service.complete(
            db,
            org.id,
            job.id,
            VerificationRetestComplete(
                lease_id=lease.lease_id,
                outcome="scored",
                candidate_head_sha="a" * 40,
                pull_request_number=901,
                results=[
                    VerificationSimulationResult(
                        simulation_id="SIM-AC002E-001",
                        true_positive_count=4,
                        false_positive_count=1,
                        false_negative_count=1,
                    )
                ],
                summary="partial result set",
            ),
        )

    assert exc_info.value.code == "RETEST_RESULT_SET_INVALID"
