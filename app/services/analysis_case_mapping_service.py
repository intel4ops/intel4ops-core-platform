from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import pandas as pd
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.domain_registry import DOMAIN_SIGNATURES, canonicalize_field
from app.models.analysis_case import AnalysisCaseFieldMapping, MappingStatus


@dataclass(frozen=True)
class MappingBridgeResult:
    canonical_dataframe: pd.DataFrame
    field_mappings: list[AnalysisCaseFieldMapping]
    overall_status: str


class AnalysisCaseMappingService:
    """MVP deterministic mapping bridge (Section 8/scope decision 5 of the
    plan): a known alias table, not the full governed Canonical Mapping
    template lifecycle. Structured so a validated mapping can be promoted
    into a real MappingTemplateVersion/FieldMapping later without losing
    which source column fed which canonical field."""

    def apply(
        self,
        organization_id: object,
        analysis_case_dataset_id: object,
        dataframe: pd.DataFrame,
        domain: str | None,
    ) -> MappingBridgeResult:
        required_fields: frozenset[str] = frozenset()
        for signature in DOMAIN_SIGNATURES:
            if signature.domain == domain:
                required_fields = signature.required_canonical_fields
                break

        rename_map: dict[str, str] = {}
        mappings: list[AnalysisCaseFieldMapping] = []
        mapped_canonical_fields: set[str] = set()
        for column in dataframe.columns:
            canonical = canonicalize_field(str(column))
            if canonical is not None:
                rename_map[str(column)] = canonical
                mapped_canonical_fields.add(canonical)
                status = MappingStatus.AUTO_MAPPED
            else:
                status = MappingStatus.IGNORED
            mappings.append(
                AnalysisCaseFieldMapping(
                    organization_id=organization_id,
                    analysis_case_dataset_id=analysis_case_dataset_id,
                    source_field=str(column),
                    canonical_field=canonical,
                    mapping_status=status,
                )
            )

        missing_required = required_fields - mapped_canonical_fields
        for missing_field in sorted(missing_required):
            mappings.append(
                AnalysisCaseFieldMapping(
                    organization_id=organization_id,
                    analysis_case_dataset_id=analysis_case_dataset_id,
                    source_field=f"<missing:{missing_field}>",
                    canonical_field=missing_field,
                    mapping_status=MappingStatus.MISSING_REQUIRED_FIELD,
                )
            )

        overall_status = (
            MappingStatus.NEEDS_REVIEW if missing_required else MappingStatus.AUTO_MAPPED
        )
        canonical_dataframe = dataframe.rename(columns=rename_map)
        return MappingBridgeResult(
            canonical_dataframe=canonical_dataframe,
            field_mappings=mappings,
            overall_status=overall_status,
        )

    def persist(
        self, db: Session, analysis_case_dataset_id: UUID, result: MappingBridgeResult
    ) -> None:
        """Mapping state reflects the current understanding of a dataset's
        schema, recomputed fresh on every run -- replace, never accumulate,
        so re-running the same case doesn't violate the per-dataset
        (source_field) uniqueness constraint."""
        db.execute(
            delete(AnalysisCaseFieldMapping).where(
                AnalysisCaseFieldMapping.analysis_case_dataset_id == analysis_case_dataset_id
            )
        )
        db.add_all(result.field_mappings)


analysis_case_mapping_service = AnalysisCaseMappingService()
