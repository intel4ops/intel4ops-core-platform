from __future__ import annotations

import logging
import signal
import socket
import threading
from datetime import timedelta
from time import monotonic
from types import FrameType
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.db.session import SessionLocal, engine
from app.services.canonical_mapping_service import (
    MappingExecutionClaim,
    MappingExecutionLeaseLost,
    mapping_execution_service,
)

logger = logging.getLogger("intel4ops.mapping_worker")


def worker_identity(settings: Settings) -> str:
    return settings.mapping_worker_id or f"{socket.gethostname()}-{uuid4()}"


class HeartbeatPump:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        claim: MappingExecutionClaim,
        interval_seconds: float,
    ) -> None:
        self.session_factory = session_factory
        self.claim = claim
        self.interval_seconds = interval_seconds
        self.stop_event = threading.Event()
        self.lease_lost = threading.Event()
        self.thread = threading.Thread(target=self._run, name="mapping-heartbeat", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=self.interval_seconds + 1)

    def _run(self) -> None:
        while not self.stop_event.wait(self.interval_seconds):
            try:
                with self.session_factory() as db:
                    if not mapping_execution_service.heartbeat(db, self.claim):
                        self.lease_lost.set()
                        return
            except SQLAlchemyError:
                logger.exception(
                    "mapping_worker_heartbeat_database_error",
                    extra={
                        "worker_id": self.claim.worker_id,
                        "mapping_run_id": str(self.claim.run_id),
                    },
                )


class MappingExecutionWorker:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session] = SessionLocal,
        stop_event: threading.Event | None = None,
    ) -> None:
        if (
            settings.mapping_worker_heartbeat_interval_seconds
            >= settings.mapping_worker_stale_threshold_seconds
        ):
            raise ValueError("Mapping worker heartbeat interval must be below stale threshold")
        self.settings = settings
        self.session_factory = session_factory
        self.stop_event = stop_event or threading.Event()
        self.worker_id = worker_identity(settings)

    def recover_stale_once(self) -> int:
        with self.session_factory() as db:
            recovered = mapping_execution_service.recover_stale(
                db,
                timedelta(seconds=self.settings.mapping_worker_stale_threshold_seconds),
            )
        for organization_id, run_id in recovered:
            logger.warning(
                "mapping_worker_stale_run_recovered",
                extra={
                    "worker_id": self.worker_id,
                    "organization_id": str(organization_id),
                    "mapping_run_id": str(run_id),
                },
            )
        return len(recovered)

    def process_one(self) -> bool:
        if self.stop_event.is_set():
            return False
        with self.session_factory() as db:
            claim = mapping_execution_service.claim_next(db, self.worker_id)
        if claim is None:
            return False
        logger.info(
            "mapping_worker_run_claimed",
            extra={
                "worker_id": self.worker_id,
                "organization_id": str(claim.organization_id),
                "mapping_run_id": str(claim.run_id),
            },
        )
        started = monotonic()
        heartbeat = HeartbeatPump(
            self.session_factory,
            claim,
            self.settings.mapping_worker_heartbeat_interval_seconds,
        )
        heartbeat.start()
        try:
            with self.session_factory() as db:
                run = mapping_execution_service.execute_claimed(db, claim)
            event = (
                "mapping_worker_run_completed"
                if run.status != "failed"
                else "mapping_worker_run_failed"
            )
            logger.info(
                event,
                extra={
                    "worker_id": self.worker_id,
                    "organization_id": str(claim.organization_id),
                    "mapping_run_id": str(claim.run_id),
                    "correlation_id": run.correlation_id,
                    "execution_duration_seconds": monotonic() - started,
                },
            )
        except MappingExecutionLeaseLost:
            logger.warning(
                "mapping_worker_lease_lost",
                extra={
                    "worker_id": self.worker_id,
                    "organization_id": str(claim.organization_id),
                    "mapping_run_id": str(claim.run_id),
                },
            )
        finally:
            heartbeat.stop()
        return True

    def run(self) -> None:
        self.recover_stale_once()
        while not self.stop_event.is_set():
            try:
                processed = self.process_one()
                delay = 0 if processed else self.settings.mapping_worker_poll_interval_seconds
            except SQLAlchemyError:
                logger.exception(
                    "mapping_worker_database_error", extra={"worker_id": self.worker_id}
                )
                delay = self.settings.mapping_worker_db_backoff_seconds
            self.stop_event.wait(delay)


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    stop_event = threading.Event()

    def request_shutdown(_signum: int, _frame: FrameType | None) -> None:
        logger.info("mapping_worker_shutdown_requested")
        stop_event.set()

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    worker = MappingExecutionWorker(settings, stop_event=stop_event)
    logger.info("mapping_worker_started", extra={"worker_id": worker.worker_id})
    worker.run()
    logger.info("mapping_worker_stopped", extra={"worker_id": worker.worker_id})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
