from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FindingType(StrEnum):
    KPI = "kpi"
    LEAKAGE = "leakage"
    EXCEPTION = "exception"
    CONTROL_FAILURE = "control_failure"
    RECONCILIATION = "reconciliation"
    RISK = "risk"
    OPPORTUNITY = "opportunity"
    DATA_QUALITY = "data_quality"


class FindingSeverity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConfidenceLevel(StrEnum):
    UNKNOWN = "unknown"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"


class FindingValueType(StrEnum):
    COUNT = "count"
    INTEGER = "integer"
    DECIMAL = "decimal"
    PERCENTAGE = "percentage"
    RATIO = "ratio"
    DURATION = "duration"
    DISTANCE = "distance"
    VOLUME = "volume"
    MASS = "mass"
    ENERGY = "energy"
    CURRENCY = "currency"
    BOOLEAN = "boolean"
    TEXT_CATEGORY = "text_category"


class FindingStatusValue(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    UNDER_REVIEW = "under_review"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"
    SUPERSEDED = "superseded"
    RESOLVED = "resolved"
    ARCHIVED = "archived"


class EvidenceType(StrEnum):
    EXECUTION = "execution"
    OIKB_DEFINITION = "oikb_definition"
    TRUST_ASSESSMENT = "trust_assessment"
    READINESS_DECISION = "readiness_decision"
    DATASET = "dataset"
    INGESTION_BATCH = "ingestion_batch"
    SOURCE_SYSTEM = "source_system"
    LINEAGE = "lineage"
    AFFECTED_RECORD = "affected_record"
    CALCULATION_TRACE = "calculation_trace"
    RULE_TRACE = "rule_trace"
    COMPARISON_PERIOD = "comparison_period"
    BENCHMARK = "benchmark"
    DOCUMENT_REFERENCE = "document_reference"
    HUMAN_VERIFICATION = "human_verification"


class ReviewDecision(StrEnum):
    CONFIRM = "confirm"
    DISMISS = "dismiss"
    REQUEST_MORE_EVIDENCE = "request_more_evidence"
    RETURN_TO_DRAFT = "return_to_draft"
    MARK_SUPERSEDED = "mark_superseded"


def _currency(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.upper()
    if len(normalized) != 3 or not normalized.isascii() or not normalized.isalpha():
        raise ValueError("Currency must contain three ASCII letters")
    return normalized


class EvidenceItemCreate(BaseModel):
    evidence_type: EvidenceType
    reference_type: str = Field(min_length=1, max_length=50)
    reference_id: str | None = Field(default=None, max_length=255)
    reference_uri: str | None = Field(default=None, max_length=500)
    reference_fingerprint: str | None = Field(default=None, max_length=128)
    label: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    source_system_id: UUID | None = None
    ingestion_batch_id: UUID | None = None
    dataset_id: UUID | None = None
    lineage_node_id: UUID | None = None
    raw_record_reference_id: UUID | None = None
    canonical_entity: str | None = Field(default=None, max_length=100)
    canonical_record_reference: str | None = Field(default=None, max_length=255)
    field_reference: str | None = Field(default=None, max_length=150)
    comparison_value: Decimal | None = None
    comparison_unit: str | None = Field(default=None, max_length=50)
    comparison_currency: str | None = None
    metadata: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict,
        max_length=20,
    )

    @field_validator("comparison_currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return _currency(value)

    @model_validator(mode="after")
    def require_reference(self) -> "EvidenceItemCreate":
        if not any(
            (
                self.reference_id,
                self.reference_uri,
                self.canonical_record_reference,
                self.source_system_id,
                self.ingestion_batch_id,
                self.dataset_id,
                self.lineage_node_id,
                self.raw_record_reference_id,
            )
        ):
            raise ValueError("Evidence must contain a governed reference")
        return self


class CalculationTraceCreate(BaseModel):
    engine_version: str = Field(default="1.0", min_length=1, max_length=30)
    operation_code: str = Field(min_length=1, max_length=100)
    input_reference_summary: dict[str, str | int | bool | None] = Field(
        default_factory=dict,
        max_length=20,
    )
    parameter_summary: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict,
        max_length=20,
    )
    warnings: list[str] = Field(default_factory=list, max_length=20)


class RuleTraceCreate(BaseModel):
    condition_code: str = Field(min_length=1, max_length=100)
    evaluation_result: bool
    operand_reference_summary: dict[str, str | int | bool | None] = Field(
        default_factory=dict,
        max_length=20,
    )
    comparison_operator: str = Field(min_length=1, max_length=50)
    threshold_summary: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict,
        max_length=20,
    )
    warnings: list[str] = Field(default_factory=list, max_length=20)


class CandidateFindingCreate(BaseModel):
    execution_id: UUID
    result_id: UUID
    finding_type: FindingType
    title: str = Field(min_length=1, max_length=250)
    summary: str = Field(min_length=1, max_length=2000)
    description: str | None = Field(default=None, max_length=5000)
    domain_code: str = Field(min_length=1, max_length=100)
    process_code: str | None = Field(default=None, max_length=100)
    industry_pack_code: str | None = Field(default=None, max_length=100)
    measured_value: Decimal
    measured_value_type: FindingValueType
    measured_unit: str | None = Field(default=None, max_length=50)
    measured_currency: str | None = None
    exposure_value: Decimal | None = None
    exposure_value_type: FindingValueType | None = None
    exposure_currency: str | None = None
    severity: FindingSeverity
    severity_reason: dict[str, str | int | float | bool | None] = Field(max_length=20)
    confidence_level: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    confidence_score: Decimal | None = Field(default=None, ge=0, le=1)
    confidence_method_code: str | None = Field(default=None, max_length=100)
    confidence_method_version: str | None = Field(default=None, max_length=30)
    confidence_components: dict[str, str | int | float | bool | None] | None = Field(
        default=None,
        max_length=20,
    )
    confidence_interpretation: str | None = Field(default=None, max_length=1000)
    confidence_limitations: list[str] = Field(default_factory=list, max_length=20)
    affected_record_count: int = Field(default=0, ge=0)
    occurrence_start: datetime | None = None
    occurrence_end: datetime | None = None
    dataset_reference: str = Field(min_length=1, max_length=255)
    evidence_policy_code: str = Field(min_length=1, max_length=100)
    evidence_policy_version: str = Field(min_length=1, max_length=30)
    evidence: list[EvidenceItemCreate] = Field(default_factory=list, max_length=200)
    calculation_traces: list[CalculationTraceCreate] = Field(
        default_factory=list,
        max_length=20,
    )
    rule_traces: list[RuleTraceCreate] = Field(default_factory=list, max_length=20)
    warnings: list[str] = Field(default_factory=list, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("measured_currency", "exposure_currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return _currency(value)

    @field_validator("occurrence_start", "occurrence_end")
    @classmethod
    def aware_datetime(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("Datetime must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_contract(self) -> "CandidateFindingCreate":
        if self.execution_id != self.result_id:
            raise ValueError("WP-2.07 result_id must equal execution_id")
        if self.occurrence_start and self.occurrence_end:
            if self.occurrence_start > self.occurrence_end:
                raise ValueError("Occurrence start must not exceed end")
        if self.measured_value_type == FindingValueType.CURRENCY:
            if self.measured_currency is None:
                raise ValueError("Measured currency is required for currency values")
        elif self.measured_currency is not None:
            raise ValueError("Measured currency is only valid for currency values")
        if self.exposure_value is None:
            if self.exposure_value_type is not None or self.exposure_currency is not None:
                raise ValueError("Exposure metadata requires an exposure value")
        else:
            if self.exposure_value_type is None:
                raise ValueError("Exposure value type is required")
            if self.exposure_value_type == FindingValueType.CURRENCY:
                if self.exposure_currency is None:
                    raise ValueError("Exposure currency is required")
            elif self.exposure_currency is not None:
                raise ValueError("Exposure currency is only valid for currency exposure")
        if self.confidence_score is not None:
            required = (
                self.confidence_method_code,
                self.confidence_method_version,
                self.confidence_components,
                self.confidence_interpretation,
            )
            if not all(required):
                raise ValueError("Numeric confidence requires complete methodology metadata")
        if not self.calculation_traces and not self.rule_traces:
            raise ValueError("At least one calculation or rule trace is required")
        if self.finding_type == FindingType.LEAKAGE:
            if self.exposure_value is None or self.affected_record_count == 0:
                raise ValueError("Leakage findings require exposure and affected records")
            if not any(
                item.evidence_type == EvidenceType.AFFECTED_RECORD for item in self.evidence
            ):
                raise ValueError("Leakage findings require affected-record evidence")
            if not self.warnings and not self.limitations:
                raise ValueError("Leakage findings require warnings or limitations")
        return self


class FindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    finding_code: str
    finding_type: FindingType
    title: str
    summary: str
    description: str | None
    domain_code: str
    process_code: str | None
    industry_pack_code: str | None
    status: FindingStatusValue
    severity: FindingSeverity
    severity_reason: dict[str, object]
    confidence_level: ConfidenceLevel
    confidence_score: Decimal | None
    measured_value: Decimal
    measured_value_type: FindingValueType
    measured_unit: str | None
    measured_currency: str | None
    exposure_value: Decimal | None
    exposure_value_type: FindingValueType | None
    exposure_currency: str | None
    affected_record_count: int
    occurrence_start: datetime | None
    occurrence_end: datetime | None
    detected_at: datetime
    published_at: datetime | None
    superseded_by_finding_id: UUID | None
    source_execution_id: UUID
    source_result_id: UUID
    definition_code: str
    definition_version: str
    trust_assessment_id: UUID
    analytical_readiness_id: UUID
    dataset_id: UUID
    dataset_reference: str
    warnings: list[str]
    limitations: list[str]
    content_fingerprint: str
    created_at: datetime
    updated_at: datetime | None


class FindingPage(BaseModel):
    items: list[FindingRead]
    page: int
    page_size: int
    total: int


class EvidenceBundleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    finding_id: UUID
    bundle_version: int
    evidence_policy_code: str
    evidence_policy_version: str
    status: str
    completeness_status: str
    content_hash: str
    finalized_at: datetime | None


class EvidenceItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    evidence_bundle_id: UUID
    evidence_type: EvidenceType
    reference_type: str
    reference_id: str | None
    reference_uri: str | None
    reference_fingerprint: str | None
    label: str
    description: str | None
    sequence_number: int
    metadata_json: dict[str, object]


class EvidenceResponse(BaseModel):
    bundle: EvidenceBundleRead
    items: list[EvidenceItemRead]


class CalculationTraceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    finding_id: UUID
    execution_id: UUID
    definition_code: str
    definition_version: str
    engine_version: str
    operation_code: str
    sequence_number: int
    input_reference_summary: dict[str, object]
    parameter_summary: dict[str, object]
    output_value: Decimal | None
    output_type: str
    output_unit: str | None
    output_currency: str | None
    warnings: list[str]
    content_hash: str


class RuleTraceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    finding_id: UUID
    execution_id: UUID
    rule_code: str
    rule_version: str
    condition_code: str
    sequence_number: int
    evaluation_result: bool
    operand_reference_summary: dict[str, object]
    comparison_operator: str
    threshold_summary: dict[str, object]
    warnings: list[str]
    content_hash: str


class ReviewCreate(BaseModel):
    decision: ReviewDecision
    reason_code: str = Field(min_length=1, max_length=100)
    comments: str | None = Field(default=None, max_length=2000)
    superseding_finding_id: UUID | None = None


class ReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    finding_id: UUID
    review_status: str
    decision: ReviewDecision
    reviewer_user_id: UUID
    reviewer_role: str
    reason_code: str
    comments: str | None
    reviewed_at: datetime
    created_at: datetime


class LifecycleCommand(BaseModel):
    reason_code: str = Field(min_length=1, max_length=100)
    superseding_finding_id: UUID | None = None


class StatusHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    finding_id: UUID
    previous_status: str | None
    new_status: str
    reason_code: str
    changed_by_user_id: UUID
    changed_at: datetime
    metadata_json: dict[str, object]
