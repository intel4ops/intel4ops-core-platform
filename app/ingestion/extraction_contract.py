from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

# ---------------------------------------------------------------------------
# The one generic contract every ArtifactParser returns. Analysis Case
# orchestration consumes only this contract -- it never contains file-
# format-specific parsing logic of its own (P3.xxC.1 final refinement #2).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExtractedDataset:
    """One logical, tabular extraction (e.g. one sheet of a workbook, one
    reliably-extracted table from a PDF page)."""

    label: str
    dataframe: pd.DataFrame
    lineage: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ExtractedEvidence:
    """Non-tabular extracted content (narrative text, email body, slide
    notes, document metadata) that Intelligence can cite without forcing it
    into a dataframe."""

    evidence_type: Literal["text_block", "key_value", "metadata"]
    content: str
    lineage: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ChildArtifact:
    """A compound artifact's nested file (an email attachment) -- re-enters
    the same parser-selection pipeline as a first-class SourceArtifact,
    linked back to its parent."""

    filename: str
    mime_type: str
    content: bytes


@dataclass(frozen=True)
class ArtifactExtractionResult:
    parser_code: str
    parser_version: str
    status: Literal["extracted", "partial", "failed", "unavailable"]
    warnings: list[str] = field(default_factory=list)
    datasets: list[ExtractedDataset] = field(default_factory=list)
    evidence_objects: list[ExtractedEvidence] = field(default_factory=list)
    child_artifacts: list[ChildArtifact] = field(default_factory=list)
    extraction_metadata: dict[str, object] = field(default_factory=dict)
