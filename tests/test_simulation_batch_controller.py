"""AGENTIC-CONTROL-001 Phase H/I/J/K/P: SimulationBatchController --
happy path (discover -> select -> prepare -> run -> score -> classify ->
cluster -> decision package), a safety-gate pause blocking the next
batch, and validation-before-terminal rejection (delegated to, and
enforced by, `validation_service.validate_run` itself)."""

from pathlib import Path
from uuid import uuid4

import pytest
from corpus_discovery_fixtures import valid_package
from sqlalchemy.orm import Session

from app.ground_truth_validation.service import ValidationServiceError, validation_service
from app.models.agent_jobs import AgentJobStatus
from app.models.entities import Organization
from app.models.simulation_batch import SimulationBatchItemState, SimulationBatchStatus
from app.schemas.contracts import OrganizationCreate
from app.services.agent_job_service import AgentJobService
from app.services.organization_service import OrganizationService
from app.storage.local_storage import LocalFileStorage
from app.validation_program.batch_controller import (
    SimulationBatchController,
    SimulationControllerError,
)


def _organization(db: Session, slug: str) -> Organization:
    return OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug.title(), slug=slug, country_code="US", default_currency="USD", timezone="UTC"
        ),
    )


def test_batch_controller_happy_path_discover_through_gap_clustering(
    db: Session, tmp_path: Path
) -> None:
    org = _organization(db, "batch-happy")
    corpus_root = tmp_path / "corpus"
    valid_package(corpus_root, "FieldMaintenance", "SIM-AC001-001", leakage_value=5000.0)

    storage = LocalFileStorage(str(tmp_path / "storage"))
    controller = SimulationBatchController(storage=storage)
    actor = uuid4()

    candidates = controller.discover_candidates(db, org.id, corpus_root)
    assert [c.simulation_id for c in candidates] == ["SIM-AC001-001"]

    batch = controller.select_batch(db, org.id, corpus_root, actor, name="batch-1", batch_size=5)
    from sqlalchemy import select

    from app.models.simulation_batch import SimulationBatchItem

    item = db.scalar(select(SimulationBatchItem).where(SimulationBatchItem.batch_id == batch.id))
    assert item is not None
    assert item.state == SimulationBatchItemState.SELECTED.value

    controller.prepare_batch(db, batch.id, corpus_root, actor)
    db.refresh(item)
    assert item.analysis_case_id is not None

    controller.run_batch(db, batch.id, actor)
    db.refresh(item)
    assert item.state == SimulationBatchItemState.SCORED.value
    assert item.frozen_at is not None
    assert item.truth_accessed_at is not None
    assert item.truth_accessed_at >= item.frozen_at
    # The synthetic package's expected finding has no real production
    # capability behind it -- it must show up as a miss, not a phantom TP.
    assert item.false_negative_count and item.false_negative_count >= 1

    job_ids = controller.create_miss_classification_jobs(db, batch.id, actor)
    assert len(job_ids) == 1

    # Drive the created job to a terminal SUCCEEDED state the same way a
    # real local worker would, to prove the full pipeline end to end.
    from app.models.agent_jobs import AgentWorkerCredential

    credential = AgentWorkerCredential(
        organization_id=org.id,
        worker_id=f"w-{uuid4()}",
        token_hash="x",
        allowed_risk_classes=["R0", "R1"],
    )
    db.add(credential)
    db.commit()
    job_service = AgentJobService(storage=storage)
    claim = job_service.claim_next(db, credential)
    assert claim is not None
    result_job = job_service.submit_result(
        db,
        claim,
        {
            "primary_gap_class": "INTELLIGENCE_CAPABILITY_GAP",
            "secondary_gap_classes": [],
            "confidence": 93,
            "summary": "No capability covers this scenario family yet",
            "evidence_refs": [],
            "fp_risk": "low",
            "architecture_impact": False,
            "policy_dependency": False,
            "data_contract_dependency": False,
            "recommended_action": "discovery only",
            "escalate": False,
            "escalation_reason": None,
        },
        execution_time_ms=700,
        input_tokens=300,
        output_tokens=90,
        reasoning_tokens=0,
        model_identifier="qwen/qwen3.5-9b",
    )
    assert result_job.status == AgentJobStatus.SUCCEEDED.value

    ref = controller.build_decision_package(db, batch.id)
    assert ref is not None
    package = job_service._read_json(ref)  # noqa: SLF001 -- test-only introspection
    assert package["gap_clusters"][0]["gap_class"] == "INTELLIGENCE_CAPABILITY_GAP"
    assert package["gap_clusters"][0]["simulations_affected"] == ["SIM-AC001-001"]

    from app.models.simulation_batch import SimulationBatch

    refreshed_batch = db.get(SimulationBatch, batch.id)
    assert refreshed_batch is not None
    assert refreshed_batch.status == SimulationBatchStatus.OWNER_REVIEW_REQUIRED.value


def test_select_batch_rejects_when_a_prior_batch_is_paused(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "batch-safety-gate")
    corpus_root = tmp_path / "corpus"
    valid_package(corpus_root, "FieldMaintenance", "SIM-AC001-GATE", leakage_value=100.0)
    storage = LocalFileStorage(str(tmp_path / "storage"))
    controller = SimulationBatchController(storage=storage)
    actor = uuid4()

    batch = controller.select_batch(db, org.id, corpus_root, actor, name="batch-1")
    controller.pause_for_safety(db, batch.id, "simulated R3 issue pending owner review")

    with pytest.raises(SimulationControllerError) as excinfo:
        controller.select_batch(db, org.id, corpus_root, actor, name="batch-2")
    assert excinfo.value.code == "SAFETY_GATE_OPEN"


def test_validate_run_rejects_a_non_terminal_run(db: Session, tmp_path: Path) -> None:
    """Validation-before-terminal rejection is enforced by
    validation_service.validate_run itself (which this controller
    delegates to via wave_coordinator) -- exercised directly here since
    it is the exact mechanism the mission's Phase P calls out by name."""
    from app.services.analysis_case_orchestration_service import analysis_case_orchestration_service
    from app.services.analysis_case_service import AnalysisCaseService, UploadedFile

    org = _organization(db, "batch-non-terminal")
    storage = LocalFileStorage(str(tmp_path / "storage"))
    service = AnalysisCaseService(storage=storage)
    actor = uuid4()
    case = service.create(db, org.id, "Non-terminal case", "single", actor)
    service.register_artifacts(
        db,
        org.id,
        case.id,
        [UploadedFile("maintenance_events.csv", b"asset_id,failure_code\nV1,brake\n")],
        actor,
    )
    simulation = validation_service.create_simulation(
        db, org.id, "SIM-NONTERMINAL", "SIM-NONTERMINAL", case.id, actor
    )
    validation_service.upload_ground_truth(
        db, org.id, simulation.id, {"expected_findings": []}, actor
    )
    run = analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
    # Deliberately never call execute() -- the run stays "running".

    with pytest.raises(ValidationServiceError) as excinfo:
        validation_service.validate_run(db, org.id, simulation.id, run.id, actor)
    assert excinfo.value.code == "run_not_terminal"
