from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from conftest import IdentityState
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_commercial_api import commercial_foundation, create_subscription
from test_operational_memory_service import field_candidate, memory_foundation

from app.models.entities import OrganizationMembership
from app.models.operational_memory import (
    OperationalMemoryItem,
    OperationalMemoryReuseEvent,
    OperationalMemoryVersion,
)
from app.schemas.operational_memory import MemoryDecisionRequest
from app.services.operational_memory_service import operational_memory_service


@pytest.fixture(autouse=True)
def cleanup_memory_rows(db_engine: Engine) -> Iterator[None]:
    yield
    with Session(db_engine) as cleanup:
        cleanup.execute(delete(OperationalMemoryReuseEvent))
        ids = list(
            cleanup.scalars(
                select(OperationalMemoryVersion.id).order_by(
                    OperationalMemoryVersion.version_number.desc()
                )
            )
        )
        for identifier in ids:
            cleanup.execute(
                delete(OperationalMemoryVersion).where(OperationalMemoryVersion.id == identifier)
            )
        cleanup.execute(delete(OperationalMemoryItem))
        cleanup.commit()


def test_memory_api_list_get_retrieve_decide_and_safe_foreign_id(
    client: TestClient, db: Session
) -> None:
    org, actor, schema, field_id = memory_foundation(db, "memory-api")
    other, _, _, _ = memory_foundation(db, "memory-api-other")
    observed, _ = operational_memory_service.record_candidate(
        db, org, field_candidate(schema, field_id, "api:candidate"), actor
    )
    path = f"/api/v1/organizations/{org}/operational-memories"
    listed = client.get(path, params={"category": "FIELD_MAPPING", "limit": 1})
    assert listed.status_code == 200, listed.text
    assert listed.json()["items"][0]["id"] == str(observed.id)
    assert client.get(f"{path}/{observed.id}").status_code == 200
    assert (
        client.get(f"/api/v1/organizations/{other}/operational-memories/{observed.id}").status_code
        == 404
    )

    confirmed = client.post(
        f"{path}/{observed.id}/decisions",
        json={
            "idempotency_key": "api:confirm",
            "expected_current_version": 1,
            "action": "CONFIRM",
            "decision_reason_code": "HUMAN_REVIEWED",
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["item"]["current_status"] == "CONFIRMED"
    retrieved = client.post(
        f"{path}/retrieve",
        json={
            "idempotency_key": "api:retrieve",
            "category": "FIELD_MAPPING",
            "subject_kind": "SOURCE_FIELD",
            "subject": "Equipment Number",
            "source_system_family": "ERP",
            "canonical_domain": "maintenance",
            "context": {
                "schema_fingerprint": schema.schema_fingerprint,
                "source_table_or_entity_context": "equipment_master",
                "neighboring_field_signatures": ["status:string", "description:string"],
            },
        },
    )
    assert retrieved.status_code == 200, retrieved.text
    assert retrieved.json()["suggestions"][0]["memory_id"] == str(observed.id)


def test_memory_api_keyset_pagination_and_validation(client: TestClient, db: Session) -> None:
    org, actor, schema, field_id = memory_foundation(db, "memory-pagination")
    for number in range(3):
        operational_memory_service.record_candidate(
            db,
            org,
            field_candidate(
                schema,
                field_id,
                f"page:{number}",
                subject=f"Equipment Field {number}",
            ),
            actor,
        )
    path = f"/api/v1/organizations/{org}/operational-memories"
    first = client.get(path, params={"limit": 2})
    assert first.status_code == 200
    assert len(first.json()["items"]) == 2
    cursor = first.json()["next_cursor"]
    second = client.get(path, params={"limit": 2, "cursor": cursor})
    assert second.status_code == 200
    assert len(second.json()["items"]) == 1
    assert client.get(path, params={"cursor": "not-a-cursor"}).status_code == 422
    invalid = client.post(
        f"{path}/retrieve",
        json={
            "idempotency_key": "invalid",
            "category": "FIELD_MAPPING",
            "subject_kind": "TERM",
            "subject": "equipment",
        },
    )
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "CATEGORY_SUBJECT_MISMATCH"


def test_memory_api_roles_revocation_and_entitlement(
    client: TestClient,
    db: Session,
    db_engine: Engine,
    identity: IdentityState,
) -> None:
    org, actor, schema, field_id = memory_foundation(db, "memory-auth")
    item, _ = operational_memory_service.record_candidate(
        db, org, field_candidate(schema, field_id, "auth:candidate"), actor
    )
    viewer = uuid4()
    admin = uuid4()
    for user_id, role in ((viewer, "viewer"), (admin, "organization_admin")):
        response = client.post(
            f"/api/v1/organizations/{org}/members",
            json={"user_id": str(user_id), "role": role, "status": "active"},
        )
        assert response.status_code == 201
    path = f"/api/v1/organizations/{org}/operational-memories"
    identity.is_platform_admin = False
    identity.user_id = viewer
    assert client.get(path).status_code == 200
    denied = client.post(
        f"{path}/{item.id}/decisions",
        json=MemoryDecisionRequest(
            idempotency_key="viewer:denied",
            expected_current_version=1,
            action="CONFIRM",
        ).model_dump(mode="json"),
    )
    assert denied.status_code == 403
    with Session(db_engine) as worker:
        worker.execute(
            update(OrganizationMembership)
            .where(
                OrganizationMembership.organization_id == org,
                OrganizationMembership.user_id == viewer,
            )
            .values(status="revoked")
        )
        worker.commit()
    assert client.get(path).status_code == 403

    plan_version = commercial_foundation(db)
    identity.user_id = admin
    create_subscription(client, str(org), str(plan_version.id), key="memory:subscription")
    missing = client.get(path)
    assert missing.status_code == 403
    assert missing.json()["detail"]["code"] == "ENTITLEMENT_REQUIRED"


def test_no_generic_create_patch_or_delete_routes(client: TestClient, db: Session) -> None:
    org, _, _, _ = memory_foundation(db, "memory-no-create")
    path = f"/api/v1/organizations/{org}/operational-memories"
    assert client.post(path, json={}).status_code == 405
    assert client.patch(f"{path}/{uuid4()}", json={}).status_code == 405
    assert client.delete(f"{path}/{uuid4()}").status_code == 405
