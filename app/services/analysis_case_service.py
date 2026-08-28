from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.analysis_case import (
    AnalysisCase,
    AnalysisCaseDataset,
    AnalysisCaseEvidenceObject,
    AnalysisCaseStatus,
    ArtifactExtractionStatus,
    ArtifactParserStatus,
    SourceArtifact,
)
from app.models.entities import Organization, utc_now
from app.models.ingestion import (
    Dataset,
    DatasetStatus,
    DatasetType,
    DatasetVersion,
    IngestionBatch,
    IngestionBatchStatus,
    IngestionMethod,
    TriggerType,
)
from app.models.source_system import SourceSystem
from app.services.domain_detection_service import detect_domain
from app.storage.base import StorageBackend
from app.storage.local_storage import LocalFileStorage


class AnalysisCaseServiceError(ValueError):
    def __init__(self, message: str, *, code: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def _default_storage() -> StorageBackend:
    return LocalFileStorage(get_settings().storage_root)


@dataclass(frozen=True)
class UploadedFile:
    filename: str
    content: bytes


class AnalysisCaseService:
    def __init__(self, storage: StorageBackend | None = None) -> None:
        self._storage = storage or _default_storage()

    def _organization(self, db: Session, organization_id: UUID) -> Organization:
        org = db.get(Organization, organization_id)
        if org is None:
            raise AnalysisCaseServiceError(
                "Organization not found", code="organization_not_found", status=404
            )
        return org

    def create(
        self,
        db: Session,
        organization_id: UUID,
        name: str,
        mode: str,
        actor_user_id: UUID,
        industry_code: str | None = None,
        business_model: str | None = None,
        operating_context: str | None = None,
        case_currency_hint: str | None = None,
        idempotency_key: str | None = None,
    ) -> AnalysisCase:
        self._organization(db, organization_id)
        if idempotency_key is not None:
            existing = db.scalar(
                select(AnalysisCase).where(
                    AnalysisCase.organization_id == organization_id,
                    AnalysisCase.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                return existing
        case = AnalysisCase(
            organization_id=organization_id,
            case_code=f"CASE-{uuid4().hex[:12].upper()}",
            idempotency_key=idempotency_key,
            name=name,
            mode=mode,
            status=AnalysisCaseStatus.CREATED.value,
            industry_code=industry_code,
            business_model=business_model,
            operating_context=operating_context,
            case_currency_hint=case_currency_hint,
            created_by_user_id=actor_user_id,
        )
        db.add(case)
        db.commit()
        db.refresh(case)
        return case

    def get(self, db: Session, organization_id: UUID, analysis_case_id: UUID) -> AnalysisCase:
        case = db.scalar(
            select(AnalysisCase).where(
                AnalysisCase.id == analysis_case_id, AnalysisCase.organization_id == organization_id
            )
        )
        if case is None:
            raise AnalysisCaseServiceError("Case not found", code="case_not_found", status=404)
        return case

    def list_cases(
        self, db: Session, organization_id: UUID, include_archived: bool = False
    ) -> list[AnalysisCase]:
        stmt = select(AnalysisCase).where(AnalysisCase.organization_id == organization_id)
        if not include_archived:
            stmt = stmt.where(AnalysisCase.archived_at.is_(None))
        return list(db.scalars(stmt.order_by(AnalysisCase.created_at.desc())).all())

    def archive(
        self, db: Session, organization_id: UUID, analysis_case_id: UUID, actor_user_id: UUID
    ) -> AnalysisCase:
        """Soft-archive only -- never deletes the case or any artifact,
        dataset, run, finding, action, or recovery record it produced.
        Idempotent: archiving an already-archived case is a no-op that
        returns its existing archived_at/archived_by_user_id unchanged."""
        case = self.get(db, organization_id, analysis_case_id)
        if case.archived_at is None:
            case.archived_at = utc_now()
            case.archived_by_user_id = actor_user_id
            db.add(case)
            db.commit()
            db.refresh(case)
        return case

    def _ensure_source_system(
        self, db: Session, organization_id: UUID, actor_user_id: UUID
    ) -> SourceSystem:
        from app.models.source_system import IntegrationMethod, SourceEnvironment, SourceSystemType

        existing = db.scalar(
            select(SourceSystem).where(
                SourceSystem.organization_id == organization_id,
                SourceSystem.code == "analysis-case-uploads",
            )
        )
        if existing is not None:
            return existing
        source_system = SourceSystem(
            organization_id=organization_id,
            name="Analysis Case Uploads",
            code="analysis-case-uploads",
            system_type=SourceSystemType.FLAT_FILE.value,
            integration_method=IntegrationMethod.FILE_UPLOAD.value,
            environment=SourceEnvironment.PRODUCTION.value,
            created_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
        )
        db.add(source_system)
        db.flush()
        return source_system

    def register_artifacts(
        self,
        db: Session,
        organization_id: UUID,
        analysis_case_id: UUID,
        files: list[UploadedFile],
        actor_user_id: UUID,
        parent_artifact_id: UUID | None = None,
    ) -> list[SourceArtifact]:
        """CONNECT stage: every file becomes a SourceArtifact with bytes
        persisted regardless of whether a parser exists for it. Tabular
        extractions become logical Dataset/DatasetVersion rows with
        immediate domain detection; non-tabular extractions become
        AnalysisCaseEvidenceObject rows; child artifacts (email
        attachments) recurse through this same method."""
        from app.ingestion.parsers import default_parser_registry

        self.get(db, organization_id, analysis_case_id)  # validates existence/tenancy
        settings = get_settings()
        registry = default_parser_registry()
        source_system = self._ensure_source_system(db, organization_id, actor_user_id)
        ingestion_batch = IngestionBatch(
            organization_id=organization_id,
            source_system_id=source_system.id,
            batch_number=f"AC-{uuid4().hex[:16].upper()}",
            ingestion_method=IngestionMethod.FILE_UPLOAD.value,
            status=IngestionBatchStatus.COMPLETED.value,
            trigger_type=TriggerType.MANUAL.value,
            submitted_by_user_id=actor_user_id,
        )
        db.add(ingestion_batch)
        db.flush()
        created: list[SourceArtifact] = []

        for uploaded in files:
            if len(uploaded.content) > settings.max_artifact_size_bytes:
                raise AnalysisCaseServiceError(
                    f"Artifact {uploaded.filename!r} exceeds the maximum allowed size",
                    code="artifact_too_large",
                    status=413,
                )
            extension = Path(uploaded.filename).suffix.lower()
            guessed_mime, _ = mimetypes.guess_type(uploaded.filename)
            mime_type = guessed_mime or "application/octet-stream"

            artifact_id = uuid4()
            storage_key = f"{organization_id}/{artifact_id}/source"
            write_result = self._storage.write_stream(storage_key, [uploaded.content])

            artifact = SourceArtifact(
                id=artifact_id,
                organization_id=organization_id,
                analysis_case_id=analysis_case_id,
                parent_artifact_id=parent_artifact_id,
                original_filename=uploaded.filename,
                mime_type=mime_type,
                extension=extension,
                size_bytes=write_result.size_bytes,
                checksum=write_result.checksum,
                storage_reference=write_result.reference,
                parser_status=ArtifactParserStatus.PENDING.value,
                extraction_status=ArtifactExtractionStatus.PENDING.value,
            )
            db.add(artifact)
            db.flush()

            parser = registry.select(mime_type, extension)
            if parser is None:
                artifact.parser_status = ArtifactParserStatus.UNSUPPORTED.value
                artifact.extraction_status = ArtifactExtractionStatus.UNAVAILABLE.value
                db.add(artifact)
                db.commit()
                created.append(artifact)
                continue

            try:
                result = parser.extract(uploaded.content, uploaded.filename)
            except Exception as exc:  # noqa: BLE001 -- one bad artifact must not fail the case
                artifact.parser_status = ArtifactParserStatus.FAILED.value
                artifact.extraction_status = ArtifactExtractionStatus.FAILED.value
                artifact.extraction_warnings = [str(exc)]
                db.add(artifact)
                db.commit()
                created.append(artifact)
                continue

            # "unavailable" covers two structurally different situations:
            # a sub-feature is unavailable but the artifact was still
            # genuinely processed (e.g. an image decodes fine and is
            # preserved as evidence, only OCR text extraction is
            # unavailable -- real content exists, parser_status stays
            # PARSED), versus a parser whose runtime dependency itself
            # could not load, so nothing was or could be attempted at all
            # (e.g. PPTX/DOCX when lxml is blocked -- no content exists,
            # so this is the same honest signal as no parser being
            # registered for the format at all: UNSUPPORTED).
            produced_content = bool(
                result.datasets or result.evidence_objects or result.child_artifacts
            )
            if result.status == "failed":
                artifact.parser_status = ArtifactParserStatus.FAILED.value
            elif result.status == "unavailable" and not produced_content:
                artifact.parser_status = ArtifactParserStatus.UNSUPPORTED.value
            else:
                artifact.parser_status = ArtifactParserStatus.PARSED.value
            artifact.parser_code = result.parser_code
            artifact.parser_version = result.parser_version
            artifact.extraction_status = result.status
            artifact.extraction_warnings = result.warnings
            artifact.extraction_metadata = result.extraction_metadata
            db.add(artifact)

            for extracted_dataset in result.datasets:
                detection = detect_domain([str(c) for c in extracted_dataset.dataframe.columns])
                dataset = Dataset(
                    organization_id=organization_id,
                    source_system_id=source_system.id,
                    name=extracted_dataset.label,
                    code=f"ac-{uuid4().hex[:12]}",
                    domain=detection.domain or "unknown",
                    dataset_type=DatasetType.TRANSACTIONAL.value,
                    status=DatasetStatus.ACTIVE.value,
                    created_by_user_id=actor_user_id,
                    updated_by_user_id=actor_user_id,
                )
                db.add(dataset)
                db.flush()
                dataset_version = DatasetVersion(
                    organization_id=organization_id,
                    dataset_id=dataset.id,
                    ingestion_batch_id=ingestion_batch.id,
                    version_number=1,
                    source_file_name=uploaded.filename,
                    record_count=len(extracted_dataset.dataframe),
                    storage_reference=write_result.reference,
                )
                db.add(dataset_version)
                db.flush()
                case_dataset = AnalysisCaseDataset(
                    organization_id=organization_id,
                    analysis_case_id=analysis_case_id,
                    source_artifact_id=artifact.id,
                    dataset_id=dataset.id,
                    dataset_version_id=dataset_version.id,
                    source_label=extracted_dataset.label,
                    detected_domain=detection.domain,
                    detection_basis=detection.basis,
                    detection_status=detection.status,
                    row_count=len(extracted_dataset.dataframe),
                )
                db.add(case_dataset)

            for evidence in result.evidence_objects:
                db.add(
                    AnalysisCaseEvidenceObject(
                        organization_id=organization_id,
                        analysis_case_id=analysis_case_id,
                        source_artifact_id=artifact.id,
                        evidence_type=evidence.evidence_type,
                        content=evidence.content,
                        lineage_ref=evidence.lineage,
                    )
                )

            db.commit()
            db.refresh(artifact)
            created.append(artifact)

            if result.child_artifacts:
                child_uploads = [
                    UploadedFile(filename=child.filename, content=child.content)
                    for child in result.child_artifacts
                ]
                created.extend(
                    self.register_artifacts(
                        db,
                        organization_id,
                        analysis_case_id,
                        child_uploads,
                        actor_user_id,
                        parent_artifact_id=artifact.id,
                    )
                )

        return created

    def list_datasets(
        self, db: Session, organization_id: UUID, analysis_case_id: UUID
    ) -> list[AnalysisCaseDataset]:
        return list(
            db.scalars(
                select(AnalysisCaseDataset).where(
                    AnalysisCaseDataset.organization_id == organization_id,
                    AnalysisCaseDataset.analysis_case_id == analysis_case_id,
                )
            ).all()
        )

    @property
    def storage(self) -> StorageBackend:
        return self._storage


analysis_case_service = AnalysisCaseService()
