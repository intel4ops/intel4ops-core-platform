from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.entities import portable_json, utc_now
from app.semantic.candidate import InterpretationDecisionStatus

# ---------------------------------------------------------------------------
# P3.xxE.1 Semantic Foundation persistence. Production execution surface --
# reused by AnalysisCase orchestration, never by app.ground_truth_validation
# (see tests/test_semantic_architecture_guardrails.py). Recomputed fresh on
# every run (same latest-state convention as AnalysisCaseDataset.
# mapping_status), never overwritten -- run history stays comparable, same
# as findings.
# ---------------------------------------------------------------------------


class SemanticDatasetProfile(Base):
    """One DatasetProfiler result per (dataset, run) -- section 3. Field-
    level profiles are stored as one JSON list rather than a child table:
    they are read as a whole per dataset, never queried/filtered field-by-
    field across datasets, so a child table would add join cost with no
    real benefit."""

    __tablename__ = "semantic_dataset_profiles"
    __table_args__ = (
        Index("ix_semantic_dataset_profiles_dataset", "analysis_case_dataset_id"),
        Index("ix_semantic_dataset_profiles_run", "run_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    analysis_case_dataset_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_case_datasets.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_case_runs.id", ondelete="CASCADE"), nullable=False
    )
    dataset_label: Mapped[str] = mapped_column(String(255), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    column_count: Mapped[int] = mapped_column(Integer, default=0)
    field_profiles: Mapped[list[dict[str, object]]] = mapped_column(portable_json, default=list)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SemanticRoleInterpretation(Base):
    """One DatasetRoleClassifier result per (dataset, run) -- section 4.
    primary_role is intentionally unconstrained (String, not a DB CHECK
    against DatasetRole) so a future registry-driven role vocabulary
    extension never requires a migration -- DatasetRole in
    app/semantic/role_classifier.py is the governed source of truth for
    valid values today."""

    __tablename__ = "semantic_role_interpretations"
    __table_args__ = (
        Index("ix_semantic_role_interpretations_dataset", "analysis_case_dataset_id"),
        Index("ix_semantic_role_interpretations_run", "run_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    analysis_case_dataset_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_case_datasets.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_case_runs.id", ondelete="CASCADE"), nullable=False
    )
    primary_role: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float] = mapped_column(default=0.0)
    evidence: Mapped[list[str]] = mapped_column(portable_json, default=list)
    secondary_roles: Mapped[list[str]] = mapped_column(portable_json, default=list)
    alternative_roles: Mapped[list[dict[str, object]]] = mapped_column(portable_json, default=list)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SemanticInterpretationDecision(Base):
    """One governed field-level interpretation decision per (dataset,
    field, run) -- section 7. Only the selected decision + a bounded
    top-N alternatives are persisted (section 6: never every ephemeral
    candidate)."""

    __tablename__ = "semantic_interpretation_decisions"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({', '.join(repr(s.value) for s in InterpretationDecisionStatus)})",
            name="ck_semantic_interpretation_decision_status",
        ),
        Index("ix_semantic_interpretation_decisions_dataset", "analysis_case_dataset_id"),
        Index("ix_semantic_interpretation_decisions_run", "run_id"),
        Index("ix_semantic_interpretation_decisions_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    analysis_case_dataset_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_case_datasets.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_case_runs.id", ondelete="CASCADE"), nullable=False
    )
    source_field: Mapped[str] = mapped_column(String(255), nullable=False)
    selected_concept: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confidence: Mapped[float] = mapped_column(default=0.0)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    evidence_summary: Mapped[list[str]] = mapped_column(portable_json, default=list)
    alternative_candidates: Mapped[list[dict[str, object]]] = mapped_column(
        portable_json, default=list
    )
    decision_source: Mapped[str] = mapped_column(String(100), nullable=False)
    decision_version: Mapped[str] = mapped_column(String(100), nullable=False)
    review_actor_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    review_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
