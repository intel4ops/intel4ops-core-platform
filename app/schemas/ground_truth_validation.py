from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ValidationSimulationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    simulation_code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    analysis_case_id: UUID


class ValidationSimulationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    simulation_code: str
    name: str
    analysis_case_id: UUID
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


class ExpectedFindingUpload(BaseModel):
    """V1 simple-package shape (section 15) -- kept for backward
    compatibility. A V2 package sends documents.expected_findings instead,
    in whatever field names its adapter's schema_version declares."""

    model_config = ConfigDict(extra="forbid")

    expected_finding_code: str = Field(min_length=1, max_length=100)
    domain: str = Field(min_length=1, max_length=100)
    severity: str = Field(min_length=1, max_length=50)
    entities: list[dict[str, object]] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    expected_economic_impact: float | None = None
    currency: str | None = Field(default=None, max_length=3)
    description: str = ""


class GroundTruthUpload(BaseModel):
    """V1: the original flat simple-package shape."""

    model_config = ConfigDict(extra="forbid")

    expected_findings: list[ExpectedFindingUpload] = Field(min_length=1)
    expected_clean_areas: list[str] = Field(default_factory=list)
    tolerance: dict[str, object] = Field(default_factory=dict)


class GroundTruthPackageUploadV2(BaseModel):
    """V2 (section 15): a versioned, multi-document package. schema_version
    selects (or hints at) the GroundTruthPackageAdapter
    (app/ground_truth_validation/adapters/) that interprets `manifest` and
    `documents`; document roles and their field names are owned entirely
    by that adapter, not by this schema -- Core normalizes the whole
    package server-side, so the frontend never derives matching/scores/
    domains itself (section 16)."""

    model_config = ConfigDict(extra="allow")

    schema_version: str
    manifest: dict[str, object] | None = None
    documents: dict[str, object]


class ExpectedFindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    expected_finding_code: str
    domain: str | None
    severity: str
    entities: list[dict[str, object]]
    evidence_refs: list[str]
    expected_economic_impact: float | None
    currency: str | None
    description: str
    expected_detection_family: str | None
    linked_leakage_id: str | None
    affected_records: list[str] | None


class LeakageTruthRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    truth_leakage_id: str
    scenario_code: str | None
    business_context: str | None
    severity: str | None
    recoverable: bool | None
    detection_family: str | None
    true_leakage_value: float | None
    recoverable_value: float | None
    currency: str | None


class CausalTruthRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    truth_causal_id: str
    linked_leakage_id: str | None
    linked_finding_id: str | None
    expected_root_cause: str | None


class DataQualityTruthRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    truth_dq_id: str
    dq_family: str | None
    affected_record: str | None
    severity: str | None


class IntegrityIssueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    severity: str
    code: str
    message: str
    document_role: str | None
    truth_ref: str | None


class GroundTruthRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    simulation_id: UUID
    version: int
    checksum: str
    schema_version: str
    adapter_code: str | None
    adapter_version: str | None
    manifest_summary: dict[str, object] | None
    expected_clean_areas: list[str]
    tolerance: dict[str, object]
    uploaded_by_user_id: UUID
    uploaded_at: datetime
    expected_finding_count: int = 0
    leakage_truth_count: int = 0
    causal_truth_count: int = 0
    data_quality_truth_count: int = 0
    integrity_issues: list[IntegrityIssueRead] = Field(default_factory=list)
    expected_findings: list[ExpectedFindingRead] = Field(default_factory=list)


class ValidationSimulationDetail(ValidationSimulationRead):
    ground_truth_versions: list[GroundTruthRead] = Field(default_factory=list)


class ValidationFindingMatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dimension_code: str
    match_type: str
    expected_finding_id: UUID | None
    expected_leakage_truth_id: UUID | None
    actual_finding_id: UUID | None
    severity_match: bool | None
    entity_match: bool | None
    evidence_match: bool | None
    economic_variance_pct: float | None
    matched_dimensions: list[str] | None
    unmatched_dimensions: list[str] | None
    reason: str | None


class ValidationScoreRead(BaseModel):
    """The original finding-detection score shape (section 15 backward
    compatibility). Equivalent detail for every dimension, including this
    one, is also available in `dimensions` on ValidationResultRead."""

    model_config = ConfigDict(from_attributes=True)

    true_positive_count: int
    false_positive_count: int
    false_negative_count: int
    precision: float | None
    recall: float | None
    f1: float | None
    severity_accuracy: float | None
    entity_accuracy: float | None
    evidence_accuracy: float | None
    economic_variance_avg_pct: float | None
    critical_leakage_recall: float | None
    computed_at: datetime


class ValidationDimensionResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dimension_code: str
    status: str
    summary: str | None
    metrics: dict[str, object]
    computed_at: datetime


class SimulationValidationRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    simulation_id: UUID
    ground_truth_id: UUID
    analysis_case_run_id: UUID
    status: str
    triggered_by_user_id: UUID
    started_at: datetime
    completed_at: datetime | None
    error_summary: str | None


class ValidationResultRead(BaseModel):
    run: SimulationValidationRunRead
    score: ValidationScoreRead | None
    dimensions: list[ValidationDimensionResultRead] = Field(default_factory=list)
    matches: list[ValidationFindingMatchRead] = Field(default_factory=list)


class ValidationResultsHistoryRead(BaseModel):
    simulation_id: UUID
    results: list[ValidationResultRead] = Field(default_factory=list)
