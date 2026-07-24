import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


@pytest.mark.postgres
def test_migrations_on_disposable_postgres() -> None:
    database_url = os.getenv("TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("Set TEST_POSTGRES_URL to a disposable PostgreSQL database")
    if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        pytest.fail("TEST_POSTGRES_URL must be a PostgreSQL URL")
    if database_url == os.getenv("DATABASE_URL"):
        pytest.fail("TEST_POSTGRES_URL must not match the runtime DATABASE_URL")

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)

    engine = create_engine(database_url)
    try:
        command.upgrade(config, "head")
        tables = set(inspect(engine).get_table_names())
        assert {"organizations", "findings", "finding_evidence", "recovery_actions"} <= tables

        command.downgrade(config, "base")
        remaining_tables = set(inspect(engine).get_table_names())
        assert (
            not {
                "organizations",
                "findings",
                "finding_evidence",
                "recovery_actions",
            }
            & remaining_tables
        )

        command.upgrade(config, "head")
        restored_tables = set(inspect(engine).get_table_names())
        assert {
            "organizations",
            "findings",
            "finding_evidence",
            "recovery_actions",
        } <= restored_tables
    finally:
        engine.dispose()
