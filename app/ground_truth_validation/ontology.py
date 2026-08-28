from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

# ---------------------------------------------------------------------------
# P3.xxD.1E Normalized Validation Ontology (section 5/6). This is what
# every GroundTruthPackageAdapter must produce and what the central
# matchers/integrity checker operate on -- neither ever sees a source
# document's own field names. A source schema's vocabulary
# ("finding_id", "expected_severity", "leakage_id", ...) is translated
# into this ontology exclusively inside adapters
# (app/ground_truth_validation/adapters/); nothing here is aware any
# specific adapter or simulation exists.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NormalizedExpectedFinding:
    truth_finding_id: str
    scenario_code: str | None
    severity: str
    domain: str | None = None
    expected_detection_family: str | None = None
    linked_leakage_id: str | None = None
    entities: list[dict[str, object]] = field(default_factory=list)
    affected_records: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    expected_economic_impact: Decimal | None = None
    currency: str | None = None
    description: str = ""


@dataclass(frozen=True)
class NormalizedLeakageTruth:
    truth_leakage_id: str
    scenario_code: str | None
    business_context: str | None = None
    affected_records: list[str] = field(default_factory=list)
    entities: list[dict[str, object]] = field(default_factory=list)
    time_window: dict[str, object] | None = None
    root_cause: str | None = None
    causal_chain: list[object] = field(default_factory=list)
    severity: str | None = None
    recoverable: bool | None = None
    detection_family: str | None = None
    expected_evidence: list[str] = field(default_factory=list)
    true_leakage_value: Decimal | None = None
    recoverable_value: Decimal | None = None
    currency: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class NormalizedCausalTruth:
    truth_causal_id: str
    scenario_code: str | None = None
    linked_leakage_id: str | None = None
    linked_finding_id: str | None = None
    expected_root_cause: str | None = None
    expected_causal_chain: list[object] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class NormalizedDataQualityTruth:
    truth_dq_id: str
    dq_family: str | None = None
    affected_record: str | None = None
    affected_dataset_or_field: str | None = None
    detail: str | None = None
    severity: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class NormalizedDocument:
    """One raw input document, before adapter normalization -- used both as
    persistence input and, together with NormalizedManifest, as the
    `package_metadata` an adapter's can_handle() inspects for role
    detection when no manifest is present (section 4D)."""

    declared_role: str | None
    detected_role: str | None
    raw_content: object
    storage_reference: str | None = None
    checksum: str | None = None


@dataclass(frozen=True)
class NormalizedManifest:
    simulation_code: str | None
    truth_schema_version: str | None
    sealed_at: str | None
    summary: dict[str, object] = field(default_factory=dict)
    document_inventory: list[dict[str, object]] = field(default_factory=list)
    checksums: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class IntegrityIssue:
    severity: str  # "warning" | "error"
    code: str
    message: str
    document_role: str | None = None
    truth_ref: str | None = None


@dataclass(frozen=True)
class NormalizedPackage:
    adapter_code: str
    adapter_version: str
    schema_version: str
    manifest: NormalizedManifest | None
    expected_findings: list[NormalizedExpectedFinding] = field(default_factory=list)
    leakage_truth: list[NormalizedLeakageTruth] = field(default_factory=list)
    causal_truth: list[NormalizedCausalTruth] = field(default_factory=list)
    data_quality_truth: list[NormalizedDataQualityTruth] = field(default_factory=list)
    expected_clean_areas: list[str] = field(default_factory=list)
    tolerance: dict[str, object] = field(default_factory=dict)
    documents: list[NormalizedDocument] = field(default_factory=list)
