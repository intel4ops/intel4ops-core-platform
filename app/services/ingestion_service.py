from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import utc_now
from app.models.ingestion import (
    Dataset,
    DatasetStatus,
    DatasetType,
    DatasetVersion,
    DatasetVersionStatus,
    IngestionBatch,
    IngestionBatchStatus,
    IngestionMethod,
    SchemaStatus,
    TriggerType,
)
from app.models.source_system import (
    DOWNSTREAM_CREATION_SOURCE_STATUSES,
    DataClassification,
    SourceSystem,
)
from app.schemas.ingestion import (
    BatchCountsUpdate,
    DatasetCreate,
    DatasetUpdate,
    DatasetVersionCountsUpdate,
    DatasetVersionCreate,
    DatasetVersionMetadataUpdate,
    IngestionBatchCreate,
)


class IngestionNotFoundError(ValueError):
    pass


class IngestionTenantMismatchError(ValueError):
    pass


class IngestionConflictError(ValueError):
    pass


class InvalidIngestionTransitionError(ValueError):
    pass


BATCH_TRANSITIONS: dict[IngestionBatchStatus, set[IngestionBatchStatus]] = {
    IngestionBatchStatus.RECEIVED: {
        IngestionBatchStatus.QUEUED,
        IngestionBatchStatus.VALIDATING,
        IngestionBatchStatus.CANCELLED,
    },
    IngestionBatchStatus.QUEUED: {
        IngestionBatchStatus.VALIDATING,
        IngestionBatchStatus.CANCELLED,
    },
    IngestionBatchStatus.VALIDATING: {
        IngestionBatchStatus.PROCESSING,
        IngestionBatchStatus.QUARANTINED,
        IngestionBatchStatus.FAILED,
    },
    IngestionBatchStatus.PROCESSING: {
        IngestionBatchStatus.COMPLETED,
        IngestionBatchStatus.PARTIALLY_COMPLETED,
        IngestionBatchStatus.FAILED,
        IngestionBatchStatus.QUARANTINED,
    },
    IngestionBatchStatus.PARTIALLY_COMPLETED: {
        IngestionBatchStatus.COMPLETED,
        IngestionBatchStatus.FAILED,
    },
    IngestionBatchStatus.FAILED: {IngestionBatchStatus.QUEUED},
    IngestionBatchStatus.QUARANTINED: {
        IngestionBatchStatus.QUEUED,
        IngestionBatchStatus.CANCELLED,
    },
    IngestionBatchStatus.COMPLETED: set(),
    IngestionBatchStatus.CANCELLED: set(),
}

DATASET_TRANSITIONS: dict[DatasetStatus, set[DatasetStatus]] = {
    DatasetStatus.DRAFT: {DatasetStatus.ACTIVE, DatasetStatus.DECOMMISSIONED},
    DatasetStatus.ACTIVE: {
        DatasetStatus.PAUSED,
        DatasetStatus.DEPRECATED,
        DatasetStatus.DECOMMISSIONED,
    },
    DatasetStatus.PAUSED: {
        DatasetStatus.ACTIVE,
        DatasetStatus.DEPRECATED,
        DatasetStatus.DECOMMISSIONED,
    },
    DatasetStatus.DEPRECATED: {DatasetStatus.DECOMMISSIONED},
    DatasetStatus.DECOMMISSIONED: set(),
}

VERSION_TRANSITIONS: dict[DatasetVersionStatus, set[DatasetVersionStatus]] = {
    DatasetVersionStatus.RECEIVED: {DatasetVersionStatus.VALIDATING},
    DatasetVersionStatus.VALIDATING: {
        DatasetVersionStatus.ACCEPTED,
        DatasetVersionStatus.PARTIALLY_ACCEPTED,
        DatasetVersionStatus.REJECTED,
        DatasetVersionStatus.QUARANTINED,
        DatasetVersionStatus.FAILED,
    },
    DatasetVersionStatus.ACCEPTED: {DatasetVersionStatus.PROCESSED},
    DatasetVersionStatus.PARTIALLY_ACCEPTED: {
        DatasetVersionStatus.PROCESSED,
        DatasetVersionStatus.FAILED,
    },
    DatasetVersionStatus.QUARANTINED: {DatasetVersionStatus.VALIDATING},
    DatasetVersionStatus.FAILED: {DatasetVersionStatus.VALIDATING},
    DatasetVersionStatus.REJECTED: set(),
    DatasetVersionStatus.PROCESSED: set(),
}


def source_for_organization(
    db: Session, organization_id: UUID, source_system_id: UUID
) -> SourceSystem:
    source = db.scalar(
        select(SourceSystem).where(
            SourceSystem.id == source_system_id,
            SourceSystem.organization_id == organization_id,
        )
    )
    if source is None:
        raise IngestionTenantMismatchError("Source system not found in organization")
    return source


def source_for_downstream_creation(
    db: Session, organization_id: UUID, source_system_id: UUID
) -> SourceSystem:
    source = source_for_organization(db, organization_id, source_system_id)
    if source.status not in DOWNSTREAM_CREATION_SOURCE_STATUSES:
        raise IngestionConflictError(
            f"Source system status '{source.status}' does not permit new downstream data"
        )
    return source


class IngestionBatchService:
    immutable_idempotency_fields = (
        "source_system_id",
        "batch_number",
        "ingestion_method",
        "trigger_type",
        "external_batch_id",
        "source_period_start",
        "source_period_end",
    )

    def create(
        self,
        db: Session,
        organization_id: UUID,
        payload: IngestionBatchCreate,
        actor_user_id: UUID,
    ) -> IngestionBatch:
        source_for_downstream_creation(db, organization_id, payload.source_system_id)
        if payload.idempotency_key:
            existing = db.scalar(
                select(IngestionBatch).where(
                    IngestionBatch.organization_id == organization_id,
                    IngestionBatch.idempotency_key == payload.idempotency_key,
                )
            )
            if existing is not None:
                if self._equivalent(existing, payload):
                    return existing
                raise IngestionConflictError("Idempotency key conflicts with an existing batch")
        duplicate = db.scalar(
            select(IngestionBatch.id).where(
                IngestionBatch.organization_id == organization_id,
                IngestionBatch.batch_number == payload.batch_number,
            )
        )
        if duplicate is not None:
            raise IngestionConflictError("Batch number already exists")
        batch = IngestionBatch(
            organization_id=organization_id,
            submitted_by_user_id=actor_user_id,
            **payload.model_dump(),
        )
        db.add(batch)
        self._commit(db, batch)
        return batch

    def list(
        self,
        db: Session,
        organization_id: UUID,
        *,
        source_system_id: UUID | None = None,
        status: IngestionBatchStatus | None = None,
        ingestion_method: IngestionMethod | None = None,
        trigger_type: TriggerType | None = None,
        received_from: datetime | None = None,
        received_to: datetime | None = None,
        correlation_id: str | None = None,
        external_batch_id: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[IngestionBatch]:
        statement = select(IngestionBatch).where(IngestionBatch.organization_id == organization_id)
        filters = {
            IngestionBatch.source_system_id: source_system_id,
            IngestionBatch.status: status.value if status else None,
            IngestionBatch.ingestion_method: (ingestion_method.value if ingestion_method else None),
            IngestionBatch.trigger_type: trigger_type.value if trigger_type else None,
            IngestionBatch.correlation_id: correlation_id,
            IngestionBatch.external_batch_id: external_batch_id,
        }
        for column, value in filters.items():
            if value is not None:
                statement = statement.where(column == value)
        if received_from is not None:
            statement = statement.where(IngestionBatch.received_at >= received_from)
        if received_to is not None:
            statement = statement.where(IngestionBatch.received_at <= received_to)
        statement = (
            statement.order_by(IngestionBatch.received_at.desc(), IngestionBatch.id)
            .offset(offset)
            .limit(limit)
        )
        return list(db.scalars(statement).all())

    def get(
        self,
        db: Session,
        organization_id: UUID,
        batch_id: UUID,
        *,
        for_update: bool = False,
    ) -> IngestionBatch:
        statement = select(IngestionBatch).where(
            IngestionBatch.id == batch_id,
            IngestionBatch.organization_id == organization_id,
        )
        if for_update:
            statement = statement.with_for_update()
        batch = db.scalar(statement)
        if batch is None:
            raise IngestionNotFoundError("Ingestion batch not found")
        return batch

    def transition(
        self,
        db: Session,
        organization_id: UUID,
        batch_id: UUID,
        target: IngestionBatchStatus,
    ) -> IngestionBatch:
        batch = self.get(db, organization_id, batch_id, for_update=True)
        self._transition(batch, target)
        self._commit(db, batch)
        return batch

    def retry(self, db: Session, organization_id: UUID, batch_id: UUID) -> IngestionBatch:
        return self.transition(db, organization_id, batch_id, IngestionBatchStatus.QUEUED)

    def quarantine(self, db: Session, organization_id: UUID, batch_id: UUID) -> IngestionBatch:
        return self.transition(db, organization_id, batch_id, IngestionBatchStatus.QUARANTINED)

    def release(self, db: Session, organization_id: UUID, batch_id: UUID) -> IngestionBatch:
        return self.transition(db, organization_id, batch_id, IngestionBatchStatus.QUEUED)

    def cancel(self, db: Session, organization_id: UUID, batch_id: UUID) -> IngestionBatch:
        return self.transition(db, organization_id, batch_id, IngestionBatchStatus.CANCELLED)

    def update_counts(
        self,
        db: Session,
        organization_id: UUID,
        batch_id: UUID,
        payload: BatchCountsUpdate,
    ) -> IngestionBatch:
        batch = self.get(db, organization_id, batch_id, for_update=True)
        self._ensure_mutable(batch)
        for field, value in payload.model_dump().items():
            setattr(batch, field, value)
        self._commit(db, batch)
        return batch

    def record_failure(
        self,
        db: Session,
        organization_id: UUID,
        batch_id: UUID,
        failure_code: str,
        failure_summary: str,
    ) -> IngestionBatch:
        batch = self.get(db, organization_id, batch_id, for_update=True)
        self._transition(batch, IngestionBatchStatus.FAILED)
        batch.failure_code = failure_code
        batch.failure_summary = failure_summary
        self._commit(db, batch)
        return batch

    def recalculate(self, db: Session, organization_id: UUID, batch_id: UUID) -> IngestionBatch:
        batch = self.get(db, organization_id, batch_id, for_update=True)
        self._ensure_mutable(batch)
        self._apply_reconciliation(db, organization_id, batch)
        self._commit(db, batch)
        return batch

    @staticmethod
    def _apply_reconciliation(db: Session, organization_id: UUID, batch: IngestionBatch) -> None:
        totals = db.execute(
            select(
                func.count(DatasetVersion.id),
                func.coalesce(func.sum(DatasetVersion.record_count), 0),
                func.coalesce(func.sum(DatasetVersion.accepted_record_count), 0),
                func.coalesce(func.sum(DatasetVersion.rejected_record_count), 0),
            ).where(
                DatasetVersion.organization_id == organization_id,
                DatasetVersion.ingestion_batch_id == batch.id,
            )
        ).one()
        (
            batch.actual_dataset_count,
            batch.actual_record_count,
            batch.accepted_record_count,
            batch.rejected_record_count,
        ) = (int(value) for value in totals)

    @classmethod
    def _equivalent(cls, existing: IngestionBatch, payload: IngestionBatchCreate) -> bool:
        values = payload.model_dump()
        return all(
            cls._identity_value(getattr(existing, field)) == cls._identity_value(values[field])
            for field in cls.immutable_idempotency_fields
        )

    @staticmethod
    def _identity_value(value: object) -> object:
        if hasattr(value, "value"):
            return value.value
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=UTC)
            return value.astimezone(UTC)
        return value

    @staticmethod
    def _transition(batch: IngestionBatch, target: IngestionBatchStatus) -> None:
        current = IngestionBatchStatus(batch.status)
        if target not in BATCH_TRANSITIONS[current]:
            raise InvalidIngestionTransitionError(
                f"Cannot transition batch from {current.value} to {target.value}"
            )
        now = utc_now()
        batch.status = target.value
        if (
            target
            in {
                IngestionBatchStatus.VALIDATING,
                IngestionBatchStatus.PROCESSING,
            }
            and batch.started_at is None
        ):
            batch.started_at = now
        if target in {
            IngestionBatchStatus.COMPLETED,
            IngestionBatchStatus.PARTIALLY_COMPLETED,
        }:
            batch.completed_at = now
        if target is IngestionBatchStatus.FAILED:
            batch.failed_at = now
        elif target is IngestionBatchStatus.QUEUED:
            batch.failed_at = None

    @staticmethod
    def _ensure_mutable(batch: IngestionBatch) -> None:
        if batch.status in {
            IngestionBatchStatus.COMPLETED.value,
            IngestionBatchStatus.CANCELLED.value,
        }:
            raise InvalidIngestionTransitionError(
                "Completed or cancelled batches cannot be modified"
            )

    @staticmethod
    def _commit(db: Session, batch: IngestionBatch) -> None:
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise IngestionConflictError("Ingestion batch conflicts with existing data") from exc
        db.refresh(batch)


class DatasetService:
    def create(
        self,
        db: Session,
        organization_id: UUID,
        payload: DatasetCreate,
        actor_user_id: UUID,
    ) -> Dataset:
        source_for_downstream_creation(db, organization_id, payload.source_system_id)
        if db.scalar(
            select(Dataset.id).where(
                Dataset.organization_id == organization_id,
                Dataset.code == payload.code,
            )
        ):
            raise IngestionConflictError("Dataset code already exists")
        dataset = Dataset(
            organization_id=organization_id,
            created_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
            **payload.model_dump(),
        )
        db.add(dataset)
        self._commit(db, dataset)
        return dataset

    def list(
        self,
        db: Session,
        organization_id: UUID,
        *,
        source_system_id: UUID | None = None,
        domain: str | None = None,
        dataset_type: DatasetType | None = None,
        status: DatasetStatus | None = None,
        sensitivity: DataClassification | None = None,
        schema_status: SchemaStatus | None = None,
        search: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Dataset]:
        statement = select(Dataset).where(Dataset.organization_id == organization_id)
        filters = {
            Dataset.source_system_id: source_system_id,
            Dataset.domain: domain,
            Dataset.dataset_type: dataset_type.value if dataset_type else None,
            Dataset.status: status.value if status else None,
            Dataset.sensitivity: sensitivity.value if sensitivity else None,
            Dataset.schema_status: schema_status.value if schema_status else None,
        }
        for column, value in filters.items():
            if value is not None:
                statement = statement.where(column == value)
        if search:
            term = f"%{search.strip()}%"
            statement = statement.where(or_(Dataset.name.ilike(term), Dataset.code.ilike(term)))
        return list(
            db.scalars(
                statement.order_by(Dataset.name, Dataset.id).offset(offset).limit(limit)
            ).all()
        )

    def get(
        self,
        db: Session,
        organization_id: UUID,
        dataset_id: UUID,
        *,
        for_update: bool = False,
    ) -> Dataset:
        statement = select(Dataset).where(
            Dataset.id == dataset_id, Dataset.organization_id == organization_id
        )
        if for_update:
            statement = statement.with_for_update()
        dataset = db.scalar(statement)
        if dataset is None:
            raise IngestionNotFoundError("Dataset not found")
        return dataset

    def update(
        self,
        db: Session,
        organization_id: UUID,
        dataset_id: UUID,
        payload: DatasetUpdate,
        actor_user_id: UUID,
    ) -> Dataset:
        dataset = self.get(db, organization_id, dataset_id, for_update=True)
        if dataset.status == DatasetStatus.DECOMMISSIONED.value:
            raise InvalidIngestionTransitionError("Decommissioned datasets cannot be modified")
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(dataset, field, value)
        dataset.updated_by_user_id = actor_user_id
        self._commit(db, dataset)
        return dataset

    def transition(
        self,
        db: Session,
        organization_id: UUID,
        dataset_id: UUID,
        target: DatasetStatus,
        actor_user_id: UUID,
    ) -> Dataset:
        dataset = self.get(db, organization_id, dataset_id, for_update=True)
        current = DatasetStatus(dataset.status)
        if target not in DATASET_TRANSITIONS[current]:
            raise InvalidIngestionTransitionError(
                f"Cannot transition dataset from {current.value} to {target.value}"
            )
        dataset.status = target.value
        dataset.updated_by_user_id = actor_user_id
        if target is DatasetStatus.DECOMMISSIONED:
            dataset.deactivated_at = utc_now()
        self._commit(db, dataset)
        return dataset

    @staticmethod
    def _commit(db: Session, dataset: Dataset) -> None:
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise IngestionConflictError("Dataset conflicts with existing data") from exc
        db.refresh(dataset)


class DatasetVersionService:
    def __init__(
        self,
        dataset_service: DatasetService | None = None,
        batch_service: IngestionBatchService | None = None,
    ) -> None:
        self.dataset_service = dataset_service or DatasetService()
        self.batch_service = batch_service or IngestionBatchService()

    def create(
        self,
        db: Session,
        organization_id: UUID,
        dataset_id: UUID,
        payload: DatasetVersionCreate,
    ) -> DatasetVersion:
        dataset = self.dataset_service.get(db, organization_id, dataset_id, for_update=True)
        batch = self.batch_service.get(
            db, organization_id, payload.ingestion_batch_id, for_update=True
        )
        self.batch_service._ensure_mutable(batch)
        if dataset.source_system_id != batch.source_system_id:
            raise IngestionTenantMismatchError("Dataset and batch source systems must match")
        source_for_downstream_creation(db, organization_id, dataset.source_system_id)
        if db.scalar(
            select(DatasetVersion.id).where(
                DatasetVersion.organization_id == organization_id,
                DatasetVersion.dataset_id == dataset_id,
                DatasetVersion.ingestion_batch_id == batch.id,
            )
        ):
            raise IngestionConflictError("Dataset already has a version in this ingestion batch")
        next_number = (
            db.scalar(
                select(func.max(DatasetVersion.version_number)).where(
                    DatasetVersion.dataset_id == dataset_id
                )
            )
            or 0
        ) + 1
        version = DatasetVersion(
            organization_id=organization_id,
            dataset_id=dataset_id,
            version_number=next_number,
            **payload.model_dump(),
        )
        db.add(version)
        try:
            db.flush()
            self.batch_service._apply_reconciliation(db, organization_id, batch)
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise IngestionConflictError("Dataset version already exists") from exc
        db.refresh(version)
        return version

    def list(
        self,
        db: Session,
        organization_id: UUID,
        *,
        dataset_id: UUID | None = None,
        ingestion_batch_id: UUID | None = None,
        status: DatasetVersionStatus | None = None,
        received_from: datetime | None = None,
        received_to: datetime | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[DatasetVersion]:
        statement = select(DatasetVersion).where(DatasetVersion.organization_id == organization_id)
        if dataset_id is not None:
            statement = statement.where(DatasetVersion.dataset_id == dataset_id)
        if ingestion_batch_id is not None:
            statement = statement.where(DatasetVersion.ingestion_batch_id == ingestion_batch_id)
        if status is not None:
            statement = statement.where(DatasetVersion.status == status.value)
        if received_from is not None:
            statement = statement.where(DatasetVersion.received_at >= received_from)
        if received_to is not None:
            statement = statement.where(DatasetVersion.received_at <= received_to)
        return list(
            db.scalars(
                statement.order_by(DatasetVersion.received_at, DatasetVersion.version_number)
                .offset(offset)
                .limit(limit)
            ).all()
        )

    def get(
        self,
        db: Session,
        organization_id: UUID,
        dataset_id: UUID,
        version_id: UUID,
        *,
        for_update: bool = False,
    ) -> DatasetVersion:
        statement = select(DatasetVersion).where(
            DatasetVersion.id == version_id,
            DatasetVersion.dataset_id == dataset_id,
            DatasetVersion.organization_id == organization_id,
        )
        if for_update:
            statement = statement.with_for_update()
        version = db.scalar(statement)
        if version is None:
            raise IngestionNotFoundError("Dataset version not found")
        return version

    def update_counts(
        self,
        db: Session,
        organization_id: UUID,
        dataset_id: UUID,
        version_id: UUID,
        payload: DatasetVersionCountsUpdate,
    ) -> DatasetVersion:
        version = self.get(db, organization_id, dataset_id, version_id, for_update=True)
        self._ensure_mutable(version)
        batch = self.batch_service.get(
            db, organization_id, version.ingestion_batch_id, for_update=True
        )
        self.batch_service._ensure_mutable(batch)
        for field, value in payload.model_dump().items():
            setattr(version, field, value)
        db.flush()
        self.batch_service._apply_reconciliation(db, organization_id, batch)
        db.commit()
        db.refresh(version)
        return version

    def update_metadata(
        self,
        db: Session,
        organization_id: UUID,
        dataset_id: UUID,
        version_id: UUID,
        payload: DatasetVersionMetadataUpdate,
    ) -> DatasetVersion:
        version = self.get(db, organization_id, dataset_id, version_id, for_update=True)
        self._ensure_mutable(version)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(version, field, value)
        db.commit()
        db.refresh(version)
        return version

    def transition(
        self,
        db: Session,
        organization_id: UUID,
        dataset_id: UUID,
        version_id: UUID,
        target: DatasetVersionStatus,
    ) -> DatasetVersion:
        version = self.get(db, organization_id, dataset_id, version_id, for_update=True)
        current = DatasetVersionStatus(version.status)
        if target not in VERSION_TRANSITIONS[current]:
            raise InvalidIngestionTransitionError(
                f"Cannot transition dataset version from {current.value} to {target.value}"
            )
        version.status = target.value
        if target is DatasetVersionStatus.PROCESSED:
            version.processed_at = utc_now()
        db.commit()
        db.refresh(version)
        return version

    @staticmethod
    def _ensure_mutable(version: DatasetVersion) -> None:
        if version.status in {
            DatasetVersionStatus.PROCESSED.value,
            DatasetVersionStatus.REJECTED.value,
        }:
            raise InvalidIngestionTransitionError(
                "Processed or rejected dataset versions cannot be modified"
            )


ingestion_batch_service = IngestionBatchService()
dataset_service = DatasetService()
dataset_version_service = DatasetVersionService(dataset_service, ingestion_batch_service)
