from importlib import import_module
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import (
    ForeignKeyConstraint,
    UniqueConstraint,
    create_engine,
    event,
    inspect,
    select,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, configure_mappers

import app.models  # noqa: F401
from app.db.session import Base
from app.models.actions import ActionDependency, ActionPlanStep, OperationalAction
from app.models.entities import Organization

PARENT_CONSTRAINTS = {
    "operational_actions": "uq_operational_actions_org_id",
}

RELATIONSHIPS = (
    (
        "action_plan_steps",
        "fk_action_plan_steps_org_action",
        "operational_actions",
        "action_id",
        "CASCADE",
    ),
    (
        "action_dependencies",
        "fk_action_dependencies_org_action",
        "operational_actions",
        "action_id",
        "CASCADE",
    ),
    (
        "action_dependencies",
        "fk_action_dependencies_org_prerequisite",
        "operational_actions",
        "prerequisite_action_id",
        "RESTRICT",
    ),
    (
        "action_resource_requirements",
        "fk_action_resource_requirements_org_action",
        "operational_actions",
        "action_id",
        "CASCADE",
    ),
    (
        "action_events",
        "fk_action_events_org_action",
        "operational_actions",
        "action_id",
        "CASCADE",
    ),
    (
        "action_evidence",
        "fk_action_evidence_org_action",
        "operational_actions",
        "action_id",
        "CASCADE",
    ),
    (
        "action_outcomes",
        "fk_action_outcomes_org_action",
        "operational_actions",
        "action_id",
        "CASCADE",
    ),
    (
        "action_model_feedback",
        "fk_action_model_feedback_org_action",
        "operational_actions",
        "action_id",
        "CASCADE",
    ),
    (
        "action_model_feedback",
        "fk_action_model_feedback_org_reliability_execution",
        "reliability_executions",
        "reliability_execution_id",
        "RESTRICT",
    ),
    (
        "operational_actions",
        "fk_operational_actions_org_reliability_execution",
        "reliability_executions",
        "reliability_execution_id",
        "RESTRICT",
    ),
    (
        "operational_actions",
        "fk_operational_actions_org_forecast_execution",
        "forecast_executions",
        "forecast_execution_id",
        "RESTRICT",
    ),
    (
        "operational_actions",
        "fk_operational_actions_org_orchestration_request",
        "intelligence_orchestration_requests",
        "orchestration_request_id",
        "RESTRICT",
    ),
)

TENANT_FOREIGN_KEYS = {item[1] for item in RELATIONSHIPS}

NEW_INDEXES = {
    "ix_action_dependency_org_prerequisite",
    "ix_action_feedback_org_reliability_execution",
    "ix_action_org_reliability_execution",
    "ix_action_org_forecast_execution",
    "ix_action_org_orchestration_request",
}

REUSED_INDEXES = {
    "ix_action_plan_step_org_action",
    "ix_action_dependency_org_action",
    "ix_action_resource_org_action",
    "ix_action_event_org_action",
    "ix_action_evidence_org_action",
    "ix_action_outcome_org_action",
    "ix_action_feedback_org_action",
}

IN_SCOPE_TABLES = {
    "operational_actions",
    "action_plan_steps",
    "action_dependencies",
    "action_resource_requirements",
    "action_events",
    "action_evidence",
    "action_outcomes",
    "action_model_feedback",
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

    assert unique_counts["uq_operational_actions_org_id"] == 1
    assert unique_counts["uq_action_idempotency"] == 1
    assert all(foreign_key_counts[name] == 1 for name in TENANT_FOREIGN_KEYS)
    assert all(index_counts[name] == 1 for name in NEW_INDEXES | REUSED_INDEXES)
    assert sum(item[4] == "CASCADE" for item in RELATIONSHIPS) == 7
    assert sum(item[4] == "RESTRICT" for item in RELATIONSHIPS) == 5

    for child, name, parent, parent_column, ondelete in RELATIONSHIPS:
        matches = [
            constraint
            for constraint in Base.metadata.tables[child].foreign_key_constraints
            if constraint.name == name
        ]
        assert len(matches) == 1
        constraint = matches[0]
        assert [column.name for column in constraint.columns] == [
            "organization_id",
            parent_column,
        ]
        assert [element.target_fullname for element in constraint.elements] == [
            f"{parent}.organization_id",
            f"{parent}.id",
        ]
        assert constraint.ondelete == ondelete


def test_single_column_foreign_keys_and_index_shapes_are_preserved() -> None:
    index_shapes: set[tuple[str, tuple[str, ...]]] = set()
    for table_name in IN_SCOPE_TABLES:
        table = Base.metadata.tables[table_name]
        for index in table.indexes:
            shape = (table_name, tuple(column.name for column in index.columns))
            assert shape not in index_shapes
            index_shapes.add(shape)

    for child, _, parent, parent_column, ondelete in RELATIONSHIPS:
        table = Base.metadata.tables[child]
        matches = [
            constraint
            for constraint in table.foreign_key_constraints
            if len(constraint.columns) == 1
            and tuple(constraint.columns)[0].name == parent_column
            and next(iter(constraint.elements)).column.table.name == parent
        ]
        assert len(matches) == 1
        assert matches[0].ondelete == ondelete

    action_mapper = inspect(OperationalAction).relationships
    assert len(action_mapper) == 0
    for table_name in IN_SCOPE_TABLES:
        model = next(
            mapper.class_
            for mapper in Base.registry.mappers
            if mapper.local_table.description == table_name
        )
        assert len(inspect(model).relationships) == 0


def _constraint_engine(
    relationship: tuple[str, str, str, str, str],
) -> tuple[Engine, str, str]:
    _, constraint_name, _, parent_column, ondelete = relationship
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection: object, _: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE parent_rows ("
                "id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, "
                "CONSTRAINT uq_parent_org_id UNIQUE (organization_id, id))"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE child_rows ("
                "id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, "
                f"{parent_column} TEXT, "
                f"CONSTRAINT {constraint_name} "
                f"FOREIGN KEY (organization_id, {parent_column}) "
                "REFERENCES parent_rows (organization_id, id) "
                f"ON DELETE {ondelete})"
            )
        )
    return engine, parent_column, ondelete


@pytest.mark.parametrize("relationship", RELATIONSHIPS, ids=lambda item: item[1])
def test_real_sql_enforces_same_tenant_insert_and_cross_tenant_write(
    relationship: tuple[str, str, str, str, str],
) -> None:
    engine, parent_column, _ = _constraint_engine(relationship)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO parent_rows (id, organization_id) "
                "VALUES ('parent-a', 'tenant-a'), ('parent-b', 'tenant-b')"
            )
        )
        connection.execute(
            text(
                f"INSERT INTO child_rows (id, organization_id, {parent_column}) "
                "VALUES ('valid', 'tenant-a', 'parent-a')"
            )
        )

    with engine.connect() as connection:
        transaction = connection.begin()
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    f"INSERT INTO child_rows (id, organization_id, {parent_column}) "
                    "VALUES ('invalid', 'tenant-b', 'parent-a')"
                )
            )
        transaction.rollback()
        assert connection.scalar(text("SELECT count(*) FROM child_rows WHERE id = 'invalid'")) == 0
        connection.rollback()

        transaction = connection.begin()
        with pytest.raises(IntegrityError):
            connection.execute(
                text("UPDATE child_rows SET organization_id = 'tenant-b' WHERE id = 'valid'")
            )
        transaction.rollback()
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM child_rows "
                    "WHERE id = 'valid' AND organization_id = 'tenant-a'"
                )
            )
            == 1
        )
    engine.dispose()


@pytest.mark.parametrize("relationship", RELATIONSHIPS, ids=lambda item: item[1])
def test_real_sql_delete_behavior_matches_contract(
    relationship: tuple[str, str, str, str, str],
) -> None:
    engine, parent_column, ondelete = _constraint_engine(relationship)
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO parent_rows (id, organization_id) VALUES ('parent-a', 'tenant-a')")
        )
        connection.execute(
            text(
                f"INSERT INTO child_rows (id, organization_id, {parent_column}) "
                "VALUES ('child-a', 'tenant-a', 'parent-a')"
            )
        )

    if ondelete == "CASCADE":
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM parent_rows WHERE id = 'parent-a'"))
            assert connection.scalar(text("SELECT count(*) FROM child_rows")) == 0
    else:
        with engine.connect() as connection:
            transaction = connection.begin()
            with pytest.raises(IntegrityError):
                connection.execute(text("DELETE FROM parent_rows WHERE id = 'parent-a'"))
            transaction.rollback()
            assert connection.scalar(text("SELECT count(*) FROM child_rows")) == 1
    engine.dispose()


def _organization(slug: str) -> Organization:
    return Organization(
        name=slug,
        slug=slug,
        country_code="US",
        default_currency="USD",
        timezone="UTC",
        status="active",
    )


def _action(organization_id: UUID, suffix: str) -> OperationalAction:
    return OperationalAction(
        organization_id=organization_id,
        source_type="manual",
        source_reference=f"source-{suffix}",
        recommendation_type="inspection",
        recommendation_rule_version="1.0.0",
        title=f"Action {suffix}",
        description="Tenant integrity action.",
        rationale="TI-C2 certification.",
        priority="medium",
        priority_score=50,
        priority_components={},
        status="proposed",
        approval_required=False,
        approval_level="none",
        approval_role="operator",
        approval_status="not_required",
        idempotency_fingerprint=uuid4().hex * 2,
        created_by_user_id=uuid4(),
    )


def test_orm_mapped_attributes_enforce_action_tenant_and_rollback_cleanly(db: Session) -> None:
    first_org = _organization(f"ti-c2-first-{uuid4().hex[:8]}")
    second_org = _organization(f"ti-c2-second-{uuid4().hex[:8]}")
    db.add_all([first_org, second_org])
    db.flush()
    first_action = _action(first_org.id, "first")
    second_action = _action(second_org.id, "second")
    db.add_all([first_action, second_action])
    db.commit()

    valid = ActionPlanStep(
        organization_id=first_org.id,
        action_id=first_action.id,
        sequence_number=1,
        title="Valid",
        description="Same tenant.",
    )
    db.add(valid)
    db.commit()
    assert db.scalar(select(ActionPlanStep).where(ActionPlanStep.id == valid.id)) is not None

    invalid = ActionPlanStep(
        organization_id=second_org.id,
        action_id=first_action.id,
        sequence_number=2,
        title="Invalid",
        description="Cross tenant.",
    )
    db.add(invalid)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    assert db.scalar(select(ActionPlanStep).where(ActionPlanStep.id == invalid.id)) is None


def test_dual_action_references_must_share_the_dependency_tenant(db: Session) -> None:
    first_org = _organization(f"ti-c2-dep-first-{uuid4().hex[:8]}")
    second_org = _organization(f"ti-c2-dep-second-{uuid4().hex[:8]}")
    db.add_all([first_org, second_org])
    db.flush()
    action = _action(first_org.id, "dependent")
    prerequisite = _action(first_org.id, "prerequisite")
    foreign_prerequisite = _action(second_org.id, "foreign")
    db.add_all([action, prerequisite, foreign_prerequisite])
    db.commit()

    valid = ActionDependency(
        organization_id=first_org.id,
        action_id=action.id,
        prerequisite_action_id=prerequisite.id,
        dependency_type="finish_to_start",
    )
    db.add(valid)
    db.commit()

    invalid = ActionDependency(
        organization_id=first_org.id,
        action_id=action.id,
        prerequisite_action_id=foreign_prerequisite.id,
        dependency_type="finish_to_start",
    )
    db.add(invalid)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    assert db.scalar(select(ActionDependency).where(ActionDependency.id == invalid.id)) is None


def test_nullable_execution_and_orchestration_references_remain_valid(db: Session) -> None:
    organization = _organization(f"ti-c2-null-{uuid4().hex[:8]}")
    db.add(organization)
    db.flush()
    action = _action(organization.id, "nullable")
    db.add(action)
    db.commit()
    assert action.reliability_execution_id is None
    assert action.forecast_execution_id is None
    assert action.orchestration_request_id is None


@pytest.mark.parametrize("relationship", RELATIONSHIPS, ids=lambda item: item[1])
def test_diagnostics_detect_each_cross_tenant_relationship(
    relationship: tuple[str, str, str, str, str],
) -> None:
    child, constraint_name, parent, parent_column, ondelete = relationship
    migration = import_module("migrations.versions.20260802_0030_ti_c2_action_workflow_integrity")
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
            pytest.raises(RuntimeError, match=f"{constraint_name}.*1 tenant violations"),
        ):
            migration._assert_clean_tenant_references()


@pytest.mark.parametrize("violation", ("orphan", "missing_tenant", "duplicate_parent"))
def test_diagnostics_detect_orphans_missing_tenants_and_duplicate_targets(
    violation: str,
) -> None:
    migration = import_module("migrations.versions.20260802_0030_ti_c2_action_workflow_integrity")
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
            expected = "fk_children_org_parent.*1 tenant violations"

        with (
            patch.object(migration, "COMPOSITE_FOREIGN_KEYS", foreign_keys),
            patch.object(migration, "PARENT_UNIQUES", parents),
            patch.object(migration.op, "get_bind", return_value=connection),
            pytest.raises(RuntimeError, match=expected),
        ):
            migration._assert_clean_tenant_references()


def test_sqlite_migration_round_trip_restores_ti_c2_objects(tmp_path: Path) -> None:
    database_path = tmp_path / "ti-c2-lifecycle.sqlite"
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

        command.downgrade(config, "20260801_0029")
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
        assert REUSED_INDEXES <= index_names
    finally:
        engine.dispose()
