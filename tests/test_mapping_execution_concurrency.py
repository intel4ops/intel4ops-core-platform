from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_canonical_mapping_foundation import (
    discovered_schema,
    foundation,
    published_entity_mapping,
)

from app.models.canonical_mapping import MappingRun
from app.models.operational_memory import OperationalMemoryItem
from app.models.trust import TrustAssessment
from app.schemas.canonical_mapping import MappingInputRecord, MappingRunCreate
from app.services.canonical_mapping_service import (
    CanonicalMappingServiceError,
    mapping_execution_service,
)


def _request(
    dataset_version_id: UUID,
    template_version_id: UUID,
    source_schema_id: UUID,
    idempotency_key: str,
    raw_reference_id: UUID,
) -> MappingRunCreate:
    return MappingRunCreate(
        dataset_version_id=dataset_version_id,
        template_version_id=template_version_id,
        source_schema_id=source_schema_id,
        idempotency_key=idempotency_key,
        records=[
            MappingInputRecord(
                raw_record_reference_id=raw_reference_id,
                values={"customer_id": "C-200", "customer_name": "Acme"},
            )
        ],
    )


def test_sequential_identical_request_replays_governed_result(db: Session) -> None:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(
        db, "cm02-sequential-replay"
    )
    _, template_version = published_entity_mapping(db, organization_id, actor)
    schema = discovered_schema(
        db, organization_id, dataset_id, version_id, "cm02-sequential-replay"
    )
    request = _request(
        version_id, template_version.id, schema.id, "cm02-sequential-replay-key", raw_reference_id
    )
    first = mapping_execution_service.execute(db, organization_id, request, actor)
    second = mapping_execution_service.execute(db, organization_id, request, actor)
    assert first.id == second.id
    count = db.scalar(
        select(func.count())
        .select_from(MappingRun)
        .where(
            MappingRun.organization_id == organization_id,
            MappingRun.idempotency_key == "cm02-sequential-replay-key",
        )
    )
    assert count == 1


def test_sequential_same_key_different_fingerprint_conflicts(db: Session) -> None:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(
        db, "cm02-sequential-conflict"
    )
    _, template_version = published_entity_mapping(db, organization_id, actor)
    schema = discovered_schema(
        db, organization_id, dataset_id, version_id, "cm02-sequential-conflict"
    )
    first_request = _request(
        version_id, template_version.id, schema.id, "cm02-sequential-conflict-key", raw_reference_id
    )
    mapping_execution_service.execute(db, organization_id, first_request, actor)
    second_request = first_request.model_copy(update={"correlation_id": "changed-request-shape"})
    with pytest.raises(CanonicalMappingServiceError) as exc:
        mapping_execution_service.execute(db, organization_id, second_request, actor)
    assert (exc.value.code, exc.value.status) == ("IDEMPOTENCY_CONFLICT", 409)


def test_cross_tenant_same_idempotency_key_remains_independent(db: Session) -> None:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(
        db, "cm02-tenant-a"
    )
    other_id, other_actor, other_dataset_id, other_version_id, _, other_raw_reference_id = (
        foundation(db, "cm02-tenant-b")
    )
    _, template_version = published_entity_mapping(db, organization_id, actor)
    _, other_template_version = published_entity_mapping(db, other_id, other_actor)
    schema = discovered_schema(db, organization_id, dataset_id, version_id, "cm02-tenant-a")
    other_schema = discovered_schema(
        db, other_id, other_dataset_id, other_version_id, "cm02-tenant-b"
    )
    shared_key = "cm02-shared-idempotency-key"
    run_a = mapping_execution_service.execute(
        db,
        organization_id,
        _request(version_id, template_version.id, schema.id, shared_key, raw_reference_id),
        actor,
    )
    run_b = mapping_execution_service.execute(
        db,
        other_id,
        _request(
            other_version_id,
            other_template_version.id,
            other_schema.id,
            shared_key,
            other_raw_reference_id,
        ),
        other_actor,
    )
    assert run_a.id != run_b.id
    assert run_a.organization_id != run_b.organization_id


def test_unrelated_integrity_error_still_propagates(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(
        db, "cm02-unrelated-error"
    )
    _, template_version = published_entity_mapping(db, organization_id, actor)
    schema = discovered_schema(db, organization_id, dataset_id, version_id, "cm02-unrelated-error")

    class _FakeDiag:
        constraint_name = "ck_mapping_run_counts"

    class _FakeOrig(Exception):
        diag = _FakeDiag()

    def _raise_unrelated(*_args: object, **_kwargs: object) -> None:
        raise IntegrityError("INSERT", {}, _FakeOrig())

    monkeypatch.setattr(db, "flush", _raise_unrelated)

    with pytest.raises(IntegrityError):
        mapping_execution_service.execute(
            db,
            organization_id,
            _request(
                version_id,
                template_version.id,
                schema.id,
                "cm02-unrelated-error-run",
                raw_reference_id,
            ),
            actor,
        )


def test_historical_mapping_run_behavior_unchanged(db: Session) -> None:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(
        db, "cm02-historical"
    )
    _, template_version = published_entity_mapping(db, organization_id, actor)
    historical = MappingRun(
        organization_id=organization_id,
        dataset_version_id=version_id,
        template_version_id=template_version.id,
        source_schema_id=None,
        schema_fingerprint_snapshot=None,
        status="completed",
        idempotency_key="cm02-historical-run",
        request_fingerprint="9" * 64,
        input_count=0,
        mapped_count=0,
        exception_count=0,
        rejected_count=0,
        created_by_user_id=actor,
    )
    db.add(historical)
    db.commit()
    db.refresh(historical)
    assert historical.source_schema_id is None
    assert historical.schema_fingerprint_snapshot is None
    reread = db.get(MappingRun, historical.id)
    assert reread is not None
    assert reread.source_schema_id is None


def test_cm01_provenance_preserved_on_replayed_result(db: Session) -> None:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(
        db, "cm02-provenance"
    )
    _, template_version = published_entity_mapping(db, organization_id, actor)
    schema = discovered_schema(db, organization_id, dataset_id, version_id, "cm02-provenance")
    request = _request(
        version_id, template_version.id, schema.id, "cm02-provenance-key", raw_reference_id
    )
    first = mapping_execution_service.execute(db, organization_id, request, actor)
    replay = mapping_execution_service.execute(db, organization_id, request, actor)
    assert replay.source_schema_id == first.source_schema_id == schema.id
    assert (
        replay.schema_fingerprint_snapshot
        == first.schema_fingerprint_snapshot
        == schema.schema_fingerprint
    )


def test_no_trust_or_operational_memory_mutation_from_recovery_path(db: Session) -> None:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(
        db, "cm02-no-mutation"
    )
    _, template_version = published_entity_mapping(db, organization_id, actor)
    schema = discovered_schema(db, organization_id, dataset_id, version_id, "cm02-no-mutation")
    request = _request(
        version_id, template_version.id, schema.id, "cm02-no-mutation-key", raw_reference_id
    )
    mapping_execution_service.execute(db, organization_id, request, actor)
    trust_before = db.scalar(
        select(func.count())
        .select_from(TrustAssessment)
        .where(TrustAssessment.organization_id == organization_id)
    )
    memory_before = db.scalar(
        select(func.count())
        .select_from(OperationalMemoryItem)
        .where(OperationalMemoryItem.organization_id == organization_id)
    )
    mapping_execution_service.execute(db, organization_id, request, actor)
    trust_after = db.scalar(
        select(func.count())
        .select_from(TrustAssessment)
        .where(TrustAssessment.organization_id == organization_id)
    )
    memory_after = db.scalar(
        select(func.count())
        .select_from(OperationalMemoryItem)
        .where(OperationalMemoryItem.organization_id == organization_id)
    )
    assert trust_after == trust_before
    assert memory_after == memory_before
