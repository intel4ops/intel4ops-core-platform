from uuid import UUID, uuid4

from conftest import IdentityState
from fastapi.testclient import TestClient
from pydantic import TypeAdapter
from sqlalchemy.orm import Session

from app.models.entities import MembershipRole, MembershipStatus
from app.schemas.memberships import MembershipCreate
from app.services.membership_service import OrganizationMembershipService

JSON_OBJECT = TypeAdapter(dict[str, object])


def create_organization(client: TestClient, slug: str) -> dict[str, object]:
    response = client.post(
        "/api/v1/me/organizations",
        json={
            "name": slug,
            "slug": slug,
            "country_code": "US",
            "default_currency": "USD",
            "timezone": "UTC",
        },
    )
    assert response.status_code == 201, response.text
    return JSON_OBJECT.validate_python(response.json())


def add_member(
    db: Session,
    organization_id: str,
    role: MembershipRole,
    *,
    status: MembershipStatus = MembershipStatus.ACTIVE,
) -> UUID:
    user_id = uuid4()
    OrganizationMembershipService().create(
        db,
        UUID(organization_id),
        MembershipCreate(user_id=user_id, role=role, status=status),
        invited_by_user_id=uuid4(),
    )
    return user_id


# ---------------------------------------------------------------------------
# Catalogs
# ---------------------------------------------------------------------------
def test_catalog_endpoints_require_authentication_only(
    client: TestClient, identity: IdentityState
) -> None:
    for path in (
        "/api/v1/industries",
        "/api/v1/objectives",
        "/api/v1/challenges",
        "/api/v1/systems",
    ):
        response = client.get(path)
        assert response.status_code == 200, path
        assert len(response.json()) > 0

    identity.user_id = None
    for path in (
        "/api/v1/industries",
        "/api/v1/objectives",
        "/api/v1/challenges",
        "/api/v1/systems",
    ):
        assert client.get(path).status_code == 401, path


# ---------------------------------------------------------------------------
# Known good
# ---------------------------------------------------------------------------
def test_workspace_summary_reflects_profile_industry_and_objectives(
    client: TestClient, identity: IdentityState
) -> None:
    identity.is_platform_admin = False
    organization = create_organization(client, "workspace-api-summary")
    organization_id = str(organization["id"])

    before = client.get(f"/api/v1/organizations/{organization_id}/workspace-summary")
    assert before.status_code == 200
    assert before.json()["handoff_state"] == "SETUP_IN_PROGRESS"

    profile = client.patch(
        f"/api/v1/organizations/{organization_id}", json={"industry": "manufacturing"}
    )
    assert profile.status_code == 200

    objectives = client.put(
        f"/api/v1/organizations/{organization_id}/objectives",
        json={"objective_codes": ["increase_revenue", "reduce_downtime"]},
    )
    assert objectives.status_code == 200
    assert {item["objective_code"] for item in objectives.json()} == {
        "increase_revenue",
        "reduce_downtime",
    }

    after = client.get(f"/api/v1/organizations/{organization_id}/workspace-summary")
    body = after.json()
    assert body["setup_progress"]["missing_required"] == []
    assert body["handoff_state"] == "DATA_PENDING"


def test_challenges_and_systems_round_trip(client: TestClient, identity: IdentityState) -> None:
    identity.is_platform_admin = False
    organization = create_organization(client, "workspace-api-challenges")
    organization_id = str(organization["id"])

    challenges = client.put(
        f"/api/v1/organizations/{organization_id}/challenges",
        json={"challenge_codes": ["downtime"]},
    )
    assert challenges.status_code == 200
    assert [item["challenge_code"] for item in challenges.json()] == ["downtime"]

    systems = client.put(
        f"/api/v1/organizations/{organization_id}/systems",
        json={"systems": [{"system_code": "sap"}, {"system_code": "other", "custom_label": "X"}]},
    )
    assert systems.status_code == 200
    assert {(item["system_code"], item["custom_label"]) for item in systems.json()} == {
        ("sap", None),
        ("other", "X"),
    }

    read_back = client.get(f"/api/v1/organizations/{organization_id}/systems")
    assert read_back.status_code == 200
    assert len(read_back.json()) == 2


def test_team_summary_via_api(client: TestClient, identity: IdentityState, db: Session) -> None:
    identity.is_platform_admin = False
    organization = create_organization(client, "workspace-api-team")
    organization_id = str(organization["id"])
    add_member(db, organization_id, MembershipRole.OPERATOR)

    summary = client.get(f"/api/v1/organizations/{organization_id}/team-summary")
    assert summary.status_code == 200
    body = summary.json()
    assert body["active_member_count"] == 2
    assert body["counts_by_persona"]["Operations"] == 1
    assert body["counts_by_persona"]["Admin"] == 1


# ---------------------------------------------------------------------------
# Security probes
# ---------------------------------------------------------------------------
def test_probe_a_viewer_cannot_modify_profile(
    client: TestClient, identity: IdentityState, db: Session
) -> None:
    identity.is_platform_admin = False
    organization = create_organization(client, "probe-a-viewer-profile")
    organization_id = str(organization["id"])
    viewer_id = add_member(db, organization_id, MembershipRole.VIEWER)
    identity.user_id = viewer_id

    response = client.patch(f"/api/v1/organizations/{organization_id}", json={"industry": "retail"})
    assert response.status_code == 403


def test_probe_b_analyst_cannot_replace_objectives(
    client: TestClient, identity: IdentityState, db: Session
) -> None:
    identity.is_platform_admin = False
    organization = create_organization(client, "probe-b-analyst-objectives")
    organization_id = str(organization["id"])
    analyst_id = add_member(db, organization_id, MembershipRole.ANALYST)
    identity.user_id = analyst_id

    response = client.put(
        f"/api/v1/organizations/{organization_id}/objectives",
        json={"objective_codes": ["increase_revenue"]},
    )
    assert response.status_code == 403


def test_probe_c_cross_tenant_workspace_summary_rejected(
    client: TestClient, identity: IdentityState
) -> None:
    identity.is_platform_admin = False
    organization_a = create_organization(client, "probe-c-org-a")
    identity.user_id = uuid4()
    create_organization(client, "probe-c-org-b")

    response = client.get(f"/api/v1/organizations/{organization_a['id']}/workspace-summary")
    assert response.status_code == 403


def test_probe_d_cross_tenant_mutation_rejected(
    client: TestClient, identity: IdentityState
) -> None:
    identity.is_platform_admin = False
    organization_a = create_organization(client, "probe-d-org-a")
    identity.user_id = uuid4()
    create_organization(client, "probe-d-org-b")

    for path, body in (
        ("objectives", {"objective_codes": ["increase_revenue"]}),
        ("challenges", {"challenge_codes": ["downtime"]}),
        ("systems", {"systems": [{"system_code": "sap"}]}),
    ):
        response = client.put(f"/api/v1/organizations/{organization_a['id']}/{path}", json=body)
        assert response.status_code == 403, path


def test_probe_e_invalid_registry_code_rejected(
    client: TestClient, identity: IdentityState
) -> None:
    identity.is_platform_admin = False
    organization = create_organization(client, "probe-e-invalid-code")
    organization_id = str(organization["id"])

    response = client.put(
        f"/api/v1/organizations/{organization_id}/objectives",
        json={"objective_codes": ["not_a_real_code"]},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_registry_code"


def test_probe_f_custom_label_without_permitted_code_rejected(
    client: TestClient, identity: IdentityState
) -> None:
    identity.is_platform_admin = False
    organization = create_organization(client, "probe-f-custom-label")
    organization_id = str(organization["id"])

    response = client.put(
        f"/api/v1/organizations/{organization_id}/systems",
        json={"systems": [{"system_code": "sap", "custom_label": "Not allowed"}]},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_system_selection"


def test_probe_g_team_summary_scoped_to_own_tenant(
    client: TestClient, identity: IdentityState, db: Session
) -> None:
    identity.is_platform_admin = False
    organization_a = create_organization(client, "probe-g-org-a")
    organization_a_id = str(organization_a["id"])
    add_member(db, organization_a_id, MembershipRole.OPERATOR)
    add_member(db, organization_a_id, MembershipRole.OPERATOR)

    identity.user_id = uuid4()
    organization_b = create_organization(client, "probe-g-org-b")

    summary_b = client.get(f"/api/v1/organizations/{organization_b['id']}/team-summary")
    assert summary_b.status_code == 200
    assert summary_b.json()["active_member_count"] == 1
    assert "operator" not in summary_b.json()["counts_by_role"]


def test_probe_h_revoked_user_immediately_loses_workspace_access(
    client: TestClient, identity: IdentityState, db: Session
) -> None:
    identity.is_platform_admin = False
    organization = create_organization(client, "probe-h-revoked")
    organization_id = str(organization["id"])
    member_id = add_member(db, organization_id, MembershipRole.VIEWER)

    identity.user_id = member_id
    ok = client.get(f"/api/v1/organizations/{organization_id}/workspace-summary")
    assert ok.status_code == 200

    membership_service = OrganizationMembershipService()
    membership = next(
        m for m in membership_service.list(db, UUID(organization_id)) if m.user_id == member_id
    )
    membership_service.revoke(db, UUID(organization_id), membership.id)

    revoked = client.get(f"/api/v1/organizations/{organization_id}/workspace-summary")
    assert revoked.status_code == 403


def test_probe_i_readiness_never_reaches_100_from_optional_fields_alone(
    client: TestClient, identity: IdentityState
) -> None:
    identity.is_platform_admin = False
    organization = create_organization(client, "probe-i-optional-only")
    organization_id = str(organization["id"])

    client.put(
        f"/api/v1/organizations/{organization_id}/challenges",
        json={"challenge_codes": ["downtime"]},
    )
    client.put(
        f"/api/v1/organizations/{organization_id}/systems",
        json={"systems": [{"system_code": "sap"}]},
    )

    summary = client.get(f"/api/v1/organizations/{organization_id}/workspace-summary")
    body = summary.json()
    assert body["setup_progress"]["percent"] < 100
    assert "industry" in body["setup_progress"]["missing_required"]
    assert "objectives" in body["setup_progress"]["missing_required"]


def test_probe_j_ready_for_value_scan_requires_real_data_evidence(
    client: TestClient, identity: IdentityState
) -> None:
    identity.is_platform_admin = False
    organization = create_organization(client, "probe-j-no-fake-data")
    organization_id = str(organization["id"])

    client.patch(f"/api/v1/organizations/{organization_id}", json={"industry": "manufacturing"})
    client.put(
        f"/api/v1/organizations/{organization_id}/objectives",
        json={"objective_codes": ["increase_revenue"]},
    )

    summary = client.get(f"/api/v1/organizations/{organization_id}/workspace-summary")
    body = summary.json()
    # All required components are satisfied (industry + >=1 objective + base
    # profile), so workspace setup itself is no longer blocking -- but no
    # dataset/ingestion evidence exists for this org, so the handoff must
    # not claim readiness merely because the required fields were filled in.
    assert body["setup_progress"]["missing_required"] == []
    assert body["data_readiness"] == "NOT_STARTED"
    assert body["ai_readiness"] in ("NOT_READY", "PENDING_DATA")
    assert body["handoff_state"] != "READY_FOR_VALUE_SCAN"
