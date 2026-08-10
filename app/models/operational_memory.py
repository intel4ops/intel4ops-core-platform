from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    event,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.entities import portable_json, utc_now

MEMORY_CATEGORIES = ("FIELD_MAPPING", "SCHEMA_PATTERN", "TERMINOLOGY")
MEMORY_STATUSES = (
    "OBSERVED",
    "CONFIRMED",
    "CORRECTED",
    "AMBIGUOUS",
    "REJECTED",
    "DEPRECATED",
)
ASSERTION_KINDS = (
    "FIELD_TO_CANONICAL_FIELD",
    "SCHEMA_TO_CANONICAL_DOMAIN",
    "TERM_TO_CANONICAL_CONCEPT",
)
STALE_REASONS = (
    "SCHEMA_CHANGED",
    "SOURCE_SYSTEM_CHANGED",
    "MAPPING_VERSION_RETIRED",
    "CANONICAL_DEFINITION_INCOMPATIBLE",
    "VALIDITY_EXPIRED",
    "CONTRADICTORY_EVIDENCE",
)


class OperationalMemoryItem(Base):
    __tablename__ = "operational_memory_items"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_operational_memory_items_org_id"),
        UniqueConstraint(
            "organization_id",
            "category",
            "memory_fingerprint",
            name="uq_operational_memory_items_org_fingerprint",
        ),
        CheckConstraint(
            "category IN ('FIELD_MAPPING','SCHEMA_PATTERN','TERMINOLOGY')",
            name="ck_operational_memory_items_category",
        ),
        CheckConstraint(
            "subject_kind IN ('SOURCE_FIELD','SOURCE_SCHEMA','TERM')",
            name="ck_operational_memory_items_subject_kind",
        ),
        CheckConstraint(
            "(category = 'FIELD_MAPPING' AND subject_kind = 'SOURCE_FIELD') OR "
            "(category = 'SCHEMA_PATTERN' AND subject_kind = 'SOURCE_SCHEMA') OR "
            "(category = 'TERMINOLOGY' AND subject_kind = 'TERM')",
            name="ck_operational_memory_items_category_subject",
        ),
        CheckConstraint(
            "current_status IN "
            "('OBSERVED','CONFIRMED','CORRECTED','AMBIGUOUS','REJECTED','DEPRECATED')",
            name="ck_operational_memory_items_status",
        ),
        CheckConstraint("current_version_number >= 1", name="ck_operational_memory_items_version"),
        CheckConstraint(
            "support_count >= 0 AND contradiction_count >= 0 AND "
            "confirmation_count >= 0 AND rejection_count >= 0",
            name="ck_operational_memory_items_counts",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name="ck_operational_memory_items_validity",
        ),
        CheckConstraint(
            "security_classification IN ('TENANT_INTERNAL','TENANT_SENSITIVE')",
            name="ck_operational_memory_items_security",
        ),
        CheckConstraint(
            "(is_stale = false AND stale_reason_code IS NULL AND stale_detected_at IS NULL) OR "
            "(is_stale = true AND stale_reason_code IN "
            "('SCHEMA_CHANGED','SOURCE_SYSTEM_CHANGED','MAPPING_VERSION_RETIRED',"
            "'CANONICAL_DEFINITION_INCOMPATIBLE','VALIDITY_EXPIRED',"
            "'CONTRADICTORY_EVIDENCE') AND stale_detected_at IS NOT NULL)",
            name="ck_operational_memory_items_stale_projection",
        ),
        CheckConstraint(
            "length(context_signature) = 64 AND length(memory_fingerprint) = 64",
            name="ck_operational_memory_items_hashes",
        ),
        Index(
            "ix_operational_memory_items_org_status_category",
            "organization_id",
            "current_status",
            "category",
        ),
        Index(
            "ix_operational_memory_items_org_category_source_domain",
            "organization_id",
            "category",
            "source_system_family",
            "canonical_domain",
        ),
        Index(
            "ix_operational_memory_items_org_category_subject",
            "organization_id",
            "category",
            "normalized_subject",
        ),
        Index(
            "ix_operational_memory_items_org_category_context",
            "organization_id",
            "category",
            "context_signature",
        ),
        Index(
            "ix_operational_memory_items_org_stale",
            "organization_id",
            "is_stale",
            "current_status",
        ),
        Index(
            "ix_operational_memory_items_org_retention",
            "organization_id",
            "retention_until",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "organizations.id",
            name="fk_operational_memory_items_organization",
            ondelete="RESTRICT",
        )
    )
    category: Mapped[str] = mapped_column(String(30))
    subject_kind: Mapped[str] = mapped_column(String(30))
    normalized_subject: Mapped[str] = mapped_column(String(500))
    source_system_family: Mapped[str | None] = mapped_column(String(100), nullable=True)
    canonical_domain: Mapped[str | None] = mapped_column(String(100), nullable=True)
    context_signature: Mapped[str] = mapped_column(String(64))
    memory_fingerprint: Mapped[str] = mapped_column(String(64))
    normalization_policy_code: Mapped[str] = mapped_column(
        String(60), default="memory_normalization_v1", server_default="memory_normalization_v1"
    )
    identity_policy_code: Mapped[str] = mapped_column(
        String(60), default="memory_identity_v1", server_default="memory_identity_v1"
    )
    current_version_number: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    current_status: Mapped[str] = mapped_column(
        String(30), default="OBSERVED", server_default="OBSERVED"
    )
    support_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    contradiction_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    confirmation_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    rejection_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    stale_reason_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    stale_detected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    security_classification: Mapped[str] = mapped_column(
        String(30), default="TENANT_INTERNAL", server_default="TENANT_INTERNAL"
    )
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class OperationalMemoryVersion(Base):
    __tablename__ = "operational_memory_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "memory_id"],
            ["operational_memory_items.organization_id", "operational_memory_items.id"],
            name="fk_operational_memory_versions_org_memory",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "memory_id", "supersedes_version_id"],
            [
                "operational_memory_versions.organization_id",
                "operational_memory_versions.memory_id",
                "operational_memory_versions.id",
            ],
            name="fk_operational_memory_versions_org_supersedes",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "source_schema_id"],
            ["source_schemas.organization_id", "source_schemas.id"],
            name="fk_operational_memory_versions_org_source_schema",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "mapping_record_result_id"],
            ["mapping_record_results.organization_id", "mapping_record_results.id"],
            name="fk_operational_memory_versions_org_mapping_result",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id", name="uq_operational_memory_versions_org_id"),
        UniqueConstraint(
            "organization_id",
            "memory_id",
            "id",
            name="uq_operational_memory_versions_org_memory_id",
        ),
        UniqueConstraint(
            "organization_id",
            "memory_id",
            "version_number",
            name="uq_operational_memory_versions_org_memory_version",
        ),
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_operational_memory_versions_org_idempotency",
        ),
        CheckConstraint("version_number >= 1", name="ck_operational_memory_versions_version"),
        CheckConstraint(
            "(version_number = 1 AND supersedes_version_id IS NULL) OR "
            "(version_number > 1 AND supersedes_version_id IS NOT NULL)",
            name="ck_operational_memory_versions_supersession",
        ),
        CheckConstraint(
            "status IN ('OBSERVED','CONFIRMED','CORRECTED','AMBIGUOUS','REJECTED','DEPRECATED')",
            name="ck_operational_memory_versions_status",
        ),
        CheckConstraint(
            "assertion_kind IN "
            "('FIELD_TO_CANONICAL_FIELD','SCHEMA_TO_CANONICAL_DOMAIN',"
            "'TERM_TO_CANONICAL_CONCEPT')",
            name="ck_operational_memory_versions_assertion",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_operational_memory_versions_effective",
        ),
        CheckConstraint(
            "confidence_label IS NULL OR confidence_label IN ('UNASSESSED','HUMAN_CONFIRMED')",
            name="ck_operational_memory_versions_confidence",
        ),
        CheckConstraint(
            "actor_role IN ('system','platform_admin','organization_admin','analyst',"
            "'operator','recovery_manager','viewer')",
            name="ck_operational_memory_versions_actor",
        ),
        CheckConstraint(
            "length(source_fingerprint) = 64 AND length(context_fingerprint) = 64 "
            "AND length(request_fingerprint) = 64 AND length(content_hash) = 64",
            name="ck_operational_memory_versions_hashes",
        ),
        Index(
            "ix_operational_memory_versions_org_source_schema",
            "organization_id",
            "source_schema_id",
        ),
        Index(
            "ix_operational_memory_versions_org_mapping_result",
            "organization_id",
            "mapping_record_result_id",
        ),
        Index(
            "ix_operational_memory_versions_org_supersedes",
            "organization_id",
            "memory_id",
            "supersedes_version_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "organizations.id",
            name="fk_operational_memory_versions_organization",
            ondelete="RESTRICT",
        )
    )
    memory_id: Mapped[UUID] = mapped_column(Uuid)
    version_number: Mapped[int] = mapped_column(Integer)
    supersedes_version_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(30))
    assertion_kind: Mapped[str] = mapped_column(String(50))
    value_payload: Mapped[dict[str, object]] = mapped_column(portable_json)
    source_schema_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    mapping_record_result_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    source_fingerprint: Mapped[str] = mapped_column(String(64))
    context_fingerprint: Mapped[str] = mapped_column(String(64))
    provenance_snapshot: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    confidence_label: Mapped[str | None] = mapped_column(String(30), nullable=True)
    confidence_method_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confidence_method_version: Mapped[str | None] = mapped_column(String(30), nullable=True)
    decision_reason_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    actor_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    actor_role: Mapped[str] = mapped_column(String(50))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OperationalMemoryReuseEvent(Base):
    __tablename__ = "operational_memory_reuse_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "memory_id", "memory_version_id"],
            [
                "operational_memory_versions.organization_id",
                "operational_memory_versions.memory_id",
                "operational_memory_versions.id",
            ],
            name="fk_operational_memory_reuse_org_version",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id", name="uq_operational_memory_reuse_org_id"),
        UniqueConstraint(
            "organization_id",
            "consumer_code",
            "idempotency_key",
            "event_sequence",
            name="uq_operational_memory_reuse_idempotency_sequence",
        ),
        CheckConstraint(
            "event_type IN ('RETRIEVED','NO_MATCH')",
            name="ck_operational_memory_reuse_event_type",
        ),
        CheckConstraint(
            "(event_type = 'NO_MATCH' AND memory_id IS NULL AND "
            "memory_version_id IS NULL AND rank IS NULL) OR "
            "(event_type = 'RETRIEVED' AND memory_id IS NOT NULL AND "
            "memory_version_id IS NOT NULL AND rank IS NOT NULL)",
            name="ck_operational_memory_reuse_reference_shape",
        ),
        CheckConstraint("rank IS NULL OR rank >= 1", name="ck_operational_memory_reuse_rank"),
        CheckConstraint(
            "event_sequence >= 1 AND suggestion_count >= 0",
            name="ck_operational_memory_reuse_counts",
        ),
        CheckConstraint("retrieval_latency_ms >= 0", name="ck_operational_memory_reuse_latency"),
        CheckConstraint(
            "length(context_fingerprint) = 64 AND length(request_fingerprint) = 64",
            name="ck_operational_memory_reuse_hashes",
        ),
        Index(
            "ix_operational_memory_reuse_org_consumer_time",
            "organization_id",
            "consumer_code",
            "occurred_at",
        ),
        Index(
            "ix_operational_memory_reuse_org_memory_time",
            "organization_id",
            "memory_id",
            "occurred_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "organizations.id",
            name="fk_operational_memory_reuse_organization",
            ondelete="RESTRICT",
        )
    )
    memory_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    memory_version_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    event_type: Mapped[str] = mapped_column(String(30))
    consumer_code: Mapped[str] = mapped_column(String(100))
    consumer_version: Mapped[str] = mapped_column(String(30))
    context_fingerprint: Mapped[str] = mapped_column(String(64))
    retrieval_policy_code: Mapped[str] = mapped_column(
        String(100),
        default="deterministic_mapping_memory",
        server_default="deterministic_mapping_memory",
    )
    retrieval_policy_version: Mapped[str] = mapped_column(
        String(30), default="1.0", server_default="1.0"
    )
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event_sequence: Mapped[int] = mapped_column(Integer)
    suggestion_count: Mapped[int] = mapped_column(Integer)
    match_reasons: Mapped[list[object]] = mapped_column(portable_json, default=list)
    retrieval_latency_ms: Mapped[int] = mapped_column(Integer)
    idempotency_key: Mapped[str] = mapped_column(String(255))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    correlation_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


def _immutable(*_: object) -> None:
    raise ValueError("operational-memory history is immutable")


event.listen(OperationalMemoryVersion, "before_update", _immutable)
event.listen(OperationalMemoryVersion, "before_delete", _immutable)
event.listen(OperationalMemoryReuseEvent, "before_update", _immutable)
event.listen(OperationalMemoryReuseEvent, "before_delete", _immutable)
