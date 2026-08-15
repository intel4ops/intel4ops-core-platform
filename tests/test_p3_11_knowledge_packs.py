from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from conftest import IdentityState
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_decision_intelligence_foundation import make_org

from app.main import app
from app.models.learning import OperationalLearning


def _path(organization_id: UUID, suffix: str = "") -> str:
    return f"/api/v1/organizations/{organization_id}/knowledge-packs{suffix}"


def _learning(
    db: Session,
    organization_id: UUID,
    actor_id: UUID,
    suffix: str,
    provenance: str,
    status: str = "approved_for_reuse",
) -> OperationalLearning:
    row = OperationalLearning(
        organization_id=organization_id,
        learning_type="corrective_action",
        title=f"Reference job-to-cash learning {suffix}",
        statement="Synthetic reference fixture; not production-validated client knowledge.",
        scope="Oilfield services job-to-cash reference test context only.",
        status=status,
        provenance_type=provenance,
        value_basis="none",
        created_by_user_id=actor_id,
    )
    db.add(row)
    db.commit()
    return row


def _create(client: TestClient, organization_id: UUID, slug: str = "job-to-cash-reference") -> dict:
    response = client.post(
        _path(organization_id),
        json={
            "name": "Oilfield Services — Job-to-Cash Reference Pack",
            "slug": slug,
            "description": "Governed reference structure; no client validation claim.",
            "industry": "oilfield_services",
            "domain": "job_to_cash",
            "scope": "Reference operational value leakage patterns for bounded review.",
            "change_summary": "Create reference pack structure.",
        },
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


def _add(
    client: TestClient,
    organization_id: UUID,
    pack_id: str,
    version_id: str,
    learning_id: UUID,
) -> dict:
    response = client.post(
        _path(organization_id, f"/{pack_id}/versions/{version_id}/learning"),
        json={
            "learning_id": str(learning_id),
            "inclusion_rationale": "Approved reference Learning is relevant to this bounded scope.",
        },
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


def _transition(
    client: TestClient,
    organization_id: UUID,
    pack_id: str,
    version_id: str,
    command: str,
) -> dict:
    response = client.post(
        _path(organization_id, f"/{pack_id}/versions/{version_id}/{command}"),
        json={"rationale": f"Governed {command} after bounded human review."},
    )
    assert response.status_code == 200, response.text
    return cast(dict[str, Any], response.json())


def test_auth_membership_required_and_scope_is_validated(
    client: TestClient, identity: IdentityState, db: Session
) -> None:
    identity.user_id = None
    assert client.get(_path(uuid4())).status_code == 401
    identity.user_id = uuid4()
    identity.is_platform_admin = False
    organization_id, _ = make_org(db, "p311-membership")
    assert client.get(_path(organization_id)).status_code in {403, 404}
    identity.is_platform_admin = True
    invalid = client.post(
        _path(organization_id),
        json={
            "name": "Missing scope",
            "slug": "missing-scope",
            "description": "Invalid bounded fixture",
            "industry": "oilfield_services",
            "domain": "job_to_cash",
            "scope": "",
            "change_summary": "Invalid",
        },
    )
    assert invalid.status_code == 422


def test_create_is_draft_version_one_and_audited(client: TestClient, db: Session) -> None:
    organization_id, _ = make_org(db, "p311-create")
    pack = _create(client, organization_id)
    assert pack["organization_id"] == str(organization_id)
    assert pack["current_approved_version"] is None
    assert pack["latest_draft_version"]["version_number"] == 1
    assert pack["latest_draft_version"]["lifecycle_status"] == "draft"
    assert pack["latest_draft_version"]["provenance_summary"] is None
    assert [event["event_type"] for event in pack["audit_history"]] == [
        "pack_created",
        "version_created",
    ]


def test_only_approved_same_tenant_learning_can_enter_draft(
    client: TestClient, identity: IdentityState, db: Session
) -> None:
    organization_id, actor_id = make_org(db, "p311-eligibility")
    pack = _create(client, organization_id)
    version_id = pack["latest_draft_version"]["id"]
    candidate = _learning(db, organization_id, actor_id, "candidate", "manual", "candidate")
    denied = client.post(
        _path(organization_id, f"/{pack['id']}/versions/{version_id}/learning"),
        json={"learning_id": str(candidate.id), "inclusion_rationale": "Not yet eligible."},
    )
    assert denied.status_code == 409
    assert denied.json()["detail"]["code"] == "LEARNING_NOT_ELIGIBLE"
    foreign_id, foreign_actor = make_org(db, "p311-foreign-learning")
    foreign = _learning(db, foreign_id, foreign_actor, "foreign", "production")
    foreign_denied = client.post(
        _path(organization_id, f"/{pack['id']}/versions/{version_id}/learning"),
        json={"learning_id": str(foreign.id), "inclusion_rationale": "Must not cross tenant."},
    )
    assert foreign_denied.status_code == 404
    identity.is_platform_admin = True


def test_provenance_is_derived_and_cannot_be_forged(client: TestClient, db: Session) -> None:
    organization_id, actor_id = make_org(db, "p311-provenance")
    production = _learning(db, organization_id, actor_id, "production", "production")
    simulation = _learning(db, organization_id, actor_id, "simulation", "simulation")
    pack = _create(client, organization_id)
    version = pack["latest_draft_version"]
    production_version = _add(client, organization_id, pack["id"], version["id"], production.id)
    assert production_version["provenance_summary"] == "production"
    forged = client.post(
        _path(organization_id, f"/{pack['id']}/versions/{version['id']}/learning"),
        json={
            "learning_id": str(simulation.id),
            "inclusion_rationale": "Simulation must remain visible.",
            "provenance_summary": "production",
        },
    )
    assert forged.status_code == 201
    assert forged.json()["provenance_summary"] == "mixed"
    assert {member["learning"]["provenance_type"] for member in forged.json()["members"]} == {
        "production",
        "simulation",
    }


def test_simulation_only_and_manual_only_are_honest(client: TestClient, db: Session) -> None:
    organization_id, actor_id = make_org(db, "p311-honest-provenance")
    for provenance in ("simulation", "manual"):
        learning = _learning(db, organization_id, actor_id, provenance, provenance)
        pack = _create(client, organization_id, f"{provenance}-reference")
        version = pack["latest_draft_version"]
        body = _add(client, organization_id, pack["id"], version["id"], learning.id)
        assert body["provenance_summary"] == provenance


def test_approval_immutability_and_version_supersession(client: TestClient, db: Session) -> None:
    organization_id, actor_id = make_org(db, "p311-versioning")
    learning = _learning(db, organization_id, actor_id, "v1", "production")
    second = _learning(db, organization_id, actor_id, "v2", "manual")
    pack = _create(client, organization_id)
    v1 = pack["latest_draft_version"]
    _add(client, organization_id, pack["id"], v1["id"], learning.id)
    _transition(client, organization_id, pack["id"], v1["id"], "submit")
    approved = _transition(client, organization_id, pack["id"], v1["id"], "approve")
    assert approved["current_approved_version"]["id"] == v1["id"]
    immutable = client.delete(
        _path(organization_id, f"/{pack['id']}/versions/{v1['id']}/learning/{learning.id}")
    )
    assert immutable.status_code == 409
    next_version = client.post(
        _path(organization_id, f"/{pack['id']}/versions"),
        json={"change_summary": "Add expert-authored bounded context."},
    )
    assert next_version.status_code == 201, next_version.text
    v2 = next_version.json()["latest_draft_version"]
    assert v2["version_number"] == 2
    assert next_version.json()["current_approved_version"]["id"] == v1["id"]
    assert len(v2["members"]) == 1
    _add(client, organization_id, pack["id"], v2["id"], second.id)
    _transition(client, organization_id, pack["id"], v2["id"], "submit")
    promoted = _transition(client, organization_id, pack["id"], v2["id"], "approve")
    assert promoted["current_approved_version"]["id"] == v2["id"]
    historical = {row["version_number"]: row for row in promoted["versions"]}
    assert historical[1]["lifecycle_status"] == "superseded"
    assert historical[1]["members"][0]["learning"]["id"] == str(learning.id)
    assert historical[2]["provenance_summary"] == "mixed"


def test_reject_retire_and_invalid_transitions_are_explicit(
    client: TestClient, db: Session
) -> None:
    organization_id, actor_id = make_org(db, "p311-transitions")
    learning = _learning(db, organization_id, actor_id, "transition", "manual")
    rejected_pack = _create(client, organization_id, "rejected-reference")
    rejected_version = rejected_pack["latest_draft_version"]
    _add(
        client,
        organization_id,
        rejected_pack["id"],
        rejected_version["id"],
        learning.id,
    )
    _transition(client, organization_id, rejected_pack["id"], rejected_version["id"], "submit")
    rejected = _transition(
        client, organization_id, rejected_pack["id"], rejected_version["id"], "reject"
    )
    assert rejected["versions"][0]["lifecycle_status"] == "rejected"
    invalid = client.post(
        _path(
            organization_id,
            f"/{rejected_pack['id']}/versions/{rejected_version['id']}/approve",
        ),
        json={"rationale": "Rejected cannot be approved directly."},
    )
    assert invalid.status_code == 409

    approved_pack = _create(client, organization_id, "retired-reference")
    approved_version = approved_pack["latest_draft_version"]
    _add(client, organization_id, approved_pack["id"], approved_version["id"], learning.id)
    _transition(client, organization_id, approved_pack["id"], approved_version["id"], "submit")
    _transition(client, organization_id, approved_pack["id"], approved_version["id"], "approve")
    retired = _transition(
        client, organization_id, approved_pack["id"], approved_version["id"], "retire"
    )
    assert retired["current_approved_version"] is None
    assert retired["versions"][0]["lifecycle_status"] == "retired"


def test_empty_pack_cannot_submit_and_no_auto_approval(client: TestClient, db: Session) -> None:
    organization_id, _ = make_org(db, "p311-no-auto")
    pack = _create(client, organization_id)
    version = pack["latest_draft_version"]
    response = client.post(
        _path(organization_id, f"/{pack['id']}/versions/{version['id']}/submit"),
        json={"rationale": "Must not pass without Learning."},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "PACK_MEMBERSHIP_REQUIRED"


def test_tenant_reads_filters_pagination_and_openapi(client: TestClient, db: Session) -> None:
    first_id, _ = make_org(db, "p311-list-first")
    second_id, _ = make_org(db, "p311-list-second")
    pack = _create(client, first_id)
    _create(client, first_id, "second-reference")
    assert client.get(_path(second_id, f"/{pack['id']}")).status_code == 404
    page = client.get(
        _path(first_id) + "?page=1&page_size=1&industry=oilfield_services&domain=job_to_cash"
    ).json()
    assert page["total"] == 2
    assert len(page["items"]) == 1
    draft = client.get(_path(first_id) + "?lifecycle=draft").json()
    assert draft["total"] == 2
    assert all("guaranteed" not in str(item).lower() for item in draft["items"])
    route = "/api/v1/organizations/{organization_id}/knowledge-packs"
    assert route in app.openapi()["paths"]
    ids = [
        operation["operationId"]
        for path in app.openapi()["paths"].values()
        for operation in path.values()
        if isinstance(operation, dict) and "operationId" in operation
    ]
    assert len(ids) == len(set(ids))


def test_audit_order_is_deterministic_under_a_forced_identical_timestamp(
    monkeypatch: pytest.MonkeyPatch, db: Session
) -> None:
    """Regression for the P3.11 post-merge defect: pack_created and version_created
    used to receive independent datetime.now(UTC) calls and were ordered by
    (occurred_at, id) -- a random UUID tiebreaker whenever both calls landed on the
    same timestamp. Force that exact tie here and prove `sequence` decides order
    instead, deterministically, every time."""
    from datetime import UTC, datetime
    from datetime import tzinfo as TzInfo

    import app.services.knowledge_pack_service as kp_module
    from app.schemas.knowledge_pack import KnowledgePackCreate
    from app.services.knowledge_pack_service import knowledge_pack_service

    organization_id, actor_id = make_org(db, "p311-audit-tie")
    frozen = datetime(2026, 8, 21, 12, 0, 0, tzinfo=UTC)

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: TzInfo | None = None) -> "_FrozenDateTime":
            return cast(_FrozenDateTime, frozen)

    monkeypatch.setattr(kp_module, "datetime", _FrozenDateTime)
    for attempt in range(25):
        pack = knowledge_pack_service.create(
            db,
            organization_id,
            KnowledgePackCreate(
                name="Forced-tie reference pack",
                slug=f"forced-tie-{attempt}",
                description="Deterministic ordering regression fixture.",
                industry="oilfield_services",
                domain="job_to_cash",
                scope="Reference test context only.",
                change_summary="Initial draft",
            ),
            actor_id,
            "organization_admin",
        )
        events = [(e.event_type, e.occurred_at.replace(tzinfo=UTC)) for e in pack.audit_history]
        assert events[0][1] == events[1][1] == frozen, "test did not actually force a tie"
        assert [e.event_type for e in pack.audit_history] == [
            "pack_created",
            "version_created",
        ], f"attempt {attempt}: audit order was not deterministic under a forced timestamp tie"


def test_audit_order_survives_many_creation_repetitions(client: TestClient, db: Session) -> None:
    organization_id, _ = make_org(db, "p311-audit-repeat")
    for attempt in range(60):
        pack = _create(client, organization_id, f"repeat-reference-{attempt}")
        assert [event["event_type"] for event in pack["audit_history"]] == [
            "pack_created",
            "version_created",
        ], f"repetition {attempt} produced non-deterministic audit order"


def test_version_lifecycle_audit_preserves_true_event_order(
    client: TestClient, db: Session
) -> None:
    organization_id, actor_id = make_org(db, "p311-audit-lifecycle")
    learning = _learning(db, organization_id, actor_id, "lifecycle-v1", "production")
    second = _learning(db, organization_id, actor_id, "lifecycle-v2", "manual")
    pack = _create(client, organization_id, "lifecycle-reference")
    v1 = pack["latest_draft_version"]
    _add(client, organization_id, pack["id"], v1["id"], learning.id)
    _transition(client, organization_id, pack["id"], v1["id"], "submit")
    _transition(client, organization_id, pack["id"], v1["id"], "approve")
    next_version = client.post(
        _path(organization_id, f"/{pack['id']}/versions"),
        json={"change_summary": "Next bounded revision."},
    ).json()
    v2 = next_version["latest_draft_version"]
    _add(client, organization_id, pack["id"], v2["id"], second.id)
    _transition(client, organization_id, pack["id"], v2["id"], "submit")
    promoted = _transition(client, organization_id, pack["id"], v2["id"], "approve")
    event_types = [event["event_type"] for event in promoted["audit_history"]]
    # True causal order: v1 is created, gains its Learning, is submitted and approved;
    # only then does v2 exist to be created, gain Learning, be submitted, and on its
    # own approval, cause v1's supersession as part of that same request.
    assert event_types == [
        "pack_created",
        "version_created",
        "learning_added",
        "submit",
        "approve",
        "version_created",
        "learning_added",
        "submit",
        "version_superseded",
        "approve",
    ]
    for event in promoted["audit_history"]:
        assert event["actor_role"]
        assert event["actor_user_id"]
    supersede_event = next(
        e for e in promoted["audit_history"] if e["event_type"] == "version_superseded"
    )
    assert supersede_event["prior_status"] == "approved"
    assert supersede_event["new_status"] == "superseded"
    assert supersede_event["rationale"] == "Governed approve after bounded human review."


def test_audit_retrieval_remains_tenant_scoped_after_ordering_fix(
    client: TestClient, db: Session
) -> None:
    first_id, _ = make_org(db, "p311-audit-tenant-first")
    second_id, _ = make_org(db, "p311-audit-tenant-second")
    _create(client, first_id, "tenant-audit-first")
    _create(client, second_id, "tenant-audit-second")
    first_page = client.get(_path(first_id)).json()
    assert first_page["total"] == 1
    assert all(
        event["event_type"] in {"pack_created", "version_created"}
        for pack in first_page["items"]
        for event in pack["audit_history"]
    )
    second_page = client.get(_path(second_id)).json()
    assert second_page["total"] == 1
    assert first_page["items"][0]["id"] != second_page["items"][0]["id"]
