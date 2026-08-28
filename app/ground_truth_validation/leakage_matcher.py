from __future__ import annotations

from dataclasses import dataclass

from app.ground_truth_validation.family_registry import (
    ValidationFindingFamilyMappingRegistry,
    default_validation_finding_family_mapping_registry,
)
from app.models.ground_truth_validation import (
    ValidationDimensionStatus,
    ValidationLeakageTruth,
    ValidationMatchType,
)
from app.services.analysis_case_command_service import PrioritizedFinding

# Leakage / value accuracy dimension (section 11B). Presence (TP/FP/FN --
# "did production find something matching this leakage's family/entities
# at all") is always computable from persisted Finding rows. Value
# accuracy (variance %, recoverable-value accuracy) is only computable
# when the matched Finding actually carries a comparable observed
# economic value -- today's wired rules (MAINT-001/XDOM-A/XDOM-B) publish
# COUNT-typed findings with no exposure_value (P3.xxC.1's deliberate
# economics boundary), so value metrics will honestly read as unavailable
# against the current production rule set. That is a true statement about
# production coverage, not a defect in this matcher -- it will start
# scoring the moment a rule publishes a comparable value.


def _entity_keys(entities: list[dict[str, object]] | None) -> set[tuple[object, object]]:
    return {(e.get("entity_type"), e.get("canonical_key")) for e in (entities or [])}


@dataclass(frozen=True)
class LeakageMatchedPair:
    match_type: str
    expected: ValidationLeakageTruth | None
    actual: PrioritizedFinding | None
    economic_variance_pct: float | None
    reason: str


def _candidate_matches(
    leakage: ValidationLeakageTruth,
    actual: PrioritizedFinding,
    family_registry: ValidationFindingFamilyMappingRegistry,
) -> bool:
    mapping = family_registry.lookup(leakage.detection_family)
    if mapping is None:
        return False
    if actual.finding.rule_id in mapping.production_rule_families:
        return True
    return bool(
        mapping.production_domains and (mapping.production_domains & set(actual.impacted_domains))
    )


def match_leakage(
    leakage_truth: list[ValidationLeakageTruth],
    actual_findings: list[PrioritizedFinding],
    family_registry: ValidationFindingFamilyMappingRegistry | None = None,
) -> list[LeakageMatchedPair]:
    if not leakage_truth:
        # No leakage truth was uploaded for this ground-truth version --
        # this dimension is NOT_AVAILABLE, not "every actual finding is a
        # false positive." Never fabricate a comparison against nothing.
        return []

    family_registry = family_registry or default_validation_finding_family_mapping_registry
    unmatched_actual = list(actual_findings)
    pairs: list[LeakageMatchedPair] = []

    for leakage in leakage_truth:
        entity_keys = _entity_keys(leakage.entities)
        found: PrioritizedFinding | None = None
        for actual in unmatched_actual:
            if not _candidate_matches(leakage, actual, family_registry):
                continue
            actual_keys = _entity_keys(actual.finding.entities_json)
            if entity_keys and not (entity_keys & actual_keys):
                continue
            found = actual
            break

        if found is None:
            pairs.append(
                LeakageMatchedPair(
                    match_type=ValidationMatchType.FALSE_NEGATIVE.value,
                    expected=leakage,
                    actual=None,
                    economic_variance_pct=None,
                    reason=f"No production finding matched leakage {leakage.truth_leakage_id!r}",
                )
            )
            continue

        unmatched_actual.remove(found)
        variance = None
        if leakage.true_leakage_value is not None:
            observed = found.observed_values_by_currency
            if observed:
                expected_value = float(leakage.true_leakage_value)
                if expected_value != 0:
                    actual_value = next(iter(observed.values()))
                    variance = abs(actual_value - expected_value) / abs(expected_value) * 100.0
        pairs.append(
            LeakageMatchedPair(
                match_type=ValidationMatchType.TRUE_POSITIVE.value,
                expected=leakage,
                actual=found,
                economic_variance_pct=variance,
                reason=f"Matched production finding {found.finding.rule_id!r}",
            )
        )

    for actual in unmatched_actual:
        pairs.append(
            LeakageMatchedPair(
                match_type=ValidationMatchType.FALSE_POSITIVE.value,
                expected=None,
                actual=actual,
                economic_variance_pct=None,
                reason=f"Production finding {actual.finding.rule_id!r} matched no leakage truth",
            )
        )
    return pairs


@dataclass(frozen=True)
class LeakageScoreSummary:
    status: str
    true_positive_count: int
    false_positive_count: int
    false_negative_count: int
    precision: float | None
    recall: float | None
    f1: float | None
    total_true_leakage_value_by_currency: dict[str, float]
    total_recoverable_value_by_currency: dict[str, float]
    value_weighted_recall: float | None
    economic_variance_avg_pct: float | None
    summary: str


def score_leakage(pairs: list[LeakageMatchedPair]) -> LeakageScoreSummary:
    if not pairs:
        return LeakageScoreSummary(
            status=ValidationDimensionStatus.NOT_AVAILABLE.value,
            true_positive_count=0,
            false_positive_count=0,
            false_negative_count=0,
            precision=None,
            recall=None,
            f1=None,
            total_true_leakage_value_by_currency={},
            total_recoverable_value_by_currency={},
            value_weighted_recall=None,
            economic_variance_avg_pct=None,
            summary="No leakage truth was uploaded for this ground-truth version.",
        )

    tp = [p for p in pairs if p.match_type == ValidationMatchType.TRUE_POSITIVE.value]
    fp = [p for p in pairs if p.match_type == ValidationMatchType.FALSE_POSITIVE.value]
    fn = [p for p in pairs if p.match_type == ValidationMatchType.FALSE_NEGATIVE.value]

    precision = len(tp) / (len(tp) + len(fp)) if (tp or fp) else None
    recall = len(tp) / (len(tp) + len(fn)) if (tp or fn) else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and (precision + recall) > 0
        else None
    )

    true_value_by_currency: dict[str, float] = {}
    recoverable_value_by_currency: dict[str, float] = {}
    for pair in tp + fn:
        if pair.expected is None:
            continue
        currency = pair.expected.currency or "UNSPECIFIED"
        if pair.expected.true_leakage_value is not None:
            true_value_by_currency[currency] = true_value_by_currency.get(currency, 0.0) + float(
                pair.expected.true_leakage_value
            )
        if pair.expected.recoverable_value is not None:
            recoverable_value_by_currency[currency] = recoverable_value_by_currency.get(
                currency, 0.0
            ) + float(pair.expected.recoverable_value)

    value_weighted_recall = None
    total_value = sum(true_value_by_currency.values())
    if total_value > 0:
        detected_value = sum(
            float(p.expected.true_leakage_value)
            for p in tp
            if p.expected is not None and p.expected.true_leakage_value is not None
        )
        value_weighted_recall = detected_value / total_value

    variances = [p.economic_variance_pct for p in tp if p.economic_variance_pct is not None]
    economic_variance_avg_pct = sum(variances) / len(variances) if variances else None

    if variances:
        status = ValidationDimensionStatus.SCORED.value
        summary = "Presence and value comparisons both available."
    elif tp or fp or fn:
        status = ValidationDimensionStatus.PARTIALLY_SCORED.value
        summary = (
            "Presence (TP/FP/FN) scored; no matched production finding carried a "
            "comparable observed economic value, so value variance is not available."
        )
    else:
        status = ValidationDimensionStatus.NOT_AVAILABLE.value
        summary = "No comparable production findings were available."

    return LeakageScoreSummary(
        status=status,
        true_positive_count=len(tp),
        false_positive_count=len(fp),
        false_negative_count=len(fn),
        precision=precision,
        recall=recall,
        f1=f1,
        total_true_leakage_value_by_currency=true_value_by_currency,
        total_recoverable_value_by_currency=recoverable_value_by_currency,
        value_weighted_recall=value_weighted_recall,
        economic_variance_avg_pct=economic_variance_avg_pct,
        summary=summary,
    )
