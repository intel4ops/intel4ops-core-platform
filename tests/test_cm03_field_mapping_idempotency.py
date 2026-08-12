from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_canonical_mapping_foundation import foundation

from app.models.canonical_mapping import FieldMapping
from app.schemas.canonical_mapping import (
    CanonicalFieldCreate,
    CanonicalTypeCreate,
    FieldMappingCreate,
    MappingTemplateCreate,
    MappingTemplateVersionCreate,
)
from app.services.canonical_mapping_service import (
    CanonicalMappingServiceError,
    canonical_registry_service,
    mapping_template_service,
)


def _mapping_context(db: Session, slug: str) -> tuple[UUID, UUID, UUID, UUID]:
    organization_id, actor, *_ = foundation(db, slug)
    type_code = slug.replace("-", "_")
    entity_type = canonical_registry_service.create_type(
        db,
        "entity",
        CanonicalTypeCreate(
            type_code=f"{type_code}_entity",
            display_name="CM-03 entity",
            scope_type="organization",
            scope_key=f"organization:{organization_id}",
            owner_organization_id=organization_id,
            identity_strategy_code="exact_identifier",
        ),
    )
    first_field = canonical_registry_service.create_field(
        db,
        CanonicalFieldCreate(
            canonical_type_kind="entity",
            canonical_type_id=entity_type.id,
            field_code="first",
            display_name="First",
            data_type="string",
        ),
        organization_id,
    )
    second_field = canonical_registry_service.create_field(
        db,
        CanonicalFieldCreate(
            canonical_type_kind="entity",
            canonical_type_id=entity_type.id,
            field_code="second",
            display_name="Second",
            data_type="string",
        ),
        organization_id,
    )
    template = mapping_template_service.create(
        db,
        MappingTemplateCreate(
            template_code=f"{type_code}_template",
            name="CM-03 template",
            scope_type="organization",
            scope_key=f"organization:{organization_id}",
            owner_organization_id=organization_id,
            source_system_type="file_upload",
            target_canonical_type_kind="entity",
            target_canonical_type_id=entity_type.id,
        ),
        actor,
        authorized_organization_id=organization_id,
    )
    version = mapping_template_service.create_version(
        db,
        template.id,
        MappingTemplateVersionCreate(semantic_version="1.0.0", definition_json={}),
        actor,
        organization_id,
    )
    return organization_id, version.id, first_field.id, second_field.id


def _payload(field_id: UUID, **changes: object) -> FieldMappingCreate:
    values: dict[str, object] = {
        "source_field_path": "customer.name",
        "canonical_field_definition_id": field_id,
        "sequence": 0,
        "default_value": "unknown",
        "is_required_for_publication": True,
    }
    values.update(changes)
    return FieldMappingCreate.model_validate(values)


def test_first_create_and_repeated_exact_retries_are_stable(db: Session) -> None:
    organization_id, version_id, field_id, _ = _mapping_context(db, "cm03-retry")
    payload = _payload(field_id)

    created = mapping_template_service.add_field_mapping_with_status(
        db, version_id, payload, organization_id
    )
    first_replay = mapping_template_service.add_field_mapping_with_status(
        db, version_id, payload, organization_id
    )
    second_replay = mapping_template_service.add_field_mapping_with_status(
        db, version_id, payload, organization_id
    )

    assert created.created is True
    assert first_replay.created is second_replay.created is False
    assert (
        created.field_mapping.id == first_replay.field_mapping.id == second_replay.field_mapping.id
    )
    assert db.scalar(select(func.count()).select_from(FieldMapping)) == 1
    assert first_replay.field_mapping.origin_memory_version_id is None
    assert db.scalar(select(func.count()).select_from(FieldMapping)) == 1


@pytest.mark.parametrize(
    ("change", "value"),
    [("default_value", "different"), ("is_required_for_publication", False)],
)
def test_same_semantic_identity_with_different_content_conflicts(
    db: Session, change: str, value: object
) -> None:
    organization_id, version_id, field_id, _ = _mapping_context(
        db, f"cm03-{change.replace('_', '-')}"
    )
    mapping_template_service.add_field_mapping(db, version_id, _payload(field_id), organization_id)

    with pytest.raises(CanonicalMappingServiceError) as caught:
        mapping_template_service.add_field_mapping(
            db, version_id, _payload(field_id, **{change: value}), organization_id
        )

    assert caught.value.status == 409
    assert caught.value.code == "FIELD_MAPPING_CONFLICT"


def test_different_target_with_occupied_sequence_is_sequence_conflict(db: Session) -> None:
    organization_id, version_id, first_field_id, second_field_id = _mapping_context(
        db, "cm03-sequence"
    )
    mapping_template_service.add_field_mapping(
        db, version_id, _payload(first_field_id), organization_id
    )

    with pytest.raises(CanonicalMappingServiceError) as caught:
        mapping_template_service.add_field_mapping(
            db,
            version_id,
            _payload(second_field_id, source_field_path="customer.alias"),
            organization_id,
        )

    assert caught.value.status == 409
    assert caught.value.code == "FIELD_MAPPING_SEQUENCE_CONFLICT"
    assert db.scalar(select(func.count()).select_from(FieldMapping)) == 1


def test_different_target_with_free_sequence_is_independent(db: Session) -> None:
    organization_id, version_id, first_field_id, second_field_id = _mapping_context(
        db, "cm03-independent"
    )
    first = mapping_template_service.add_field_mapping(
        db, version_id, _payload(first_field_id), organization_id
    )
    second = mapping_template_service.add_field_mapping(
        db,
        version_id,
        _payload(second_field_id, source_field_path="customer.alias", sequence=1),
        organization_id,
    )

    assert first.id != second.id
    assert db.scalar(select(func.count()).select_from(FieldMapping)) == 2


def test_origin_lineage_is_immutable_replay_content() -> None:
    field_id = uuid4()
    origin_id = uuid4()
    existing = FieldMapping(
        template_version_id=uuid4(),
        source_field_path="customer.name",
        canonical_field_definition_id=field_id,
        sequence=0,
        default_value=None,
        is_required_for_publication=False,
        origin_memory_version_id=origin_id,
    )

    assert mapping_template_service._field_mapping_content_matches(
        existing,
        _payload(
            field_id,
            default_value=None,
            is_required_for_publication=False,
            origin_memory_version_id=origin_id,
        ),
    )
    assert not mapping_template_service._field_mapping_content_matches(
        existing,
        _payload(
            field_id,
            default_value=None,
            is_required_for_publication=False,
            origin_memory_version_id=None,
        ),
    )
    assert existing.origin_memory_version_id == origin_id


def test_foreign_tenant_cannot_reconcile_mapping(db: Session) -> None:
    organization_a, _, _, _ = _mapping_context(db, "cm03-tenant-a")
    organization_b, version_b, field_b, _ = _mapping_context(db, "cm03-tenant-b")
    mapping_template_service.add_field_mapping(db, version_b, _payload(field_b), organization_b)

    with pytest.raises(CanonicalMappingServiceError) as caught:
        mapping_template_service.add_field_mapping(db, version_b, _payload(field_b), organization_a)

    assert caught.value.code == "MAPPING_TEMPLATE_NOT_FOUND"
    assert db.scalar(select(func.count()).select_from(FieldMapping)) == 1


def test_unrelated_integrity_error_is_not_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    db = Mock(spec=Session)
    db.commit.side_effect = IntegrityError("insert", {}, RuntimeError("unrelated"))
    db.scalar.side_effect = [None, None]
    version = Mock(id=uuid4(), template_id=uuid4(), lifecycle_status="draft")
    field = Mock(canonical_type_kind="entity", canonical_type_id=uuid4())
    template = Mock(
        target_canonical_type_kind="entity", target_canonical_type_id=field.canonical_type_id
    )
    monkeypatch.setattr(mapping_template_service, "require_version", Mock(return_value=version))
    monkeypatch.setattr(canonical_registry_service, "require_field", Mock(return_value=field))
    db.get.return_value = template

    with pytest.raises(IntegrityError):
        mapping_template_service.add_field_mapping(db, version.id, _payload(uuid4()), uuid4())

    db.rollback.assert_called_once_with()
