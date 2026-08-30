from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.entities import portable_json, utc_now
from app.semantic.review import (
    SemanticDecisionEffectiveStatus,
    SemanticDecisionSource,
    SemanticReviewAction,
)

# ---------------------------------------------------------------------------
# P3.xxE.1A Semantic Review & Governance Foundation. Production execution
# surface -- reused by the semantic review API/service, never by
# app.ground_truth_validation (see tests/test_semantic_architecture_guardrails.py
# and tests/test_validation_import_boundary.py). Both tables here are
# append-only (see the event.listen immutability guards at the bottom of
# this file, copied verbatim from app/models/findings.py) -- a later human
# review never mutates an earlier one, it always appends a new row.
#
# Deliberately NOT in this milestone: any cross-run identity/signature
# concept. SemanticDecisionVersion is keyed to exactly one
# SemanticInterpretationDecision.id, never to a field "lineage" that could
# span multiple runs -- see the approved P3.xxE.1A plan's Out of Scope
# section. Reuse/inheritance is P3.xxE.6's job, not this milestone's.
# ---------------------------------------------------------------------------


def _enum_values(enum_type: type[StrEnum]) -> str:
    return ", ".join(repr(member.value) for member in enum_type)


class SemanticReview(Base):
    """One append-only reviewer action against a SemanticInterpretationDecision
    -- section 6 of the plan. Never mutates the reviewed decision row; the
    decision row stays exactly as the machine produced it, forever."""

    __tablename__ = "semantic_reviews"
    __table_args__ = (
        CheckConstraint(
            f"action IN ({_enum_values(SemanticReviewAction)})",
            name="ck_semantic_review_action",
        ),
        Index("ix_semantic_reviews_decision", "decision_id"),
        Index("ix_semantic_reviews_org", "organization_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    decision_id: Mapped[UUID] = mapped_column(
        ForeignKey("semantic_interpretation_decisions.id", ondelete="RESTRICT"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    corrected_concept: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    reviewer_role: Mapped[str] = mapped_column(String(50), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SemanticDecisionVersion(Base):
    """The effective-decision version chain for one SemanticInterpretationDecision
    -- section 7 of the plan. Keyed to decision_id, NOT a cross-run
    signature. MACHINE_AUTO_ACCEPTED/deterministic_confidence_engine never
    appear here as stored values -- they are resolver-computed only (see
    app/semantic/review.py::resolve_effective_decision)."""

    __tablename__ = "semantic_decision_versions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "decision_id",
            "version_number",
            name="uq_semantic_decision_versions_org_decision_version",
        ),
        CheckConstraint(
            "(version_number = 1 AND supersedes_version_id IS NULL) OR "
            "(version_number > 1 AND supersedes_version_id IS NOT NULL)",
            name="ck_semantic_decision_versions_supersession",
        ),
        CheckConstraint(
            f"effective_status IN ({_enum_values(SemanticDecisionEffectiveStatus)})",
            name="ck_semantic_decision_versions_status",
        ),
        CheckConstraint(
            f"source IN ({_enum_values(SemanticDecisionSource)})",
            name="ck_semantic_decision_versions_source",
        ),
        Index("ix_semantic_decision_versions_org_decision", "organization_id", "decision_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    decision_id: Mapped[UUID] = mapped_column(
        ForeignKey("semantic_interpretation_decisions.id", ondelete="RESTRICT"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # ondelete="NO ACTION" (not RESTRICT) specifically on this
    # self-referential FK -- nothing ever deletes these rows in practice
    # (append-only, enforced below), but SQLite's DROP TABLE treats a
    # self-referential ON DELETE RESTRICT as an immediate per-row check
    # and fails on any chained (version 2+) row, breaking the SQLite-
    # backed test suite even though the same schema is fine on Postgres.
    supersedes_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("semantic_decision_versions.id", ondelete="NO ACTION"), nullable=True
    )
    effective_status: Mapped[str] = mapped_column(String(30), nullable=False)
    effective_concept: Mapped[str | None] = mapped_column(String(100), nullable=True)
    review_id: Mapped[UUID] = mapped_column(
        ForeignKey("semantic_reviews.id", ondelete="RESTRICT"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    effective_confidence: Mapped[float | None] = mapped_column(nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SemanticDecisionAuditEvent(Base):
    """Standard per-domain audit table -- same shape as MappingAuditEvent
    (app/models/canonical_mapping.py). Written by a private _audit() in
    app/services/semantic_review_service.py; never updated or deleted."""

    __tablename__ = "semantic_decision_audit_events"
    __table_args__ = (
        Index("ix_semantic_decision_audit_org_time", "organization_id", "occurred_at"),
        Index(
            "ix_semantic_decision_audit_org_entity",
            "organization_id",
            "entity_type",
            "entity_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    actor_type: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


def _immutable(_: object, __: object, target: object) -> None:
    raise ValueError(f"{type(target).__name__} is immutable")


for _immutable_model in (SemanticReview, SemanticDecisionVersion):
    event.listen(_immutable_model, "before_update", _immutable)
    event.listen(_immutable_model, "before_delete", _immutable)
