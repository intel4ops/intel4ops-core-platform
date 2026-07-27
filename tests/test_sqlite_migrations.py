from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_sqlite_migration_upgrade_downgrade_reupgrade() -> None:
    database_path = Path(__file__).parent / ".wp206_migration.sqlite"
    database_path.unlink(missing_ok=True)
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    engine = create_engine(database_url)

    try:
        command.upgrade(config, "head")
        wp_205_tables = {
            "raw_storage_objects",
            "raw_record_references",
            "processing_runs",
            "lineage_nodes",
            "lineage_edges",
            "lineage_events",
        }
        wp_206_tables = {
            "trust_assessments",
            "trust_rule_results",
            "trust_evidence",
            "analytical_readiness_decisions",
        }
        wp_207_tables = {
            "intelligence_executions",
            "intelligence_execution_evidence",
        }
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
            "operational_actions",
            "action_plan_steps",
            "action_dependencies",
            "action_resource_requirements",
            "action_events",
            "action_evidence",
            "action_outcomes",
            "action_model_feedback",
        }
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
        wp_216_tables = {
            "recovery_cases",
            "recovery_executions",
            "recovery_value_measurements",
            "recovery_evidence_links",
            "recovery_finance_verifications",
            "verified_value_ledger_entries",
            "recovery_audit_events",
        }
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
        wp_219_tables = {
            "industry_pack_versions",
            "industry_pack_assignment_states",
            "industry_pack_components",
            "industry_pack_validation_results",
            "industry_pack_executions",
            "industry_pack_governance_events",
        }
        assert (
            wp_210_tables
            | wp_211_tables
            | wp_212_tables
            | wp_215_tables
            | wp_216_tables
            | wp_217_tables
            | wp_218_tables
            | wp_219_tables
            <= set(inspect(engine).get_table_names())
        )
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM products")) == 6
            assert connection.scalar(text("SELECT count(*) FROM plans")) == 5
            assert connection.scalar(text("SELECT count(*) FROM usage_meter_definitions")) == 18
            assert connection.scalar(text("SELECT count(*) FROM industry_pack_definitions")) == 7
            assert connection.scalar(text("SELECT count(*) FROM application_clients")) == 4
            assert connection.scalar(text("SELECT count(*) FROM industry_pack_versions")) == 4
            assert connection.scalar(text("SELECT count(*) FROM industry_pack_components")) == 76
        command.downgrade(config, "20260726_0018")
        assert not (wp_219_tables & set(inspect(engine).get_table_names()))
        assert wp_218_tables <= set(inspect(engine).get_table_names())
        command.upgrade(config, "head")
        assert wp_219_tables <= set(inspect(engine).get_table_names())
        command.downgrade(config, "20260726_0017")
        assert not (wp_218_tables & set(inspect(engine).get_table_names()))
        assert wp_217_tables <= set(inspect(engine).get_table_names())
        command.upgrade(config, "head")
        assert wp_218_tables <= set(inspect(engine).get_table_names())
        command.downgrade(config, "20260726_0016")
        assert not (wp_217_tables & set(inspect(engine).get_table_names()))
        assert wp_216_tables <= set(inspect(engine).get_table_names())
        command.upgrade(config, "head")
        assert wp_217_tables <= set(inspect(engine).get_table_names())
        command.downgrade(config, "20260726_0015")
        assert not ((wp_216_tables | wp_217_tables) & set(inspect(engine).get_table_names()))
        assert wp_215_tables <= set(inspect(engine).get_table_names())
        command.upgrade(config, "head")
        assert wp_216_tables <= set(inspect(engine).get_table_names())
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM oikb_definitions")) == 34
            assert connection.scalar(text("SELECT count(*) FROM oikb_validation_cases")) == 320
            assert connection.scalar(text("SELECT count(*) FROM statistical_method_registry")) == 40
            assert connection.scalar(text("SELECT count(*) FROM forecast_method_registry")) == 19
        command.downgrade(config, "20260725_0014")
        assert not (
            (wp_215_tables | wp_216_tables | wp_217_tables | wp_218_tables | wp_219_tables)
            & set(inspect(engine).get_table_names())
        )
        assert wp_212_tables <= set(inspect(engine).get_table_names())
        command.upgrade(config, "head")
        assert wp_215_tables <= set(inspect(engine).get_table_names())
        command.downgrade(config, "20260725_0011")
        assert not (wp_212_tables & set(inspect(engine).get_table_names()))
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM oikb_definitions")) == 22
            assert connection.scalar(text("SELECT count(*) FROM oikb_validation_cases")) == 308
        command.upgrade(config, "head")
        assert wp_212_tables <= set(inspect(engine).get_table_names())
        command.downgrade(config, "20260725_0010")
        assert not (wp_211_tables & set(inspect(engine).get_table_names()))
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM oikb_definitions")) == 10
            assert connection.scalar(text("SELECT count(*) FROM oikb_validation_cases")) == 56
        command.upgrade(config, "head")
        assert wp_211_tables <= set(inspect(engine).get_table_names())
        command.downgrade(config, "20260725_0009")
        assert not (wp_210_tables & set(inspect(engine).get_table_names()))
        command.upgrade(config, "head")
        assert wp_210_tables <= set(inspect(engine).get_table_names())
        assert wp_205_tables | wp_206_tables | wp_207_tables <= set(
            inspect(engine).get_table_names()
        )
        command.downgrade(config, "20260724_0006")
        assert not (wp_207_tables & set(inspect(engine).get_table_names()))
        assert wp_206_tables <= set(inspect(engine).get_table_names())
        command.upgrade(config, "head")
        assert wp_207_tables <= set(inspect(engine).get_table_names())
        command.downgrade(config, "20260724_0005")
        assert not (wp_206_tables & set(inspect(engine).get_table_names()))
        assert wp_205_tables <= set(inspect(engine).get_table_names())
        command.upgrade(config, "head")
        assert wp_206_tables <= set(inspect(engine).get_table_names())
        command.downgrade(config, "20260724_0004")
        assert not (wp_205_tables & set(inspect(engine).get_table_names()))
        assert {"ingestion_batches", "datasets", "dataset_versions"} <= set(
            inspect(engine).get_table_names()
        )
        command.upgrade(config, "head")
        assert wp_205_tables | wp_206_tables <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
        database_path.unlink(missing_ok=True)
