from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

ScopeType = Literal["shared_core", "industry", "regional", "organization"]
CanonicalKind = Literal["entity", "event", "metric"]


class CanonicalTypeCreate(BaseModel):
    type_code: str = Field(min_length=2, max_length=150, pattern=r"^[a-z][a-z0-9_]*$")
    display_name: str = Field(min_length=1, max_length=250)
    description: str | None = None
    scope_type: ScopeType
    scope_key: str = Field(min_length=1, max_length=180)
    owner_organization_id: UUID | None = None
    industry_pack_code: str | None = Field(default=None, max_length=100)
    identity_strategy_code: str | None = Field(default=None, max_length=100)
    applicable_entity_type_id: UUID | None = None
    unit_dimension: str | None = Field(default=None, max_length=80)
    default_unit: str | None = Field(default=None, max_length=40)
    aggregation_hint: Literal["sum", "average", "last_value", "max", "min", "count"] | None = None


class CanonicalTypeRead(CanonicalTypeCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class CanonicalFieldCreate(BaseModel):
    canonical_type_kind: CanonicalKind
    canonical_type_id: UUID
    field_code: str = Field(min_length=1, max_length=150, pattern=r"^[a-z][a-z0-9_]*$")
    display_name: str = Field(min_length=1, max_length=250)
    data_type: Literal[
        "string", "integer", "decimal", "boolean", "datetime", "date", "uuid", "enum"
    ]
    is_required: bool = False
    unit_dimension: str | None = Field(default=None, max_length=80)
    allowed_values: list[object] | None = None
    validation_rule: dict[str, object] | None = None


class CanonicalFieldRead(CanonicalFieldCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class MappingTemplateCreate(BaseModel):
    template_code: str = Field(min_length=2, max_length=150, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=250)
    description: str | None = None
    scope_type: ScopeType
    scope_key: str = Field(min_length=1, max_length=180)
    owner_organization_id: UUID | None = None
    industry_pack_code: str | None = Field(default=None, max_length=100)
    source_system_type: str | None = Field(default=None, max_length=100)
    target_canonical_type_kind: CanonicalKind
    target_canonical_type_id: UUID


class MappingTemplateRead(MappingTemplateCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class MappingTemplateVersionCreate(BaseModel):
    semantic_version: str = Field(pattern=r"^\d+\.\d+\.\d+$", max_length=30)
    definition_json: dict[str, object] = Field(default_factory=dict)


class MappingTemplateVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    template_id: UUID
    semantic_version: str
    lifecycle_status: str
    content_hash: str
    definition_json: dict[str, object]
    validated_at: datetime | None
    approved_at: datetime | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class FieldMappingCreate(BaseModel):
    source_field_path: str = Field(min_length=1, max_length=500)
    canonical_field_definition_id: UUID
    sequence: int = Field(default=0, ge=0)
    is_required_for_publication: bool = False
    default_value: object | None = None
    origin_memory_version_id: UUID | None = None


class FieldMappingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    template_version_id: UUID
    source_field_path: str
    canonical_field_definition_id: UUID
    sequence: int
    is_required_for_publication: bool
    default_value: object | None
    origin_memory_version_id: UUID | None
    created_at: datetime
    updated_at: datetime


class MappingTransformationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    field_mapping_id: UUID
    sequence: int
    transformation_type: str
    parameters_json: dict[str, object]
    created_at: datetime
    updated_at: datetime


class FieldMappingConfigurationRead(FieldMappingRead):
    transformations: list[MappingTransformationRead] = Field(default_factory=list)


class MappingTemplateVersionConfigurationRead(MappingTemplateVersionRead):
    template: MappingTemplateRead
    field_mappings: list[FieldMappingConfigurationRead] = Field(default_factory=list)


class TransformationCreate(BaseModel):
    sequence: int = Field(ge=0)
    transformation_type: Literal[
        "type_cast",
        "date_parse",
        "timezone_normalize",
        "unit_convert",
        "currency_normalize",
        "crosswalk_lookup",
        "derive",
        "constant",
        "trim_normalize",
        "custom_function",
    ]
    parameters_json: dict[str, object] = Field(default_factory=dict)


class ValueCrosswalkCreate(BaseModel):
    crosswalk_code: str = Field(min_length=2, max_length=150, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=250)
    canonical_field_definition_id: UUID
    scope_type: ScopeType
    scope_key: str = Field(min_length=1, max_length=180)
    owner_organization_id: UUID | None = None


class ValueCrosswalkEntryCreate(BaseModel):
    source_value: str = Field(max_length=500)
    canonical_target_value: str = Field(max_length=500)
    mapping_confidence_score: Decimal | None = Field(default=None, ge=0, le=1)
    confidence_method_code: str | None = Field(default=None, max_length=100)
    confidence_method_version: str | None = Field(default=None, max_length=30)
    effective_from: datetime | None = None
    effective_to: datetime | None = None

    @field_validator("canonical_target_value")
    @classmethod
    def nonempty_target(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("canonical target value is required")
        return value


class SourceFieldCreate(BaseModel):
    field_path: str = Field(min_length=1, max_length=500)
    inferred_data_type: str = Field(min_length=1, max_length=50)
    sample_values: list[object] | None = None
    null_ratio: Decimal | None = Field(default=None, ge=0, le=1)
    distinct_ratio: Decimal | None = Field(default=None, ge=0, le=1)


class SourceSchemaDiscover(BaseModel):
    dataset_id: UUID
    dataset_version_id: UUID | None = None
    schema_fingerprint: str = Field(min_length=32, max_length=255)
    fields: list[SourceFieldCreate] = Field(default_factory=list)


class SourceSchemaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    dataset_id: UUID
    dataset_version_id: UUID | None
    status: str
    schema_fingerprint: str
    discovered_at: datetime


class FieldMappingSuggestion(BaseModel):
    source_field_path: str
    suggested_canonical_field_definition_id: UUID | None = None
    suggested_canonical_field_code: str | None = None
    confidence_status: Literal["CONFIRMED", "CORRECTED"] | None = None
    last_confirmed_at: datetime | None = None
    matched_context_dimensions: list[str] = Field(default_factory=list)
    memory_id: UUID | None = None
    memory_version_id: UUID | None = None
    evaluated: bool


class FieldMappingSuggestionListRead(BaseModel):
    source_schema_id: UUID
    suggestions: list[FieldMappingSuggestion]


class MappingInputRecord(BaseModel):
    raw_record_reference_id: UUID
    values: dict[str, object]
    source_reported_timestamp: datetime | None = None


class MappingRunCreate(BaseModel):
    dataset_version_id: UUID
    template_version_id: UUID
    source_schema_id: UUID
    idempotency_key: str = Field(min_length=1, max_length=255)
    correlation_id: str | None = Field(default=None, max_length=100)
    records: list[MappingInputRecord] = Field(default_factory=list)


class MappingRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    dataset_version_id: UUID
    template_version_id: UUID
    source_schema_id: UUID | None
    schema_fingerprint_snapshot: str | None
    status: str
    idempotency_key: str
    request_fingerprint: str
    input_count: int
    mapped_count: int
    exception_count: int
    rejected_count: int
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    created_by_user_id: UUID
    correlation_id: str | None
    failure_code: str | None
    failure_message: str | None
    failure_retryable: bool | None
    failed_at: datetime | None
    retry_of_run_id: UUID | None
    root_run_id: UUID | None
    attempt_number: int
    execution_claimed_at: datetime | None
    heartbeat_at: datetime | None


class MappingRunPage(BaseModel):
    items: list[MappingRunRead]
    page: int
    page_size: int
    total: int


class MappingRunRetryCreate(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=255)
    correlation_id: str | None = Field(default=None, max_length=100)


class MappingExceptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    mapping_record_result_id: UUID
    exception_type: str
    status: str
    detail_json: dict[str, object]


class MappingReviewCreate(BaseModel):
    decision: Literal["confirm", "override", "reject", "defer"]
    notes: str | None = None
    override_value: object | None = None


class EntityMatchDecision(BaseModel):
    decision: Literal["accepted", "rejected", "superseded"]


class CanonicalEntityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    entity_type_id: UUID
    canonical_entity_key: str | None
    attributes_json: dict[str, object]
    mapping_confidence_score: Decimal | None
    content_fingerprint: str


class CanonicalEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    canonical_entity_id: UUID
    event_type_id: UUID
    occurrence_start: datetime
    occurrence_end: datetime | None
    occurrence_precision: str
    source_reported_timestamp: datetime | None
    first_detected_at: datetime
    last_detected_at: datetime
    mapping_status: str
    mapping_confidence_score: Decimal | None
    attributes_json: dict[str, object]


class CanonicalMetricRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    canonical_entity_id: UUID
    metric_type_id: UUID
    measured_value: Decimal
    unit: str
    currency: str | None
    occurrence_start: datetime
    occurrence_end: datetime | None
    occurrence_precision: str
    mapping_status: str
    mapping_confidence_score: Decimal | None
    attributes_json: dict[str, object]


class LineagePathRead(BaseModel):
    canonical_target_id: UUID
    node_ids: list[UUID]
    relationship_types: list[str]
