from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ingestion import (
    Dataset,
    DatasetStatus,
    DatasetVersion,
    DatasetVersionStatus,
    IngestionBatch,
    IngestionBatchStatus,
)


class GovernedProvenanceError(ValueError):
    def __init__(self, code: str, message: str, http_status: int = 422) -> None:
        self.code = code
        self.http_status = http_status
        super().__init__(message)


@dataclass(frozen=True)
class GovernedDatasetProvenance:
    dataset_id: UUID
    dataset_version_id: UUID
    ingestion_batch_id: UUID
    source_system_id: UUID
    dataset_reference: str
    dataset_fingerprint: str
    source_lineage_reference: str

    def identity(self) -> dict[str, str]:
        return {
            "dataset_id": str(self.dataset_id),
            "dataset_version_id": str(self.dataset_version_id),
            "ingestion_batch_id": str(self.ingestion_batch_id),
            "source_system_id": str(self.source_system_id),
            "dataset_reference": self.dataset_reference,
            "dataset_fingerprint": self.dataset_fingerprint,
            "source_lineage_reference": self.source_lineage_reference,
        }


class GovernedDatasetProvenanceService:
    eligible_dataset_versions = {
        DatasetVersionStatus.ACCEPTED.value,
        DatasetVersionStatus.PARTIALLY_ACCEPTED.value,
        DatasetVersionStatus.PROCESSED.value,
    }
    eligible_ingestion_batches = {
        IngestionBatchStatus.PARTIALLY_COMPLETED.value,
        IngestionBatchStatus.COMPLETED.value,
    }

    def resolve(
        self,
        db: Session,
        organization_id: UUID,
        dataset_id: UUID,
        dataset_version_id: UUID,
    ) -> GovernedDatasetProvenance:
        dataset = db.scalar(
            select(Dataset).where(
                Dataset.id == dataset_id,
                Dataset.organization_id == organization_id,
            )
        )
        if dataset is None:
            raise GovernedProvenanceError(
                "DATASET_NOT_FOUND",
                "Governed dataset is not eligible",
                404,
            )
        version = db.scalar(
            select(DatasetVersion).where(
                DatasetVersion.id == dataset_version_id,
                DatasetVersion.organization_id == organization_id,
                DatasetVersion.dataset_id == dataset.id,
            )
        )
        if version is None:
            raise GovernedProvenanceError(
                "DATASET_VERSION_NOT_FOUND",
                "Governed dataset version is not eligible",
                404,
            )
        batch = db.scalar(
            select(IngestionBatch).where(
                IngestionBatch.id == version.ingestion_batch_id,
                IngestionBatch.organization_id == organization_id,
            )
        )
        if batch is None:
            raise GovernedProvenanceError(
                "INGESTION_BATCH_NOT_FOUND",
                "Governed ingestion batch is not eligible",
                404,
            )
        if dataset.status != DatasetStatus.ACTIVE.value:
            raise GovernedProvenanceError(
                "DATASET_NOT_ELIGIBLE",
                "Governed dataset is not active",
            )
        if version.status not in self.eligible_dataset_versions:
            raise GovernedProvenanceError(
                "DATASET_VERSION_NOT_ELIGIBLE",
                "Governed dataset version is not execution eligible",
            )
        if batch.status not in self.eligible_ingestion_batches:
            raise GovernedProvenanceError(
                "INGESTION_BATCH_NOT_ELIGIBLE",
                "Governed ingestion batch is not execution eligible",
            )
        if dataset.source_system_id != batch.source_system_id:
            raise GovernedProvenanceError(
                "SOURCE_SYSTEM_MISMATCH",
                "Dataset source does not match the selected version ingestion source",
            )
        fingerprint = self._fingerprint(version)
        lineage_reference = (
            f"dataset:{dataset.id}:version:{version.id}:"
            f"batch:{batch.id}:source:{batch.source_system_id}"
        )
        return GovernedDatasetProvenance(
            dataset_id=dataset.id,
            dataset_version_id=version.id,
            ingestion_batch_id=batch.id,
            source_system_id=batch.source_system_id,
            dataset_reference=dataset.code,
            dataset_fingerprint=fingerprint,
            source_lineage_reference=lineage_reference,
        )

    @staticmethod
    def _fingerprint(version: DatasetVersion) -> str:
        if version.source_file_checksum:
            checksum = version.source_file_checksum.strip().lower()
            if len(checksum) == 64 and all(
                character in "0123456789abcdef" for character in checksum
            ):
                return checksum
            return hashlib.sha256(checksum.encode("utf-8")).hexdigest()
        payload = {
            "dataset_version_id": str(version.id),
            "version_number": version.version_number,
            "schema_fingerprint": version.schema_fingerprint,
            "storage_reference": version.storage_reference,
            "record_count": version.record_count,
            "accepted_record_count": version.accepted_record_count,
            "rejected_record_count": version.rejected_record_count,
        }
        serialized = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(serialized).hexdigest()


governed_dataset_provenance_service = GovernedDatasetProvenanceService()
