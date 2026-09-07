from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.models.agent_jobs import AgentJob, AgentJobStatus
from app.models.entities import Organization
from app.models.simulation_batch import (
    SimulationBatch,
    SimulationBatchItem,
    SimulationBatchItemState,
    SimulationBatchStatus,
)
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
from app.services.agent_job_service import AgentJobService
from app.services.organization_service import OrganizationService
from app.storage.local_storage import LocalFileStorage
from app.validation_program.autonomous_engineering_handoff import (
    AutonomousEngineeringHandoffError,
    AutonomousEngineeringHandoffService,
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


def _batch_with_item(
    db: Session, org_id: UUID, simulation_id: str
) -> tuple[SimulationBatch, SimulationBatchItem]:
    batch = SimulationBatch(
        organization_id=org_id,
        name=f"batch-{simulation_id}",
        status=SimulationBatchStatus.ACTIVE.value,
        created_by_user_id=uuid4(),
    )
    db.add(batch)
    db.flush()
    item = SimulationBatchItem(
        batch_id=batch.id,
        organization_id=org_id,
        simulation_id=simulation_id,
        state=SimulationBatchItemState.MISS_CLASSIFICATION.value,
        frozen_at=None,
    )
    db.add(item)
    db.commit()
    return batch, item


def _classification_job(
    db: Session,
    storage: LocalFileStorage,
    org_id: UUID,
    simulation_id: str,
    gap_class: str,
    action: str,
) -> AgentJob:
    service = AgentJobService(storage=storage)
    evidence = EvidencePackage(
        work_item_id=f"{simulation_id}:family",
        evidence_plane="validation",
        simulation_ids=[simulation_id],
        risk_class="R0",
        observation=EvidenceObservation(observed_behavior="missed expected finding"),
        impact=EvidenceImpact(affected_items=1, simulations_affected=1),
        evidence=EvidenceEvidence(),
        control=EvidenceControl(),
        safety=EvidenceSafety(fp_exposure="low"),
        code_context=EvidenceCodeContext(),
        question="classify",
    )
    job = service.create_job(
        db,
        org_id,
        AgentJobCreate(
            job_type="MISS_CLASSIFICATION",
            risk_class="R0",
            requested_capability="gap_classification_v1",
            evidence_plane="validation",
            simulation_id=simulation_id,
            evidence_package=evidence,
            client_idempotency_key=f"test:{simulation_id}",
        ),
        created_by_user_id=uuid4(),
    )
    job.status = AgentJobStatus.SUCCEEDED.value
    job.result_ref = service._write_json(  # noqa: SLF001 -- test fixture
        f"agent-jobs/{job.id}/result.json",
        {
            "primary_gap_class": gap_class,
            "confidence": 95,
            "recommended_action": action,
        },
    )
    db.commit()
    return job


def test_handoff_is_batch_scoped_and_stops_at_owner_gate(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "ac002b-scope")
    storage = LocalFileStorage(str(tmp_path / "storage"))
    batch, item = _batch_with_item(db, org.id, "SIM-AC002B-001")
    other_batch, _ = _batch_with_item(db, org.id, "SIM-AC002B-OTHER")

    wanted = _classification_job(
        db,
        storage,
        org.id,
        "SIM-AC002B-001",
        "INTELLIGENCE_CAPABILITY_GAP",
        "add bounded detector coverage",
    )
    unwanted = _classification_job(
        db,
        storage,
        org.id,
        "SIM-AC002B-OTHER",
        "MAPPING_GAP",
        "change mapping",
    )

    result = AutonomousEngineeringHandoffService(storage).prepare(db, org.id, batch.id)
    reader = AgentJobService(storage=storage)
    decision = reader._read_json(result.decision_package_ref)  # noqa: SLF001
    handoff = reader._read_json(result.engineering_handoff_ref)  # noqa: SLF001

    assert decision["batch_id"] == str(batch.id)
    assert decision["gap_clusters"] == [
        {
            "gap_class": "INTELLIGENCE_CAPABILITY_GAP",
            "job_count": 1,
            "job_ids": [str(wanted.id)],
            "recommended_actions": ["add bounded detector coverage"],
            "simulations_affected": ["SIM-AC002B-001"],
        }
    ]
    assert str(unwanted.id) not in str(decision)
    assert str(other_batch.id) not in str(decision)

    assert handoff["target_worker_profile"] == "CODEX_IMPLEMENTATION"
    assert handoff["handoff_state"] == "OWNER_APPROVAL_REQUIRED"
    assert handoff["dispatch_allowed"] is False
    assert handoff["owner_gate"]["required"] is True
    assert handoff["owner_gate"]["decision"] is None

    db.refresh(batch)
    db.refresh(item)
    assert batch.status == SimulationBatchStatus.OWNER_REVIEW_REQUIRED.value
    assert item.state == SimulationBatchItemState.GAP_CLUSTERING.value


def test_handoff_rejects_incomplete_classification(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "ac002b-incomplete")
    storage = LocalFileStorage(str(tmp_path / "storage"))
    batch, _ = _batch_with_item(db, org.id, "SIM-AC002B-PENDING")

    service = AgentJobService(storage=storage)
    evidence = EvidencePackage(
        work_item_id="pending",
        evidence_plane="validation",
        simulation_ids=["SIM-AC002B-PENDING"],
        risk_class="R0",
        observation=EvidenceObservation(observed_behavior="miss"),
        impact=EvidenceImpact(),
        evidence=EvidenceEvidence(),
        control=EvidenceControl(),
        safety=EvidenceSafety(),
        code_context=EvidenceCodeContext(),
        question="classify",
    )
    service.create_job(
        db,
        org.id,
        AgentJobCreate(
            job_type="MISS_CLASSIFICATION",
            risk_class="R0",
            requested_capability="gap_classification_v1",
            evidence_plane="validation",
            simulation_id="SIM-AC002B-PENDING",
            evidence_package=evidence,
        ),
        created_by_user_id=uuid4(),
    )

    with pytest.raises(AutonomousEngineeringHandoffError) as excinfo:
        AutonomousEngineeringHandoffService(storage).prepare(db, org.id, batch.id)

    assert excinfo.value.code == "CLASSIFICATION_INCOMPLETE"
