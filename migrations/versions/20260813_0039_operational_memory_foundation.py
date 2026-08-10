"""Add tenant mapping operational-memory foundation.

Revision ID: 20260813_0039
Revises: 20260812_0038
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260813_0039"
down_revision: str | None = "20260812_0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

portable_json = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "operational_memory_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("subject_kind", sa.String(length=30), nullable=False),
        sa.Column("normalized_subject", sa.String(length=500), nullable=False),
        sa.Column("source_system_family", sa.String(length=100), nullable=True),
        sa.Column("canonical_domain", sa.String(length=100), nullable=True),
        sa.Column("context_signature", sa.String(length=64), nullable=False),
        sa.Column("memory_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "normalization_policy_code",
            sa.String(length=60),
            server_default="memory_normalization_v1",
            nullable=False,
        ),
        sa.Column(
            "identity_policy_code",
            sa.String(length=60),
            server_default="memory_identity_v1",
            nullable=False,
        ),
        sa.Column("current_version_number", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "current_status", sa.String(length=30), server_default="OBSERVED", nullable=False
        ),
        sa.Column("support_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("contradiction_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("confirmation_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rejection_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_stale", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("stale_reason_code", sa.String(length=60), nullable=True),
        sa.Column("stale_detected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "security_classification",
            sa.String(length=30),
            server_default="TENANT_INTERNAL",
            nullable=False,
        ),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "category IN ('FIELD_MAPPING','SCHEMA_PATTERN','TERMINOLOGY')",
            name="ck_operational_memory_items_category",
        ),
        sa.CheckConstraint(
            "subject_kind IN ('SOURCE_FIELD','SOURCE_SCHEMA','TERM')",
            name="ck_operational_memory_items_subject_kind",
        ),
        sa.CheckConstraint(
            "(category = 'FIELD_MAPPING' AND subject_kind = 'SOURCE_FIELD') OR "
            "(category = 'SCHEMA_PATTERN' AND subject_kind = 'SOURCE_SCHEMA') OR "
            "(category = 'TERMINOLOGY' AND subject_kind = 'TERM')",
            name="ck_operational_memory_items_category_subject",
        ),
        sa.CheckConstraint(
            "current_status IN "
            "('OBSERVED','CONFIRMED','CORRECTED','AMBIGUOUS','REJECTED','DEPRECATED')",
            name="ck_operational_memory_items_status",
        ),
        sa.CheckConstraint(
            "current_version_number >= 1", name="ck_operational_memory_items_version"
        ),
        sa.CheckConstraint(
            "support_count >= 0 AND contradiction_count >= 0 AND "
            "confirmation_count >= 0 AND rejection_count >= 0",
            name="ck_operational_memory_items_counts",
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name="ck_operational_memory_items_validity",
        ),
        sa.CheckConstraint(
            "security_classification IN ('TENANT_INTERNAL','TENANT_SENSITIVE')",
            name="ck_operational_memory_items_security",
        ),
        sa.CheckConstraint(
            "(is_stale = false AND stale_reason_code IS NULL AND stale_detected_at IS NULL) OR "
            "(is_stale = true AND stale_reason_code IN "
            "('SCHEMA_CHANGED','SOURCE_SYSTEM_CHANGED','MAPPING_VERSION_RETIRED',"
            "'CANONICAL_DEFINITION_INCOMPATIBLE','VALIDITY_EXPIRED',"
            "'CONTRADICTORY_EVIDENCE') AND stale_detected_at IS NOT NULL)",
            name="ck_operational_memory_items_stale_projection",
        ),
        sa.CheckConstraint(
            "length(context_signature) = 64 AND length(memory_fingerprint) = 64",
            name="ck_operational_memory_items_hashes",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_operational_memory_items_organization",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_operational_memory_items_org_id"),
        sa.UniqueConstraint(
            "organization_id",
            "category",
            "memory_fingerprint",
            name="uq_operational_memory_items_org_fingerprint",
        ),
    )
    op.create_index(
        "ix_operational_memory_items_org_status_category",
        "operational_memory_items",
        ["organization_id", "current_status", "category"],
    )
    op.create_index(
        "ix_operational_memory_items_org_category_source_domain",
        "operational_memory_items",
        ["organization_id", "category", "source_system_family", "canonical_domain"],
    )
    op.create_index(
        "ix_operational_memory_items_org_category_subject",
        "operational_memory_items",
        ["organization_id", "category", "normalized_subject"],
    )
    op.create_index(
        "ix_operational_memory_items_org_category_context",
        "operational_memory_items",
        ["organization_id", "category", "context_signature"],
    )
    op.create_index(
        "ix_operational_memory_items_org_stale",
        "operational_memory_items",
        ["organization_id", "is_stale", "current_status"],
    )
    op.create_index(
        "ix_operational_memory_items_org_retention",
        "operational_memory_items",
        ["organization_id", "retention_until"],
    )

    op.create_table(
        "operational_memory_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("memory_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("supersedes_version_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("assertion_kind", sa.String(length=50), nullable=False),
        sa.Column("value_payload", portable_json, nullable=False),
        sa.Column("source_schema_id", sa.Uuid(), nullable=True),
        sa.Column("mapping_record_result_id", sa.Uuid(), nullable=True),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("context_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("provenance_snapshot", portable_json, nullable=False),
        sa.Column("confidence_label", sa.String(length=30), nullable=True),
        sa.Column("confidence_method_code", sa.String(length=100), nullable=True),
        sa.Column("confidence_method_version", sa.String(length=30), nullable=True),
        sa.Column("decision_reason_code", sa.String(length=60), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_role", sa.String(length=50), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version_number >= 1", name="ck_operational_memory_versions_version"),
        sa.CheckConstraint(
            "(version_number = 1 AND supersedes_version_id IS NULL) OR "
            "(version_number > 1 AND supersedes_version_id IS NOT NULL)",
            name="ck_operational_memory_versions_supersession",
        ),
        sa.CheckConstraint(
            "status IN ('OBSERVED','CONFIRMED','CORRECTED','AMBIGUOUS','REJECTED','DEPRECATED')",
            name="ck_operational_memory_versions_status",
        ),
        sa.CheckConstraint(
            "assertion_kind IN "
            "('FIELD_TO_CANONICAL_FIELD','SCHEMA_TO_CANONICAL_DOMAIN',"
            "'TERM_TO_CANONICAL_CONCEPT')",
            name="ck_operational_memory_versions_assertion",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_operational_memory_versions_effective",
        ),
        sa.CheckConstraint(
            "confidence_label IS NULL OR confidence_label IN ('UNASSESSED','HUMAN_CONFIRMED')",
            name="ck_operational_memory_versions_confidence",
        ),
        sa.CheckConstraint(
            "actor_role IN ('system','platform_admin','organization_admin','analyst',"
            "'operator','recovery_manager','viewer')",
            name="ck_operational_memory_versions_actor",
        ),
        sa.CheckConstraint(
            "length(source_fingerprint) = 64 AND length(context_fingerprint) = 64 "
            "AND length(request_fingerprint) = 64 AND length(content_hash) = 64",
            name="ck_operational_memory_versions_hashes",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_operational_memory_versions_organization",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "memory_id"],
            ["operational_memory_items.organization_id", "operational_memory_items.id"],
            name="fk_operational_memory_versions_org_memory",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "memory_id", "supersedes_version_id"],
            [
                "operational_memory_versions.organization_id",
                "operational_memory_versions.memory_id",
                "operational_memory_versions.id",
            ],
            name="fk_operational_memory_versions_org_supersedes",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "source_schema_id"],
            ["source_schemas.organization_id", "source_schemas.id"],
            name="fk_operational_memory_versions_org_source_schema",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "mapping_record_result_id"],
            ["mapping_record_results.organization_id", "mapping_record_results.id"],
            name="fk_operational_memory_versions_org_mapping_result",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_operational_memory_versions_org_id"),
        sa.UniqueConstraint(
            "organization_id",
            "memory_id",
            "id",
            name="uq_operational_memory_versions_org_memory_id",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "memory_id",
            "version_number",
            name="uq_operational_memory_versions_org_memory_version",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_operational_memory_versions_org_idempotency",
        ),
    )
    op.create_index(
        "ix_operational_memory_versions_org_source_schema",
        "operational_memory_versions",
        ["organization_id", "source_schema_id"],
    )
    op.create_index(
        "ix_operational_memory_versions_org_mapping_result",
        "operational_memory_versions",
        ["organization_id", "mapping_record_result_id"],
    )
    op.create_index(
        "ix_operational_memory_versions_org_supersedes",
        "operational_memory_versions",
        ["organization_id", "memory_id", "supersedes_version_id"],
    )

    op.create_table(
        "operational_memory_reuse_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("memory_id", sa.Uuid(), nullable=True),
        sa.Column("memory_version_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("consumer_code", sa.String(length=100), nullable=False),
        sa.Column("consumer_version", sa.String(length=30), nullable=False),
        sa.Column("context_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "retrieval_policy_code",
            sa.String(length=100),
            server_default="deterministic_mapping_memory",
            nullable=False,
        ),
        sa.Column(
            "retrieval_policy_version",
            sa.String(length=30),
            server_default="1.0",
            nullable=False,
        ),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("suggestion_count", sa.Integer(), nullable=False),
        sa.Column("match_reasons", portable_json, nullable=False),
        sa.Column("retrieval_latency_ms", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("correlation_id", sa.String(length=100), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('RETRIEVED','NO_MATCH')",
            name="ck_operational_memory_reuse_event_type",
        ),
        sa.CheckConstraint(
            "(event_type = 'NO_MATCH' AND memory_id IS NULL AND "
            "memory_version_id IS NULL AND rank IS NULL) OR "
            "(event_type = 'RETRIEVED' AND memory_id IS NOT NULL AND "
            "memory_version_id IS NOT NULL AND rank IS NOT NULL)",
            name="ck_operational_memory_reuse_reference_shape",
        ),
        sa.CheckConstraint("rank IS NULL OR rank >= 1", name="ck_operational_memory_reuse_rank"),
        sa.CheckConstraint(
            "event_sequence >= 1 AND suggestion_count >= 0",
            name="ck_operational_memory_reuse_counts",
        ),
        sa.CheckConstraint("retrieval_latency_ms >= 0", name="ck_operational_memory_reuse_latency"),
        sa.CheckConstraint(
            "length(context_fingerprint) = 64 AND length(request_fingerprint) = 64",
            name="ck_operational_memory_reuse_hashes",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_operational_memory_reuse_organization",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "memory_id", "memory_version_id"],
            [
                "operational_memory_versions.organization_id",
                "operational_memory_versions.memory_id",
                "operational_memory_versions.id",
            ],
            name="fk_operational_memory_reuse_org_version",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_operational_memory_reuse_org_id"),
        sa.UniqueConstraint(
            "organization_id",
            "consumer_code",
            "idempotency_key",
            "event_sequence",
            name="uq_operational_memory_reuse_idempotency_sequence",
        ),
    )
    op.create_index(
        "ix_operational_memory_reuse_org_consumer_time",
        "operational_memory_reuse_events",
        ["organization_id", "consumer_code", "occurred_at"],
    )
    op.create_index(
        "ix_operational_memory_reuse_org_memory_time",
        "operational_memory_reuse_events",
        ["organization_id", "memory_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_operational_memory_reuse_org_memory_time",
        table_name="operational_memory_reuse_events",
    )
    op.drop_index(
        "ix_operational_memory_reuse_org_consumer_time",
        table_name="operational_memory_reuse_events",
    )
    op.drop_table("operational_memory_reuse_events")
    op.drop_index(
        "ix_operational_memory_versions_org_supersedes",
        table_name="operational_memory_versions",
    )
    op.drop_index(
        "ix_operational_memory_versions_org_mapping_result",
        table_name="operational_memory_versions",
    )
    op.drop_index(
        "ix_operational_memory_versions_org_source_schema",
        table_name="operational_memory_versions",
    )
    op.drop_table("operational_memory_versions")
    op.drop_index(
        "ix_operational_memory_items_org_retention", table_name="operational_memory_items"
    )
    op.drop_index("ix_operational_memory_items_org_stale", table_name="operational_memory_items")
    op.drop_index(
        "ix_operational_memory_items_org_category_context",
        table_name="operational_memory_items",
    )
    op.drop_index(
        "ix_operational_memory_items_org_category_subject",
        table_name="operational_memory_items",
    )
    op.drop_index(
        "ix_operational_memory_items_org_category_source_domain",
        table_name="operational_memory_items",
    )
    op.drop_index(
        "ix_operational_memory_items_org_status_category",
        table_name="operational_memory_items",
    )
    op.drop_table("operational_memory_items")
