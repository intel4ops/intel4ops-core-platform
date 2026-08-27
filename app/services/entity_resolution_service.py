from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import pandas as pd

from app.models.analysis_case import AnalysisCaseEntityLink, EntityLinkStatus

# Canonical id field -> (entity_type, entity_subtype). Runs AFTER the
# mapping bridge (plan Section 7 correction) -- operates purely on the
# now-uniform canonical field names, with no separate alias table of its
# own, avoiding a second alias system inside entity resolution.
ENTITY_ID_FIELDS: dict[str, tuple[str, str | None]] = {
    "asset_id": ("asset", None),
    "operational_event_id": ("operational_event", None),
    "route_id": ("location", "route"),
    "depot_id": ("location", "depot"),
}


@dataclass(frozen=True)
class DatasetEntityInput:
    analysis_case_dataset_id: UUID
    dataset_id: UUID
    canonical_dataframe: pd.DataFrame


class EntityResolutionService:
    """Exact-match only -- no fuzzy matching where an exact business
    identifier exists (Section 6). Conflict detection is intentionally
    modest this pass: it flags an identifier reused across datasets with a
    differing descriptive value only where such a column is itself
    canonically mapped; without one present it degrades to matched/
    unresolved, which is the honest behavior given no name/label canonical
    field is defined yet."""

    def resolve(self, inputs: list[DatasetEntityInput]) -> list[AnalysisCaseEntityLink]:
        # (entity_type, subtype, canonical_key) -> set of dataset_ids
        occurrences: dict[tuple[str, str | None, str], set[str]] = {}
        for item in inputs:
            for field_name, (entity_type, subtype) in ENTITY_ID_FIELDS.items():
                if field_name not in item.canonical_dataframe.columns:
                    continue
                for raw_value in item.canonical_dataframe[field_name].dropna().unique():
                    key = (entity_type, subtype, str(raw_value))
                    occurrences.setdefault(key, set()).add(str(item.dataset_id))

        links: list[AnalysisCaseEntityLink] = []
        for (entity_type, subtype, canonical_key), dataset_ids in occurrences.items():
            status = (
                EntityLinkStatus.MATCHED if len(dataset_ids) >= 2 else EntityLinkStatus.UNRESOLVED
            )
            links.append(
                AnalysisCaseEntityLink(
                    entity_type=entity_type,
                    entity_subtype=subtype,
                    canonical_key=canonical_key,
                    status=status,
                    source_dataset_ids=sorted(dataset_ids),
                    detail={},
                )
            )
        return links


entity_resolution_service = EntityResolutionService()
