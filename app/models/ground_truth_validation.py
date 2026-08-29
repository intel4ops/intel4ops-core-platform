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


class ValidationDimensionCode(StrEnum):
    """P3.xxD.1E: the open-ended set of independently-scored validation
    dimensions (section 11E) -- new dimensions are new registry/config
    entries and new rows here, never a rewrite of the matching engine."""

    FINDING_DETECTION = "finding_detection"
    LEAKAGE_VALUE = "leakage_value"
    CAUSAL = "causal"
    DATA_QUALITY = "data_quality"


class ValidationDimensionStatus(StrEnum):
    """Never a fabricated zero when a dimension cannot be evaluated --
    see ValidationDimensionResult.status."""

    SCORED = "scored"
    PARTIALLY_SCORED = "partially_scored"
    NOT_AVAILABLE = "not_available"
    NOT_IMPLEMENTED = "not_implemented"
    INSUFFICIENT_PRODUCTION_EVIDENCE = "insufficient_production_evidence"
    INVALID_GROUND_TRUTH = "invalid_ground_truth"


class ValidationIntegritySeverity(StrEnum):
    WARNING = "warning"
    ERROR = "error"


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
    # P3.xxD.1E.1: which GroundTruthPackageAdapter normalized this upload.
    # Never a simulation identifier -- an adapter is schema-shaped, not
    # simulation-specific (see app/ground_truth_validation/adapters/).
    adapter_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    adapter_version: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # The SELECTED adapter's own schema_version (== adapter_code today, but
    # kept as a distinct field since an adapter could in principle support
    # more than one schema_version in the future). Always populated once an
    # adapter has been selected.
    schema_version: Mapped[str] = mapped_column(String(50), default="intel4ops_simple_v1")
    # P3.xxD.1E.1: the RAW schema_version the caller declared in the
    # request, exactly as sent -- None if the caller omitted it and
    # selection went through can_handle() shape-detection instead. Never
    # conflated with `schema_version` above (the resolved adapter's own
    # identifier): the whole point of this column is to preserve "the
    # caller declared nothing" as a real, distinguishable fact rather than
    # silently rewriting it to whatever got selected.
    source_schema_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # The authored manifest document's own declared metadata (simulation_id,
    # sealed_at, summary totals, file/checksum inventory) -- kept verbatim,
    # never reshaped into engine-specific fields.
    manifest_summary: Mapped[dict[str, object] | None] = mapped_column(portable_json, nullable=True)
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
    # P3.xxD.1E section 7: domain is no longer required -- authored truth may
    # express business semantics purely through expected_detection_family
    # (resolved to production domains/rule_ids only inside Validation via
    # app/ground_truth_validation/family_registry.py, never required by the
    # matcher). Kept nullable, not removed, for V1-package backward
    # compatibility and as an optional direct hint when authors do supply it.
    domain: Mapped[str | None] = mapped_column(String(100), nullable=True)
    severity: Mapped[str] = mapped_column(String(50), nullable=False)
    entities: Mapped[list[dict[str, object]]] = mapped_column(portable_json, default=list)
    evidence_refs: Mapped[list[str]] = mapped_column(portable_json, default=list)
    expected_economic_impact: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    # P3.xxD.1E additive fields (all nullable -- a V1 upload never sets them).
    expected_detection_family: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Adapter-emitted normalized link, e.g. "LK-1" -- the *value*, never a
    # parsing rule ("strip EF- prefix") which stays inside the adapter that
    # produced it (section 9).
    linked_leakage_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    affected_records: Mapped[list[str] | None] = mapped_column(portable_json, nullable=True)
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
    """A single truth-vs-actual match. Originally finding-detection only
    (P3.xxD.1B); P3.xxD.1E broadens it to also carry leakage-value matches
    (dimension_code distinguishes which), reusing the identical TP/FP/FN
    shape rather than standing up a parallel table for a structurally
    identical concept (section 17: no unnecessary duplicate tables)."""

    __tablename__ = "validation_finding_matches"
    __table_args__ = (
        CheckConstraint(
            f"match_type IN ({', '.join(repr(m.value) for m in ValidationMatchType)})",
            name="ck_validation_finding_match_type",
        ),
        CheckConstraint(
            "expected_finding_id IS NOT NULL OR actual_finding_id IS NOT NULL "
            "OR expected_leakage_truth_id IS NOT NULL",
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
    dimension_code: Mapped[str] = mapped_column(
        String(30), default=ValidationDimensionCode.FINDING_DETECTION.value
    )
    match_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # Null for a false positive (no expected finding matched).
    expected_finding_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("validation_expected_findings.id", ondelete="RESTRICT"), nullable=True
    )
    # Set instead of expected_finding_id when dimension_code=leakage_value.
    expected_leakage_truth_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("validation_leakage_truths.id", ondelete="RESTRICT"), nullable=True
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
    # P3.xxD.1E section 14 explainability -- which comparison dimensions
    # agreed/disagreed and why, so a match's classification is auditable
    # rather than implicit in score arithmetic.
    matched_dimensions: Mapped[list[str] | None] = mapped_column(portable_json, nullable=True)
    unmatched_dimensions: Mapped[list[str] | None] = mapped_column(portable_json, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
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


class ValidationGroundTruthDocument(Base):
    """One raw document within an uploaded ground-truth package (manifest,
    expected_findings, leakage_truth, causal_truth, data_quality_truth, or
    any future role) -- section 4E/17. declared_role is what the caller (or
    the package's own manifest) claimed; detected_role is what the selected
    adapter's can_handle/role-detection logic actually resolved it to --
    kept distinct so a mismatch is visible rather than silently
    overwritten."""

    __tablename__ = "validation_ground_truth_documents"
    __table_args__ = (Index("ix_validation_gt_documents_gt", "ground_truth_id"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    ground_truth_id: Mapped[UUID] = mapped_column(
        ForeignKey("validation_ground_truths.id", ondelete="CASCADE"), nullable=False
    )
    declared_role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    detected_role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    storage_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    record_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ValidationLeakageTruth(Base):
    """Normalized LeakageTruth ontology entity (section 5B). Never keyed to
    a specific simulation's field names -- an adapter produced these values
    from whatever the authored schema called them."""

    __tablename__ = "validation_leakage_truths"
    __table_args__ = (
        UniqueConstraint(
            "ground_truth_id", "truth_leakage_id", name="uq_validation_leakage_truth_id"
        ),
        Index("ix_validation_leakage_truths_org", "organization_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    ground_truth_id: Mapped[UUID] = mapped_column(
        ForeignKey("validation_ground_truths.id", ondelete="CASCADE"), nullable=False
    )
    truth_leakage_id: Mapped[str] = mapped_column(String(100), nullable=False)
    scenario_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    business_context: Mapped[str | None] = mapped_column(String(200), nullable=True)
    affected_records: Mapped[list[str] | None] = mapped_column(portable_json, nullable=True)
    entities: Mapped[list[dict[str, object]]] = mapped_column(portable_json, default=list)
    time_window: Mapped[dict[str, object] | None] = mapped_column(portable_json, nullable=True)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    causal_chain: Mapped[list[object] | None] = mapped_column(portable_json, nullable=True)
    severity: Mapped[str | None] = mapped_column(String(50), nullable=True)
    recoverable: Mapped[bool | None] = mapped_column(nullable=True)
    detection_family: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expected_evidence: Mapped[list[str]] = mapped_column(portable_json, default=list)
    true_leakage_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    recoverable_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    metadata_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ValidationCausalTruth(Base):
    """Normalized CausalTruth ontology entity (section 5C). Linked by
    adapter-emitted normalized id, never a central-engine parsing rule
    (section 9) -- exactly one of linked_leakage_id / linked_finding_id is
    expected to resolve for a given record, per whatever the authored
    package actually links causal truth to."""

    __tablename__ = "validation_causal_truths"
    __table_args__ = (Index("ix_validation_causal_truths_org", "organization_id"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    ground_truth_id: Mapped[UUID] = mapped_column(
        ForeignKey("validation_ground_truths.id", ondelete="CASCADE"), nullable=False
    )
    truth_causal_id: Mapped[str] = mapped_column(String(100), nullable=False)
    linked_leakage_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    linked_finding_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    scenario_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expected_root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_causal_chain: Mapped[list[object] | None] = mapped_column(portable_json, nullable=True)
    metadata_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ValidationDataQualityTruth(Base):
    """Normalized DataQualityTruth ontology entity (section 5D)."""

    __tablename__ = "validation_data_quality_truths"
    __table_args__ = (
        UniqueConstraint("ground_truth_id", "truth_dq_id", name="uq_validation_dq_truth_id"),
        Index("ix_validation_dq_truths_org", "organization_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    ground_truth_id: Mapped[UUID] = mapped_column(
        ForeignKey("validation_ground_truths.id", ondelete="CASCADE"), nullable=False
    )
    truth_dq_id: Mapped[str] = mapped_column(String(100), nullable=False)
    dq_family: Mapped[str | None] = mapped_column(String(100), nullable=True)
    affected_record: Mapped[str | None] = mapped_column(String(200), nullable=True)
    affected_dataset_or_field: Mapped[str | None] = mapped_column(String(200), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str | None] = mapped_column(String(50), nullable=True)
    metadata_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ValidationPackageIntegrityIssue(Base):
    """Generic package-integrity findings (section 10) -- never a silent
    coercion. error severity blocks persistence of the upload; warning does
    not."""

    __tablename__ = "validation_package_integrity_issues"
    __table_args__ = (
        CheckConstraint(
            f"severity IN ({', '.join(repr(s.value) for s in ValidationIntegritySeverity)})",
            name="ck_validation_integrity_severity",
        ),
        Index("ix_validation_integrity_issues_gt", "ground_truth_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    ground_truth_id: Mapped[UUID] = mapped_column(
        ForeignKey("validation_ground_truths.id", ondelete="CASCADE"), nullable=False
    )
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    document_role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    truth_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ValidationDimensionResult(Base):
    """One row per (validation_run_id, dimension_code) -- the generic,
    extensible home for every scored dimension (section 11E/12). Adding a
    dimension (relationship accuracy, readiness accuracy, ...) never
    requires a new table, only a new dimension_code and a new matcher
    function that produces one of these."""

    __tablename__ = "validation_dimension_results"
    __table_args__ = (
        UniqueConstraint(
            "validation_run_id", "dimension_code", name="uq_validation_dimension_result"
        ),
        Index("ix_validation_dimension_results_run", "validation_run_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    validation_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("simulation_validation_runs.id", ondelete="CASCADE"), nullable=False
    )
    dimension_code: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
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
event.listen(ValidationLeakageTruth, "before_update", _immutable)
event.listen(ValidationLeakageTruth, "before_delete", _immutable)
event.listen(ValidationCausalTruth, "before_update", _immutable)
event.listen(ValidationCausalTruth, "before_delete", _immutable)
event.listen(ValidationDataQualityTruth, "before_update", _immutable)
event.listen(ValidationDataQualityTruth, "before_delete", _immutable)
