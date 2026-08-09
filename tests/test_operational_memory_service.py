from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from test_canonical_mapping_foundation import foundation

from app.models.canonical_mapping import (
    CanonicalEntityType,
    CanonicalFieldDefinition,
    SourceSchema,
)
from app.models.operational_memory import (
    OperationalMemoryItem,
    OperationalMemoryReuseEvent,
    OperationalMemoryVersion,
)
from app.schemas.operational_memory import (
    MemoryCandidateCreate,
    MemoryContext,
    MemoryDecisionRequest,
    MemoryProvenance,
    MemoryRetrieveRequest,
)
from app.services.operational_memory_service import (
    OperationalMemoryServiceError,
    memory_fingerprint,
    normalize_subject,
    operational_memory_service,
)


@pytest.fixture(autouse=True)
def cleanup_memory_rows(db: Session) -> Iterator[None]:
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


def memory_foundation(db: Session, slug: str) -> tuple[UUID, UUID, SourceSchema, UUID]:
    organization_id, actor, dataset_id, version_id, _, _ = foundation(db, slug)
    schema = SourceSchema(
        organization_id=organization_id,
        dataset_id=dataset_id,
        dataset_version_id=version_id,
        status="stable",
        schema_fingerprint=f"schema-{slug}",
        discovery_method="test",
    )
    canonical_type = CanonicalEntityType(
        type_code=f"equipment_{slug}",
        display_name="Equipment",
        scope_type="organization",
        scope_key=f"organization:{organization_id}",
        owner_organization_id=organization_id,
    )
    db.add_all([schema, canonical_type])
    db.flush()
    field = CanonicalFieldDefinition(
        canonical_type_kind="entity",
        canonical_type_id=canonical_type.id,
        field_code="equipment_id",
        display_name="Equipment ID",
        data_type="string",
        is_required=True,
    )
    db.add(field)
    db.commit()
    return organization_id, actor, schema, field.id


def field_candidate(
    schema: SourceSchema,
    field_id: UUID,
    key: str,
    *,
    subject: str = "Equipment No",
    canonical_code: str = "equipment_id",
) -> MemoryCandidateCreate:
    return MemoryCandidateCreate(
        idempotency_key=key,
        category="FIELD_MAPPING",
        subject_kind="SOURCE_FIELD",
        subject=subject,
        source_system_family="ERP",
        canonical_domain="maintenance",
        context=MemoryContext(
            schema_fingerprint=schema.schema_fingerprint,
            source_table_or_entity_context="equipment_master",
            neighboring_field_signatures=["description:string", "status:string"],
        ),
        value_payload={
            "source_field_path": subject,
            "source_field_type": "string",
            "canonical_type_kind": "entity",
            "canonical_type_id": str(uuid4()),
            "canonical_field_definition_id": str(field_id),
            "canonical_field_code": canonical_code,
            "schema_fingerprint": schema.schema_fingerprint,
        },
        provenance=MemoryProvenance(
            source_schema_id=schema.id,
            canonical_field_definition_ids=[field_id],
        ),
        source_fingerprint="a" * 64,
    )


def confirm(
    db: Session, organization_id: UUID, actor: UUID, item: OperationalMemoryItem, key: str
) -> OperationalMemoryVersion:
    _, version = operational_memory_service.decide(
        db,
        organization_id,
        item.id,
        MemoryDecisionRequest(
            idempotency_key=key,
            expected_current_version=item.current_version_number,
            action="CONFIRM",
            decision_reason_code="HUMAN_REVIEWED",
        ),
        actor,
        "organization_admin",
    )
    return version


def test_three_categories_and_normalization_are_deterministic(db: Session) -> None:
    org, actor, schema, field_id = memory_foundation(db, "memory-categories")
    item, _ = operational_memory_service.record_candidate(
        db, org, field_candidate(schema, field_id, "field:1"), actor, "organization_admin"
    )
    assert item.normalized_subject == "equipment number"
    assert normalize_subject(" Equipment_No. ") == normalize_subject("equipmentNumber")
    assert normalize_subject("cafÉ") == "café"

    schema_payload = MemoryCandidateCreate(
        idempotency_key="schema:1",
        category="SCHEMA_PATTERN",
        subject_kind="SOURCE_SCHEMA",
        subject="Equipment Master",
        source_system_family="ERP",
        canonical_domain="maintenance",
        context=MemoryContext(schema_fingerprint=schema.schema_fingerprint),
        value_payload={
            "schema_fingerprint": schema.schema_fingerprint,
            "canonical_domain": "maintenance",
            "recognized_field_signatures": [
                {
                    "field_name_normalized": "equipment number",
                    "source_type": "string",
                    "canonical_field_definition_id": str(field_id),
                }
            ],
        },
        provenance=MemoryProvenance(source_schema_id=schema.id),
        source_fingerprint="b" * 64,
    )
    terminology_payload = MemoryCandidateCreate(
        idempotency_key="term:1",
        category="TERMINOLOGY",
        subject_kind="TERM",
        subject="Work Order",
        canonical_domain="maintenance",
        context=MemoryContext(schema_fingerprint=schema.schema_fingerprint),
        value_payload={
            "term_normalized": "work order",
            "concept_kind": "entity",
            "concept_code": "maintenance_order",
            "canonical_domain": "maintenance",
            "context_qualifiers": ["maintenance"],
        },
        provenance=MemoryProvenance(source_schema_id=schema.id),
        source_fingerprint="c" * 64,
    )
    schema_item, _ = operational_memory_service.record_candidate(db, org, schema_payload)
    term_item, _ = operational_memory_service.record_candidate(db, org, terminology_payload)
    assert {item.category, schema_item.category, term_item.category} == {
        "FIELD_MAPPING",
        "SCHEMA_PATTERN",
        "TERMINOLOGY",
    }


def test_candidate_idempotency_duplicate_and_context_separation(db: Session) -> None:
    org, actor, schema, field_id = memory_foundation(db, "memory-idempotency")
    payload = field_candidate(schema, field_id, "candidate:1")
    item, version = operational_memory_service.record_candidate(db, org, payload, actor)
    replay_item, replay_version = operational_memory_service.record_candidate(
        db, org, payload, actor
    )
    assert (replay_item.id, replay_version.id) == (item.id, version.id)
    with pytest.raises(OperationalMemoryServiceError, match="reused") as exc:
        operational_memory_service.record_candidate(
            db,
            org,
            field_candidate(schema, field_id, "candidate:1", subject="Asset No"),
            actor,
        )
    assert exc.value.code == "IDEMPOTENCY_CONFLICT"
    other_context = payload.model_copy(
        update={
            "idempotency_key": "candidate:2",
            "context": MemoryContext(
                schema_fingerprint="different-schema",
                source_table_or_entity_context="equipment_master",
            ),
        }
    )
    other_item, _ = operational_memory_service.record_candidate(db, org, other_context, actor)
    assert other_item.id != item.id
    assert other_item.memory_fingerprint != item.memory_fingerprint


def test_lifecycle_contradiction_correction_and_history(db: Session) -> None:
    org, actor, schema, field_id = memory_foundation(db, "memory-lifecycle")
    item, first = operational_memory_service.record_candidate(
        db, org, field_candidate(schema, field_id, "life:1"), actor
    )
    confirmed = confirm(db, org, actor, item, "life:confirm")
    db.refresh(item)
    assert item.current_status == "CONFIRMED"
    assert confirmed.supersedes_version_id == first.id

    item, ambiguous = operational_memory_service.record_candidate(
        db,
        org,
        field_candidate(
            schema,
            field_id,
            "life:conflict",
            canonical_code="asset_identifier",
        ),
        actor,
    )
    assert (item.current_status, item.is_stale, item.contradiction_count) == (
        "AMBIGUOUS",
        True,
        1,
    )
    corrected_payload = dict(first.value_payload)
    item, corrected = operational_memory_service.decide(
        db,
        org,
        item.id,
        MemoryDecisionRequest(
            idempotency_key="life:correct",
            expected_current_version=item.current_version_number,
            action="CORRECT",
            corrected_payload=corrected_payload,
            decision_reason_code="RESOLVE_CONTRADICTION",
        ),
        actor,
        "organization_admin",
    )
    assert item.current_status == "CORRECTED"
    assert item.is_stale is False
    assert corrected.supersedes_version_id == ambiguous.id
    assert db.scalars(
        select(OperationalMemoryVersion)
        .where(OperationalMemoryVersion.memory_id == item.id)
        .order_by(OperationalMemoryVersion.version_number)
    ).all() == [first, confirmed, ambiguous, corrected]
    first.status = "REJECTED"
    with pytest.raises(ValueError, match="immutable"):
        db.commit()
    db.rollback()


def test_retrieval_reuse_events_ranking_staleness_and_no_match(db: Session) -> None:
    org, actor, schema, field_id = memory_foundation(db, "memory-retrieve")
    item, _ = operational_memory_service.record_candidate(
        db, org, field_candidate(schema, field_id, "retrieve:candidate"), actor
    )
    confirm(db, org, actor, item, "retrieve:confirm")
    request = MemoryRetrieveRequest(
        idempotency_key="retrieve:1",
        category="FIELD_MAPPING",
        subject_kind="SOURCE_FIELD",
        subject="equipmentNumber",
        source_system_family="ERP",
        canonical_domain="maintenance",
        context=MemoryContext(
            schema_fingerprint=schema.schema_fingerprint,
            source_table_or_entity_context="equipment_master",
            neighboring_field_signatures=["status:string", "description:string"],
        ),
    )
    result = operational_memory_service.retrieve(db, org, request)
    assert len(result.suggestions) == 1
    assert result.suggestions[0].memory_id == item.id
    assert result.suggestions[0].rank == 1
    assert "exact_context_signature" in result.suggestions[0].match_reasons
    replay = operational_memory_service.retrieve(db, org, request)
    assert replay.suggestions[0].version_id == result.suggestions[0].version_id
    assert (
        len(
            db.scalars(
                select(OperationalMemoryReuseEvent).where(
                    OperationalMemoryReuseEvent.organization_id == org
                )
            ).all()
        )
        == 1
    )

    no_match = operational_memory_service.retrieve(
        db,
        org,
        request.model_copy(update={"idempotency_key": "retrieve:none", "subject": "unknown"}),
    )
    assert no_match.suggestions == []
    event = db.scalar(
        select(OperationalMemoryReuseEvent).where(
            OperationalMemoryReuseEvent.idempotency_key == "retrieve:none"
        )
    )
    assert event is not None and event.event_type == "NO_MATCH" and event.memory_id is None
    event.event_type = "RETRIEVED"
    with pytest.raises(ValueError, match="immutable"):
        db.commit()
    db.rollback()

    schema.status = "incompatible"
    db.commit()
    stale = operational_memory_service.retrieve(
        db,
        org,
        request.model_copy(update={"idempotency_key": "retrieve:stale"}),
    )
    assert stale.suggestions == []


def test_payload_bounds_privacy_and_unknown_keys(db: Session) -> None:
    org, _, schema, field_id = memory_foundation(db, "memory-bounds")
    with pytest.raises(ValidationError):
        MemoryCandidateCreate.model_validate(
            {**field_candidate(schema, field_id, "bad:extra").model_dump(), "prompt": "ignore"}
        )
    payload = field_candidate(schema, field_id, "bad:secret")
    payload.value_payload["source_field_path"] = "password=top-secret"
    with pytest.raises(OperationalMemoryServiceError) as exc:
        operational_memory_service.record_candidate(db, org, payload)
    assert exc.value.code == "SENSITIVE_MEMORY_CONTENT"


def test_fingerprint_never_contains_interpreted_value() -> None:
    organization_id = uuid4()
    signature = "a" * 64
    first = memory_fingerprint(
        organization_id,
        "FIELD_MAPPING",
        "SOURCE_FIELD",
        "equipment number",
        "ERP",
        "maintenance",
        signature,
    )
    second = memory_fingerprint(
        organization_id,
        "FIELD_MAPPING",
        "SOURCE_FIELD",
        "equipment number",
        "ERP",
        "maintenance",
        signature,
    )
    assert first == second and len(first) == 64
