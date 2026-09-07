"""AGENTIC-CONTROL-001 Phase L/M: cost/performance telemetry and the
Learning Transfer Rate KPI.

Per-job telemetry is already captured directly on the `AgentJob` row
(worker, model, execution_time_ms, input/output/reasoning tokens,
estimated/actual cost) at submission time -- see
`app.services.agent_job_service.AgentJobService.submit_result`. This
module only aggregates what is already persisted; it introduces no new
capture mechanism.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent_jobs import AgentJob, AgentJobStatus, AgentWorkerProfile
from app.storage.base import StorageBackend

_LOCAL_PROFILES = frozenset(
    {
        AgentWorkerProfile.QWEN_R0.value,
        AgentWorkerProfile.QWEN_R1.value,
        AgentWorkerProfile.DEVSTRAL_SPECIALIST.value,
    }
)
_LOCAL_MODEL_IDENTIFIERS = frozenset({"qwen/qwen3.5-9b", "mistralai/devstral-small-2-2512"})


@dataclass(frozen=True)
class AgentCostTelemetrySummary:
    total_jobs: int
    local_jobs: int
    premium_jobs: int
    local_workload_pct: float
    premium_workload_pct: float
    qwen_jobs: int
    qwen_accepted: int
    qwen_escalated: int
    qwen_acceptance_rate: float
    qwen_escalation_rate: float
    devstral_jobs: int
    devstral_escalated: int
    devstral_escalation_rate: float
    average_execution_time_ms: float
    total_estimated_cost: float


def summarize(db: Session, organization_id: UUID) -> AgentCostTelemetrySummary:
    jobs = list(db.scalars(select(AgentJob).where(AgentJob.organization_id == organization_id)))
    total = len(jobs)
    local_jobs = [j for j in jobs if (j.assigned_model or "") in _LOCAL_MODEL_IDENTIFIERS]
    premium_jobs = [j for j in jobs if j not in local_jobs and j.assigned_model]

    qwen_jobs = [j for j in jobs if j.assigned_model == "qwen/qwen3.5-9b"]
    qwen_accepted = [j for j in qwen_jobs if j.status == AgentJobStatus.SUCCEEDED.value]
    qwen_escalated = [j for j in qwen_jobs if j.status == AgentJobStatus.ESCALATED.value]

    devstral_jobs = [j for j in jobs if j.assigned_model == "mistralai/devstral-small-2-2512"]
    devstral_escalated = [j for j in devstral_jobs if j.status == AgentJobStatus.ESCALATED.value]

    exec_times = [j.execution_time_ms for j in jobs if j.execution_time_ms is not None]
    costs = [float(j.actual_cost or j.estimated_cost or 0) for j in jobs]

    def _rate(numerator: int, denominator: int) -> float:
        return round(numerator / denominator, 4) if denominator else 0.0

    return AgentCostTelemetrySummary(
        total_jobs=total,
        local_jobs=len(local_jobs),
        premium_jobs=len(premium_jobs),
        local_workload_pct=_rate(len(local_jobs), total) * 100,
        premium_workload_pct=_rate(len(premium_jobs), total) * 100,
        qwen_jobs=len(qwen_jobs),
        qwen_accepted=len(qwen_accepted),
        qwen_escalated=len(qwen_escalated),
        qwen_acceptance_rate=_rate(len(qwen_accepted), len(qwen_jobs)),
        qwen_escalation_rate=_rate(len(qwen_escalated), len(qwen_jobs)),
        devstral_jobs=len(devstral_jobs),
        devstral_escalated=len(devstral_escalated),
        devstral_escalation_rate=_rate(len(devstral_escalated), len(devstral_jobs)),
        average_execution_time_ms=round(sum(exec_times) / len(exec_times), 1)
        if exec_times
        else 0.0,
        total_estimated_cost=round(sum(costs), 4),
    )


@dataclass(frozen=True)
class LearningTransferRate:
    """previously remediated gap types successfully handled in later
    unseen simulations without new code / previously remediated gap
    types encountered again. `remediated_gap_classes` is supplied by the
    caller (this program's own gap ledger, not derived automatically --
    a gap is only "remediated" once a human has actually shipped and
    verified a fix, which this codebase cannot infer from job data
    alone)."""

    encountered: int
    handled_without_new_code: int
    rate: float


def learning_transfer_rate(
    db: Session,
    organization_id: UUID,
    storage: StorageBackend,
    remediated_gap_classes: frozenset[str],
) -> LearningTransferRate:
    """Reads each terminal MISS_CLASSIFICATION job's own stored
    `WorkerStructuredResult` (never re-derives it) to determine the gap
    class it was actually classified under. A previously-remediated gap
    class "encountered again" that reaches SUCCEEDED (accepted without
    escalation, i.e. handled the same way every time, no new code
    required) counts toward the numerator; ESCALATED/FAILED count as
    encountered-but-not-cleanly-handled."""
    if not remediated_gap_classes:
        return LearningTransferRate(0, 0, 0.0)
    jobs = list(
        db.scalars(
            select(AgentJob).where(
                AgentJob.organization_id == organization_id,
                AgentJob.job_type == "MISS_CLASSIFICATION",
                AgentJob.status.in_(
                    [AgentJobStatus.SUCCEEDED.value, AgentJobStatus.ESCALATED.value]
                ),
                AgentJob.result_ref.is_not(None),
            )
        )
    )
    encountered = 0
    handled = 0
    for job in jobs:
        assert job.result_ref is not None  # guaranteed by the query filter above
        chunks = list(storage.open_stream(job.result_ref))
        result = json.loads(b"".join(chunks).decode("utf-8"))
        gap_class = result.get("primary_gap_class")
        if gap_class not in remediated_gap_classes:
            continue
        encountered += 1
        if job.status == AgentJobStatus.SUCCEEDED.value:
            handled += 1
    rate = round(handled / encountered, 4) if encountered else 0.0
    return LearningTransferRate(encountered, handled, rate)
