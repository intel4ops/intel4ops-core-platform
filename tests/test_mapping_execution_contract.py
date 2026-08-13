from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_canonical_mapping_foundation import (
    discovered_schema,
    foundation,
    published_entity_mapping,
)

from app.models.canonical_mapping import MappingRun, MappingRunInput, MappingRunStatus
from app.schemas.canonical_mapping import (
    MappingInputRecord,
    MappingRunCreate,
    MappingRunRetryCreate,
)
from app.services.canonical_mapping_service import (
    CanonicalMappingServiceError,
    mapping_execution_service,
)


def _request(
    dataset_version_id: UUID,
    template_version_id: UUID,
    source_schema_id: UUID,
    raw_reference_id: UUID,
    key: str,
    correlation: str | None = None,
) -> MappingRunCreate:
    return MappingRunCreate(
        dataset_version_id=dataset_version_id,
        template_version_id=template_version_id,
        source_schema_id=source_schema_id,
        idempotency_key=key,
        correlation_id=correlation,
        records=[
            MappingInputRecord(
                raw_record_reference_id=raw_reference_id,
                values={"customer_id": "C-1", "customer_name": "Acme"},
                source_reported_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            )
        ],
    )


def _setup(db: Session, slug: str) -> tuple[UUID, UUID, MappingRunCreate]:
    organization_id, actor, dataset_id, version_id, _, raw_reference_id = foundation(db, slug)
    _, template_version = published_entity_mapping(db, organization_id, actor)
    schema = discovered_schema(db, organization_id, dataset_id, version_id, slug)
    return (
        organization_id,
        actor,
        _request(version_id, template_version.id, schema.id, raw_reference_id, f"{slug}-key"),
    )


def test_submission_is_durable_queued_version_pinned_and_replayable(db: Session) -> None:
    organization_id, actor, request = _setup(db, "p305b-submit")

    run, created = mapping_execution_service.submit(db, organization_id, request, actor)
    replay, replay_created = mapping_execution_service.submit(
        db,
        organization_id,
        request.model_copy(update={"correlation_id": "new-trace"}),
        actor,
    )

    assert created is True
    assert replay_created is False
    assert replay.id == run.id
    assert run.status == MappingRunStatus.QUEUED.value
    assert run.template_version_id == request.template_version_id
    assert run.root_run_id == run.id
    assert run.attempt_number == 1
    inputs = list(
        db.scalars(
            select(MappingRunInput)
            .where(MappingRunInput.mapping_run_id == run.id)
            .order_by(MappingRunInput.record_sequence)
        )
    )
    assert [(item.record_sequence, item.values_json) for item in inputs] == [
        (0, request.records[0].values)
    ]


def test_semantic_idempotency_conflict(db: Session) -> None:
    organization_id, actor, request = _setup(db, "p305b-conflict")
    mapping_execution_service.submit(db, organization_id, request, actor)

    changed = request.model_copy(
        update={"records": [request.records[0].model_copy(update={"values": {"changed": True}})]}
    )
    with pytest.raises(CanonicalMappingServiceError) as exc:
        mapping_execution_service.submit(db, organization_id, changed, actor)

    assert (exc.value.status, exc.value.code) == (409, "IDEMPOTENCY_CONFLICT")


def test_atomic_claim_and_terminal_execution(db: Session) -> None:
    organization_id, actor, request = _setup(db, "p305b-claim")
    run, _ = mapping_execution_service.submit(db, organization_id, request, actor)

    completed = mapping_execution_service.claim_and_execute(db, organization_id, run.id)

    assert completed.status == MappingRunStatus.COMPLETED.value
    assert completed.execution_claimed_at is not None
    assert completed.completed_at is not None
    with pytest.raises(CanonicalMappingServiceError) as exc:
        mapping_execution_service.claim_and_execute(db, organization_id, run.id)
    assert exc.value.code == "MAPPING_RUN_INVALID_TRANSITION"


def test_failure_is_safe_durable_and_retry_reuses_immutable_input(db: Session) -> None:
    organization_id, actor, request = _setup(db, "p305b-retry")
    predecessor, _ = mapping_execution_service.submit(db, organization_id, request, actor)
    failed = mapping_execution_service.fail(
        db,
        organization_id,
        predecessor.id,
        "MAPPING_EXECUTION_TRANSIENT_FAILURE",
        "Mapping execution is temporarily unavailable",
        True,
    )

    child, created = mapping_execution_service.retry(
        db,
        organization_id,
        failed.id,
        MappingRunRetryCreate(idempotency_key="p305b-retry-child"),
        actor,
    )
    replay, replay_created = mapping_execution_service.retry(
        db,
        organization_id,
        failed.id,
        MappingRunRetryCreate(idempotency_key="p305b-retry-child"),
        actor,
    )

    assert failed.status == MappingRunStatus.FAILED.value
    assert failed.failed_at is not None
    assert created is True and replay_created is False and replay.id == child.id
    assert child.retry_of_run_id == failed.id
    assert child.root_run_id == failed.id
    assert child.attempt_number == 2
    parent_input = db.scalar(
        select(MappingRunInput).where(MappingRunInput.mapping_run_id == failed.id)
    )
    child_input = db.scalar(
        select(MappingRunInput).where(MappingRunInput.mapping_run_id == child.id)
    )
    assert parent_input is not None and child_input is not None
    assert child_input.values_json == parent_input.values_json
    assert child_input.raw_record_reference_id == parent_input.raw_record_reference_id


def test_retry_rejections_and_single_direct_child(db: Session) -> None:
    organization_id, actor, request = _setup(db, "p305b-retry-guard")
    run, _ = mapping_execution_service.submit(db, organization_id, request, actor)
    with pytest.raises(CanonicalMappingServiceError) as active:
        mapping_execution_service.retry(
            db, organization_id, run.id, MappingRunRetryCreate(idempotency_key="active"), actor
        )
    assert active.value.code == "MAPPING_RUN_ACTIVE"
    mapping_execution_service.fail(
        db, organization_id, run.id, "MAPPING_EXECUTION_TRANSIENT_FAILURE", "Temporary", True
    )
    mapping_execution_service.retry(
        db, organization_id, run.id, MappingRunRetryCreate(idempotency_key="first"), actor
    )
    with pytest.raises(CanonicalMappingServiceError) as sibling:
        mapping_execution_service.retry(
            db, organization_id, run.id, MappingRunRetryCreate(idempotency_key="second"), actor
        )
    assert sibling.value.code == "MAPPING_RUN_RETRY_ALREADY_CREATED"


def test_list_is_tenant_scoped_filtered_paginated_and_read_only(db: Session) -> None:
    organization_id, actor, request = _setup(db, "p305b-list")
    first, _ = mapping_execution_service.submit(db, organization_id, request, actor)
    second, _ = mapping_execution_service.submit(
        db,
        organization_id,
        request.model_copy(update={"idempotency_key": "p305b-list-second"}),
        actor,
    )
    foreign_id, foreign_actor, foreign_request = _setup(db, "p305b-list-foreign")
    mapping_execution_service.submit(db, foreign_id, foreign_request, foreign_actor)
    before = db.scalar(select(func.count()).select_from(MappingRun))

    page = mapping_execution_service.list_runs(db, organization_id, 1, 1)
    filtered = mapping_execution_service.list_runs(
        db, organization_id, 1, 50, template_version_id=request.template_version_id
    )

    assert page.total == 2 and len(page.items) == 1
    assert page.items[0].id == second.id
    assert [item.id for item in filtered.items] == [second.id, first.id]
    assert db.scalar(select(func.count()).select_from(MappingRun)) == before


def test_list_uses_id_as_deterministic_tie_breaker(db: Session) -> None:
    organization_id, actor, request = _setup(db, "p305b-list-tie")
    tied_at = datetime(2026, 2, 1, tzinfo=UTC)
    rows = [
        MappingRun(
            id=UUID(int=value),
            organization_id=organization_id,
            dataset_version_id=request.dataset_version_id,
            template_version_id=request.template_version_id,
            source_schema_id=request.source_schema_id,
            status=MappingRunStatus.QUEUED.value,
            idempotency_key=f"tie-{value}",
            request_fingerprint=str(value) * 64,
            created_by_user_id=actor,
            created_at=tied_at,
            updated_at=tied_at,
        )
        for value in (2, 1)
    ]
    db.add_all(rows)
    db.commit()

    page = mapping_execution_service.list_runs(db, organization_id, 1, 50)

    assert [item.id for item in page.items[:2]] == [UUID(int=2), UUID(int=1)]
