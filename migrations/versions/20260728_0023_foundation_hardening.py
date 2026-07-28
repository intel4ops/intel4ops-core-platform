"""Harden Phase 1 foundation invariants.

Revision ID: 20260728_0023
Revises: 20260728_0022
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "20260728_0023"
down_revision: str | None = "20260728_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ALLOWED_VALUES = {
    ("organizations", "status"): {"active", "inactive"},
    ("findings", "severity"): {"info", "low", "medium", "high", "critical"},
    (
        "findings",
        "status",
    ): {
        "draft",
        "published",
        "under_review",
        "confirmed",
        "dismissed",
        "superseded",
        "resolved",
        "archived",
        "open",
        "accepted",
        "in_recovery",
        "verified",
    },
    ("recovery_actions", "status"): {"planned"},
}


def _validate_existing_values() -> None:
    if context.is_offline_mode():
        return
    bind = op.get_bind()
    for (table, column), allowed in ALLOWED_VALUES.items():
        values = set(
            bind.execute(
                sa.text(f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL")
            ).scalars()
        )
        unexpected = values - allowed
        if unexpected:
            rendered = ", ".join(sorted(str(value) for value in unexpected))
            raise RuntimeError(
                f"Cannot apply foundation constraints: unexpected {table}.{column} "
                f"value(s): {rendered}"
            )


def upgrade() -> None:
    _validate_existing_values()
    with op.batch_alter_table("organizations") as batch:
        batch.create_check_constraint(
            "ck_organizations_status",
            "status IN ('active', 'inactive')",
        )
    with op.batch_alter_table("findings") as batch:
        batch.create_check_constraint(
            "ck_findings_severity",
            "severity IN ('info', 'low', 'medium', 'high', 'critical')",
        )
        batch.create_check_constraint(
            "ck_findings_status",
            "status IN ('draft', 'published', 'under_review', 'confirmed', "
            "'dismissed', 'superseded', 'resolved', 'archived', 'open', "
            "'accepted', 'in_recovery', 'verified')",
        )
    with op.batch_alter_table("recovery_actions") as batch:
        batch.create_check_constraint(
            "ck_recovery_actions_status",
            "status IN ('planned')",
        )
    with op.batch_alter_table("processing_runs") as batch:
        batch.create_check_constraint(
            "ck_processing_runs_data_anchor",
            "run_type IN ('integrity_verification', 'custom') "
            "OR ingestion_batch_id IS NOT NULL OR dataset_version_id IS NOT NULL",
        )
    with op.batch_alter_table("trust_assessments") as batch:
        batch.add_column(sa.Column("idempotency_key", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("request_fingerprint", sa.String(length=64), nullable=True))
        batch.create_check_constraint(
            "ck_trust_assessment_idempotency_pair",
            "(idempotency_key IS NULL AND request_fingerprint IS NULL) OR "
            "(idempotency_key IS NOT NULL AND request_fingerprint IS NOT NULL)",
        )
        batch.create_unique_constraint(
            "uq_trust_assessments_organization_idempotency",
            ["organization_id", "idempotency_key"],
        )


def downgrade() -> None:
    with op.batch_alter_table("trust_assessments") as batch:
        batch.drop_constraint(
            "uq_trust_assessments_organization_idempotency",
            type_="unique",
        )
        batch.drop_constraint("ck_trust_assessment_idempotency_pair", type_="check")
        batch.drop_column("request_fingerprint")
        batch.drop_column("idempotency_key")
    with op.batch_alter_table("processing_runs") as batch:
        batch.drop_constraint("ck_processing_runs_data_anchor", type_="check")
    with op.batch_alter_table("recovery_actions") as batch:
        batch.drop_constraint("ck_recovery_actions_status", type_="check")
    with op.batch_alter_table("findings") as batch:
        batch.drop_constraint("ck_findings_status", type_="check")
        batch.drop_constraint("ck_findings_severity", type_="check")
    with op.batch_alter_table("organizations") as batch:
        batch.drop_constraint("ck_organizations_status", type_="check")
