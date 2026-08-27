from __future__ import annotations

from io import BytesIO

import pandas as pd

from app.ingestion.extraction_contract import ArtifactExtractionResult, ExtractedDataset


class ExcelParser:
    """One ExtractedDataset per sheet -- the compound-artifact case
    explicitly in scope this pass (one SourceArtifact -> N logical
    datasets)."""

    code = "excel"
    version = "1.0"

    def supports(self, mime_type: str, extension: str) -> bool:
        return extension.lower() in (".xlsx", ".xls") or mime_type in (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel",
        )

    def extract(self, raw_bytes: bytes, filename: str) -> ArtifactExtractionResult:
        try:
            sheets = pd.read_excel(BytesIO(raw_bytes), sheet_name=None)
        except Exception as exc:  # noqa: BLE001
            return ArtifactExtractionResult(
                parser_code=self.code,
                parser_version=self.version,
                status="failed",
                warnings=[f"Excel parse failed: {exc}"],
            )
        datasets = [
            ExtractedDataset(
                label=f"{filename}:{sheet_name}",
                dataframe=dataframe,
                lineage={"sheet_name": sheet_name},
            )
            for sheet_name, dataframe in sheets.items()
        ]
        return ArtifactExtractionResult(
            parser_code=self.code,
            parser_version=self.version,
            status="extracted" if datasets else "partial",
            warnings=[] if datasets else ["Workbook contained no sheets"],
            datasets=datasets,
        )
