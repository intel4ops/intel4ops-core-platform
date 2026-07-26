"""forecasting intelligence engine

Revision ID: 20260725_0012
Revises: 20260725_0011
Create Date: 2026-07-25 17:56:15.105133
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

revision: str = "20260725_0012"
down_revision: str | None = "20260725_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

METHODS = (
    ("NAIVE", "Naive", "POINT_FORECAST", 2, True),
    ("SEASONAL_NAIVE", "Seasonal naive", "SEASONAL_FORECAST", 4, True),
    ("DRIFT", "Drift", "TREND_FORECAST", 2, True),
    ("HISTORICAL_MEAN", "Historical mean", "POINT_FORECAST", 2, True),
    ("HISTORICAL_MEDIAN", "Historical median", "POINT_FORECAST", 2, True),
    ("SIMPLE_MOVING_AVERAGE", "Simple moving average", "ROLLING_FORECAST", 3, True),
    ("WEIGHTED_MOVING_AVERAGE", "Weighted moving average", "ROLLING_FORECAST", 3, True),
    ("EXPANDING_MEAN", "Expanding mean", "ROLLING_FORECAST", 2, True),
    ("SIMPLE_EXPONENTIAL_SMOOTHING", "Simple exponential smoothing", "POINT_FORECAST", 3, True),
    ("HOLT_LINEAR_TREND", "Holt linear trend", "TREND_FORECAST", 4, True),
    ("HOLT_DAMPED_TREND", "Holt damped trend", "TREND_FORECAST", 4, True),
    ("HOLT_WINTERS_ADDITIVE", "Holt-Winters additive", "SEASONAL_FORECAST", 8, True),
    ("LINEAR_TIME_TREND", "Linear time trend", "TREND_FORECAST", 3, True),
    ("POLYNOMIAL_TIME_TREND_DEGREE_2", "Polynomial time trend degree 2", "TREND_FORECAST", 5, True),
    ("SEASONAL_DUMMY_REGRESSION", "Seasonal dummy regression", "SEASONAL_FORECAST", 8, True),
    (
        "BOUNDED_MULTIVARIATE_LINEAR_REGRESSION",
        "Bounded multivariate regression",
        "MULTI_HORIZON_FORECAST",
        8,
        False,
    ),
    ("CROSTON", "Croston", "POINT_FORECAST", 5, True),
    ("SBA_CROSTON", "SBA Croston", "POINT_FORECAST", 5, True),
    (
        "WEIGHTED_FORECAST_ENSEMBLE",
        "Weighted forecast ensemble",
        "FORECAST_MODEL_SELECTION",
        3,
        True,
    ),
)

SEEDS = (
    "SHARED.FORECASTING.UNIVARIATE_DEMAND",
    "SHARED.FORECASTING.ROLLING_VOLUME",
    "SHARED.FORECASTING.SEASONAL_VOLUME",
    "SHARED.FORECASTING.TREND_AND_INTERVAL",
    "SHARED.FORECASTING.INTERMITTENT_DEMAND",
    "SHARED.FORECASTING.SCENARIO_ADJUSTMENT",
    "SHARED.FORECASTING.ACCURACY_MONITORING",
    "JOB_TO_CASH.REVENUE.MONTHLY_REVENUE_FORECAST",
    "JOB_TO_CASH.BILLING.INVOICE_VOLUME_FORECAST",
    "JOB_TO_CASH.PAYMENTS.CASH_RECEIPTS_FORECAST",
    "MANUFACTURING.PRODUCTION.OUTPUT_FORECAST",
    "MOBILITY.DEMAND.PASSENGER_VOLUME_FORECAST",
)


def _json(value: object) -> object:
    return json.dumps(value, sort_keys=True) if context.is_offline_mode() else value


def _seed_foundation() -> None:
    now = datetime(2026, 7, 25, tzinfo=UTC)
    json_type = (
        sa.Text()
        if context.is_offline_mode()
        else sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql")
    )
    actor = uuid5(NAMESPACE_URL, "intel4ops:forecasting:system-seed-actor")
    methods = sa.table(
        "forecast_method_registry",
        sa.column("id", sa.Uuid()),
        sa.column("method_code", sa.String()),
        sa.column("method_name", sa.String()),
        sa.column("method_version", sa.String()),
        sa.column("capability_class", sa.String()),
        sa.column("supported", sa.Boolean()),
        sa.column("minimum_history", sa.Integer()),
        sa.column("minimum_seasonal_cycles", sa.Integer()),
        sa.column("supports_trend", sa.Boolean()),
        sa.column("supports_seasonality", sa.Boolean()),
        sa.column("supports_exogenous", sa.Boolean()),
        sa.column("supports_intervals", sa.Boolean()),
        sa.column("supports_negative_values", sa.Boolean()),
        sa.column("supports_zero_values", sa.Boolean()),
        sa.column("supports_intermittent_demand", sa.Boolean()),
        sa.column("parameter_schema", json_type),
        sa.column("output_schema", json_type),
        sa.column("implementation_reference", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        methods,
        [
            {
                "id": uuid5(NAMESPACE_URL, f"intel4ops:forecast-method:{code}:1.0"),
                "method_code": code,
                "method_name": name,
                "method_version": "1.0",
                "capability_class": capability,
                "supported": supported,
                "minimum_history": minimum,
                "minimum_seasonal_cycles": 2 if "SEASONAL" in code else 0,
                "supports_trend": code
                in {
                    "DRIFT",
                    "HOLT_LINEAR_TREND",
                    "HOLT_DAMPED_TREND",
                    "HOLT_WINTERS_ADDITIVE",
                    "LINEAR_TIME_TREND",
                    "POLYNOMIAL_TIME_TREND_DEGREE_2",
                    "SEASONAL_DUMMY_REGRESSION",
                },
                "supports_seasonality": code
                in {"SEASONAL_NAIVE", "HOLT_WINTERS_ADDITIVE", "SEASONAL_DUMMY_REGRESSION"},
                "supports_exogenous": code == "BOUNDED_MULTIVARIATE_LINEAR_REGRESSION",
                "supports_intervals": True,
                "supports_negative_values": True,
                "supports_zero_values": True,
                "supports_intermittent_demand": code in {"CROSTON", "SBA_CROSTON"},
                "parameter_schema": _json({"bounded": True, "arbitrary_code": False}),
                "output_schema": _json({"point": "decimal", "interval": "optional"}),
                "implementation_reference": "app.engines.forecasting_engine",
                "created_at": now,
                "updated_at": now,
            }
            for code, name, capability, minimum, supported in METHODS
        ],
    )
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
    for code in SEEDS:
        definition_id = uuid5(NAMESPACE_URL, f"intel4ops:oikb:definition:{code}")
        version_id = uuid5(NAMESPACE_URL, f"intel4ops:oikb:version:{code}:1.0.0")
        expression = {
            "operation": "forecast",
            "candidate_methods": ["NAIVE", "HOLT_LINEAR_TREND"],
            "naive_benchmark": "NAIVE",
            "backtest_type": "ROLLING_ORIGIN",
            "primary_metric": "WAPE",
            "interval_levels": [0.8, 0.9, 0.95],
            "missing_period_policy": "BLOCK",
            "partial_period_policy": "EXCLUDE",
            "outlier_policy": "KEEP",
            "forecast_horizon": 3,
        }
        fingerprint = hashlib.sha256(
            json.dumps({"code": code, "expression": expression}, sort_keys=True).encode()
        ).hexdigest()
        op.bulk_insert(
            definitions,
            [
                {
                    "id": definition_id,
                    "stable_code": code,
                    "name": code.replace(".", " ").title(),
                    "description": "Governed provisional bounded forecasting definition.",
                    "knowledge_class": "forecasting_method",
                    "analytical_level": "forecasting",
                    "domain": code.split(".")[0].lower(),
                    "subdomain": code.split(".")[1].lower(),
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
                    "expression_schema": _json(expression),
                    "output_type": "forecast_series",
                    "output_unit": "governed_unit",
                    "currency_code": None,
                    "rounding_policy": _json({"mode": "half_even", "decimal_places": 6}),
                    "null_policy": "structured_null",
                    "zero_denominator_policy": "structured_null",
                    "trust_requirement": _json({"minimum_status": "completed"}),
                    "readiness_requirement": _json(
                        {"analytical_level": "forecasting", "minimum_history": 6}
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
            approvals,
            [
                {
                    "id": uuid5(NAMESPACE_URL, f"intel4ops:oikb:approval:{code}"),
                    "definition_version_id": version_id,
                    "approval_role": "forecast_seed_approver",
                    "approver_id": actor,
                    "decision": "approved",
                    "notes": "Provisional WP-2.12 seed.",
                    "decided_at": now,
                }
            ],
        )
        op.bulk_insert(
            cases,
            [
                {
                    "id": uuid5(NAMESPACE_URL, f"intel4ops:oikb:case:{code}:stable"),
                    "definition_version_id": version_id,
                    "case_code": "STABLE_LEVEL_SERIES",
                    "description": "Deterministic stable-series forecast contract.",
                    "input_payload": _json({"values": [10, 10, 10, 10, 10, 10], "method": "NAIVE"}),
                    "expected_output": _json({"status": "succeeded", "point": 10}),
                    "tolerance": "0.000001",
                    "expected_status": "completed",
                    "created_at": now,
                    "updated_at": now,
                }
            ],
        )


def _remove_seeds() -> None:
    definitions = sa.table(
        "oikb_definitions", sa.column("id", sa.Uuid()), sa.column("stable_code", sa.String())
    )
    ids = [uuid5(NAMESPACE_URL, f"intel4ops:oikb:definition:{code}") for code in SEEDS]
    version_ids = [uuid5(NAMESPACE_URL, f"intel4ops:oikb:version:{code}:1.0.0") for code in SEEDS]
    for table_name in ("oikb_approvals", "oikb_validation_cases"):
        table = sa.table(table_name, sa.column("definition_version_id", sa.Uuid()))
        op.get_bind().execute(table.delete().where(table.c.definition_version_id.in_(version_ids)))
    versions = sa.table(
        "oikb_definition_versions",
        sa.column("id", sa.Uuid()),
        sa.column("definition_id", sa.Uuid()),
    )
    op.get_bind().execute(versions.delete().where(versions.c.id.in_(version_ids)))
    op.get_bind().execute(definitions.delete().where(definitions.c.id.in_(ids)))


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("analytical_readiness_decisions") as batch_op:
        batch_op.drop_constraint("ck_readiness_level", type_="check")
        batch_op.create_check_constraint(
            "ck_readiness_level",
            "analytical_level IN ('arithmetic', 'statistical', 'forecasting', "
            "'predictive', 'optimization', 'economic_recovery')",
        )
    op.create_table(
        "forecast_method_registry",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("method_code", sa.String(length=100), nullable=False),
        sa.Column("method_name", sa.String(length=200), nullable=False),
        sa.Column("method_version", sa.String(length=30), nullable=False),
        sa.Column("capability_class", sa.String(length=60), nullable=False),
        sa.Column("supported", sa.Boolean(), nullable=False),
        sa.Column("minimum_history", sa.Integer(), nullable=False),
        sa.Column("minimum_seasonal_cycles", sa.Integer(), nullable=False),
        sa.Column("supports_trend", sa.Boolean(), nullable=False),
        sa.Column("supports_seasonality", sa.Boolean(), nullable=False),
        sa.Column("supports_exogenous", sa.Boolean(), nullable=False),
        sa.Column("supports_intervals", sa.Boolean(), nullable=False),
        sa.Column("supports_negative_values", sa.Boolean(), nullable=False),
        sa.Column("supports_zero_values", sa.Boolean(), nullable=False),
        sa.Column("supports_intermittent_demand", sa.Boolean(), nullable=False),
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
        sa.Column("implementation_reference", sa.String(length=300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("method_code", "method_version", name="uq_forecast_method_version"),
    )
    op.create_index(
        "ix_forecast_method_supported", "forecast_method_registry", ["supported"], unique=False
    )
    op.create_table(
        "forecast_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("orchestration_request_id", sa.Uuid(), nullable=True),
        sa.Column("oikb_definition_id", sa.Uuid(), nullable=False),
        sa.Column("oikb_definition_version_id", sa.Uuid(), nullable=False),
        sa.Column("trust_assessment_id", sa.Uuid(), nullable=False),
        sa.Column("readiness_assessment_id", sa.Uuid(), nullable=False),
        sa.Column("execution_package_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("reproducibility_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("target_code", sa.String(length=150), nullable=False),
        sa.Column("target_unit", sa.String(length=50), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=True),
        sa.Column("source_time_grain", sa.String(length=40), nullable=False),
        sa.Column("forecast_time_grain", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dataset_reference", sa.String(length=255), nullable=False),
        sa.Column("dataset_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("prepared_series_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("source_lineage_reference", sa.String(length=500), nullable=False),
        sa.Column("training_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("training_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("forecast_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("forecast_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("forecast_horizon", sa.Integer(), nullable=False),
        sa.Column("selected_method_code", sa.String(length=100), nullable=True),
        sa.Column("selected_method_version", sa.String(length=30), nullable=True),
        sa.Column("engine_version", sa.String(length=30), nullable=False),
        sa.Column("correlation_id", sa.String(length=100), nullable=False),
        sa.Column(
            "readiness_snapshot",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "explanation",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
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
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'blocked', 'not_ready', "
            "'insufficient_history', 'insufficient_seasonal_cycles', "
            "'invalid_time_series', 'unsupported', 'backtest_failed', "
            "'model_selection_failed', 'failed', 'cancelled')",
            name="ck_forecast_execution_status",
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
            "organization_id", "reproducibility_fingerprint", name="uq_forecast_reproducibility"
        ),
    )
    op.create_index(
        "ix_forecast_execution_dataset",
        "forecast_executions",
        ["organization_id", "dataset_reference"],
        unique=False,
    )
    op.create_index(
        "ix_forecast_execution_definition",
        "forecast_executions",
        ["oikb_definition_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_forecast_execution_org_status",
        "forecast_executions",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_table(
        "forecast_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("forecast_execution_id", sa.Uuid(), nullable=False),
        sa.Column("method_code", sa.String(length=100), nullable=False),
        sa.Column("method_version", sa.String(length=30), nullable=False),
        sa.Column(
            "parameter_snapshot",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("eligible", sa.Boolean(), nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("primary_metric_code", sa.String(length=40), nullable=False),
        sa.Column("primary_metric_value", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column(
            "secondary_metrics",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("bias_value", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("interval_coverage", sa.Numeric(precision=8, scale=5), nullable=True),
        sa.Column("complexity_rank", sa.Integer(), nullable=False),
        sa.Column("selected", sa.Boolean(), nullable=False),
        sa.Column("selection_rank", sa.Integer(), nullable=True),
        sa.Column("selection_rationale", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["forecast_execution_id"], ["forecast_executions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "forecast_execution_id", "method_code", "method_version", name="uq_forecast_candidate"
        ),
    )
    op.create_index(
        "ix_forecast_candidate_execution",
        "forecast_candidates",
        ["forecast_execution_id"],
        unique=False,
    )
    op.create_table(
        "forecast_execution_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("forecast_execution_id", sa.Uuid(), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("step_code", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["forecast_execution_id"], ["forecast_executions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "forecast_execution_id", "sequence_number", name="uq_forecast_step_sequence"
        ),
    )
    op.create_table(
        "forecast_points",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("forecast_execution_id", sa.Uuid(), nullable=False),
        sa.Column("entity_reference", sa.String(length=255), nullable=True),
        sa.Column("scenario_code", sa.String(length=50), nullable=False),
        sa.Column("forecast_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("forecast_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon_step", sa.Integer(), nullable=False),
        sa.Column("point_forecast", sa.Numeric(precision=38, scale=12), nullable=False),
        sa.Column("lower_bound", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("upper_bound", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("interval_level", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("output_unit", sa.String(length=50), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=True),
        sa.Column("is_partial_period", sa.Boolean(), nullable=False),
        sa.Column(
            "assumptions",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["forecast_execution_id"], ["forecast_executions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "forecast_execution_id",
            "scenario_code",
            "horizon_step",
            "entity_reference",
            name="uq_forecast_point",
        ),
    )
    op.create_index(
        "ix_forecast_point_org_period",
        "forecast_points",
        ["organization_id", "forecast_period_start"],
        unique=False,
    )
    op.create_table(
        "forecast_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("prior_forecast_execution_id", sa.Uuid(), nullable=False),
        sa.Column("revised_forecast_execution_id", sa.Uuid(), nullable=False),
        sa.Column("revision_reason", sa.Text(), nullable=False),
        sa.Column("revision_type", sa.String(length=50), nullable=False),
        sa.Column("absolute_revision", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("percentage_revision", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("method_changed", sa.Boolean(), nullable=False),
        sa.Column("parameters_changed", sa.Boolean(), nullable=False),
        sa.Column("data_changed", sa.Boolean(), nullable=False),
        sa.Column("readiness_changed", sa.Boolean(), nullable=False),
        sa.Column("scenario_changed", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["prior_forecast_execution_id"], ["forecast_executions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["revised_forecast_execution_id"], ["forecast_executions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_forecast_revision_org_prior",
        "forecast_revisions",
        ["organization_id", "prior_forecast_execution_id"],
        unique=False,
    )
    op.create_table(
        "forecast_scenarios",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("forecast_execution_id", sa.Uuid(), nullable=False),
        sa.Column("scenario_code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("adjustment_type", sa.String(length=40), nullable=False),
        sa.Column(
            "adjustment_parameters",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["forecast_execution_id"], ["forecast_executions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("forecast_execution_id", "scenario_code", name="uq_forecast_scenario"),
    )
    op.create_table(
        "forecast_accuracy_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("forecast_execution_id", sa.Uuid(), nullable=False),
        sa.Column("forecast_point_id", sa.Uuid(), nullable=True),
        sa.Column("metric_code", sa.String(length=40), nullable=False),
        sa.Column("metric_value", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("horizon_step", sa.Integer(), nullable=True),
        sa.Column("entity_reference", sa.String(length=255), nullable=True),
        sa.Column("evaluation_status", sa.String(length=30), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["forecast_execution_id"], ["forecast_executions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["forecast_point_id"], ["forecast_points.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_forecast_accuracy_org_execution",
        "forecast_accuracy_results",
        ["organization_id", "forecast_execution_id"],
        unique=False,
    )
    op.create_table(
        "forecast_actuals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("forecast_point_id", sa.Uuid(), nullable=False),
        sa.Column("actual_reference", sa.String(length=500), nullable=False),
        sa.Column("actual_value", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("actual_status", sa.String(length=30), nullable=False),
        sa.Column("actual_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actual_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actual_dataset_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["forecast_point_id"], ["forecast_points.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "forecast_point_id", name="uq_forecast_actual_point"
        ),
    )
    op.create_table(
        "forecast_backtests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("forecast_execution_id", sa.Uuid(), nullable=False),
        sa.Column("forecast_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("backtest_type", sa.String(length=30), nullable=False),
        sa.Column("fold_number", sa.Integer(), nullable=False),
        sa.Column("train_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("train_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("forecast_origin", sa.DateTime(timezone=True), nullable=False),
        sa.Column("forecast_period", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon_step", sa.Integer(), nullable=False),
        sa.Column("actual_value", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("forecast_value", sa.Numeric(precision=38, scale=12), nullable=False),
        sa.Column("lower_bound", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("upper_bound", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("error_value", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("absolute_error", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("percentage_error", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("interval_contains_actual", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["forecast_candidate_id"], ["forecast_candidates.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["forecast_execution_id"], ["forecast_executions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_forecast_backtest_execution_fold",
        "forecast_backtests",
        ["forecast_execution_id", "fold_number"],
        unique=False,
    )
    op.create_table(
        "forecast_metrics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("forecast_execution_id", sa.Uuid(), nullable=False),
        sa.Column("forecast_candidate_id", sa.Uuid(), nullable=True),
        sa.Column("metric_code", sa.String(length=40), nullable=False),
        sa.Column("metric_value", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("horizon_step", sa.Integer(), nullable=True),
        sa.Column("segment_reference", sa.String(length=255), nullable=True),
        sa.Column("valid", sa.Boolean(), nullable=False),
        sa.Column("invalid_reason", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["forecast_candidate_id"], ["forecast_candidates.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["forecast_execution_id"], ["forecast_executions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_forecast_metric_execution", "forecast_metrics", ["forecast_execution_id"], unique=False
    )
    _seed_foundation()
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    _remove_seeds()
    op.drop_index("ix_forecast_metric_execution", table_name="forecast_metrics")
    op.drop_table("forecast_metrics")
    op.drop_index("ix_forecast_backtest_execution_fold", table_name="forecast_backtests")
    op.drop_table("forecast_backtests")
    op.drop_table("forecast_actuals")
    op.drop_index("ix_forecast_accuracy_org_execution", table_name="forecast_accuracy_results")
    op.drop_table("forecast_accuracy_results")
    op.drop_table("forecast_scenarios")
    op.drop_index("ix_forecast_revision_org_prior", table_name="forecast_revisions")
    op.drop_table("forecast_revisions")
    op.drop_index("ix_forecast_point_org_period", table_name="forecast_points")
    op.drop_table("forecast_points")
    op.drop_table("forecast_execution_steps")
    op.drop_index("ix_forecast_candidate_execution", table_name="forecast_candidates")
    op.drop_table("forecast_candidates")
    op.drop_index("ix_forecast_execution_org_status", table_name="forecast_executions")
    op.drop_index("ix_forecast_execution_definition", table_name="forecast_executions")
    op.drop_index("ix_forecast_execution_dataset", table_name="forecast_executions")
    op.drop_table("forecast_executions")
    op.drop_index("ix_forecast_method_supported", table_name="forecast_method_registry")
    op.drop_table("forecast_method_registry")
    op.execute(
        sa.text(
            "UPDATE analytical_readiness_decisions "
            "SET analytical_level = 'statistical' "
            "WHERE analytical_level = 'forecasting'"
        )
    )
    with op.batch_alter_table("analytical_readiness_decisions") as batch_op:
        batch_op.drop_constraint("ck_readiness_level", type_="check")
        batch_op.create_check_constraint(
            "ck_readiness_level",
            "analytical_level IN ('arithmetic', 'statistical', 'predictive', "
            "'optimization', 'economic_recovery')",
        )
    # ### end Alembic commands ###
