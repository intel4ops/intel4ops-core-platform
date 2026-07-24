import os
from collections.abc import Iterator
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
from app.schemas.memberships import MembershipCreate
from app.services.finding_service import FindingService
from app.services.membership_service import (
    DuplicateMembershipError,
    OrganizationMembershipService,
)
from app.services.organization_service import OrganizationService

MANAGED_TABLES = {
    "organizations",
    "findings",
    "finding_evidence",
    "recovery_actions",
    "organization_members",
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

    command.downgrade(config, "20260724_0001")
    wp_201_tables = set(inspect(postgres_engine).get_table_names())
    assert "organization_members" not in wp_201_tables
    assert MANAGED_TABLES - {"organization_members"} <= wp_201_tables

    command.upgrade(config, "head")
    assert_schema_at_head(postgres_engine)

    command.downgrade(config, "base")
    assert not (MANAGED_TABLES & set(inspect(postgres_engine).get_table_names()))

    command.upgrade(config, "head")
    assert_schema_at_head(postgres_engine)


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
