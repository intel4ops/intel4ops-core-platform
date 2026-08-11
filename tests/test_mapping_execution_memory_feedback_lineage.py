from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from test_canonical_mapping_foundation import foundation

from app.models.canonical_mapping import (
    CanonicalFieldDefinition,
    FieldMapping,
    MappingRun,
    MappingRunStatus,
    MappingTemplateVersion,
    SourceSchema,
)
from app.models.operational_memory import (
    OperationalMemoryItem,
    OperationalMemoryReuseEvent,
    OperationalMemoryVersion,
)
from app.models.trust import TrustAssessment
from app.schemas.canonical_mapping import (
    CanonicalFieldCreate,
    CanonicalTypeCreate,
    FieldMappingCreate,
    MappingInputRecord,
    MappingRunCreate,
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
    canonical_registry_service,
    mapping_execution_service,
    mapping_template_service,
    schema_discovery_service,
)
from app.services.operational_memory_service import operational_memory_service

FIELD_PATH = "equipment_no"


@pytest.fixture(autouse=True)
def cleanup_memory_rows(db: Session) -> Iterator[None]:
    # Mirrors test_mapping_execution_memory_feedback.py / test_field_mapping_suggestions.py:
    # SQLite's Base.metadata.drop_all() cannot resolve the self-referential
    # OperationalMemoryVersion.supersedes_version_id FK together with
    # OperationalMemoryReuseEvent's reference to it, so rows referencing a
    # CONFIRMED/CORRECTED supersession chain must be cleared before teardown.
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


def _schema_with_field(
    db: Session,
    organization_id: UUID,
    dataset_id: UUID,
    dataset_version_id: UUID,
    slug: str,
) -> SourceSchema:
    return schema_discovery_service.discover(
        db,
        organization_id,
        SourceSchemaDiscover(
            dataset_id=dataset_id,
            dataset_version_id=dataset_version_id,
            schema_fingerprint=f"{slug}-fingerprint".ljust(32, "0"),
            fields=[SourceFieldCreate(field_path=FIELD_PATH, inferred_data_type="string")],
        ),
    )


def _memory_payload(schema: SourceSchema, field: CanonicalFieldDefinition) -> dict[str, object]:
    return {
        "source_field_path": FIELD_PATH,
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
) -> OperationalMemoryItem:
    candidate = MemoryCandidateCreate(
        idempotency_key=f"{key}-candidate",
        category="FIELD_MAPPING",
        subject_kind="SOURCE_FIELD",
        subject=FIELD_PATH,
        context=MemoryContext(schema_fingerprint=schema.schema_fingerprint),
        value_payload=_memory_payload(schema, field),
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
) -> tuple[OperationalMemoryItem, OperationalMemoryVersion]:
    item = _record(db, organization_id, schema, field, key)
    version = _confirm(db, organization_id, actor, item, key)
    db.refresh(item)
    return item, version


def _publish(
    db: Session,
    template_version: MappingTemplateVersion,
    field: CanonicalFieldDefinition,
    actor: UUID,
    organization_id: UUID,
    *,
    origin_memory_version_id: UUID | None = None,
) -> FieldMapping:
    field_mapping = mapping_template_service.add_field_mapping(
        db,
        template_version.id,
        FieldMappingCreate(
            source_field_path=FIELD_PATH,
            canonical_field_definition_id=field.id,
            origin_memory_version_id=origin_memory_version_id,
        ),
        organization_id,
    )
    for target in ("candidate", "validated", "approved", "published"):
        mapping_template_service.transition(db, template_version.id, target, actor, organization_id)
    return field_mapping


def _run(
    db: Session,
    organization_id: UUID,
    actor: UUID,
    dataset_version_id: UUID,
    template_version_id: UUID,
    source_schema_id: UUID,
    raw_reference_id: UUID,
    key: str,
    value: str = "EQ-1",
) -> MappingRun:
    return mapping_execution_service.execute(
        db,
        organization_id,
        MappingRunCreate(
            dataset_version_id=dataset_version_id,
            template_version_id=template_version_id,
            source_schema_id=source_schema_id,
            idempotency_key=key,
            records=[
                MappingInputRecord(
                    raw_record_reference_id=raw_reference_id,
                    values={FIELD_PATH: value},
                )
            ],
        ),
        actor,
    )


def _field_items(db: Session, organization_id: UUID) -> list[OperationalMemoryItem]:
    return list(
        db.scalars(
            select(OperationalMemoryItem).where(
                OperationalMemoryItem.organization_id == organization_id,
                OperationalMemoryItem.category == "FIELD_MAPPING",
            )
        )
    )


# --- A/B/C: memory-derived unchanged does not self-reinforce -------------------


def test_memory_derived_unchanged_execution_does_not_inflate_support_count(db: Session) -> None:
    org, actor, dataset_id, dataset_version_id, _, raw_reference_id = foundation(db, "lfh-a")
    field, _, template_version = _organization_template(db, org, actor, "lfh-a")
    schema = _schema_with_field(db, org, dataset_id, dataset_version_id, "lfh-a")
    item, origin_version = _confirmed_memory(db, org, actor, schema, field, "lfh-a")
    assert item.support_count == 1
    assert item.current_version_number == 2

    _publish(db, template_version, field, actor, org, origin_memory_version_id=origin_version.id)

    run = _run(
        db,
        org,
        actor,
        dataset_version_id,
        template_version.id,
        schema.id,
        raw_reference_id,
        "lfh-a-run",
    )
    assert run.status == MappingRunStatus.COMPLETED.value

    db.refresh(item)
    assert item.support_count == 1
    assert item.current_version_number == 2


def test_repeated_execution_of_memory_derived_unchanged_mapping_keeps_support_count_flat(
    db: Session,
) -> None:
    org, actor, dataset_id, dataset_version_id, _, raw_reference_id = foundation(db, "lfh-b")
    field, _, template_version = _organization_template(db, org, actor, "lfh-b")
    schema = _schema_with_field(db, org, dataset_id, dataset_version_id, "lfh-b")
    item, origin_version = _confirmed_memory(db, org, actor, schema, field, "lfh-b")
    _publish(db, template_version, field, actor, org, origin_memory_version_id=origin_version.id)

    for i in range(3):
        run = _run(
            db,
            org,
            actor,
            dataset_version_id,
            template_version.id,
            schema.id,
            raw_reference_id,
            f"lfh-b-run-{i}",
            value=f"EQ-{i}",
        )
        assert run.status == MappingRunStatus.COMPLETED.value

    db.refresh(item)
    assert item.support_count == 1
    assert item.current_version_number == 2


def test_multiple_field_mappings_accepting_same_origin_unchanged_do_not_inflate_support_count(
    db: Session,
) -> None:
    org, actor, dataset_id, dataset_version_id, _, raw_reference_id = foundation(db, "lfh-c")
    field, _, template_version_1 = _organization_template(db, org, actor, "lfh-c-1")
    schema = _schema_with_field(db, org, dataset_id, dataset_version_id, "lfh-c")
    item, origin_version = _confirmed_memory(db, org, actor, schema, field, "lfh-c")
    _publish(db, template_version_1, field, actor, org, origin_memory_version_id=origin_version.id)

    template_2 = mapping_template_service.create(
        db,
        MappingTemplateCreate(
            template_code="lfh_c_second",
            name="Equipment Second",
            scope_type="organization",
            scope_key=f"organization:{org}",
            owner_organization_id=org,
            source_system_type="file_upload",
            target_canonical_type_kind="entity",
            target_canonical_type_id=field.canonical_type_id,
        ),
        actor,
        authorized_organization_id=org,
    )
    template_version_2 = mapping_template_service.create_version(
        db,
        template_2.id,
        MappingTemplateVersionCreate(semantic_version="1.0.0", definition_json={}),
        actor,
        org,
    )
    _publish(db, template_version_2, field, actor, org, origin_memory_version_id=origin_version.id)

    run_1 = _run(
        db,
        org,
        actor,
        dataset_version_id,
        template_version_1.id,
        schema.id,
        raw_reference_id,
        "lfh-c-run-1",
    )
    run_2 = _run(
        db,
        org,
        actor,
        dataset_version_id,
        template_version_2.id,
        schema.id,
        raw_reference_id,
        "lfh-c-run-2",
    )
    assert run_1.status == MappingRunStatus.COMPLETED.value
    assert run_2.status == MappingRunStatus.COMPLETED.value

    db.refresh(item)
    assert item.support_count == 1
    assert item.current_version_number == 2


# --- D/E: memory-derived modified uses existing D-A contradiction logic --------


def test_memory_derived_modified_target_calls_record_candidate_and_surfaces_existing_ambiguity(
    db: Session,
) -> None:
    org, actor, dataset_id, dataset_version_id, _, raw_reference_id = foundation(db, "lfh-d")
    field, other_field, template_version = _organization_template(db, org, actor, "lfh-d")
    schema = _schema_with_field(db, org, dataset_id, dataset_version_id, "lfh-d")
    item, origin_version = _confirmed_memory(db, org, actor, schema, field, "lfh-d")
    # FieldMapping targets a DIFFERENT canonical field than the origin memory
    # recorded: this is a deliberate divergence from the suggestion, not an
    # unchanged acceptance.
    _publish(
        db, template_version, other_field, actor, org, origin_memory_version_id=origin_version.id
    )

    run = _run(
        db,
        org,
        actor,
        dataset_version_id,
        template_version.id,
        schema.id,
        raw_reference_id,
        "lfh-d-run",
    )
    assert run.status == MappingRunStatus.COMPLETED.value

    db.refresh(item)
    # record_candidate() was called normally (a new version was recorded)
    # rather than skipped.
    assert item.current_version_number == 3
    # D-A's existing identity/value contradiction logic fired unmodified;
    # D-C.1 introduces no new correction semantics.
    assert item.current_status == "AMBIGUOUS"
    assert item.contradiction_count == 1
    assert item.support_count == 1


def test_replay_of_memory_derived_modified_mapping_does_not_multiply_evidence(
    db: Session,
) -> None:
    org, actor, dataset_id, dataset_version_id, _, raw_reference_id = foundation(db, "lfh-k")
    field, other_field, template_version = _organization_template(db, org, actor, "lfh-k")
    schema = _schema_with_field(db, org, dataset_id, dataset_version_id, "lfh-k")
    item, origin_version = _confirmed_memory(db, org, actor, schema, field, "lfh-k")
    _publish(
        db, template_version, other_field, actor, org, origin_memory_version_id=origin_version.id
    )

    request = MappingRunCreate(
        dataset_version_id=dataset_version_id,
        template_version_id=template_version.id,
        source_schema_id=schema.id,
        idempotency_key="lfh-k-run",
        records=[
            MappingInputRecord(
                raw_record_reference_id=raw_reference_id, values={FIELD_PATH: "EQ-1"}
            )
        ],
    )
    mapping_execution_service.execute(db, org, request, actor)
    db.refresh(item)
    assert item.current_version_number == 3

    # Replay of the same idempotency key: CM-02 returns the existing MappingRun
    # before evidence registration is ever reached again.
    mapping_execution_service.execute(db, org, request, actor)
    db.refresh(item)
    assert item.current_version_number == 3


# --- F: NULL lineage is unaffected ----------------------------------------------


def test_null_lineage_field_mapping_registers_evidence_normally(db: Session) -> None:
    org, actor, dataset_id, dataset_version_id, _, raw_reference_id = foundation(db, "lfh-f")
    field, _, template_version = _organization_template(db, org, actor, "lfh-f")
    schema = _schema_with_field(db, org, dataset_id, dataset_version_id, "lfh-f")
    _publish(db, template_version, field, actor, org)

    run = _run(
        db,
        org,
        actor,
        dataset_version_id,
        template_version.id,
        schema.id,
        raw_reference_id,
        "lfh-f-run",
    )
    assert run.status == MappingRunStatus.COMPLETED.value

    items = _field_items(db, org)
    assert len(items) == 1
    assert items[0].support_count == 1
    assert items[0].current_version_number == 1
    assert items[0].current_status == "OBSERVED"


# --- G/H: classification uses the origin's frozen historical payload -----------


def test_unchanged_use_of_later_corrected_origin_remains_skipped(db: Session) -> None:
    org, actor, dataset_id, dataset_version_id, _, raw_reference_id = foundation(db, "lfh-g")
    field, other_field, template_version = _organization_template(db, org, actor, "lfh-g")
    schema = _schema_with_field(db, org, dataset_id, dataset_version_id, "lfh-g")
    item, origin_version = _confirmed_memory(db, org, actor, schema, field, "lfh-g")
    _publish(db, template_version, field, actor, org, origin_memory_version_id=origin_version.id)

    operational_memory_service.decide(
        db,
        org,
        item.id,
        MemoryDecisionRequest(
            idempotency_key="lfh-g-correct",
            expected_current_version=item.current_version_number,
            action="CORRECT",
            corrected_payload=_memory_payload(schema, other_field),
        ),
        actor,
        "organization_admin",
    )
    db.refresh(item)
    assert item.current_version_number == 3
    assert item.current_status == "CORRECTED"

    run = _run(
        db,
        org,
        actor,
        dataset_version_id,
        template_version.id,
        schema.id,
        raw_reference_id,
        "lfh-g-run",
    )
    assert run.status == MappingRunStatus.COMPLETED.value

    db.refresh(item)
    # Classification compared against the origin version's own frozen payload
    # (still equipment_id), never the item's current (now-corrected) status or
    # value, so no new version was recorded for this execution.
    assert item.current_version_number == 3
    assert item.support_count == 1


def test_unchanged_use_of_later_deprecated_origin_remains_skipped(db: Session) -> None:
    org, actor, dataset_id, dataset_version_id, _, raw_reference_id = foundation(db, "lfh-h")
    field, _, template_version = _organization_template(db, org, actor, "lfh-h")
    schema = _schema_with_field(db, org, dataset_id, dataset_version_id, "lfh-h")
    item, origin_version = _confirmed_memory(db, org, actor, schema, field, "lfh-h")
    _publish(db, template_version, field, actor, org, origin_memory_version_id=origin_version.id)

    operational_memory_service.decide(
        db,
        org,
        item.id,
        MemoryDecisionRequest(
            idempotency_key="lfh-h-deprecate",
            expected_current_version=item.current_version_number,
            action="DEPRECATE",
        ),
        actor,
        "organization_admin",
    )
    db.refresh(item)
    assert item.current_version_number == 3
    assert item.current_status == "DEPRECATED"

    run = _run(
        db,
        org,
        actor,
        dataset_version_id,
        template_version.id,
        schema.id,
        raw_reference_id,
        "lfh-h-run",
    )
    assert run.status == MappingRunStatus.COMPLETED.value

    db.refresh(item)
    assert item.current_version_number == 3
    assert item.support_count == 1


# --- I/J: corrupted/unresolvable lineage fails safe to independent evidence ----


def test_foreign_tenant_origin_fails_safe_to_independent_evidence(db: Session) -> None:
    org_a, actor_a, dataset_a, dataset_version_a, _, raw_reference_a = foundation(db, "lfh-i-a")
    org_b, actor_b, dataset_b, dataset_version_b, _, _ = foundation(db, "lfh-i-b")
    field_a, _, template_version_a = _organization_template(db, org_a, actor_a, "lfh-i-a")
    field_b, _, _ = _organization_template(db, org_b, actor_b, "lfh-i-b")
    schema_a = _schema_with_field(db, org_a, dataset_a, dataset_version_a, "lfh-i-a")
    schema_b = _schema_with_field(db, org_b, dataset_b, dataset_version_b, "lfh-i-b")
    item_b, origin_version_b = _confirmed_memory(db, org_b, actor_b, schema_b, field_b, "lfh-i-b")

    field_mapping = _publish(db, template_version_a, field_a, actor_a, org_a)
    # Simulate corrupted/direct-database data: the normal API rejects a foreign
    # origin at write time (ORIGIN_MEMORY_VERSION_NOT_FOUND); this bypasses it.
    field_mapping = db.get(FieldMapping, field_mapping.id)
    assert field_mapping is not None
    field_mapping.origin_memory_version_id = origin_version_b.id
    db.commit()

    run = _run(
        db,
        org_a,
        actor_a,
        dataset_version_a,
        template_version_a.id,
        schema_a.id,
        raw_reference_a,
        "lfh-i-run",
    )
    assert run.status == MappingRunStatus.COMPLETED.value

    db.refresh(item_b)
    # Tenant B's memory must never be read for, or affected by, Tenant A's execution.
    assert item_b.current_version_number == 2
    assert item_b.support_count == 1

    # Tenant A still receives ordinary, independent evidence for its own execution.
    org_a_items = _field_items(db, org_a)
    assert len(org_a_items) == 1
    assert org_a_items[0].support_count == 1


def test_unresolvable_origin_fails_safe_to_independent_evidence(db: Session) -> None:
    org, actor, dataset_id, dataset_version_id, _, raw_reference_id = foundation(db, "lfh-j")
    field, _, template_version = _organization_template(db, org, actor, "lfh-j")
    schema = _schema_with_field(db, org, dataset_id, dataset_version_id, "lfh-j")
    field_mapping = _publish(db, template_version, field, actor, org)
    field_mapping = db.get(FieldMapping, field_mapping.id)
    assert field_mapping is not None
    field_mapping.origin_memory_version_id = uuid4()
    db.commit()

    run = _run(
        db,
        org,
        actor,
        dataset_version_id,
        template_version.id,
        schema.id,
        raw_reference_id,
        "lfh-j-run",
    )
    assert run.status == MappingRunStatus.COMPLETED.value

    items = _field_items(db, org)
    assert len(items) == 1
    assert items[0].support_count == 1


# --- L/M: confirmation_count and Trust are never touched by classification -----


def test_confirmation_count_unaffected_by_lineage_classification(db: Session) -> None:
    org, actor, dataset_id, dataset_version_id, _, raw_reference_id = foundation(db, "lfh-l")
    field, _, template_version = _organization_template(db, org, actor, "lfh-l")
    schema = _schema_with_field(db, org, dataset_id, dataset_version_id, "lfh-l")
    item, origin_version = _confirmed_memory(db, org, actor, schema, field, "lfh-l")
    assert item.confirmation_count == 1
    _publish(db, template_version, field, actor, org, origin_memory_version_id=origin_version.id)

    _run(
        db,
        org,
        actor,
        dataset_version_id,
        template_version.id,
        schema.id,
        raw_reference_id,
        "lfh-l-run",
    )

    db.refresh(item)
    assert item.confirmation_count == 1


def test_no_trust_mutation_from_lineage_classification(db: Session) -> None:
    org, actor, dataset_id, dataset_version_id, _, raw_reference_id = foundation(db, "lfh-m")
    field, _, template_version = _organization_template(db, org, actor, "lfh-m")
    schema = _schema_with_field(db, org, dataset_id, dataset_version_id, "lfh-m")
    item, origin_version = _confirmed_memory(db, org, actor, schema, field, "lfh-m")
    _publish(db, template_version, field, actor, org, origin_memory_version_id=origin_version.id)

    before = db.scalar(
        select(func.count())
        .select_from(TrustAssessment)
        .where(TrustAssessment.organization_id == org)
    )
    _run(
        db,
        org,
        actor,
        dataset_version_id,
        template_version.id,
        schema.id,
        raw_reference_id,
        "lfh-m-run",
    )
    after = db.scalar(
        select(func.count())
        .select_from(TrustAssessment)
        .where(TrustAssessment.organization_id == org)
    )
    assert before == after
