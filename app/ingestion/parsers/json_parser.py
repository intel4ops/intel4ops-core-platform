from __future__ import annotations

import json

import pandas as pd

from app.ingestion.extraction_contract import (
    ArtifactExtractionResult,
    ExtractedDataset,
    ExtractedEvidence,
)


class JsonParser:
    """A JSON array of flat objects becomes a tabular ExtractedDataset;
    anything else (a single object, nested structures) is preserved as
    key_value evidence rather than forced into a dataframe."""

    code = "json"
    version = "1.0"

    def supports(self, mime_type: str, extension: str) -> bool:
        return extension.lower() == ".json" or mime_type == "application/json"

    def extract(self, raw_bytes: bytes, filename: str) -> ArtifactExtractionResult:
        try:
            payload = json.loads(raw_bytes.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            return ArtifactExtractionResult(
                parser_code=self.code,
                parser_version=self.version,
                status="failed",
                warnings=[f"JSON parse failed: {exc}"],
            )
        if (
            isinstance(payload, list)
            and payload
            and all(isinstance(item, dict) for item in payload)
        ):
            dataframe = pd.DataFrame(payload)
            return ArtifactExtractionResult(
                parser_code=self.code,
                parser_version=self.version,
                status="extracted",
                datasets=[ExtractedDataset(label=filename, dataframe=dataframe)],
            )
        return ArtifactExtractionResult(
            parser_code=self.code,
            parser_version=self.version,
            status="extracted",
            evidence_objects=[
                ExtractedEvidence(evidence_type="key_value", content=json.dumps(payload, indent=2))
            ],
        )
