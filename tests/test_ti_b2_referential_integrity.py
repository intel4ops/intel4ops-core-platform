from importlib import import_module
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import (
    ForeignKeyConstraint,
    Index,
    Table,
    UniqueConstraint,
    create_engine,
    delete,
    insert,
    inspect,
    select,
    text,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, configure_mappers
from test_reliability_service import (
    reliability_foundation,
    reliability_payload,
)
from test_statistical_service import (
    execution_payload,
    statistical_foundation,
)

import app.models  # noqa: F401
from app.db.session import Base
from app.models.reliability import (
    ReliabilityExecution,
    ReliabilityMetric,
    ReliabilityModelResult,
    ReliabilityReviewFeedback,
)
from app.models.statistics import (
    AnomalyReviewFeedback,
    StatisticalBaseline,
    StatisticalExecution,
    StatisticalObservation,
)
from app.services.reliability_service import reliability_execution_service
from app.services.statistical_service import statistical_execution_service

PARENT_CONSTRAINTS = {
    "reliability_executions": "uq_reliability_executions_org_id",
    "statistical_executions": "uq_statistical_executions_org_id",
    "statistical_observations": "uq_statistical_observations_org_id",
}

TENANT_FOREIGN_KEYS = {
    "fk_reliability_executions_org_dataset",
    "fk_reliability_executions_org_dataset_version",
    "fk_reliability_executions_org_ingestion_batch",
    "fk_reliability_executions_org_source_system",
    "fk_reliability_executions_org_trust_assessment",
    "fk_reliability_executions_org_readiness",
    "fk_reliability_metrics_org_execution",
    "fk_reliability_model_results_org_execution",
    "fk_reliability_review_feedback_org_execution",
    "fk_statistical_executions_org_dataset",
    "fk_statistical_executions_org_dataset_version",
    "fk_statistical_executions_org_ingestion_batch",
    "fk_statistical_executions_org_source_system",
    "fk_statistical_executions_org_trust_assessment",
    "fk_statistical_executions_org_readiness",
    "fk_statistical_baselines_org_execution",
    "fk_statistical_observations_org_execution",
    "fk_anomaly_review_feedback_org_observation",
}

NEW_INDEXES = {
    "ix_reliability_execution_org_dataset",
    "ix_reliability_execution_org_dataset_version",
    "ix_reliability_execution_org_ingestion_batch",
    "ix_reliability_execution_org_source_system",
    "ix_reliability_execution_org_trust_assessment",
    "ix_reliability_execution_org_readiness",
    "ix_reliability_model_result_org_execution",
    "ix_statistical_execution_org_dataset",
    "ix_statistical_execution_org_dataset_version",
    "ix_statistical_execution_org_ingestion_batch",
    "ix_statistical_execution_org_source_system",
    "ix_statistical_execution_org_trust_assessment",
    "ix_statistical_execution_org_readiness",
}

REUSED_INDEXES = {
    "ix_reliability_metric_org_execution",
    "ix_reliability_review_org_execution",
    "ix_statistical_baseline_org_execution",
    "ix_statistical_observation_org_execution",
    "ix_anomaly_review_org_observation",
}

IN_SCOPE_TABLES = {
    "reliability_executions",
    "reliability_metrics",
    "reliability_model_results",
    "reliability_review_feedback",
    "statistical_executions",
    "statistical_baselines",
    "statistical_observations",
    "anomaly_review_feedback",
}

RELATIONSHIPS = (
    (
        "reliability_executions",
        "fk_reliability_executions_org_dataset",
        "datasets",
        "dataset_id",
        "RESTRICT",
    ),
    (
        "reliability_executions",
        "fk_reliability_executions_org_dataset_version",
        "dataset_versions",
        "dataset_version_id",
        "RESTRICT",
    ),
    (
        "reliability_executions",
        "fk_reliability_executions_org_ingestion_batch",
        "ingestion_batches",
        "ingestion_batch_id",
        "RESTRICT",
    ),
    (
        "reliability_executions",
        "fk_reliability_executions_org_source_system",
        "source_systems",
        "source_system_id",
        "RESTRICT",
    ),
    (
        "reliability_executions",
        "fk_reliability_executions_org_trust_assessment",
        "trust_assessments",
        "trust_assessment_id",
        "RESTRICT",
    ),
    (
        "reliability_executions",
        "fk_reliability_executions_org_readiness",
        "analytical_readiness_decisions",
        "readiness_assessment_id",
        "RESTRICT",
    ),
    (
        "reliability_metrics",
        "fk_reliability_metrics_org_execution",
        "reliability_executions",
        "reliability_execution_id",
        "CASCADE",
    ),
    (
        "reliability_model_results",
        "fk_reliability_model_results_org_execution",
        "reliability_executions",
        "reliability_execution_id",
        "CASCADE",
    ),
    (
        "reliability_review_feedback",
        "fk_reliability_review_feedback_org_execution",
        "reliability_executions",
        "reliability_execution_id",
        "CASCADE",
    ),
    (
        "statistical_executions",
        "fk_statistical_executions_org_dataset",
        "datasets",
        "dataset_id",
        "RESTRICT",
    ),
    (
        "statistical_executions",
        "fk_statistical_executions_org_dataset_version",
        "dataset_versions",
        "dataset_version_id",
        "RESTRICT",
    ),
    (
        "statistical_executions",
        "fk_statistical_executions_org_ingestion_batch",
        "ingestion_batches",
        "ingestion_batch_id",
        "RESTRICT",
    ),
    (
        "statistical_executions",
        "fk_statistical_executions_org_source_system",
        "source_systems",
        "source_system_id",
        "RESTRICT",
    ),
    (
        "statistical_executions",
        "fk_statistical_executions_org_trust_assessment",
        "trust_assessments",
        "trust_assessment_id",
        "RESTRICT",
    ),
    (
        "statistical_executions",
        "fk_statistical_executions_org_readiness",
        "analytical_readiness_decisions",
        "readiness_assessment_id",
        "RESTRICT",
    ),
    (
        "statistical_baselines",
        "fk_statistical_baselines_org_execution",
        "statistical_executions",
        "statistical_execution_id",
        "CASCADE",
    ),
    (
        "statistical_observations",
        "fk_statistical_observations_org_execution",
        "statistical_executions",
        "statistical_execution_id",
        "CASCADE",
    ),
    (
        "anomaly_review_feedback",
        "fk_anomaly_review_feedback_org_observation",
        "statistical_observations",
        "statistical_observation_id",
        "CASCADE",
    ),
)


def test_metadata_mappers_and_indexes_define_exact_ti_b2_contract() -> None:
    configure_mappers()
    unique_names: list[str] = []
    foreign_key_names: list[str] = []
    index_names: list[str] = []

    for table_name in IN_SCOPE_TABLES:
        table = Base.metadata.tables[table_name]
        unique_names.extend(
            str(item.name)
            for item in table.constraints
            if isinstance(item, UniqueConstraint) and item.name in PARENT_CONSTRAINTS.values()
        )
        foreign_key_names.extend(
            str(item.name)
            for item in table.constraints
            if isinstance(item, ForeignKeyConstraint) and item.name in TENANT_FOREIGN_KEYS
        )
        index_names.extend(str(item.name) for item in table.indexes if item.name in NEW_INDEXES)

        column_sets = [
            tuple(column.name for column in item.columns)
            for item in table.indexes
            if isinstance(item, Index)
        ]
        assert len(column_sets) == len(set(column_sets))

    assert set(unique_names) == set(PARENT_CONSTRAINTS.values())
    assert len(unique_names) == 3
    assert set(foreign_key_names) == TENANT_FOREIGN_KEYS
    assert len(foreign_key_names) == 18
    assert set(index_names) == NEW_INDEXES
    assert len(index_names) == 13

    reused = [
        str(index.name)
        for table_name in IN_SCOPE_TABLES
        for index in Base.metadata.tables[table_name].indexes
        if index.name in REUSED_INDEXES
    ]
    assert set(reused) == REUSED_INDEXES
    assert len(reused) == 5

    for table_name, constraint_name in PARENT_CONSTRAINTS.items():
        matches = [
            item
            for item in Base.metadata.tables[table_name].constraints
            if isinstance(item, UniqueConstraint) and item.name == constraint_name
        ]
        assert len(matches) == 1
        assert [column.name for column in matches[0].columns] == ["organization_id", "id"]

    for child, name, parent, parent_column, ondelete in RELATIONSHIPS:
        fk_matches: list[ForeignKeyConstraint] = [
            item
            for item in Base.metadata.tables[child].constraints
            if isinstance(item, ForeignKeyConstraint) and item.name == name
        ]
        assert len(fk_matches) == 1
        constraint = fk_matches[0]
        assert [column.name for column in constraint.columns] == [
            "organization_id",
            parent_column,
        ]
        assert [element.target_fullname for element in constraint.elements] == [
            f"{parent}.organization_id",
            f"{parent}.id",
        ]
        assert constraint.ondelete == ondelete
        single_targets = {
            foreign_key.target_fullname
            for foreign_key in Base.metadata.tables[child].c[parent_column].foreign_keys
        }
        assert f"{parent}.id" in single_targets

    for table_name in ("reliability_executions", "statistical_executions"):
        table = Base.metadata.tables[table_name]
        composite_columns = {
            tuple(column.name for column in item.columns)
            for item in table.constraints
            if isinstance(item, ForeignKeyConstraint) and len(item.columns) == 2
        }
        assert ("organization_id", "oikb_definition_id") not in composite_columns
        assert ("organization_id", "oikb_definition_version_id") not in composite_columns
        assert ("organization_id", "orchestration_request_id") not in composite_columns
    suppression = Base.metadata.tables["anomaly_suppression_records"]
    assert not any(
        isinstance(item, ForeignKeyConstraint)
        and len(item.columns) == 2
        and "definition_version_id" in item.columns
        for item in suppression.constraints
    )


@pytest.mark.parametrize("relationship", RELATIONSHIPS, ids=lambda item: item[1])
def test_diagnostics_detect_each_cross_tenant_relationship(
    relationship: tuple[str, str, str, str, str],
) -> None:
    child, constraint_name, parent, parent_column, ondelete = relationship
    migration = import_module(
        "migrations.versions.20260801_0027_ti_b2_reliability_statistical_integrity"
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(f"CREATE TABLE {parent} (id TEXT PRIMARY KEY, organization_id TEXT NOT NULL)")
        )
        connection.execute(
            text(
                f"CREATE TABLE {child} "
                f"(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, "
                f"{parent_column} TEXT)"
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
        "migrations.versions.20260801_0027_ti_b2_reliability_statistical_integrity"
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE parents (id TEXT, organization_id TEXT)"))
        connection.execute(
            text(
                "CREATE TABLE children (id TEXT PRIMARY KEY, organization_id TEXT, parent_id TEXT)"
            )
        )
        parents: tuple[tuple[str, str], ...]
        if violation == "duplicate_parent":
            connection.execute(
                text(
                    "INSERT INTO parents (id, organization_id) "
                    "VALUES ('parent-1', 'tenant-a'), ('parent-1', 'tenant-a')"
                )
            )
            foreign_keys: tuple[tuple[str, str, str, str, str], ...] = ()
            parents = (("parents", "uq_parents_org_id"),)
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
                (
                    "children",
                    "fk_children_org_parent",
                    "parents",
                    "parent_id",
                    "RESTRICT",
                ),
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

        if violation != "duplicate_parent":
            assert (
                connection.scalar(text("SELECT count(*) FROM children WHERE id = 'child-1'")) == 1
            )


def _reliability_graph(db: Session, slug: str) -> dict[str, UUID]:
    organization_id, trust_id, readiness_id, actor = reliability_foundation(db, slug)
    execution = reliability_execution_service.execute(
        db,
        organization_id,
        reliability_payload(
            trust_id,
            readiness_id,
            method_code="WEIBULL_TWO_PARAMETER",
            dataset_fingerprint=uuid4().hex * 2,
        ),
        actor,
    )
    metric_id = db.scalar(
        select(ReliabilityMetric.id).where(
            ReliabilityMetric.reliability_execution_id == execution.id
        )
    )
    model_id = db.scalar(
        select(ReliabilityModelResult.id).where(
            ReliabilityModelResult.reliability_execution_id == execution.id
        )
    )
    assert metric_id is not None
    assert model_id is not None
    review = ReliabilityReviewFeedback(
        organization_id=organization_id,
        reliability_execution_id=execution.id,
        assessment_type="human_review",
        assessment_reference=f"review:{execution.id}",
        review_status="confirmed",
        reviewer_id=actor,
        was_actionable=True,
        was_false_positive=False,
        notes="TI-B2 test",
    )
    db.add(review)
    db.commit()
    return {
        "organization": organization_id,
        "execution": execution.id,
        "dataset": cast(UUID, execution.dataset_id),
        "dataset_version": cast(UUID, execution.dataset_version_id),
        "ingestion_batch": cast(UUID, execution.ingestion_batch_id),
        "source_system": cast(UUID, execution.source_system_id),
        "trust_assessment": trust_id,
        "readiness": readiness_id,
        "metric": metric_id,
        "model_result": model_id,
        "review": review.id,
    }


def _statistical_graph(db: Session, slug: str) -> dict[str, UUID]:
    organization_id, _, trust_id, readiness_id, actor = statistical_foundation(db, slug)
    execution = statistical_execution_service.execute(
        db,
        organization_id,
        execution_payload(trust_id, readiness_id, key=f"ti-b2-{uuid4().hex}"),
        actor,
    )
    baseline_id = db.scalar(
        select(StatisticalBaseline.id).where(
            StatisticalBaseline.statistical_execution_id == execution.id
        )
    )
    observation_id = db.scalar(
        select(StatisticalObservation.id).where(
            StatisticalObservation.statistical_execution_id == execution.id
        )
    )
    assert baseline_id is not None
    assert observation_id is not None
    review = AnomalyReviewFeedback(
        organization_id=organization_id,
        statistical_observation_id=observation_id,
        review_status="confirmed",
        reviewer_id=actor,
        classification="true_positive",
        was_actionable=True,
        was_false_positive=False,
        notes="TI-B2 test",
    )
    db.add(review)
    db.commit()
    return {
        "organization": organization_id,
        "execution": execution.id,
        "dataset": cast(UUID, execution.dataset_id),
        "dataset_version": cast(UUID, execution.dataset_version_id),
        "ingestion_batch": cast(UUID, execution.ingestion_batch_id),
        "source_system": cast(UUID, execution.source_system_id),
        "trust_assessment": trust_id,
        "readiness": readiness_id,
        "baseline": baseline_id,
        "observation": observation_id,
        "review": review.id,
    }


def _clone_values(db: Session, table: Table, row_id: UUID) -> dict[str, Any]:
    values = dict(db.execute(select(table).where(table.c.id == row_id)).mappings().one())
    values["id"] = uuid4()
    if table.name == "reliability_executions":
        values["reproducibility_fingerprint"] = uuid4().hex * 2
        values["execution_package_fingerprint"] = uuid4().hex * 2
        values["correlation_id"] = f"ti-b2-{uuid4().hex}"
    elif table.name == "statistical_executions":
        values["reproducibility_fingerprint"] = uuid4().hex * 2
        values["execution_package_fingerprint"] = uuid4().hex * 2
        values["idempotency_key"] = f"ti-b2-{uuid4().hex}"
        values["correlation_id"] = f"ti-b2-{uuid4().hex}"
    elif table.name == "anomaly_review_feedback":
        values["reviewer_id"] = uuid4()
    return values


def _relationship_cases(
    reliability: dict[str, UUID],
    statistics: dict[str, UUID],
) -> tuple[tuple[Table, UUID, str, UUID], ...]:
    return (
        (
            cast(Table, ReliabilityExecution.__table__),
            reliability["execution"],
            "dataset_id",
            reliability["dataset"],
        ),
        (
            cast(Table, ReliabilityExecution.__table__),
            reliability["execution"],
            "dataset_version_id",
            reliability["dataset_version"],
        ),
        (
            cast(Table, ReliabilityExecution.__table__),
            reliability["execution"],
            "ingestion_batch_id",
            reliability["ingestion_batch"],
        ),
        (
            cast(Table, ReliabilityExecution.__table__),
            reliability["execution"],
            "source_system_id",
            reliability["source_system"],
        ),
        (
            cast(Table, ReliabilityExecution.__table__),
            reliability["execution"],
            "trust_assessment_id",
            reliability["trust_assessment"],
        ),
        (
            cast(Table, ReliabilityExecution.__table__),
            reliability["execution"],
            "readiness_assessment_id",
            reliability["readiness"],
        ),
        (
            cast(Table, ReliabilityMetric.__table__),
            reliability["metric"],
            "reliability_execution_id",
            reliability["execution"],
        ),
        (
            cast(Table, ReliabilityModelResult.__table__),
            reliability["model_result"],
            "reliability_execution_id",
            reliability["execution"],
        ),
        (
            cast(Table, ReliabilityReviewFeedback.__table__),
            reliability["review"],
            "reliability_execution_id",
            reliability["execution"],
        ),
        (
            cast(Table, StatisticalExecution.__table__),
            statistics["execution"],
            "dataset_id",
            statistics["dataset"],
        ),
        (
            cast(Table, StatisticalExecution.__table__),
            statistics["execution"],
            "dataset_version_id",
            statistics["dataset_version"],
        ),
        (
            cast(Table, StatisticalExecution.__table__),
            statistics["execution"],
            "ingestion_batch_id",
            statistics["ingestion_batch"],
        ),
        (
            cast(Table, StatisticalExecution.__table__),
            statistics["execution"],
            "source_system_id",
            statistics["source_system"],
        ),
        (
            cast(Table, StatisticalExecution.__table__),
            statistics["execution"],
            "trust_assessment_id",
            statistics["trust_assessment"],
        ),
        (
            cast(Table, StatisticalExecution.__table__),
            statistics["execution"],
            "readiness_assessment_id",
            statistics["readiness"],
        ),
        (
            cast(Table, StatisticalBaseline.__table__),
            statistics["baseline"],
            "statistical_execution_id",
            statistics["execution"],
        ),
        (
            cast(Table, StatisticalObservation.__table__),
            statistics["observation"],
            "statistical_execution_id",
            statistics["execution"],
        ),
        (
            cast(Table, AnomalyReviewFeedback.__table__),
            statistics["review"],
            "statistical_observation_id",
            statistics["observation"],
        ),
    )


def test_direct_sql_allows_same_tenant_and_rejects_cross_tenant_rows(
    db: Session,
) -> None:
    first_reliability = _reliability_graph(db, f"ti-b2-rel-first-{uuid4().hex[:8]}")
    second_reliability = _reliability_graph(db, f"ti-b2-rel-second-{uuid4().hex[:8]}")
    first_statistics = _statistical_graph(db, f"ti-b2-stat-first-{uuid4().hex[:8]}")
    second_statistics = _statistical_graph(db, f"ti-b2-stat-second-{uuid4().hex[:8]}")
    first_cases = _relationship_cases(first_reliability, first_statistics)
    second_cases = _relationship_cases(second_reliability, second_statistics)

    for (table, row_id, parent_column, same_parent), (_, _, _, wrong_parent) in zip(
        first_cases, second_cases, strict=True
    ):
        same_values = _clone_values(db, table, row_id)
        same_values[parent_column] = same_parent
        same_id = cast(UUID, same_values["id"])
        db.execute(insert(table).values(**same_values))
        db.commit()
        assert db.scalar(select(table.c.id).where(table.c.id == same_id)) == same_id
        db.execute(delete(table).where(table.c.id == same_id))
        db.commit()

        cross_values = _clone_values(db, table, row_id)
        cross_values[parent_column] = wrong_parent
        cross_id = cast(UUID, cross_values["id"])
        with pytest.raises(IntegrityError):
            db.execute(insert(table).values(**cross_values))
            db.commit()
        db.rollback()
        assert db.scalar(select(table.c.id).where(table.c.id == cross_id)) is None

        with pytest.raises(IntegrityError):
            db.execute(
                update(table).where(table.c.id == row_id).values({parent_column: wrong_parent})
            )
            db.commit()
        db.rollback()
        assert db.scalar(select(table.c.id).where(table.c.id == row_id)) == row_id


def test_orm_rejects_cross_tenant_rows_and_rolls_back_cleanly(db: Session) -> None:
    first_reliability = _reliability_graph(db, f"ti-b2-rel-orm-first-{uuid4().hex[:8]}")
    second_reliability = _reliability_graph(db, f"ti-b2-rel-orm-second-{uuid4().hex[:8]}")
    first_statistics = _statistical_graph(db, f"ti-b2-stat-orm-first-{uuid4().hex[:8]}")
    second_statistics = _statistical_graph(db, f"ti-b2-stat-orm-second-{uuid4().hex[:8]}")
    first_cases = _relationship_cases(first_reliability, first_statistics)
    second_cases = _relationship_cases(second_reliability, second_statistics)
    model_by_table = {
        "reliability_executions": ReliabilityExecution,
        "reliability_metrics": ReliabilityMetric,
        "reliability_model_results": ReliabilityModelResult,
        "reliability_review_feedback": ReliabilityReviewFeedback,
        "statistical_executions": StatisticalExecution,
        "statistical_baselines": StatisticalBaseline,
        "statistical_observations": StatisticalObservation,
        "anomaly_review_feedback": AnomalyReviewFeedback,
    }

    for (table, row_id, parent_column, _), (_, _, _, wrong_parent) in zip(
        first_cases, second_cases, strict=True
    ):
        values = _clone_values(db, table, row_id)
        values[parent_column] = wrong_parent
        row_id = cast(UUID, values["id"])
        model: Any = model_by_table[table.name]
        db.add(model(**values))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        assert db.scalar(select(model.id).where(model.id == row_id)) is None


def test_orm_collections_nullable_provenance_and_cascades(db: Session) -> None:
    reliability = _reliability_graph(db, f"ti-b2-rel-orm-{uuid4().hex[:8]}")
    statistics = _statistical_graph(db, f"ti-b2-stat-orm-{uuid4().hex[:8]}")
    reliability_execution = db.get(ReliabilityExecution, reliability["execution"])
    statistical_execution = db.get(StatisticalExecution, statistics["execution"])
    assert reliability_execution is not None
    assert statistical_execution is not None
    assert reliability_execution.metrics
    assert reliability_execution.models
    assert statistical_execution.baselines
    assert statistical_execution.observations

    for execution in (reliability_execution, statistical_execution):
        execution.dataset_id = None
        execution.dataset_version_id = None
        execution.ingestion_batch_id = None
        execution.source_system_id = None
    db.commit()

    reliability_children = (
        (ReliabilityMetric, reliability["metric"]),
        (ReliabilityModelResult, reliability["model_result"]),
        (ReliabilityReviewFeedback, reliability["review"]),
    )
    statistical_children = (
        (StatisticalBaseline, statistics["baseline"]),
        (StatisticalObservation, statistics["observation"]),
        (AnomalyReviewFeedback, statistics["review"]),
    )
    db.execute(
        delete(ReliabilityExecution).where(ReliabilityExecution.id == reliability["execution"])
    )
    db.execute(
        delete(StatisticalExecution).where(StatisticalExecution.id == statistics["execution"])
    )
    db.commit()
    db.expire_all()
    for model, row_id in reliability_children + statistical_children:
        assert db.scalar(select(model.id).where(model.id == row_id)) is None


def test_sqlite_migration_round_trip_restores_ti_b2_objects(tmp_path: Path) -> None:
    database_path = tmp_path / "ti-b2-lifecycle.sqlite"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    engine = create_engine(database_url)

    def object_names() -> tuple[set[str], set[str], set[str]]:
        inspector = inspect(engine)
        return (
            {
                str(item["name"])
                for table_name in PARENT_CONSTRAINTS
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

        command.downgrade(config, "20260731_0026")
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
