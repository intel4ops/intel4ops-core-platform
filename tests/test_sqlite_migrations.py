from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_sqlite_migration_upgrade_downgrade_reupgrade() -> None:
    database_path = Path(__file__).parent / ".wp205_migration.sqlite"
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
        assert wp_205_tables <= set(inspect(engine).get_table_names())
        command.downgrade(config, "20260724_0004")
        assert not (wp_205_tables & set(inspect(engine).get_table_names()))
        assert {"ingestion_batches", "datasets", "dataset_versions"} <= set(
            inspect(engine).get_table_names()
        )
        command.upgrade(config, "head")
        assert wp_205_tables <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
        database_path.unlink(missing_ok=True)
