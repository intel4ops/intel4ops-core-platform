from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

import pytest
from conftest import IdentityState
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from test_canonical_mapping_foundation import foundation

from app.models.canonical_mapping import (
    CanonicalFieldDefinition,
    FieldMapping,
    MappingTemplateVersion,
    SourceSchema,
)
from app.models.entities import MembershipRole, MembershipStatus, OrganizationMembership
from app.models.ingestion import Dataset
from app.models.operational_memory import (
    OperationalMemoryItem,
    OperationalMemoryReuseEvent,
    OperationalMemoryVersion,
)
from app.models.source_system import SourceSystem
from app.models.trust import TrustAssessment
from app.schemas.canonical_mapping import (
    CanonicalFieldCreate,
    CanonicalTypeCreate,
    FieldMappingCreate,
    MappingTemplateCreate,
    MappingTemplateVersionCreate,
    SourceFieldCreate,
    SourceSchemaDiscover,
)
from app.schemas.operational_memory import (
    MemoryCandidateCreate,
    MemoryContext,
    MemoryDecisionRequest,
    MemoryProvenance,
)
from app.services.canonical_mapping_service import (
    CanonicalMappingServiceError,
    canonical_registry_service,
    field_mapping_suggestion_service,
    mapping_template_service,
    schema_discovery_service,
)
from app.services.operational_memory_service import operational_memory_service

FIELD_PATH = "equipment_no"


@pytest.fixture(autouse=True)
def cleanup_memory_rows(db: Session) -> Iterator[None]:
    # SQLite cannot resolve OperationalMemoryVersion's self-referential
    # supersedes FK together with OperationalMemoryReuseEvent's reference to
    # it during Base.metadata.drop_all(); pre-clear before teardown.
    yield
    db.rollback()
    db.execute(delete(OperationalMemoryReuseEvent))
    version_ids = list(
        db.scalars(
            select(OperationalMemoryVersion.id).order_by(
                OperationalMemoryVersion.version_number.desc()
            )
        )
    )
    for version_id in version_ids:
        db.execute(
            delete(OperationalMemoryVersion).where(OperationalMemoryVersion.id == version_id)
        )
    db.execute(delete(OperationalMemoryItem))
    db.commit()


def _organization_template(
    db: Session, organization_id: UUID, actor: UUID, slug: str
) -> tuple[CanonicalFieldDefinition, CanonicalFieldDefinition, MappingTemplateVersion]:
    code = slug.replace("-", "_")
    entity_type = canonical_registry_service.create_type(
        db,
        "entity",
        CanonicalTypeCreate(
            type_code=f"equip_{code}",
            display_name="Equipment",
            scope_type="organization",
            scope_key=f"organization:{organization_id}",
            owner_organization_id=organization_id,
            identity_strategy_code="exact_identifier",
        ),
    )
    field = canonical_registry_service.create_field(
        db,
        CanonicalFieldCreate(
            canonical_type_kind="entity",
            canonical_type_id=entity_type.id,
            field_code="equipment_id",
            display_name="Equipment ID",
            data_type="string",
            is_required=True,
        ),
        organization_id,
    )
    other_field = canonical_registry_service.create_field(
        db,
        CanonicalFieldCreate(
            canonical_type_kind="entity",
            canonical_type_id=entity_type.id,
            field_code="asset_number",
            display_name="Asset Number",
            data_type="string",
            is_required=False,
        ),
        organization_id,
    )
    template = mapping_template_service.create(
        db,
        MappingTemplateCreate(
            template_code=f"equip_{code}",
            name="Equipment",
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
    return field, other_field, version


def _shared_template_version(
    db: Session, actor: UUID, slug: str
) -> tuple[CanonicalFieldDefinition, MappingTemplateVersion]:
    code = slug.replace("-", "_")
    entity_type = canonical_registry_service.create_type(
        db,
        "entity",
        CanonicalTypeCreate(
            type_code=f"shared_{code}",
            display_name="Shared Equipment",
            scope_type="shared_core",
            scope_key=f"shared:{slug}",
            identity_strategy_code="exact_identifier",
        ),
    )
    field = canonical_registry_service.create_field(
        db,
        CanonicalFieldCreate(
            canonical_type_kind="entity",
            canonical_type_id=entity_type.id,
            field_code="equipment_id",
            display_name="Equipment ID",
            data_type="string",
            is_required=True,
        ),
        None,
    )
    template = mapping_template_service.create(
        db,
        MappingTemplateCreate(
            template_code=f"shared_{code}",
            name="Shared Equipment",
            scope_type="shared_core",
            scope_key=f"shared:{slug}",
            source_system_type="file_upload",
            target_canonical_type_kind="entity",
            target_canonical_type_id=entity_type.id,
        ),
        actor,
    )
    version = mapping_template_service.create_version(
        db,
        template.id,
        MappingTemplateVersionCreate(semantic_version="1.0.0", definition_json={}),
        actor,
        None,
    )
    return field, version


def _schema_with_field(
    db: Session,
    organization_id: UUID,
    dataset_id: UUID,
    dataset_version_id: UUID,
    slug: str,
    field_path: str = FIELD_PATH,
    inferred_data_type: str = "string",
) -> SourceSchema:
    return schema_discovery_service.discover(
        db,
        organization_id,
        SourceSchemaDiscover(
            dataset_id=dataset_id,
            dataset_version_id=dataset_version_id,
            schema_fingerprint=f"{slug}-fingerprint".ljust(32, "0"),
            fields=[
                SourceFieldCreate(field_path=field_path, inferred_data_type=inferred_data_type)
            ],
        ),
    )


def _foundation_context(db: Session, dataset_id: UUID) -> tuple[str | None, str | None]:
    dataset = db.get(Dataset, dataset_id)
    assert dataset is not None
    source_system = db.get(SourceSystem, dataset.source_system_id)
    family = source_system.system_type if source_system is not None else None
    return family, dataset.domain


def _memory_payload(
    schema: SourceSchema, field: CanonicalFieldDefinition, field_path: str
) -> dict[str, object]:
    return {
        "source_field_path": field_path,
        "source_field_type": "string",
        "canonical_type_kind": "entity",
        "canonical_type_id": str(field.canonical_type_id),
        "canonical_field_definition_id": str(field.id),
        "canonical_field_code": field.field_code,
        "schema_fingerprint": schema.schema_fingerprint,
    }


def _record(
    db: Session,
    organization_id: UUID,
    schema: SourceSchema,
    field: CanonicalFieldDefinition,
    key: str,
    *,
    field_path: str = FIELD_PATH,
    source_system_family: str | None = None,
    canonical_domain: str | None = None,
) -> OperationalMemoryItem:
    candidate = MemoryCandidateCreate(
        idempotency_key=f"{key}-candidate",
        category="FIELD_MAPPING",
        subject_kind="SOURCE_FIELD",
        subject=field_path,
        source_system_family=source_system_family,
        canonical_domain=canonical_domain,
        context=MemoryContext(schema_fingerprint=schema.schema_fingerprint),
        value_payload=_memory_payload(schema, field, field_path),
        provenance=MemoryProvenance(
            source_schema_id=schema.id, canonical_field_definition_ids=[field.id]
        ),
        source_fingerprint="a" * 64,
    )
    item, _ = operational_memory_service.record_candidate(
        db, organization_id, candidate, None, "system"
    )
    return item


def _confirm(
    db: Session, organization_id: UUID, actor: UUID, item: OperationalMemoryItem, key: str
) -> OperationalMemoryVersion:
    _, version = operational_memory_service.decide(
        db,
        organization_id,
        item.id,
        MemoryDecisionRequest(
            idempotency_key=f"{key}-confirm",
            expected_current_version=item.current_version_number,
            action="CONFIRM",
        ),
        actor,
        "organization_admin",
    )
    return version


def _confirmed_memory(
    db: Session,
    organization_id: UUID,
    actor: UUID,
    schema: SourceSchema,
    field: CanonicalFieldDefinition,
    key: str,
    *,
    field_path: str = FIELD_PATH,
    source_system_family: str | None = None,
    canonical_domain: str | None = None,
) -> OperationalMemoryVersion:
    item = _record(
        db,
        organization_id,
        schema,
        field,
        key,
        field_path=field_path,
        source_system_family=source_system_family,
        canonical_domain=canonical_domain,
    )
    return _confirm(db, organization_id, actor, item, key)


# --- suggestions: eligibility -------------------------------------------------


def test_confirmed_exact_context_memory_suggested(db: Session) -> None:
    org, actor, dataset_id, version_id, _, _ = foundation(db, "sugg-confirmed")
    field, _, _ = _organization_template(db, org, actor, "sugg-confirmed")
    schema = _schema_with_field(db, org, dataset_id, version_id, "sugg-confirmed")
    family, domain = _foundation_context(db, dataset_id)
    memory_version = _confirmed_memory(
        db,
        org,
        actor,
        schema,
        field,
        "sugg-confirmed",
        source_system_family=family,
        canonical_domain=domain,
    )

    result = field_mapping_suggestion_service.suggest(db, org, schema.id)
    assert len(result.suggestions) == 1
    suggestion = result.suggestions[0]
    assert suggestion.evaluated is True
    assert suggestion.suggested_canonical_field_definition_id == field.id
    assert suggestion.suggested_canonical_field_code == field.field_code
    assert suggestion.confidence_status == "CONFIRMED"
    assert suggestion.memory_version_id == memory_version.id
    assert "context_signature" in suggestion.matched_context_dimensions


def test_corrected_exact_context_memory_suggested(db: Session) -> None:
    org, actor, dataset_id, version_id, _, _ = foundation(db, "sugg-corrected")
    field, other_field, _ = _organization_template(db, org, actor, "sugg-corrected")
    schema = _schema_with_field(db, org, dataset_id, version_id, "sugg-corrected")
    family, domain = _foundation_context(db, dataset_id)
    item = _record(
        db,
        org,
        schema,
        field,
        "sugg-corrected",
        source_system_family=family,
        canonical_domain=domain,
    )
    confirmed = _confirm(db, org, actor, item, "sugg-corrected")
    db.refresh(item)
    _, corrected = operational_memory_service.decide(
        db,
        org,
        item.id,
        MemoryDecisionRequest(
            idempotency_key="sugg-corrected-correct",
            expected_current_version=item.current_version_number,
            action="CORRECT",
            corrected_payload=_memory_payload(schema, other_field, FIELD_PATH),
        ),
        actor,
        "organization_admin",
    )
    assert corrected.id != confirmed.id

    result = field_mapping_suggestion_service.suggest(db, org, schema.id)
    assert len(result.suggestions) == 1
    suggestion = result.suggestions[0]
    assert suggestion.confidence_status == "CORRECTED"
    assert suggestion.suggested_canonical_field_definition_id == other_field.id
    assert suggestion.memory_version_id == corrected.id


def test_observed_memory_not_suggested(db: Session) -> None:
    org, actor, dataset_id, version_id, _, _ = foundation(db, "sugg-observed")
    field, _, _ = _organization_template(db, org, actor, "sugg-observed")
    schema = _schema_with_field(db, org, dataset_id, version_id, "sugg-observed")
    _record(db, org, schema, field, "sugg-observed")

    result = field_mapping_suggestion_service.suggest(db, org, schema.id)
    assert len(result.suggestions) == 1
    assert result.suggestions[0].suggested_canonical_field_definition_id is None
    assert result.suggestions[0].evaluated is True


def test_rejected_memory_not_suggested(db: Session) -> None:
    org, actor, dataset_id, version_id, _, _ = foundation(db, "sugg-rejected")
    field, _, _ = _organization_template(db, org, actor, "sugg-rejected")
    schema = _schema_with_field(db, org, dataset_id, version_id, "sugg-rejected")
    item = _record(db, org, schema, field, "sugg-rejected")
    operational_memory_service.decide(
        db,
        org,
        item.id,
        MemoryDecisionRequest(
            idempotency_key="sugg-rejected-reject",
            expected_current_version=item.current_version_number,
            action="REJECT",
        ),
        actor,
        "organization_admin",
    )

    result = field_mapping_suggestion_service.suggest(db, org, schema.id)
    assert result.suggestions[0].suggested_canonical_field_definition_id is None


def test_ambiguous_memory_not_suggested(db: Session) -> None:
    org, actor, dataset_id, version_id, _, _ = foundation(db, "sugg-ambiguous")
    field, other_field, _ = _organization_template(db, org, actor, "sugg-ambiguous")
    schema = _schema_with_field(db, org, dataset_id, version_id, "sugg-ambiguous")
    candidate = MemoryCandidateCreate(
        idempotency_key="sugg-ambiguous-1",
        category="FIELD_MAPPING",
        subject_kind="SOURCE_FIELD",
        subject=FIELD_PATH,
        context=MemoryContext(schema_fingerprint=schema.schema_fingerprint),
        value_payload=_memory_payload(schema, field, FIELD_PATH),
        provenance=MemoryProvenance(
            source_schema_id=schema.id, canonical_field_definition_ids=[field.id]
        ),
        source_fingerprint="a" * 64,
    )
    item, _ = operational_memory_service.record_candidate(db, org, candidate, None, "system")
    conflicting = candidate.model_copy(
        update={
            "idempotency_key": "sugg-ambiguous-2",
            "value_payload": _memory_payload(schema, other_field, FIELD_PATH),
        }
    )
    operational_memory_service.record_candidate(db, org, conflicting, None, "system")
    db.refresh(item)
    assert item.current_status == "AMBIGUOUS"

    result = field_mapping_suggestion_service.suggest(db, org, schema.id)
    assert result.suggestions[0].suggested_canonical_field_definition_id is None


def test_deprecated_memory_not_suggested(db: Session) -> None:
    org, actor, dataset_id, version_id, _, _ = foundation(db, "sugg-deprecated")
    field, _, _ = _organization_template(db, org, actor, "sugg-deprecated")
    schema = _schema_with_field(db, org, dataset_id, version_id, "sugg-deprecated")
    item = _record(db, org, schema, field, "sugg-deprecated")
    _confirm(db, org, actor, item, "sugg-deprecated")
    db.refresh(item)
    operational_memory_service.decide(
        db,
        org,
        item.id,
        MemoryDecisionRequest(
            idempotency_key="sugg-deprecated-deprecate",
            expected_current_version=item.current_version_number,
            action="DEPRECATE",
        ),
        actor,
        "organization_admin",
    )

    result = field_mapping_suggestion_service.suggest(db, org, schema.id)
    assert result.suggestions[0].suggested_canonical_field_definition_id is None


def test_stale_memory_not_suggested(db: Session) -> None:
    org, actor, dataset_id, version_id, _, _ = foundation(db, "sugg-stale")
    field, _, _ = _organization_template(db, org, actor, "sugg-stale")
    schema = _schema_with_field(db, org, dataset_id, version_id, "sugg-stale")
    _confirmed_memory(db, org, actor, schema, field, "sugg-stale")

    schema.status = "changed"
    db.commit()

    result = field_mapping_suggestion_service.suggest(db, org, schema.id)
    assert result.suggestions[0].suggested_canonical_field_definition_id is None


def test_wrong_context_not_surfaced(db: Session) -> None:
    org, actor, dataset_id, version_id, _, _ = foundation(db, "sugg-wrong-ctx")
    field, _, _ = _organization_template(db, org, actor, "sugg-wrong-ctx")
    target_schema = _schema_with_field(db, org, dataset_id, version_id, "sugg-wrong-ctx-target")
    other_schema = _schema_with_field(db, org, dataset_id, version_id, "sugg-wrong-ctx-other")
    _confirmed_memory(db, org, actor, other_schema, field, "sugg-wrong-ctx")

    result = field_mapping_suggestion_service.suggest(db, org, target_schema.id)
    assert result.suggestions[0].suggested_canonical_field_definition_id is None
    assert result.suggestions[0].evaluated is True


def test_exact_context_wins_over_wrong_context(db: Session) -> None:
    org, actor, dataset_id, version_id, _, _ = foundation(db, "sugg-wins")
    field, other_field, _ = _organization_template(db, org, actor, "sugg-wins")
    target_schema = _schema_with_field(db, org, dataset_id, version_id, "sugg-wins-target")
    other_schema = _schema_with_field(db, org, dataset_id, version_id, "sugg-wins-other")
    family, domain = _foundation_context(db, dataset_id)
    _confirmed_memory(db, org, actor, other_schema, other_field, "sugg-wins-wrong")
    matching_version = _confirmed_memory(
        db,
        org,
        actor,
        target_schema,
        field,
        "sugg-wins-right",
        source_system_family=family,
        canonical_domain=domain,
    )

    result = field_mapping_suggestion_service.suggest(db, org, target_schema.id)
    assert len(result.suggestions) == 1
    assert result.suggestions[0].memory_version_id == matching_version.id
    assert result.suggestions[0].suggested_canonical_field_definition_id == field.id


def test_max_one_suggestion_per_field(db: Session) -> None:
    org, actor, dataset_id, version_id, _, _ = foundation(db, "sugg-max-one")
    field, _, _ = _organization_template(db, org, actor, "sugg-max-one")
    schema = _schema_with_field(db, org, dataset_id, version_id, "sugg-max-one")
    _confirmed_memory(db, org, actor, schema, field, "sugg-max-one")

    result = field_mapping_suggestion_service.suggest(db, org, schema.id)
    assert len(result.suggestions) == 1
    non_null = [
        s for s in result.suggestions if s.suggested_canonical_field_definition_id is not None
    ]
    assert len(non_null) <= 1


def test_deterministic_repeated_result(db: Session) -> None:
    org, actor, dataset_id, version_id, _, _ = foundation(db, "sugg-deterministic")
    field, _, _ = _organization_template(db, org, actor, "sugg-deterministic")
    schema = _schema_with_field(db, org, dataset_id, version_id, "sugg-deterministic")
    _confirmed_memory(db, org, actor, schema, field, "sugg-deterministic")

    first = field_mapping_suggestion_service.suggest(db, org, schema.id)
    second = field_mapping_suggestion_service.suggest(db, org, schema.id)
    assert first.model_dump() == second.model_dump()


def test_tenant_b_memory_not_surfaced_to_tenant_a(db: Session) -> None:
    org_a, actor_a, dataset_a, version_a, _, _ = foundation(db, "sugg-tenant-a")
    org_b, actor_b, dataset_b, version_b, _, _ = foundation(db, "sugg-tenant-b")
    field_a, _, _ = _organization_template(db, org_a, actor_a, "sugg-tenant-a")
    field_b, _, _ = _organization_template(db, org_b, actor_b, "sugg-tenant-b")
    schema_a = _schema_with_field(db, org_a, dataset_a, version_a, "sugg-tenant-a")
    schema_b = _schema_with_field(db, org_b, dataset_b, version_b, "sugg-tenant-b")
    _confirmed_memory(db, org_b, actor_b, schema_b, field_b, "sugg-tenant-b")

    result = field_mapping_suggestion_service.suggest(db, org_a, schema_a.id)
    assert result.suggestions[0].suggested_canonical_field_definition_id is None


def test_foreign_source_schema_rejected(db: Session) -> None:
    org_a, actor_a, dataset_a, version_a, _, _ = foundation(db, "sugg-foreign-schema-a")
    org_b, actor_b, dataset_b, version_b, _, _ = foundation(db, "sugg-foreign-schema-b")
    schema_b = _schema_with_field(db, org_b, dataset_b, version_b, "sugg-foreign-schema-b")

    with pytest.raises(CanonicalMappingServiceError) as exc:
        field_mapping_suggestion_service.suggest(db, org_a, schema_b.id)
    assert exc.value.code == "SOURCE_SCHEMA_NOT_FOUND"


def test_suggestions_create_zero_field_mappings(db: Session) -> None:
    org, actor, dataset_id, version_id, _, _ = foundation(db, "sugg-zero-writes")
    field, _, _ = _organization_template(db, org, actor, "sugg-zero-writes")
    schema = _schema_with_field(db, org, dataset_id, version_id, "sugg-zero-writes")
    _confirmed_memory(db, org, actor, schema, field, "sugg-zero-writes")

    before = db.scalar(select(func.count()).select_from(FieldMapping))
    field_mapping_suggestion_service.suggest(db, org, schema.id)
    after = db.scalar(select(func.count()).select_from(FieldMapping))
    assert before == after


def test_suggestions_do_not_mutate_trust(db: Session) -> None:
    org, actor, dataset_id, version_id, _, _ = foundation(db, "sugg-trust")
    field, _, _ = _organization_template(db, org, actor, "sugg-trust")
    schema = _schema_with_field(db, org, dataset_id, version_id, "sugg-trust")
    _confirmed_memory(db, org, actor, schema, field, "sugg-trust")

    before = db.scalar(
        select(func.count())
        .select_from(TrustAssessment)
        .where(TrustAssessment.organization_id == org)
    )
    field_mapping_suggestion_service.suggest(db, org, schema.id)
    after = db.scalar(
        select(func.count())
        .select_from(TrustAssessment)
        .where(TrustAssessment.organization_id == org)
    )
    assert before == after


def test_suggestions_do_not_change_memory_status(db: Session) -> None:
    org, actor, dataset_id, version_id, _, _ = foundation(db, "sugg-no-auto")
    field, _, _ = _organization_template(db, org, actor, "sugg-no-auto")
    schema = _schema_with_field(db, org, dataset_id, version_id, "sugg-no-auto")
    item = _record(db, org, schema, field, "sugg-no-auto")

    field_mapping_suggestion_service.suggest(db, org, schema.id)
    db.refresh(item)
    assert item.current_status == "OBSERVED"
    assert item.current_version_number == 1


# --- lineage -------------------------------------------------------------------


def test_valid_organization_scoped_lineage_accepted(db: Session) -> None:
    org, actor, dataset_id, version_id, _, _ = foundation(db, "lineage-valid")
    field, _, template_version = _organization_template(db, org, actor, "lineage-valid")
    schema = _schema_with_field(db, org, dataset_id, version_id, "lineage-valid")
    memory_version = _confirmed_memory(db, org, actor, schema, field, "lineage-valid")

    created = mapping_template_service.add_field_mapping(
        db,
        template_version.id,
        FieldMappingCreate(
            source_field_path=FIELD_PATH,
            canonical_field_definition_id=field.id,
            origin_memory_version_id=memory_version.id,
        ),
        org,
    )
    assert created.origin_memory_version_id == memory_version.id


def test_foreign_memory_version_rejected(db: Session) -> None:
    org_a, actor_a, dataset_a, version_a, _, _ = foundation(db, "lineage-foreign-a")
    org_b, actor_b, dataset_b, version_b, _, _ = foundation(db, "lineage-foreign-b")
    field_a, _, template_version_a = _organization_template(db, org_a, actor_a, "lineage-foreign-a")
    field_b, _, _ = _organization_template(db, org_b, actor_b, "lineage-foreign-b")
    schema_b = _schema_with_field(db, org_b, dataset_b, version_b, "lineage-foreign-b")
    foreign_version = _confirmed_memory(db, org_b, actor_b, schema_b, field_b, "lineage-foreign-b")

    with pytest.raises(CanonicalMappingServiceError) as exc:
        mapping_template_service.add_field_mapping(
            db,
            template_version_a.id,
            FieldMappingCreate(
                source_field_path=FIELD_PATH,
                canonical_field_definition_id=field_a.id,
                origin_memory_version_id=foreign_version.id,
            ),
            org_a,
        )
    assert exc.value.code == "ORIGIN_MEMORY_VERSION_NOT_FOUND"


def test_observed_memory_version_lineage_rejected(db: Session) -> None:
    org, actor, dataset_id, version_id, _, _ = foundation(db, "lineage-observed")
    field, _, template_version = _organization_template(db, org, actor, "lineage-observed")
    schema = _schema_with_field(db, org, dataset_id, version_id, "lineage-observed")
    item = _record(db, org, schema, field, "lineage-observed")
    observed_version_id = item.current_version_number

    version_row = db.scalar(
        select(OperationalMemoryVersion).where(OperationalMemoryVersion.memory_id == item.id)
    )
    assert version_row is not None
    assert observed_version_id == 1

    with pytest.raises(CanonicalMappingServiceError) as exc:
        mapping_template_service.add_field_mapping(
            db,
            template_version.id,
            FieldMappingCreate(
                source_field_path=FIELD_PATH,
                canonical_field_definition_id=field.id,
                origin_memory_version_id=version_row.id,
            ),
            org,
        )
    assert exc.value.code == "ORIGIN_MEMORY_NOT_REUSABLE"


def test_rejected_memory_lineage_rejected(db: Session) -> None:
    org, actor, dataset_id, version_id, _, _ = foundation(db, "lineage-rejected")
    field, _, template_version = _organization_template(db, org, actor, "lineage-rejected")
    schema = _schema_with_field(db, org, dataset_id, version_id, "lineage-rejected")
    item = _record(db, org, schema, field, "lineage-rejected")
    _, rejected_version = operational_memory_service.decide(
        db,
        org,
        item.id,
        MemoryDecisionRequest(
            idempotency_key="lineage-rejected-reject",
            expected_current_version=item.current_version_number,
            action="REJECT",
        ),
        actor,
        "organization_admin",
    )

    with pytest.raises(CanonicalMappingServiceError) as exc:
        mapping_template_service.add_field_mapping(
            db,
            template_version.id,
            FieldMappingCreate(
                source_field_path=FIELD_PATH,
                canonical_field_definition_id=field.id,
                origin_memory_version_id=rejected_version.id,
            ),
            org,
        )
    assert exc.value.code == "ORIGIN_MEMORY_NOT_REUSABLE"


def test_stale_browser_lineage_rejected_after_memory_state_changes(db: Session) -> None:
    org, actor, dataset_id, version_id, _, _ = foundation(db, "lineage-stale-replay")
    field, _, template_version = _organization_template(db, org, actor, "lineage-stale-replay")
    schema = _schema_with_field(db, org, dataset_id, version_id, "lineage-stale-replay")
    item = _record(db, org, schema, field, "lineage-stale-replay")
    confirmed_version = _confirm(db, org, actor, item, "lineage-stale-replay")
    db.refresh(item)

    # A CONFIRMED item can only transition to CORRECTED/DEPRECATED, never
    # directly back to REJECTED; DEPRECATE is the reachable "no longer
    # reusable" transition used here to simulate the replay scenario.
    operational_memory_service.decide(
        db,
        org,
        item.id,
        MemoryDecisionRequest(
            idempotency_key="lineage-stale-replay-deprecate",
            expected_current_version=item.current_version_number,
            action="DEPRECATE",
        ),
        actor,
        "organization_admin",
    )

    with pytest.raises(CanonicalMappingServiceError) as exc:
        mapping_template_service.add_field_mapping(
            db,
            template_version.id,
            FieldMappingCreate(
                source_field_path=FIELD_PATH,
                canonical_field_definition_id=field.id,
                origin_memory_version_id=confirmed_version.id,
            ),
            org,
        )
    assert exc.value.code == "ORIGIN_MEMORY_NOT_REUSABLE"


def test_non_organization_template_lineage_rejected(db: Session) -> None:
    org, actor, dataset_id, version_id, _, _ = foundation(db, "lineage-shared")
    field, _, _ = _organization_template(db, org, actor, "lineage-shared")
    schema = _schema_with_field(db, org, dataset_id, version_id, "lineage-shared")
    memory_version = _confirmed_memory(db, org, actor, schema, field, "lineage-shared")
    shared_field, shared_version = _shared_template_version(db, actor, "lineage-shared")

    with pytest.raises(CanonicalMappingServiceError) as exc:
        mapping_template_service.add_field_mapping(
            db,
            shared_version.id,
            FieldMappingCreate(
                source_field_path=FIELD_PATH,
                canonical_field_definition_id=shared_field.id,
                origin_memory_version_id=memory_version.id,
            ),
            org,
        )
    assert exc.value.code == "ORIGIN_LINEAGE_TEMPLATE_SCOPE_INVALID"


def test_lineage_survives_later_memory_correction(db: Session) -> None:
    org, actor, dataset_id, version_id, _, _ = foundation(db, "lineage-later-correction")
    field, other_field, template_version = _organization_template(
        db, org, actor, "lineage-later-correction"
    )
    schema = _schema_with_field(db, org, dataset_id, version_id, "lineage-later-correction")
    item = _record(db, org, schema, field, "lineage-later-correction")
    original_version = _confirm(db, org, actor, item, "lineage-later-correction")
    db.refresh(item)

    created = mapping_template_service.add_field_mapping(
        db,
        template_version.id,
        FieldMappingCreate(
            source_field_path=FIELD_PATH,
            canonical_field_definition_id=field.id,
            origin_memory_version_id=original_version.id,
        ),
        org,
    )
    assert created.origin_memory_version_id == original_version.id

    operational_memory_service.decide(
        db,
        org,
        item.id,
        MemoryDecisionRequest(
            idempotency_key="lineage-later-correction-correct",
            expected_current_version=item.current_version_number,
            action="CORRECT",
            corrected_payload=_memory_payload(schema, other_field, FIELD_PATH),
        ),
        actor,
        "organization_admin",
    )

    db.refresh(created)
    assert created.origin_memory_version_id == original_version.id
    resolvable = db.get(OperationalMemoryVersion, original_version.id)
    assert resolvable is not None
    assert resolvable.value_payload["canonical_field_definition_id"] == str(field.id)


def test_field_mapping_with_no_lineage_remains_valid(db: Session) -> None:
    org, actor, dataset_id, version_id, _, _ = foundation(db, "lineage-none")
    field, _, template_version = _organization_template(db, org, actor, "lineage-none")

    created = mapping_template_service.add_field_mapping(
        db,
        template_version.id,
        FieldMappingCreate(source_field_path=FIELD_PATH, canonical_field_definition_id=field.id),
        org,
    )
    assert created.origin_memory_version_id is None


def test_lineage_write_does_not_auto_confirm_or_correct_or_reject(db: Session) -> None:
    org, actor, dataset_id, version_id, _, _ = foundation(db, "lineage-no-auto-decision")
    field, _, template_version = _organization_template(db, org, actor, "lineage-no-auto-decision")
    schema = _schema_with_field(db, org, dataset_id, version_id, "lineage-no-auto-decision")
    memory_version = _confirmed_memory(db, org, actor, schema, field, "lineage-no-auto-decision")
    item = db.get(OperationalMemoryItem, memory_version.memory_id)
    assert item is not None
    version_number_before = item.current_version_number

    mapping_template_service.add_field_mapping(
        db,
        template_version.id,
        FieldMappingCreate(
            source_field_path=FIELD_PATH,
            canonical_field_definition_id=field.id,
            origin_memory_version_id=memory_version.id,
        ),
        org,
    )

    db.refresh(item)
    assert item.current_status == "CONFIRMED"
    assert item.current_version_number == version_number_before


# --- authorization (HTTP) -------------------------------------------------------


def _grant(db: Session, organization_id: UUID, user_id: UUID, role: MembershipRole) -> None:
    db.add(
        OrganizationMembership(
            organization_id=organization_id,
            user_id=user_id,
            role=role.value,
            status=MembershipStatus.ACTIVE.value,
        )
    )
    db.commit()


def test_viewer_may_read_suggestions_but_cannot_add_field_mapping(
    client: TestClient, db: Session, identity: IdentityState
) -> None:
    org, actor, dataset_id, version_id, _, _ = foundation(db, "authz-viewer")
    field, _, template_version = _organization_template(db, org, actor, "authz-viewer")
    schema = _schema_with_field(db, org, dataset_id, version_id, "authz-viewer")

    identity.is_platform_admin = False
    assert identity.user_id is not None
    _grant(db, org, identity.user_id, MembershipRole.VIEWER)

    read = client.get(
        f"/api/v1/organizations/{org}/canonical-mapping/source-schemas/{schema.id}/field-mapping-suggestions"
    )
    assert read.status_code == 200

    write = client.post(
        f"/api/v1/organizations/{org}/canonical-mapping/mapping-template-versions/{template_version.id}/field-mappings",
        json={
            "source_field_path": FIELD_PATH,
            "canonical_field_definition_id": str(field.id),
        },
    )
    assert write.status_code == 403


def test_authorized_author_may_add_field_mapping(
    client: TestClient, db: Session, identity: IdentityState
) -> None:
    org, actor, dataset_id, version_id, _, _ = foundation(db, "authz-author")
    field, _, template_version = _organization_template(db, org, actor, "authz-author")

    identity.is_platform_admin = False
    assert identity.user_id is not None
    _grant(db, org, identity.user_id, MembershipRole.ANALYST)

    write = client.post(
        f"/api/v1/organizations/{org}/canonical-mapping/mapping-template-versions/{template_version.id}/field-mappings",
        json={
            "source_field_path": FIELD_PATH,
            "canonical_field_definition_id": str(field.id),
        },
    )
    assert write.status_code == 201
    assert write.json()["origin_memory_version_id"] is None
