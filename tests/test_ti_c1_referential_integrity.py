from importlib import import_module
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import (
    ForeignKeyConstraint,
    UniqueConstraint,
    create_engine,
    inspect,
    select,
    text,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, configure_mappers
from test_progressive_orchestrator import (
    foundation as orchestration_foundation,
)
from test_progressive_orchestrator import request as orchestration_payload

import app.models  # noqa: F401
from app.db.session import Base
from app.models.orchestration import (
    IntelligenceOrchestrationDecision,
    IntelligenceOrchestrationRequest,
    IntelligenceOrchestrationStatusHistory,
    IntelligenceOrchestrationStep,
)
from app.services.orchestration_service import OrchestrationService

PARENT_CONSTRAINTS = {
    "intelligence_orchestration_requests": "uq_orchestration_requests_org_id",
}

RELATIONSHIPS = (
    (
        "intelligence_orchestration_decisions",
        "fk_orchestration_decisions_org_request",
        "intelligence_orchestration_requests",
        "orchestration_request_id",
        "CASCADE",
    ),
    (
        "intelligence_orchestration_steps",
        "fk_orchestration_steps_org_request",
        "intelligence_orchestration_requests",
        "orchestration_request_id",
        "CASCADE",
    ),
    (
        "intelligence_orchestration_status_history",
        "fk_orchestration_history_org_request",
        "intelligence_orchestration_requests",
        "orchestration_request_id",
        "CASCADE",
    ),
    (
        "intelligence_orchestration_requests",
        "fk_orchestration_requests_org_dataset",
        "datasets",
        "dataset_id",
        "RESTRICT",
    ),
    (
        "intelligence_orchestration_requests",
        "fk_orchestration_requests_org_dataset_version",
        "dataset_versions",
        "dataset_version_id",
        "RESTRICT",
    ),
    (
        "intelligence_orchestration_requests",
        "fk_orchestration_requests_org_trust_assessment",
        "trust_assessments",
        "trust_assessment_id",
        "RESTRICT",
    ),
    (
        "intelligence_orchestration_requests",
        "fk_orchestration_requests_org_readiness",
        "analytical_readiness_decisions",
        "analytical_readiness_id",
        "RESTRICT",
    ),
    (
        "reliability_executions",
        "fk_reliability_executions_org_orchestration_request",
        "intelligence_orchestration_requests",
        "orchestration_request_id",
        "RESTRICT",
    ),
    (
        "statistical_executions",
        "fk_statistical_executions_org_orchestration_request",
        "intelligence_orchestration_requests",
        "orchestration_request_id",
        "RESTRICT",
    ),
    (
        "forecast_executions",
        "fk_forecast_executions_org_orchestration_request",
        "intelligence_orchestration_requests",
        "orchestration_request_id",
        "RESTRICT",
    ),
)

TENANT_FOREIGN_KEYS = {item[1] for item in RELATIONSHIPS}

NEW_INDEXES = {
    "ix_orchestration_requests_org_dataset",
    "ix_orchestration_requests_org_dataset_version",
    "ix_orchestration_requests_org_trust_assessment",
    "ix_orchestration_requests_org_readiness",
    "ix_reliability_execution_org_orchestration_request",
    "ix_statistical_execution_org_orchestration_request",
    "ix_forecast_execution_org_orchestration_request",
}

REUSED_INDEXES = {
    "ix_orchestration_decisions_organization_request",
    "ix_orchestration_steps_organization_request",
    "ix_orchestration_history_organization_request",
}

IN_SCOPE_TABLES = {
    "intelligence_orchestration_requests",
    "intelligence_orchestration_decisions",
    "intelligence_orchestration_steps",
    "intelligence_orchestration_status_history",
    "reliability_executions",
    "statistical_executions",
    "forecast_executions",
}


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

    assert unique_counts["uq_orchestration_requests_org_id"] == 1
    assert all(foreign_key_counts[name] == 1 for name in TENANT_FOREIGN_KEYS)
    assert all(index_counts[name] == 1 for name in NEW_INDEXES | REUSED_INDEXES)
    assert unique_counts["uq_orchestration_requests_organization_idempotency"] == 1
    assert unique_counts["uq_orchestration_requests_organization_correlation"] == 1

    relationship_expectations = {
        IntelligenceOrchestrationRequest.decisions: "orchestration_request_id",
        IntelligenceOrchestrationDecision.request: "orchestration_request_id",
        IntelligenceOrchestrationRequest.steps: "orchestration_request_id",
        IntelligenceOrchestrationStep.request: "orchestration_request_id",
        IntelligenceOrchestrationRequest.history: "orchestration_request_id",
        IntelligenceOrchestrationStatusHistory.request: "orchestration_request_id",
    }
    for relationship_attribute, column_name in relationship_expectations.items():
        assert {
            column.name for column in relationship_attribute.property._user_defined_foreign_keys
        } == {column_name}


def test_single_column_foreign_keys_and_set_null_references_remain() -> None:
    for child, _, parent, parent_column, _ in RELATIONSHIPS:
        table = Base.metadata.tables[child]
        assert any(
            len(constraint.columns) == 1
            and tuple(constraint.columns)[0].name == parent_column
            and next(iter(constraint.elements)).column.table.name == parent
            for constraint in table.foreign_key_constraints
        )

    for table_name in (
        "reliability_executions",
        "statistical_executions",
        "forecast_executions",
    ):
        table = Base.metadata.tables[table_name]
        matching = [
            constraint
            for constraint in table.foreign_key_constraints
            if len(constraint.columns) == 1
            and tuple(constraint.columns)[0].name == "orchestration_request_id"
        ]
        assert len(matching) == 1
        assert matching[0].ondelete == "SET NULL"


def _orchestration_graph(
    db: Session, slug: str
) -> tuple[IntelligenceOrchestrationRequest, dict[str, object]]:
    organization_id, dataset_id, trust_id, readiness_id = orchestration_foundation(db, slug)
    request = OrchestrationService().orchestrate(
        db,
        organization_id,
        orchestration_payload(
            dataset_id,
            trust_id,
            readiness_id,
            key=f"ti-c1-{uuid4().hex}",
        ),
        uuid4(),
    )
    return request, {
        "organization_id": organization_id,
        "dataset_id": dataset_id,
        "dataset_version_id": request.dataset_version_id,
        "trust_assessment_id": trust_id,
        "analytical_readiness_id": readiness_id,
    }


def test_real_sql_enforces_orchestration_request_and_child_tenants(db: Session) -> None:
    first, first_refs = _orchestration_graph(db, f"ti-c1-first-{uuid4().hex[:8]}")
    second, second_refs = _orchestration_graph(db, f"ti-c1-second-{uuid4().hex[:8]}")

    request_reference_columns = (
        "dataset_id",
        "dataset_version_id",
        "trust_assessment_id",
        "analytical_readiness_id",
    )
    for column_name in request_reference_columns:
        original = getattr(first, column_name)
        setattr(first, column_name, second_refs[column_name])
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        assert getattr(db.get(IntelligenceOrchestrationRequest, first.id), column_name) == original

    child_models: tuple[type[Any], ...] = (
        IntelligenceOrchestrationDecision,
        IntelligenceOrchestrationStep,
        IntelligenceOrchestrationStatusHistory,
    )
    for model in child_models:
        child = db.scalar(select(model).where(model.orchestration_request_id == first.id))
        assert child is not None
        child.orchestration_request_id = second.id
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        restored = db.get(model, child.id)
        assert restored is not None
        assert restored.orchestration_request_id == first.id


def test_orm_navigation_and_clean_cross_tenant_rollback(db: Session) -> None:
    first, _ = _orchestration_graph(db, f"ti-c1-orm-first-{uuid4().hex[:8]}")
    second, _ = _orchestration_graph(db, f"ti-c1-orm-second-{uuid4().hex[:8]}")
    db.refresh(first)
    assert first.decisions and first.steps and first.history
    assert all(item.request.id == first.id for item in first.decisions)
    assert all(item.request.id == first.id for item in first.steps)
    assert all(item.request.id == first.id for item in first.history)

    decision = first.decisions[0]
    decision.request = second
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    restored = db.get(IntelligenceOrchestrationDecision, decision.id)
    assert restored is not None
    assert restored.request.id == first.id


@pytest.mark.parametrize("relationship", RELATIONSHIPS, ids=lambda item: item[1])
def test_diagnostics_detect_each_cross_tenant_relationship(
    relationship: tuple[str, str, str, str, str],
) -> None:
    child, constraint_name, parent, parent_column, ondelete = relationship
    migration = import_module("migrations.versions.20260801_0029_ti_c1_orchestration_integrity")
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
    migration = import_module("migrations.versions.20260801_0029_ti_c1_orchestration_integrity")
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


def test_nullable_orchestration_references_remain_nullable() -> None:
    for table_name, column_name in (
        ("intelligence_orchestration_requests", "dataset_version_id"),
        ("reliability_executions", "orchestration_request_id"),
        ("statistical_executions", "orchestration_request_id"),
        ("forecast_executions", "orchestration_request_id"),
    ):
        assert Base.metadata.tables[table_name].c[column_name].nullable is True


def test_sqlite_migration_round_trip_restores_ti_c1_objects(tmp_path: Path) -> None:
    database_path = tmp_path / "ti-c1-lifecycle.sqlite"
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
        assert REUSED_INDEXES <= index_names

        command.downgrade(config, "20260801_0028")
        unique_names, foreign_key_names, index_names = object_names()
        assert set(PARENT_CONSTRAINTS.values()).isdisjoint(unique_names)
        assert TENANT_FOREIGN_KEYS.isdisjoint(foreign_key_names)
        assert NEW_INDEXES.isdisjoint(index_names)
        assert REUSED_INDEXES <= index_names

        command.upgrade(config, "head")
        unique_names, foreign_key_names, index_names = object_names()
        assert set(PARENT_CONSTRAINTS.values()) <= unique_names
        assert TENANT_FOREIGN_KEYS <= foreign_key_names
        assert NEW_INDEXES <= index_names
    finally:
        engine.dispose()
