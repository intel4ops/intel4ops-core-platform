from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MemoryCategory = Literal["FIELD_MAPPING", "SCHEMA_PATTERN", "TERMINOLOGY"]
MemoryStatus = Literal["OBSERVED", "CONFIRMED", "CORRECTED", "AMBIGUOUS", "REJECTED", "DEPRECATED"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FieldMappingPayload(StrictModel):
    source_field_path: str = Field(min_length=1, max_length=500)
    source_field_type: str = Field(min_length=1, max_length=100)
    canonical_type_kind: Literal["entity", "event", "metric"]
    canonical_type_id: UUID
    canonical_field_definition_id: UUID
    canonical_field_code: str = Field(min_length=1, max_length=150)
    schema_fingerprint: str = Field(min_length=1, max_length=255)
    mapping_transform_code: str | None = Field(default=None, max_length=100)
    unit_context: str | None = Field(default=None, max_length=80)


class RecognizedFieldSignature(StrictModel):
    field_name_normalized: str = Field(min_length=1, max_length=500)
    source_type: str = Field(min_length=1, max_length=100)
    canonical_field_definition_id: UUID | None = None


class SchemaPatternPayload(StrictModel):
    schema_fingerprint: str = Field(min_length=1, max_length=255)
    canonical_domain: str = Field(min_length=1, max_length=100)
    recognized_field_signatures: list[RecognizedFieldSignature] = Field(min_length=1, max_length=50)
    source_system_family: str | None = Field(default=None, max_length=100)
    source_entity: str | None = Field(default=None, max_length=500)


class TerminologyPayload(StrictModel):
    term_normalized: str = Field(min_length=1, max_length=500)
    concept_kind: Literal["entity", "event", "metric", "field"]
    concept_code: str = Field(min_length=1, max_length=150)
    canonical_domain: str = Field(min_length=1, max_length=100)
    context_qualifiers: list[str] = Field(default_factory=list, max_length=10)


class MemoryContext(StrictModel):
    schema_fingerprint: str | None = Field(default=None, max_length=255)
    source_table_or_entity_context: str | None = Field(default=None, max_length=500)
    neighboring_field_signatures: list[str] = Field(default_factory=list, max_length=20)


class MemoryProvenance(StrictModel):
    source_schema_id: UUID | None = None
    mapping_record_result_id: UUID | None = None
    mapping_review_id: UUID | None = None
    mapping_template_version_id: UUID | None = None
    canonical_field_definition_ids: list[UUID] = Field(default_factory=list, max_length=50)
    source_content_hashes: list[str] = Field(default_factory=list, max_length=20)
    raw_data_included: Literal[False] = False


class MemoryCandidateCreate(StrictModel):
    idempotency_key: str = Field(min_length=1, max_length=255)
    category: MemoryCategory
    subject_kind: Literal["SOURCE_FIELD", "SOURCE_SCHEMA", "TERM"]
    subject: str = Field(min_length=1, max_length=500)
    source_system_family: str | None = Field(default=None, max_length=100)
    canonical_domain: str | None = Field(default=None, max_length=100)
    context: MemoryContext = Field(default_factory=MemoryContext)
    value_payload: dict[str, object]
    provenance: MemoryProvenance
    source_fingerprint: str = Field(min_length=64, max_length=64)
    security_classification: Literal["TENANT_INTERNAL", "TENANT_SENSITIVE"] = "TENANT_INTERNAL"
    valid_to: datetime | None = None


class MemoryDecisionRequest(StrictModel):
    idempotency_key: str = Field(min_length=1, max_length=255)
    expected_current_version: int = Field(ge=1)
    action: Literal["CONFIRM", "CORRECT", "REJECT", "DEPRECATE"]
    corrected_payload: dict[str, object] | None = None
    decision_reason_code: str | None = Field(
        default=None, min_length=1, max_length=60, pattern=r"^[A-Z][A-Z0-9_]*$"
    )
    correlation_id: str | None = Field(default=None, max_length=100)


class MemoryRetrieveRequest(StrictModel):
    idempotency_key: str = Field(min_length=1, max_length=255)
    category: MemoryCategory
    subject_kind: Literal["SOURCE_FIELD", "SOURCE_SCHEMA", "TERM"]
    subject: str = Field(min_length=1, max_length=500)
    source_system_family: str | None = Field(default=None, max_length=100)
    canonical_domain: str | None = Field(default=None, max_length=100)
    context: MemoryContext = Field(default_factory=MemoryContext)
    max_suggestions: int = Field(default=5, ge=1, le=5)
    correlation_id: str | None = Field(default=None, max_length=100)


class MemoryVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version_number: int
    status: str
    assertion_kind: str
    value_payload: dict[str, object]
    source_schema_id: UUID | None
    mapping_record_result_id: UUID | None
    provenance_snapshot: dict[str, object]
    confidence_label: str | None
    actor_role: str
    effective_from: datetime
    effective_to: datetime | None
    content_hash: str
    created_at: datetime


class MemoryItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    category: str
    subject_kind: str
    normalized_subject: str
    source_system_family: str | None
    canonical_domain: str | None
    context_signature: str
    current_version_number: int
    current_status: str
    support_count: int
    contradiction_count: int
    confirmation_count: int
    rejection_count: int
    is_stale: bool
    stale_reason_code: str | None
    last_confirmed_at: datetime | None
    last_validated_at: datetime | None
    valid_from: datetime
    valid_to: datetime | None
    security_classification: str
    retention_until: datetime | None
    created_at: datetime
    updated_at: datetime


class MemoryDetailRead(StrictModel):
    item: MemoryItemRead
    current_version: MemoryVersionRead


class MemoryListRead(StrictModel):
    items: list[MemoryItemRead]
    next_cursor: str | None


class MemorySuggestionRead(StrictModel):
    memory_id: UUID
    version_id: UUID
    category: str
    status: str
    normalized_subject: str
    matched_context_dimensions: list[str]
    match_reasons: list[str]
    last_confirmed_at: datetime | None
    last_validated_at: datetime | None
    actor_class: str
    stale: bool
    ambiguous: bool
    provenance_references: dict[str, object]
    interpreted_payload: dict[str, object]
    rank: int


class MemoryRetrieveRead(StrictModel):
    request_fingerprint: str
    evaluated_count: int
    suggestions: list[MemorySuggestionRead]
