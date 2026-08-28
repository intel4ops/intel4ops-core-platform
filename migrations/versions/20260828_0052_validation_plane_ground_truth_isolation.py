"""P3.xxD.1B: Validation Plane -- structurally isolated ground-truth
simulation scoring.

Six new tables, none of which AnalysisCase orchestration ever queries:
validation_simulations, validation_ground_truths,
validation_expected_findings, simulation_validation_runs,
validation_finding_matches, validation_scores. ValidationSimulation links
to AnalysisCase by a one-way reference (analysis_case_id) -- no reciprocal
column exists on analysis_cases or analysis_case_runs, and no production
query joins these tables (see tests/test_validation_import_boundary.py and
tests/test_validation_isolation.py).

Named simulation_validation_runs (not validation_runs) because
validation_runs already exists as an unrelated CI/release-gate
certification table (app/models/certification.py) -- see
app/models/ground_truth_validation.py's module docstring for the full
naming rationale.

Revision ID: 20260828_0052
Revises: 20260827_0051
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260828_0052"
down_revision: str | None = "20260827_0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "validation_simulations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("simulation_code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("analysis_case_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["analysis_case_id"], ["analysis_cases.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "simulation_code", name="uq_validation_simulation_code"
        ),
    )
    op.create_index("ix_validation_simulations_org", "validation_simulations", ["organization_id"])

    op.create_table(
        "validation_ground_truths",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("simulation_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("storage_reference", sa.String(length=500), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column(
            "expected_clean_areas",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "tolerance",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("raw_format_version", sa.String(length=20), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["simulation_id"], ["validation_simulations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "simulation_id", "version", name="uq_validation_ground_truth_simulation_version"
        ),
    )
    op.create_index(
        "ix_validation_ground_truths_org", "validation_ground_truths", ["organization_id"]
    )

    op.create_table(
        "simulation_validation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("simulation_id", sa.Uuid(), nullable=False),
        sa.Column("ground_truth_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_case_run_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("triggered_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'failed')",
            name="ck_simulation_validation_run_status",
        ),
        sa.ForeignKeyConstraint(
            ["analysis_case_run_id"], ["analysis_case_runs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["ground_truth_id"], ["validation_ground_truths.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["simulation_id"], ["validation_simulations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_simulation_validation_runs_org_sim",
        "simulation_validation_runs",
        ["organization_id", "simulation_id"],
    )

    op.create_table(
        "validation_expected_findings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("ground_truth_id", sa.Uuid(), nullable=False),
        sa.Column("expected_finding_code", sa.String(length=100), nullable=False),
        sa.Column("domain", sa.String(length=100), nullable=False),
        sa.Column("severity", sa.String(length=50), nullable=False),
        sa.Column(
            "entities",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "evidence_refs",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("expected_economic_impact", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["ground_truth_id"], ["validation_ground_truths.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ground_truth_id", "expected_finding_code", name="uq_validation_expected_finding_code"
        ),
    )
    op.create_index(
        "ix_validation_expected_findings_org", "validation_expected_findings", ["organization_id"]
    )

    op.create_table(
        "validation_scores",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("validation_run_id", sa.Uuid(), nullable=False),
        sa.Column("true_positive_count", sa.Integer(), nullable=False),
        sa.Column("false_positive_count", sa.Integer(), nullable=False),
        sa.Column("false_negative_count", sa.Integer(), nullable=False),
        sa.Column("precision", sa.Float(), nullable=True),
        sa.Column("recall", sa.Float(), nullable=True),
        sa.Column("f1", sa.Float(), nullable=True),
        sa.Column("severity_accuracy", sa.Float(), nullable=True),
        sa.Column("entity_accuracy", sa.Float(), nullable=True),
        sa.Column("evidence_accuracy", sa.Float(), nullable=True),
        sa.Column("economic_variance_avg_pct", sa.Float(), nullable=True),
        sa.Column("critical_leakage_recall", sa.Float(), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["validation_run_id"], ["simulation_validation_runs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("validation_run_id", name="uq_validation_score_run"),
    )

    op.create_table(
        "validation_finding_matches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("validation_run_id", sa.Uuid(), nullable=False),
        sa.Column("match_type", sa.String(length=20), nullable=False),
        sa.Column("expected_finding_id", sa.Uuid(), nullable=True),
        sa.Column("actual_finding_id", sa.Uuid(), nullable=True),
        sa.Column("severity_match", sa.Boolean(), nullable=True),
        sa.Column("entity_match", sa.Boolean(), nullable=True),
        sa.Column("evidence_match", sa.Boolean(), nullable=True),
        sa.Column("economic_variance_pct", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "match_type IN ('true_positive', 'false_positive', 'false_negative')",
            name="ck_validation_finding_match_type",
        ),
        sa.CheckConstraint(
            "expected_finding_id IS NOT NULL OR actual_finding_id IS NOT NULL",
            name="ck_validation_finding_match_has_side",
        ),
        sa.ForeignKeyConstraint(["actual_finding_id"], ["findings.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["expected_finding_id"], ["validation_expected_findings.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["validation_run_id"], ["simulation_validation_runs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_validation_finding_matches_run", "validation_finding_matches", ["validation_run_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_validation_finding_matches_run", table_name="validation_finding_matches")
    op.drop_table("validation_finding_matches")
    op.drop_table("validation_scores")
    op.drop_index("ix_validation_expected_findings_org", table_name="validation_expected_findings")
    op.drop_table("validation_expected_findings")
    op.drop_index("ix_simulation_validation_runs_org_sim", table_name="simulation_validation_runs")
    op.drop_table("simulation_validation_runs")
    op.drop_index("ix_validation_ground_truths_org", table_name="validation_ground_truths")
    op.drop_table("validation_ground_truths")
    op.drop_index("ix_validation_simulations_org", table_name="validation_simulations")
    op.drop_table("validation_simulations")
