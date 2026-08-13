from uuid import uuid4

from conftest import IdentityState
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_canonical_mapping_entitlements import (
    _commercialize,
    _grant_membership,
    _set_identity,
)
from test_canonical_mapping_foundation import foundation
from test_field_mapping_suggestions import _organization_template

from app.models.canonical_mapping import (
    FieldMapping,
    MappingRun,
    MappingTemplate,
    MappingTemplateVersion,
    MappingTransformation,
)
from app.models.entities import MembershipRole


def _base(organization_id: object) -> str:
    return f"/api/v1/organizations/{organization_id}/canonical-mapping"


def _counts(db: Session) -> tuple[int, int, int, int, int]:
    return tuple(
        db.scalar(select(func.count()).select_from(model)) or 0
        for model in (
            MappingTemplate,
            MappingTemplateVersion,
            FieldMapping,
            MappingTransformation,
            MappingRun,
        )
    )  # type: ignore[return-value]


def test_template_reads_preserve_visibility_empty_states_and_ordering(
    client: TestClient, db: Session
) -> None:
    organization_id, actor, *_ = foundation(db, "p305a-list")
    foreign_id, foreign_actor, *_ = foundation(db, "p305a-foreign")
    _, _, own_version = _organization_template(db, organization_id, actor, "z-own")
    _, _, foreign_version = _organization_template(db, foreign_id, foreign_actor, "a-foreign")
    own_template = db.get(MappingTemplate, own_version.template_id)
    assert own_template is not None
    versionless = MappingTemplate(
        template_code="versionless",
        name="Versionless",
        scope_type="organization",
        scope_key=f"organization:{organization_id}",
        owner_organization_id=organization_id,
        target_canonical_type_kind=own_template.target_canonical_type_kind,
        target_canonical_type_id=own_template.target_canonical_type_id,
    )
    shared = MappingTemplate(
        template_code="a_shared",
        name="A shared",
        scope_type="shared_core",
        scope_key="shared_core",
        owner_organization_id=None,
        target_canonical_type_kind=own_template.target_canonical_type_kind,
        target_canonical_type_id=own_template.target_canonical_type_id,
    )
    empty_id, *_ = foundation(db, "p305a-empty")
    db.add_all([shared, versionless])
    db.commit()

    response = client.get(f"{_base(organization_id)}/mapping-templates")
    empty = client.get(f"{_base(empty_id)}/mapping-templates")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [
        str(shared.id),
        str(own_template.id),
        str(versionless.id),
    ]
    assert str(foreign_version.template_id) not in {item["id"] for item in response.json()}
    assert empty.status_code == 200
    assert [item["id"] for item in empty.json()] == [str(shared.id)]
    no_versions = client.get(
        f"{_base(organization_id)}/mapping-templates/{versionless.id}/versions"
    )
    assert no_versions.status_code == 200
    assert no_versions.json() == []


def test_template_and_version_reads_fail_closed_and_versions_are_deterministic(
    client: TestClient, db: Session
) -> None:
    organization_id, actor, *_ = foundation(db, "p305a-detail")
    foreign_id, foreign_actor, *_ = foundation(db, "p305a-detail-foreign")
    _, _, version = _organization_template(db, organization_id, actor, "p305a-detail")
    _, _, foreign_version = _organization_template(
        db, foreign_id, foreign_actor, "p305a-detail-foreign"
    )
    second = MappingTemplateVersion(
        template_id=version.template_id,
        semantic_version="2.0.0",
        lifecycle_status="draft",
        content_hash="b" * 64,
        definition_json={"revision": 2},
        created_by_user_id=actor,
    )
    db.add(second)
    db.commit()

    detail = client.get(f"{_base(organization_id)}/mapping-templates/{version.template_id}")
    versions = client.get(
        f"{_base(organization_id)}/mapping-templates/{version.template_id}/versions"
    )
    foreign = client.get(
        f"{_base(organization_id)}/mapping-templates/{foreign_version.template_id}"
    )
    missing = client.get(f"{_base(organization_id)}/mapping-templates/{uuid4()}")
    missing_version = client.get(f"{_base(organization_id)}/mapping-template-versions/{uuid4()}")

    assert detail.status_code == 200
    assert [item["id"] for item in versions.json()] == [str(second.id), str(version.id)]
    assert foreign.status_code == 404
    assert missing.status_code == 404
    assert missing_version.status_code == 404


def test_version_detail_reloads_complete_ordered_configuration_and_run_navigation(
    client: TestClient, db: Session
) -> None:
    organization_id, actor, _, dataset_version_id, *_ = foundation(db, "p305a-reload")
    field, other_field, version = _organization_template(db, organization_id, actor, "p305a-reload")
    origin_memory_version_id = uuid4()
    later = FieldMapping(
        template_version_id=version.id,
        source_field_path="source.later",
        canonical_field_definition_id=other_field.id,
        sequence=20,
        is_required_for_publication=False,
        default_value=None,
    )
    earlier = FieldMapping(
        template_version_id=version.id,
        source_field_path="source.earlier",
        canonical_field_definition_id=field.id,
        sequence=10,
        is_required_for_publication=True,
        default_value="unknown",
        origin_memory_version_id=origin_memory_version_id,
    )
    db.add_all([later, earlier])
    db.flush()
    db.add_all(
        [
            MappingTransformation(
                field_mapping_id=earlier.id,
                sequence=2,
                transformation_type="trim_normalize",
                parameters_json={"mode": "strict"},
            ),
            MappingTransformation(
                field_mapping_id=earlier.id,
                sequence=1,
                transformation_type="type_cast",
                parameters_json={"target": "string"},
            ),
        ]
    )
    run = MappingRun(
        organization_id=organization_id,
        dataset_version_id=dataset_version_id,
        template_version_id=version.id,
        source_schema_id=None,
        status="created",
        idempotency_key="p305a-run",
        request_fingerprint="c" * 64,
        created_by_user_id=actor,
    )
    db.add(run)
    db.commit()
    before = _counts(db)

    run_response = client.get(f"{_base(organization_id)}/mapping-runs/{run.id}")
    detail = client.get(f"{_base(organization_id)}/mapping-template-versions/{version.id}")
    repeated = client.get(f"{_base(organization_id)}/mapping-template-versions/{version.id}")

    assert run_response.status_code == 200
    assert run_response.json()["template_version_id"] == str(version.id)
    assert detail.status_code == 200
    body = detail.json()
    assert body["id"] == str(version.id)
    assert body["template"]["id"] == str(version.template_id)
    assert [item["sequence"] for item in body["field_mappings"]] == [10, 20]
    first = body["field_mappings"][0]
    assert first["default_value"] == "unknown"
    assert first["is_required_for_publication"] is True
    assert first["origin_memory_version_id"] == str(origin_memory_version_id)
    assert [item["sequence"] for item in first["transformations"]] == [1, 2]
    assert body["field_mappings"][1]["transformations"] == []
    assert repeated.json() == body
    assert _counts(db) == before


def test_version_detail_empty_and_foreign_configuration_are_safe(
    client: TestClient, db: Session
) -> None:
    organization_id, actor, *_ = foundation(db, "p305a-empty-version")
    foreign_id, foreign_actor, *_ = foundation(db, "p305a-empty-version-foreign")
    _, _, version = _organization_template(db, organization_id, actor, "p305a-empty-version")
    _, _, foreign_version = _organization_template(
        db, foreign_id, foreign_actor, "p305a-empty-version-foreign"
    )

    empty = client.get(f"{_base(organization_id)}/mapping-template-versions/{version.id}")
    foreign = client.get(f"{_base(organization_id)}/mapping-template-versions/{foreign_version.id}")

    assert empty.status_code == 200
    assert empty.json()["field_mappings"] == []
    assert foreign.status_code == 404


def test_read_contract_requires_entitlement_and_membership(
    client: TestClient, db: Session, identity: IdentityState
) -> None:
    organization_id, actor, *_ = foundation(db, "p305a-auth")
    member = uuid4()
    outsider = uuid4()
    _grant_membership(db, organization_id, member, MembershipRole.VIEWER)
    _commercialize(client, db, organization_id, actor, entitled=False)

    _set_identity(identity, member)
    denied = client.get(f"{_base(organization_id)}/mapping-templates")
    _set_identity(identity, outsider)
    no_membership = client.get(f"{_base(organization_id)}/mapping-templates")

    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "ENTITLEMENT_REQUIRED"
    assert no_membership.status_code == 403
    assert no_membership.json()["detail"] == "Organization access denied"


def test_entitled_viewer_can_read_but_cannot_create_template(
    client: TestClient, db: Session, identity: IdentityState
) -> None:
    organization_id, actor, *_ = foundation(db, "p305a-role")
    viewer = uuid4()
    _grant_membership(db, organization_id, viewer, MembershipRole.VIEWER)
    _commercialize(client, db, organization_id, actor, entitled=True)
    _set_identity(identity, viewer)

    read = client.get(f"{_base(organization_id)}/mapping-templates")
    write = client.post(f"{_base(organization_id)}/mapping-templates", json={})

    assert read.status_code == 200
    assert write.status_code == 403
    assert write.json()["detail"] == "Organization access denied"
