from datetime import timedelta
from threading import Event
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from test_mapping_execution_contract import _setup

from app.core.config import Settings
from app.models.canonical_mapping import MappingRun, MappingRunStatus
from app.services.canonical_mapping_service import MappingExecutionClaim, mapping_execution_service
from app.workers.mapping_execution import MappingExecutionWorker, worker_identity


def test_claim_persists_lease_worker_and_oldest_first(db: Session) -> None:
    organization_id, actor, first_request = _setup(db, "p305c-first")
    first, _ = mapping_execution_service.submit(db, organization_id, first_request, actor)
    second_organization_id, actor_two, second_request = _setup(db, "p305c-second")
    mapping_execution_service.submit(db, second_organization_id, second_request, actor_two)

    claim = mapping_execution_service.claim_next(db, "worker-a")

    assert claim is not None
    assert claim.run_id == first.id
    persisted = db.get(MappingRun, first.id)
    assert persisted is not None
    assert persisted.status == MappingRunStatus.RUNNING.value
    assert persisted.execution_worker_id == "worker-a"
    assert persisted.execution_lease_id == claim.lease_id
    assert persisted.execution_claimed_at is not None
    assert persisted.heartbeat_at is not None


def test_heartbeat_is_fenced_by_lease(db: Session) -> None:
    organization_id, actor, request = _setup(db, "p305c-heartbeat")
    run, _ = mapping_execution_service.submit(db, organization_id, request, actor)
    claim = mapping_execution_service.claim_run(db, organization_id, run.id, "worker-a")
    wrong = MappingExecutionClaim(run.id, organization_id, uuid4(), "worker-b")

    assert mapping_execution_service.heartbeat(db, wrong) is False
    assert mapping_execution_service.heartbeat(db, claim) is True


def test_terminal_rows_are_not_discovered(db: Session) -> None:
    organization_id, actor, request = _setup(db, "p305c-terminal")
    run, _ = mapping_execution_service.submit(db, organization_id, request, actor)
    run.status = MappingRunStatus.FAILED.value
    run.failure_retryable = False
    db.commit()

    assert mapping_execution_service.claim_next(db, "worker-a") is None


def test_worker_stop_prevents_new_claim(db_engine: Engine) -> None:
    factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    with factory() as db:
        organization_id, actor, request = _setup(db, "p305c-stop")
        mapping_execution_service.submit(db, organization_id, request, actor)
    stop = Event()
    stop.set()
    worker = MappingExecutionWorker(Settings(), factory, stop)

    assert worker.process_one() is False
    with factory() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(MappingRun)
                .where(MappingRun.status == MappingRunStatus.RUNNING.value)
            )
            == 0
        )


def test_worker_identity_override_and_configuration_validation() -> None:
    assert worker_identity(Settings(mapping_worker_id="worker-explicit")) == "worker-explicit"
    try:
        MappingExecutionWorker(
            Settings(
                mapping_worker_heartbeat_interval_seconds=60,
                mapping_worker_stale_threshold_seconds=60,
            )
        )
    except ValueError as exc:
        assert "below stale threshold" in str(exc)
    else:
        raise AssertionError("invalid heartbeat/stale configuration was accepted")


def test_stale_threshold_is_configured_as_duration() -> None:
    settings = Settings(mapping_worker_stale_threshold_seconds=90)
    assert timedelta(seconds=settings.mapping_worker_stale_threshold_seconds) == timedelta(
        seconds=90
    )
