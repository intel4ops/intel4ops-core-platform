from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NoReturn
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent_jobs import AgentJob, AgentJobStatus, AgentWorkerProfile
from app.models.simulation_batch import (
    SimulationBatch,
    SimulationBatchItem,
    SimulationBatchItemState,
    SimulationBatchStatus,
)
from app.schemas.verified_release_authorization import VerifiedReleaseAuthorizationRequest
from app.services.agent_job_service import AgentJobService
from app.storage.base import StorageBackend

_JOB_TYPE = "CODEX_IMPLEMENTATION"


class VerifiedReleaseAuthorizationError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def _fail(code: str, message: str, status: int = 400) -> NoReturn:
    raise VerifiedReleaseAuthorizationError(code, message, status)


@dataclass(frozen=True)
class ReleaseAuthorizationDecision:
    batch_id: UUID
    job_id: UUID
    decision: str
    authorization_ref: str
    merge_allowed: bool
    deploy_allowed: bool


class VerifiedReleaseAuthorizationService:
    def __init__(self, storage: StorageBackend) -> None:
        self._jobs = AgentJobService(storage=storage)

    def _job(self, db: Session, organization_id: UUID, job_id: UUID) -> AgentJob:
        job = db.scalar(
            select(AgentJob).where(
                AgentJob.id == job_id,
                AgentJob.organization_id == organization_id,
            )
        )
        if job is None:
            _fail("CODEX_JOB_NOT_FOUND", "Codex implementation job not found", 404)
        if job.job_type != _JOB_TYPE:
            _fail("JOB_TYPE_INVALID", "Job is not a Codex implementation job", 409)
        if job.assigned_worker != AgentWorkerProfile.CODEX_IMPLEMENTATION.value:
            _fail("WORKER_PROFILE_INVALID", "Job is not assigned to the Codex profile", 409)
        if job.status != AgentJobStatus.SUCCEEDED.value or not job.result_ref:
            _fail("CODEX_JOB_NOT_SUCCEEDED", "Codex implementation job is not complete", 409)
        return job

    def _batch_id(self, job: AgentJob) -> UUID:
        parts = (job.client_idempotency_key or "").split(":")
        if len(parts) != 3 or parts[0] != "ac002c" or parts[2] != "codex":
            _fail("SOURCE_BATCH_UNRESOLVED", "Codex job is not linked to an AC-002C batch", 409)
        try:
            return UUID(parts[1])
        except ValueError as exc:
            raise VerifiedReleaseAuthorizationError(
                "SOURCE_BATCH_UNRESOLVED", "Codex job source batch identifier is invalid", 409
            ) from exc

    def _batch(
        self, db: Session, organization_id: UUID, batch_id: UUID
    ) -> tuple[SimulationBatch, list[SimulationBatchItem]]:
        batch = db.scalar(
            select(SimulationBatch).where(
                SimulationBatch.id == batch_id,
                SimulationBatch.organization_id == organization_id,
            )
        )
        if batch is None:
            _fail("BATCH_NOT_FOUND", "Simulation batch not found", 404)
        items = list(
            db.scalars(
                select(SimulationBatchItem).where(
                    SimulationBatchItem.batch_id == batch_id,
                    SimulationBatchItem.organization_id == organization_id,
                )
            )
        )
        if batch.status != SimulationBatchStatus.OWNER_REVIEW_REQUIRED.value:
            _fail("OWNER_REVIEW_NOT_PENDING", "Batch is not awaiting release authorization", 409)
        if not items or any(item.state != SimulationBatchItemState.GRADUATED.value for item in items):
            _fail("BATCH_NOT_VERIFIED", "Batch items are not fully graduated", 409)
        return batch, items

    def _candidate(self, job: AgentJob) -> dict[str, Any]:
        assert job.result_ref is not None
        result = self._jobs._read_json(job.result_ref)  # noqa: SLF001
        required = ("head_sha", "pull_request_number", "pull_request_url", "branch_name")
        if any(not result.get(field) for field in required):
            _fail("CODEX_RESULT_INCOMPLETE", "Codex result lacks candidate PR metadata", 409)
        if result.get("automatic_merge_performed") is not False:
            _fail("CANDIDATE_ALREADY_MERGED", "Candidate was already automatically merged", 409)
        if result.get("automatic_deploy_performed") is not False:
            _fail("CANDIDATE_ALREADY_DEPLOYED", "Candidate was already automatically deployed", 409)
        return result

    def _verification(self, organization_id: UUID, batch_id: UUID, job: AgentJob) -> dict[str, Any]:
        ref = f"agent-jobs/{job.id}/verification-retest-result.json"
        try:
            result = self._jobs._read_json(ref)  # noqa: SLF001
        except (FileNotFoundError, ValueError) as exc:
            raise VerifiedReleaseAuthorizationError(
                "VERIFICATION_RESULT_MISSING", "AC-002E verification result is missing", 409
            ) from exc
        if result.get("schema_version") != "ac002e-verification-result-v1":
            _fail("VERIFICATION_SCHEMA_INVALID", "Verification result schema is invalid", 409)
        if result.get("organization_id") != str(organization_id) or result.get("batch_id") != str(batch_id):
            _fail("VERIFICATION_SCOPE_MISMATCH", "Verification result scope does not match the batch", 409)
        if result.get("implementation_job_id") != str(job.id):
            _fail("VERIFICATION_JOB_MISMATCH", "Verification result does not match the Codex job", 409)
        if result.get("decision") != "VERIFIED_IMPROVEMENT" or result.get("owner_review_required") is not True:
            _fail("VERIFICATION_NOT_APPROVABLE", "Only a verified improvement may be authorized", 409)
        if result.get("automatic_merge_performed") is not False or result.get("automatic_deploy_performed") is not False:
            _fail("VERIFICATION_BOUNDARY_BROKEN", "Verification boundary was already crossed", 409)
        return result

    def authorize(
        self,
        db: Session,
        organization_id: UUID,
        job_id: UUID,
        actor_user_id: UUID,
        payload: VerifiedReleaseAuthorizationRequest,
    ) -> ReleaseAuthorizationDecision:
        job = self._job(db, organization_id, job_id)
        batch_id = self._batch_id(job)
        batch, _items = self._batch(db, organization_id, batch_id)
        candidate = self._candidate(job)
        verification = self._verification(organization_id, batch_id, job)

        if payload.expected_head_sha != candidate["head_sha"]:
            _fail("CANDIDATE_SHA_MISMATCH", "Owner approval does not match the verified candidate SHA", 409)
        if payload.pull_request_number != candidate["pull_request_number"]:
            _fail("CANDIDATE_PR_MISMATCH", "Owner approval does not match the verified pull request", 409)
        if verification.get("candidate_head_sha") != candidate["head_sha"]:
            _fail("VERIFIED_CANDIDATE_MISMATCH", "Verification result is stale for this candidate", 409)
        if verification.get("pull_request_number") != candidate["pull_request_number"]:
            _fail("VERIFIED_PR_MISMATCH", "Verification result is stale for this pull request", 409)

        authorization_ref = f"agent-jobs/{job.id}/release-authorization.json"
        decision = "APPROVED" if payload.approve else "REJECTED"
        merge_allowed = payload.approve
        try:
            existing = self._jobs._read_json(authorization_ref)  # noqa: SLF001
        except (FileNotFoundError, ValueError):
            existing = None
        if existing is not None:
            same = (
                existing.get("decision") == decision
                and existing.get("candidate_head_sha") == candidate["head_sha"]
                and existing.get("pull_request_number") == candidate["pull_request_number"]
            )
            if not same:
                _fail("AUTHORIZATION_ALREADY_DECIDED", "Release authorization already recorded", 409)
            return ReleaseAuthorizationDecision(
                batch_id=batch_id,
                job_id=job.id,
                decision=decision,
                authorization_ref=authorization_ref,
                merge_allowed=bool(existing.get("merge_allowed")),
                deploy_allowed=False,
            )

        artifact = {
            "schema_version": "ac002f-release-authorization-v1",
            "organization_id": str(organization_id),
            "batch_id": str(batch_id),
            "implementation_job_id": str(job.id),
            "verification_ref": f"agent-jobs/{job.id}/verification-retest-result.json",
            "verified_decision": "VERIFIED_IMPROVEMENT",
            "candidate_head_sha": candidate["head_sha"],
            "pull_request_number": candidate["pull_request_number"],
            "pull_request_url": candidate["pull_request_url"],
            "branch_name": candidate["branch_name"],
            "decision": decision,
            "owner_user_id": str(actor_user_id),
            "owner_note": payload.note,
            "merge_allowed": merge_allowed,
            "deploy_allowed": False,
            "automatic_merge_performed": False,
            "automatic_deploy_performed": False,
            "next_action": (
                "merge exact verified candidate through governed GitHub executor"
                if payload.approve
                else "close candidate without merge and return batch to safety review"
            ),
        }
        self._jobs._write_json(authorization_ref, artifact)  # noqa: SLF001

        if payload.approve:
            batch.status = SimulationBatchStatus.COMPLETE.value
            batch.safety_gate_reason = None
        else:
            batch.status = SimulationBatchStatus.PAUSED_SAFETY_GATE.value
            batch.safety_gate_reason = "AC-002F owner rejected verified release candidate"
        db.commit()
        return ReleaseAuthorizationDecision(
            batch_id=batch_id,
            job_id=job.id,
            decision=decision,
            authorization_ref=authorization_ref,
            merge_allowed=merge_allowed,
            deploy_allowed=False,
        )
