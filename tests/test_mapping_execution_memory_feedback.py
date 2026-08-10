from __future__ import annotations

import inspect
from collections.abc import Iterator
from uuid import UUID

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from test_canonical_mapping_foundation import foundation, published_entity_mapping

from app.models.canonical_mapping import MappingRun, MappingRunStatus, SourceSchema
from app.models.operational_memory import (
    OperationalMemoryItem,
    OperationalMemoryReuseEvent,
    OperationalMemoryVersion,
)
from app.models.trust import TrustAssessment
from app.schemas.canonical_mapping import (
    MappingInputRecord,
    MappingRunCreate,
    SourceFieldCreate,
    SourceSchemaDiscover,
)
from app.schemas.operational_memory import (
    MemoryContext,
    MemoryDecisionRequest,
    MemoryRetrieveRequest,
)
from app.services.canonical_mapping_service import (
    mapping_execution_service,
    schema_discovery_service,
)
from app.services.operational_memory_service import operational_memory_service


@pytest.fixture(autouse=True)
def cleanup_memory_rows(db: Session) -> Iterator[None]:
    # Mirrors test_operational_memory_service.py: SQLite's Base.metadata.drop_all()
    # cannot resolve the self-referential OperationalMemoryVersion.supersedes_version_id
    # FK together with OperationalMemoryReuseEvent's reference to it, so rows referencing
    # a CONFIRMED/CORRECTED supersession chain must be cleared before teardown.
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


def _schema_with_fields(
    db: Session,
    organization_id: UUID,
    dataset_id: UUID,
    dataset_version_id: UUID,
    slug: str,
    field_paths: tuple[str, ...] = ("customer_name", "customer_id"),
) -> SourceSchema:
    return schema_discovery_service.discover(
        db,
        organization_id,
        SourceSchemaDiscover(
            dataset_id=dataset_id,
            dataset_version_id=dataset_version_id,
            schema_fingerprint=f"{slug}-schema-fingerprint".ljust(32, "0"),
            fields=[
                SourceFieldCreate(field_path=path, inferred_data_type="string")
                for path in field_paths
            ],
        ),
    )


def _request(
    dataset_version_id: UUID,
    template_version_id: UUID,
    source_schema_id: UUID,
    idempotency_key: str,
    raw_reference_id: UUID,
    values: dict[str, object] | None = None,
) -> MappingRunCreate:
    record_values = (
        values if values is not None else {"customer_id": "C-1", "customer_name": "Acme"}
    )
    return MappingRunCreate(
        dataset_version_id=dataset_version_id,
        template_version_id=template_version_id,
        source_schema_id=source_schema_id,
        idempotency_key=idempotency_key,
        records=[
            MappingInputRecord(
                raw_record_reference_id=raw_reference_id,
                values=record_values,
            )
        ],
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


def test_completed_run_with_resolvable_fields_creates_field_mapping_evidence(
    db: Session,
) -> None:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(
        db, "dbfeedback-a"
    )
    _, template_version = published_entity_mapping(db, organization_id, actor)
    schema = _schema_with_fields(db, organization_id, dataset_id, version_id, "dbfeedback-a")
    run = mapping_execution_service.execute(
        db,
        organization_id,
        _request(version_id, template_version.id, schema.id, "dbfeedback-a-key", raw_reference_id),
        actor,
    )
    assert run.status == MappingRunStatus.COMPLETED.value
    items = _field_items(db, organization_id)
    assert {item.normalized_subject for item in items} == {"customer name", "customer id"}


def test_evidence_status_is_observed(db: Session) -> None:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(
        db, "dbfeedback-b"
    )
    _, template_version = published_entity_mapping(db, organization_id, actor)
    schema = _schema_with_fields(db, organization_id, dataset_id, version_id, "dbfeedback-b")
    mapping_execution_service.execute(
        db,
        organization_id,
        _request(version_id, template_version.id, schema.id, "dbfeedback-b-key", raw_reference_id),
        actor,
    )
    items = _field_items(db, organization_id)
    assert items
    assert all(item.current_status == "OBSERVED" for item in items)


def test_evidence_actor_is_system_not_run_executor(db: Session) -> None:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(
        db, "dbfeedback-c"
    )
    _, template_version = published_entity_mapping(db, organization_id, actor)
    schema = _schema_with_fields(db, organization_id, dataset_id, version_id, "dbfeedback-c")
    mapping_execution_service.execute(
        db,
        organization_id,
        _request(version_id, template_version.id, schema.id, "dbfeedback-c-key", raw_reference_id),
        actor,
    )
    items = _field_items(db, organization_id)
    assert items
    for item in items:
        version = db.scalar(
            select(OperationalMemoryVersion).where(
                OperationalMemoryVersion.organization_id == organization_id,
                OperationalMemoryVersion.memory_id == item.id,
                OperationalMemoryVersion.version_number == 1,
            )
        )
        assert version is not None
        assert version.actor_user_id is None
        assert version.actor_role == "system"
        assert version.actor_user_id != actor


def test_schema_fingerprint_matches_run_snapshot(db: Session) -> None:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(
        db, "dbfeedback-d"
    )
    _, template_version = published_entity_mapping(db, organization_id, actor)
    schema = _schema_with_fields(db, organization_id, dataset_id, version_id, "dbfeedback-d")
    run = mapping_execution_service.execute(
        db,
        organization_id,
        _request(version_id, template_version.id, schema.id, "dbfeedback-d-key", raw_reference_id),
        actor,
    )
    items = _field_items(db, organization_id)
    assert items
    for item in items:
        version = db.scalar(
            select(OperationalMemoryVersion).where(
                OperationalMemoryVersion.organization_id == organization_id,
                OperationalMemoryVersion.memory_id == item.id,
                OperationalMemoryVersion.version_number == 1,
            )
        )
        assert version is not None
        assert version.value_payload["schema_fingerprint"] == run.schema_fingerprint_snapshot
        assert run.schema_fingerprint_snapshot == schema.schema_fingerprint


def test_source_field_type_matches_exact_source_field(db: Session) -> None:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(
        db, "dbfeedback-e"
    )
    _, template_version = published_entity_mapping(db, organization_id, actor)
    schema = schema_discovery_service.discover(
        db,
        organization_id,
        SourceSchemaDiscover(
            dataset_id=dataset_id,
            dataset_version_id=version_id,
            schema_fingerprint="dbfeedback-e-schema-fingerprint".ljust(32, "0"),
            fields=[
                SourceFieldCreate(field_path="customer_name", inferred_data_type="varchar"),
                SourceFieldCreate(field_path="customer_id", inferred_data_type="integer"),
            ],
        ),
    )
    mapping_execution_service.execute(
        db,
        organization_id,
        _request(version_id, template_version.id, schema.id, "dbfeedback-e-key", raw_reference_id),
        actor,
    )
    items = _field_items(db, organization_id)
    by_subject = {item.normalized_subject: item for item in items}
    name_version = db.scalar(
        select(OperationalMemoryVersion).where(
            OperationalMemoryVersion.memory_id == by_subject["customer name"].id,
            OperationalMemoryVersion.version_number == 1,
        )
    )
    id_version = db.scalar(
        select(OperationalMemoryVersion).where(
            OperationalMemoryVersion.memory_id == by_subject["customer id"].id,
            OperationalMemoryVersion.version_number == 1,
        )
    )
    assert name_version is not None and name_version.value_payload["source_field_type"] == "varchar"
    assert id_version is not None and id_version.value_payload["source_field_type"] == "integer"


def test_canonical_target_matches_exact_canonical_field_definition(db: Session) -> None:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(
        db, "dbfeedback-f"
    )
    entity_type, template_version = published_entity_mapping(db, organization_id, actor)
    schema = _schema_with_fields(db, organization_id, dataset_id, version_id, "dbfeedback-f")
    mapping_execution_service.execute(
        db,
        organization_id,
        _request(version_id, template_version.id, schema.id, "dbfeedback-f-key", raw_reference_id),
        actor,
    )
    items = _field_items(db, organization_id)
    by_subject = {item.normalized_subject: item for item in items}
    name_version = db.scalar(
        select(OperationalMemoryVersion).where(
            OperationalMemoryVersion.memory_id == by_subject["customer name"].id,
            OperationalMemoryVersion.version_number == 1,
        )
    )
    assert name_version is not None
    payload = name_version.value_payload
    assert payload["canonical_type_kind"] == "entity"
    assert payload["canonical_type_id"] == str(entity_type.id)
    assert payload["canonical_field_code"] == "name"


def test_unresolvable_source_field_is_skipped_not_fabricated(db: Session) -> None:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(
        db, "dbfeedback-g"
    )
    _, template_version = published_entity_mapping(db, organization_id, actor)
    schema = _schema_with_fields(
        db, organization_id, dataset_id, version_id, "dbfeedback-g", field_paths=("customer_id",)
    )
    mapping_execution_service.execute(
        db,
        organization_id,
        _request(version_id, template_version.id, schema.id, "dbfeedback-g-key", raw_reference_id),
        actor,
    )
    items = _field_items(db, organization_id)
    assert {item.normalized_subject for item in items} == {"customer id"}


def test_partially_completed_run_creates_no_evidence(db: Session) -> None:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(
        db, "dbfeedback-h"
    )
    _, template_version = published_entity_mapping(db, organization_id, actor)
    schema = _schema_with_fields(db, organization_id, dataset_id, version_id, "dbfeedback-h")
    run = mapping_execution_service.execute(
        db,
        organization_id,
        _request(
            version_id,
            template_version.id,
            schema.id,
            "dbfeedback-h-key",
            raw_reference_id,
            values={"customer_id": "C-1"},
        ),
        actor,
    )
    assert run.status == MappingRunStatus.PARTIALLY_COMPLETED.value
    assert _field_items(db, organization_id) == []


def test_registration_gate_is_exactly_completed_status() -> None:
    source = inspect.getsource(mapping_execution_service.__class__.execute)
    assert "run.status == MappingRunStatus.COMPLETED.value" in source
    assert "run.source_schema_id is not None" in source
    gate_marker = "run.status == MappingRunStatus.COMPLETED.value"
    gate_line = next(line for line in source.splitlines() if gate_marker in line)
    assert "PARTIALLY_COMPLETED" not in gate_line
    assert "FAILED" not in gate_line


def test_sequential_replay_creates_no_additional_evidence(db: Session) -> None:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(
        db, "dbfeedback-i"
    )
    _, template_version = published_entity_mapping(db, organization_id, actor)
    schema = _schema_with_fields(db, organization_id, dataset_id, version_id, "dbfeedback-i")
    request = _request(
        version_id, template_version.id, schema.id, "dbfeedback-i-key", raw_reference_id
    )
    mapping_execution_service.execute(db, organization_id, request, actor)
    first_items = _field_items(db, organization_id)
    mapping_execution_service.execute(db, organization_id, request, actor)
    second_items = _field_items(db, organization_id)
    assert len(first_items) == len(second_items) == 2
    assert {item.id for item in first_items} == {item.id for item in second_items}


def test_sequential_replay_does_not_inflate_support_count(db: Session) -> None:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(
        db, "dbfeedback-j"
    )
    _, template_version = published_entity_mapping(db, organization_id, actor)
    schema = _schema_with_fields(db, organization_id, dataset_id, version_id, "dbfeedback-j")
    request = _request(
        version_id, template_version.id, schema.id, "dbfeedback-j-key", raw_reference_id
    )
    mapping_execution_service.execute(db, organization_id, request, actor)
    mapping_execution_service.execute(db, organization_id, request, actor)
    items = _field_items(db, organization_id)
    assert items
    for item in items:
        assert item.support_count == 1
        assert item.current_version_number == 1


def test_observed_evidence_not_returned_by_retrieve(db: Session) -> None:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(
        db, "dbfeedback-k"
    )
    _, template_version = published_entity_mapping(db, organization_id, actor)
    schema = _schema_with_fields(db, organization_id, dataset_id, version_id, "dbfeedback-k")
    mapping_execution_service.execute(
        db,
        organization_id,
        _request(version_id, template_version.id, schema.id, "dbfeedback-k-key", raw_reference_id),
        actor,
    )
    result = operational_memory_service.retrieve(
        db,
        organization_id,
        MemoryRetrieveRequest(
            idempotency_key="dbfeedback-k-retrieve",
            category="FIELD_MAPPING",
            subject_kind="SOURCE_FIELD",
            subject="customer_name",
            context=MemoryContext(),
        ),
    )
    assert result.suggestions == []


def test_manual_confirm_makes_evidence_reusable(db: Session) -> None:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(
        db, "dbfeedback-l"
    )
    _, template_version = published_entity_mapping(db, organization_id, actor)
    schema = _schema_with_fields(db, organization_id, dataset_id, version_id, "dbfeedback-l")
    mapping_execution_service.execute(
        db,
        organization_id,
        _request(version_id, template_version.id, schema.id, "dbfeedback-l-key", raw_reference_id),
        actor,
    )
    items = _field_items(db, organization_id)
    name_item = next(item for item in items if item.normalized_subject == "customer name")
    operational_memory_service.decide(
        db,
        organization_id,
        name_item.id,
        MemoryDecisionRequest(
            idempotency_key="dbfeedback-l-decision",
            expected_current_version=1,
            action="CONFIRM",
        ),
        actor,
        "organization_admin",
    )
    result = operational_memory_service.retrieve(
        db,
        organization_id,
        MemoryRetrieveRequest(
            idempotency_key="dbfeedback-l-retrieve",
            category="FIELD_MAPPING",
            subject_kind="SOURCE_FIELD",
            subject="customer_name",
            context=MemoryContext(),
        ),
    )
    assert len(result.suggestions) == 1
    assert result.suggestions[0].memory_id == name_item.id


def test_cross_tenant_source_field_never_used_for_evidence(db: Session) -> None:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(
        db, "dbfeedback-m"
    )
    other_id, other_actor, other_dataset_id, other_version_id, _, _ = foundation(
        db, "dbfeedback-m-other"
    )
    _, template_version = published_entity_mapping(db, organization_id, actor)
    schema = _schema_with_fields(db, organization_id, dataset_id, version_id, "dbfeedback-m")
    _schema_with_fields(db, other_id, other_dataset_id, other_version_id, "dbfeedback-m-other")
    mapping_execution_service.execute(
        db,
        organization_id,
        _request(version_id, template_version.id, schema.id, "dbfeedback-m-key", raw_reference_id),
        actor,
    )
    assert _field_items(db, organization_id)
    assert _field_items(db, other_id) == []


def test_cross_tenant_same_field_path_produces_independent_evidence(db: Session) -> None:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(
        db, "dbfeedback-n"
    )
    other_id, other_actor, other_dataset_id, other_version_id, _, other_raw_reference_id = (
        foundation(db, "dbfeedback-n-other")
    )
    _, template_version = published_entity_mapping(db, organization_id, actor)
    _, other_template_version = published_entity_mapping(db, other_id, other_actor)
    schema = _schema_with_fields(db, organization_id, dataset_id, version_id, "dbfeedback-n")
    other_schema = _schema_with_fields(
        db, other_id, other_dataset_id, other_version_id, "dbfeedback-n-other"
    )
    mapping_execution_service.execute(
        db,
        organization_id,
        _request(version_id, template_version.id, schema.id, "dbfeedback-n-key", raw_reference_id),
        actor,
    )
    mapping_execution_service.execute(
        db,
        other_id,
        _request(
            other_version_id,
            other_template_version.id,
            other_schema.id,
            "dbfeedback-n-key",
            other_raw_reference_id,
        ),
        other_actor,
    )
    own_items = _field_items(db, organization_id)
    other_items = _field_items(db, other_id)
    assert len(own_items) == len(other_items) == 2
    assert {item.id for item in own_items}.isdisjoint({item.id for item in other_items})


def test_memory_registration_failure_does_not_affect_authoritative_mapping_run(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(
        db, "dbfeedback-o"
    )
    _, template_version = published_entity_mapping(db, organization_id, actor)
    schema = _schema_with_fields(db, organization_id, dataset_id, version_id, "dbfeedback-o")

    def _raise(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("simulated operational memory outage")

    monkeypatch.setattr(operational_memory_service, "record_candidate", _raise)

    run = mapping_execution_service.execute(
        db,
        organization_id,
        _request(version_id, template_version.id, schema.id, "dbfeedback-o-key", raw_reference_id),
        actor,
    )
    assert run.status == MappingRunStatus.COMPLETED.value
    assert run.mapped_count == 1

    persisted = db.get(MappingRun, run.id)
    assert persisted is not None
    assert persisted.status == MappingRunStatus.COMPLETED.value
    assert _field_items(db, organization_id) == []

    # session must remain usable after the injected failure
    count = db.scalar(
        select(func.count())
        .select_from(MappingRun)
        .where(MappingRun.organization_id == organization_id)
    )
    assert count == 1


def test_no_trust_mutation_from_evidence_registration(db: Session) -> None:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(
        db, "dbfeedback-p"
    )
    _, template_version = published_entity_mapping(db, organization_id, actor)
    schema = _schema_with_fields(db, organization_id, dataset_id, version_id, "dbfeedback-p")
    before = db.scalar(
        select(func.count())
        .select_from(TrustAssessment)
        .where(TrustAssessment.organization_id == organization_id)
    )
    mapping_execution_service.execute(
        db,
        organization_id,
        _request(version_id, template_version.id, schema.id, "dbfeedback-p-key", raw_reference_id),
        actor,
    )
    after = db.scalar(
        select(func.count())
        .select_from(TrustAssessment)
        .where(TrustAssessment.organization_id == organization_id)
    )
    assert before == after
