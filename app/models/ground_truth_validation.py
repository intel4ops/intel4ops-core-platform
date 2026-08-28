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
    Text,
    UniqueConstraint,
    Uuid,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.entities import portable_json, utc_now

# ---------------------------------------------------------------------------
# P3.xxD.1B Validation Plane. Structurally separate from every production
# execution module (Connect/Trust/Mapping/Entity Resolution/Intelligence/
# Command/Recovery/AnalysisCase orchestration) -- see
# app/ground_truth_validation/__init__.py for the dependency-direction
# contract this module family enforces: Validation reads persisted
# operational results one-way; nothing in app/services/analysis_case_* or
# app/services/*intelligence*.py (the production execution surface) may
# import anything from here (enforced by
# tests/test_validation_import_boundary.py, release-blocking).
#
# NOTE ON NAMING: this is deliberately app/models/ground_truth_validation.py,
# not app/models/validation.py, because app/validation/ and
# app/models/certification.py already implement an entirely different,
# pre-existing "validation" concern -- a CI/release-gate certification
# system (ValidationRun/ValidationSuite/ValidationScenarioVersion:
# commit_sha/branch/migration_head, pass/fail gate results), used only by
# app/cli/certify.py. To avoid any namespace collision or confusion with
# that unrelated system, this module's run entity is named
# `SimulationValidationRun` instead of the illustrative `ValidationRun` name
# from the original spec. Every other entity name here is free of collision.
# ---------------------------------------------------------------------------


class SimulationValidationRunStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class ValidationMatchType(StrEnum):
    TRUE_POSITIVE = "true_positive"
    FALSE_POSITIVE = "false_positive"
    FALSE_NEGATIVE = "false_negative"


class ValidationSimulation(Base):
    """Links a simulation_id (e.g. "SIM-OFS-FIELDMAINT-001") to the
    AnalysisCase that will be run against it. AnalysisCase execution never
    reads this table or anything reachable from it -- the link is
    Validation -> AnalysisCase (by reference only, read-only), never the
    reverse."""

    __tablename__ = "validation_simulations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "simulation_code", name="uq_validation_simulation_code"
        ),
        Index("ix_validation_simulations_org", "organization_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    simulation_code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Reference only -- Validation reads this AnalysisCase's persisted
    # results after a run; AnalysisCase orchestration never reads this
    # table or knows a ValidationSimulation exists.
    analysis_case_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_cases.id", ondelete="RESTRICT"), nullable=False
    )
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ValidationGroundTruth(Base):
    """One immutable, versioned upload of ground truth for a simulation.
    Never stored as a SourceArtifact and never exposed through any
    AnalysisCase dataset API -- ground truth has its own storage namespace
    (see app/validation/storage.py) and its own normalizer (see
    app/validation/normalizer.py), deliberately never touching
    ArtifactParserRegistry or the customer-data ingestion path."""

    __tablename__ = "validation_ground_truths"
    __table_args__ = (
        UniqueConstraint(
            "simulation_id", "version", name="uq_validation_ground_truth_simulation_version"
        ),
        Index("ix_validation_ground_truths_org", "organization_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    simulation_id: Mapped[UUID] = mapped_column(
        ForeignKey("validation_simulations.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_clean_areas: Mapped[list[str]] = mapped_column(portable_json, default=list)
    tolerance: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    raw_format_version: Mapped[str] = mapped_column(String(20), default="1.0")
    uploaded_by_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ValidationExpectedFinding(Base):
    """One expected finding within a ground-truth version. Matched, not
    compared by literal text, against actual governed Findings -- see
    app/validation/matcher.py."""

    __tablename__ = "validation_expected_findings"
    __table_args__ = (
        UniqueConstraint(
            "ground_truth_id",
            "expected_finding_code",
            name="uq_validation_expected_finding_code",
        ),
        Index("ix_validation_expected_findings_org", "organization_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    ground_truth_id: Mapped[UUID] = mapped_column(
        ForeignKey("validation_ground_truths.id", ondelete="CASCADE"), nullable=False
    )
    expected_finding_code: Mapped[str] = mapped_column(String(100), nullable=False)
    domain: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(50), nullable=False)
    entities: Mapped[list[dict[str, object]]] = mapped_column(portable_json, default=list)
    evidence_refs: Mapped[list[str]] = mapped_column(portable_json, default=list)
    expected_economic_impact: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SimulationValidationRun(Base):
    """One comparison of a ground-truth version against one terminal-state
    AnalysisCaseRun's persisted results. Read-only with respect to the
    AnalysisCaseRun it validates -- validating never mutates production
    state (see app/validation/service.py). See the module docstring above
    for why this is not named `ValidationRun` (already taken by the
    unrelated CI/release-gate certification system in
    app/models/certification.py)."""

    __tablename__ = "simulation_validation_runs"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({', '.join(repr(s.value) for s in SimulationValidationRunStatus)})",
            name="ck_simulation_validation_run_status",
        ),
        Index("ix_simulation_validation_runs_org_sim", "organization_id", "simulation_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    simulation_id: Mapped[UUID] = mapped_column(
        ForeignKey("validation_simulations.id", ondelete="CASCADE"), nullable=False
    )
    ground_truth_id: Mapped[UUID] = mapped_column(
        ForeignKey("validation_ground_truths.id", ondelete="RESTRICT"), nullable=False
    )
    # Reference only, read after the fact -- never written back to.
    analysis_case_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_case_runs.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default=SimulationValidationRunStatus.PENDING.value
    )
    triggered_by_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class ValidationFindingMatch(Base):
    __tablename__ = "validation_finding_matches"
    __table_args__ = (
        CheckConstraint(
            f"match_type IN ({', '.join(repr(m.value) for m in ValidationMatchType)})",
            name="ck_validation_finding_match_type",
        ),
        CheckConstraint(
            "expected_finding_id IS NOT NULL OR actual_finding_id IS NOT NULL",
            name="ck_validation_finding_match_has_side",
        ),
        Index("ix_validation_finding_matches_run", "validation_run_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    validation_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("simulation_validation_runs.id", ondelete="CASCADE"), nullable=False
    )
    match_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # Null for a false positive (no expected finding matched).
    expected_finding_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("validation_expected_findings.id", ondelete="RESTRICT"), nullable=True
    )
    # Null for a false negative (no actual finding matched). References the
    # existing governed Finding table -- read-only, never duplicated.
    actual_finding_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("findings.id", ondelete="RESTRICT"), nullable=True
    )
    severity_match: Mapped[bool | None] = mapped_column(nullable=True)
    entity_match: Mapped[bool | None] = mapped_column(nullable=True)
    evidence_match: Mapped[bool | None] = mapped_column(nullable=True)
    economic_variance_pct: Mapped[float | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ValidationScore(Base):
    __tablename__ = "validation_scores"
    __table_args__ = (UniqueConstraint("validation_run_id", name="uq_validation_score_run"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    validation_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("simulation_validation_runs.id", ondelete="CASCADE"), nullable=False
    )
    true_positive_count: Mapped[int] = mapped_column(Integer, default=0)
    false_positive_count: Mapped[int] = mapped_column(Integer, default=0)
    false_negative_count: Mapped[int] = mapped_column(Integer, default=0)
    precision: Mapped[float | None] = mapped_column(nullable=True)
    recall: Mapped[float | None] = mapped_column(nullable=True)
    f1: Mapped[float | None] = mapped_column(nullable=True)
    severity_accuracy: Mapped[float | None] = mapped_column(nullable=True)
    entity_accuracy: Mapped[float | None] = mapped_column(nullable=True)
    evidence_accuracy: Mapped[float | None] = mapped_column(nullable=True)
    economic_variance_avg_pct: Mapped[float | None] = mapped_column(nullable=True)
    critical_leakage_recall: Mapped[float | None] = mapped_column(nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


def _immutable(*_: object) -> None:
    raise ValueError("validation ground truth is immutable once uploaded -- upload a new version")


# Ground truth is append-only: correcting it means uploading a new version,
# never editing history out from under a prior SimulationValidationRun that
# already scored against it.
event.listen(ValidationGroundTruth, "before_update", _immutable)
event.listen(ValidationGroundTruth, "before_delete", _immutable)
event.listen(ValidationExpectedFinding, "before_update", _immutable)
event.listen(ValidationExpectedFinding, "before_delete", _immutable)
