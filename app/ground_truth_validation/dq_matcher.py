from __future__ import annotations

from dataclasses import dataclass

from app.ground_truth_validation.family_registry import (
    ValidationFindingFamilyMappingRegistry,
    default_validation_finding_family_mapping_registry,
)
from app.models.ground_truth_validation import ValidationDataQualityTruth, ValidationDimensionStatus
from app.services.analysis_case_command_service import PrioritizedFinding

# Data-quality detection dimension (section 11D). Structurally identical
# shape to finding-detection -- a DQ defect is matched against a
# production Finding whose rule_id/domain resolves, through the SAME
# family registry, to a DQ-family entry. Nothing here is DQ-specific
# beyond that reuse: the moment a DQ-emitting Intelligence pack and a
# corresponding "DATA_QUALITY_*"-style family mapping exist, this starts
# scoring real TP/FP/FN without any matcher change. Today's default
# family registry (app/ground_truth_validation/family_registry.py)
# registers no data-quality family and no wired production rule emits a
# DQ-classified finding, so this honestly reports NOT_AVAILABLE.


def _dq_family_for(dq: ValidationDataQualityTruth) -> str | None:
    return dq.dq_family


@dataclass(frozen=True)
class DataQualityScoreSummary:
    status: str
    summary: str
    true_positive_count: int = 0
    false_positive_count: int = 0
    false_negative_count: int = 0
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None


def score_data_quality(
    dq_truth: list[ValidationDataQualityTruth],
    actual_findings: list[PrioritizedFinding],
    family_registry: ValidationFindingFamilyMappingRegistry | None = None,
) -> DataQualityScoreSummary:
    if not dq_truth:
        return DataQualityScoreSummary(
            status=ValidationDimensionStatus.NOT_AVAILABLE.value,
            summary="No data-quality truth was uploaded for this ground-truth version.",
        )

    family_registry = family_registry or default_validation_finding_family_mapping_registry
    resolvable = [dq for dq in dq_truth if family_registry.lookup(_dq_family_for(dq)) is not None]
    if not resolvable:
        return DataQualityScoreSummary(
            status=ValidationDimensionStatus.NOT_AVAILABLE.value,
            summary=(
                f"{len(dq_truth)} data-quality defect(s) were uploaded, but none declare a "
                "dq_family the validation family registry maps to a production rule -- "
                "Intelligence currently has no wired data-quality detection rule."
            ),
        )

    unmatched_actual = list(actual_findings)
    tp = fn = 0
    for dq in resolvable:
        mapping = family_registry.lookup(_dq_family_for(dq))
        assert mapping is not None
        found = next(
            (
                a
                for a in unmatched_actual
                if a.finding.rule_id in mapping.production_rule_families
                or (
                    mapping.production_domains
                    and mapping.production_domains & set(a.impacted_domains)
                )
            ),
            None,
        )
        if found is not None:
            unmatched_actual.remove(found)
            tp += 1
        else:
            fn += 1
    fp = len(unmatched_actual)

    precision = tp / (tp + fp) if (tp or fp) else None
    recall = tp / (tp + fn) if (tp or fn) else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and (precision + recall) > 0
        else None
    )
    return DataQualityScoreSummary(
        status=ValidationDimensionStatus.SCORED.value,
        summary=(
            f"Scored {len(resolvable)} of {len(dq_truth)} uploaded defect(s) with a "
            "resolvable family mapping."
        ),
        true_positive_count=tp,
        false_positive_count=fp,
        false_negative_count=fn,
        precision=precision,
        recall=recall,
        f1=f1,
    )
