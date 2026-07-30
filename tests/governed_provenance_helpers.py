from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ingestion import Dataset, DatasetVersion, IngestionBatch


def add_eligible_dataset_version(
    db: Session,
    organization_id: UUID,
    source_system_id: UUID,
    dataset_id: UUID,
    actor_user_id: UUID,
    *,
    checksum: str = "a" * 64,
) -> DatasetVersion:
    dataset = db.get(Dataset, dataset_id)
    assert dataset is not None
    dataset.status = "active"
    batch = IngestionBatch(
        organization_id=organization_id,
        source_system_id=source_system_id,
        batch_number=f"governed-{uuid4().hex}",
        ingestion_method="api",
        status="completed",
        trigger_type="manual",
        submitted_by_user_id=actor_user_id,
        checksum=checksum,
    )
    db.add(batch)
    db.flush()
    next_version = (
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
        ingestion_batch_id=batch.id,
        version_number=next_version,
        status="accepted",
        source_file_checksum=checksum,
        record_count=10,
        accepted_record_count=10,
        rejected_record_count=0,
    )
    db.add(version)
    db.commit()
    return version
