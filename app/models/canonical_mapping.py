from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
    inspect,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.entities import utc_now
from app.models.ingestion import SchemaStatus
from app.models.source_system import enum_values, portable_json


class GovernanceScope(StrEnum):
    SHARED_CORE = "shared_core"
    INDUSTRY = "industry"
    REGIONAL = "regional"
    ORGANIZATION = "organization"


class CanonicalTypeKind(StrEnum):
    ENTITY = "entity"
    EVENT = "event"
    METRIC = "metric"


class CanonicalDataType(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    DATE = "date"
    UUID = "uuid"
    ENUM = "enum"


class AggregationHint(StrEnum):
    SUM = "sum"
    AVERAGE = "average"
    LAST_VALUE = "last_value"
    MAX = "max"
    MIN = "min"
    COUNT = "count"


class MappingLifecycleStatus(StrEnum):
    DRAFT = "draft"
    CANDIDATE = "candidate"
    VALIDATED = "validated"
    APPROVED = "approved"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


class TransformationType(StrEnum):
    TYPE_CAST = "type_cast"
    DATE_PARSE = "date_parse"
    TIMEZONE_NORMALIZE = "timezone_normalize"
    UNIT_CONVERT = "unit_convert"
    CURRENCY_NORMALIZE = "currency_normalize"
    CROSSWALK_LOOKUP = "crosswalk_lookup"
    DERIVE = "derive"
    CONSTANT = "constant"
    TRIM_NORMALIZE = "trim_normalize"
    CUSTOM_FUNCTION = "custom_function"


class CrosswalkEntryStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


class EntityMatchMethod(StrEnum):
    EXACT_IDENTIFIER = "exact_identifier"
    NORMALIZED_IDENTIFIER = "normalized_identifier"
    DETERMINISTIC_COMPOSITE = "deterministic_composite"
    FUZZY_CANDIDATE = "fuzzy_candidate"


class MappingRunStatus(StrEnum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MappingRecordStatus(StrEnum):
    MAPPED = "mapped"
    HUMAN_CONFIRMED = "human_confirmed"
    UNRESOLVED = "unresolved"
    AMBIGUOUS = "ambiguous"
    CONFLICTING = "conflicting"
    MISSING_REQUIRED_FIELD = "missing_required_field"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class MappingExceptionType(StrEnum):
    UNRESOLVED_FIELD = "unresolved_field"
    AMBIGUOUS_ENTITY = "ambiguous_entity"
    CONFLICTING_MAPPING = "conflicting_mapping"
    MISSING_REQUIRED_FIELD = "missing_required_field"
    TRANSFORMATION_FAILURE = "transformation_failure"
    CROSSWALK_MISS = "crosswalk_miss"
    VALIDATION_FAILURE = "validation_failure"


class MappingExceptionStatus(StrEnum):
    OPEN = "open"
    UNDER_REVIEW = "under_review"
    RESOLVED = "resolved"
    WONT_FIX = "wont_fix"


class MappingReviewDecision(StrEnum):
    CONFIRM = "confirm"
    OVERRIDE = "override"
    REJECT = "reject"
    DEFER = "defer"


class OccurrencePrecision(StrEnum):
    INSTANT = "instant"
    SECOND = "second"
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"
    PERIOD = "period"


class MatchCandidateStatus(StrEnum):
    CANDIDATE = "candidate"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class GovernedScopeMixin:
    owner_organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True
    )
    scope_type: Mapped[str] = mapped_column(String(30))
    scope_key: Mapped[str] = mapped_column(String(180))


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class MappingConfidenceMixin:
    mapping_confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    confidence_method_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confidence_method_version: Mapped[str | None] = mapped_column(String(30), nullable=True)
    confidence_components: Mapped[dict[str, object] | None] = mapped_column(
        portable_json, nullable=True
    )
    confidence_interpretation: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_limitations: Mapped[str | None] = mapped_column(Text, nullable=True)


SCOPE_CHECK = (
    "scope_type IN ('shared_core','industry','regional','organization') "
    "AND ((scope_type = 'organization' AND owner_organization_id IS NOT NULL) "
    "OR (scope_type <> 'organization'))"
)
CONFIDENCE_CHECK = (
    "mapping_confidence_score IS NULL OR "
    "(mapping_confidence_score >= 0 AND mapping_confidence_score <= 1)"
)


class CanonicalEntityType(GovernedScopeMixin, TimestampMixin, Base):
    __tablename__ = "canonical_entity_types"
    __table_args__ = (
        UniqueConstraint("type_code", "scope_key", name="uq_canonical_entity_type_scope"),
        CheckConstraint(SCOPE_CHECK, name="ck_canonical_entity_type_scope"),
        Index("ix_canonical_entity_type_code", "type_code"),
        Index("ix_canonical_entity_type_owner", "owner_organization_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    type_code: Mapped[str] = mapped_column(String(150))
    display_name: Mapped[str] = mapped_column(String(250))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    industry_pack_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    identity_strategy_code: Mapped[str | None] = mapped_column(String(100), nullable=True)


class CanonicalEventType(GovernedScopeMixin, TimestampMixin, Base):
    __tablename__ = "canonical_event_types"
    __table_args__ = (
        UniqueConstraint("type_code", "scope_key", name="uq_canonical_event_type_scope"),
        CheckConstraint(SCOPE_CHECK, name="ck_canonical_event_type_scope"),
        Index("ix_canonical_event_type_code", "type_code"),
        Index("ix_canonical_event_type_owner", "owner_organization_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    type_code: Mapped[str] = mapped_column(String(150))
    display_name: Mapped[str] = mapped_column(String(250))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    industry_pack_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    applicable_entity_type_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("canonical_entity_types.id", ondelete="RESTRICT"), nullable=True
    )


class CanonicalMetricType(GovernedScopeMixin, TimestampMixin, Base):
    __tablename__ = "canonical_metric_types"
    __table_args__ = (
        UniqueConstraint("type_code", "scope_key", name="uq_canonical_metric_type_scope"),
        CheckConstraint(SCOPE_CHECK, name="ck_canonical_metric_type_scope"),
        CheckConstraint(
            f"aggregation_hint IN ({enum_values(AggregationHint)})",
            name="ck_canonical_metric_type_aggregation",
        ),
        Index("ix_canonical_metric_type_code", "type_code"),
        Index("ix_canonical_metric_type_owner", "owner_organization_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    type_code: Mapped[str] = mapped_column(String(150))
    display_name: Mapped[str] = mapped_column(String(250))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    industry_pack_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    unit_dimension: Mapped[str | None] = mapped_column(String(80), nullable=True)
    default_unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    aggregation_hint: Mapped[str] = mapped_column(String(30))


class CanonicalFieldDefinition(TimestampMixin, Base):
    __tablename__ = "canonical_field_definitions"
    __table_args__ = (
        UniqueConstraint(
            "canonical_type_kind",
            "canonical_type_id",
            "field_code",
            name="uq_canonical_field_type_code",
        ),
        CheckConstraint(
            f"canonical_type_kind IN ({enum_values(CanonicalTypeKind)})",
            name="ck_canonical_field_type_kind",
        ),
        CheckConstraint(
            f"data_type IN ({enum_values(CanonicalDataType)})",
            name="ck_canonical_field_data_type",
        ),
        Index(
            "ix_canonical_field_type",
            "canonical_type_kind",
            "canonical_type_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    canonical_type_kind: Mapped[str] = mapped_column(String(20))
    canonical_type_id: Mapped[UUID] = mapped_column(Uuid)
    field_code: Mapped[str] = mapped_column(String(150))
    display_name: Mapped[str] = mapped_column(String(250))
    data_type: Mapped[str] = mapped_column(String(30))
    is_required: Mapped[bool] = mapped_column(Boolean, default=False)
    unit_dimension: Mapped[str | None] = mapped_column(String(80), nullable=True)
    allowed_values: Mapped[list[object] | None] = mapped_column(portable_json, nullable=True)
    validation_rule: Mapped[dict[str, object] | None] = mapped_column(portable_json, nullable=True)


class MappingTemplate(GovernedScopeMixin, TimestampMixin, Base):
    __tablename__ = "mapping_templates"
    __table_args__ = (
        UniqueConstraint("template_code", "scope_key", name="uq_mapping_template_scope"),
        CheckConstraint(SCOPE_CHECK, name="ck_mapping_template_scope"),
        CheckConstraint(
            f"target_canonical_type_kind IN ({enum_values(CanonicalTypeKind)})",
            name="ck_mapping_template_target_kind",
        ),
        Index("ix_mapping_template_code", "template_code"),
        Index("ix_mapping_template_owner", "owner_organization_id"),
        Index("ix_mapping_template_industry", "industry_pack_code"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    template_code: Mapped[str] = mapped_column(String(150))
    name: Mapped[str] = mapped_column(String(250))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    industry_pack_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_system_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    target_canonical_type_kind: Mapped[str] = mapped_column(String(20))
    target_canonical_type_id: Mapped[UUID] = mapped_column(Uuid)


class MappingTemplateVersion(TimestampMixin, Base):
    __tablename__ = "mapping_template_versions"
    __table_args__ = (
        UniqueConstraint(
            "template_id",
            "semantic_version",
            name="uq_mapping_template_semantic_version",
        ),
        UniqueConstraint("template_id", "content_hash", name="uq_mapping_template_content_hash"),
        CheckConstraint(
            f"lifecycle_status IN ({enum_values(MappingLifecycleStatus)})",
            name="ck_mapping_template_version_lifecycle",
        ),
        Index("ix_mapping_template_version_template", "template_id"),
        Index(
            "uq_mapping_template_one_published_version",
            "template_id",
            unique=True,
            postgresql_where=text("lifecycle_status = 'published'"),
            sqlite_where=text("lifecycle_status = 'published'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    template_id: Mapped[UUID] = mapped_column(
        ForeignKey("mapping_templates.id", ondelete="CASCADE")
    )
    semantic_version: Mapped[str] = mapped_column(String(30))
    lifecycle_status: Mapped[str] = mapped_column(
        String(30), default=MappingLifecycleStatus.DRAFT.value
    )
    content_hash: Mapped[str] = mapped_column(String(64))
    definition_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)


class FieldMapping(TimestampMixin, Base):
    __tablename__ = "field_mappings"
    __table_args__ = (
        UniqueConstraint(
            "template_version_id",
            "sequence",
            name="uq_field_mapping_version_sequence",
        ),
        UniqueConstraint(
            "template_version_id",
            "source_field_path",
            "canonical_field_definition_id",
            name="uq_field_mapping_source_target",
        ),
        CheckConstraint("sequence >= 0", name="ck_field_mapping_sequence"),
        Index("ix_field_mapping_version", "template_version_id"),
        Index("ix_field_mapping_canonical_field", "canonical_field_definition_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    template_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("mapping_template_versions.id", ondelete="CASCADE")
    )
    source_field_path: Mapped[str] = mapped_column(String(500))
    canonical_field_definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("canonical_field_definitions.id", ondelete="RESTRICT")
    )
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    is_required_for_publication: Mapped[bool] = mapped_column(Boolean, default=False)
    default_value: Mapped[object | None] = mapped_column(portable_json, nullable=True)
    origin_memory_version_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)


class MappingTransformation(TimestampMixin, Base):
    __tablename__ = "mapping_transformations"
    __table_args__ = (
        UniqueConstraint(
            "field_mapping_id",
            "sequence",
            name="uq_mapping_transformation_sequence",
        ),
        CheckConstraint("sequence >= 0", name="ck_mapping_transformation_sequence"),
        CheckConstraint(
            f"transformation_type IN ({enum_values(TransformationType)})",
            name="ck_mapping_transformation_type",
        ),
        Index("ix_mapping_transformation_field", "field_mapping_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    field_mapping_id: Mapped[UUID] = mapped_column(
        ForeignKey("field_mappings.id", ondelete="CASCADE")
    )
    sequence: Mapped[int] = mapped_column(Integer)
    transformation_type: Mapped[str] = mapped_column(String(40))
    parameters_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)


class ValueCrosswalk(GovernedScopeMixin, TimestampMixin, Base):
    __tablename__ = "value_crosswalks"
    __table_args__ = (
        UniqueConstraint("crosswalk_code", "scope_key", name="uq_value_crosswalk_scope"),
        UniqueConstraint(
            "owner_organization_id",
            "id",
            name="uq_value_crosswalk_owner_id",
        ),
        CheckConstraint(SCOPE_CHECK, name="ck_value_crosswalk_scope"),
        Index("ix_value_crosswalk_code", "crosswalk_code"),
        Index("ix_value_crosswalk_owner", "owner_organization_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    crosswalk_code: Mapped[str] = mapped_column(String(150))
    name: Mapped[str] = mapped_column(String(250))
    canonical_field_definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("canonical_field_definitions.id", ondelete="RESTRICT")
    )
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)


class ValueCrosswalkEntry(MappingConfidenceMixin, TimestampMixin, Base):
    __tablename__ = "value_crosswalk_entries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_organization_id", "crosswalk_id"],
            ["value_crosswalks.owner_organization_id", "value_crosswalks.id"],
            name="fk_value_crosswalk_entry_owner_crosswalk",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["owner_organization_id", "supersedes_entry_id"],
            [
                "value_crosswalk_entries.owner_organization_id",
                "value_crosswalk_entries.id",
            ],
            name="fk_value_crosswalk_entry_owner_supersedes",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "owner_organization_id",
            "id",
            name="uq_value_crosswalk_entries_owner_id",
        ),
        UniqueConstraint(
            "crosswalk_id",
            "normalized_source_value",
            "effective_from",
            name="uq_value_crosswalk_entry_effective_source",
        ),
        CheckConstraint(
            f"status IN ({enum_values(CrosswalkEntryStatus)})",
            name="ck_value_crosswalk_entry_status",
        ),
        CheckConstraint(CONFIDENCE_CHECK, name="ck_value_crosswalk_entry_confidence"),
        CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to > effective_from",
            name="ck_value_crosswalk_entry_effective_dates",
        ),
        Index(
            "ix_value_crosswalk_entry_owner_crosswalk",
            "owner_organization_id",
            "crosswalk_id",
        ),
        Index(
            "ix_value_crosswalk_entry_lookup",
            "crosswalk_id",
            "normalized_source_value",
            "status",
        ),
        Index(
            "ix_value_crosswalk_entry_owner_supersedes",
            "owner_organization_id",
            "supersedes_entry_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True
    )
    crosswalk_id: Mapped[UUID] = mapped_column(
        ForeignKey("value_crosswalks.id", ondelete="CASCADE")
    )
    source_value: Mapped[str] = mapped_column(String(500))
    normalized_source_value: Mapped[str] = mapped_column(String(500))
    canonical_target_value: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(30), default=CrosswalkEntryStatus.DRAFT.value)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    supersedes_entry_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("value_crosswalk_entries.id", ondelete="RESTRICT"), nullable=True
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EntityMatchRule(TimestampMixin, Base):
    __tablename__ = "entity_match_rules"
    __table_args__ = (
        UniqueConstraint("entity_type_id", "rule_code", name="uq_entity_match_rule_code"),
        CheckConstraint(
            f"match_method IN ({enum_values(EntityMatchMethod)})",
            name="ck_entity_match_rule_method",
        ),
        CheckConstraint(
            "confidence_weight >= 0 AND confidence_weight <= 1",
            name="ck_entity_match_rule_weight",
        ),
        Index("ix_entity_match_rule_entity_type", "entity_type_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    entity_type_id: Mapped[UUID] = mapped_column(
        ForeignKey("canonical_entity_types.id", ondelete="CASCADE")
    )
    rule_code: Mapped[str] = mapped_column(String(150))
    match_method: Mapped[str] = mapped_column(String(40))
    match_fields: Mapped[list[str]] = mapped_column(portable_json, default=list)
    confidence_weight: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    normalization_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)


class SourceSchema(TimestampMixin, Base):
    __tablename__ = "source_schemas"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "dataset_id"],
            ["datasets.organization_id", "datasets.id"],
            name="fk_source_schemas_org_dataset",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "dataset_version_id"],
            ["dataset_versions.organization_id", "dataset_versions.id"],
            name="fk_source_schemas_org_dataset_version",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id", name="uq_source_schemas_org_id"),
        UniqueConstraint(
            "organization_id",
            "dataset_id",
            "schema_fingerprint",
            name="uq_source_schema_fingerprint",
        ),
        CheckConstraint(
            f"status IN ({enum_values(SchemaStatus)})",
            name="ck_source_schema_status",
        ),
        Index("ix_source_schema_org_dataset", "organization_id", "dataset_id"),
        Index(
            "ix_source_schema_org_dataset_version",
            "organization_id",
            "dataset_version_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    dataset_id: Mapped[UUID] = mapped_column(Uuid)
    dataset_version_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default=SchemaStatus.DISCOVERED.value)
    schema_fingerprint: Mapped[str] = mapped_column(String(255))
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    discovery_method: Mapped[str] = mapped_column(String(80), default="automated")


class SourceField(TimestampMixin, Base):
    __tablename__ = "source_fields"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "source_schema_id"],
            ["source_schemas.organization_id", "source_schemas.id"],
            name="fk_source_fields_org_source_schema",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "source_schema_id",
            "field_path",
            name="uq_source_field_path",
        ),
        CheckConstraint(
            "null_ratio IS NULL OR (null_ratio >= 0 AND null_ratio <= 1)",
            name="ck_source_field_null_ratio",
        ),
        CheckConstraint(
            "distinct_ratio IS NULL OR (distinct_ratio >= 0 AND distinct_ratio <= 1)",
            name="ck_source_field_distinct_ratio",
        ),
        Index("ix_source_field_org_schema", "organization_id", "source_schema_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    source_schema_id: Mapped[UUID] = mapped_column(Uuid)
    field_path: Mapped[str] = mapped_column(String(500))
    inferred_data_type: Mapped[str] = mapped_column(String(50))
    sample_values: Mapped[list[object] | None] = mapped_column(portable_json, nullable=True)
    null_ratio: Mapped[Decimal | None] = mapped_column(Numeric(7, 6), nullable=True)
    distinct_ratio: Mapped[Decimal | None] = mapped_column(Numeric(7, 6), nullable=True)


class MappingRun(TimestampMixin, Base):
    __tablename__ = "mapping_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "dataset_version_id"],
            ["dataset_versions.organization_id", "dataset_versions.id"],
            name="fk_mapping_runs_org_dataset_version",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "source_schema_id"],
            ["source_schemas.organization_id", "source_schemas.id"],
            name="fk_mapping_runs_org_source_schema",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id", name="uq_mapping_runs_org_id"),
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_mapping_run_idempotency_key",
        ),
        CheckConstraint(
            f"status IN ({enum_values(MappingRunStatus)})",
            name="ck_mapping_run_status",
        ),
        CheckConstraint(
            "input_count >= 0 AND mapped_count >= 0 AND exception_count >= 0 "
            "AND rejected_count >= 0",
            name="ck_mapping_run_counts",
        ),
        Index(
            "ix_mapping_run_org_dataset_version",
            "organization_id",
            "dataset_version_id",
        ),
        Index("ix_mapping_run_template_version", "template_version_id"),
        Index("ix_mapping_run_org_created", "organization_id", "created_at"),
        Index("ix_mapping_run_dispatch_fifo", "status", "created_at", "id"),
        Index("ix_mapping_run_stale_heartbeat", "status", "heartbeat_at"),
        Index("ix_mapping_run_retry_root", "organization_id", "root_run_id", "attempt_number"),
        UniqueConstraint("organization_id", "retry_of_run_id", name="uq_mapping_run_retry_child"),
        ForeignKeyConstraint(
            ["organization_id", "retry_of_run_id"],
            ["mapping_runs.organization_id", "mapping_runs.id"],
            name="fk_mapping_run_retry_same_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "root_run_id"],
            ["mapping_runs.organization_id", "mapping_runs.id"],
            name="fk_mapping_run_root_same_org",
        ),
        CheckConstraint("attempt_number >= 1", name="ck_mapping_run_attempt_number"),
        Index(
            "ix_mapping_runs_org_source_schema",
            "organization_id",
            "source_schema_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    dataset_version_id: Mapped[UUID] = mapped_column(Uuid)
    template_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("mapping_template_versions.id", ondelete="RESTRICT")
    )
    source_schema_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    schema_fingerprint_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default=MappingRunStatus.CREATED.value)
    idempotency_key: Mapped[str] = mapped_column(String(255))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    correlation_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    input_count: Mapped[int] = mapped_column(Integer, default=0)
    mapped_count: Mapped[int] = mapped_column(Integer, default=0)
    exception_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_retryable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_of_run_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    root_run_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    execution_claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_lease_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    execution_worker_id: Mapped[str | None] = mapped_column(String(200), nullable=True)


class MappingRunInput(TimestampMixin, Base):
    __tablename__ = "mapping_run_inputs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "mapping_run_id"],
            ["mapping_runs.organization_id", "mapping_runs.id"],
            name="fk_mapping_run_inputs_org_run",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "raw_record_reference_id"],
            ["raw_record_references.organization_id", "raw_record_references.id"],
            name="fk_mapping_run_inputs_org_raw_record",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("mapping_run_id", "record_sequence", name="uq_mapping_run_input_sequence"),
        CheckConstraint("record_sequence >= 0", name="ck_mapping_run_input_sequence"),
        Index("ix_mapping_run_inputs_org_run", "organization_id", "mapping_run_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid)
    mapping_run_id: Mapped[UUID] = mapped_column(Uuid)
    record_sequence: Mapped[int] = mapped_column(Integer)
    raw_record_reference_id: Mapped[UUID] = mapped_column(Uuid)
    values_json: Mapped[dict[str, object]] = mapped_column(portable_json)
    source_reported_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class MappingRecordResult(MappingConfidenceMixin, TimestampMixin, Base):
    __tablename__ = "mapping_record_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "mapping_run_id"],
            ["mapping_runs.organization_id", "mapping_runs.id"],
            name="fk_mapping_record_results_org_mapping_run",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "raw_record_reference_id"],
            ["raw_record_references.organization_id", "raw_record_references.id"],
            name="fk_mapping_record_results_org_raw_record",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_mapping_record_results_org_id",
        ),
        UniqueConstraint(
            "mapping_run_id",
            "raw_record_reference_id",
            "canonical_target_kind",
            name="uq_mapping_record_result_target",
        ),
        CheckConstraint(
            f"status IN ({enum_values(MappingRecordStatus)})",
            name="ck_mapping_record_result_status",
        ),
        CheckConstraint(
            f"canonical_target_kind IN ({enum_values(CanonicalTypeKind)})",
            name="ck_mapping_record_result_target_kind",
        ),
        CheckConstraint(CONFIDENCE_CHECK, name="ck_mapping_record_result_confidence"),
        Index(
            "ix_mapping_record_result_org_run",
            "organization_id",
            "mapping_run_id",
        ),
        Index(
            "ix_mapping_record_result_org_raw",
            "organization_id",
            "raw_record_reference_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    mapping_run_id: Mapped[UUID] = mapped_column(Uuid)
    raw_record_reference_id: Mapped[UUID] = mapped_column(Uuid)
    status: Mapped[str] = mapped_column(String(40))
    canonical_target_kind: Mapped[str] = mapped_column(String(20))
    canonical_target_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    source_reported_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    mapped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    content_hash: Mapped[str] = mapped_column(String(64))
    result_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)


class MappingException(TimestampMixin, Base):
    __tablename__ = "mapping_exceptions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "mapping_record_result_id"],
            ["mapping_record_results.organization_id", "mapping_record_results.id"],
            name="fk_mapping_exceptions_org_record_result",
            ondelete="CASCADE",
        ),
        UniqueConstraint("organization_id", "id", name="uq_mapping_exceptions_org_id"),
        CheckConstraint(
            f"exception_type IN ({enum_values(MappingExceptionType)})",
            name="ck_mapping_exception_type",
        ),
        CheckConstraint(
            f"status IN ({enum_values(MappingExceptionStatus)})",
            name="ck_mapping_exception_status",
        ),
        Index(
            "ix_mapping_exception_org_result",
            "organization_id",
            "mapping_record_result_id",
        ),
        Index("ix_mapping_exception_org_status", "organization_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    mapping_record_result_id: Mapped[UUID] = mapped_column(Uuid)
    exception_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(30), default=MappingExceptionStatus.OPEN.value)
    detail_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    resolution_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class MappingReview(TimestampMixin, Base):
    __tablename__ = "mapping_reviews"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "mapping_exception_id"],
            ["mapping_exceptions.organization_id", "mapping_exceptions.id"],
            name="fk_mapping_reviews_org_exception",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"decision IN ({enum_values(MappingReviewDecision)})",
            name="ck_mapping_review_decision",
        ),
        Index(
            "ix_mapping_review_org_exception",
            "organization_id",
            "mapping_exception_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    mapping_exception_id: Mapped[UUID] = mapped_column(Uuid)
    decision: Mapped[str] = mapped_column(String(30))
    reviewer_user_id: Mapped[UUID] = mapped_column(Uuid)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    override_value: Mapped[object | None] = mapped_column(portable_json, nullable=True)


class SourceCanonicalLink(MappingConfidenceMixin, TimestampMixin, Base):
    __tablename__ = "source_canonical_links"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "raw_record_reference_id"],
            ["raw_record_references.organization_id", "raw_record_references.id"],
            name="fk_source_canonical_links_org_raw_record",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "mapping_run_id"],
            ["mapping_runs.organization_id", "mapping_runs.id"],
            name="fk_source_canonical_links_org_mapping_run",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id", name="uq_source_canonical_links_org_id"),
        UniqueConstraint(
            "organization_id",
            "raw_record_reference_id",
            "canonical_target_kind",
            "canonical_target_id",
            "mapping_run_id",
            name="uq_source_canonical_link_target",
        ),
        CheckConstraint(
            f"canonical_target_kind IN ({enum_values(CanonicalTypeKind)})",
            name="ck_source_canonical_link_target_kind",
        ),
        CheckConstraint(CONFIDENCE_CHECK, name="ck_source_canonical_link_confidence"),
        Index(
            "ix_source_canonical_link_org_raw",
            "organization_id",
            "raw_record_reference_id",
        ),
        Index(
            "ix_source_canonical_link_org_run",
            "organization_id",
            "mapping_run_id",
        ),
        Index(
            "ix_source_canonical_link_target",
            "organization_id",
            "canonical_target_kind",
            "canonical_target_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    raw_record_reference_id: Mapped[UUID] = mapped_column(Uuid)
    canonical_target_kind: Mapped[str] = mapped_column(String(20))
    canonical_target_id: Mapped[UUID] = mapped_column(Uuid)
    mapping_run_id: Mapped[UUID] = mapped_column(Uuid)
    template_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("mapping_template_versions.id", ondelete="RESTRICT")
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)


class CanonicalEntity(MappingConfidenceMixin, TimestampMixin, Base):
    __tablename__ = "canonical_entities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "survivorship_source_link_id"],
            ["source_canonical_links.organization_id", "source_canonical_links.id"],
            name="fk_canonical_entities_org_survivorship_link",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id", name="uq_canonical_entities_org_id"),
        UniqueConstraint(
            "organization_id",
            "entity_type_id",
            "canonical_entity_key",
            name="uq_canonical_entity_business_key",
        ),
        UniqueConstraint(
            "organization_id",
            "content_fingerprint",
            name="uq_canonical_entity_fingerprint",
        ),
        CheckConstraint(CONFIDENCE_CHECK, name="ck_canonical_entity_confidence"),
        Index("ix_canonical_entity_org_type", "organization_id", "entity_type_id"),
        Index(
            "ix_canonical_entity_org_survivorship",
            "organization_id",
            "survivorship_source_link_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    entity_type_id: Mapped[UUID] = mapped_column(
        ForeignKey("canonical_entity_types.id", ondelete="RESTRICT")
    )
    canonical_entity_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    attributes_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    survivorship_source_link_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    content_fingerprint: Mapped[str] = mapped_column(String(64))


class CanonicalEvent(MappingConfidenceMixin, TimestampMixin, Base):
    __tablename__ = "canonical_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "canonical_entity_id"],
            ["canonical_entities.organization_id", "canonical_entities.id"],
            name="fk_canonical_events_org_entity",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id", name="uq_canonical_events_org_id"),
        UniqueConstraint(
            "organization_id",
            "content_fingerprint",
            name="uq_canonical_event_fingerprint",
        ),
        CheckConstraint(
            f"occurrence_precision IN ({enum_values(OccurrencePrecision)})",
            name="ck_canonical_event_occurrence_precision",
        ),
        CheckConstraint(
            f"mapping_status IN ({enum_values(MappingRecordStatus)})",
            name="ck_canonical_event_mapping_status",
        ),
        CheckConstraint(
            "occurrence_end IS NULL OR occurrence_end >= occurrence_start",
            name="ck_canonical_event_occurrence_range",
        ),
        CheckConstraint(CONFIDENCE_CHECK, name="ck_canonical_event_confidence"),
        Index(
            "ix_canonical_events_occurrence",
            "organization_id",
            "canonical_entity_id",
            "occurrence_start",
        ),
        Index("ix_canonical_event_type", "event_type_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    canonical_entity_id: Mapped[UUID] = mapped_column(Uuid)
    event_type_id: Mapped[UUID] = mapped_column(
        ForeignKey("canonical_event_types.id", ondelete="RESTRICT")
    )
    occurrence_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    occurrence_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    occurrence_precision: Mapped[str] = mapped_column(String(20))
    source_reported_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    actor_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mapping_status: Mapped[str] = mapped_column(String(40))
    attributes_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    content_fingerprint: Mapped[str] = mapped_column(String(64))


class CanonicalMetric(MappingConfidenceMixin, TimestampMixin, Base):
    __tablename__ = "canonical_metrics"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "canonical_entity_id"],
            ["canonical_entities.organization_id", "canonical_entities.id"],
            name="fk_canonical_metrics_org_entity",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id", name="uq_canonical_metrics_org_id"),
        UniqueConstraint(
            "organization_id",
            "content_fingerprint",
            name="uq_canonical_metric_fingerprint",
        ),
        CheckConstraint(
            f"occurrence_precision IN ({enum_values(OccurrencePrecision)})",
            name="ck_canonical_metric_occurrence_precision",
        ),
        CheckConstraint(
            f"mapping_status IN ({enum_values(MappingRecordStatus)})",
            name="ck_canonical_metric_mapping_status",
        ),
        CheckConstraint(
            "occurrence_end IS NULL OR occurrence_end >= occurrence_start",
            name="ck_canonical_metric_occurrence_range",
        ),
        CheckConstraint(
            "currency IS NULL OR length(currency) = 3",
            name="ck_canonical_metric_currency",
        ),
        CheckConstraint(CONFIDENCE_CHECK, name="ck_canonical_metric_confidence"),
        Index(
            "ix_canonical_metrics_occurrence",
            "organization_id",
            "canonical_entity_id",
            "occurrence_start",
        ),
        Index("ix_canonical_metric_type", "metric_type_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    canonical_entity_id: Mapped[UUID] = mapped_column(Uuid)
    metric_type_id: Mapped[UUID] = mapped_column(
        ForeignKey("canonical_metric_types.id", ondelete="RESTRICT")
    )
    measured_value: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    unit: Mapped[str] = mapped_column(String(40))
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    occurrence_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    occurrence_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    occurrence_precision: Mapped[str] = mapped_column(String(20))
    source_reported_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    mapping_status: Mapped[str] = mapped_column(String(40))
    attributes_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    content_fingerprint: Mapped[str] = mapped_column(String(64))


class EntityMatchCandidate(TimestampMixin, Base):
    __tablename__ = "entity_match_candidates"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "source_canonical_link_id"],
            ["source_canonical_links.organization_id", "source_canonical_links.id"],
            name="fk_entity_match_candidates_org_source_link",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "candidate_entity_id"],
            ["canonical_entities.organization_id", "canonical_entities.id"],
            name="fk_entity_match_candidates_org_entity",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "source_canonical_link_id",
            "candidate_entity_id",
            "match_rule_id",
            name="uq_entity_match_candidate",
        ),
        CheckConstraint(
            "match_score >= 0 AND match_score <= 1",
            name="ck_entity_match_candidate_score",
        ),
        CheckConstraint(
            f"status IN ({enum_values(MatchCandidateStatus)})",
            name="ck_entity_match_candidate_status",
        ),
        Index(
            "ix_entity_match_candidate_org_link",
            "organization_id",
            "source_canonical_link_id",
        ),
        Index(
            "ix_entity_match_candidate_org_entity",
            "organization_id",
            "candidate_entity_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    source_canonical_link_id: Mapped[UUID] = mapped_column(Uuid)
    candidate_entity_id: Mapped[UUID] = mapped_column(Uuid)
    match_rule_id: Mapped[UUID] = mapped_column(
        ForeignKey("entity_match_rules.id", ondelete="RESTRICT")
    )
    match_score: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    status: Mapped[str] = mapped_column(String(30), default=MatchCandidateStatus.CANDIDATE.value)
    decided_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MappingAuditEvent(Base):
    __tablename__ = "mapping_audit_events"
    __table_args__ = (
        Index("ix_mapping_audit_org_time", "organization_id", "occurred_at"),
        Index("ix_mapping_audit_entity", "organization_id", "entity_type", "entity_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    event_type: Mapped[str] = mapped_column(String(60))
    entity_type: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[UUID] = mapped_column(Uuid)
    actor_type: Mapped[str] = mapped_column(String(30))
    actor_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


def _guard_published_version(_: object, __: object, target: MappingTemplateVersion) -> None:
    state = inspect(target)
    prior = state.attrs.lifecycle_status.history.deleted
    prior_status = prior[0] if prior else target.lifecycle_status
    if prior_status in {
        MappingLifecycleStatus.PUBLISHED.value,
        MappingLifecycleStatus.DEPRECATED.value,
        MappingLifecycleStatus.RETIRED.value,
    }:
        changed = {
            attribute.key
            for attribute in state.mapper.column_attrs
            if state.attrs[attribute.key].history.has_changes()
        }
        if changed - {"lifecycle_status", "updated_at"}:
            raise ValueError("published mapping-template versions are immutable")
        allowed = {
            (
                MappingLifecycleStatus.PUBLISHED.value,
                MappingLifecycleStatus.DEPRECATED.value,
            ),
            (
                MappingLifecycleStatus.DEPRECATED.value,
                MappingLifecycleStatus.RETIRED.value,
            ),
        }
        if (
            state.attrs.lifecycle_status.history.has_changes()
            and (
                prior_status,
                target.lifecycle_status,
            )
            not in allowed
        ):
            raise ValueError("published mapping-template versions are immutable")


def _guard_published_delete(_: object, __: object, target: MappingTemplateVersion) -> None:
    if target.lifecycle_status in {
        MappingLifecycleStatus.PUBLISHED.value,
        MappingLifecycleStatus.DEPRECATED.value,
        MappingLifecycleStatus.RETIRED.value,
    }:
        raise ValueError("published mapping-template versions are immutable")


def _immutable(*_: object) -> None:
    raise ValueError("mapping audit events are immutable")


event.listen(MappingTemplateVersion, "before_update", _guard_published_version)
event.listen(MappingTemplateVersion, "before_delete", _guard_published_delete)
event.listen(MappingReview, "before_update", _immutable)
event.listen(MappingReview, "before_delete", _immutable)
event.listen(MappingAuditEvent, "before_update", _immutable)
event.listen(MappingAuditEvent, "before_delete", _immutable)
