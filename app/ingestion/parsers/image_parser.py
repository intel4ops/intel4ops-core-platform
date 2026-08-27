from __future__ import annotations

from io import BytesIO

from PIL import Image

from app.ingestion.extraction_contract import ArtifactExtractionResult, ExtractedEvidence
from app.ingestion.ocr_adapter import OcrAdapter, UnavailableOcrAdapter


class ImageParser:
    """PNG/JPEG always register as visual evidence with real metadata
    (dimensions, format). Text extraction goes through the modular
    OcrAdapter -- with UnavailableOcrAdapter as the default, images get
    extraction_status=unavailable, never a fabricated OCR result."""

    code = "image"
    version = "1.0"

    def __init__(self, ocr_adapter: OcrAdapter | None = None) -> None:
        self._ocr = ocr_adapter or UnavailableOcrAdapter()

    def supports(self, mime_type: str, extension: str) -> bool:
        return extension.lower() in (".png", ".jpg", ".jpeg") or mime_type in (
            "image/png",
            "image/jpeg",
        )

    def extract(self, raw_bytes: bytes, filename: str) -> ArtifactExtractionResult:
        try:
            with Image.open(BytesIO(raw_bytes)) as image:
                metadata: dict[str, object] = {
                    "width": image.width,
                    "height": image.height,
                    "format": image.format,
                }
        except Exception as exc:  # noqa: BLE001
            return ArtifactExtractionResult(
                parser_code=self.code,
                parser_version=self.version,
                status="failed",
                warnings=[f"Image decode failed: {exc}"],
            )
        if not self._ocr.is_available():
            return ArtifactExtractionResult(
                parser_code=self.code,
                parser_version=self.version,
                status="unavailable",
                warnings=[
                    "No OCR backend provisioned -- image preserved as evidence, no text extracted"
                ],
                evidence_objects=[
                    ExtractedEvidence(
                        evidence_type="metadata", content=str(metadata), lineage=metadata
                    )
                ],
                extraction_metadata=metadata,
            )
        result = self._ocr.extract_text(raw_bytes)
        return ArtifactExtractionResult(
            parser_code=self.code,
            parser_version=self.version,
            status="extracted",
            evidence_objects=[
                ExtractedEvidence(
                    evidence_type="text_block",
                    content=result.text,
                    lineage={**metadata, "ocr_confidence": result.confidence},
                )
            ],
            extraction_metadata=metadata,
        )
