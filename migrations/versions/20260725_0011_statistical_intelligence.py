"""statistical intelligence and anomaly detection

Revision ID: 20260725_0011
Revises: 20260725_0010
Create Date: 2026-07-25 16:27:41.428846
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

revision: str = "20260725_0011"
down_revision: str | None = "20260725_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED_SPECS = (
    ("SHARED.STATISTICS.UNIVARIATE_OUTLIER", "Univariate outlier", "Z_SCORE"),
    ("SHARED.STATISTICS.ROBUST_OUTLIER", "Robust outlier", "MODIFIED_Z_SCORE"),
    ("SHARED.STATISTICS.ROLLING_DEVIATION", "Rolling deviation", "ROLLING_Z_SCORE"),
    ("SHARED.STATISTICS.PEER_GROUP_DEVIATION", "Peer group deviation", "PEER_MODIFIED_Z_SCORE"),
    ("SHARED.STATISTICS.TREND_CHANGE", "Trend change", "LINEAR_TREND"),
    ("SHARED.STATISTICS.LEVEL_SHIFT", "Level shift", "LEVEL_SHIFT"),
    ("SHARED.STATISTICS.VOLATILITY_CHANGE", "Volatility change", "ROLLING_MAD"),
    (
        "SHARED.STATISTICS.COMPOSITE_ANOMALY_SCORE",
        "Composite anomaly score",
        "WEIGHTED_COMPONENT_SCORE",
    ),
    (
        "JOB_TO_CASH.BILLING.INVOICE_AMOUNT_OUTLIER",
        "Invoice amount outlier",
        "MODIFIED_Z_SCORE",
    ),
    (
        "JOB_TO_CASH.REVENUE.COMPLETED_NOT_INVOICED_TREND",
        "Completed not invoiced trend",
        "LINEAR_TREND",
    ),
    (
        "MANUFACTURING.QUALITY.SCRAP_RATE_DEVIATION",
        "Scrap rate deviation",
        "ROLLING_Z_SCORE",
    ),
    (
        "MOBILITY.FUEL.CONSUMPTION_PEER_DEVIATION",
        "Fuel consumption peer deviation",
        "PEER_MODIFIED_Z_SCORE",
    ),
)

METHOD_SPECS = (
    ("COUNT", "DESCRIPTIVE_STATISTICS", 1, False, False),
    ("MISSING_COUNT", "DESCRIPTIVE_STATISTICS", 1, False, False),
    ("MEAN", "DESCRIPTIVE_STATISTICS", 1, False, False),
    ("MEDIAN", "DESCRIPTIVE_STATISTICS", 1, False, False),
    ("MODE", "DESCRIPTIVE_STATISTICS", 1, False, False),
    ("MINIMUM", "DESCRIPTIVE_STATISTICS", 1, False, False),
    ("MAXIMUM", "DESCRIPTIVE_STATISTICS", 1, False, False),
    ("RANGE", "DESCRIPTIVE_STATISTICS", 1, False, False),
    ("VARIANCE", "DESCRIPTIVE_STATISTICS", 1, False, False),
    ("STANDARD_DEVIATION", "DESCRIPTIVE_STATISTICS", 1, False, False),
    ("COEFFICIENT_OF_VARIATION", "DESCRIPTIVE_STATISTICS", 1, False, False),
    ("QUARTILES", "DESCRIPTIVE_STATISTICS", 1, False, False),
    ("INTERQUARTILE_RANGE", "DESCRIPTIVE_STATISTICS", 1, False, False),
    ("PERCENTILE", "DESCRIPTIVE_STATISTICS", 1, False, False),
    ("SKEWNESS", "DESCRIPTIVE_STATISTICS", 1, False, False),
    ("Z_SCORE", "OUTLIER_DETECTION", 3, False, False),
    ("MODIFIED_Z_SCORE", "ROBUST_OUTLIER_DETECTION", 3, False, False),
    ("IQR_RULE", "ROBUST_OUTLIER_DETECTION", 5, False, False),
    ("PERCENTILE_THRESHOLD", "OUTLIER_DETECTION", 5, False, False),
    ("STANDARD_DEVIATION_BAND", "VARIABILITY_ANALYSIS", 3, False, False),
    ("MEDIAN_BASELINE", "BASELINE_ESTIMATION", 3, False, False),
    ("TRIMMED_MEAN_BASELINE", "BASELINE_ESTIMATION", 5, False, False),
    ("WINSORIZED_MEAN_BASELINE", "BASELINE_ESTIMATION", 5, False, False),
    ("ROLLING_MEDIAN", "BASELINE_ESTIMATION", 4, True, False),
    ("ROLLING_MAD", "VARIABILITY_ANALYSIS", 4, True, False),
    ("PEER_Z_SCORE", "PEER_GROUP_DEVIATION", 4, False, True),
    ("PEER_MODIFIED_Z_SCORE", "PEER_GROUP_DEVIATION", 4, False, True),
    ("PEER_PERCENTILE", "PEER_GROUP_DEVIATION", 5, False, True),
    ("PEER_RATIO_DEVIATION", "PEER_GROUP_DEVIATION", 4, False, True),
    ("ROLLING_Z_SCORE", "TIME_SERIES_DEVIATION", 4, True, False),
    ("ROLLING_MODIFIED_Z_SCORE", "TIME_SERIES_DEVIATION", 4, True, False),
    ("ROLLING_IQR", "TIME_SERIES_DEVIATION", 6, True, False),
    ("EWMA_DEVIATION", "TIME_SERIES_DEVIATION", 4, True, False),
    ("CUSUM_CHANGE_DETECTION", "CHANGE_POINT_DETECTION", 6, True, False),
    ("LINEAR_TREND", "TREND_DETECTION", 3, True, False),
    ("SLOPE_CHANGE", "CHANGE_POINT_DETECTION", 6, True, False),
    ("LEVEL_SHIFT", "CHANGE_POINT_DETECTION", 6, True, False),
    ("WEIGHTED_COMPONENT_SCORE", "COMPOSITE_ANOMALY_SCORING", 1, False, False),
    ("MAX_COMPONENT_SCORE", "COMPOSITE_ANOMALY_SCORING", 1, False, False),
    ("ROBUST_NORMALIZED_SCORE", "COMPOSITE_ANOMALY_SCORING", 3, False, False),
)


def _seed_statistical_foundation() -> None:
    offline = context.is_offline_mode()
    json_type = (
        sa.Text()
        if offline
        else sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql")
    )

    def seed_json(value: object) -> object:
        return json.dumps(value, sort_keys=True) if offline else value

    now = datetime(2026, 7, 25, tzinfo=UTC)
    actor = uuid5(NAMESPACE_URL, "intel4ops:statistics:system-seed-actor")
    source_id = uuid5(NAMESPACE_URL, "intel4ops:statistics:wp-2.11-provenance")
    method_table = sa.table(
        "statistical_method_registry",
        sa.column("id", sa.Uuid()),
        sa.column("method_code", sa.String()),
        sa.column("method_name", sa.String()),
        sa.column("method_version", sa.String()),
        sa.column("capability_class", sa.String()),
        sa.column("supported", sa.Boolean()),
        sa.column("minimum_sample_size", sa.Integer()),
        sa.column("supports_time_series", sa.Boolean()),
        sa.column("supports_peer_group", sa.Boolean()),
        sa.column("supports_grouping", sa.Boolean()),
        sa.column("supports_weights", sa.Boolean()),
        sa.column("parameter_schema", json_type),
        sa.column("output_schema", json_type),
        sa.column("implementation_reference", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        method_table,
        [
            {
                "id": uuid5(NAMESPACE_URL, f"intel4ops:statistics:method:{code}:1.0"),
                "method_code": code,
                "method_name": code.replace("_", " ").title(),
                "method_version": "1.0",
                "capability_class": capability,
                "supported": True,
                "minimum_sample_size": minimum,
                "supports_time_series": time_series,
                "supports_peer_group": peer,
                "supports_grouping": peer,
                "supports_weights": code == "WEIGHTED_COMPONENT_SCORE",
                "parameter_schema": seed_json(
                    {"bounded": True, "arbitrary_code": False, "customer_thresholds": False}
                ),
                "output_schema": seed_json(
                    {"finite_numeric": True, "explainable": True, "score_scale": [0, 1]}
                ),
                "implementation_reference": "app.engines.statistical_engine",
                "created_at": now,
                "updated_at": now,
            }
            for code, capability, minimum, time_series, peer in METHOD_SPECS
        ],
    )
    definitions = sa.table(
        "oikb_definitions",
        *[
            sa.column(name, type_)
            for name, type_ in (
                ("id", sa.Uuid()),
                ("stable_code", sa.String()),
                ("name", sa.String()),
                ("description", sa.Text()),
                ("knowledge_class", sa.String()),
                ("analytical_level", sa.String()),
                ("domain", sa.String()),
                ("subdomain", sa.String()),
                ("owner_organization_id", sa.Uuid()),
                ("industry_pack_code", sa.String()),
                ("region_code", sa.String()),
                ("scope_type", sa.String()),
                ("scope_key", sa.String()),
                ("is_system_definition", sa.Boolean()),
                ("created_by", sa.Uuid()),
                ("created_at", sa.DateTime(timezone=True)),
                ("updated_at", sa.DateTime(timezone=True)),
            )
        ],
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
    op.bulk_insert(
        sources,
        [
            {
                "id": source_id,
                "source_type": "internal_governance",
                "title": "Intel4Ops WP-2.11 bounded statistical method design",
                "publisher": "Intel4Ops",
                "citation": "WP-2.11 governed statistical seed library.",
                "source_uri": None,
                "publication_date": None,
                "authority_level": "intel4ops_proprietary",
                "notes": "Explainable deterministic methods; no causal or misconduct claims.",
                "owner_organization_id": None,
                "created_at": now,
            }
        ],
    )
    validation_codes = (
        "NORMAL_NO_ANOMALY",
        "SINGLE_EXTREME_OUTLIER",
        "MULTIPLE_MODERATE_OUTLIERS",
        "INSUFFICIENT_SAMPLE",
        "MISSING_WITHIN_TOLERANCE",
        "MISSING_ABOVE_TOLERANCE",
        "ZERO_VARIANCE",
        "NEGATIVE_VALUES",
        "MIXED_UNITS",
        "PEER_BELOW_MINIMUM",
        "INCOMPLETE_TIME_SERIES",
        "DUPLICATED_PERIODS",
        "LEVEL_SHIFT",
        "GRADUAL_TREND",
        "VOLATILITY_INCREASE",
        "FALSE_POSITIVE_SUPPRESSION",
        "MATERIAL_MODERATE_DEVIATION",
        "EXTREME_IMMATERIAL_DEVIATION",
        "UNAUTHORIZED_TENANT",
        "INACTIVE_DEFINITION",
        "UNSUPPORTED_METHOD",
    )
    for code, name, method in SEED_SPECS:
        definition_id = uuid5(NAMESPACE_URL, f"intel4ops:oikb:definition:{code}")
        version_id = uuid5(NAMESPACE_URL, f"intel4ops:oikb:version:{code}:1.0.0")
        expression = {
            "operation": method,
            "method_version": "1.0",
            "baseline_type": ("peer_group" if method.startswith("PEER_") else "historical_self"),
            "parameters": {
                "deviation_threshold": 3.5,
                "minimum_confidence": 0.5,
                "minimum_materiality": 0.1,
                "minimum_persistence": 1,
            },
            "false_positive_controls": [
                "minimum_sample",
                "persistence",
                "suppression",
                "known_event",
                "planned_maintenance",
                "materiality",
            ],
            "limitations": ["Anomaly is not evidence of cause or misconduct"],
        }
        fingerprint = hashlib.sha256(
            json.dumps(
                {"code": code, "version": "1.0.0", "expression": expression},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        op.bulk_insert(
            definitions,
            [
                {
                    "id": definition_id,
                    "stable_code": code,
                    "name": name,
                    "description": (
                        f"Governed explainable statistical definition for {name.lower()}."
                    ),
                    "knowledge_class": "statistical_method",
                    "analytical_level": "statistical",
                    "domain": code.split(".")[1].lower(),
                    "subdomain": code.split(".")[2].lower(),
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
                    "output_type": "anomaly_assessment",
                    "output_unit": "score",
                    "currency_code": None,
                    "rounding_policy": seed_json({"mode": "half_even", "decimal_places": 5}),
                    "null_policy": "exclude_with_threshold",
                    "zero_denominator_policy": "structured_null",
                    "trust_requirement": seed_json({"minimum_status": "completed"}),
                    "readiness_requirement": seed_json(
                        {
                            "analytical_level": "statistical",
                            "minimum_sample_size": 5,
                            "minimum_peer_count": 5,
                            "maximum_missing_percentage": 10,
                            "stable_units": True,
                            "stable_currency": True,
                        }
                    ),
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
                    "id": uuid5(NAMESPACE_URL, f"intel4ops:oikb:input:{code}:observed_value"),
                    "definition_version_id": version_id,
                    "input_code": "observed_value",
                    "canonical_entity": "governed_observation",
                    "canonical_field": "observed_value",
                    "required": True,
                    "expected_type": "decimal",
                    "expected_unit": "governed_unit",
                    "currency_code": None,
                    "minimum_record_count": 5,
                    "allowed_null_percentage": 10,
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
                    "evidence_type": "statistical_execution_trace",
                    "requirement_code": "GOVERNED_STATISTICAL_TRACE",
                    "description": (
                        "Aggregate baseline, lineage, Trust, readiness, method, "
                        "score, and limitations."
                    ),
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
                    "approval_role": "oikb_statistical_seed_approver",
                    "approver_id": actor,
                    "decision": "approved",
                    "notes": "Approved as a provisional bounded statistical seed.",
                    "decided_at": now,
                }
            ],
        )
        op.bulk_insert(
            cases,
            [
                {
                    "id": uuid5(NAMESPACE_URL, f"intel4ops:oikb:case:{code}:{case_code}"),
                    "definition_version_id": version_id,
                    "case_code": case_code,
                    "description": f"Governed {case_code.lower().replace('_', ' ')} contract.",
                    "input_payload": seed_json(
                        {
                            "method": method,
                            "case": case_code,
                            "deterministic": True,
                            "raw_data_persisted": False,
                        }
                    ),
                    "expected_output": seed_json(
                        {
                            "status": (
                                "blocked"
                                if case_code
                                in {
                                    "UNAUTHORIZED_TENANT",
                                    "INACTIVE_DEFINITION",
                                    "UNSUPPORTED_METHOD",
                                }
                                else "evaluated"
                            )
                        }
                    ),
                    "tolerance": "0.00001",
                    "expected_status": "completed",
                    "created_at": now,
                    "updated_at": now,
                }
                for case_code in validation_codes
            ],
        )


def _remove_statistical_seeds() -> None:
    codes = [item[0] for item in SEED_SPECS]
    definitions = sa.table(
        "oikb_definitions",
        sa.column("id", sa.Uuid()),
        sa.column("stable_code", sa.String()),
    )
    sources = sa.table(
        "oikb_sources",
        sa.column("id", sa.Uuid()),
    )
    versions = sa.table(
        "oikb_definition_versions",
        sa.column("id", sa.Uuid()),
        sa.column("definition_id", sa.Uuid()),
    )
    version_ids = sa.select(versions.c.id).where(
        versions.c.definition_id.in_(
            sa.select(definitions.c.id).where(definitions.c.stable_code.in_(codes))
        )
    )
    for table_name in (
        "oikb_validation_results",
        "oikb_validation_cases",
        "oikb_approvals",
        "oikb_definition_sources",
        "oikb_evidence_requirements",
        "oikb_input_requirements",
        "oikb_parameters",
    ):
        child = sa.table(
            table_name,
            sa.column("definition_version_id", sa.Uuid()),
        )
        op.execute(sa.delete(child).where(child.c.definition_version_id.in_(version_ids)))
    op.execute(sa.delete(versions).where(versions.c.id.in_(version_ids)))
    op.execute(sa.delete(definitions).where(definitions.c.stable_code.in_(codes)))
    op.execute(
        sa.delete(sources).where(
            sources.c.id == uuid5(NAMESPACE_URL, "intel4ops:statistics:wp-2.11-provenance")
        )
    )


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "statistical_method_registry",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("method_code", sa.String(length=100), nullable=False),
        sa.Column("method_name", sa.String(length=200), nullable=False),
        sa.Column("method_version", sa.String(length=30), nullable=False),
        sa.Column("capability_class", sa.String(length=60), nullable=False),
        sa.Column("supported", sa.Boolean(), nullable=False),
        sa.Column("minimum_sample_size", sa.Integer(), nullable=False),
        sa.Column("supports_time_series", sa.Boolean(), nullable=False),
        sa.Column("supports_peer_group", sa.Boolean(), nullable=False),
        sa.Column("supports_grouping", sa.Boolean(), nullable=False),
        sa.Column("supports_weights", sa.Boolean(), nullable=False),
        sa.Column(
            "parameter_schema",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "output_schema",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("implementation_reference", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("method_code", "method_version", name="uq_statistical_method_version"),
    )
    op.create_index(
        "ix_statistical_method_capability",
        "statistical_method_registry",
        ["capability_class"],
        unique=False,
    )
    op.create_index(
        "ix_statistical_method_supported",
        "statistical_method_registry",
        ["supported"],
        unique=False,
    )
    op.create_table(
        "anomaly_suppression_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("definition_version_id", sa.Uuid(), nullable=False),
        sa.Column("entity_reference", sa.String(length=255), nullable=True),
        sa.Column("suppression_reason", sa.Text(), nullable=False),
        sa.Column(
            "suppression_scope",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["definition_version_id"], ["oikb_definition_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_anomaly_suppression_effective",
        "anomaly_suppression_records",
        ["effective_from", "effective_to"],
        unique=False,
    )
    op.create_index(
        "ix_anomaly_suppression_org_definition",
        "anomaly_suppression_records",
        ["organization_id", "definition_version_id"],
        unique=False,
    )
    op.create_table(
        "statistical_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("orchestration_request_id", sa.Uuid(), nullable=True),
        sa.Column("oikb_definition_id", sa.Uuid(), nullable=False),
        sa.Column("oikb_definition_version_id", sa.Uuid(), nullable=False),
        sa.Column("execution_package_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("reproducibility_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("method_code", sa.String(length=100), nullable=False),
        sa.Column("method_version", sa.String(length=30), nullable=False),
        sa.Column("analytical_level", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("blocked_reason", sa.Text(), nullable=True),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("trust_assessment_id", sa.Uuid(), nullable=False),
        sa.Column("readiness_assessment_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_reference", sa.String(length=255), nullable=False),
        sa.Column("dataset_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("source_lineage_reference", sa.String(length=500), nullable=False),
        sa.Column(
            "parameter_snapshot",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("engine_version", sa.String(length=30), nullable=False),
        sa.Column("correlation_id", sa.String(length=100), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column(
            "warnings",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "limitations",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'blocked', "
            "'insufficient_data', 'not_ready', 'unsupported', 'failed', "
            "'cancelled')",
            name="ck_statistical_execution_status",
        ),
        sa.ForeignKeyConstraint(
            ["oikb_definition_id"], ["oikb_definitions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["oikb_definition_version_id"], ["oikb_definition_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["orchestration_request_id"],
            ["intelligence_orchestration_requests.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["readiness_assessment_id"], ["analytical_readiness_decisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["trust_assessment_id"], ["trust_assessments.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "idempotency_key", name="uq_statistical_execution_idempotency"
        ),
    )
    op.create_index(
        "ix_statistical_execution_created", "statistical_executions", ["created_at"], unique=False
    )
    op.create_index(
        "ix_statistical_execution_definition",
        "statistical_executions",
        ["oikb_definition_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_statistical_execution_fingerprint",
        "statistical_executions",
        ["reproducibility_fingerprint"],
        unique=False,
    )
    op.create_index(
        "ix_statistical_execution_org_status",
        "statistical_executions",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_table(
        "statistical_baselines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("statistical_execution_id", sa.Uuid(), nullable=False),
        sa.Column("baseline_type", sa.String(length=40), nullable=False),
        sa.Column(
            "baseline_scope",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "population_definition",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("time_window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("time_window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("entity_count", sa.Integer(), nullable=False),
        sa.Column("mean_value", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("median_value", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("minimum_value", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("maximum_value", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("variance_value", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("standard_deviation_value", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("mad_value", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column(
            "percentile_values",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("baseline_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "limitations",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("record_count >= 0 AND entity_count >= 0", name="ck_baseline_counts"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["statistical_execution_id"], ["statistical_executions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_statistical_baseline_fingerprint",
        "statistical_baselines",
        ["baseline_fingerprint"],
        unique=False,
    )
    op.create_index(
        "ix_statistical_baseline_org_execution",
        "statistical_baselines",
        ["organization_id", "statistical_execution_id"],
        unique=False,
    )
    op.create_table(
        "statistical_execution_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("statistical_execution_id", sa.Uuid(), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("step_code", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "input_summary",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "output_summary",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("warning_code", sa.String(length=100), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sequence_number > 0", name="ck_statistical_step_sequence"),
        sa.ForeignKeyConstraint(
            ["statistical_execution_id"], ["statistical_executions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "statistical_execution_id", "sequence_number", name="uq_statistical_step_sequence"
        ),
    )
    op.create_index(
        "ix_statistical_step_execution",
        "statistical_execution_steps",
        ["statistical_execution_id"],
        unique=False,
    )
    op.create_table(
        "statistical_observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("statistical_execution_id", sa.Uuid(), nullable=False),
        sa.Column("entity_reference", sa.String(length=255), nullable=True),
        sa.Column("period_reference", sa.String(length=100), nullable=True),
        sa.Column("observed_value", sa.Numeric(precision=38, scale=12), nullable=False),
        sa.Column("expected_value", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("absolute_deviation", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("relative_deviation", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("normalized_deviation", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("statistical_score", sa.Numeric(precision=6, scale=5), nullable=False),
        sa.Column("confidence_score", sa.Numeric(precision=6, scale=5), nullable=False),
        sa.Column("materiality_score", sa.Numeric(precision=6, scale=5), nullable=False),
        sa.Column("anomaly_direction", sa.String(length=40), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("is_anomaly", sa.Boolean(), nullable=False),
        sa.Column("persistence_count", sa.Integer(), nullable=False),
        sa.Column("recurrence_count", sa.Integer(), nullable=False),
        sa.Column(
            "method_trace",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "explanation",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "limitations",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "evidence_references",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "anomaly_direction IN ('above_expected', 'below_expected', "
            "'bidirectional', 'level_shift', 'trend_increase', 'trend_decrease', "
            "'volatility_increase', 'volatility_decrease')",
            name="ck_statistical_observation_direction",
        ),
        sa.CheckConstraint(
            "severity IN ('informational', 'low', 'medium', 'high', 'critical')",
            name="ck_statistical_observation_severity",
        ),
        sa.CheckConstraint(
            "statistical_score >= 0 AND statistical_score <= 1 AND "
            "confidence_score >= 0 AND confidence_score <= 1 AND "
            "materiality_score >= 0 AND materiality_score <= 1",
            name="ck_statistical_observation_scores",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["statistical_execution_id"], ["statistical_executions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_statistical_observation_anomaly",
        "statistical_observations",
        ["organization_id", "is_anomaly"],
        unique=False,
    )
    op.create_index(
        "ix_statistical_observation_org_execution",
        "statistical_observations",
        ["organization_id", "statistical_execution_id"],
        unique=False,
    )
    op.create_table(
        "anomaly_review_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("statistical_observation_id", sa.Uuid(), nullable=False),
        sa.Column("review_status", sa.String(length=30), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("classification", sa.String(length=50), nullable=False),
        sa.Column("was_actionable", sa.Boolean(), nullable=False),
        sa.Column("was_false_positive", sa.Boolean(), nullable=False),
        sa.Column("confirmed_cause", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["statistical_observation_id"], ["statistical_observations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "statistical_observation_id",
            "reviewer_id",
            name="uq_anomaly_review_reviewer",
        ),
    )
    op.create_index(
        "ix_anomaly_review_org_observation",
        "anomaly_review_feedback",
        ["organization_id", "statistical_observation_id"],
        unique=False,
    )
    op.create_table(
        "statistical_score_components",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("statistical_observation_id", sa.Uuid(), nullable=False),
        sa.Column("component_code", sa.String(length=100), nullable=False),
        sa.Column("raw_value", sa.Numeric(precision=38, scale=12), nullable=False),
        sa.Column("normalized_value", sa.Numeric(precision=6, scale=5), nullable=False),
        sa.Column("weight", sa.Numeric(precision=6, scale=5), nullable=False),
        sa.Column("contribution", sa.Numeric(precision=6, scale=5), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["statistical_observation_id"], ["statistical_observations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "statistical_observation_id", "component_code", name="uq_statistical_score_component"
        ),
    )
    op.create_index(
        op.f("ix_statistical_score_components_statistical_observation_id"),
        "statistical_score_components",
        ["statistical_observation_id"],
        unique=False,
    )
    _seed_statistical_foundation()
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(
        op.f("ix_statistical_score_components_statistical_observation_id"),
        table_name="statistical_score_components",
    )
    op.drop_table("statistical_score_components")
    op.drop_index("ix_anomaly_review_org_observation", table_name="anomaly_review_feedback")
    op.drop_table("anomaly_review_feedback")
    op.drop_index("ix_statistical_observation_org_execution", table_name="statistical_observations")
    op.drop_index("ix_statistical_observation_anomaly", table_name="statistical_observations")
    op.drop_table("statistical_observations")
    op.drop_index("ix_statistical_step_execution", table_name="statistical_execution_steps")
    op.drop_table("statistical_execution_steps")
    op.drop_index("ix_statistical_baseline_org_execution", table_name="statistical_baselines")
    op.drop_index("ix_statistical_baseline_fingerprint", table_name="statistical_baselines")
    op.drop_table("statistical_baselines")
    op.drop_index("ix_statistical_execution_org_status", table_name="statistical_executions")
    op.drop_index("ix_statistical_execution_fingerprint", table_name="statistical_executions")
    op.drop_index("ix_statistical_execution_definition", table_name="statistical_executions")
    op.drop_index("ix_statistical_execution_created", table_name="statistical_executions")
    op.drop_table("statistical_executions")
    op.drop_index("ix_anomaly_suppression_org_definition", table_name="anomaly_suppression_records")
    op.drop_index("ix_anomaly_suppression_effective", table_name="anomaly_suppression_records")
    op.drop_table("anomaly_suppression_records")
    op.drop_index("ix_statistical_method_supported", table_name="statistical_method_registry")
    op.drop_index("ix_statistical_method_capability", table_name="statistical_method_registry")
    op.drop_table("statistical_method_registry")
    _remove_statistical_seeds()
    # ### end Alembic commands ###
