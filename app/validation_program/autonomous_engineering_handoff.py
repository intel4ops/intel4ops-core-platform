"""AC-002B: governed handoff from simulation learning to bounded engineering.

This service deliberately stops at the genuine owner-approval gate. It prepares
an implementation-ready, batch-scoped artifact for Codex, but it does not
create, dispatch, approve, merge, or deploy an implementation job.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent_jobs import AgentJob, AgentJobStatus, AgentWorkerProfile
from app.models.entities import utc_now
from app.models.simulation_batch import (
    SimulationBatch,
    SimulationBatchItem,
    SimulationBatchItemState,
    SimulationBatchStatus,
)
from app.services.agent_job_service import AgentJobService
from app.storage.base import StorageBackend

_ACCEPTED_CLASSIFICATION_STATUSES = frozenset(
    {AgentJobStatus.SUCCEEDED.value, AgentJobStatus.ESCALATED.value}
)


class AutonomousEngineeringHandoffError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class EngineeringHandoffResult:
    decision_package_ref: str
    engineering_handoff_ref: str
    owner_approval_required: bool = True
    status: str = SimulationBatchStatus.OWNER_REVIEW_REQUIRED.value


class AutonomousEngineeringHandoffService:
    """Prepare a batch-bounded Codex handoff without crossing owner approval."""

    def __init__(self, storage: StorageBackend) -> None:
        self._agent_jobs = AgentJobService(storage=storage)

    def prepare(
        self, db: Session, organization_id: UUID, batch_id: UUID
    ) -> EngineeringHandoffResult:
        batch = db.scalar(
            select(SimulationBatch).where(
                SimulationBatch.id == batch_id,
                SimulationBatch.organization_id == organization_id,
            )
        )
        if batch is None:
            raise AutonomousEngineeringHandoffError(
                "BATCH_NOT_FOUND", "Simulation batch not found", 404
            )

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
        simulation_ids = {item.simulation_id for item in items}
        if not simulation_ids:
            raise AutonomousEngineeringHandoffError(
                "EMPTY_BATCH", "Simulation batch contains no items", 409
            )

        # Scope by organization *and* by this batch's immutable simulation set.
        # The older controller-level DecisionPackage builder only scoped by org;
        # that is not sufficiently tight for an implementation handoff.
        jobs = list(
            db.scalars(
                select(AgentJob)
                .where(
                    AgentJob.organization_id == organization_id,
                    AgentJob.job_type == "MISS_CLASSIFICATION",
                    AgentJob.simulation_id.in_(simulation_ids),
                )
                .order_by(AgentJob.created_at, AgentJob.id)
            )
        )
        if not jobs:
            raise AutonomousEngineeringHandoffError(
                "NO_CLASSIFICATION_JOBS",
                "No miss-classification jobs exist for this simulation batch",
                409,
            )

        incomplete = [job for job in jobs if job.status not in _ACCEPTED_CLASSIFICATION_STATUSES]
        if incomplete:
            raise AutonomousEngineeringHandoffError(
                "CLASSIFICATION_INCOMPLETE",
                "All batch miss-classification jobs must be succeeded or escalated before handoff",
                409,
            )

        clusters: dict[str, dict[str, object]] = defaultdict(
            lambda: {"job_ids": [], "simulations": set(), "recommended_actions": []}
        )
        for job in jobs:
            if job.result_ref is None:
                raise AutonomousEngineeringHandoffError(
                    "CLASSIFICATION_RESULT_MISSING",
                    f"Classification job {job.id} is terminal but has no result artifact",
                    409,
                )
            result = self._agent_jobs._read_json(job.result_ref)  # noqa: SLF001
            gap_class = str(result.get("primary_gap_class") or "UNSPECIFIED")
            cluster = clusters[gap_class]
            job_ids = cluster["job_ids"]
            simulations = cluster["simulations"]
            recommended_actions = cluster["recommended_actions"]
            assert isinstance(job_ids, list)
            assert isinstance(simulations, set)
            assert isinstance(recommended_actions, list)
            job_ids.append(str(job.id))
            if job.simulation_id:
                simulations.add(job.simulation_id)
            action = result.get("recommended_action")
            if action and action not in recommended_actions:
                recommended_actions.append(str(action))

        generated_at = utc_now().isoformat()
        gap_clusters = [
            {
                "gap_class": gap_class,
                "job_ids": cluster["job_ids"],
                "simulations_affected": sorted(cluster["simulations"]),
                "job_count": len(cluster["job_ids"]),
                "recommended_actions": cluster["recommended_actions"],
            }
            for gap_class, cluster in sorted(clusters.items())
        ]
        decision_package = {
            "schema_version": "ac002b-decision-package-v1",
            "batch_id": str(batch_id),
            "organization_id": str(organization_id),
            "generated_at": generated_at,
            "items": [
                {
                    "simulation_id": item.simulation_id,
                    "state": item.state,
                    "analysis_case_id": str(item.analysis_case_id)
                    if item.analysis_case_id
                    else None,
                    "run_id": str(item.run_id) if item.run_id else None,
                    "true_positive_count": item.true_positive_count,
                    "false_positive_count": item.false_positive_count,
                    "false_negative_count": item.false_negative_count,
                    "precision": item.precision,
                    "recall": item.recall,
                }
                for item in items
            ],
            "gap_clusters": gap_clusters,
            "recommendation": "OWNER_REVIEW_REQUIRED",
        }
        decision_ref = self._agent_jobs._write_json(  # noqa: SLF001
            f"simulation-batches/{batch_id}/decision-package-ac002b.json",
            decision_package,
        )

        handoff = {
            "schema_version": "ac002b-engineering-handoff-v1",
            "batch_id": str(batch_id),
            "organization_id": str(organization_id),
            "generated_at": generated_at,
            "decision_package_ref": decision_ref,
            "target_worker_profile": AgentWorkerProfile.CODEX_IMPLEMENTATION.value,
            "handoff_state": "OWNER_APPROVAL_REQUIRED",
            "dispatch_allowed": False,
            "implementation_boundary": {
                "allowed": [
                    "inspect repository implementation relevant to approved gap clusters",
                    "prepare a bounded code change on a feature branch",
                    "add or update tests for the bounded change",
                    "run Ruff, mypy, Pytest, and Alembic checks",
                    "prepare a pull request for review",
                ],
                "prohibited_before_owner_approval": [
                    "dispatch an implementation worker",
                    "write remediation code",
                    "merge a pull request",
                    "deploy or modify production infrastructure",
                    "weaken evidence, tenant, authentication, or truth-isolation gates",
                ],
                "truth_isolation": (
                    "Implementation work may use this summarized validation decision package, "
                    "but must not read hidden-truth package files or introduce validation-plane "
                    "dependencies into production execution."
                ),
            },
            "work_items": gap_clusters,
            "owner_gate": {
                "required": True,
                "decision": None,
                "next_action_if_approved": (
                    "Create a bounded CODEX_IMPLEMENTATION work item from this artifact."
                ),
                "next_action_if_rejected": "Close the handoff without implementation.",
            },
        }
        handoff_ref = self._agent_jobs._write_json(  # noqa: SLF001
            f"simulation-batches/{batch_id}/engineering-handoff.json",
            handoff,
        )

        batch.decision_package_ref = decision_ref
        batch.status = SimulationBatchStatus.OWNER_REVIEW_REQUIRED.value
        for item in items:
            if item.state == SimulationBatchItemState.MISS_CLASSIFICATION.value:
                item.state = SimulationBatchItemState.GAP_CLUSTERING.value
        db.commit()

        return EngineeringHandoffResult(
            decision_package_ref=decision_ref,
            engineering_handoff_ref=handoff_ref,
        )
