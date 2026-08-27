from __future__ import annotations

from io import BytesIO

import pandas as pd

from app.ingestion.extraction_contract import ArtifactExtractionResult, ExtractedDataset


class CsvParser:
    code = "csv"
    version = "1.0"

    def supports(self, mime_type: str, extension: str) -> bool:
        return extension.lower() == ".csv" or mime_type in ("text/csv", "application/csv")

    def extract(self, raw_bytes: bytes, filename: str) -> ArtifactExtractionResult:
        try:
            dataframe = pd.read_csv(BytesIO(raw_bytes))
        except Exception as exc:  # noqa: BLE001 -- malformed file must not crash the case
            return ArtifactExtractionResult(
                parser_code=self.code,
                parser_version=self.version,
                status="failed",
                warnings=[f"CSV parse failed: {exc}"],
            )
        return ArtifactExtractionResult(
            parser_code=self.code,
            parser_version=self.version,
            status="extracted",
            datasets=[ExtractedDataset(label=filename, dataframe=dataframe)],
        )
