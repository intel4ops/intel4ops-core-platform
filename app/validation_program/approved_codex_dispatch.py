"""AC-002C: owner-approved creation of a bounded Codex implementation work item.

This module deliberately does not call Codex, merge code, or deploy anything.
It converts an AC-002B engineering handoff into one durable, auditable
``CODEX_IMPLEMENTATION`` AgentJob only after an explicit owner decision.
The resulting job is not claimable by the R0/R1 Local Worker Bridge.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NoReturn
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent_jobs import (
    AgentJob,
    AgentJobEvent,
    AgentJobEventType,
    AgentJobOwnerApprovalStatus,
    AgentJobRiskClass,
    AgentJobStatus,
    AgentWorkerProfile,
)
from app.models.entities import utc_now
from app.models.simulation_batch import (
    SimulationBatch,
    SimulationBatchItem,
    SimulationBatchItemState,
    SimulationBatchStatus,
)
from app.schemas.agent_jobs import (
    EvidenceCodeContext,
    EvidenceControl,
    EvidenceEvidence,
    EvidenceImpact,
    EvidenceObservation,
    EvidencePackage,
    EvidenceSafety,
)
from app.services.agent_job_service import AgentJobService
from app.storage.base import StorageBackend

_JOB_TYPE = "CODEX_IMPLEMENTATION"
_CAPABILITY = "bounded_implementation_from_approved_handoff_v1"


class ApprovedCodexDispatchError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def _fail(code: str, message: str, status: int = 400) -> NoReturn:
    raise ApprovedCodexDispatchError(code, message, status)


@dataclass(frozen=True)
class CodexDispatchResult:
    batch_id: UUID
    decision: str
    implementation_job_id: UUID | None
    dispatch_authorized: bool
    provider_execution_started: bool = False


class ApprovedCodexDispatchService:
    """Apply the owner decision to one AC-002B handoff and, if approved,
    create exactly one bounded Codex implementation AgentJob.
    """

    def __init__(self, storage: StorageBackend) -> None:
        self._agent_jobs = AgentJobService(storage=storage)

    def _handoff_ref(self, batch_id: UUID) -> str:
        return f"simulation-batches/{batch_id}/engineering-handoff.json"

    def _get_batch(self, db: Session, organization_id: UUID, batch_id: UUID) -> SimulationBatch:
        batch = db.scalar(
            select(SimulationBatch).where(
                SimulationBatch.id == batch_id,
                SimulationBatch.organization_id == organization_id,
            )
        )
        if batch is None:
            _fail("BATCH_NOT_FOUND", "Simulation batch not found", 404)
        return batch

    def _get_items(
        self, db: Session, organization_id: UUID, batch_id: UUID
    ) -> list[SimulationBatchItem]:
        return list(
            db.scalars(
                select(SimulationBatchItem)
                .where(
                    SimulationBatchItem.batch_id == batch_id,
                    SimulationBatchItem.organization_id == organization_id,
                )
                .order_by(SimulationBatchItem.created_at, SimulationBatchItem.id)
            )
        )

    def _load_and_validate_handoff(
        self, organization_id: UUID, batch_id: UUID
    ) -> tuple[str, dict[str, Any]]:
        handoff_ref = self._handoff_ref(batch_id)
        try:
            handoff = self._agent_jobs._read_json(handoff_ref)  # noqa: SLF001
        except (FileNotFoundError, KeyError, ValueError) as exc:
            raise ApprovedCodexDispatchError(
                "HANDOFF_NOT_FOUND", "AC-002B engineering handoff not found", 409
            ) from exc

        if handoff.get("schema_version") != "ac002b-engineering-handoff-v1":
            _fail("HANDOFF_SCHEMA_INVALID", "Unsupported engineering handoff schema", 409)
        if handoff.get("organization_id") != str(organization_id):
            _fail("HANDOFF_ORGANIZATION_MISMATCH", "Engineering handoff organization mismatch", 409)
        if handoff.get("batch_id") != str(batch_id):
            _fail("HANDOFF_BATCH_MISMATCH", "Engineering handoff batch mismatch", 409)
        if handoff.get("target_worker_profile") != AgentWorkerProfile.CODEX_IMPLEMENTATION.value:
            _fail("HANDOFF_TARGET_INVALID", "Engineering handoff does not target Codex", 409)
        if handoff.get("handoff_state") != "OWNER_APPROVAL_REQUIRED":
            _fail(
                "HANDOFF_ALREADY_DECIDED", "Engineering handoff is not awaiting owner approval", 409
            )
        if handoff.get("dispatch_allowed") is not False:
            _fail("HANDOFF_DISPATCH_STATE_INVALID", "Unapproved handoff cannot allow dispatch", 409)
        owner_gate = handoff.get("owner_gate") or {}
        if owner_gate.get("required") is not True or owner_gate.get("decision") is not None:
            _fail("HANDOFF_OWNER_GATE_INVALID", "Engineering handoff owner gate is invalid", 409)
        if not handoff.get("decision_package_ref"):
            _fail(
                "HANDOFF_DECISION_PACKAGE_MISSING",
                "Engineering handoff has no decision package",
                409,
            )
        return handoff_ref, handoff

    def _existing_job(self, db: Session, organization_id: UUID, batch_id: UUID) -> AgentJob | None:
        return db.scalar(
            select(AgentJob).where(
                AgentJob.organization_id == organization_id,
                AgentJob.job_type == _JOB_TYPE,
                AgentJob.client_idempotency_key == f"ac002c:{batch_id}:codex",
            )
        )

    def _build_evidence(
        self, batch_id: UUID, handoff_ref: str, handoff: dict[str, Any]
    ) -> EvidencePackage:
        work_items = handoff.get("work_items") or []
        simulation_ids = sorted(
            {
                str(simulation_id)
                for item in work_items
                for simulation_id in (item.get("simulations_affected") or [])
            }
        )
        actions = [
            str(action)
            for item in work_items
            for action in (item.get("recommended_actions") or [])
            if str(action).strip()
        ]
        gap_classes = sorted(
            {str(item.get("gap_class")) for item in work_items if item.get("gap_class")}
        )
        return EvidencePackage(
            work_item_id=f"ac002c:{batch_id}",
            evidence_plane="validation",
            simulation_ids=simulation_ids,
            risk_class=AgentJobRiskClass.R2.value,
            observation=EvidenceObservation(
                observed_behavior=(
                    "Owner-approved simulation gap clusters require a bounded "
                    "implementation change."
                ),
                expected_capability_behavior=(
                    "Implement only the approved bounded remediation and preserve "
                    "all existing gates."
                ),
            ),
            impact=EvidenceImpact(
                affected_items=len(work_items), simulations_affected=len(simulation_ids)
            ),
            evidence=EvidenceEvidence(
                source_artifact_refs=[str(handoff["decision_package_ref"]), handoff_ref]
            ),
            control=EvidenceControl(existing_capabilities=gap_classes),
            safety=EvidenceSafety(
                fp_exposure="unknown",
                truth_isolation_constraints=(
                    "Use only the summarized AC-002B decision/handoff artifacts. "
                    "Never read hidden-truth package files and never introduce "
                    "validation-plane dependencies into production execution."
                ),
            ),
            code_context=EvidenceCodeContext(),
            question=(
                "Prepare a bounded implementation for the owner-approved actions: "
                + ("; ".join(actions) if actions else "the approved AC-002B work items")
                + ". Do not merge or deploy automatically."
            ),
        )

    def _create_job(
        self,
        db: Session,
        organization_id: UUID,
        batch_id: UUID,
        handoff_ref: str,
        handoff: dict[str, Any],
        owner_user_id: UUID | None,
        note: str | None,
    ) -> AgentJob:
        existing = self._existing_job(db, organization_id, batch_id)
        if existing is not None:
            return existing

        evidence = self._build_evidence(batch_id, handoff_ref, handoff)
        job = AgentJob(
            organization_id=organization_id,
            job_type=_JOB_TYPE,
            risk_class=AgentJobRiskClass.R2.value,
            status=AgentJobStatus.QUEUED.value,
            priority=0,
            evidence_plane="validation",
            requested_capability=_CAPABILITY,
            assigned_worker=AgentWorkerProfile.CODEX_IMPLEMENTATION.value,
            prompt_template_version="ac002c-v1",
            owner_approval_required=True,
            owner_approval_status=AgentJobOwnerApprovalStatus.APPROVED.value,
            created_by_user_id=owner_user_id,
            client_idempotency_key=f"ac002c:{batch_id}:codex",
        )
        db.add(job)
        db.flush()
        job.input_evidence_ref = self._agent_jobs._write_json(  # noqa: SLF001
            f"agent-jobs/{job.id}/evidence.json", evidence.model_dump(mode="json")
        )
        db.add_all(
            [
                AgentJobEvent(
                    agent_job_id=job.id,
                    organization_id=organization_id,
                    event_type=AgentJobEventType.CREATED.value,
                    detail_json={"job_type": _JOB_TYPE, "source": "AC-002C"},
                    idempotency_key=str(uuid4()),
                ),
                AgentJobEvent(
                    agent_job_id=job.id,
                    organization_id=organization_id,
                    event_type=AgentJobEventType.ROUTED.value,
                    detail_json={
                        "worker_profile": AgentWorkerProfile.CODEX_IMPLEMENTATION.value,
                        "local_allowed": False,
                        "owner_gate_required": True,
                        "reasoning": (
                            "Explicit AC-002C dispatch from owner-approved "
                            "AC-002B handoff"
                        ),
                    },
                    idempotency_key=str(uuid4()),
                ),
                AgentJobEvent(
                    agent_job_id=job.id,
                    organization_id=organization_id,
                    event_type=AgentJobEventType.OWNER_APPROVED.value,
                    detail_json={"note": note, "source": "AC-002B engineering handoff"},
                    idempotency_key=str(uuid4()),
                ),
            ]
        )
        return job

    def decide(
        self,
        db: Session,
        organization_id: UUID,
        batch_id: UUID,
        approve: bool,
        note: str | None,
        owner_user_id: UUID | None,
    ) -> CodexDispatchResult:
        batch = self._get_batch(db, organization_id, batch_id)
        if batch.status != SimulationBatchStatus.OWNER_REVIEW_REQUIRED.value:
            _fail(
                "BATCH_NOT_AWAITING_OWNER",
                "Simulation batch is not awaiting an owner engineering decision",
                409,
            )
        items = self._get_items(db, organization_id, batch_id)
        if not items:
            _fail("EMPTY_BATCH", "Simulation batch contains no items", 409)
        handoff_ref, handoff = self._load_and_validate_handoff(organization_id, batch_id)

        decided_at = utc_now().isoformat()
        handoff["owner_gate"] = {
            **handoff["owner_gate"],
            "decision": "APPROVED" if approve else "REJECTED",
            "decided_at": decided_at,
            "decided_by_user_id": str(owner_user_id) if owner_user_id else None,
            "note": note,
        }

        if not approve:
            handoff["handoff_state"] = "OWNER_REJECTED"
            handoff["dispatch_allowed"] = False
            handoff["provider_execution_started"] = False
            self._agent_jobs._write_json(handoff_ref, handoff)  # noqa: SLF001
            batch.status = SimulationBatchStatus.COMPLETE.value
            for item in items:
                if item.state == SimulationBatchItemState.GAP_CLUSTERING.value:
                    item.state = SimulationBatchItemState.BLOCKED.value
                    item.block_reason = "Owner rejected AC-002B engineering handoff"
            db.commit()
            return CodexDispatchResult(
                batch_id=batch_id,
                decision="REJECTED",
                implementation_job_id=None,
                dispatch_authorized=False,
            )

        job = self._create_job(
            db,
            organization_id,
            batch_id,
            handoff_ref,
            handoff,
            owner_user_id,
            note,
        )
        handoff["handoff_state"] = "DISPATCH_AUTHORIZED"
        handoff["dispatch_allowed"] = True
        handoff["implementation_job_id"] = str(job.id)
        handoff["provider_execution_started"] = False
        handoff["next_action"] = (
            "A premium Codex dispatcher may consume the approved AgentJob; "
            "automatic merge/deploy remains prohibited."
        )
        self._agent_jobs._write_json(handoff_ref, handoff)  # noqa: SLF001

        batch.status = SimulationBatchStatus.ACTIVE.value
        for item in items:
            if item.state == SimulationBatchItemState.GAP_CLUSTERING.value:
                item.state = SimulationBatchItemState.REMEDIATION_REVIEW.value
        db.commit()
        return CodexDispatchResult(
            batch_id=batch_id,
            decision="APPROVED",
            implementation_job_id=job.id,
            dispatch_authorized=True,
        )
