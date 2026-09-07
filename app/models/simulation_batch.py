"""AGENTIC-CONTROL-001 Phase H: Simulation Controller state tracking.

This is a THIN layer on top of already-existing, already-tested
infrastructure -- it must never duplicate what already exists:

- Corpus discovery: `app.ground_truth_validation.corpus_discovery.SimulationCorpusDiscovery`
- Ground truth registration:
  `app.ground_truth_validation.service.validation_service.register_corpus`
- Production run + scoring: `app.validation_program.wave_coordinator.wave_coordinator`
  (already does AnalysisCaseRun execution + `validate_run()` synchronously,
  one simulation at a time -- see that module's own docstring)

What is genuinely new here (not present anywhere else in this codebase):
a persistent micro-batch/state-machine record so a batch of simulations
can be tracked through the states Phase H specifies, an owner-approval
gate before any remediation is even considered, and a hard, DB-enforced
truth-isolation invariant: `truth_accessed_at` may never predate
`frozen_at`, and `frozen_at` may only be set once the referenced
AnalysisCaseRun has reached one of validation's own terminal statuses
(see `app.ground_truth_validation.service._TERMINAL_RUN_STATUSES`,
mirrored -- not re-defined -- by `SimulationBatchService`).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.entities import utc_now
from app.models.source_system import enum_values


class SimulationBatchStatus(StrEnum):
    ACTIVE = "active"
    PAUSED_SAFETY_GATE = "paused_safety_gate"
    OWNER_REVIEW_REQUIRED = "owner_review_required"
    COMPLETE = "complete"


class SimulationBatchItemState(StrEnum):
    AVAILABLE = "available"
    SELECTED = "selected"
    IMPORTING = "importing"
    PRODUCTION_RUNNING = "production_running"
    TERMINAL = "terminal"
    FROZEN = "frozen"
    VALIDATING = "validating"
    SCORED = "scored"
    MISS_CLASSIFICATION = "miss_classification"
    GAP_CLUSTERING = "gap_clustering"
    REMEDIATION_REVIEW = "remediation_review"
    RETEST = "retest"
    REGRESSION = "regression"
    GRADUATED = "graduated"
    # Not one of the mission's 14 "happy path" states -- an explicit,
    # honest terminal-but-blocked state for a run that never legitimately
    # reached TERMINAL (RUN-RELIABILITY-001-class failure) or whose
    # validation itself failed. Never silently coerced into TERMINAL or
    # SCORED (Phase H: "never fabricate terminal status").
    BLOCKED = "blocked"


class SimulationBatch(Base):
    __tablename__ = "simulation_batches"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({enum_values(SimulationBatchStatus)})", name="ck_sim_batch_status"
        ),
        Index("ix_simulation_batch_org_created", "organization_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=SimulationBatchStatus.ACTIVE.value
    )
    safety_gate_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    decision_package_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)


class SimulationBatchItem(Base):
    __tablename__ = "simulation_batch_items"
    __table_args__ = (
        CheckConstraint(
            f"state IN ({enum_values(SimulationBatchItemState)})", name="ck_sim_batch_item_state"
        ),
        # The non-negotiable rule, enforced at the database, not just in
        # application code: truth may never be accessed before the
        # production run it belongs to has been frozen.
        CheckConstraint(
            "truth_accessed_at IS NULL OR "
            "(frozen_at IS NOT NULL AND truth_accessed_at >= frozen_at)",
            name="ck_sim_batch_item_truth_isolation",
        ),
        Index("ix_sim_batch_item_batch", "batch_id"),
        Index("ix_sim_batch_item_simulation", "simulation_id"),
        Index("ix_sim_batch_item_state", "state"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("simulation_batches.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    simulation_id: Mapped[str] = mapped_column(String(200), nullable=False)
    state: Mapped[str] = mapped_column(
        String(30), nullable=False, default=SimulationBatchItemState.AVAILABLE.value
    )
    analysis_case_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    run_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    validation_simulation_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    validation_run_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)

    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    truth_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    true_positive_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    false_positive_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    false_negative_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    precision: Mapped[float | None] = mapped_column(nullable=True)
    recall: Mapped[float | None] = mapped_column(nullable=True)
    economic_capture_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    economic_total_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)

    block_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
