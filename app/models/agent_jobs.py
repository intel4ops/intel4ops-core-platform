"""AGENTIC-CONTROL-001: the durable Agent Job domain model.

This is the automation/control layer for the existing Intel4Ops learning
program -- it does NOT replace, and must never bypass, the existing
production orchestration (`app/services/analysis_case_orchestration_service.py`)
or the existing Validation Plane (`app/ground_truth_validation/`, see that
package's own `__init__.py` for the non-negotiable one-way dependency
rule this module also respects: nothing here writes ground truth, and a
job's evidence package may only carry truth-derived facts when
`evidence_plane == "validation"` and the referenced work has already
reached a frozen/terminal state -- see `evidence_plane` below).

Claim/heartbeat/lease mechanics are deliberately modeled on the existing,
already-proven `MappingRun` worker-lease pattern
(`app/models/canonical_mapping.py`, `app/services/canonical_mapping_service.py`,
`app/workers/mapping_execution.py`) rather than inventing a new one --
same `execution_lease_id`/`execution_worker_id`/`heartbeat_at` shape, same
`SELECT ... FOR UPDATE SKIP LOCKED` FIFO claim, same stale-lease recovery
sweep. The one architectural difference: AgentJob workers may run on a
remote machine (the owner's laptop, via the Local Worker Bridge) rather
than in-process, so the claim/heartbeat/result contract is exposed over
HTTP (`app/api/agent_job_routes.py`), not just called directly.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.session import Base
from app.models.entities import utc_now
from app.models.source_system import enum_values

# Portable JSON: JSONB on Postgres, JSON (TEXT-backed) on SQLite -- the
# same pattern already used elsewhere in this codebase (see
# app.models.source_system.portable_json) so the full non-Postgres test
# suite keeps working without a live Postgres instance.
_JSON = JSON().with_variant(JSONB(), "postgresql")


class AgentJobRiskClass(StrEnum):
    R0 = "R0"  # routine: extraction, classification, log triage
    R1 = "R1"  # engineering analysis: first-pass root cause, gap classification
    R2 = "R2"  # platform: canonical/shared changes, orchestration architecture
    R3 = "R3"  # safety/governance: mandatory Claude + owner gate, never automatic


class AgentJobStatus(StrEnum):
    QUEUED = "queued"
    CLAIMED = "claimed"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    ESCALATED = "escalated"
    OWNER_REVIEW_REQUIRED = "owner_review_required"
    CANCELLED = "cancelled"


class AgentJobOwnerApprovalStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class AgentJobEvidencePlane(StrEnum):
    """Which side of the Validation Plane's one-way boundary this job's
    evidence package is allowed to draw from. `production` jobs may only
    see already-persisted operational output (Findings, canonical
    entities, mappings, readiness -- never hidden truth). `validation`
    jobs may additionally carry truth-derived facts (a miss's expected
    value, its scenario family) -- but ONLY once the referenced
    SimulationBatchItem has reached FROZEN or later (see
    app/models/simulation_batch.py and
    app/services/agent_job_service.py's `create_job` enforcement)."""

    PRODUCTION = "production"
    VALIDATION = "validation"


class AgentJobEventType(StrEnum):
    CREATED = "CREATED"
    ROUTED = "ROUTED"
    CLAIMED = "CLAIMED"
    STARTED = "STARTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    RETRIED = "RETRIED"
    ESCALATED = "ESCALATED"
    OWNER_REVIEW_REQUIRED = "OWNER_REVIEW_REQUIRED"
    OWNER_APPROVED = "OWNER_APPROVED"
    OWNER_REJECTED = "OWNER_REJECTED"


class AgentWorkerProfile(StrEnum):
    """Config-driven routing targets (AGENTIC-CONTROL-001 Phase D) -- a
    profile name/version is stored on the job, never ad hoc parameters
    scattered through call sites."""

    QWEN_R0 = "QWEN_R0"
    QWEN_R1 = "QWEN_R1"
    DEVSTRAL_SPECIALIST = "DEVSTRAL_SPECIALIST"
    GEMINI_SYNTHESIS = "GEMINI_SYNTHESIS"
    CLAUDE_PLATFORM_REVIEW = "CLAUDE_PLATFORM_REVIEW"
    CODEX_IMPLEMENTATION = "CODEX_IMPLEMENTATION"


class AgentJob(Base):
    __tablename__ = "agent_jobs"
    __table_args__ = (
        CheckConstraint(
            f"risk_class IN ({enum_values(AgentJobRiskClass)})", name="ck_agent_job_risk_class"
        ),
        CheckConstraint(f"status IN ({enum_values(AgentJobStatus)})", name="ck_agent_job_status"),
        CheckConstraint(
            f"owner_approval_status IN ({enum_values(AgentJobOwnerApprovalStatus)})",
            name="ck_agent_job_owner_approval_status",
        ),
        CheckConstraint(
            f"evidence_plane IN ({enum_values(AgentJobEvidencePlane)})",
            name="ck_agent_job_evidence_plane",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 100)",
            name="ck_agent_job_confidence_range",
        ),
        CheckConstraint("retry_count >= 0", name="ck_agent_job_retry_count"),
        # A job requiring owner approval must not be left ambiguous about
        # whether that approval was ever asked for.
        CheckConstraint(
            "(owner_approval_required = false AND owner_approval_status = 'not_required') "
            "OR (owner_approval_required = true AND owner_approval_status != 'not_required')",
            name="ck_agent_job_owner_gate_consistency",
        ),
        Index("ix_agent_job_dispatch_fifo", "status", "risk_class", "created_at", "id"),
        Index("ix_agent_job_stale_heartbeat", "status", "heartbeat_at"),
        Index("ix_agent_job_org_created", "organization_id", "created_at"),
        Index("ix_agent_job_case", "analysis_case_id"),
        Index("ix_agent_job_run", "run_id"),
        Index("ix_agent_job_simulation", "simulation_id"),
        Index("ix_agent_job_gap", "gap_id"),
        Index("ix_agent_job_parent", "parent_job_id"),
        Index("ix_agent_job_owner_review", "owner_approval_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True
    )
    analysis_case_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    run_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    simulation_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    gap_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    parent_job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_jobs.id", ondelete="SET NULL"), nullable=True
    )

    job_type: Mapped[str] = mapped_column(String(100), nullable=False)
    risk_class: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=AgentJobStatus.QUEUED.value
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_plane: Mapped[str] = mapped_column(
        String(20), nullable=False, default=AgentJobEvidencePlane.PRODUCTION.value
    )

    requested_capability: Mapped[str] = mapped_column(String(150), nullable=False)
    assigned_worker: Mapped[str | None] = mapped_column(String(200), nullable=True)
    assigned_model: Mapped[str | None] = mapped_column(String(150), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    prompt_template_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Reference-only -- the evidence package and worker result are stored
    # as artifacts via StorageBackend (see app/storage/), never inlined
    # into this transactional row (AGENTIC-CONTROL-001 Phase B).
    input_evidence_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    result_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)

    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    escalation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    execution_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    actual_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)

    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    owner_approval_required: Mapped[bool] = mapped_column(nullable=False, default=False)
    owner_approval_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=AgentJobOwnerApprovalStatus.NOT_REQUIRED.value
    )

    # Worker-lease mechanics -- see this module's docstring.
    execution_lease_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    execution_worker_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    # Guards duplicate job creation from a retried "create job" call
    # (Phase B: "job processing must be idempotent").
    client_idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)


class AgentJobEvent(Base):
    """Durable, append-only lifecycle history -- never mutated, never
    deleted. One row per state transition; `detail_json` carries whatever
    structured context that transition needs (routing decision,
    escalation reason, owner decision note) without bloating the
    transactional AgentJob row itself."""

    __tablename__ = "agent_job_events"
    __table_args__ = (
        CheckConstraint(
            f"event_type IN ({enum_values(AgentJobEventType)})", name="ck_agent_job_event_type"
        ),
        Index("ix_agent_job_event_job", "agent_job_id", "created_at"),
        # A given (job, event_type, idempotency_key) combination may only
        # be recorded once -- lets a retried worker callback safely no-op
        # instead of writing a duplicate history entry.
        Index(
            "uq_agent_job_event_idempotency",
            "agent_job_id",
            "event_type",
            "idempotency_key",
            unique=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    agent_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_jobs.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    detail_json: Mapped[dict | None] = mapped_column(_JSON, nullable=True)
    # Defaults to a random value so most events remain independently
    # insertable; callers that need real idempotency (e.g. a worker
    # retrying a SUCCEEDED callback) pass a stable key of their own.
    idempotency_key: Mapped[str] = mapped_column(
        String(200), nullable=False, default=lambda: str(uuid4())
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AgentWorkerCredential(Base):
    """A scoped, revocable machine credential for a Local Worker Bridge
    instance (AGENTIC-CONTROL-001 Phase N). Never a user session, never a
    Supabase JWT -- a separate, narrow auth surface (see
    app/auth/worker_auth.py) that can claim only the risk classes and job
    types it is explicitly scoped to. `allowed_risk_classes` structurally
    excludes R2/R3 by default -- a worker credential can never claim a
    platform/safety-gated job no matter what a compromised or buggy
    worker script requests (Phase N: "Local worker cannot ... self-promote
    R2/R3 decisions"). Only a salted hash of the token is stored; the raw
    token is shown once at creation time and never persisted or logged."""

    __tablename__ = "agent_worker_credentials"
    __table_args__ = (Index("ix_agent_worker_credential_org", "organization_id"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    worker_id: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    allowed_risk_classes: Mapped[list] = mapped_column(
        _JSON,
        nullable=False,
        default=lambda: [AgentJobRiskClass.R0.value, AgentJobRiskClass.R1.value],
    )
    allowed_job_types: Mapped[list | None] = mapped_column(_JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
