import os
from collections.abc import Iterator
from datetime import UTC, datetime
from urllib.parse import urlparse
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import (
    Finding,
    MembershipRole,
    MembershipStatus,
    OrganizationMembership,
)
from app.schemas.contracts import FindingCreate, OrganizationCreate
from app.schemas.ingestion import (
    DatasetCreate,
    DatasetVersionCountsUpdate,
    DatasetVersionCreate,
    IngestionBatchCreate,
)
from app.schemas.memberships import MembershipCreate
from app.schemas.raw_lineage import RawStorageObjectCreate
from app.schemas.source_systems import SourceSystemCreate
from app.schemas.trust import TrustAssessmentCreate
from app.services.finding_service import FindingService
from app.services.ingestion_service import (
    DatasetService,
    DatasetVersionService,
    IngestionBatchService,
)
from app.services.membership_service import (
    DuplicateMembershipError,
    OrganizationMembershipService,
)
from app.services.organization_service import OrganizationService
from app.services.raw_lineage_service import RawStorageObjectService
from app.services.source_system_service import (
    DuplicateSourceSystemCodeError,
    SourceSystemService,
)
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
        "findings": {("organization_id", "organizations", "id")},
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


@pytest.mark.postgres
def test_migrations_on_disposable_postgres(postgres_engine: Engine) -> None:
    config = alembic_config(require_disposable_postgres_url())

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
    assert MANAGED_TABLES - wp_204_tables - wp_205_tables - wp_206_tables <= wp_203_tables

    command.upgrade(config, "head")
    assert_schema_at_head(postgres_engine)

    command.downgrade(config, "base")
    assert not (MANAGED_TABLES & set(inspect(postgres_engine).get_table_names()))

    command.upgrade(config, "head")
    assert_schema_at_head(postgres_engine)


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
        assert len(trust_service.readiness(session, organization.id, assessment.id)) == 5


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
