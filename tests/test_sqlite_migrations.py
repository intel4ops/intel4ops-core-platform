from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


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
