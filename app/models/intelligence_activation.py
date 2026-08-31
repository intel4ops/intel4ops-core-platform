from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.entities import utc_now
from app.models.source_system import enum_values, portable_json

# ---------------------------------------------------------------------------
# P3.xxE.5 Phase 1 (SHADOW): the one new, additive table this milestone
# introduces. Persists both the pre-existing hard-coded activation
# condition and the new generic registry/readiness evaluator's result for
# each migrated (pack_code, rule_code) per run -- SHADOW mode never reads
# this table to decide what runs; it exists purely for auditability and to
# serve the readiness/activation-decision/shadow-comparison read API.
# Scoped (organization_id, analysis_case_id, run_id), matching E.3/E.4's
# own tenant/run-scoping convention exactly. Named IntelligenceActivationDecision
# per plan review correction 4 -- pairs naturally with the existing
# IntelligenceOrchestrationDecision/IntelligenceExecution model family
# (app/models/orchestration.py); no naming collision (checked directly).
# ---------------------------------------------------------------------------


class ActivationMode(StrEnum):
    SHADOW = "shadow"
    GOVERNED = "governed"


class GovernedReadinessStatus(StrEnum):
    DISABLED = "DISABLED"
    READY = "READY"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"


class IntelligenceActivationDecision(Base):
    __tablename__ = "intelligence_activation_decisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "analysis_case_id"],
            ["analysis_cases.organization_id", "analysis_cases.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            f"mode IN ({enum_values(ActivationMode)})",
            name="ck_intelligence_activation_decision_mode",
        ),
        CheckConstraint(
            f"governed_status IN ({enum_values(GovernedReadinessStatus)})",
            name="ck_intelligence_activation_decision_status",
        ),
        Index(
            "ix_intelligence_activation_decisions_org_case_run",
            "organization_id",
            "analysis_case_id",
            "run_id",
        ),
        Index("ix_intelligence_activation_decisions_rule", "run_id", "rule_code"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    analysis_case_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_case_runs.id", ondelete="CASCADE"), nullable=False
    )
    pack_code: Mapped[str] = mapped_column(String(40), nullable=False)
    rule_code: Mapped[str] = mapped_column(String(100), nullable=False)
    pack_version: Mapped[str] = mapped_column(String(20), nullable=False)
    activation_policy_version: Mapped[str] = mapped_column(String(20), nullable=False)
    mode: Mapped[str] = mapped_column(String(10), nullable=False)
    legacy_activated: Mapped[bool] = mapped_column(nullable=False)
    legacy_reason: Mapped[str] = mapped_column(String(500), nullable=False)
    governed_status: Mapped[str] = mapped_column(String(10), nullable=False)
    governed_missing_summary: Mapped[list[str]] = mapped_column(portable_json, default=list)
    governed_confidence_summary: Mapped[dict[str, object]] = mapped_column(
        portable_json, default=dict
    )
    agree: Mapped[bool] = mapped_column(nullable=False)
    evidence_summary: Mapped[list[str]] = mapped_column(portable_json, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
