"""oikb governed definition registry

Revision ID: 20260725_0010
Revises: 20260725_0009
Create Date: 2026-07-25 14:17:17.400359
"""

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

revision: str = "20260725_0010"
down_revision: str | None = "20260725_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _seed_governed_definitions() -> None:
    offline = context.is_offline_mode()
    json_type = (
        sa.Text()
        if offline
        else sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql")
    )

    def seed_json(value: object) -> object:
        return json.dumps(value, sort_keys=True) if offline else value

    definitions = sa.table(
        "oikb_definitions",
        sa.column("id", sa.Uuid()),
        sa.column("stable_code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("knowledge_class", sa.String()),
        sa.column("analytical_level", sa.String()),
        sa.column("domain", sa.String()),
        sa.column("subdomain", sa.String()),
        sa.column("owner_organization_id", sa.Uuid()),
        sa.column("industry_pack_code", sa.String()),
        sa.column("region_code", sa.String()),
        sa.column("scope_type", sa.String()),
        sa.column("scope_key", sa.String()),
        sa.column("is_system_definition", sa.Boolean()),
        sa.column("created_by", sa.Uuid()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    versions = sa.table(
        "oikb_definition_versions",
        sa.column("id", sa.Uuid()),
        sa.column("definition_id", sa.Uuid()),
        sa.column("semantic_version", sa.String()),
        sa.column("lifecycle_status", sa.String()),
        sa.column("quality_level", sa.String()),
        sa.column("effective_from", sa.DateTime(timezone=True)),
        sa.column("effective_to", sa.DateTime(timezone=True)),
        sa.column("expression_schema", json_type),
        sa.column("output_type", sa.String()),
        sa.column("output_unit", sa.String()),
        sa.column("currency_code", sa.String()),
        sa.column("rounding_policy", json_type),
        sa.column("null_policy", sa.String()),
        sa.column("zero_denominator_policy", sa.String()),
        sa.column("trust_requirement", json_type),
        sa.column("readiness_requirement", json_type),
        sa.column("fingerprint", sa.String()),
        sa.column("validation_satisfied", sa.Boolean()),
        sa.column("created_by", sa.Uuid()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("activated_by", sa.Uuid()),
        sa.column("activated_at", sa.DateTime(timezone=True)),
    )
    inputs = sa.table(
        "oikb_input_requirements",
        sa.column("id", sa.Uuid()),
        sa.column("definition_version_id", sa.Uuid()),
        sa.column("input_code", sa.String()),
        sa.column("canonical_entity", sa.String()),
        sa.column("canonical_field", sa.String()),
        sa.column("required", sa.Boolean()),
        sa.column("expected_type", sa.String()),
        sa.column("expected_unit", sa.String()),
        sa.column("currency_code", sa.String()),
        sa.column("minimum_record_count", sa.Integer()),
        sa.column("allowed_null_percentage", sa.Numeric()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    evidence = sa.table(
        "oikb_evidence_requirements",
        sa.column("id", sa.Uuid()),
        sa.column("definition_version_id", sa.Uuid()),
        sa.column("evidence_type", sa.String()),
        sa.column("requirement_code", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("required", sa.Boolean()),
        sa.column("minimum_count", sa.Integer()),
        sa.column("retention_class", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    sources = sa.table(
        "oikb_sources",
        sa.column("id", sa.Uuid()),
        sa.column("source_type", sa.String()),
        sa.column("title", sa.String()),
        sa.column("publisher", sa.String()),
        sa.column("citation", sa.Text()),
        sa.column("source_uri", sa.String()),
        sa.column("publication_date", sa.Date()),
        sa.column("authority_level", sa.String()),
        sa.column("notes", sa.Text()),
        sa.column("owner_organization_id", sa.Uuid()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    links = sa.table(
        "oikb_definition_sources",
        sa.column("id", sa.Uuid()),
        sa.column("definition_version_id", sa.Uuid()),
        sa.column("source_id", sa.Uuid()),
        sa.column("relationship_type", sa.String()),
        sa.column("is_primary", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    cases = sa.table(
        "oikb_validation_cases",
        sa.column("id", sa.Uuid()),
        sa.column("definition_version_id", sa.Uuid()),
        sa.column("case_code", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("input_payload", json_type),
        sa.column("expected_output", json_type),
        sa.column("tolerance", sa.String()),
        sa.column("expected_status", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    approvals = sa.table(
        "oikb_approvals",
        sa.column("id", sa.Uuid()),
        sa.column("definition_version_id", sa.Uuid()),
        sa.column("approval_role", sa.String()),
        sa.column("approver_id", sa.Uuid()),
        sa.column("decision", sa.String()),
        sa.column("notes", sa.Text()),
        sa.column("decided_at", sa.DateTime(timezone=True)),
    )
    now = datetime(2026, 7, 25, tzinfo=UTC)
    actor = uuid5(NAMESPACE_URL, "intel4ops:oikb:system-seed-actor")
    source_id = uuid5(NAMESPACE_URL, "intel4ops:oikb:wp-2.10-provenance")
    op.bulk_insert(
        sources,
        [
            {
                "id": source_id,
                "source_type": "internal_governance",
                "title": "Intel4Ops WP-2.10 governed seed review",
                "publisher": "Intel4Ops",
                "citation": "WP-2.10 architecture-approved provisional seed library.",
                "source_uri": None,
                "publication_date": None,
                "authority_level": "intel4ops_proprietary",
                "notes": "Provisional definitions; not a regulatory or standards claim.",
                "owner_organization_id": None,
                "created_at": now,
            }
        ],
    )
    seed_specs = [
        (
            "SHARED.FINANCE.OUTSTANDING_BALANCE",
            "Outstanding balance",
            "reconciliation",
            "currency",
            "currency",
            "USD",
            "invoice_balance",
        ),
        (
            "SHARED.FINANCE.PAYMENT_VARIANCE",
            "Payment variance",
            "absolute_variance",
            "currency",
            "currency",
            "USD",
            "payment_amount",
        ),
        (
            "SHARED.OPERATIONS.THROUGHPUT",
            "Operational throughput",
            "count",
            "count",
            "integer",
            None,
            "completed_record",
        ),
        (
            "SHARED.OPERATIONS.BACKLOG",
            "Operational backlog",
            "count",
            "count",
            "integer",
            None,
            "open_record",
        ),
        (
            "SHARED.OPERATIONS.ABSOLUTE_VARIANCE",
            "Absolute variance",
            "absolute_variance",
            "unit",
            "decimal",
            None,
            "actual_value",
        ),
        (
            "SHARED.OPERATIONS.PERCENTAGE_VARIANCE",
            "Percentage variance",
            "percentage_variance",
            "percent",
            "decimal",
            None,
            "actual_value",
        ),
        (
            "SHARED.QUALITY.DEFECT_RATE",
            "Defect rate",
            "percentage",
            "percent",
            "decimal",
            None,
            "defect_count",
        ),
        (
            "JOB_TO_CASH.REVENUE.COMPLETED_NOT_INVOICED",
            "Completed not invoiced",
            "sum",
            "currency",
            "currency",
            "USD",
            "uninvoiced_amount",
        ),
        (
            "JOB_TO_CASH.REVENUE.UNBILLED_REVENUE",
            "Unbilled revenue",
            "sum",
            "currency",
            "currency",
            "USD",
            "unbilled_amount",
        ),
        (
            "MOBILITY.FUEL.FUEL_VARIANCE",
            "Fuel variance",
            "absolute_variance",
            "volume",
            "decimal",
            None,
            "actual_fuel",
        ),
    ]
    for code, name, operation, unit, output_type, currency, input_code in seed_specs:
        definition_id = uuid5(NAMESPACE_URL, f"intel4ops:oikb:definition:{code}")
        version_id = uuid5(NAMESPACE_URL, f"intel4ops:oikb:version:{code}:1.0.0")
        expression = {"operation": operation, "inputs": [input_code], "parameters": {}}
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "code": code,
                    "version": "1.0.0",
                    "expression": expression,
                    "unit": unit,
                    "currency": currency,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        domain = code.split(".")[1]
        op.bulk_insert(
            definitions,
            [
                {
                    "id": definition_id,
                    "stable_code": code,
                    "name": name,
                    "description": f"Provisional governed definition for {name.lower()}.",
                    "knowledge_class": "kpi",
                    "analytical_level": "arithmetic",
                    "domain": domain.lower(),
                    "subdomain": None,
                    "owner_organization_id": None,
                    "industry_pack_code": None,
                    "region_code": None,
                    "scope_type": "shared_core",
                    "scope_key": "shared_core",
                    "is_system_definition": True,
                    "created_by": actor,
                    "created_at": now,
                    "updated_at": now,
                }
            ],
        )
        op.bulk_insert(
            versions,
            [
                {
                    "id": version_id,
                    "definition_id": definition_id,
                    "semantic_version": "1.0.0",
                    "lifecycle_status": "active",
                    "quality_level": "provisional",
                    "effective_from": now,
                    "effective_to": None,
                    "expression_schema": seed_json(expression),
                    "output_type": output_type,
                    "output_unit": unit,
                    "currency_code": currency,
                    "rounding_policy": seed_json({"mode": "half_even", "decimal_places": 2}),
                    "null_policy": "exclude",
                    "zero_denominator_policy": "error",
                    "trust_requirement": seed_json({"minimum_status": "completed"}),
                    "readiness_requirement": seed_json({"analytical_level": "arithmetic"}),
                    "fingerprint": fingerprint,
                    "validation_satisfied": True,
                    "created_by": actor,
                    "created_at": now,
                    "activated_by": actor,
                    "activated_at": now,
                }
            ],
        )
        op.bulk_insert(
            inputs,
            [
                {
                    "id": uuid5(NAMESPACE_URL, f"intel4ops:oikb:input:{code}:{input_code}"),
                    "definition_version_id": version_id,
                    "input_code": input_code,
                    "canonical_entity": "governed_record",
                    "canonical_field": input_code,
                    "required": True,
                    "expected_type": output_type,
                    "expected_unit": unit,
                    "currency_code": currency,
                    "minimum_record_count": 1,
                    "allowed_null_percentage": 0,
                    "created_at": now,
                }
            ],
        )
        op.bulk_insert(
            evidence,
            [
                {
                    "id": uuid5(NAMESPACE_URL, f"intel4ops:oikb:evidence:{code}"),
                    "definition_version_id": version_id,
                    "evidence_type": "calculation_trace",
                    "requirement_code": "BOUNDED_CALCULATION_TRACE",
                    "description": "Dataset lineage, Trust, readiness, and calculation trace.",
                    "required": True,
                    "minimum_count": 1,
                    "retention_class": "governed_reference",
                    "created_at": now,
                }
            ],
        )
        op.bulk_insert(
            links,
            [
                {
                    "id": uuid5(NAMESPACE_URL, f"intel4ops:oikb:source-link:{code}"),
                    "definition_version_id": version_id,
                    "source_id": source_id,
                    "relationship_type": "governance_provenance",
                    "is_primary": True,
                    "created_at": now,
                }
            ],
        )
        op.bulk_insert(
            approvals,
            [
                {
                    "id": uuid5(NAMESPACE_URL, f"intel4ops:oikb:approval:{code}"),
                    "definition_version_id": version_id,
                    "approval_role": "oikb_system_seed_approver",
                    "approver_id": actor,
                    "decision": "approved",
                    "notes": "Approved as a provisional architecture seed.",
                    "decided_at": now,
                }
            ],
        )
        case_specs: tuple[tuple[str, dict[str, object], object], ...]
        if operation == "count":
            case_specs = (
                ("NORMAL_CASE", {"values": [1, 2]}, 2),
                ("ZERO_CASE", {"values": []}, 0),
            )
        elif operation == "sum":
            case_specs = (
                ("NORMAL_CASE", {"values": [1, 2]}, "3"),
                ("ZERO_CASE", {"values": []}, "0"),
            )
        elif operation in {"absolute_variance", "reconciliation"}:
            case_specs = (
                ("NORMAL_CASE", {"left": 2, "right": 1}, "1"),
                ("ZERO_CASE", {"left": 0, "right": 0}, "0"),
            )
        elif operation == "percentage_variance":
            case_specs = (
                ("NORMAL_CASE", {"left": 3, "right": 2}, "50"),
                ("ZERO_CASE", {"left": 1, "right": 1}, "0"),
            )
        else:
            case_specs = (
                ("NORMAL_CASE", {"left": 1, "right": 2}, "50"),
                ("ZERO_CASE", {"left": 0, "right": 1}, "0"),
            )
        for case_code, payload, expected in case_specs:
            op.bulk_insert(
                cases,
                [
                    {
                        "id": uuid5(NAMESPACE_URL, f"intel4ops:oikb:case:{code}:{case_code}"),
                        "definition_version_id": version_id,
                        "case_code": case_code,
                        "description": f"{case_code.replace('_', ' ').title()} seed validation.",
                        "input_payload": seed_json(payload),
                        "expected_output": seed_json(expected),
                        "tolerance": "0",
                        "expected_status": "completed",
                        "created_at": now,
                        "updated_at": now,
                    }
                ],
            )


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "oikb_definitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("stable_code", sa.String(length=150), nullable=False),
        sa.Column("name", sa.String(length=250), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("knowledge_class", sa.String(length=50), nullable=False),
        sa.Column("analytical_level", sa.String(length=30), nullable=False),
        sa.Column("domain", sa.String(length=100), nullable=False),
        sa.Column("subdomain", sa.String(length=100), nullable=True),
        sa.Column("owner_organization_id", sa.Uuid(), nullable=True),
        sa.Column("industry_pack_code", sa.String(length=100), nullable=True),
        sa.Column("region_code", sa.String(length=30), nullable=True),
        sa.Column("scope_type", sa.String(length=30), nullable=False),
        sa.Column("scope_key", sa.String(length=180), nullable=False),
        sa.Column("is_system_definition", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "scope_type IN ('shared_core','industry','regional','organization')",
            name="ck_oikb_definition_scope_type",
        ),
        sa.ForeignKeyConstraint(
            ["owner_organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stable_code", "scope_key", name="uq_oikb_definition_scope"),
    )
    op.create_index("ix_oikb_definition_code", "oikb_definitions", ["stable_code"], unique=False)
    op.create_index(
        "ix_oikb_definition_owner", "oikb_definitions", ["owner_organization_id"], unique=False
    )
    op.create_index(
        "ix_oikb_definition_resolution",
        "oikb_definitions",
        ["stable_code", "scope_type"],
        unique=False,
    )
    op.create_table(
        "oikb_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=250), nullable=False),
        sa.Column("publisher", sa.String(length=200), nullable=False),
        sa.Column("citation", sa.Text(), nullable=False),
        sa.Column("source_uri", sa.String(length=1000), nullable=True),
        sa.Column("publication_date", sa.Date(), nullable=True),
        sa.Column("authority_level", sa.String(length=50), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("owner_organization_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_oikb_source_authority", "oikb_sources", ["authority_level"], unique=False)
    op.create_index(
        op.f("ix_oikb_sources_owner_organization_id"),
        "oikb_sources",
        ["owner_organization_id"],
        unique=False,
    )
    op.create_table(
        "oikb_definition_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("definition_id", sa.Uuid(), nullable=False),
        sa.Column("semantic_version", sa.String(length=30), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=30), nullable=False),
        sa.Column("quality_level", sa.String(length=30), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "expression_schema",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("output_type", sa.String(length=50), nullable=False),
        sa.Column("output_unit", sa.String(length=50), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=True),
        sa.Column(
            "rounding_policy",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("null_policy", sa.String(length=50), nullable=False),
        sa.Column("zero_denominator_policy", sa.String(length=50), nullable=False),
        sa.Column(
            "trust_requirement",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "readiness_requirement",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("validation_satisfied", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_by", sa.Uuid(), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "lifecycle_status IN "
            "('draft','in_review','validated','approved','active','deprecated',"
            "'retired','rejected')",
            name="ck_oikb_version_lifecycle",
        ),
        sa.CheckConstraint(
            "quality_level IN "
            "('experimental','provisional','validated','production','reference_grade')",
            name="ck_oikb_version_quality",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to > effective_from",
            name="ck_oikb_version_effective_dates",
        ),
        sa.ForeignKeyConstraint(["definition_id"], ["oikb_definitions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("definition_id", "fingerprint", name="uq_oikb_definition_fingerprint"),
        sa.UniqueConstraint(
            "definition_id", "semantic_version", name="uq_oikb_definition_semantic_version"
        ),
    )
    op.create_index(
        "ix_oikb_version_definition", "oikb_definition_versions", ["definition_id"], unique=False
    )
    op.create_index(
        "ix_oikb_version_status_effective",
        "oikb_definition_versions",
        ["lifecycle_status", "effective_from"],
        unique=False,
    )
    op.create_index(
        "uq_oikb_one_active_version",
        "oikb_definition_versions",
        ["definition_id"],
        unique=True,
        postgresql_where=sa.text("lifecycle_status = 'active'"),
        sqlite_where=sa.text("lifecycle_status = 'active'"),
    )
    op.create_table(
        "oikb_relationships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_definition_id", sa.Uuid(), nullable=False),
        sa.Column("target_definition_id", sa.Uuid(), nullable=False),
        sa.Column("relationship_type", sa.String(length=50), nullable=False),
        sa.Column(
            "metadata_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_definition_id"], ["oikb_definitions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["target_definition_id"], ["oikb_definitions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_definition_id",
            "target_definition_id",
            "relationship_type",
            name="uq_oikb_relationship",
        ),
    )
    op.create_table(
        "oikb_approvals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("definition_version_id", sa.Uuid(), nullable=False),
        sa.Column("approval_role", sa.String(length=50), nullable=False),
        sa.Column("approver_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=30), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["definition_version_id"], ["oikb_definition_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_oikb_approvals_definition_version_id"),
        "oikb_approvals",
        ["definition_version_id"],
        unique=False,
    )
    op.create_table(
        "oikb_change_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("definition_id", sa.Uuid(), nullable=False),
        sa.Column("definition_version_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("previous_state", sa.String(length=30), nullable=True),
        sa.Column("new_state", sa.String(length=30), nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["definition_id"], ["oikb_definitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["definition_version_id"], ["oikb_definition_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_oikb_change_definition_time",
        "oikb_change_log",
        ["definition_id", "occurred_at"],
        unique=False,
    )
    op.create_table(
        "oikb_definition_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("definition_version_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("relationship_type", sa.String(length=50), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["definition_version_id"], ["oikb_definition_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["source_id"], ["oikb_sources.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("definition_version_id", "source_id", name="uq_oikb_definition_source"),
    )
    op.create_index(
        op.f("ix_oikb_definition_sources_definition_version_id"),
        "oikb_definition_sources",
        ["definition_version_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_oikb_definition_sources_source_id"),
        "oikb_definition_sources",
        ["source_id"],
        unique=False,
    )
    op.create_table(
        "oikb_evidence_requirements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("definition_version_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_type", sa.String(length=50), nullable=False),
        sa.Column("requirement_code", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("minimum_count", sa.Integer(), nullable=False),
        sa.Column("retention_class", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["definition_version_id"], ["oikb_definition_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "definition_version_id", "requirement_code", name="uq_oikb_evidence_requirement"
        ),
    )
    op.create_index(
        op.f("ix_oikb_evidence_requirements_definition_version_id"),
        "oikb_evidence_requirements",
        ["definition_version_id"],
        unique=False,
    )
    op.create_table(
        "oikb_input_requirements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("definition_version_id", sa.Uuid(), nullable=False),
        sa.Column("input_code", sa.String(length=100), nullable=False),
        sa.Column("canonical_entity", sa.String(length=100), nullable=False),
        sa.Column("canonical_field", sa.String(length=100), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("expected_type", sa.String(length=30), nullable=False),
        sa.Column("expected_unit", sa.String(length=50), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=True),
        sa.Column("minimum_record_count", sa.Integer(), nullable=False),
        sa.Column("allowed_null_percentage", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "allowed_null_percentage >= 0 AND allowed_null_percentage <= 100",
            name="ck_oikb_input_null_percentage",
        ),
        sa.ForeignKeyConstraint(
            ["definition_version_id"], ["oikb_definition_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "definition_version_id", "input_code", name="uq_oikb_input_requirement_code"
        ),
    )
    op.create_index(
        op.f("ix_oikb_input_requirements_definition_version_id"),
        "oikb_input_requirements",
        ["definition_version_id"],
        unique=False,
    )
    op.create_table(
        "oikb_parameters",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("definition_version_id", sa.Uuid(), nullable=False),
        sa.Column("parameter_code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("data_type", sa.String(length=30), nullable=False),
        sa.Column(
            "default_value",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("minimum_value", sa.String(length=100), nullable=True),
        sa.Column("maximum_value", sa.String(length=100), nullable=True),
        sa.Column(
            "allowed_values",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("unit", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["definition_version_id"], ["oikb_definition_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "definition_version_id", "parameter_code", name="uq_oikb_parameter_code"
        ),
    )
    op.create_index(
        op.f("ix_oikb_parameters_definition_version_id"),
        "oikb_parameters",
        ["definition_version_id"],
        unique=False,
    )
    op.create_table(
        "oikb_validation_cases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("definition_version_id", sa.Uuid(), nullable=False),
        sa.Column("case_code", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "input_payload",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "expected_output",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("tolerance", sa.String(length=100), nullable=True),
        sa.Column("expected_status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["definition_version_id"], ["oikb_definition_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("definition_version_id", "case_code", name="uq_oikb_validation_case"),
    )
    op.create_index(
        op.f("ix_oikb_validation_cases_definition_version_id"),
        "oikb_validation_cases",
        ["definition_version_id"],
        unique=False,
    )
    op.create_table(
        "oikb_validation_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("definition_version_id", sa.Uuid(), nullable=False),
        sa.Column("validation_case_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column(
            "actual_output",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("variance", sa.String(length=100), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("executed_by", sa.Uuid(), nullable=False),
        sa.Column("engine_version", sa.String(length=50), nullable=False),
        sa.Column("definition_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["definition_version_id"], ["oikb_definition_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["validation_case_id"], ["oikb_validation_cases.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_oikb_validation_results_definition_version_id"),
        "oikb_validation_results",
        ["definition_version_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_oikb_validation_results_validation_case_id"),
        "oikb_validation_results",
        ["validation_case_id"],
        unique=False,
    )
    op.add_column("findings", sa.Column("oikb_definition_id", sa.Uuid(), nullable=True))
    op.add_column("findings", sa.Column("oikb_definition_version_id", sa.Uuid(), nullable=True))
    with op.batch_alter_table("findings") as batch_op:
        batch_op.create_foreign_key(
            "fk_findings_oikb_definition",
            "oikb_definitions",
            ["oikb_definition_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "fk_findings_oikb_definition_version",
            "oikb_definition_versions",
            ["oikb_definition_version_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index(
            "ix_findings_oikb_definition",
            ["organization_id", "oikb_definition_id", "oikb_definition_version_id"],
        )
    _seed_governed_definitions()
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("findings") as batch_op:
        batch_op.drop_index("ix_findings_oikb_definition")
        batch_op.drop_constraint("fk_findings_oikb_definition_version", type_="foreignkey")
        batch_op.drop_constraint("fk_findings_oikb_definition", type_="foreignkey")
        batch_op.drop_column("oikb_definition_version_id")
        batch_op.drop_column("oikb_definition_id")
    op.drop_index(
        op.f("ix_oikb_validation_results_validation_case_id"), table_name="oikb_validation_results"
    )
    op.drop_index(
        op.f("ix_oikb_validation_results_definition_version_id"),
        table_name="oikb_validation_results",
    )
    op.drop_table("oikb_validation_results")
    op.drop_index(
        op.f("ix_oikb_validation_cases_definition_version_id"), table_name="oikb_validation_cases"
    )
    op.drop_table("oikb_validation_cases")
    op.drop_index(op.f("ix_oikb_parameters_definition_version_id"), table_name="oikb_parameters")
    op.drop_table("oikb_parameters")
    op.drop_index(
        op.f("ix_oikb_input_requirements_definition_version_id"),
        table_name="oikb_input_requirements",
    )
    op.drop_table("oikb_input_requirements")
    op.drop_index(
        op.f("ix_oikb_evidence_requirements_definition_version_id"),
        table_name="oikb_evidence_requirements",
    )
    op.drop_table("oikb_evidence_requirements")
    op.drop_index(
        op.f("ix_oikb_definition_sources_source_id"), table_name="oikb_definition_sources"
    )
    op.drop_index(
        op.f("ix_oikb_definition_sources_definition_version_id"),
        table_name="oikb_definition_sources",
    )
    op.drop_table("oikb_definition_sources")
    op.drop_index("ix_oikb_change_definition_time", table_name="oikb_change_log")
    op.drop_table("oikb_change_log")
    op.drop_index(op.f("ix_oikb_approvals_definition_version_id"), table_name="oikb_approvals")
    op.drop_table("oikb_approvals")
    op.drop_table("oikb_relationships")
    op.drop_index("uq_oikb_one_active_version", table_name="oikb_definition_versions")
    op.drop_index("ix_oikb_version_status_effective", table_name="oikb_definition_versions")
    op.drop_index("ix_oikb_version_definition", table_name="oikb_definition_versions")
    op.drop_table("oikb_definition_versions")
    op.drop_index(op.f("ix_oikb_sources_owner_organization_id"), table_name="oikb_sources")
    op.drop_index("ix_oikb_source_authority", table_name="oikb_sources")
    op.drop_table("oikb_sources")
    op.drop_index("ix_oikb_definition_resolution", table_name="oikb_definitions")
    op.drop_index("ix_oikb_definition_owner", table_name="oikb_definitions")
    op.drop_index("ix_oikb_definition_code", table_name="oikb_definitions")
    op.drop_table("oikb_definitions")
    # ### end Alembic commands ###
