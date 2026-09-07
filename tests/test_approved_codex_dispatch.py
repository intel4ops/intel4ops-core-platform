from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

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
from app.models.simulation_batch import (
    SimulationBatch,
    SimulationBatchItem,
    SimulationBatchItemState,
    SimulationBatchStatus,
)
from app.schemas.contracts import OrganizationCreate
from app.services.agent_job_service import AgentJobService
from app.services.organization_service import OrganizationService
from app.storage.local_storage import LocalFileStorage
from app.validation_program.approved_codex_dispatch import ApprovedCodexDispatchService


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


def _owner_review_batch(
    db: Session, org_id: UUID, simulation_id: str
) -> tuple[SimulationBatch, SimulationBatchItem]:
    batch = SimulationBatch(
        organization_id=org_id,
        name=f"batch-{simulation_id}",
        status=SimulationBatchStatus.OWNER_REVIEW_REQUIRED.value,
        decision_package_ref=f"simulation-batches/{simulation_id}/decision.json",
        created_by_user_id=uuid4(),
    )
    db.add(batch)
    db.flush()
    item = SimulationBatchItem(
        batch_id=batch.id,
        organization_id=org_id,
        simulation_id=simulation_id,
        state=SimulationBatchItemState.GAP_CLUSTERING.value,
    )
    db.add(item)
    db.commit()
    return batch, item


def _write_handoff(
    storage: LocalFileStorage, org_id: UUID, batch: SimulationBatch, simulation_id: str
) -> str:
    service = AgentJobService(storage=storage)
    ref = f"simulation-batches/{batch.id}/engineering-handoff.json"
    service._write_json(  # noqa: SLF001 -- fixture writes the AC-002B artifact
        ref,
        {
            "schema_version": "ac002b-engineering-handoff-v1",
            "batch_id": str(batch.id),
            "organization_id": str(org_id),
            "decision_package_ref": batch.decision_package_ref,
            "target_worker_profile": "CODEX_IMPLEMENTATION",
            "handoff_state": "OWNER_APPROVAL_REQUIRED",
            "dispatch_allowed": False,
            "work_items": [
                {
                    "gap_class": "INTELLIGENCE_CAPABILITY_GAP",
                    "job_ids": [str(uuid4())],
                    "simulations_affected": [simulation_id],
                    "job_count": 1,
                    "recommended_actions": ["add bounded detector coverage"],
                }
            ],
            "owner_gate": {
                "required": True,
                "decision": None,
                "next_action_if_approved": "Create a bounded CODEX_IMPLEMENTATION work item.",
                "next_action_if_rejected": "Close without implementation.",
            },
        },
    )
    return ref


def test_owner_approval_creates_bounded_codex_job(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "ac002c-approve")
    storage = LocalFileStorage(str(tmp_path / "storage"))
    batch, item = _owner_review_batch(db, org.id, "SIM-AC002C-001")
    handoff_ref = _write_handoff(storage, org.id, batch, item.simulation_id)
    owner_id = uuid4()

    result = ApprovedCodexDispatchService(storage).decide(
        db,
        org.id,
        batch.id,
        approve=True,
        note="approved bounded implementation",
        owner_user_id=owner_id,
    )

    assert result.decision == "APPROVED"
    assert result.dispatch_authorized is True
    assert result.provider_execution_started is False
    assert result.implementation_job_id is not None

    job = db.scalar(select(AgentJob).where(AgentJob.id == result.implementation_job_id))
    assert job is not None
    assert job.organization_id == org.id
    assert job.job_type == "CODEX_IMPLEMENTATION"
    assert job.risk_class == AgentJobRiskClass.R2.value
    assert job.status == AgentJobStatus.QUEUED.value
    assert job.assigned_worker == AgentWorkerProfile.CODEX_IMPLEMENTATION.value
    assert job.owner_approval_required is True
    assert job.owner_approval_status == AgentJobOwnerApprovalStatus.APPROVED.value
    assert job.evidence_plane == "validation"
    assert job.created_by_user_id == owner_id

    evidence = AgentJobService(storage=storage).get_evidence_package(job)
    assert evidence.simulation_ids == ["SIM-AC002C-001"]
    assert evidence.evidence.source_artifact_refs == [batch.decision_package_ref, handoff_ref]
    assert "hidden-truth" in (evidence.safety.truth_isolation_constraints or "")
    assert "Do not merge or deploy automatically" in evidence.question

    events = list(
        db.scalars(
            select(AgentJobEvent)
            .where(AgentJobEvent.agent_job_id == job.id)
            .order_by(AgentJobEvent.created_at, AgentJobEvent.id)
        )
    )
    assert {event.event_type for event in events} == {"CREATED", "ROUTED", "OWNER_APPROVED"}

    handoff = AgentJobService(storage=storage)._read_json(handoff_ref)  # noqa: SLF001
    assert handoff["owner_gate"]["decision"] == "APPROVED"
    assert handoff["handoff_state"] == "DISPATCH_AUTHORIZED"
    assert handoff["dispatch_allowed"] is True
    assert handoff["implementation_job_id"] == str(job.id)
    assert handoff["provider_execution_started"] is False

    db.refresh(batch)
    db.refresh(item)
    assert batch.status == SimulationBatchStatus.ACTIVE.value
    assert item.state == SimulationBatchItemState.REMEDIATION_REVIEW.value


def test_owner_rejection_closes_handoff_without_job(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "ac002c-reject")
    storage = LocalFileStorage(str(tmp_path / "storage"))
    batch, item = _owner_review_batch(db, org.id, "SIM-AC002C-REJECT")
    handoff_ref = _write_handoff(storage, org.id, batch, item.simulation_id)

    result = ApprovedCodexDispatchService(storage).decide(
        db,
        org.id,
        batch.id,
        approve=False,
        note="do not implement",
        owner_user_id=uuid4(),
    )

    assert result.decision == "REJECTED"
    assert result.implementation_job_id is None
    assert result.dispatch_authorized is False
    assert db.scalar(
        select(AgentJob).where(
            AgentJob.organization_id == org.id,
            AgentJob.job_type == "CODEX_IMPLEMENTATION",
        )
    ) is None

    handoff = AgentJobService(storage=storage)._read_json(handoff_ref)  # noqa: SLF001
    assert handoff["owner_gate"]["decision"] == "REJECTED"
    assert handoff["handoff_state"] == "OWNER_REJECTED"
    assert handoff["dispatch_allowed"] is False

    db.refresh(batch)
    db.refresh(item)
    assert batch.status == SimulationBatchStatus.COMPLETE.value
    assert item.state == SimulationBatchItemState.BLOCKED.value
    assert item.block_reason == "Owner rejected AC-002B engineering handoff"
