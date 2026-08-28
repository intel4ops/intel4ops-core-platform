from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.ingestion.parsers import PowerPointParser, WordParser, default_parser_registry
from app.models.analysis_case import ArtifactExtractionStatus, ArtifactParserStatus
from app.models.entities import Organization
from app.schemas.contracts import OrganizationCreate
from app.services.analysis_case_service import AnalysisCaseService, UploadedFile
from app.services.organization_service import OrganizationService
from app.storage.local_storage import LocalFileStorage


def test_csv_xlsx_json_txt_are_registered_and_extract() -> None:
    registry = default_parser_registry()
    assert registry.select("text/csv", ".csv") is not None
    result = registry.select("text/csv", ".csv").extract(b"a,b\n1,2\n", "x.csv")  # type: ignore[union-attr]
    assert result.status == "extracted"
    assert len(result.datasets) == 1


def test_pdf_docx_pptx_eml_png_are_registered() -> None:
    registry = default_parser_registry()
    assert registry.select("application/pdf", ".pdf") is not None
    assert (
        registry.select(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"
        )
        is not None
    )
    assert (
        registry.select(
            "application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx"
        )
        is not None
    )
    assert registry.select("message/rfc822", ".eml") is not None
    assert registry.select("image/png", ".png") is not None


def test_unregistered_formats_return_none_not_a_fake_result() -> None:
    """XML/MSG/TIFF/Parquet have no real parser this pass -- registry.select
    returning None IS the honest 'not yet built' signal; the caller (not
    this registry) is responsible for setting parser_status=unsupported."""
    registry = default_parser_registry()
    assert registry.select("application/xml", ".xml") is None
    assert registry.select("application/vnd.ms-outlook", ".msg") is None
    assert registry.select("image/tiff", ".tiff") is None
    assert registry.select("application/x-parquet", ".parquet") is None


def test_malformed_csv_fails_cleanly_without_raising() -> None:
    registry = default_parser_registry()
    parser = registry.select("text/csv", ".csv")
    assert parser is not None
    # An empty file is a degenerate but not truly malformed case for pandas;
    # assert the parser never raises regardless of status outcome.
    result = parser.extract(b"", "empty.csv")
    assert result.status in ("failed", "extracted", "partial")


def test_image_without_ocr_backend_is_unavailable_not_fabricated() -> None:
    import io

    from PIL import Image

    registry = default_parser_registry()
    parser = registry.select("image/png", ".png")
    assert parser is not None
    buf = io.BytesIO()
    Image.new("RGB", (4, 4)).save(buf, format="PNG")
    result = parser.extract(buf.getvalue(), "x.png")
    assert result.status == "unavailable"
    assert not any(e.evidence_type == "text_block" for e in result.evidence_objects)


# ---------------------------------------------------------------------------
# Resiliency hardening: an optional format parser's runtime dependency
# (python-pptx/python-docx, both pulling in lxml) can be unavailable in a
# given deployment environment -- e.g. blocked outright by an Application
# Control / EDR policy. That must never prevent the app from starting, the
# parser registry from building, or unrelated CSV/JSON/XLSX artifacts from
# being processed. These tests force the unavailable state deterministically
# via monkeypatch so they pass identically whether or not the *current* test
# machine actually has a working lxml -- they prove the resiliency
# mechanism itself, not today's ambient environment.
# ---------------------------------------------------------------------------


def _organization(db: Session, slug: str) -> Organization:
    return OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug.title(), slug=slug, country_code="US", default_currency="USD", timezone="UTC"
        ),
    )


def test_registry_builds_when_pptx_and_docx_dependencies_are_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Application/registry startup must not depend on every optional
    parser's dependency being loadable."""
    import app.ingestion.parsers.powerpoint_parser as pptx_module
    import app.ingestion.parsers.word_parser as docx_module

    monkeypatch.setattr(pptx_module, "_IMPORT_ERROR", "simulated: DLL blocked")
    monkeypatch.setattr(docx_module, "_IMPORT_ERROR", "simulated: DLL blocked")

    registry = default_parser_registry()
    assert len(registry._parsers) == 9

    pptx_parser = registry.select(
        "application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx"
    )
    docx_parser = registry.select(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"
    )
    assert isinstance(pptx_parser, PowerPointParser)
    assert isinstance(docx_parser, WordParser)
    assert pptx_parser.is_available() is False
    assert docx_parser.is_available() is False


def test_pptx_extract_reports_unavailable_with_explicit_reason_when_dependency_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.ingestion.parsers.powerpoint_parser as pptx_module

    monkeypatch.setattr(pptx_module, "_IMPORT_ERROR", "simulated: DLL blocked")
    parser = pptx_module.PowerPointParser()
    result = parser.extract(b"not a real pptx", "deck.pptx")
    assert result.status == "unavailable"
    assert result.datasets == []
    assert result.evidence_objects == []
    assert result.extraction_metadata.get("reason") == "dependency_unavailable"
    assert any("dependency" in w.lower() for w in result.warnings)


def test_unrelated_parsers_remain_usable_when_pptx_docx_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B/D. CSV/JSON/XLSX (and any other non-Office parser) must keep
    working normally regardless of PPTX/DOCX's dependency state."""
    import app.ingestion.parsers.powerpoint_parser as pptx_module
    import app.ingestion.parsers.word_parser as docx_module

    monkeypatch.setattr(pptx_module, "_IMPORT_ERROR", "simulated: DLL blocked")
    monkeypatch.setattr(docx_module, "_IMPORT_ERROR", "simulated: DLL blocked")

    registry = default_parser_registry()
    csv_parser = registry.select("text/csv", ".csv")
    assert csv_parser is not None
    result = csv_parser.extract(b"a,b\n1,2\n", "x.csv")
    assert result.status == "extracted"
    assert len(result.datasets) == 1

    json_parser = registry.select("application/json", ".json")
    assert json_parser is not None
    json_result = json_parser.extract(b'[{"a": 1}]', "x.json")
    assert json_result.status == "extracted"


def test_pptx_upload_preserved_and_marked_unavailable_when_dependency_down(
    monkeypatch: pytest.MonkeyPatch, db: Session, tmp_path: Path
) -> None:
    """C. A PPTX upload must never crash the case or silently vanish: the
    SourceArtifact is preserved with an explicit dependency_unavailable
    signal, distinct from "no parser was ever built for this format"."""
    import app.ingestion.parsers.powerpoint_parser as pptx_module

    monkeypatch.setattr(pptx_module, "_IMPORT_ERROR", "simulated: DLL blocked")

    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    org = _organization(db, "resiliency-pptx-unavailable")
    actor = uuid4()
    case = service.create(db, org.id, "Resiliency Case", "orchestrated", actor)

    artifacts = service.register_artifacts(
        db,
        org.id,
        case.id,
        [
            UploadedFile("deck.pptx", b"not a real pptx but bytes exist"),
            UploadedFile(
                "maintenance_events.csv", b"asset_id,failure_code,downtime_hours\nV1,brake,4\n"
            ),
        ],
        actor,
    )
    by_name = {a.original_filename: a for a in artifacts}

    pptx_artifact = by_name["deck.pptx"]
    assert pptx_artifact.parser_status == ArtifactParserStatus.UNSUPPORTED.value
    assert pptx_artifact.extraction_status == ArtifactExtractionStatus.UNAVAILABLE.value
    assert pptx_artifact.extraction_warnings
    assert any("dependency" in w.lower() for w in pptx_artifact.extraction_warnings)

    # A. the unrelated CSV artifact is completely unaffected -- both the
    # artifact row and its downstream dataset are created normally.
    csv_artifact = by_name["maintenance_events.csv"]
    assert csv_artifact.parser_status == ArtifactParserStatus.PARSED.value
    datasets = service.list_datasets(db, org.id, case.id)
    assert len(datasets) == 1
    assert datasets[0].source_label == "maintenance_events.csv"


def test_csv_orchestration_completes_when_pptx_dependency_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, db: Session, tmp_path: Path
) -> None:
    """A. A full run (register -> execute) completes normally on the CSV
    data in a mixed-format case even while PPTX's dependency is down."""
    import app.ingestion.parsers.powerpoint_parser as pptx_module
    from app.models.analysis_case import AnalysisCaseRunStatus
    from app.services.analysis_case_orchestration_service import (
        analysis_case_orchestration_service,
    )

    monkeypatch.setattr(pptx_module, "_IMPORT_ERROR", "simulated: DLL blocked")

    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    org = _organization(db, "resiliency-csv-orchestration")
    actor = uuid4()
    case = service.create(db, org.id, "Resiliency Orchestration Case", "orchestrated", actor)
    maint_csv = (
        b"asset_id,failure_code,downtime_hours,repair_cost,event_date\n"
        b"V1,brake,4,10000,2026-08-01T08:00:00\n"
        b"V1,brake,5,11000,2026-08-05T08:00:00\n"
        b"V1,brake,6,12000,2026-08-10T08:00:00\n"
    )
    service.register_artifacts(
        db,
        org.id,
        case.id,
        [
            UploadedFile("deck.pptx", b"not a real pptx"),
            UploadedFile("maintenance_events.csv", maint_csv),
        ],
        actor,
    )

    run = analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org.id, case.id, run.id, actor)
    db.refresh(run)
    assert run.status == AnalysisCaseRunStatus.COMPLETED.value
