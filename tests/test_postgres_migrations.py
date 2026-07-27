import os
from collections.abc import Iterator
from datetime import UTC, datetime
from urllib.parse import urlparse
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_statistical_service import execution_payload, statistical_foundation

from app.models.entities import (
    Finding,
    MembershipRole,
    MembershipStatus,
    OrganizationMembership,
)
from app.models.orchestration import IntelligenceOrchestrationRequest
from app.models.trust import AnalyticalReadinessDecision
from app.schemas.contracts import FindingCreate, OrganizationCreate
from app.schemas.findings import CandidateFindingCreate
from app.schemas.ingestion import (
    DatasetCreate,
    DatasetVersionCountsUpdate,
    DatasetVersionCreate,
    IngestionBatchCreate,
)
from app.schemas.intelligence import IntelligenceExecutionCreate
from app.schemas.memberships import MembershipCreate
from app.schemas.orchestration import OrchestrationCreate
from app.schemas.raw_lineage import RawStorageObjectCreate
from app.schemas.source_systems import SourceSystemCreate
from app.schemas.trust import TrustAssessmentCreate
from app.services.finding_platform_service import (
    FindingPublicationService,
    FindingQueryService,
)
from app.services.finding_service import FindingService
from app.services.ingestion_service import (
    DatasetService,
    DatasetVersionService,
    IngestionBatchService,
)
from app.services.intelligence_service import IntelligenceExecutionService
from app.services.membership_service import (
    DuplicateMembershipError,
    OrganizationMembershipService,
)
from app.services.orchestration_service import OrchestrationService
from app.services.organization_service import OrganizationService
from app.services.raw_lineage_service import RawStorageObjectService
from app.services.source_system_service import (
    DuplicateSourceSystemCodeError,
    SourceSystemService,
)
from app.services.statistical_service import statistical_execution_service
from app.services.trust_service import TrustAssessmentService

MANAGED_TABLES = {
    "organizations",
    "findings",
    "finding_evidence",
    "recovery_actions",
    "organization_members",
    "source_systems",
    "ingestion_batches",
    "datasets",
    "dataset_versions",
    "raw_storage_objects",
    "raw_record_references",
    "processing_runs",
    "lineage_nodes",
    "lineage_edges",
    "lineage_events",
    "trust_assessments",
    "trust_rule_results",
    "trust_evidence",
    "analytical_readiness_decisions",
    "intelligence_executions",
    "intelligence_execution_evidence",
    "finding_evidence_bundles",
    "finding_evidence_items",
    "finding_calculation_traces",
    "finding_rule_traces",
    "finding_reviews",
    "finding_status_history",
    "intelligence_orchestration_requests",
    "intelligence_orchestration_decisions",
    "intelligence_orchestration_steps",
    "intelligence_engine_registrations",
    "intelligence_orchestration_status_history",
    "oikb_definitions",
    "oikb_definition_versions",
    "oikb_parameters",
    "oikb_input_requirements",
    "oikb_evidence_requirements",
    "oikb_sources",
    "oikb_definition_sources",
    "oikb_validation_cases",
    "oikb_validation_results",
    "oikb_approvals",
    "oikb_change_log",
    "oikb_relationships",
    "statistical_executions",
    "statistical_baselines",
    "statistical_observations",
    "statistical_score_components",
    "statistical_execution_steps",
    "statistical_method_registry",
    "anomaly_suppression_records",
    "anomaly_review_feedback",
    "forecast_executions",
    "forecast_candidates",
    "forecast_backtests",
    "forecast_metrics",
    "forecast_points",
    "forecast_scenarios",
    "forecast_revisions",
    "forecast_actuals",
    "forecast_accuracy_results",
    "forecast_method_registry",
    "forecast_execution_steps",
    "reliability_executions",
    "reliability_metrics",
    "reliability_model_results",
    "reliability_execution_steps",
    "reliability_method_registry",
    "reliability_review_feedback",
    "operational_actions",
    "action_plan_steps",
    "action_dependencies",
    "action_resource_requirements",
    "action_events",
    "action_evidence",
    "action_outcomes",
    "action_model_feedback",
    "recovery_opportunities",
    "opportunity_findings",
    "opportunity_actions",
    "economic_scenarios",
    "economic_assumptions",
    "economic_calculations",
    "prioritization_assessments",
    "opportunity_overlap_groups",
    "opportunity_overlap_members",
    "opportunity_decisions",
    "economic_audit_events",
    "economic_baseline_versions",
    "recovery_cases",
    "recovery_executions",
    "recovery_value_measurements",
    "recovery_evidence_links",
    "recovery_finance_verifications",
    "verified_value_ledger_entries",
    "recovery_audit_events",
    "products",
    "product_versions",
    "features",
    "plans",
    "plan_versions",
    "plan_version_entitlements",
    "subscriptions",
    "contracts",
    "contract_overrides",
    "entitlements",
    "usage_meter_definitions",
    "usage_events",
    "usage_periods",
    "industry_pack_definitions",
    "industry_pack_assignments",
    "feature_flags",
    "limit_definitions",
    "limit_evaluations",
    "commercial_audit_events",
    "application_clients",
    "api_request_audit_events",
    "job_to_cash_runs",
    "job_to_cash_records",
}
DISPOSABLE_NAME_MARKERS = ("test", "testing", "disposable", "validation")


def require_disposable_postgres_url() -> str:
    database_url = os.getenv("TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("Set TEST_POSTGRES_URL to a disposable PostgreSQL database")
    if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        pytest.fail("TEST_POSTGRES_URL must be a PostgreSQL URL")
    if database_url == os.getenv("DATABASE_URL"):
        pytest.fail("TEST_POSTGRES_URL must not match the runtime DATABASE_URL")
    database_name = urlparse(database_url.replace("postgresql+psycopg://", "postgresql://")).path
    if not any(marker in database_name.lower() for marker in DISPOSABLE_NAME_MARKERS):
        pytest.fail("Disposable PostgreSQL database name must contain a safety marker")
    if os.getenv("CONFIRM_DISPOSABLE_POSTGRES") != "1":
        pytest.fail("Set CONFIRM_DISPOSABLE_POSTGRES=1 to permit destructive migration tests")
    return database_url


@pytest.fixture
def postgres_engine() -> Iterator[Engine]:
    engine = create_engine(require_disposable_postgres_url())
    try:
        yield engine
    finally:
        engine.dispose()


def alembic_config(database_url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def assert_schema_at_head(engine: Engine) -> None:
    inspector = inspect(engine)
    assert MANAGED_TABLES <= set(inspector.get_table_names())

    organization_columns = {
        column["name"]: column for column in inspector.get_columns("organizations")
    }
    assert set(organization_columns) == {
        "id",
        "name",
        "slug",
        "legal_name",
        "industry",
        "country_code",
        "default_currency",
        "timezone",
        "status",
        "description",
        "is_demo",
        "created_at",
        "updated_at",
    }
    assert str(organization_columns["id"]["type"]) == "UUID"
    assert organization_columns["id"]["nullable"] is False

    organization_indexes = {
        index["name"]: index for index in inspector.get_indexes("organizations")
    }
    assert organization_indexes["ix_organizations_slug"]["unique"] is True
    assert organization_indexes["ix_organizations_slug"]["column_names"] == ["slug"]

    membership_columns = {
        column["name"]: column for column in inspector.get_columns("organization_members")
    }
    assert set(membership_columns) == {
        "id",
        "organization_id",
        "user_id",
        "role",
        "status",
        "invited_by_user_id",
        "joined_at",
        "created_at",
        "updated_at",
    }
    assert str(membership_columns["id"]["type"]) == "UUID"
    assert str(membership_columns["organization_id"]["type"]) == "UUID"
    assert str(membership_columns["user_id"]["type"]) == "UUID"

    membership_indexes = {
        index["name"]: index for index in inspector.get_indexes("organization_members")
    }
    assert {
        "ix_organization_members_organization_id",
        "ix_organization_members_user_id",
        "ix_organization_members_role",
        "ix_organization_members_status",
    } <= set(membership_indexes)
    membership_unique_constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("organization_members")
    }
    assert "uq_organization_members_organization_user" in membership_unique_constraints
    membership_checks = {
        constraint["name"] for constraint in inspector.get_check_constraints("organization_members")
    }
    assert {
        "ck_organization_members_role",
        "ck_organization_members_status",
    } <= membership_checks
    membership_foreign_keys = inspector.get_foreign_keys("organization_members")
    assert len(membership_foreign_keys) == 1
    assert membership_foreign_keys[0]["constrained_columns"] == ["organization_id"]
    assert membership_foreign_keys[0]["referred_table"] == "organizations"
    assert membership_foreign_keys[0]["options"]["ondelete"] == "CASCADE"

    source_columns = {column["name"]: column for column in inspector.get_columns("source_systems")}
    assert {
        "id",
        "organization_id",
        "code",
        "credential_reference",
        "configuration_metadata",
        "capabilities",
        "failure_count",
        "created_by_user_id",
        "updated_by_user_id",
        "deactivated_at",
    } <= set(source_columns)
    assert str(source_columns["id"]["type"]) == "UUID"
    assert str(source_columns["organization_id"]["type"]) == "UUID"
    assert str(source_columns["configuration_metadata"]["type"]) == "JSONB"
    assert {
        "ix_source_systems_organization_id",
        "ix_source_systems_system_type",
        "ix_source_systems_status",
        "ix_source_systems_health_status",
        "ix_source_systems_provider",
        "ix_source_systems_is_active",
    } <= {index["name"] for index in inspector.get_indexes("source_systems")}
    assert "uq_source_systems_organization_code" in {
        constraint["name"] for constraint in inspector.get_unique_constraints("source_systems")
    }
    assert {
        "ck_source_systems_failure_count",
        "ck_source_systems_system_type",
        "ck_source_systems_integration_method",
        "ck_source_systems_environment",
        "ck_source_systems_status",
        "ck_source_systems_health_status",
        "ck_source_systems_data_classification",
    } <= {constraint["name"] for constraint in inspector.get_check_constraints("source_systems")}
    source_foreign_keys = inspector.get_foreign_keys("source_systems")
    assert len(source_foreign_keys) == 1
    assert source_foreign_keys[0]["referred_table"] == "organizations"
    assert source_foreign_keys[0]["options"]["ondelete"] == "RESTRICT"

    for table, json_column in (
        ("ingestion_batches", "manifest_metadata"),
        ("datasets", "metadata_json"),
        ("dataset_versions", "metadata_json"),
    ):
        columns = {column["name"]: column for column in inspector.get_columns(table)}
        assert str(columns["id"]["type"]) == "UUID"
        assert str(columns["organization_id"]["type"]) == "UUID"
        assert str(columns[json_column]["type"]) == "JSONB"
    assert "uq_ingestion_batches_organization_batch" in {
        constraint["name"] for constraint in inspector.get_unique_constraints("ingestion_batches")
    }
    assert "uq_ingestion_batches_organization_idempotency" in {
        constraint["name"] for constraint in inspector.get_unique_constraints("ingestion_batches")
    }
    assert "uq_datasets_organization_code" in {
        constraint["name"] for constraint in inspector.get_unique_constraints("datasets")
    }
    assert {
        "uq_dataset_versions_dataset_version",
        "uq_dataset_versions_batch_dataset",
    } <= {constraint["name"] for constraint in inspector.get_unique_constraints("dataset_versions")}
    assert {
        "ix_ingestion_batches_organization_id",
        "ix_ingestion_batches_source_system_id",
        "ix_ingestion_batches_status",
    } <= {index["name"] for index in inspector.get_indexes("ingestion_batches")}
    assert {
        "ix_datasets_organization_id",
        "ix_datasets_source_system_id",
        "ix_datasets_status",
    } <= {index["name"] for index in inspector.get_indexes("datasets")}
    assert {
        "ix_dataset_versions_organization_id",
        "ix_dataset_versions_dataset_id",
        "ix_dataset_versions_ingestion_batch_id",
    } <= {index["name"] for index in inspector.get_indexes("dataset_versions")}
    assert {
        foreign_key["referred_table"]
        for foreign_key in inspector.get_foreign_keys("dataset_versions")
    } == {"organizations", "datasets", "ingestion_batches"}

    wp_205_json_columns = {
        "raw_storage_objects": "metadata_json",
        "raw_record_references": "metadata_json",
        "processing_runs": "parameters_json",
        "lineage_nodes": "metadata_json",
        "lineage_edges": "metadata_json",
        "lineage_events": "metadata_json",
    }
    for table, json_column in wp_205_json_columns.items():
        columns = {column["name"]: column for column in inspector.get_columns(table)}
        assert str(columns["id"]["type"]) == "UUID"
        assert str(columns["organization_id"]["type"]) == "UUID"
        assert str(columns[json_column]["type"]) == "JSONB"
    assert "uq_raw_objects_organization_number" in {
        constraint["name"] for constraint in inspector.get_unique_constraints("raw_storage_objects")
    }
    assert "uq_raw_records_object_sequence" in {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("raw_record_references")
    }
    assert "uq_lineage_node_entity" in {
        constraint["name"] for constraint in inspector.get_unique_constraints("lineage_nodes")
    }
    assert {
        "organizations",
        "source_systems",
        "ingestion_batches",
        "dataset_versions",
        "raw_storage_objects",
    } == {
        foreign_key["referred_table"]
        for foreign_key in inspector.get_foreign_keys("raw_storage_objects")
    }

    execution_columns = {
        column["name"]: column for column in inspector.get_columns("intelligence_executions")
    }
    assert str(execution_columns["id"]["type"]) == "UUID"
    assert str(execution_columns["organization_id"]["type"]) == "UUID"
    assert str(execution_columns["parameters_json"]["type"]) == "JSONB"
    assert str(execution_columns["result_value"]["type"]) == "NUMERIC(38, 12)"
    assert {
        "ix_intelligence_executions_organization_id",
        "ix_intelligence_executions_dataset_id",
        "ix_intelligence_executions_trust_assessment_id",
        "ix_intelligence_executions_definition",
        "ix_intelligence_executions_status",
        "ix_intelligence_executions_created_at",
    } <= {index["name"] for index in inspector.get_indexes("intelligence_executions")}
    evidence_columns = {
        column["name"]: column
        for column in inspector.get_columns("intelligence_execution_evidence")
    }
    assert str(evidence_columns["aggregate_reference"]["type"]) == "JSONB"

    for table, json_columns in {
        "trust_rule_results": {"threshold_definition", "observed_value"},
        "trust_evidence": {"observed_value"},
        "analytical_readiness_decisions": {
            "blocking_rule_codes",
            "warning_rule_codes",
        },
    }.items():
        columns = {column["name"]: column for column in inspector.get_columns(table)}
        assert str(columns["id"]["type"]) == "UUID"
        assert str(columns["organization_id"]["type"]) == "UUID"
        assert all(str(columns[column]["type"]) == "JSONB" for column in json_columns)
    assert {
        "ix_trust_assessments_organization_id",
        "ix_trust_assessments_dataset_id",
        "ix_trust_assessments_status",
        "ix_trust_assessments_created_at",
    } <= {index["name"] for index in inspector.get_indexes("trust_assessments")}
    assert {
        foreign_key["referred_table"]
        for foreign_key in inspector.get_foreign_keys("trust_assessments")
    } == {"organizations", "datasets", "ingestion_batches"}

    expected_indexes = {
        "findings": {
            "ix_findings_domain",
            "ix_findings_organization_id",
            "ix_findings_rule_id",
            "ix_findings_organization_status",
            "ix_findings_organization_type",
            "ix_findings_organization_severity",
            "ix_findings_organization_detected",
            "ix_findings_organization_occurrence",
            "ix_findings_source_execution",
            "ix_findings_definition",
            "uq_findings_organization_deduplication",
        },
        "finding_evidence": {
            "ix_finding_evidence_finding_id",
            "ix_finding_evidence_organization_id",
        },
        "recovery_actions": {
            "ix_recovery_actions_finding_id",
            "ix_recovery_actions_organization_id",
        },
    }
    for table, names in expected_indexes.items():
        assert names <= {index["name"] for index in inspector.get_indexes(table)}

    expected_foreign_keys = {
        "findings": {
            ("organization_id", "organizations", "id"),
            ("superseded_by_finding_id", "findings", "id"),
            ("source_execution_id", "intelligence_executions", "id"),
            ("source_result_id", "intelligence_executions", "id"),
            ("trust_assessment_id", "trust_assessments", "id"),
            (
                "analytical_readiness_id",
                "analytical_readiness_decisions",
                "id",
            ),
            ("dataset_id", "datasets", "id"),
            ("oikb_definition_id", "oikb_definitions", "id"),
            (
                "oikb_definition_version_id",
                "oikb_definition_versions",
                "id",
            ),
        },
        "finding_evidence": {
            ("finding_id", "findings", "id"),
            ("organization_id", "organizations", "id"),
        },
        "recovery_actions": {
            ("finding_id", "findings", "id"),
            ("organization_id", "organizations", "id"),
        },
    }
    for table, expected in expected_foreign_keys.items():
        actual = {
            (
                foreign_key["constrained_columns"][0],
                foreign_key["referred_table"],
                foreign_key["referred_columns"][0],
            )
            for foreign_key in inspector.get_foreign_keys(table)
        }
        assert actual == expected

    finding_columns = {column["name"]: column for column in inspector.get_columns("findings")}
    assert str(finding_columns["measured_value"]["type"]) == "NUMERIC(38, 12)"
    assert str(finding_columns["exposure_value"]["type"]) == "NUMERIC(38, 12)"
    assert str(finding_columns["confidence_score"]["type"]) == "NUMERIC(6, 4)"
    assert str(finding_columns["severity_reason"]["type"]) == "JSONB"
    assert str(finding_columns["warnings"]["type"]) == "JSONB"
    assert str(finding_columns["limitations"]["type"]) == "JSONB"
    evidence_item_columns = {
        column["name"]: column for column in inspector.get_columns("finding_evidence_items")
    }
    assert str(evidence_item_columns["metadata_json"]["type"]) == "JSONB"
    assert str(evidence_item_columns["comparison_value"]["type"]) == "NUMERIC(38, 12)"

    orchestration_columns = {
        column["name"]: column
        for column in inspector.get_columns("intelligence_orchestration_requests")
    }
    assert str(orchestration_columns["id"]["type"]) == "UUID"
    assert str(orchestration_columns["organization_id"]["type"]) == "UUID"
    assert str(orchestration_columns["parameters_summary"]["type"]) == "JSONB"
    assert str(orchestration_columns["request_context"]["type"]) == "JSONB"
    assert {
        "ix_orchestration_requests_organization_status",
        "ix_orchestration_requests_organization_definition",
        "ix_orchestration_requests_organization_requested",
        "ix_orchestration_requests_dataset_id",
        "ix_orchestration_requests_trust_assessment_id",
        "ix_orchestration_requests_readiness_id",
    } <= {index["name"] for index in inspector.get_indexes("intelligence_orchestration_requests")}
    orchestration_uniques = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("intelligence_orchestration_requests")
    }
    assert {
        "uq_orchestration_requests_organization_idempotency",
        "uq_orchestration_requests_organization_correlation",
    } <= orchestration_uniques
    assert {
        foreign_key["referred_table"]
        for foreign_key in inspector.get_foreign_keys("intelligence_orchestration_requests")
    } == {
        "organizations",
        "datasets",
        "dataset_versions",
        "trust_assessments",
        "analytical_readiness_decisions",
    }
    step_columns = {
        column["name"]: column
        for column in inspector.get_columns("intelligence_orchestration_steps")
    }
    assert str(step_columns["input_reference_summary"]["type"]) == "JSONB"
    assert str(step_columns["source_execution_id"]["type"]) == "UUID"
    assert str(step_columns["source_result_id"]["type"]) == "UUID"
    assert str(step_columns["result_locator"]["type"]) == "VARCHAR(100)"
    assert str(step_columns["output_index"]["type"]) == "INTEGER"
    decision_columns = {
        column["name"]: column
        for column in inspector.get_columns("intelligence_orchestration_decisions")
    }
    assert str(decision_columns["warnings"]["type"]) == "JSONB"
    assert str(decision_columns["readiness_mapping_policy_code"]["type"]) == "VARCHAR(100)"
    assert {
        foreign_key["referred_table"]
        for foreign_key in inspector.get_foreign_keys("intelligence_orchestration_steps")
    } == {
        "organizations",
        "intelligence_orchestration_requests",
        "intelligence_executions",
        "findings",
    }
    definition_columns = {
        column["name"]: column for column in inspector.get_columns("oikb_definitions")
    }
    assert str(definition_columns["id"]["type"]) == "UUID"
    assert definition_columns["scope_key"]["nullable"] is False
    assert "uq_oikb_definition_scope" in {
        constraint["name"] for constraint in inspector.get_unique_constraints("oikb_definitions")
    }
    version_columns = {
        column["name"]: column for column in inspector.get_columns("oikb_definition_versions")
    }
    assert str(version_columns["expression_schema"]["type"]) == "JSONB"
    assert str(version_columns["fingerprint"]["type"]) == "VARCHAR(64)"
    assert {
        "uq_oikb_definition_semantic_version",
        "uq_oikb_definition_fingerprint",
    } <= {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("oikb_definition_versions")
    }
    finding_foreign_tables = {
        foreign_key["referred_table"] for foreign_key in inspector.get_foreign_keys("findings")
    }
    assert {"oikb_definitions", "oikb_definition_versions"} <= finding_foreign_tables
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT count(*) FROM oikb_definitions WHERE scope_key = 'shared_core'")
            )
            == 34
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM ("
                    "SELECT stable_code, count(*) "
                    "FROM oikb_definitions "
                    "WHERE scope_key = 'shared_core' "
                    "GROUP BY stable_code HAVING count(*) > 1"
                    ") duplicate_shared_core_codes"
                )
            )
            == 0
        )
        assert connection.scalar(text("SELECT count(*) FROM oikb_validation_cases")) == 320
        assert connection.scalar(text("SELECT count(*) FROM statistical_method_registry")) == 40
        assert connection.scalar(text("SELECT count(*) FROM forecast_method_registry")) == 19
    forecast_columns = {
        column["name"]: column for column in inspector.get_columns("forecast_executions")
    }
    assert str(forecast_columns["id"]["type"]) == "UUID"
    assert str(forecast_columns["readiness_snapshot"]["type"]) == "JSONB"
    assert {
        foreign_key["referred_table"]
        for foreign_key in inspector.get_foreign_keys("forecast_executions")
    } >= {
        "organizations",
        "oikb_definitions",
        "oikb_definition_versions",
        "trust_assessments",
        "analytical_readiness_decisions",
    }


@pytest.mark.postgres
def test_migrations_on_disposable_postgres(postgres_engine: Engine) -> None:
    config = alembic_config(require_disposable_postgres_url())

    command.upgrade(config, "head")
    assert_schema_at_head(postgres_engine)

    wp_217_tables = {
        "products",
        "product_versions",
        "features",
        "plans",
        "plan_versions",
        "plan_version_entitlements",
        "subscriptions",
        "contracts",
        "contract_overrides",
        "entitlements",
        "usage_meter_definitions",
        "usage_events",
        "usage_periods",
        "industry_pack_definitions",
        "industry_pack_assignments",
        "feature_flags",
        "limit_definitions",
        "limit_evaluations",
        "commercial_audit_events",
    }
    wp_218_tables = {
        "application_clients",
        "api_request_audit_events",
        "job_to_cash_runs",
        "job_to_cash_records",
    }
    commercial_inspector = inspect(postgres_engine)
    usage_columns = {
        column["name"]: column for column in commercial_inspector.get_columns("usage_events")
    }
    assert str(usage_columns["id"]["type"]) == "UUID"
    assert str(usage_columns["quantity"]["type"]) == "NUMERIC(38, 12)"
    assert str(usage_columns["metadata_json"]["type"]) == "JSONB"
    assert {
        "organizations",
        "usage_meter_definitions",
    } <= {
        foreign_key["referred_table"]
        for foreign_key in commercial_inspector.get_foreign_keys("usage_events")
    }
    assert "uq_usage_event_key" in {
        item["name"] for item in commercial_inspector.get_unique_constraints("usage_events")
    }
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM products")) == 6
        assert connection.scalar(text("SELECT count(*) FROM plans")) == 5
        assert connection.scalar(text("SELECT count(*) FROM usage_meter_definitions")) == 18
        assert connection.scalar(text("SELECT count(*) FROM industry_pack_definitions")) == 7
        assert connection.scalar(text("SELECT count(*) FROM application_clients")) == 4
    command.downgrade(config, "20260726_0017")
    assert not (wp_218_tables & set(inspect(postgres_engine).get_table_names()))
    assert wp_217_tables <= set(inspect(postgres_engine).get_table_names())
    command.upgrade(config, "head")
    assert wp_218_tables <= set(inspect(postgres_engine).get_table_names())
    command.downgrade(config, "20260726_0016")
    assert not (wp_217_tables & set(inspect(postgres_engine).get_table_names()))
    assert "verified_value_ledger_entries" in inspect(postgres_engine).get_table_names()
    command.upgrade(config, "head")
    assert wp_217_tables <= set(inspect(postgres_engine).get_table_names())

    wp_216_tables = {
        "recovery_cases",
        "recovery_executions",
        "recovery_value_measurements",
        "recovery_evidence_links",
        "recovery_finance_verifications",
        "verified_value_ledger_entries",
        "recovery_audit_events",
    }
    ledger_inspector = inspect(postgres_engine)
    ledger_columns = {
        column["name"]: column
        for column in ledger_inspector.get_columns("verified_value_ledger_entries")
    }
    measurement_columns = {
        column["name"]: column
        for column in ledger_inspector.get_columns("recovery_value_measurements")
    }
    assert str(ledger_columns["id"]["type"]) == "UUID"
    assert str(ledger_columns["amount"]["type"]) == "NUMERIC(38, 12)"
    assert str(measurement_columns["calculation_inputs"]["type"]) == "JSONB"
    assert {
        "recovery_cases",
        "recovery_value_measurements",
        "recovery_finance_verifications",
        "verified_value_ledger_entries",
    } <= {
        foreign_key["referred_table"]
        for foreign_key in ledger_inspector.get_foreign_keys("verified_value_ledger_entries")
    }
    assert "uq_verified_ledger_idempotency" in {
        item["name"]
        for item in ledger_inspector.get_unique_constraints("verified_value_ledger_entries")
    }
    command.downgrade(config, "20260726_0015")
    assert not (wp_216_tables & set(inspect(postgres_engine).get_table_names()))
    assert "economic_baseline_versions" in inspect(postgres_engine).get_table_names()
    command.upgrade(config, "head")
    assert wp_216_tables <= set(inspect(postgres_engine).get_table_names())

    wp_215_tables = {
        "recovery_opportunities",
        "opportunity_findings",
        "opportunity_actions",
        "economic_scenarios",
        "economic_assumptions",
        "economic_calculations",
        "prioritization_assessments",
        "opportunity_overlap_groups",
        "opportunity_overlap_members",
        "opportunity_decisions",
        "economic_audit_events",
        "economic_baseline_versions",
    }
    economics_inspector = inspect(postgres_engine)
    opportunity_columns = {
        column["name"]: column
        for column in economics_inspector.get_columns("recovery_opportunities")
    }
    calculation_columns = {
        column["name"]: column
        for column in economics_inspector.get_columns("economic_calculations")
    }
    assert str(opportunity_columns["id"]["type"]) == "UUID"
    assert str(opportunity_columns["organization_id"]["type"]) == "UUID"
    assert str(opportunity_columns["limitations"]["type"]) == "JSONB"
    assert str(calculation_columns["gross_exposure"]["type"]) == "NUMERIC(38, 12)"
    assert str(calculation_columns["expected_roi"]["type"]) == "NUMERIC(38, 12)"
    assert str(calculation_columns["input_snapshot"]["type"]) == "JSONB"
    assert {
        "uq_recovery_opportunity_idempotency",
        "uq_recovery_opportunity_source",
    } <= {
        item["name"]
        for item in economics_inspector.get_unique_constraints("recovery_opportunities")
    }
    assert "ck_scenario_rates" in {
        item["name"] for item in economics_inspector.get_check_constraints("economic_scenarios")
    }
    assert {
        "organizations",
        "findings",
        "recovery_opportunities",
    } <= {
        foreign_key["referred_table"]
        for table in ("recovery_opportunities", "opportunity_findings")
        for foreign_key in economics_inspector.get_foreign_keys(table)
    }
    command.downgrade(config, "20260725_0014")
    assert not (wp_215_tables & set(inspect(postgres_engine).get_table_names()))
    assert "operational_actions" in inspect(postgres_engine).get_table_names()
    command.upgrade(config, "head")
    assert_schema_at_head(postgres_engine)

    wp_214_tables = {
        "operational_actions",
        "action_plan_steps",
        "action_dependencies",
        "action_resource_requirements",
        "action_events",
        "action_evidence",
        "action_outcomes",
        "action_model_feedback",
    }
    action_columns = {
        column["name"]: column
        for column in inspect(postgres_engine).get_columns("operational_actions")
    }
    assert str(action_columns["id"]["type"]) == "UUID"
    assert str(action_columns["priority_components"]["type"]) == "JSONB"
    assert str(action_columns["expected_avoided_cost"]["type"]) == "NUMERIC(38, 12)"
    assert "uq_action_idempotency" in {
        item["name"]
        for item in inspect(postgres_engine).get_unique_constraints("operational_actions")
    }
    command.downgrade(config, "20260725_0013")
    assert not (wp_214_tables & set(inspect(postgres_engine).get_table_names()))
    assert "reliability_executions" in inspect(postgres_engine).get_table_names()
    command.upgrade(config, "head")
    assert_schema_at_head(postgres_engine)

    wp_213_tables = {
        "reliability_executions",
        "reliability_metrics",
        "reliability_model_results",
        "reliability_execution_steps",
        "reliability_method_registry",
        "reliability_review_feedback",
    }
    command.downgrade(config, "20260725_0012")
    tables_at_wp_212 = set(inspect(postgres_engine).get_table_names())
    assert not (wp_213_tables & tables_at_wp_212)
    assert {
        "forecast_executions",
        "forecast_method_registry",
        "forecast_execution_steps",
    } <= tables_at_wp_212
    command.upgrade(config, "head")
    assert_schema_at_head(postgres_engine)

    wp_212_tables = {
        "forecast_executions",
        "forecast_candidates",
        "forecast_backtests",
        "forecast_metrics",
        "forecast_points",
        "forecast_scenarios",
        "forecast_revisions",
        "forecast_actuals",
        "forecast_accuracy_results",
        "forecast_method_registry",
        "forecast_execution_steps",
    }
    command.downgrade(config, "20260725_0011")
    assert not (wp_212_tables & set(inspect(postgres_engine).get_table_names()))
    command.upgrade(config, "head")
    assert_schema_at_head(postgres_engine)

    wp_211_tables = {
        "statistical_executions",
        "statistical_baselines",
        "statistical_observations",
        "statistical_score_components",
        "statistical_execution_steps",
        "statistical_method_registry",
        "anomaly_suppression_records",
        "anomaly_review_feedback",
    }
    command.downgrade(config, "20260725_0010")
    assert not (wp_211_tables & set(inspect(postgres_engine).get_table_names()))
    command.upgrade(config, "head")
    assert_schema_at_head(postgres_engine)

    wp_210_tables = {
        "oikb_definitions",
        "oikb_definition_versions",
        "oikb_parameters",
        "oikb_input_requirements",
        "oikb_evidence_requirements",
        "oikb_sources",
        "oikb_definition_sources",
        "oikb_validation_cases",
        "oikb_validation_results",
        "oikb_approvals",
        "oikb_change_log",
        "oikb_relationships",
    }
    command.downgrade(config, "20260725_0009")
    assert not (wp_210_tables & set(inspect(postgres_engine).get_table_names()))
    assert "oikb_definition_id" not in {
        column["name"] for column in inspect(postgres_engine).get_columns("findings")
    }
    command.upgrade(config, "head")
    assert_schema_at_head(postgres_engine)

    wp_209_tables = {
        "intelligence_orchestration_requests",
        "intelligence_orchestration_decisions",
        "intelligence_orchestration_steps",
        "intelligence_engine_registrations",
        "intelligence_orchestration_status_history",
    }
    command.downgrade(config, "20260725_0008")
    assert not (wp_209_tables & set(inspect(postgres_engine).get_table_names()))
    command.upgrade(config, "head")
    assert_schema_at_head(postgres_engine)

    wp_208_tables = {
        "finding_evidence_bundles",
        "finding_evidence_items",
        "finding_calculation_traces",
        "finding_rule_traces",
        "finding_reviews",
        "finding_status_history",
    }
    command.downgrade(config, "20260724_0007")
    assert not (wp_208_tables & set(inspect(postgres_engine).get_table_names()))
    command.upgrade(config, "head")
    assert_schema_at_head(postgres_engine)

    wp_207_tables = {
        "intelligence_executions",
        "intelligence_execution_evidence",
    }
    command.downgrade(config, "20260724_0006")
    assert not (wp_207_tables & set(inspect(postgres_engine).get_table_names()))
    command.upgrade(config, "head")
    assert_schema_at_head(postgres_engine)

    wp_206_tables = {
        "trust_assessments",
        "trust_rule_results",
        "trust_evidence",
        "analytical_readiness_decisions",
    }
    command.downgrade(config, "20260724_0005")
    assert not (wp_206_tables & set(inspect(postgres_engine).get_table_names()))
    command.upgrade(config, "head")
    assert_schema_at_head(postgres_engine)

    command.downgrade(config, "20260724_0004")
    wp_205_tables = {
        "raw_storage_objects",
        "raw_record_references",
        "processing_runs",
        "lineage_nodes",
        "lineage_edges",
        "lineage_events",
    }
    assert not (wp_205_tables & set(inspect(postgres_engine).get_table_names()))
    command.upgrade(config, "head")
    assert_schema_at_head(postgres_engine)

    command.downgrade(config, "20260724_0003")
    wp_203_tables = set(inspect(postgres_engine).get_table_names())
    wp_204_tables = {"ingestion_batches", "datasets", "dataset_versions"}
    assert not (wp_204_tables & wp_203_tables)
    assert (
        MANAGED_TABLES
        - wp_204_tables
        - wp_205_tables
        - wp_206_tables
        - wp_207_tables
        - wp_208_tables
        - wp_209_tables
        - wp_210_tables
        - wp_211_tables
        - wp_212_tables
        - wp_213_tables
        - wp_214_tables
        - wp_215_tables
        - wp_216_tables
        - wp_217_tables
        <= wp_203_tables
    )

    command.upgrade(config, "head")
    assert_schema_at_head(postgres_engine)

    command.downgrade(config, "base")
    assert not (MANAGED_TABLES & set(inspect(postgres_engine).get_table_names()))

    command.upgrade(config, "head")
    assert_schema_at_head(postgres_engine)


@pytest.mark.postgres
def test_forecasting_downgrade_maps_readiness_to_supported_level(
    postgres_engine: Engine,
) -> None:
    config = alembic_config(require_disposable_postgres_url())
    command.upgrade(config, "head")
    with Session(postgres_engine) as session:
        organization_id, _, trust_id, _, _ = statistical_foundation(
            session, f"postgres-forecast-downgrade-{uuid4().hex[:8]}"
        )
        session.add(
            AnalyticalReadinessDecision(
                organization_id=organization_id,
                trust_assessment_id=trust_id,
                analytical_level="forecasting",
                readiness_status="ready",
                blocking_rule_codes=[],
                warning_rule_codes=[],
                explanation="Forecast-ready history.",
            )
        )
        session.commit()

    command.downgrade(config, "20260725_0011")
    with postgres_engine.connect() as connection:
        forecasting_count = connection.scalar(
            text(
                "SELECT count(*) FROM analytical_readiness_decisions "
                "WHERE analytical_level = 'forecasting'"
            )
        )
    assert forecasting_count == 0
    command.upgrade(config, "head")
    assert "forecast_executions" in inspect(postgres_engine).get_table_names()


@pytest.mark.postgres
def test_source_system_uuid_scope_and_constraints(postgres_engine: Engine) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    organization_service = OrganizationService()
    source_service = SourceSystemService()
    with Session(postgres_engine) as session:
        suffix = uuid4().hex[:10]
        first = organization_service.create(
            session,
            OrganizationCreate(
                name="PostgreSQL Source First",
                slug=f"postgres-source-first-{suffix}",
                country_code="US",
                default_currency="USD",
                timezone="UTC",
            ),
        )
        second = organization_service.create(
            session,
            OrganizationCreate(
                name="PostgreSQL Source Second",
                slug=f"postgres-source-second-{suffix}",
                country_code="US",
                default_currency="USD",
                timezone="UTC",
            ),
        )
        payload = SourceSystemCreate(
            name="PostgreSQL ERP",
            code="postgres-erp",
            system_type="erp",
            integration_method="database",
            configuration_metadata={"schema": "public"},
        )
        actor = uuid4()
        source = source_service.create(session, first.id, payload, actor)
        assert isinstance(source.id, UUID)
        assert source_service.list(session, first.id) == [source]
        assert source_service.list(session, second.id) == []
        with pytest.raises(DuplicateSourceSystemCodeError):
            source_service.create(session, first.id, payload, actor)
        source_service.create(session, second.id, payload, actor)


@pytest.mark.postgres
def test_ingestion_governance_on_postgres(postgres_engine: Engine) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    organization_service = OrganizationService()
    source_service = SourceSystemService()
    batch_service = IngestionBatchService()
    dataset_service = DatasetService()
    version_service = DatasetVersionService(dataset_service, batch_service)
    with Session(postgres_engine) as session:
        suffix = uuid4().hex[:10]
        organization = organization_service.create(
            session,
            OrganizationCreate(
                name="PostgreSQL Ingestion",
                slug=f"postgres-ingestion-{suffix}",
                country_code="US",
                default_currency="USD",
                timezone="UTC",
            ),
        )
        source = source_service.create(
            session,
            organization.id,
            SourceSystemCreate(
                name="PostgreSQL ERP",
                code="postgres-erp",
                system_type="erp",
                integration_method="api",
            ),
            uuid4(),
        )
        batch = batch_service.create(
            session,
            organization.id,
            IngestionBatchCreate(
                source_system_id=source.id,
                batch_number=f"postgres-batch-{suffix}",
                ingestion_method="database_extract",
                trigger_type="scheduled",
                idempotency_key=f"postgres-key-{suffix}",
                manifest_metadata={"schema": "public"},
            ),
            uuid4(),
        )
        dataset = dataset_service.create(
            session,
            organization.id,
            DatasetCreate(
                source_system_id=source.id,
                name="PostgreSQL Invoices",
                code=f"postgres-invoices-{suffix}",
                domain="invoices",
                dataset_type="transactional",
                metadata_json={"validated": True},
            ),
            uuid4(),
        )
        version = version_service.create(
            session,
            organization.id,
            dataset.id,
            DatasetVersionCreate(
                ingestion_batch_id=batch.id,
                source_file_name="invoices.csv",
                source_file_extension="csv",
            ),
        )
        version_service.update_counts(
            session,
            organization.id,
            dataset.id,
            version.id,
            DatasetVersionCountsUpdate(
                record_count=12,
                accepted_record_count=10,
                rejected_record_count=2,
            ),
        )
        reconciled = batch_service.get(session, organization.id, batch.id)
        assert isinstance(reconciled.id, UUID)
        assert (reconciled.actual_dataset_count, reconciled.actual_record_count) == (
            1,
            12,
        )


@pytest.mark.postgres
def test_raw_storage_uuid_scope_and_foreign_keys_on_postgres(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    organization_service = OrganizationService()
    source_service = SourceSystemService()
    batch_service = IngestionBatchService()
    dataset_service = DatasetService()
    version_service = DatasetVersionService(dataset_service, batch_service)
    raw_service = RawStorageObjectService()
    with Session(postgres_engine) as session:
        suffix = uuid4().hex[:10]
        organization = organization_service.create(
            session,
            OrganizationCreate(
                name="PostgreSQL Raw",
                slug=f"postgres-raw-{suffix}",
                country_code="US",
                default_currency="USD",
                timezone="UTC",
            ),
        )
        source = source_service.create(
            session,
            organization.id,
            SourceSystemCreate(
                name="Raw source",
                code="raw-source",
                system_type="erp",
                integration_method="file_upload",
            ),
            uuid4(),
        )
        batch = batch_service.create(
            session,
            organization.id,
            IngestionBatchCreate(
                source_system_id=source.id,
                batch_number=f"raw-batch-{suffix}",
                ingestion_method="file_upload",
                trigger_type="manual",
            ),
            uuid4(),
        )
        dataset = dataset_service.create(
            session,
            organization.id,
            DatasetCreate(
                source_system_id=source.id,
                name="Raw dataset",
                code=f"raw-dataset-{suffix}",
                domain="operations",
                dataset_type="transactional",
            ),
            uuid4(),
        )
        version = version_service.create(
            session,
            organization.id,
            dataset.id,
            DatasetVersionCreate(ingestion_batch_id=batch.id),
        )
        raw_object = raw_service.register(
            session,
            organization.id,
            RawStorageObjectCreate(
                source_system_id=source.id,
                ingestion_batch_id=batch.id,
                dataset_version_id=version.id,
                object_number=f"raw-object-{suffix}",
                object_type="file",
                storage_provider="local",
                storage_reference=f"opaque/raw-object-{suffix}",
                content_checksum_algorithm="sha256",
                content_checksum="a" * 64,
                size_bytes=42,
                received_at=datetime.now(UTC),
            ),
            uuid4(),
        )
        assert isinstance(raw_object.id, UUID)
        assert raw_service.list(session, organization.id) == [raw_object]
        trust_service = TrustAssessmentService()
        assessment = trust_service.create_and_execute(
            session,
            organization.id,
            dataset.id,
            TrustAssessmentCreate(
                ingestion_batch_id=batch.id,
                records=[{"id": "1", "amount": 42}],
                rule_configurations={
                    "required_field_completeness": {"required_fields": ["id", "amount"]},
                    "primary_identifier_uniqueness": {"identifier_field": "id"},
                },
            ),
        )
        assert isinstance(assessment.id, UUID)
        assert assessment.overall_score == 100
        assert len(trust_service.rule_results(session, organization.id, assessment.id)) == 2
        assert len(trust_service.readiness(session, organization.id, assessment.id)) == 7


@pytest.mark.postgres
def test_membership_constraints_and_organization_cascade(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    organization_service = OrganizationService()
    membership_service = OrganizationMembershipService()

    with Session(postgres_engine) as session:
        suffix = uuid4().hex[:10]
        organization = organization_service.create(
            session,
            OrganizationCreate(
                name="PostgreSQL Membership",
                slug=f"postgres-membership-{suffix}",
                country_code="US",
                default_currency="USD",
                timezone="UTC",
            ),
        )
        user_id = uuid4()
        payload = MembershipCreate(
            user_id=user_id,
            role=MembershipRole.ORGANIZATION_ADMIN,
            status=MembershipStatus.ACTIVE,
        )
        membership = membership_service.create(
            session,
            organization.id,
            payload,
            invited_by_user_id=uuid4(),
        )
        with pytest.raises(DuplicateMembershipError):
            membership_service.create(
                session,
                organization.id,
                payload,
                invited_by_user_id=uuid4(),
            )

        membership_id = membership.id
        session.delete(organization)
        session.commit()
        assert session.get(OrganizationMembership, membership_id) is None

        invalid_organization = organization_service.create(
            session,
            OrganizationCreate(
                name="PostgreSQL Invalid Membership",
                slug=f"postgres-invalid-membership-{suffix}",
                country_code="US",
                default_currency="USD",
                timezone="UTC",
            ),
        )
        session.add(
            OrganizationMembership(
                organization_id=invalid_organization.id,
                user_id=uuid4(),
                role="invalid_role",
                status=MembershipStatus.ACTIVE.value,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


@pytest.mark.postgres
def test_uuid_foreign_keys_and_finding_tenant_scope(postgres_engine: Engine) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    organization_service = OrganizationService()
    finding_service = FindingService()

    with Session(postgres_engine) as session:
        suffix = uuid4().hex[:10]
        first = organization_service.create(
            session,
            OrganizationCreate(
                name="PostgreSQL First",
                slug=f"postgres-first-{suffix}",
                country_code="US",
                default_currency="USD",
                timezone="UTC",
            ),
        )
        second = organization_service.create(
            session,
            OrganizationCreate(
                name="PostgreSQL Second",
                slug=f"postgres-second-{suffix}",
                country_code="US",
                default_currency="USD",
                timezone="UTC",
            ),
        )
        assert isinstance(first.id, UUID)
        assert isinstance(second.id, UUID)

        payload = FindingCreate(
            rule_id="POSTGRES-TEST",
            title="PostgreSQL tenant scope",
            summary="Verifies native UUID and organization filtering",
            domain="maintenance",
            exposure_low=1,
            exposure_high=2,
            confidence_score=0.9,
            evidence=[
                {
                    "source_system": "postgres_test",
                    "source_record_id": suffix,
                    "evidence_type": "validation",
                    "payload": {"validated": True},
                }
            ],
        )
        finding = finding_service.create(session, first.id, payload)
        assert isinstance(finding.id, UUID)
        assert [item.id for item in finding_service.list(session, first.id)] == [finding.id]
        assert finding_service.list(session, second.id) == []

        session.add(
            Finding(
                organization_id=uuid4(),
                rule_id="INVALID-FK",
                title="Invalid organization",
                summary="Must fail",
                domain="maintenance",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


@pytest.mark.postgres
def test_intelligence_decimal_and_tenant_scope_on_postgres(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    organization_service = OrganizationService()
    source_service = SourceSystemService()
    dataset_service = DatasetService()
    trust_service = TrustAssessmentService()
    intelligence_service = IntelligenceExecutionService()
    with Session(postgres_engine) as session:
        suffix = uuid4().hex[:10]
        actor = uuid4()
        organizations = [
            organization_service.create(
                session,
                OrganizationCreate(
                    name=f"Intelligence {name}",
                    slug=f"postgres-intelligence-{name}-{suffix}",
                    country_code="US",
                    default_currency="USD",
                    timezone="UTC",
                ),
            )
            for name in ("first", "second")
        ]
        source = source_service.create(
            session,
            organizations[0].id,
            SourceSystemCreate(
                name="Intelligence ERP",
                code="intelligence-erp",
                system_type="erp",
                integration_method="api",
            ),
            actor,
        )
        dataset = dataset_service.create(
            session,
            organizations[0].id,
            DatasetCreate(
                source_system_id=source.id,
                name="Canonical values",
                code=f"canonical-values-{suffix}",
                domain="finance",
                dataset_type="transactional",
                default_currency="USD",
            ),
            actor,
        )
        assessment = trust_service.create_and_execute(
            session,
            organizations[0].id,
            dataset.id,
            TrustAssessmentCreate(
                records=[{"id": "1", "amount": "0.10"}],
                rule_configurations={
                    "required_field_completeness": {"required_fields": ["id", "amount"]},
                    "numeric_range_validity": {"numeric_ranges": {"amount": {"minimum": 0}}},
                },
            ),
        )
        execution = intelligence_service.execute(
            session,
            organizations[0].id,
            IntelligenceExecutionCreate(
                dataset_id=dataset.id,
                trust_assessment_id=assessment.id,
                execution_type="calculation",
                definition_code="sum",
                records=[{"amount": "0.10"}, {"amount": "0.20"}],
                parameters={"field": "amount"},
                currency="USD",
            ),
            actor,
        )
        assert str(execution.result_value) == "0.300000000000"
        assert intelligence_service.list(session, organizations[0].id) == [execution]
        assert intelligence_service.list(session, organizations[1].id) == []
        finding = FindingPublicationService().publish_candidate_finding(
            session,
            organizations[0].id,
            CandidateFindingCreate(
                execution_id=execution.id,
                result_id=execution.id,
                finding_type="kpi",
                title="PostgreSQL exact arithmetic result",
                summary="Synthetic PostgreSQL finding publication.",
                domain_code="finance",
                measured_value=execution.result_value,
                measured_value_type="currency",
                measured_currency="USD",
                severity="info",
                severity_reason={"policy": "postgres-validation"},
                dataset_reference=f"{dataset.code}@postgres-validation",
                evidence_policy_code="WP208-POSTGRES",
                evidence_policy_version="1.0",
                calculation_traces=[
                    {
                        "operation_code": "sum",
                        "input_reference_summary": {"dataset_id": str(dataset.id)},
                        "parameter_summary": {"field": "amount"},
                    }
                ],
            ),
            actor,
        )
        assert str(finding.measured_value) == "0.300000000000"
        own, own_count = FindingQueryService().list(
            session,
            organizations[0].id,
            page=1,
            page_size=10,
        )
        other, other_count = FindingQueryService().list(
            session,
            organizations[1].id,
            page=1,
            page_size=10,
        )
        assert own == [finding]
        assert own_count == 1
        assert other == []
        assert other_count == 0


@pytest.mark.postgres
def test_orchestration_uuid_jsonb_idempotency_and_tenant_scope_on_postgres(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        suffix = uuid4().hex[:10]
        actor = uuid4()
        organizations = [
            OrganizationService().create(
                session,
                OrganizationCreate(
                    name=f"Orchestration {name}",
                    slug=f"postgres-orchestration-{name}-{suffix}",
                    country_code="US",
                    default_currency="USD",
                    timezone="UTC",
                ),
            )
            for name in ("first", "second")
        ]
        source = SourceSystemService().create(
            session,
            organizations[0].id,
            SourceSystemCreate(
                name="Orchestration ERP",
                code="orchestration-erp",
                system_type="erp",
                integration_method="api",
            ),
            actor,
        )
        dataset = DatasetService().create(
            session,
            organizations[0].id,
            DatasetCreate(
                source_system_id=source.id,
                name="Orchestration values",
                code=f"orchestration-values-{suffix}",
                domain="finance",
                dataset_type="transactional",
                default_currency="USD",
            ),
            actor,
        )
        assessment = TrustAssessmentService().create_and_execute(
            session,
            organizations[0].id,
            dataset.id,
            TrustAssessmentCreate(
                records=[{"id": "1", "amount": "0.10"}],
                rule_configurations={
                    "required_field_completeness": {"required_fields": ["id", "amount"]},
                    "numeric_range_validity": {"numeric_ranges": {"amount": {"minimum": 0}}},
                },
            ),
        )
        readiness = session.scalar(
            select(AnalyticalReadinessDecision).where(
                AnalyticalReadinessDecision.trust_assessment_id == assessment.id,
                AnalyticalReadinessDecision.analytical_level == "arithmetic",
            )
        )
        assert readiness is not None
        service = OrchestrationService()
        payload = OrchestrationCreate(
            definition_code="sum",
            definition_version="1.0",
            dataset_id=dataset.id,
            dataset_reference=f"{dataset.code}@postgres",
            trust_assessment_id=assessment.id,
            analytical_readiness_id=readiness.id,
            execution_type="calculation",
            records=[{"amount": "0.10"}, {"amount": "0.20"}],
            parameters={"field": "amount"},
            currency="USD",
            request_context={"synthetic": True},
            correlation_id=f"postgres-correlation-{suffix}",
            idempotency_key=f"postgres-idempotency-{suffix}",
        )
        orchestration = service.orchestrate(session, organizations[0].id, payload, actor)
        duplicate = service.orchestrate(session, organizations[0].id, payload, actor)
        assert isinstance(orchestration.id, UUID)
        assert duplicate.id == orchestration.id
        assert orchestration.request_context == {"synthetic": True}
        own, own_count = service.list_requests(session, organizations[0].id, page=1, page_size=10)
        other, other_count = service.list_requests(
            session, organizations[1].id, page=1, page_size=10
        )
        assert own == [orchestration]
        assert own_count == 1
        assert other == []
        assert other_count == 0
        assert (
            session.scalar(
                select(IntelligenceOrchestrationRequest).where(
                    IntelligenceOrchestrationRequest.id == orchestration.id,
                    IntelligenceOrchestrationRequest.organization_id == organizations[1].id,
                )
            )
            is None
        )


@pytest.mark.postgres
def test_statistical_uuid_jsonb_tenancy_and_execution_on_postgres(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        organization_id, _, trust_id, readiness_id, actor = statistical_foundation(
            session, f"postgres-statistical-{uuid4().hex[:8]}"
        )
        execution = statistical_execution_service.execute(
            session,
            organization_id,
            execution_payload(
                trust_id,
                readiness_id,
                key=f"postgres-statistical-{uuid4().hex}",
            ),
            actor,
        )
        assert execution.status == "succeeded"
        observations = statistical_execution_service.observations_for(
            session, organization_id, execution.id
        )
        assert observations[0].is_anomaly
        metadata = observations[0].method_trace["metadata"]
        assert isinstance(metadata, dict)
        assert metadata["method_code"] == "MODIFIED_Z_SCORE"
        assert observations[0].evidence_references[0]["aggregate_only"] is True
