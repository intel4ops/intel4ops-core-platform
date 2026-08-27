from __future__ import annotations

from io import BytesIO
from typing import Literal

from pypdf import PdfReader

from app.ingestion.extraction_contract import ArtifactExtractionResult, ExtractedEvidence


class PdfParser:
    """Basic extraction only: embedded text per page, with page-number
    lineage. Reliable table extraction is not attempted this pass -- pypdf
    has no robust table extractor, and a heuristic one would risk silently
    wrong data, which is worse than not claiming the capability. A future
    pass can add a table-aware library without changing this contract."""

    code = "pdf"
    version = "1.0"

    def supports(self, mime_type: str, extension: str) -> bool:
        return extension.lower() == ".pdf" or mime_type == "application/pdf"

    def extract(self, raw_bytes: bytes, filename: str) -> ArtifactExtractionResult:
        try:
            reader = PdfReader(BytesIO(raw_bytes))
        except Exception as exc:  # noqa: BLE001
            return ArtifactExtractionResult(
                parser_code=self.code,
                parser_version=self.version,
                status="failed",
                warnings=[f"PDF parse failed: {exc}"],
            )
        evidence = []
        warnings = []
        for index, page in enumerate(reader.pages):
            try:
                text = page.extract_text() or ""
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"Page {index + 1} text extraction failed: {exc}")
                continue
            if text.strip():
                evidence.append(
                    ExtractedEvidence(
                        evidence_type="text_block",
                        content=text,
                        lineage={"page_number": index + 1},
                    )
                )
        status: Literal["extracted", "partial"] = "extracted" if evidence else "partial"
        if not evidence and not warnings:
            warnings.append("No extractable text found (may be a scanned/image-only PDF)")
        return ArtifactExtractionResult(
            parser_code=self.code,
            parser_version=self.version,
            status=status,
            warnings=warnings,
            evidence_objects=evidence,
            extraction_metadata={"page_count": len(reader.pages)},
        )
