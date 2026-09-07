"""AC-002G: governed merge execution and release-candidate promotion.

This service does not call GitHub and never deploys. It consumes the sealed
AC-002F approval, emits an exact-SHA merge manifest for an external governed
executor, then records the executor result as a release-candidate promotion.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NoReturn
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent_jobs import AgentJob, AgentJobStatus, AgentWorkerProfile
from app.models.simulation_batch import SimulationBatch, SimulationBatchStatus
from app.schemas.governed_merge_release_promotion import GovernedMergeComplete
from app.services.agent_job_service import AgentJobService
from app.storage.base import StorageBackend

_JOB_TYPE = "CODEX_IMPLEMENTATION"
_TARGET_BRANCH = "main"


class GovernedMergeReleasePromotionError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def _fail(code: str, message: str, status: int = 400) -> NoReturn:
    raise GovernedMergeReleasePromotionError(code, message, status)


@dataclass(frozen=True)
class GovernedMergeLease:
    batch_id: UUID
    job_id: UUID
    lease_id: UUID
    worker_id: str
    manifest_ref: str


@dataclass(frozen=True)
class GovernedMergeDecision:
    batch_id: UUID
    job_id: UUID
    decision: str
    promotion_ref: str
    deploy_allowed: bool


class GovernedMergeReleasePromotionService:
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
            raise GovernedMergeReleasePromotionError(
                "SOURCE_BATCH_UNRESOLVED", "Codex job source batch identifier is invalid", 409
            ) from exc

    def _batch(self, db: Session, organization_id: UUID, batch_id: UUID) -> SimulationBatch:
        batch = db.scalar(
            select(SimulationBatch).where(
                SimulationBatch.id == batch_id,
                SimulationBatch.organization_id == organization_id,
            )
        )
        if batch is None:
            _fail("BATCH_NOT_FOUND", "Simulation batch not found", 404)
        if batch.status != SimulationBatchStatus.COMPLETE.value:
            _fail("RELEASE_NOT_AUTHORIZED", "Batch is not in the AC-002F approved state", 409)
        return batch

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

    def _authorization(
        self, organization_id: UUID, batch_id: UUID, job: AgentJob, candidate: dict[str, Any]
    ) -> dict[str, Any]:
        ref = f"agent-jobs/{job.id}/release-authorization.json"
        try:
            artifact = self._jobs._read_json(ref)  # noqa: SLF001
        except (FileNotFoundError, ValueError) as exc:
            raise GovernedMergeReleasePromotionError(
                "RELEASE_AUTHORIZATION_MISSING", "AC-002F release authorization is missing", 409
            ) from exc
        if artifact.get("schema_version") != "ac002f-release-authorization-v1":
            _fail("RELEASE_AUTHORIZATION_INVALID", "Release authorization schema is invalid", 409)
        if artifact.get("organization_id") != str(organization_id) or artifact.get(
            "batch_id"
        ) != str(batch_id):
            _fail(
                "RELEASE_AUTHORIZATION_SCOPE_MISMATCH", "Release authorization scope mismatch", 409
            )
        if artifact.get("implementation_job_id") != str(job.id):
            _fail("RELEASE_AUTHORIZATION_JOB_MISMATCH", "Release authorization job mismatch", 409)
        if artifact.get("decision") != "APPROVED" or artifact.get("merge_allowed") is not True:
            _fail("MERGE_NOT_AUTHORIZED", "AC-002F did not authorize merge", 409)
        if artifact.get("deploy_allowed") is not False:
            _fail("DEPLOY_BOUNDARY_INVALID", "AC-002F must not authorize deployment", 409)
        if artifact.get("candidate_head_sha") != candidate["head_sha"]:
            _fail("AUTHORIZED_CANDIDATE_STALE", "Authorized candidate SHA is stale", 409)
        if artifact.get("pull_request_number") != candidate["pull_request_number"]:
            _fail("AUTHORIZED_PR_STALE", "Authorized pull request is stale", 409)
        return artifact

    def start(
        self,
        db: Session,
        organization_id: UUID,
        job_id: UUID,
        worker_id: str,
    ) -> GovernedMergeLease:
        job = self._job(db, organization_id, job_id)
        batch_id = self._batch_id(job)
        self._batch(db, organization_id, batch_id)
        candidate = self._candidate(job)
        authorization = self._authorization(organization_id, batch_id, job, candidate)

        lease_id = uuid4()
        manifest = {
            "schema_version": "ac002g-governed-merge-manifest-v1",
            "organization_id": str(organization_id),
            "batch_id": str(batch_id),
            "implementation_job_id": str(job.id),
            "release_authorization_ref": f"agent-jobs/{job.id}/release-authorization.json",
            "lease_id": str(lease_id),
            "worker_id": worker_id,
            "repository": "intel4ops/intel4ops-core-platform",
            "pull_request_number": candidate["pull_request_number"],
            "pull_request_url": candidate["pull_request_url"],
            "expected_head_sha": candidate["head_sha"],
            "source_branch": candidate["branch_name"],
            "target_branch": _TARGET_BRANCH,
            "merge_method": "merge",
            "owner_user_id": authorization.get("owner_user_id"),
            "owner_note": authorization.get("owner_note"),
            "execution_rules": [
                "merge only the authorized pull request",
                "reject execution if the pull-request head no longer equals expected_head_sha",
                "write only through the governed GitHub merge operation",
                "do not deploy or invoke any deployment workflow",
            ],
            "merge_allowed": True,
            "deploy_allowed": False,
            "automatic_deploy_allowed": False,
        }
        manifest_ref = self._jobs._write_json(  # noqa: SLF001
            f"agent-jobs/{job.id}/governed-merge-manifest.json", manifest
        )
        return GovernedMergeLease(batch_id, job.id, lease_id, worker_id, manifest_ref)

    def complete(
        self,
        db: Session,
        organization_id: UUID,
        job_id: UUID,
        payload: GovernedMergeComplete,
    ) -> GovernedMergeDecision:
        job = self._job(db, organization_id, job_id)
        batch_id = self._batch_id(job)
        batch = self._batch(db, organization_id, batch_id)
        candidate = self._candidate(job)
        self._authorization(organization_id, batch_id, job, candidate)

        manifest_ref = f"agent-jobs/{job.id}/governed-merge-manifest.json"
        try:
            manifest = self._jobs._read_json(manifest_ref)  # noqa: SLF001
        except (FileNotFoundError, ValueError) as exc:
            raise GovernedMergeReleasePromotionError(
                "GOVERNED_MERGE_NOT_STARTED", "Governed merge has not been started", 409
            ) from exc
        if manifest.get("lease_id") != str(payload.lease_id):
            _fail("LEASE_MISMATCH", "Governed merge lease does not match", 409)
        if payload.candidate_head_sha != candidate["head_sha"]:
            _fail(
                "CANDIDATE_SHA_MISMATCH", "Merged candidate SHA does not match authorization", 409
            )
        if payload.pull_request_number != candidate["pull_request_number"]:
            _fail("CANDIDATE_PR_MISMATCH", "Merged pull request does not match authorization", 409)
        if payload.target_branch != _TARGET_BRANCH:
            _fail("TARGET_BRANCH_INVALID", "Governed merge target must be main", 409)
        if payload.outcome == "merged" and not payload.merge_commit_sha:
            _fail("MERGE_COMMIT_REQUIRED", "Successful merge must report a merge commit SHA", 409)

        decision = "MERGED_RELEASE_CANDIDATE" if payload.outcome == "merged" else "MERGE_BLOCKED"
        if payload.outcome != "merged":
            batch.status = SimulationBatchStatus.PAUSED_SAFETY_GATE.value
            batch.safety_gate_reason = payload.escalation_reason or payload.summary

        promotion = {
            "schema_version": "ac002g-release-promotion-v1",
            "organization_id": str(organization_id),
            "batch_id": str(batch_id),
            "implementation_job_id": str(job.id),
            "governed_merge_manifest_ref": manifest_ref,
            "release_authorization_ref": f"agent-jobs/{job.id}/release-authorization.json",
            "decision": decision,
            "outcome": payload.outcome,
            "candidate_head_sha": payload.candidate_head_sha,
            "pull_request_number": payload.pull_request_number,
            "target_branch": payload.target_branch,
            "merge_commit_sha": payload.merge_commit_sha,
            "summary": payload.summary,
            "escalation_reason": payload.escalation_reason,
            "release_stage": (
                "MERGED_AWAITING_DEPLOYMENT_AUTHORIZATION"
                if payload.outcome == "merged"
                else "MERGE_BLOCKED"
            ),
            "deploy_allowed": False,
            "automatic_deploy_performed": False,
            "next_action": (
                "require separate deployment authorization"
                if payload.outcome == "merged"
                else "return to safety review before any further release action"
            ),
        }
        promotion_ref = self._jobs._write_json(  # noqa: SLF001
            f"agent-jobs/{job.id}/release-promotion.json", promotion
        )
        db.commit()
        return GovernedMergeDecision(
            batch_id=batch_id,
            job_id=job.id,
            decision=decision,
            promotion_ref=promotion_ref,
            deploy_allowed=False,
        )
