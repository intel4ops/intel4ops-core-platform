"""P3.xxC.1: Analysis Case orchestration foundation.

Adds the run-aware, industry-agnostic, artifact-first Analysis Case
architecture: a durable AnalysisCase container, repeatable AnalysisCaseRun
executions (lease/heartbeat-shaped for future async-worker migration),
SourceArtifact as the universal upload primitive, per-dataset detection/
mapping-bridge/entity-resolution tracking, an append-only stage-event audit
trail, and lightweight case-scoped Action/Recovery tracking. New join
tables (AnalysisCaseFinding, FindingSourceDataset, AnalysisCaseActionFinding)
let findings/actions reference multiple contributing datasets/findings
without touching the existing governed Finding/OpportunityFinding shapes.

Revision ID: 20260826_0049
Revises: 20260822_0048
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260826_0049"
down_revision: str | None = "20260822_0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
portable_json = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "analysis_cases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("case_code", sa.String(length=40), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("industry_code", sa.String(length=60), nullable=True),
        sa.Column("business_model", sa.String(length=60), nullable=True),
        sa.Column("operating_context", sa.String(length=200), nullable=True),
        sa.Column("case_currency_hint", sa.String(length=3), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("mode IN ('single', 'orchestrated')", name="ck_analysis_case_mode"),
        sa.CheckConstraint(
            "status IN ('created', 'running', 'review_required', 'partial', 'completed', "
            "'failed', 'cancelled')",
            name="ck_analysis_case_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_code"),
        sa.UniqueConstraint("organization_id", "id"),
        sa.UniqueConstraint("organization_id", "idempotency_key"),
    )
    op.create_index(
        "ix_analysis_cases_org_status",
        "analysis_cases",
        ["organization_id", "status"],
        unique=False,
    )

    op.create_table(
        "analysis_case_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_case_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner", sa.String(length=200), nullable=True),
        sa.Column("priority", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('open', 'in_progress', 'blocked', 'completed', 'cancelled')",
            name="ck_analysis_case_action_status",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "analysis_case_id"],
            ["analysis_cases.organization_id", "analysis_cases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_analysis_case_actions_org_case",
        "analysis_case_actions",
        ["organization_id", "analysis_case_id"],
        unique=False,
    )

    op.create_table(
        "analysis_case_entity_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_case_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_subtype", sa.String(length=60), nullable=True),
        sa.Column("canonical_key", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source_dataset_ids", portable_json, nullable=False),
        sa.Column("detail", portable_json, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('matched', 'unresolved', 'conflict')",
            name="ck_analysis_case_entity_link_status",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "analysis_case_id"],
            ["analysis_cases.organization_id", "analysis_cases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_case_id", "entity_type", "canonical_key"),
    )
    op.create_index(
        "ix_analysis_case_entity_links_org_case",
        "analysis_case_entity_links",
        ["organization_id", "analysis_case_id"],
        unique=False,
    )

    op.create_table(
        "analysis_case_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_case_id", sa.Uuid(), nullable=False),
        sa.Column("run_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_lease_id", sa.Uuid(), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("orchestration_version", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('created', 'running', 'interrupted', 'review_required', 'partial', "
            "'completed', 'failed', 'cancelled')",
            name="ck_analysis_case_run_status",
        ),
        sa.ForeignKeyConstraint(["analysis_case_id"], ["analysis_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_case_id", "run_number"),
    )
    op.create_index(
        "ix_analysis_case_runs_org_case",
        "analysis_case_runs",
        ["organization_id", "analysis_case_id"],
        unique=False,
    )

    op.create_table(
        "source_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_case_id", sa.Uuid(), nullable=False),
        sa.Column("parent_artifact_id", sa.Uuid(), nullable=True),
        sa.Column("original_filename", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=150), nullable=False),
        sa.Column("extension", sa.String(length=20), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("storage_reference", sa.String(length=1000), nullable=False),
        sa.Column("source_system", sa.String(length=100), nullable=True),
        sa.Column("ingestion_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("parser_status", sa.String(length=20), nullable=False),
        sa.Column("parser_code", sa.String(length=60), nullable=True),
        sa.Column("parser_version", sa.String(length=20), nullable=True),
        sa.Column("extraction_status", sa.String(length=20), nullable=False),
        sa.Column("extraction_warnings", portable_json, nullable=False),
        sa.Column("extraction_metadata", portable_json, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "extraction_status IN ('pending', 'extracted', 'partial', 'failed', 'unavailable')",
            name="ck_source_artifact_extraction_status",
        ),
        sa.CheckConstraint(
            "parser_status IN ('pending', 'parsed', 'failed', 'unsupported')",
            name="ck_source_artifact_parser_status",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "analysis_case_id"],
            ["analysis_cases.organization_id", "analysis_cases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["parent_artifact_id"], ["source_artifacts.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_source_artifacts_org_case",
        "source_artifacts",
        ["organization_id", "analysis_case_id"],
        unique=False,
    )

    op.create_table(
        "analysis_case_evidence_objects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_case_id", sa.Uuid(), nullable=False),
        sa.Column("source_artifact_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_type", sa.String(length=30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("lineage_ref", portable_json, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "analysis_case_id"],
            ["analysis_cases.organization_id", "analysis_cases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_artifact_id"], ["source_artifacts.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_analysis_case_evidence_objects_org_case",
        "analysis_case_evidence_objects",
        ["organization_id", "analysis_case_id"],
        unique=False,
    )

    op.create_table(
        "analysis_case_stage_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_case_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.Column("source_artifact_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("detail", portable_json, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('started', 'completed', 'skipped', 'failed')",
            name="ck_analysis_case_stage_event_status",
        ),
        sa.ForeignKeyConstraint(["analysis_case_id"], ["analysis_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["analysis_case_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_analysis_case_stage_events_org_run",
        "analysis_case_stage_events",
        ["organization_id", "run_id"],
        unique=False,
    )

    op.create_table(
        "analysis_case_datasets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_case_id", sa.Uuid(), nullable=False),
        sa.Column("source_artifact_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_version_id", sa.Uuid(), nullable=True),
        sa.Column("source_label", sa.String(length=200), nullable=False),
        sa.Column("detected_domain", sa.String(length=60), nullable=True),
        sa.Column("detection_basis", portable_json, nullable=False),
        sa.Column("detection_status", sa.String(length=20), nullable=False),
        sa.Column("trust_assessment_id", sa.Uuid(), nullable=True),
        sa.Column("trust_status", sa.String(length=30), nullable=True),
        sa.Column("mapping_status", sa.String(length=30), nullable=True),
        sa.Column("intelligence_readiness_status", sa.String(length=20), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "detection_status IN ('confirmed', 'needs_review', 'unknown')",
            name="ck_analysis_case_dataset_detection_status",
        ),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"], ["dataset_versions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "analysis_case_id"],
            ["analysis_cases.organization_id", "analysis_cases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_artifact_id"], ["source_artifacts.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_case_id", "dataset_id"),
    )
    op.create_index(
        "ix_analysis_case_datasets_org_case",
        "analysis_case_datasets",
        ["organization_id", "analysis_case_id"],
        unique=False,
    )

    op.create_table(
        "analysis_case_field_mappings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_case_dataset_id", sa.Uuid(), nullable=False),
        sa.Column("source_field", sa.String(length=200), nullable=False),
        sa.Column("canonical_field", sa.String(length=200), nullable=True),
        sa.Column("mapping_status", sa.String(length=30), nullable=False),
        sa.Column("mapping_basis", sa.String(length=60), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "mapping_status IN ('auto_mapped', 'needs_review', 'missing_required_field', "
            "'ignored')",
            name="ck_analysis_case_field_mapping_status",
        ),
        sa.ForeignKeyConstraint(
            ["analysis_case_dataset_id"], ["analysis_case_datasets.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_case_dataset_id", "source_field"),
    )
    op.create_index(
        "ix_analysis_case_field_mappings_org",
        "analysis_case_field_mappings",
        ["organization_id"],
        unique=False,
    )

    op.create_table(
        "analysis_case_action_findings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["action_id"], ["analysis_case_actions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("action_id", "finding_id"),
    )
    op.create_index(
        "ix_analysis_case_action_findings_org",
        "analysis_case_action_findings",
        ["organization_id"],
        unique=False,
    )

    op.create_table(
        "analysis_case_findings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_case_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["analysis_case_id"], ["analysis_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["analysis_case_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "finding_id"),
    )
    op.create_index(
        "ix_analysis_case_findings_org_case",
        "analysis_case_findings",
        ["organization_id", "analysis_case_id"],
        unique=False,
    )

    op.create_table(
        "analysis_case_recovery_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_case_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("baseline_condition", sa.Text(), nullable=True),
        sa.Column("intervention_summary", sa.Text(), nullable=True),
        sa.Column("recovery_status", sa.String(length=30), nullable=False),
        sa.Column("observed_post_condition", portable_json, nullable=True),
        sa.Column("observed_value", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("estimated_value", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("verified_value", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("currency_detail", portable_json, nullable=True),
        sa.Column("evidence_json", portable_json, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "recovery_status IN ('not_started', 'in_progress', 'awaiting_verification', "
            "'verified', 'not_verified')",
            name="ck_analysis_case_recovery_status",
        ),
        sa.ForeignKeyConstraint(["action_id"], ["analysis_case_actions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "analysis_case_id"],
            ["analysis_cases.organization_id", "analysis_cases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_analysis_case_recovery_records_org_case",
        "analysis_case_recovery_records",
        ["organization_id", "analysis_case_id"],
        unique=False,
    )

    op.create_table(
        "finding_source_datasets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_version_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"], ["dataset_versions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("finding_id", "dataset_id"),
    )
    op.create_index(
        "ix_finding_source_datasets_org",
        "finding_source_datasets",
        ["organization_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_finding_source_datasets_org", table_name="finding_source_datasets")
    op.drop_table("finding_source_datasets")
    op.drop_index(
        "ix_analysis_case_recovery_records_org_case", table_name="analysis_case_recovery_records"
    )
    op.drop_table("analysis_case_recovery_records")
    op.drop_index("ix_analysis_case_findings_org_case", table_name="analysis_case_findings")
    op.drop_table("analysis_case_findings")
    op.drop_index(
        "ix_analysis_case_action_findings_org", table_name="analysis_case_action_findings"
    )
    op.drop_table("analysis_case_action_findings")
    op.drop_index("ix_analysis_case_field_mappings_org", table_name="analysis_case_field_mappings")
    op.drop_table("analysis_case_field_mappings")
    op.drop_index("ix_analysis_case_datasets_org_case", table_name="analysis_case_datasets")
    op.drop_table("analysis_case_datasets")
    op.drop_index("ix_analysis_case_stage_events_org_run", table_name="analysis_case_stage_events")
    op.drop_table("analysis_case_stage_events")
    op.drop_index(
        "ix_analysis_case_evidence_objects_org_case", table_name="analysis_case_evidence_objects"
    )
    op.drop_table("analysis_case_evidence_objects")
    op.drop_index("ix_source_artifacts_org_case", table_name="source_artifacts")
    op.drop_table("source_artifacts")
    op.drop_index("ix_analysis_case_runs_org_case", table_name="analysis_case_runs")
    op.drop_table("analysis_case_runs")
    op.drop_index("ix_analysis_case_entity_links_org_case", table_name="analysis_case_entity_links")
    op.drop_table("analysis_case_entity_links")
    op.drop_index("ix_analysis_case_actions_org_case", table_name="analysis_case_actions")
    op.drop_table("analysis_case_actions")
    op.drop_index("ix_analysis_cases_org_status", table_name="analysis_cases")
    op.drop_table("analysis_cases")
