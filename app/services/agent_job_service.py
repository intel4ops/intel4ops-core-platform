"""AGENTIC-CONTROL-001 Phase B/E/O: AgentJob lifecycle -- create, route,
claim, heartbeat, submit result/failure, and stale-lease recovery.

Claim/heartbeat/CAS-guarded-completion mechanics mirror
`app.services.canonical_mapping_service`'s already-proven
`MappingRun` worker-lease pattern exactly (same `SELECT ... FOR UPDATE
SKIP LOCKED` FIFO claim, same lease-ownership-checked UPDATE for every
terminal write, same stale-heartbeat recovery sweep) -- see that
module and `app/workers/mapping_execution.py` for the precedent this
follows rather than duplicates.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from typing import NoReturn
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.agent_jobs import (
    AgentJob,
    AgentJobEvent,
    AgentJobEventType,
    AgentJobOwnerApprovalStatus,
    AgentJobStatus,
    AgentWorkerCredential,
)
from app.models.entities import utc_now
from app.schemas.agent_jobs import AgentJobCreate, EvidencePackage, WorkerStructuredResult
from app.services.agent_routing_service import agent_routing_policy
from app.storage.base import StorageBackend

_TERMINAL_STATUSES = frozenset(
    {
        AgentJobStatus.SUCCEEDED.value,
        AgentJobStatus.FAILED.value,
        AgentJobStatus.TIMED_OUT.value,
        AgentJobStatus.CANCELLED.value,
    }
)


class AgentJobServiceError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class AgentJobLeaseLost(RuntimeError):
    """The worker no longer owns the authoritative execution lease --
    e.g. a stale-recovery sweep already reclaimed this job."""


def _fail(code: str, message: str, status: int = 400) -> NoReturn:
    raise AgentJobServiceError(code, message, status)


@dataclass(frozen=True)
class AgentJobClaim:
    job_id: UUID
    organization_id: UUID | None
    lease_id: UUID
    worker_id: str


class AgentJobService:
    def __init__(self, storage: StorageBackend) -> None:
        self._storage = storage

    def _evidence_key(self, job_id: UUID) -> str:
        return f"agent-jobs/{job_id}/evidence.json"

    def _result_key(self, job_id: UUID) -> str:
        return f"agent-jobs/{job_id}/result.json"

    def _write_json(self, key: str, payload: dict) -> str:
        raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        result = self._storage.write_stream(key, [raw])
        return result.reference

    def _read_json(self, reference: str) -> dict:
        chunks = list(self._storage.open_stream(reference))
        payload: dict = json.loads(b"".join(chunks).decode("utf-8"))
        return payload

    def _record_event(
        self,
        db: Session,
        job: AgentJob,
        event_type: AgentJobEventType,
        detail: dict | None = None,
        idempotency_key: str | None = None,
    ) -> None:
        db.add(
            AgentJobEvent(
                agent_job_id=job.id,
                organization_id=job.organization_id,
                event_type=event_type.value,
                detail_json=detail,
                idempotency_key=idempotency_key or str(uuid4()),
            )
        )

    # -- Phase N truth-isolation guard -------------------------------
    def _enforce_evidence_plane(self, payload: AgentJobCreate) -> None:
        pkg = payload.evidence_package
        if pkg.evidence_plane != payload.evidence_plane:
            _fail(
                "EVIDENCE_PLANE_MISMATCH",
                "evidence_package.evidence_plane must match the job's declared evidence_plane",
                409,
            )
        if payload.evidence_plane == "production":
            # A production-plane job's evidence must never be sourced
            # from validation-plane truth. The EvidencePackage schema has
            # no field for expected/truth values at all under the
            # `evidence` section, but callers could still smuggle a truth
            # value into `impact.affected_economic_value` from truth
            # rather than from persisted production output -- that is a
            # caller discipline this service cannot fully verify from
            # shape alone, so the hard, always-checked invariant lives at
            # the caller boundary instead: `create_miss_classification_jobs`
            # in the simulation batch controller is the ONLY caller
            # permitted to pass evidence_plane="validation", and it may
            # only do so once the referenced SimulationBatchItem has
            # reached FROZEN or later (enforced there, not here, since
            # that is where the frozen/terminal fact actually lives).
            return

    # -- Phase B: create (idempotent) --------------------------------
    def create_job(
        self,
        db: Session,
        organization_id: UUID | None,
        payload: AgentJobCreate,
        created_by_user_id: UUID | None,
    ) -> AgentJob:
        self._enforce_evidence_plane(payload)

        if payload.client_idempotency_key is not None:
            existing = db.scalar(
                select(AgentJob).where(
                    AgentJob.organization_id == organization_id,
                    AgentJob.client_idempotency_key == payload.client_idempotency_key,
                )
            )
            if existing is not None:
                return existing

        routing = agent_routing_policy.route(payload.risk_class)

        job = AgentJob(
            organization_id=organization_id,
            analysis_case_id=payload.analysis_case_id,
            run_id=payload.run_id,
            simulation_id=payload.simulation_id,
            gap_id=payload.gap_id,
            parent_job_id=payload.parent_job_id,
            job_type=payload.job_type,
            risk_class=routing.risk_class,
            status=AgentJobStatus.QUEUED.value,
            priority=payload.priority,
            evidence_plane=payload.evidence_plane,
            requested_capability=payload.requested_capability,
            assigned_model=(
                agent_routing_policy.model_parameters(routing.worker_profile).get("model")
                if routing.local_allowed
                else None
            ),
            prompt_template_version="v1",
            owner_approval_required=routing.owner_gate_required,
            owner_approval_status=(
                AgentJobOwnerApprovalStatus.PENDING.value
                if routing.owner_gate_required
                else AgentJobOwnerApprovalStatus.NOT_REQUIRED.value
            ),
            created_by_user_id=created_by_user_id,
            client_idempotency_key=payload.client_idempotency_key,
        )
        db.add(job)
        db.flush()
        job.input_evidence_ref = self._write_json(
            self._evidence_key(job.id), payload.evidence_package.model_dump(mode="json")
        )
        self._record_event(db, job, AgentJobEventType.CREATED, {"job_type": job.job_type})
        self._record_event(
            db,
            job,
            AgentJobEventType.ROUTED,
            {
                "worker_profile": routing.worker_profile.value,
                "local_allowed": routing.local_allowed,
                "owner_gate_required": routing.owner_gate_required,
                "reasoning": routing.reasoning,
            },
        )
        if routing.owner_gate_required:
            job.status = AgentJobStatus.OWNER_REVIEW_REQUIRED.value
            self._record_event(db, job, AgentJobEventType.OWNER_REVIEW_REQUIRED)
        db.commit()
        return job

    def get(self, db: Session, organization_id: UUID | None, job_id: UUID) -> AgentJob:
        job = db.scalar(
            select(AgentJob).where(
                AgentJob.id == job_id, AgentJob.organization_id == organization_id
            )
        )
        if job is None:
            _fail("AGENT_JOB_NOT_FOUND", "Agent job not found", 404)
        return job

    def get_evidence_package(self, job: AgentJob) -> EvidencePackage:
        assert job.input_evidence_ref is not None
        return EvidencePackage.model_validate(self._read_json(job.input_evidence_ref))

    # -- Phase E/O: claim / heartbeat / stale recovery ----------------
    def claim_next(self, db: Session, credential: AgentWorkerCredential) -> AgentJobClaim | None:
        query = (
            select(AgentJob)
            .where(
                AgentJob.status == AgentJobStatus.QUEUED.value,
                AgentJob.risk_class.in_(credential.allowed_risk_classes),
            )
            .order_by(AgentJob.priority.desc(), AgentJob.created_at.asc(), AgentJob.id.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if credential.allowed_job_types:
            query = query.where(AgentJob.job_type.in_(credential.allowed_job_types))
        job = db.scalar(query)
        if job is None:
            db.rollback()
            return None
        lease_id = uuid4()
        now = utc_now()
        job.status = AgentJobStatus.RUNNING.value
        job.execution_lease_id = lease_id
        job.execution_worker_id = credential.worker_id
        job.assigned_worker = credential.worker_id
        job.heartbeat_at = now
        job.started_at = now
        self._record_event(db, job, AgentJobEventType.CLAIMED, {"worker_id": credential.worker_id})
        self._record_event(db, job, AgentJobEventType.STARTED)
        db.commit()
        return AgentJobClaim(job.id, job.organization_id, lease_id, credential.worker_id)

    def heartbeat(self, db: Session, claim: AgentJobClaim) -> bool:
        result = db.execute(
            update(AgentJob)
            .where(
                AgentJob.id == claim.job_id,
                AgentJob.status == AgentJobStatus.RUNNING.value,
                AgentJob.execution_lease_id == claim.lease_id,
            )
            .values(heartbeat_at=utc_now())
            .execution_options(synchronize_session=False)
        )
        db.commit()
        return getattr(result, "rowcount", 0) == 1

    def recover_stale(self, db: Session, stale_after: timedelta, limit: int = 25) -> list[UUID]:
        stale = list(
            db.scalars(
                select(AgentJob)
                .where(
                    AgentJob.status == AgentJobStatus.RUNNING.value,
                    AgentJob.heartbeat_at.is_not(None),
                    AgentJob.heartbeat_at < utc_now() - stale_after,
                )
                .order_by(AgentJob.heartbeat_at.asc(), AgentJob.id.asc())
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        recovered: list[UUID] = []
        for job in stale:
            can_retry = job.retry_count < 3
            job.execution_lease_id = None
            job.execution_worker_id = None
            job.heartbeat_at = None
            if can_retry:
                job.status = AgentJobStatus.QUEUED.value
                job.retry_count += 1
                self._record_event(
                    db,
                    job,
                    AgentJobEventType.RETRIED,
                    {"reason": "heartbeat_stale", "attempt": job.retry_count},
                )
            else:
                job.status = AgentJobStatus.TIMED_OUT.value
                job.failed_at = utc_now()
                job.error_code = "WORKER_LEASE_STALE"
                job.error_detail = "Heartbeat stale beyond threshold and retry limit exhausted"
                self._record_event(db, job, AgentJobEventType.TIMED_OUT)
            recovered.append(job.id)
        db.commit()
        return recovered

    # -- Phase G/O: structured result submission (CAS-guarded) --------
    def submit_result(
        self,
        db: Session,
        claim: AgentJobClaim,
        raw_result: dict,
        execution_time_ms: int,
        input_tokens: int,
        output_tokens: int,
        reasoning_tokens: int,
        model_identifier: str,
    ) -> AgentJob:
        job = db.scalar(
            select(AgentJob).where(
                AgentJob.id == claim.job_id,
                AgentJob.status == AgentJobStatus.RUNNING.value,
                AgentJob.execution_lease_id == claim.lease_id,
            )
        )
        if job is None:
            db.rollback()
            raise AgentJobLeaseLost(str(claim.job_id))

        try:
            structured = WorkerStructuredResult.model_validate(raw_result)
        except ValidationError as exc:
            # Malformed output is never silently accepted (Phase G).
            job.status = AgentJobStatus.FAILED.value
            job.failed_at = utc_now()
            job.error_code = "MALFORMED_WORKER_OUTPUT"
            job.error_detail = str(exc)[:2000]
            job.execution_lease_id = None
            job.execution_worker_id = None
            self._record_event(db, job, AgentJobEventType.FAILED, {"error_code": job.error_code})
            db.commit()
            return job

        decision = agent_routing_policy.evaluate_worker_result(
            risk_class=job.risk_class,
            confidence=structured.confidence,
            architecture_impact=structured.architecture_impact,
            policy_dependency=structured.policy_dependency,
            worker_requested_escalation=structured.escalate,
        )

        job.confidence = structured.confidence
        job.execution_time_ms = execution_time_ms
        job.input_tokens = input_tokens
        job.output_tokens = output_tokens
        job.reasoning_tokens = reasoning_tokens
        job.assigned_model = model_identifier
        job.completed_at = utc_now()
        job.result_ref = self._write_json(
            self._result_key(job.id), structured.model_dump(mode="json")
        )
        job.execution_lease_id = None
        job.execution_worker_id = None

        if decision.accept:
            job.status = AgentJobStatus.SUCCEEDED.value
            self._record_event(
                db, job, AgentJobEventType.SUCCEEDED, {"confidence": structured.confidence}
            )
        else:
            job.status = AgentJobStatus.ESCALATED.value
            job.escalation_reason = decision.reason
            if decision.owner_gate_required:
                job.owner_approval_required = True
                job.owner_approval_status = AgentJobOwnerApprovalStatus.PENDING.value
            self._record_event(
                db,
                job,
                AgentJobEventType.ESCALATED,
                {
                    "reason": decision.reason,
                    "next_profile": decision.next_profile.value if decision.next_profile else None,
                    "owner_gate_required": decision.owner_gate_required,
                },
            )
            if decision.owner_gate_required:
                self._record_event(db, job, AgentJobEventType.OWNER_REVIEW_REQUIRED)

        db.commit()
        return job

    def submit_failure(
        self, db: Session, claim: AgentJobClaim, error_code: str, error_detail: str, retryable: bool
    ) -> AgentJob:
        job = db.scalar(
            select(AgentJob).where(
                AgentJob.id == claim.job_id,
                AgentJob.status == AgentJobStatus.RUNNING.value,
                AgentJob.execution_lease_id == claim.lease_id,
            )
        )
        if job is None:
            db.rollback()
            raise AgentJobLeaseLost(str(claim.job_id))
        job.execution_lease_id = None
        job.execution_worker_id = None
        if retryable and job.retry_count < 3:
            job.status = AgentJobStatus.QUEUED.value
            job.retry_count += 1
            job.heartbeat_at = None
            self._record_event(
                db,
                job,
                AgentJobEventType.RETRIED,
                {"error_code": error_code, "attempt": job.retry_count},
            )
        else:
            job.status = AgentJobStatus.FAILED.value
            job.failed_at = utc_now()
            job.error_code = error_code
            job.error_detail = error_detail[:2000]
            self._record_event(db, job, AgentJobEventType.FAILED, {"error_code": error_code})
        db.commit()
        return job

    # -- Phase K: owner approval gate ---------------------------------
    def apply_owner_decision(
        self, db: Session, job: AgentJob, approve: bool, note: str | None
    ) -> AgentJob:
        if not job.owner_approval_required:
            _fail("NO_APPROVAL_PENDING", "This job does not require owner approval", 409)
        if job.owner_approval_status != AgentJobOwnerApprovalStatus.PENDING.value:
            _fail(
                "APPROVAL_ALREADY_DECIDED",
                f"Owner approval already recorded as {job.owner_approval_status!r}",
                409,
            )
        job.owner_approval_status = (
            AgentJobOwnerApprovalStatus.APPROVED.value
            if approve
            else AgentJobOwnerApprovalStatus.REJECTED.value
        )
        self._record_event(
            db,
            job,
            AgentJobEventType.OWNER_APPROVED if approve else AgentJobEventType.OWNER_REJECTED,
            {"note": note},
        )
        db.commit()
        return job


def build_agent_job_service(storage: StorageBackend) -> AgentJobService:
    return AgentJobService(storage=storage)
