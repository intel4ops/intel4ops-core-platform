from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.ground_truth_validation.family_registry import (
    ValidationFindingFamilyMappingRegistry,
    default_validation_finding_family_mapping_registry,
)
from app.models.ground_truth_validation import ValidationExpectedFinding, ValidationMatchType
from app.services.analysis_case_command_service import PrioritizedFinding

# Semantic matching only -- domain/family + entity overlap, never literal
# title/summary text equality. An expected finding with no entities
# specified degrades to a family/domain-only match (deliberately
# permissive: ground truth authors are not required to enumerate every
# entity). Domain is optional (section 7): when absent, the expected
# finding's expected_detection_family is resolved through the
# validation-only family registry to the production rule_ids/domains that
# could plausibly satisfy it -- domain is used directly only when the
# ground truth author supplied it (V1 packages, or a V2 author choosing
# to be explicit).


@dataclass(frozen=True)
class MatchedPair:
    match_type: str
    expected: ValidationExpectedFinding | None
    actual: PrioritizedFinding | None
    severity_match: bool | None
    entity_match: bool | None
    evidence_match: bool | None
    economic_variance_pct: float | None
    matched_dimensions: list[str]
    unmatched_dimensions: list[str]
    reason: str


def _entity_keys(entities: list[dict[str, object]] | None) -> set[tuple[object, object]]:
    return {(e.get("entity_type"), e.get("canonical_key")) for e in (entities or [])}


def _evidence_overlap(expected_refs: list[str], actual_source_labels: list[str]) -> bool | None:
    """Best-effort: an expected evidence_ref (e.g. "maintenance.csv:row_1-3")
    is considered matched if its filename portion appears among the
    dataset(s) that actually contributed to the finding. Returns None
    (unknown, not a fabricated False) when there is nothing to compare."""
    if not expected_refs or not actual_source_labels:
        return None
    for ref in expected_refs:
        ref_file = ref.split(":", 1)[0].strip().lower()
        if any(ref_file == label.strip().lower() for label in actual_source_labels):
            return True
    return False


def _economic_variance_pct(
    expected_impact: Decimal | None, actual: PrioritizedFinding
) -> float | None:
    if expected_impact is None:
        return None
    expected_value = float(expected_impact)
    if expected_value == 0:
        return None
    observed = actual.observed_values_by_currency
    if not observed:
        return None
    # Single-currency comparison only -- never summed across currencies.
    actual_value = next(iter(observed.values()))
    return abs(actual_value - expected_value) / abs(expected_value) * 100.0


def _candidate_matches_family_or_domain(
    expected: ValidationExpectedFinding,
    actual: PrioritizedFinding,
    family_registry: ValidationFindingFamilyMappingRegistry,
) -> bool:
    if expected.domain:
        return expected.domain in actual.impacted_domains
    mapping = family_registry.lookup(expected.expected_detection_family)
    if mapping is None:
        # No domain and no resolvable family -- cannot plausibly match
        # anything, by design (never a wildcard match).
        return False
    if actual.finding.rule_id in mapping.production_rule_families:
        return True
    if mapping.production_domains and (mapping.production_domains & set(actual.impacted_domains)):
        return True
    return False


def match_findings(
    expected_findings: list[ValidationExpectedFinding],
    actual_findings: list[PrioritizedFinding],
    source_labels_by_finding_id: dict[UUID, list[str]] | None = None,
    family_registry: ValidationFindingFamilyMappingRegistry | None = None,
) -> list[MatchedPair]:
    source_labels_by_finding_id = source_labels_by_finding_id or {}
    family_registry = family_registry or default_validation_finding_family_mapping_registry
    unmatched_actual = list(actual_findings)
    pairs: list[MatchedPair] = []

    for expected in expected_findings:
        expected_entity_keys = _entity_keys(expected.entities)
        found: PrioritizedFinding | None = None
        for actual in unmatched_actual:
            if not _candidate_matches_family_or_domain(expected, actual, family_registry):
                continue
            actual_entity_keys = _entity_keys(actual.finding.entities_json)
            if expected_entity_keys and not (expected_entity_keys & actual_entity_keys):
                continue
            found = actual
            break

        if found is None:
            pairs.append(
                MatchedPair(
                    match_type=ValidationMatchType.FALSE_NEGATIVE.value,
                    expected=expected,
                    actual=None,
                    severity_match=None,
                    entity_match=None,
                    evidence_match=None,
                    economic_variance_pct=None,
                    matched_dimensions=[],
                    unmatched_dimensions=["presence"],
                    reason=(
                        f"No production finding matched family/domain "
                        f"{expected.expected_detection_family or expected.domain!r} "
                        f"with overlapping entities {sorted(expected_entity_keys)}"
                    ),
                )
            )
            continue

        unmatched_actual.remove(found)
        actual_entity_keys = _entity_keys(found.finding.entities_json)
        severity_match = (found.finding.severity or "").lower() == (expected.severity or "").lower()
        entity_match = (
            (bool(expected_entity_keys) and expected_entity_keys <= actual_entity_keys)
            if expected_entity_keys
            else None
        )
        evidence_match = _evidence_overlap(
            expected.evidence_refs, source_labels_by_finding_id.get(found.finding.id, [])
        )
        matched_dims = ["presence"]
        unmatched_dims = []
        for label, value in (
            ("severity", severity_match),
            ("entity", entity_match),
            ("evidence", evidence_match),
        ):
            if value is True:
                matched_dims.append(label)
            elif value is False:
                unmatched_dims.append(label)
        pairs.append(
            MatchedPair(
                match_type=ValidationMatchType.TRUE_POSITIVE.value,
                expected=expected,
                actual=found,
                severity_match=severity_match,
                entity_match=entity_match,
                evidence_match=evidence_match,
                economic_variance_pct=_economic_variance_pct(
                    expected.expected_economic_impact, found
                ),
                matched_dimensions=matched_dims,
                unmatched_dimensions=unmatched_dims,
                reason=(
                    f"Matched production finding {found.finding.rule_id!r} on "
                    f"family/domain + entity overlap"
                ),
            )
        )

    for actual in unmatched_actual:
        pairs.append(
            MatchedPair(
                match_type=ValidationMatchType.FALSE_POSITIVE.value,
                expected=None,
                actual=actual,
                severity_match=None,
                entity_match=None,
                evidence_match=None,
                economic_variance_pct=None,
                matched_dimensions=[],
                unmatched_dimensions=["presence"],
                reason=f"Production finding {actual.finding.rule_id!r} matched no expected finding",
            )
        )
    return pairs


@dataclass(frozen=True)
class ScoreSummary:
    true_positive_count: int
    false_positive_count: int
    false_negative_count: int
    precision: float | None
    recall: float | None
    f1: float | None
    severity_accuracy: float | None
    entity_accuracy: float | None
    evidence_accuracy: float | None
    economic_variance_avg_pct: float | None
    critical_leakage_recall: float | None


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def score(pairs: list[MatchedPair]) -> ScoreSummary:
    tp = [p for p in pairs if p.match_type == ValidationMatchType.TRUE_POSITIVE.value]
    fp = [p for p in pairs if p.match_type == ValidationMatchType.FALSE_POSITIVE.value]
    fn = [p for p in pairs if p.match_type == ValidationMatchType.FALSE_NEGATIVE.value]

    precision = _ratio(len(tp), len(tp) + len(fp))
    recall = _ratio(len(tp), len(tp) + len(fn))
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and (precision + recall) > 0
        else None
    )

    severity_scored = [p for p in tp if p.severity_match is not None]
    entity_scored = [p for p in tp if p.entity_match is not None]
    evidence_scored = [p for p in tp if p.evidence_match is not None]
    variance_scored = [p.economic_variance_pct for p in tp if p.economic_variance_pct is not None]

    critical_expected = [
        p for p in tp + fn if (p.expected is not None and p.expected.severity.lower() == "critical")
    ]
    critical_tp = [
        p for p in critical_expected if p.match_type == ValidationMatchType.TRUE_POSITIVE.value
    ]

    return ScoreSummary(
        true_positive_count=len(tp),
        false_positive_count=len(fp),
        false_negative_count=len(fn),
        precision=precision,
        recall=recall,
        f1=f1,
        severity_accuracy=(
            sum(1 for p in severity_scored if p.severity_match) / len(severity_scored)
            if severity_scored
            else None
        ),
        entity_accuracy=(
            sum(1 for p in entity_scored if p.entity_match) / len(entity_scored)
            if entity_scored
            else None
        ),
        evidence_accuracy=(
            sum(1 for p in evidence_scored if p.evidence_match) / len(evidence_scored)
            if evidence_scored
            else None
        ),
        economic_variance_avg_pct=(
            sum(variance_scored) / len(variance_scored) if variance_scored else None
        ),
        critical_leakage_recall=(
            len(critical_tp) / len(critical_expected) if critical_expected else None
        ),
    )
