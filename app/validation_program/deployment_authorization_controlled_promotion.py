"""AC-002H: deployment authorization and controlled environment promotion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NoReturn
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent_jobs import AgentJob, AgentJobStatus, AgentWorkerProfile
from app.models.simulation_batch import SimulationBatch, SimulationBatchStatus
from app.schemas.deployment_authorization_controlled_promotion import (
    ControlledPromotionComplete,
    DeploymentAuthorizationRequest,
)
from app.services.agent_job_service import AgentJobService
from app.storage.base import StorageBackend

_JOB_TYPE = "CODEX_IMPLEMENTATION"
_ALLOWED_ENVIRONMENTS = {"staging", "production"}


class DeploymentAuthorizationControlledPromotionError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def _fail(code: str, message: str, status: int = 400) -> NoReturn:
    raise DeploymentAuthorizationControlledPromotionError(code, message, status)


@dataclass(frozen=True)
class DeploymentAuthorizationDecision:
    batch_id: UUID
    job_id: UUID
    decision: str
    authorization_ref: str
    environment: str
    deploy_allowed: bool


@dataclass(frozen=True)
class ControlledPromotionLease:
    batch_id: UUID
    job_id: UUID
    lease_id: UUID
    manifest_ref: str
    environment: str


@dataclass(frozen=True)
class ControlledPromotionDecision:
    batch_id: UUID
    job_id: UUID
    decision: str
    result_ref: str
    environment: str


class DeploymentAuthorizationControlledPromotionService:
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
        if job.job_type != _JOB_TYPE or job.assigned_worker != AgentWorkerProfile.CODEX_IMPLEMENTATION.value:
            _fail("CODEX_JOB_INVALID", "Job is not an approved Codex implementation job", 409)
        if job.status != AgentJobStatus.SUCCEEDED.value:
            _fail("CODEX_JOB_NOT_SUCCEEDED", "Codex implementation job is not complete", 409)
        return job

    def _batch_id(self, job: AgentJob) -> UUID:
        parts = (job.client_idempotency_key or "").split(":")
        if len(parts) != 3 or parts[0] != "ac002c" or parts[2] != "codex":
            _fail("SOURCE_BATCH_UNRESOLVED", "Codex job is not linked to an AC-002C batch", 409)
        try:
            return UUID(parts[1])
        except ValueError as exc:
            raise DeploymentAuthorizationControlledPromotionError(
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
        return batch

    def _promotion(self, organization_id: UUID, batch_id: UUID, job: AgentJob) -> dict[str, Any]:
        ref = f"agent-jobs/{job.id}/release-promotion.json"
        try:
            promotion = self._jobs._read_json(ref)  # noqa: SLF001
        except (FileNotFoundError, ValueError) as exc:
            raise DeploymentAuthorizationControlledPromotionError(
                "RELEASE_PROMOTION_MISSING", "AC-002G release promotion is missing", 409
            ) from exc
        if promotion.get("schema_version") != "ac002g-release-promotion-v1":
            _fail("RELEASE_PROMOTION_INVALID", "AC-002G release promotion schema is invalid", 409)
        if promotion.get("organization_id") != str(organization_id) or promotion.get("batch_id") != str(batch_id):
            _fail("RELEASE_PROMOTION_SCOPE_MISMATCH", "Release promotion scope mismatch", 409)
        if promotion.get("implementation_job_id") != str(job.id):
            _fail("RELEASE_PROMOTION_JOB_MISMATCH", "Release promotion job mismatch", 409)
        if promotion.get("decision") != "MERGED_RELEASE_CANDIDATE":
            _fail("RELEASE_NOT_MERGED", "AC-002G did not produce a merged release candidate", 409)
        if promotion.get("release_stage") != "MERGED_AWAITING_DEPLOYMENT_AUTHORIZATION":
            _fail("RELEASE_STAGE_INVALID", "Release candidate is not awaiting deployment authorization", 409)
        if promotion.get("deploy_allowed") is not False:
            _fail("DEPLOY_BOUNDARY_INVALID", "AC-002G must not pre-authorize deployment", 409)
        if not promotion.get("merge_commit_sha"):
            _fail("MERGE_COMMIT_MISSING", "Release promotion lacks a merge commit SHA", 409)
        return promotion

    def authorize(
        self,
        db: Session,
        organization_id: UUID,
        job_id: UUID,
        owner_user_id: UUID,
        payload: DeploymentAuthorizationRequest,
    ) -> DeploymentAuthorizationDecision:
        job = self._job(db, organization_id, job_id)
        batch_id = self._batch_id(job)
        batch = self._batch(db, organization_id, batch_id)
        promotion = self._promotion(organization_id, batch_id, job)
        if payload.environment not in _ALLOWED_ENVIRONMENTS:
            _fail("ENVIRONMENT_INVALID", "Deployment environment is not allowed", 409)
        if payload.expected_merge_commit_sha != promotion["merge_commit_sha"]:
            _fail("MERGE_COMMIT_MISMATCH", "Deployment authorization targets a stale merge commit", 409)

        decision = "APPROVED" if payload.approve else "REJECTED"
        artifact = {
            "schema_version": "ac002h-deployment-authorization-v1",
            "organization_id": str(organization_id),
            "batch_id": str(batch_id),
            "implementation_job_id": str(job.id),
            "release_promotion_ref": f"agent-jobs/{job.id}/release-promotion.json",
            "merge_commit_sha": promotion["merge_commit_sha"],
            "environment": payload.environment,
            "decision": decision,
            "owner_user_id": str(owner_user_id),
            "owner_note": payload.note,
            "deploy_allowed": payload.approve,
            "cross_environment_deploy_allowed": False,
            "automatic_deploy_performed": False,
        }
        ref = self._jobs._write_json(  # noqa: SLF001
            f"agent-jobs/{job.id}/deployment-authorization-{payload.environment}.json", artifact
        )
        if payload.approve:
            batch.status = SimulationBatchStatus.ACTIVE.value
            batch.safety_gate_reason = None
        else:
            batch.status = SimulationBatchStatus.PAUSED_SAFETY_GATE.value
            batch.safety_gate_reason = payload.note or "deployment rejected by owner"
        db.commit()
        return DeploymentAuthorizationDecision(batch_id, job.id, decision, ref, payload.environment, payload.approve)

    def start(
        self,
        db: Session,
        organization_id: UUID,
        job_id: UUID,
        environment: str,
        expected_merge_commit_sha: str,
        worker_id: str,
    ) -> ControlledPromotionLease:
        job = self._job(db, organization_id, job_id)
        batch_id = self._batch_id(job)
        self._batch(db, organization_id, batch_id)
        promotion = self._promotion(organization_id, batch_id, job)
        if expected_merge_commit_sha != promotion["merge_commit_sha"]:
            _fail("MERGE_COMMIT_MISMATCH", "Controlled promotion targets a stale merge commit", 409)
        auth_ref = f"agent-jobs/{job.id}/deployment-authorization-{environment}.json"
        try:
            authorization = self._jobs._read_json(auth_ref)  # noqa: SLF001
        except (FileNotFoundError, ValueError) as exc:
            raise DeploymentAuthorizationControlledPromotionError(
                "DEPLOYMENT_AUTHORIZATION_MISSING", "Deployment authorization is missing", 409
            ) from exc
        if authorization.get("schema_version") != "ac002h-deployment-authorization-v1":
            _fail("DEPLOYMENT_AUTHORIZATION_INVALID", "Deployment authorization schema is invalid", 409)
        if authorization.get("decision") != "APPROVED" or authorization.get("deploy_allowed") is not True:
            _fail("DEPLOYMENT_NOT_AUTHORIZED", "Owner did not authorize deployment", 409)
        if authorization.get("environment") != environment:
            _fail("ENVIRONMENT_SCOPE_MISMATCH", "Deployment authorization environment mismatch", 409)
        if authorization.get("merge_commit_sha") != expected_merge_commit_sha:
            _fail("AUTHORIZED_COMMIT_STALE", "Authorized deployment commit is stale", 409)

        lease_id = uuid4()
        manifest = {
            "schema_version": "ac002h-controlled-promotion-manifest-v1",
            "organization_id": str(organization_id),
            "batch_id": str(batch_id),
            "implementation_job_id": str(job.id),
            "deployment_authorization_ref": auth_ref,
            "lease_id": str(lease_id),
            "worker_id": worker_id,
            "environment": environment,
            "merge_commit_sha": expected_merge_commit_sha,
            "repository": "intel4ops/intel4ops-core-platform",
            "execution_rules": [
                "deploy only the authorized merge commit",
                "deploy only to the authorized environment",
                "do not promote to any other environment",
                "stop and escalate if health verification fails",
            ],
            "deploy_allowed": True,
            "cross_environment_deploy_allowed": False,
        }
        manifest_ref = self._jobs._write_json(  # noqa: SLF001
            f"agent-jobs/{job.id}/controlled-promotion-{environment}.json", manifest
        )
        return ControlledPromotionLease(batch_id, job.id, lease_id, manifest_ref, environment)

    def complete(
        self,
        db: Session,
        organization_id: UUID,
        job_id: UUID,
        payload: ControlledPromotionComplete,
    ) -> ControlledPromotionDecision:
        job = self._job(db, organization_id, job_id)
        batch_id = self._batch_id(job)
        batch = self._batch(db, organization_id, batch_id)
        promotion = self._promotion(organization_id, batch_id, job)
        manifest_ref = f"agent-jobs/{job.id}/controlled-promotion-{payload.environment}.json"
        try:
            manifest = self._jobs._read_json(manifest_ref)  # noqa: SLF001
        except (FileNotFoundError, ValueError) as exc:
            raise DeploymentAuthorizationControlledPromotionError(
                "CONTROLLED_PROMOTION_NOT_STARTED", "Controlled promotion has not been started", 409
            ) from exc
        if manifest.get("lease_id") != str(payload.lease_id):
            _fail("LEASE_MISMATCH", "Controlled promotion lease does not match", 409)
        if manifest.get("environment") != payload.environment:
            _fail("ENVIRONMENT_SCOPE_MISMATCH", "Controlled promotion environment mismatch", 409)
        if payload.deployed_commit_sha != promotion["merge_commit_sha"]:
            _fail("DEPLOYED_COMMIT_MISMATCH", "Deployed commit does not match the authorized merge commit", 409)
        if payload.outcome == "deployed" and not payload.deployment_reference:
            _fail("DEPLOYMENT_REFERENCE_REQUIRED", "Successful deployment requires a deployment reference", 409)

        decision = "DEPLOYED" if payload.outcome == "deployed" else "DEPLOYMENT_BLOCKED"
        if payload.outcome == "deployed":
            batch.status = SimulationBatchStatus.COMPLETE.value
            batch.safety_gate_reason = None
        else:
            batch.status = SimulationBatchStatus.PAUSED_SAFETY_GATE.value
            batch.safety_gate_reason = payload.escalation_reason or payload.summary

        result = {
            "schema_version": "ac002h-controlled-promotion-result-v1",
            "organization_id": str(organization_id),
            "batch_id": str(batch_id),
            "implementation_job_id": str(job.id),
            "decision": decision,
            "outcome": payload.outcome,
            "environment": payload.environment,
            "deployed_commit_sha": payload.deployed_commit_sha,
            "deployment_reference": payload.deployment_reference,
            "summary": payload.summary,
            "escalation_reason": payload.escalation_reason,
            "cross_environment_promotion_performed": False,
            "next_action": (
                "require a new owner authorization for any different environment"
                if payload.outcome == "deployed"
                else "return to safety review before retrying deployment"
            ),
        }
        result_ref = self._jobs._write_json(  # noqa: SLF001
            f"agent-jobs/{job.id}/controlled-promotion-result-{payload.environment}.json", result
        )
        db.commit()
        return ControlledPromotionDecision(batch_id, job.id, decision, result_ref, payload.environment)
