"""AC-002E: autonomous verification and retest gate for Codex-produced changes.

This module does not execute candidate code inside the production process and
never merges or deploys a pull request. It creates a sealed retest manifest for
an exact candidate SHA/PR, then evaluates scored retest evidence for the same
simulation set against the frozen baseline captured by the SimulationBatch.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NoReturn
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent_jobs import AgentJob, AgentJobStatus, AgentWorkerProfile
from app.models.simulation_batch import (
    SimulationBatch,
    SimulationBatchItem,
    SimulationBatchItemState,
    SimulationBatchStatus,
)
from app.schemas.autonomous_verification_retest import VerificationRetestComplete
from app.services.agent_job_service import AgentJobService
from app.storage.base import StorageBackend

_JOB_TYPE = "CODEX_IMPLEMENTATION"


class AutonomousVerificationRetestError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def _fail(code: str, message: str, status: int = 400) -> NoReturn:
    raise AutonomousVerificationRetestError(code, message, status)


@dataclass(frozen=True)
class VerificationRetestLease:
    batch_id: UUID
    job_id: UUID
    lease_id: UUID
    worker_id: str
    manifest_ref: str


@dataclass(frozen=True)
class VerificationRetestDecision:
    batch_id: UUID
    job_id: UUID
    decision: str
    verification_ref: str
    owner_review_required: bool


class AutonomousVerificationRetestService:
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
        if job.status != AgentJobStatus.SUCCEEDED.value:
            _fail("CODEX_JOB_NOT_SUCCEEDED", "Codex implementation job has not succeeded", 409)
        if not job.result_ref:
            _fail("CODEX_RESULT_MISSING", "Codex implementation result is missing", 409)
        return job

    def _batch_id_from_job(self, job: AgentJob) -> UUID:
        key = job.client_idempotency_key or ""
        parts = key.split(":")
        if len(parts) != 3 or parts[0] != "ac002c" or parts[2] != "codex":
            _fail("SOURCE_BATCH_UNRESOLVED", "Codex job is not linked to an AC-002C batch", 409)
        try:
            return UUID(parts[1])
        except ValueError as exc:
            raise AutonomousVerificationRetestError(
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
                select(SimulationBatchItem)
                .where(
                    SimulationBatchItem.batch_id == batch_id,
                    SimulationBatchItem.organization_id == organization_id,
                )
                .order_by(SimulationBatchItem.created_at, SimulationBatchItem.id)
            )
        )
        if not items:
            _fail("EMPTY_BATCH", "Simulation batch contains no items", 409)
        return batch, items

    def _candidate(self, job: AgentJob) -> dict[str, Any]:
        result = self._jobs._read_json(job.result_ref)  # noqa: SLF001
        required = ("head_sha", "pull_request_number", "pull_request_url", "branch_name")
        if any(not result.get(field) for field in required):
            _fail("CODEX_RESULT_INCOMPLETE", "Codex result lacks candidate PR metadata", 409)
        if result.get("automatic_merge_performed") is not False:
            _fail("CANDIDATE_ALREADY_MERGED", "Verification requires an unmerged candidate", 409)
        if result.get("automatic_deploy_performed") is not False:
            _fail("CANDIDATE_ALREADY_DEPLOYED", "Verification requires an undeployed candidate", 409)
        return result

    def start(
        self,
        db: Session,
        organization_id: UUID,
        job_id: UUID,
        worker_id: str,
    ) -> VerificationRetestLease:
        job = self._job(db, organization_id, job_id)
        batch_id = self._batch_id_from_job(job)
        batch, items = self._batch(db, organization_id, batch_id)
        if batch.status != SimulationBatchStatus.ACTIVE.value:
            _fail("BATCH_NOT_ACTIVE", "Simulation batch is not active for retest", 409)
        invalid = [item.simulation_id for item in items if item.state != SimulationBatchItemState.REMEDIATION_REVIEW.value]
        if invalid:
            _fail("ITEMS_NOT_READY_FOR_RETEST", "Not all batch items are ready for retest", 409)

        candidate = self._candidate(job)
        lease_id = uuid4()
        baseline = [
            {
                "simulation_id": item.simulation_id,
                "true_positive_count": item.true_positive_count or 0,
                "false_positive_count": item.false_positive_count or 0,
                "false_negative_count": item.false_negative_count or 0,
            }
            for item in items
        ]
        manifest = {
            "schema_version": "ac002e-verification-retest-v1",
            "organization_id": str(organization_id),
            "batch_id": str(batch_id),
            "implementation_job_id": str(job.id),
            "lease_id": str(lease_id),
            "worker_id": worker_id,
            "candidate": {
                "head_sha": candidate["head_sha"],
                "pull_request_number": candidate["pull_request_number"],
                "pull_request_url": candidate["pull_request_url"],
                "branch_name": candidate["branch_name"],
            },
            "simulation_ids": [item.simulation_id for item in items],
            "baseline": baseline,
            "execution_rules": [
                "run the exact same sealed simulations against the exact candidate SHA",
                "candidate production execution must not read hidden-truth files",
                "score truth only after the candidate run is frozen/terminal",
                "return one scored result for every listed simulation and no others",
            ],
            "decision_policy": {
                "verified_improvement": "total false negatives decrease, false positives do not increase, and true positives do not decrease",
                "regression": "any false-positive increase, false-negative increase, or true-positive decrease",
                "no_improvement": "all other scored outcomes",
            },
            "automatic_merge_allowed": False,
            "automatic_deploy_allowed": False,
        }
        manifest_ref = self._jobs._write_json(  # noqa: SLF001
            f"agent-jobs/{job.id}/verification-retest-manifest.json", manifest
        )
        for item in items:
            item.state = SimulationBatchItemState.RETEST.value
        db.commit()
        return VerificationRetestLease(batch_id, job.id, lease_id, worker_id, manifest_ref)

    def complete(
        self,
        db: Session,
        organization_id: UUID,
        job_id: UUID,
        payload: VerificationRetestComplete,
    ) -> VerificationRetestDecision:
        job = self._job(db, organization_id, job_id)
        batch_id = self._batch_id_from_job(job)
        batch, items = self._batch(db, organization_id, batch_id)
        candidate = self._candidate(job)
        manifest_ref = f"agent-jobs/{job.id}/verification-retest-manifest.json"
        try:
            manifest = self._jobs._read_json(manifest_ref)  # noqa: SLF001
        except (FileNotFoundError, ValueError) as exc:
            raise AutonomousVerificationRetestError(
                "VERIFICATION_NOT_STARTED", "Verification retest has not been started", 409
            ) from exc
        if manifest.get("lease_id") != str(payload.lease_id):
            _fail("LEASE_MISMATCH", "Verification retest lease does not match", 409)
        if payload.candidate_head_sha != candidate["head_sha"]:
            _fail("CANDIDATE_SHA_MISMATCH", "Retest candidate SHA does not match Codex result", 409)
        if payload.pull_request_number != candidate["pull_request_number"]:
            _fail("CANDIDATE_PR_MISMATCH", "Retest pull request does not match Codex result", 409)
        if any(item.state != SimulationBatchItemState.RETEST.value for item in items):
            _fail("ITEMS_NOT_IN_RETEST", "Batch items are not all in retest state", 409)

        decision = "ESCALATED"
        owner_review_required = True
        if payload.outcome == "scored":
            expected_ids = {item.simulation_id for item in items}
            actual_ids = {result.simulation_id for result in payload.results}
            if len(payload.results) != len(actual_ids) or actual_ids != expected_ids:
                _fail("RETEST_RESULT_SET_INVALID", "Retest results must match the batch simulation set exactly", 409)
            by_id = {result.simulation_id: result for result in payload.results}
            before_tp = sum(item.true_positive_count or 0 for item in items)
            before_fp = sum(item.false_positive_count or 0 for item in items)
            before_fn = sum(item.false_negative_count or 0 for item in items)
            after_tp = sum(by_id[item.simulation_id].true_positive_count for item in items)
            after_fp = sum(by_id[item.simulation_id].false_positive_count for item in items)
            after_fn = sum(by_id[item.simulation_id].false_negative_count for item in items)

            regressed = after_fp > before_fp or after_fn > before_fn or after_tp < before_tp
            improved = after_fn < before_fn and after_fp <= before_fp and after_tp >= before_tp
            if improved and not regressed:
                decision = "VERIFIED_IMPROVEMENT"
                batch.status = SimulationBatchStatus.OWNER_REVIEW_REQUIRED.value
                for item in items:
                    item.state = SimulationBatchItemState.GRADUATED.value
            else:
                decision = "REGRESSION" if regressed else "NO_IMPROVEMENT"
                batch.status = SimulationBatchStatus.PAUSED_SAFETY_GATE.value
                batch.safety_gate_reason = f"AC-002E {decision.lower().replace('_', ' ')}"
                owner_review_required = False
                for item in items:
                    item.state = SimulationBatchItemState.REGRESSION.value
        else:
            batch.status = SimulationBatchStatus.PAUSED_SAFETY_GATE.value
            batch.safety_gate_reason = payload.escalation_reason or payload.summary
            owner_review_required = False
            for item in items:
                item.state = SimulationBatchItemState.REGRESSION.value

        verification = {
            "schema_version": "ac002e-verification-result-v1",
            "organization_id": str(organization_id),
            "batch_id": str(batch_id),
            "implementation_job_id": str(job.id),
            "candidate_head_sha": payload.candidate_head_sha,
            "pull_request_number": payload.pull_request_number,
            "outcome": payload.outcome,
            "decision": decision,
            "summary": payload.summary,
            "escalation_reason": payload.escalation_reason,
            "results": [result.model_dump(mode="json") for result in payload.results],
            "owner_review_required": owner_review_required,
            "automatic_merge_performed": False,
            "automatic_deploy_performed": False,
        }
        verification_ref = self._jobs._write_json(  # noqa: SLF001
            f"agent-jobs/{job.id}/verification-retest-result.json", verification
        )
        db.commit()
        return VerificationRetestDecision(
            batch_id=batch_id,
            job_id=job.id,
            decision=decision,
            verification_ref=verification_ref,
            owner_review_required=owner_review_required,
        )
