from __future__ import annotations

import shutil
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO
from uuid import UUID, uuid4
from zipfile import BadZipFile, ZipFile, is_zipfile

from app.ground_truth_validation.corpus_discovery import (
    ExternalSimulationPackage,
    PackageStatus,
    SimulationCorpusDiscovery,
)


class SimulationPackageStagingError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class StagedSimulationPackage:
    corpus_root: Path
    package: ExternalSimulationPackage


class SimulationPackageStagingService:
    """Validation-plane staging bridge for one sealed Simulation Factory package."""

    _CHUNK_SIZE = 1024 * 1024
    _MAX_MEMBERS = 500

    def __init__(self, storage_root: str | Path, max_uncompressed_bytes: int) -> None:
        self._root = Path(storage_root) / "_simulation_staging"
        self._max_uncompressed_bytes = max_uncompressed_bytes

    def stage_zip(self, organization_id: UUID, source: BinaryIO) -> StagedSimulationPackage:
        incoming = self._root / str(organization_id) / "_incoming" / uuid4().hex
        corpus_root = incoming / "corpus"
        archive_path = incoming / "package.zip"
        corpus_root.mkdir(parents=True, exist_ok=False)

        try:
            self._write_bounded(source, archive_path)
            self._extract_securely(archive_path, corpus_root)
            packages = SimulationCorpusDiscovery().discover(corpus_root)
            if len(packages) != 1:
                raise SimulationPackageStagingError(
                    "INVALID_PACKAGE_COUNT",
                    "The uploaded archive must contain exactly one simulation package",
                    422,
                )
            package = packages[0]
            if package.package_status != PackageStatus.READY:
                raise SimulationPackageStagingError(
                    "PACKAGE_NOT_READY",
                    "Simulation package failed sealed-package validation: "
                    f"{package.package_status.value}: {package.status_detail}",
                    422,
                )
            archive_path.unlink(missing_ok=True)
            return StagedSimulationPackage(corpus_root=corpus_root, package=package)
        except Exception:
            shutil.rmtree(incoming, ignore_errors=True)
            raise

    def finalize_for_batch(
        self, organization_id: UUID, batch_id: UUID, staged_corpus_root: Path
    ) -> Path:
        final_root = self.batch_corpus_root(organization_id, batch_id)
        if final_root.exists():
            raise SimulationPackageStagingError(
                "BATCH_STAGING_EXISTS",
                "A staged package already exists for this simulation batch",
                409,
            )
        final_root.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staged_corpus_root), str(final_root))
        shutil.rmtree(staged_corpus_root.parent, ignore_errors=True)
        return final_root

    def discard_staged(self, staged_corpus_root: Path) -> None:
        shutil.rmtree(staged_corpus_root.parent, ignore_errors=True)

    def batch_corpus_root(self, organization_id: UUID, batch_id: UUID) -> Path:
        return self._root / str(organization_id) / "batches" / str(batch_id) / "corpus"

    def _write_bounded(self, source: BinaryIO, destination: Path) -> None:
        total = 0
        with destination.open("wb") as target:
            while True:
                chunk = source.read(self._CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > self._max_uncompressed_bytes:
                    raise SimulationPackageStagingError(
                        "ARCHIVE_TOO_LARGE",
                        "Uploaded simulation package exceeds the configured size limit",
                        413,
                    )
                target.write(chunk)
        if total == 0:
            raise SimulationPackageStagingError("EMPTY_ARCHIVE", "Uploaded archive is empty", 422)
        if not is_zipfile(destination):
            raise SimulationPackageStagingError(
                "INVALID_ARCHIVE", "Uploaded simulation package must be a ZIP archive", 422
            )

    def _extract_securely(self, archive_path: Path, destination: Path) -> None:
        try:
            with ZipFile(archive_path) as archive:
                members = archive.infolist()
                if len(members) > self._MAX_MEMBERS:
                    raise SimulationPackageStagingError(
                        "ARCHIVE_TOO_MANY_FILES",
                        "Uploaded simulation package contains too many files",
                        422,
                    )
                total_uncompressed = sum(member.file_size for member in members)
                if total_uncompressed > self._max_uncompressed_bytes:
                    raise SimulationPackageStagingError(
                        "ARCHIVE_EXPANDS_TOO_LARGE",
                        "Expanded simulation package exceeds the configured size limit",
                        413,
                    )

                destination_resolved = destination.resolve()
                for member in members:
                    normalized = member.filename.replace("\\", "/")
                    relative = PurePosixPath(normalized)
                    if relative.is_absolute() or ".." in relative.parts:
                        raise SimulationPackageStagingError(
                            "UNSAFE_ARCHIVE_PATH", "Archive contains an unsafe path", 422
                        )
                    unix_mode = (member.external_attr >> 16) & 0xFFFF
                    if stat.S_ISLNK(unix_mode):
                        raise SimulationPackageStagingError(
                            "UNSAFE_ARCHIVE_LINK", "Archive symbolic links are not allowed", 422
                        )
                    if member.is_dir():
                        continue
                    target = (destination / Path(*relative.parts)).resolve()
                    if (
                        target != destination_resolved
                        and destination_resolved not in target.parents
                    ):
                        raise SimulationPackageStagingError(
                            "UNSAFE_ARCHIVE_PATH",
                            "Archive contains an unsafe extraction target",
                            422,
                        )
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as member_source, target.open("wb") as output:
                        shutil.copyfileobj(member_source, output, self._CHUNK_SIZE)
        except BadZipFile as exc:
            raise SimulationPackageStagingError(
                "INVALID_ARCHIVE", "Uploaded simulation package is not a valid ZIP archive", 422
            ) from exc
