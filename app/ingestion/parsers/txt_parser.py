from __future__ import annotations

from app.ingestion.extraction_contract import ArtifactExtractionResult, ExtractedEvidence


class TxtParser:
    code = "txt"
    version = "1.0"

    def supports(self, mime_type: str, extension: str) -> bool:
        return extension.lower() == ".txt" or mime_type == "text/plain"

    def extract(self, raw_bytes: bytes, filename: str) -> ArtifactExtractionResult:
        try:
            text = raw_bytes.decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            return ArtifactExtractionResult(
                parser_code=self.code,
                parser_version=self.version,
                status="failed",
                warnings=[f"Text decode failed: {exc}"],
            )
        return ArtifactExtractionResult(
            parser_code=self.code,
            parser_version=self.version,
            status="extracted",
            evidence_objects=[ExtractedEvidence(evidence_type="text_block", content=text)],
        )
