"""AC-002D: premium Codex execution bridge for approved implementation jobs.

This module starts and completes a bounded premium execution lease. It does
not merge pull requests, deploy code, or grant direct writes to ``main``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent_jobs import (
    AgentJob,
    AgentJobEvent,
    AgentJobEventType,
    AgentJobOwnerApprovalStatus,
    AgentJobStatus,
    AgentWorkerProfile,
)
from app.models.entities import utc_now
from app.schemas.premium_codex_execution import PremiumCodexExecutionComplete
from app.services.agent_job_service import AgentJobService
from app.storage.base import StorageBackend

_JOB_TYPE = "CODEX_IMPLEMENTATION"
_REPOSITORY = "intel4ops/intel4ops-core-platform"


class PremiumCodexExecutionError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def _fail(code: str, message: str, status: int = 400) -> NoReturn:
    raise PremiumCodexExecutionError(code, message, status)


@dataclass(frozen=True)
class PremiumCodexExecutionLease:
    job_id: UUID
    organization_id: UUID
    lease_id: UUID
    worker_id: str
    manifest_ref: str


class PremiumCodexExecutionService:
    """Lease one approved Codex job to a premium executor and record its result."""

    def __init__(self, storage: StorageBackend) -> None:
        self._jobs = AgentJobService(storage=storage)

    def _get_job(self, db: Session, organization_id: UUID, job_id: UUID) -> AgentJob:
        job = db.scalar(
            select(AgentJob).where(
                AgentJob.id == job_id,
                AgentJob.organization_id == organization_id,
            )
        )
        if job is None:
            _fail("CODEX_JOB_NOT_FOUND", "Codex implementation job not found", 404)
        return job

    def _validate_authorized_job(self, job: AgentJob) -> None:
        if job.job_type != _JOB_TYPE:
            _fail("JOB_TYPE_INVALID", "Job is not a Codex implementation job", 409)
        if job.assigned_worker != AgentWorkerProfile.CODEX_IMPLEMENTATION.value:
            _fail("WORKER_PROFILE_INVALID", "Job is not assigned to the Codex profile", 409)
        if job.owner_approval_required is not True:
            _fail("OWNER_GATE_REQUIRED", "Codex implementation job must require owner approval", 409)
        if job.owner_approval_status != AgentJobOwnerApprovalStatus.APPROVED.value:
            _fail("OWNER_APPROVAL_MISSING", "Codex implementation job is not owner-approved", 409)
        if job.evidence_plane != "validation":
            _fail("EVIDENCE_PLANE_INVALID", "Codex implementation job must use validation evidence", 409)
        if not job.input_evidence_ref:
            _fail("EVIDENCE_MISSING", "Codex implementation job has no evidence package", 409)

    def _record_event(
        self,
        db: Session,
        job: AgentJob,
        event_type: AgentJobEventType,
        detail: dict | None = None,
    ) -> None:
        db.add(
            AgentJobEvent(
                agent_job_id=job.id,
                organization_id=job.organization_id,
                event_type=event_type.value,
                detail_json=detail,
                idempotency_key=str(uuid4()),
            )
        )

    def start(
        self,
        db: Session,
        organization_id: UUID,
        job_id: UUID,
        worker_id: str,
    ) -> PremiumCodexExecutionLease:
        job = self._get_job(db, organization_id, job_id)
        self._validate_authorized_job(job)
        if job.status != AgentJobStatus.QUEUED.value:
            _fail("JOB_NOT_QUEUED", "Codex implementation job is not queued", 409)

        evidence = self._jobs.get_evidence_package(job)
        lease_id = uuid4()
        now = utc_now()
        job.status = AgentJobStatus.RUNNING.value
        job.execution_lease_id = lease_id
        job.execution_worker_id = worker_id
        job.heartbeat_at = now
        job.started_at = now

        manifest = {
            "schema_version": "ac002d-premium-codex-execution-v1",
            "job_id": str(job.id),
            "organization_id": str(organization_id),
            "lease_id": str(lease_id),
            "worker_id": worker_id,
            "target_worker_profile": AgentWorkerProfile.CODEX_IMPLEMENTATION.value,
            "repository": _REPOSITORY,
            "base_branch": "main",
            "feature_branch_prefix": f"agent/ac002d/{job.id}",
            "input_evidence_ref": job.input_evidence_ref,
            "simulation_ids": evidence.simulation_ids,
            "question": evidence.question,
            "allowed_activities": [
                "inspect repository code relevant to the approved work item",
                "create a dedicated feature branch from main",
                "edit code only within the approved bounded scope",
                "add or update tests",
                "run Ruff, mypy, Pytest, and Alembic checks as applicable",
                "open a pull request for owner-governed review",
            ],
            "prohibited_activities": [
                "write directly to main",
                "merge a pull request",
                "deploy or modify production infrastructure",
                "read hidden-truth simulation package files",
                "weaken tenant, authentication, evidence, or truth-isolation controls",
            ],
            "escalate_instead_of_implementing": [
                "architecture boundary change",
                "security boundary change",
                "evidence gate weakening",
                "truth-isolation change",
                "destructive migration",
            ],
            "result_contract": {
                "required": ["outcome", "summary"],
                "success_requires": [
                    "branch_name",
                    "head_sha",
                    "pull_request_number",
                    "pull_request_url",
                ],
                "automatic_merge_allowed": False,
                "automatic_deploy_allowed": False,
            },
        }
        manifest_ref = self._jobs._write_json(  # noqa: SLF001
            f"agent-jobs/{job.id}/premium-execution-manifest.json", manifest
        )
        self._record_event(
            db,
            job,
            AgentJobEventType.CLAIMED,
            {"worker_id": worker_id, "lease_id": str(lease_id), "source": "AC-002D"},
        )
        self._record_event(db, job, AgentJobEventType.STARTED, {"manifest_ref": manifest_ref})
        db.commit()
        return PremiumCodexExecutionLease(
            job_id=job.id,
            organization_id=organization_id,
            lease_id=lease_id,
            worker_id=worker_id,
            manifest_ref=manifest_ref,
        )

    def complete(
        self,
        db: Session,
        organization_id: UUID,
        job_id: UUID,
        payload: PremiumCodexExecutionComplete,
    ) -> AgentJob:
        job = self._get_job(db, organization_id, job_id)
        self._validate_authorized_job(job)
        if job.status != AgentJobStatus.RUNNING.value:
            _fail("JOB_NOT_RUNNING", "Codex implementation job is not running", 409)
        if job.execution_lease_id != payload.lease_id:
            _fail("LEASE_MISMATCH", "Premium execution lease does not match", 409)

        if payload.outcome == "succeeded":
            missing = []
            if not payload.branch_name:
                missing.append("branch_name")
            if not payload.head_sha:
                missing.append("head_sha")
            if payload.pull_request_number is None:
                missing.append("pull_request_number")
            if not payload.pull_request_url:
                missing.append("pull_request_url")
            if missing:
                _fail(
                    "SUCCESS_RESULT_INCOMPLETE",
                    "Successful Codex execution is missing: " + ", ".join(missing),
                    409,
                )

        result = payload.model_dump(mode="json")
        result.update(
            {
                "schema_version": "ac002d-premium-codex-result-v1",
                "job_id": str(job.id),
                "organization_id": str(organization_id),
                "automatic_merge_performed": False,
                "automatic_deploy_performed": False,
            }
        )
        job.result_ref = self._jobs._write_json(  # noqa: SLF001
            f"agent-jobs/{job.id}/result.json", result
        )
        job.completed_at = utc_now()
        job.heartbeat_at = job.completed_at

        if payload.outcome == "succeeded":
            job.status = AgentJobStatus.SUCCEEDED.value
            self._record_event(
                db,
                job,
                AgentJobEventType.SUCCEEDED,
                {
                    "pull_request_number": payload.pull_request_number,
                    "pull_request_url": payload.pull_request_url,
                    "head_sha": payload.head_sha,
                },
            )
        elif payload.outcome == "escalated":
            job.status = AgentJobStatus.ESCALATED.value
            job.escalation_reason = payload.escalation_reason or payload.summary
            self._record_event(
                db,
                job,
                AgentJobEventType.ESCALATED,
                {"reason": job.escalation_reason, "source": "AC-002D"},
            )
        else:
            job.status = AgentJobStatus.FAILED.value
            job.failed_at = job.completed_at
            job.error_code = "PREMIUM_CODEX_EXECUTION_FAILED"
            job.error_detail = payload.summary
            self._record_event(
                db,
                job,
                AgentJobEventType.FAILED,
                {"summary": payload.summary, "source": "AC-002D"},
            )

        db.commit()
        return job
