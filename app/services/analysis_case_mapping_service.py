from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import pandas as pd
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.domain_registry import DOMAIN_SIGNATURES, canonicalize_field
from app.models.analysis_case import AnalysisCaseFieldMapping, DetectionStatus, MappingStatus
from app.semantic.candidate import InterpretationDecisionStatus
from app.semantic.interpreter import interpret_dataset
from app.semantic.provider import NullSemanticReasoningProvider


@dataclass(frozen=True)
class MappingBridgeResult:
    canonical_dataframe: pd.DataFrame
    field_mappings: list[AnalysisCaseFieldMapping]
    overall_status: str


class AnalysisCaseMappingService:
    """Customer-native mapping bridge into the existing canonical path.

    Exact governed aliases remain authoritative. For fields that do not
    resolve through the legacy alias registry, the existing semantic
    interpreter may promote a meaning only when its deterministic evidence
    reaches AUTO_ACCEPTED authority. Review-required/flagged decisions are
    persisted as mapping uncertainty and never routed as canonical data.

    The semantic pass deliberately uses the null provider here: mapping
    authority must be reproducible from customer data and governed registry
    evidence alone. The normal case-level semantic stage still runs later
    with its full cross-dataset context and configured provider policy.
    """

    def apply(
        self,
        organization_id: object,
        analysis_case_dataset_id: object,
        dataframe: pd.DataFrame,
        domain: str | None,
        detection_status: str | None = None,
    ) -> MappingBridgeResult:
        required_fields: frozenset[str] = frozenset()
        if detection_status == DetectionStatus.CONFIRMED.value:
            for signature in DOMAIN_SIGNATURES:
                if signature.domain == domain:
                    required_fields = signature.required_canonical_fields
                    break

        # Run the platform's existing semantic interpretation only as a
        # fallback for fields the governed exact/token alias bridge cannot
        # already resolve. No filename or simulation context is supplied.
        semantic_result = interpret_dataset(
            str(analysis_case_dataset_id),
            "customer_dataset",
            dataframe,
            provider=NullSemanticReasoningProvider(),
        )
        semantic_by_field = {decision.source_field: decision for decision in semantic_result.field_decisions}

        rename_map: dict[str, str] = {}
        promoted_columns: dict[str, str] = {}
        mappings: list[AnalysisCaseFieldMapping] = []
        mapped_canonical_fields: set[str] = set()
        has_mapping_uncertainty = False

        for column in dataframe.columns:
            source_field = str(column)
            canonical = canonicalize_field(source_field)
            status = MappingStatus.IGNORED

            if canonical is not None:
                rename_map[source_field] = canonical
                mapped_canonical_fields.add(canonical)
                status = MappingStatus.AUTO_MAPPED
            else:
                decision = semantic_by_field.get(source_field)
                if decision is not None and decision.selected_concept is not None:
                    if decision.status in {
                        InterpretationDecisionStatus.AUTO_ACCEPTED.value,
                        InterpretationDecisionStatus.HUMAN_CONFIRMED.value,
                    }:
                        # A second raw field claiming the same canonical
                        # concept is ambiguous. Preserve both raw fields and
                        # request review rather than silently choosing one.
                        if decision.selected_concept in mapped_canonical_fields:
                            canonical = decision.selected_concept
                            status = MappingStatus.NEEDS_REVIEW
                            has_mapping_uncertainty = True
                        else:
                            canonical = decision.selected_concept
                            promoted_columns[source_field] = canonical
                            mapped_canonical_fields.add(canonical)
                            status = MappingStatus.AUTO_MAPPED
                    elif decision.status in {
                        InterpretationDecisionStatus.ACCEPTED_WITH_FLAG.value,
                        InterpretationDecisionStatus.REVIEW_REQUIRED.value,
                    }:
                        canonical = decision.selected_concept
                        status = MappingStatus.NEEDS_REVIEW
                        has_mapping_uncertainty = True

            mappings.append(
                AnalysisCaseFieldMapping(
                    organization_id=organization_id,
                    analysis_case_dataset_id=analysis_case_dataset_id,
                    source_field=source_field,
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
            MappingStatus.NEEDS_REVIEW
            if missing_required or has_mapping_uncertainty
            else MappingStatus.AUTO_MAPPED
        )

        # Preserve source columns for semantic/entity lineage. Legacy alias
        # mappings retain their established rename behavior; semantic-only
        # promotions are additive canonical views over the same source data.
        canonical_dataframe = dataframe.rename(columns=rename_map).copy()
        for source_field, canonical in promoted_columns.items():
            if canonical not in canonical_dataframe.columns:
                canonical_dataframe[canonical] = dataframe[source_field]

        return MappingBridgeResult(
            canonical_dataframe=canonical_dataframe,
            field_mappings=mappings,
            overall_status=overall_status,
        )

    def persist(
        self, db: Session, analysis_case_dataset_id: UUID, result: MappingBridgeResult
    ) -> None:
        """Replace the current per-dataset mapping state without losing
        source-field -> canonical-field lineage."""
        db.execute(
            delete(AnalysisCaseFieldMapping).where(
                AnalysisCaseFieldMapping.analysis_case_dataset_id == analysis_case_dataset_id
            )
        )
        db.add_all(result.field_mappings)


analysis_case_mapping_service = AnalysisCaseMappingService()
