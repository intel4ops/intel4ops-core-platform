"""AGENTIC-CONTROL-001 Phase N/P: truth isolation invariants.

Two distinct checks:
1. A `SimulationBatchItem` may never carry `truth_accessed_at` earlier
   than `frozen_at` -- enforced at the database (a CHECK constraint), not
   just in application code, so no future code path can silently violate
   it.
2. An `EvidencePackage` claiming `evidence_plane="production"` must
   match the job's own declared plane -- a production-plane job can never
   smuggle validation-plane (truth-derived) evidence in under a
   mismatched label.
"""

from datetime import UTC
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import Organization
from app.models.simulation_batch import (
    SimulationBatch,
    SimulationBatchItem,
    SimulationBatchItemState,
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
from app.services.agent_job_service import AgentJobService, AgentJobServiceError
from app.services.organization_service import OrganizationService
from app.storage.local_storage import LocalFileStorage


def _organization(db: Session, slug: str) -> Organization:
    return OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug.title(), slug=slug, country_code="US", default_currency="USD", timezone="UTC"
        ),
    )


def test_truth_accessed_before_frozen_is_rejected_by_the_database(db: Session) -> None:
    from datetime import datetime

    org = _organization(db, "truth-iso-db")
    batch = SimulationBatch(organization_id=org.id, name="batch-1", status="active")
    db.add(batch)
    db.flush()

    item = SimulationBatchItem(
        batch_id=batch.id,
        organization_id=org.id,
        simulation_id="SIM-TRUTH-001",
        state=SimulationBatchItemState.TERMINAL.value,
        frozen_at=None,
        truth_accessed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    db.add(item)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_truth_accessed_at_or_after_frozen_is_allowed(db: Session) -> None:
    org = _organization(db, "truth-iso-ok")
    batch = SimulationBatch(organization_id=org.id, name="batch-1", status="active")
    db.add(batch)
    db.flush()

    from datetime import datetime

    frozen = datetime(2026, 1, 1, tzinfo=UTC)
    item = SimulationBatchItem(
        batch_id=batch.id,
        organization_id=org.id,
        simulation_id="SIM-TRUTH-002",
        state=SimulationBatchItemState.SCORED.value,
        frozen_at=frozen,
        truth_accessed_at=frozen,
    )
    db.add(item)
    db.commit()  # must not raise


def test_evidence_package_plane_mismatch_is_rejected(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "truth-iso-plane")
    service = AgentJobService(storage=LocalFileStorage(str(tmp_path)))
    mismatched_package = EvidencePackage(
        work_item_id="mismatch-1",
        evidence_plane="validation",  # claims validation-plane evidence...
        risk_class="R0",
        observation=EvidenceObservation(observed_behavior="x"),
        impact=EvidenceImpact(),
        evidence=EvidenceEvidence(),
        control=EvidenceControl(),
        safety=EvidenceSafety(),
        code_context=EvidenceCodeContext(),
        question="q",
    )
    payload = AgentJobCreate(
        job_type="PRODUCTION_TRIAGE",
        risk_class="R0",
        requested_capability="log_triage_v1",
        evidence_plane="production",  # ...but the job declares production-plane
        evidence_package=mismatched_package,
    )
    with pytest.raises(AgentJobServiceError) as excinfo:
        service.create_job(db, org.id, payload, uuid4())
    assert excinfo.value.code == "EVIDENCE_PLANE_MISMATCH"
