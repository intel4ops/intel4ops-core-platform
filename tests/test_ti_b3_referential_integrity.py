from importlib import import_module
from pathlib import Path
from unittest.mock import patch

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import (
    ForeignKeyConstraint,
    UniqueConstraint,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.orm import configure_mappers

import app.models  # noqa: F401
from app.db.session import Base
from app.models.forecasting import ForecastExecution

PARENT_CONSTRAINTS = {
    "forecast_executions": "uq_forecast_executions_org_id",
    "forecast_points": "uq_forecast_points_org_id",
}

RELATIONSHIPS = (
    (
        "forecast_executions",
        "fk_forecast_executions_org_dataset",
        "datasets",
        "dataset_id",
        "RESTRICT",
    ),
    (
        "forecast_executions",
        "fk_forecast_executions_org_dataset_version",
        "dataset_versions",
        "dataset_version_id",
        "RESTRICT",
    ),
    (
        "forecast_executions",
        "fk_forecast_executions_org_ingestion_batch",
        "ingestion_batches",
        "ingestion_batch_id",
        "RESTRICT",
    ),
    (
        "forecast_executions",
        "fk_forecast_executions_org_source_system",
        "source_systems",
        "source_system_id",
        "RESTRICT",
    ),
    (
        "forecast_executions",
        "fk_forecast_executions_org_trust_assessment",
        "trust_assessments",
        "trust_assessment_id",
        "RESTRICT",
    ),
    (
        "forecast_executions",
        "fk_forecast_executions_org_readiness",
        "analytical_readiness_decisions",
        "readiness_assessment_id",
        "RESTRICT",
    ),
    (
        "forecast_points",
        "fk_forecast_points_org_execution",
        "forecast_executions",
        "forecast_execution_id",
        "CASCADE",
    ),
    (
        "forecast_scenarios",
        "fk_forecast_scenarios_org_execution",
        "forecast_executions",
        "forecast_execution_id",
        "CASCADE",
    ),
    (
        "forecast_revisions",
        "fk_forecast_revisions_org_prior_execution",
        "forecast_executions",
        "prior_forecast_execution_id",
        "RESTRICT",
    ),
    (
        "forecast_revisions",
        "fk_forecast_revisions_org_revised_execution",
        "forecast_executions",
        "revised_forecast_execution_id",
        "RESTRICT",
    ),
    (
        "forecast_actuals",
        "fk_forecast_actuals_org_forecast_point",
        "forecast_points",
        "forecast_point_id",
        "RESTRICT",
    ),
    ("forecast_actuals", "fk_forecast_actuals_org_dataset", "datasets", "dataset_id", "RESTRICT"),
    (
        "forecast_actuals",
        "fk_forecast_actuals_org_dataset_version",
        "dataset_versions",
        "dataset_version_id",
        "RESTRICT",
    ),
    (
        "forecast_actuals",
        "fk_forecast_actuals_org_ingestion_batch",
        "ingestion_batches",
        "ingestion_batch_id",
        "RESTRICT",
    ),
    (
        "forecast_actuals",
        "fk_forecast_actuals_org_source_system",
        "source_systems",
        "source_system_id",
        "RESTRICT",
    ),
    (
        "forecast_accuracy_results",
        "fk_forecast_accuracy_results_org_execution",
        "forecast_executions",
        "forecast_execution_id",
        "CASCADE",
    ),
    (
        "forecast_accuracy_results",
        "fk_forecast_accuracy_results_org_forecast_point",
        "forecast_points",
        "forecast_point_id",
        "CASCADE",
    ),
)

TENANT_FOREIGN_KEYS = {item[1] for item in RELATIONSHIPS}

NEW_INDEXES = {
    "ix_forecast_execution_org_dataset",
    "ix_forecast_execution_org_dataset_version",
    "ix_forecast_execution_org_ingestion_batch",
    "ix_forecast_execution_org_source_system",
    "ix_forecast_execution_org_trust_assessment",
    "ix_forecast_execution_org_readiness",
    "ix_forecast_point_org_execution",
    "ix_forecast_scenario_org_execution",
    "ix_forecast_revision_org_revised",
    "ix_forecast_actual_org_dataset",
    "ix_forecast_actual_org_dataset_version",
    "ix_forecast_actual_org_ingestion_batch",
    "ix_forecast_actual_org_source_system",
    "ix_forecast_accuracy_org_forecast_point",
}

REUSED_INDEXES = {
    "ix_forecast_revision_org_prior",
    "uq_forecast_actual_point",
    "ix_forecast_accuracy_org_execution",
}

IN_SCOPE_TABLES = {
    "forecast_executions",
    "forecast_points",
    "forecast_scenarios",
    "forecast_revisions",
    "forecast_actuals",
    "forecast_accuracy_results",
}


def _named_constraints(table_name: str) -> list[object]:
    return list(Base.metadata.tables[table_name].constraints)


def test_metadata_contract_is_exact_and_mappers_configure() -> None:
    configure_mappers()
    unique_counts: dict[str, int] = {}
    foreign_key_counts: dict[str, int] = {}
    index_counts: dict[str, int] = {}

    for table in Base.metadata.tables.values():
        for constraint in table.constraints:
            if isinstance(constraint, UniqueConstraint) and constraint.name:
                name = str(constraint.name)
                unique_counts[name] = unique_counts.get(name, 0) + 1
            if isinstance(constraint, ForeignKeyConstraint) and constraint.name:
                name = str(constraint.name)
                foreign_key_counts[name] = foreign_key_counts.get(name, 0) + 1
        for index in table.indexes:
            if index.name:
                index_counts[index.name] = index_counts.get(index.name, 0) + 1

    assert {name for name in PARENT_CONSTRAINTS.values() if unique_counts.get(name)} == set(
        PARENT_CONSTRAINTS.values()
    )
    assert all(unique_counts[name] == 1 for name in PARENT_CONSTRAINTS.values())
    assert {name for name in TENANT_FOREIGN_KEYS if foreign_key_counts.get(name)} == (
        TENANT_FOREIGN_KEYS
    )
    assert all(foreign_key_counts[name] == 1 for name in TENANT_FOREIGN_KEYS)
    assert all(index_counts[name] == 1 for name in NEW_INDEXES)
    assert index_counts["ix_forecast_revision_org_prior"] == 1
    assert index_counts["ix_forecast_accuracy_org_execution"] == 1
    assert unique_counts["uq_forecast_actual_point"] == 1

    assert (
        sum(
            isinstance(item, ForeignKeyConstraint) and len(item.columns) == 1
            for table_name in IN_SCOPE_TABLES
            for item in _named_constraints(table_name)
        )
        >= 17
    )
    assert ForecastExecution.points.property._user_defined_foreign_keys == {
        Base.metadata.tables["forecast_points"].c.forecast_execution_id
    }


def test_exact_delete_policy_and_exclusions() -> None:
    assert len(RELATIONSHIPS) == 17
    assert sum(item[4] == "RESTRICT" for item in RELATIONSHIPS) == 13
    assert sum(item[4] == "CASCADE" for item in RELATIONSHIPS) == 4
    for table_name in (
        "forecast_candidates",
        "forecast_backtests",
        "forecast_metrics",
        "forecast_execution_steps",
        "forecast_method_registry",
    ):
        assert not any(
            isinstance(item, ForeignKeyConstraint) and len(item.columns) == 2
            for item in Base.metadata.tables[table_name].constraints
        )


@pytest.mark.parametrize("relationship", RELATIONSHIPS, ids=lambda item: item[1])
def test_diagnostics_detect_each_cross_tenant_relationship(
    relationship: tuple[str, str, str, str, str],
) -> None:
    child, constraint_name, parent, parent_column, ondelete = relationship
    migration = import_module(
        "migrations.versions.20260801_0028_ti_b3_forecasting_actuals_integrity"
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(f"CREATE TABLE {parent} (id TEXT PRIMARY KEY, organization_id TEXT NOT NULL)")
        )
        connection.execute(
            text(
                f"CREATE TABLE {child} "
                f"(id TEXT PRIMARY KEY, organization_id TEXT, {parent_column} TEXT)"
            )
        )
        connection.execute(
            text(f"INSERT INTO {parent} (id, organization_id) VALUES ('parent-1', 'tenant-a')")
        )
        connection.execute(
            text(
                f"INSERT INTO {child} (id, organization_id, {parent_column}) "
                "VALUES ('child-1', 'tenant-b', 'parent-1')"
            )
        )
        with (
            patch.object(
                migration,
                "COMPOSITE_FOREIGN_KEYS",
                ((child, constraint_name, parent, parent_column, ondelete),),
            ),
            patch.object(migration, "PARENT_UNIQUES", ()),
            patch.object(migration.op, "get_bind", return_value=connection),
            pytest.raises(RuntimeError, match=f"{constraint_name}.*1 violating rows"),
        ):
            migration._assert_clean_tenant_references()


@pytest.mark.parametrize("violation", ("orphan", "missing_tenant", "duplicate_parent"))
def test_diagnostics_detect_orphans_missing_tenants_and_duplicate_targets(
    violation: str,
) -> None:
    migration = import_module(
        "migrations.versions.20260801_0028_ti_b3_forecasting_actuals_integrity"
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE parents (id TEXT, organization_id TEXT)"))
        connection.execute(
            text(
                "CREATE TABLE children (id TEXT PRIMARY KEY, organization_id TEXT, parent_id TEXT)"
            )
        )
        if violation == "duplicate_parent":
            connection.execute(
                text(
                    "INSERT INTO parents (id, organization_id) "
                    "VALUES ('parent-1', 'tenant-a'), ('parent-1', 'tenant-a')"
                )
            )
            foreign_keys: tuple[tuple[str, str, str, str, str], ...] = ()
            parents: tuple[tuple[str, str], ...] = (("parents", "uq_parents_org_id"),)
            expected = "uq_parents_org_id.*1 duplicate targets"
        else:
            connection.execute(
                text(
                    "INSERT INTO children (id, organization_id, parent_id) "
                    "VALUES ('child-1', :organization_id, 'missing-parent')"
                ),
                {"organization_id": None if violation == "missing_tenant" else "tenant-a"},
            )
            foreign_keys = (
                ("children", "fk_children_org_parent", "parents", "parent_id", "RESTRICT"),
            )
            parents = ()
            expected = "fk_children_org_parent.*1 violating rows"

        with (
            patch.object(migration, "COMPOSITE_FOREIGN_KEYS", foreign_keys),
            patch.object(migration, "PARENT_UNIQUES", parents),
            patch.object(migration.op, "get_bind", return_value=connection),
            pytest.raises(RuntimeError, match=expected),
        ):
            migration._assert_clean_tenant_references()
        assert connection.scalar(text("SELECT count(*) FROM children")) == (
            0 if violation == "duplicate_parent" else 1
        )


def test_sqlite_migration_round_trip_restores_ti_b3_objects(tmp_path: Path) -> None:
    database_path = tmp_path / "ti-b3-lifecycle.sqlite"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    engine = create_engine(database_url)

    def object_names() -> tuple[set[str], set[str], set[str]]:
        inspector = inspect(engine)
        return (
            {
                str(item["name"])
                for table_name in IN_SCOPE_TABLES
                for item in inspector.get_unique_constraints(table_name)
                if item["name"] is not None
            },
            {
                str(item["name"])
                for table_name in IN_SCOPE_TABLES
                for item in inspector.get_foreign_keys(table_name)
                if item["name"] is not None
            },
            {
                str(item["name"])
                for table_name in IN_SCOPE_TABLES
                for item in inspector.get_indexes(table_name)
                if item["name"] is not None
            },
        )

    try:
        command.upgrade(config, "head")
        unique_names, foreign_key_names, index_names = object_names()
        assert set(PARENT_CONSTRAINTS.values()) <= unique_names
        assert TENANT_FOREIGN_KEYS <= foreign_key_names
        assert NEW_INDEXES <= index_names
        assert REUSED_INDEXES <= unique_names | index_names

        command.downgrade(config, "20260801_0027")
        unique_names, foreign_key_names, index_names = object_names()
        assert set(PARENT_CONSTRAINTS.values()).isdisjoint(unique_names)
        assert TENANT_FOREIGN_KEYS.isdisjoint(foreign_key_names)
        assert NEW_INDEXES.isdisjoint(index_names)
        assert REUSED_INDEXES <= unique_names | index_names

        command.upgrade(config, "head")
        unique_names, foreign_key_names, index_names = object_names()
        assert set(PARENT_CONSTRAINTS.values()) <= unique_names
        assert TENANT_FOREIGN_KEYS <= foreign_key_names
        assert NEW_INDEXES <= index_names
    finally:
        engine.dispose()
