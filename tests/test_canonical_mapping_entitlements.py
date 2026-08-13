from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from conftest import IdentityState
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_canonical_mapping_foundation import foundation
from test_commercial_api import commercial_foundation, create_subscription
from test_field_mapping_suggestions import FIELD_PATH, _organization_template, _schema_with_field

from app.api.canonical_mapping_routes import catalog_router, tenant_router
from app.api.memory_effectiveness_routes import router as memory_effectiveness_router
from app.models.canonical_mapping import FieldMapping
from app.models.entities import MembershipRole, MembershipStatus, OrganizationMembership
from app.schemas.commercial import EntitlementGrant
from app.services.commercial_service import entitlement_service

ENTITLEMENT = "connect.canonical_mapping"


def _grant_membership(
    db: Session, organization_id: UUID, user_id: UUID, role: MembershipRole
) -> None:
    db.add(
        OrganizationMembership(
            organization_id=organization_id,
            user_id=user_id,
            role=role.value,
            status=MembershipStatus.ACTIVE.value,
        )
    )
    db.commit()


def _commercialize(
    client: TestClient,
    db: Session,
    organization_id: UUID,
    actor: UUID,
    *,
    entitled: bool,
) -> None:
    plan_version = commercial_foundation(db)
    create_subscription(
        client,
        str(organization_id),
        str(plan_version.id),
        key=f"cm04:{organization_id}:subscription",
    )
    if entitled:
        now = datetime.now(UTC)
        entitlement_service.grant(
            db,
            organization_id,
            EntitlementGrant(
                entitlement_type="capability",
                entitlement_key=ENTITLEMENT,
                source="manual",
                effective_at=now - timedelta(minutes=1),
                expires_at=now + timedelta(days=30),
                idempotency_key=f"cm04:{organization_id}:entitlement",
            ),
            actor,
        )


def _set_identity(identity: IdentityState, user_id: UUID) -> None:
    identity.is_platform_admin = False
    identity.user_id = user_id


def _commercial_dependency(route: APIRoute) -> object | None:
    for dependency in route.dependant.dependencies:
        call = dependency.call
        if call is None:
            continue
        if "require_commercial_entitlement" not in getattr(call, "__qualname__", ""):
            continue
        closure_values = tuple(cell.cell_contents for cell in (call.__closure__ or ()))
        if ENTITLEMENT in closure_values:
            return call
    return None


def test_every_tenant_operation_uses_canonical_mapping_entitlement() -> None:
    routes = [route for route in tenant_router.routes if isinstance(route, APIRoute)]

    assert len(routes) == 29
    assert len({(route.path, tuple(sorted(route.methods or set()))) for route in routes}) == 29
    assert all(_commercial_dependency(route) is not None for route in routes)


def test_platform_catalog_routes_remain_platform_admin_only() -> None:
    routes = [route for route in catalog_router.routes if isinstance(route, APIRoute)]

    assert len(routes) == 4
    assert all(_commercial_dependency(route) is None for route in routes)
    assert all(
        any(
            dependency.call is not None and dependency.call.__name__ == "require_platform_admin"
            for dependency in route.dependant.dependencies
        )
        for route in routes
    )


def test_memory_effectiveness_remains_commercially_entitled() -> None:
    routes = [route for route in memory_effectiveness_router.routes if isinstance(route, APIRoute)]

    assert len(routes) == 1
    assert _commercial_dependency(routes[0]) is not None


def test_entitled_read_and_mutation_succeed(
    client: TestClient, db: Session, identity: IdentityState
) -> None:
    organization_id, actor, dataset_id, dataset_version_id, *_ = foundation(db, "cm04-entitled")
    user_id = uuid4()
    _grant_membership(db, organization_id, user_id, MembershipRole.ORGANIZATION_ADMIN)
    _commercialize(client, db, organization_id, actor, entitled=True)
    _set_identity(identity, user_id)

    read = client.get(
        f"/api/v1/organizations/{organization_id}/canonical-mapping/canonical-types",
        params={"kind": "entity"},
    )
    mutation = client.post(
        f"/api/v1/organizations/{organization_id}/canonical-mapping/source-schemas/discover",
        json={
            "dataset_id": str(dataset_id),
            "dataset_version_id": str(dataset_version_id),
            "schema_fingerprint": "a" * 32,
            "fields": [],
        },
    )

    assert read.status_code == 200
    assert mutation.status_code == 201


@pytest.mark.parametrize(
    ("method", "suffix", "payload"),
    [
        ("get", "/canonical-types?kind=entity", None),
        ("post", "/source-schemas/discover", {}),
        ("get", f"/source-schemas/{uuid4()}/field-mapping-suggestions", None),
        ("post", "/mapping-runs", {}),
        ("post", f"/mapping-template-versions/{uuid4()}/field-mappings", {}),
    ],
)
def test_commercial_tenant_without_entitlement_is_denied_before_handler(
    client: TestClient,
    db: Session,
    identity: IdentityState,
    method: str,
    suffix: str,
    payload: dict[str, object] | None,
) -> None:
    organization_id, actor, *_ = foundation(db, f"cm04-denied-{method}-{uuid4().hex[:6]}")
    user_id = uuid4()
    _grant_membership(db, organization_id, user_id, MembershipRole.ORGANIZATION_ADMIN)
    _commercialize(client, db, organization_id, actor, entitled=False)
    _set_identity(identity, user_id)

    response = client.request(
        method,
        f"/api/v1/organizations/{organization_id}/canonical-mapping{suffix}",
        json=payload,
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ENTITLEMENT_REQUIRED"


def test_role_and_membership_are_checked_before_entitlement(
    client: TestClient, db: Session, identity: IdentityState
) -> None:
    organization_id, actor, *_ = foundation(db, "cm04-ordering")
    viewer = uuid4()
    outsider = uuid4()
    _grant_membership(db, organization_id, viewer, MembershipRole.VIEWER)
    _commercialize(client, db, organization_id, actor, entitled=False)

    _set_identity(identity, viewer)
    wrong_role = client.post(
        f"/api/v1/organizations/{organization_id}/canonical-mapping/mapping-templates",
        json={},
    )
    _set_identity(identity, outsider)
    wrong_tenant = client.get(
        f"/api/v1/organizations/{organization_id}/canonical-mapping/canonical-types?kind=entity"
    )

    assert wrong_role.status_code == 403
    assert wrong_role.json()["detail"] == "Organization access denied"
    assert wrong_tenant.status_code == 403
    assert wrong_tenant.json()["detail"] == "Organization access denied"


def test_no_subscription_legacy_compatibility_is_preserved(
    client: TestClient, db: Session, identity: IdentityState
) -> None:
    organization_id, _, *_ = foundation(db, "cm04-legacy")
    viewer = uuid4()
    _grant_membership(db, organization_id, viewer, MembershipRole.VIEWER)
    _set_identity(identity, viewer)

    response = client.get(
        f"/api/v1/organizations/{organization_id}/canonical-mapping/canonical-types?kind=entity"
    )

    assert response.status_code == 200


def test_entitled_suggestions_are_read_only(
    client: TestClient, db: Session, identity: IdentityState
) -> None:
    organization_id, actor, dataset_id, version_id, *_ = foundation(db, "cm04-suggestions")
    _field, _, _version = _organization_template(db, organization_id, actor, "cm04-suggestions")
    schema = _schema_with_field(db, organization_id, dataset_id, version_id, "cm04-suggestions")
    viewer = uuid4()
    _grant_membership(db, organization_id, viewer, MembershipRole.VIEWER)
    _commercialize(client, db, organization_id, actor, entitled=True)
    _set_identity(identity, viewer)
    before = db.scalar(select(func.count()).select_from(FieldMapping))

    response = client.get(
        f"/api/v1/organizations/{organization_id}/canonical-mapping/source-schemas/{schema.id}/field-mapping-suggestions"
    )

    assert response.status_code == 200
    assert db.scalar(select(func.count()).select_from(FieldMapping)) == before


def test_entitled_field_mapping_preserves_cm03_http_semantics(
    client: TestClient, db: Session, identity: IdentityState
) -> None:
    organization_id, actor, *_ = foundation(db, "cm04-cm03")
    field, other_field, version = _organization_template(db, organization_id, actor, "cm04-cm03")
    author = uuid4()
    _grant_membership(db, organization_id, author, MembershipRole.ANALYST)
    _commercialize(client, db, organization_id, actor, entitled=True)
    _set_identity(identity, author)
    path = (
        f"/api/v1/organizations/{organization_id}/canonical-mapping/"
        f"mapping-template-versions/{version.id}/field-mappings"
    )
    payload = {
        "source_field_path": FIELD_PATH,
        "canonical_field_definition_id": str(field.id),
        "sequence": 0,
        "default_value": "unknown",
    }

    fresh = client.post(path, json=payload)
    replay = client.post(path, json=payload)
    semantic_conflict = client.post(path, json={**payload, "default_value": "different"})
    sequence_conflict = client.post(
        path,
        json={
            **payload,
            "source_field_path": "equipment_alias",
            "canonical_field_definition_id": str(other_field.id),
        },
    )

    assert fresh.status_code == 201
    assert replay.status_code == 200
    assert fresh.json()["id"] == replay.json()["id"]
    assert semantic_conflict.status_code == 409
    assert semantic_conflict.json()["detail"]["code"] == "FIELD_MAPPING_CONFLICT"
    assert sequence_conflict.status_code == 409
    assert sequence_conflict.json()["detail"]["code"] == "FIELD_MAPPING_SEQUENCE_CONFLICT"
