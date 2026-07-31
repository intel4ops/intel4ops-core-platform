from importlib import import_module
from pathlib import Path
from typing import cast
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
    insert,
    inspect,
    select,
    text,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, configure_mappers
from test_trust_service import trust_foundation

import app.models  # noqa: F401
from app.db.session import Base
from app.models.trust import (
    AnalyticalReadinessDecision,
    TrustAssessment,
    TrustEvidence,
    TrustRuleResult,
)

PARENT_CONSTRAINTS = {
    "trust_assessments": "uq_trust_assessments_org_id",
    "trust_rule_results": "uq_trust_rule_results_org_id",
    "analytical_readiness_decisions": "uq_analytical_readiness_decisions_org_id",
}

TENANT_FOREIGN_KEYS = {
    "fk_trust_assessments_org_dataset",
    "fk_trust_assessments_org_ingestion_batch",
    "fk_trust_rule_results_org_trust_assessment",
    "fk_trust_evidence_org_rule_result",
    "fk_trust_evidence_org_dataset",
    "fk_readiness_org_trust_assessment",
}

TENANT_INDEXES = {
    "ix_trust_assessments_org_dataset_id",
    "ix_trust_assessments_org_ingestion_batch_id",
    "ix_trust_rule_results_org_trust_assessment_id",
    "ix_trust_evidence_org_rule_result_id",
    "ix_trust_evidence_org_dataset_id",
    "ix_readiness_org_trust_assessment_id",
}

FOREIGN_KEY_TABLES = {
    "trust_assessments",
    "trust_rule_results",
    "trust_evidence",
    "analytical_readiness_decisions",
}

SINGLE_FOREIGN_KEYS = {
    ("trust_assessments", "organization_id", "organizations.id"),
    ("trust_assessments", "dataset_id", "datasets.id"),
    ("trust_assessments", "ingestion_batch_id", "ingestion_batches.id"),
    ("trust_rule_results", "organization_id", "organizations.id"),
    ("trust_rule_results", "trust_assessment_id", "trust_assessments.id"),
    ("trust_evidence", "organization_id", "organizations.id"),
    ("trust_evidence", "trust_rule_result_id", "trust_rule_results.id"),
    ("trust_evidence", "dataset_id", "datasets.id"),
    ("analytical_readiness_decisions", "organization_id", "organizations.id"),
    (
        "analytical_readiness_decisions",
        "trust_assessment_id",
        "trust_assessments.id",
    ),
}


def test_model_metadata_and_mappers_define_exact_ti_b1_contract() -> None:
    configure_mappers()

    found_uniques: list[str] = []
    found_foreign_keys: list[str] = []
    found_indexes: list[str] = []
    index_column_sets: list[tuple[str, tuple[str, ...]]] = []

    for table_name in FOREIGN_KEY_TABLES:
        table = Base.metadata.tables[table_name]
        found_uniques.extend(
            str(constraint.name)
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
            and constraint.name in PARENT_CONSTRAINTS.values()
        )
        found_foreign_keys.extend(
            str(constraint.name)
            for constraint in table.constraints
            if isinstance(constraint, ForeignKeyConstraint)
            and constraint.name in TENANT_FOREIGN_KEYS
        )
        found_indexes.extend(
            str(index.name)
            for index in table.indexes
            if isinstance(index, Index) and index.name in TENANT_INDEXES
        )
        index_column_sets.extend(
            (table_name, tuple(column.name for column in index.columns)) for index in table.indexes
        )

    assert set(found_uniques) == set(PARENT_CONSTRAINTS.values())
    assert len(found_uniques) == len(PARENT_CONSTRAINTS)
    assert set(found_foreign_keys) == TENANT_FOREIGN_KEYS
    assert len(found_foreign_keys) == len(TENANT_FOREIGN_KEYS)
    assert set(found_indexes) == TENANT_INDEXES
    assert len(found_indexes) == len(TENANT_INDEXES)
    assert len(index_column_sets) == len(set(index_column_sets))

    for table_name, constraint_name in PARENT_CONSTRAINTS.items():
        matches = [
            constraint
            for constraint in Base.metadata.tables[table_name].constraints
            if isinstance(constraint, UniqueConstraint) and constraint.name == constraint_name
        ]
        assert len(matches) == 1
        assert [column.name for column in matches[0].columns] == [
            "organization_id",
            "id",
        ]

    single_foreign_keys = {
        (table_name, column.name, foreign_key.target_fullname)
        for table_name in FOREIGN_KEY_TABLES
        for column in Base.metadata.tables[table_name].columns
        for foreign_key in column.foreign_keys
    }
    assert SINGLE_FOREIGN_KEYS <= single_foreign_keys


def test_precondition_diagnostic_detects_synthetic_tenant_mismatch() -> None:
    migration = import_module("migrations.versions.20260731_0026_ti_b1_trust_readiness_integrity")
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE datasets (id TEXT PRIMARY KEY, organization_id TEXT NOT NULL)")
        )
        connection.execute(
            text(
                "CREATE TABLE trust_assessments "
                "(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, dataset_id TEXT NOT NULL)"
            )
        )
        connection.execute(
            text("INSERT INTO datasets (id, organization_id) VALUES ('dataset-1', 'tenant-a')")
        )
        connection.execute(
            text(
                "INSERT INTO trust_assessments (id, organization_id, dataset_id) "
                "VALUES ('assessment-1', 'tenant-b', 'dataset-1')"
            )
        )
        with (
            patch.object(
                migration,
                "COMPOSITE_FOREIGN_KEYS",
                (
                    (
                        "trust_assessments",
                        "fk_trust_assessments_org_dataset",
                        "datasets",
                        "dataset_id",
                    ),
                ),
            ),
            patch.object(
                migration,
                "PARENT_UNIQUES",
                (("datasets", "uq_datasets_org_id"),),
            ),
            patch.object(migration.op, "get_bind", return_value=connection),
            pytest.raises(
                RuntimeError,
                match="fk_trust_assessments_org_dataset.*1 violating rows",
            ),
        ):
            migration._assert_clean_tenant_references()


def _assessment(
    organization_id: UUID,
    dataset_id: UUID,
    ingestion_batch_id: UUID | None,
    *,
    row_id: UUID | None = None,
) -> TrustAssessment:
    return TrustAssessment(
        id=row_id or uuid4(),
        organization_id=organization_id,
        dataset_id=dataset_id,
        ingestion_batch_id=ingestion_batch_id,
        status="pending",
    )


def _rule(
    organization_id: UUID,
    assessment_id: UUID,
    *,
    row_id: UUID | None = None,
) -> TrustRuleResult:
    return TrustRuleResult(
        id=row_id or uuid4(),
        organization_id=organization_id,
        trust_assessment_id=assessment_id,
        rule_code=f"ti-b1-{uuid4().hex[:8]}",
        rule_version="1.0.0",
        rule_name="TI-B1 test rule",
        dimension="validity",
        severity="warning",
        execution_status="completed",
        result_status="passed",
        message="TI-B1 test",
    )


def _evidence(
    organization_id: UUID,
    rule_id: UUID,
    dataset_id: UUID,
    *,
    row_id: UUID | None = None,
) -> TrustEvidence:
    return TrustEvidence(
        id=row_id or uuid4(),
        organization_id=organization_id,
        trust_rule_result_id=rule_id,
        dataset_id=dataset_id,
        evidence_type="summary",
    )


def _readiness(
    organization_id: UUID,
    assessment_id: UUID,
    *,
    row_id: UUID | None = None,
) -> AnalyticalReadinessDecision:
    return AnalyticalReadinessDecision(
        id=row_id or uuid4(),
        organization_id=organization_id,
        trust_assessment_id=assessment_id,
        analytical_level="arithmetic",
        readiness_status="ready",
        explanation="TI-B1 test",
    )


def _orm_graph(db: Session, slug: str) -> dict[str, UUID]:
    organization_id, batch_id, dataset_id = trust_foundation(db, slug)
    assessment = _assessment(organization_id, dataset_id, batch_id)
    db.add(assessment)
    db.flush()
    rule = _rule(organization_id, assessment.id)
    db.add(rule)
    db.flush()
    evidence = _evidence(organization_id, rule.id, dataset_id)
    readiness = _readiness(organization_id, assessment.id)
    db.add_all([evidence, readiness])
    db.commit()
    return {
        "organization": organization_id,
        "batch": batch_id,
        "dataset": dataset_id,
        "assessment": assessment.id,
        "rule": rule.id,
        "evidence": evidence.id,
        "readiness": readiness.id,
    }


def _core_graph(db: Session, slug: str) -> dict[str, UUID]:
    organization_id, batch_id, dataset_id = trust_foundation(db, slug)
    assessment_id = uuid4()
    rule_id = uuid4()
    evidence_id = uuid4()
    readiness_id = uuid4()
    db.execute(
        insert(cast(Table, TrustAssessment.__table__)).values(
            id=assessment_id,
            organization_id=organization_id,
            dataset_id=dataset_id,
            ingestion_batch_id=batch_id,
            status="pending",
        )
    )
    db.execute(
        insert(cast(Table, TrustRuleResult.__table__)).values(
            id=rule_id,
            organization_id=organization_id,
            trust_assessment_id=assessment_id,
            rule_code=f"ti-b1-core-{uuid4().hex[:8]}",
            rule_version="1.0.0",
            rule_name="TI-B1 core rule",
            dimension="validity",
            severity="warning",
            execution_status="completed",
            result_status="passed",
            message="TI-B1 core test",
        )
    )
    db.execute(
        insert(cast(Table, TrustEvidence.__table__)).values(
            id=evidence_id,
            organization_id=organization_id,
            trust_rule_result_id=rule_id,
            dataset_id=dataset_id,
            evidence_type="summary",
        )
    )
    db.execute(
        insert(cast(Table, AnalyticalReadinessDecision.__table__)).values(
            id=readiness_id,
            organization_id=organization_id,
            trust_assessment_id=assessment_id,
            analytical_level="arithmetic",
            readiness_status="ready",
            explanation="TI-B1 core test",
        )
    )
    db.commit()
    return {
        "organization": organization_id,
        "batch": batch_id,
        "dataset": dataset_id,
        "assessment": assessment_id,
        "rule": rule_id,
        "evidence": evidence_id,
        "readiness": readiness_id,
    }


def _assert_core_insert_rejected(
    db: Session,
    table: Table,
    values: dict[str, object],
) -> None:
    row_id = values["id"]
    with pytest.raises(IntegrityError):
        db.execute(insert(table).values(**values))
        db.commit()
    db.rollback()
    assert db.scalar(select(table.c.id).where(table.c.id == row_id)) is None


def test_direct_sql_enforces_all_six_relationships_without_partial_rows(
    db: Session,
) -> None:
    first = _core_graph(db, f"ti-b1-core-first-{uuid4().hex[:8]}")
    second = _core_graph(db, f"ti-b1-core-second-{uuid4().hex[:8]}")

    cross_insert_cases: tuple[tuple[Table, dict[str, object]], ...] = (
        (
            cast(Table, TrustAssessment.__table__),
            {
                "id": uuid4(),
                "organization_id": first["organization"],
                "dataset_id": second["dataset"],
                "ingestion_batch_id": None,
                "status": "pending",
            },
        ),
        (
            cast(Table, TrustAssessment.__table__),
            {
                "id": uuid4(),
                "organization_id": first["organization"],
                "dataset_id": first["dataset"],
                "ingestion_batch_id": second["batch"],
                "status": "pending",
            },
        ),
        (
            cast(Table, TrustRuleResult.__table__),
            {
                "id": uuid4(),
                "organization_id": first["organization"],
                "trust_assessment_id": second["assessment"],
                "rule_code": "ti-b1-cross-rule",
                "rule_version": "1.0.0",
                "rule_name": "Cross rule",
                "dimension": "validity",
                "severity": "warning",
                "execution_status": "completed",
                "result_status": "passed",
                "message": "Cross rule",
            },
        ),
        (
            cast(Table, TrustEvidence.__table__),
            {
                "id": uuid4(),
                "organization_id": first["organization"],
                "trust_rule_result_id": second["rule"],
                "dataset_id": first["dataset"],
                "evidence_type": "summary",
            },
        ),
        (
            cast(Table, TrustEvidence.__table__),
            {
                "id": uuid4(),
                "organization_id": first["organization"],
                "trust_rule_result_id": first["rule"],
                "dataset_id": second["dataset"],
                "evidence_type": "summary",
            },
        ),
        (
            cast(Table, AnalyticalReadinessDecision.__table__),
            {
                "id": uuid4(),
                "organization_id": first["organization"],
                "trust_assessment_id": second["assessment"],
                "analytical_level": "arithmetic",
                "readiness_status": "ready",
                "explanation": "Cross readiness",
            },
        ),
    )
    for table, values in cross_insert_cases:
        _assert_core_insert_rejected(db, table, values)

    update_cases: tuple[tuple[Table, UUID, dict[str, object]], ...] = (
        (
            cast(Table, TrustAssessment.__table__),
            first["assessment"],
            {"dataset_id": second["dataset"]},
        ),
        (
            cast(Table, TrustAssessment.__table__),
            first["assessment"],
            {"ingestion_batch_id": second["batch"]},
        ),
        (
            cast(Table, TrustRuleResult.__table__),
            first["rule"],
            {"trust_assessment_id": second["assessment"]},
        ),
        (
            cast(Table, TrustEvidence.__table__),
            first["evidence"],
            {"trust_rule_result_id": second["rule"]},
        ),
        (
            cast(Table, TrustEvidence.__table__),
            first["evidence"],
            {"dataset_id": second["dataset"]},
        ),
        (
            cast(Table, AnalyticalReadinessDecision.__table__),
            first["readiness"],
            {"trust_assessment_id": second["assessment"]},
        ),
    )
    for table, row_id, values in update_cases:
        with pytest.raises(IntegrityError):
            db.execute(update(table).where(table.c.id == row_id).values(**values))
            db.commit()
        db.rollback()
        assert db.scalar(select(table.c.id).where(table.c.id == row_id)) == row_id


def test_orm_enforces_all_six_relationships_without_partial_rows(db: Session) -> None:
    first = _orm_graph(db, f"ti-b1-orm-first-{uuid4().hex[:8]}")
    second = _orm_graph(db, f"ti-b1-orm-second-{uuid4().hex[:8]}")
    cross_rows = (
        _assessment(first["organization"], second["dataset"], None),
        _assessment(first["organization"], first["dataset"], second["batch"]),
        _rule(first["organization"], second["assessment"]),
        _evidence(first["organization"], second["rule"], first["dataset"]),
        _evidence(first["organization"], first["rule"], second["dataset"]),
        _readiness(first["organization"], second["assessment"]),
    )
    for row in cross_rows:
        row_id = row.id
        model = type(row)
        db.add(row)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        assert db.scalar(select(model.id).where(model.id == row_id)) is None


def test_nullable_ingestion_batch_remains_valid(db: Session) -> None:
    organization_id, _, dataset_id = trust_foundation(db, f"ti-b1-nullable-{uuid4().hex[:8]}")
    assessment = _assessment(organization_id, dataset_id, None)
    db.add(assessment)
    db.commit()
    assert assessment.ingestion_batch_id is None


def test_sqlite_migration_round_trip_restores_ti_b1_objects(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "ti-b1-lifecycle.sqlite"
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
                for table_name in FOREIGN_KEY_TABLES
                for item in inspector.get_foreign_keys(table_name)
                if item["name"] is not None
            },
            {
                str(item["name"])
                for table_name in FOREIGN_KEY_TABLES
                for item in inspector.get_indexes(table_name)
                if item["name"] is not None
            },
        )

    try:
        command.upgrade(config, "head")
        unique_names, foreign_key_names, index_names = object_names()
        assert set(PARENT_CONSTRAINTS.values()) <= unique_names
        assert TENANT_FOREIGN_KEYS <= foreign_key_names
        assert TENANT_INDEXES <= index_names

        command.downgrade(config, "20260731_0025")
        unique_names, foreign_key_names, index_names = object_names()
        assert set(PARENT_CONSTRAINTS.values()).isdisjoint(unique_names)
        assert TENANT_FOREIGN_KEYS.isdisjoint(foreign_key_names)
        assert TENANT_INDEXES.isdisjoint(index_names)

        command.upgrade(config, "head")
        unique_names, foreign_key_names, index_names = object_names()
        assert set(PARENT_CONSTRAINTS.values()) <= unique_names
        assert TENANT_FOREIGN_KEYS <= foreign_key_names
        assert TENANT_INDEXES <= index_names
    finally:
        engine.dispose()
