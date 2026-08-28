from __future__ import annotations

from uuid import UUID

from app.storage.base import StorageBackend, StorageWriteResult

# Dedicated ground-truth storage namespace, reusing the generic
# StorageBackend/LocalFileStorage abstraction (neutral infrastructure, not
# a production execution module) through its own dedicated key prefix --
# ground truth is never written under a SourceArtifact's key space and
# never touches ArtifactParserRegistry.


def ground_truth_storage_key(organization_id: UUID, simulation_id: UUID, version: int) -> str:
    return f"validation/{organization_id}/{simulation_id}/ground_truth_v{version}"


def write_ground_truth(
    storage: StorageBackend, organization_id: UUID, simulation_id: UUID, version: int, raw: bytes
) -> StorageWriteResult:
    key = ground_truth_storage_key(organization_id, simulation_id, version)
    return storage.write_stream(key, [raw])


def read_ground_truth(storage: StorageBackend, storage_reference: str) -> bytes:
    return b"".join(storage.open_stream(storage_reference))
