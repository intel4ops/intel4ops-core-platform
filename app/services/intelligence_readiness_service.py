from __future__ import annotations

from dataclasses import dataclass, field

from app.intelligence_packs.case_capability_index import CaseCapabilityIndex
from app.intelligence_packs.confidence_distribution import (
    EMPTY_CONFIDENCE_DISTRIBUTION,
    ConfidenceDistribution,
)
from app.intelligence_packs.registry import IntelligencePackDefinition

# ---------------------------------------------------------------------------
# P3.xxE.5 plan review correction 1: evaluate_readiness() no longer
# short-circuits through a DISABLED -> BLOCKED -> PARTIAL -> READY early-
# return chain. Every requirement category is evaluated independently
# first; nothing is discarded because an earlier check already failed --
# a BLOCKED result still carries every confidence shortfall, currency/unit
# violation, and missing-capability finding it would have carried on its
# own. The final status is derived ONCE, at the end, from the complete
# picture.
#
# Framework-free (no SQLAlchemy/FastAPI import) -- despite living under
# app/services/ for historical reasons, this module has always been pure
# (confirmed: it previously had zero callers anywhere in the codebase).
# Building the CaseCapabilityIndex this function consumes is the one
# DB-touching step, and that lives in
# app/services/case_capability_index_service.py, not here.
# ---------------------------------------------------------------------------

_STATUS_DISABLED = "DISABLED"
_STATUS_BLOCKED = "BLOCKED"
_STATUS_PARTIAL = "PARTIAL"
_STATUS_READY = "READY"


@dataclass(frozen=True)
class IntelligenceReadinessResult:
    pack: IntelligencePackDefinition
    status: str  # DISABLED | READY | PARTIAL | BLOCKED
    missing_domains: frozenset[str] = field(default_factory=frozenset)
    missing_fields: frozenset[str] = field(default_factory=frozenset)
    missing_entities: frozenset[str] = field(default_factory=frozenset)
    unresolved_currency: bool = False
    # P3.xxE.5 additions -- always populated when relevant, regardless of
    # which condition ultimately decided `status` (correction 1: never
    # hide secondary reasons because one blocker already exists).
    missing_canonical_entities: frozenset[str] = field(default_factory=frozenset)
    missing_relationships: frozenset[str] = field(default_factory=frozenset)
    missing_activities: frozenset[str] = field(default_factory=frozenset)
    missing_activity_sequences: frozenset[tuple[str, str]] = field(default_factory=frozenset)
    missing_states: frozenset[str] = field(default_factory=frozenset)
    missing_canonical_measures: frozenset[str] = field(default_factory=frozenset)
    below_confidence_threshold: frozenset[str] = field(default_factory=frozenset)
    currency_violation: bool = False
    unit_violation: bool = False
    # P3.xxE.5 corrected shadow certification: domains in
    # pack.required_resolved_trust_domains whose Trust assessment is not
    # (yet) resolved per index.domains_with_resolved_trust. A mandatory
    # unresolved Trust prerequisite is BLOCKED, never PARTIAL -- PARTIAL
    # stays reserved for structurally-available capabilities whose
    # declared confidence/evidence threshold falls short, which is a
    # different condition than a prerequisite simply not having run yet.
    missing_resolved_trust_domains: frozenset[str] = field(default_factory=frozenset)
    reason: str = ""


def _meets_confidence(
    distribution: ConfidenceDistribution,
    minimum: float,
    policy: str,
    minimum_coverage_ratio: float,
) -> bool:
    """A population that doesn't exist at all never "meets" a confidence
    bar -- callers only invoke this for categories already confirmed
    structurally present (missing_* is checked separately). minimum <= 0
    is always met -- a pack that declares no floor imposes none."""
    if minimum <= 0.0:
        return True
    if policy == "min":
        return distribution.min >= minimum
    if policy == "median":
        return distribution.median >= minimum
    if policy == "max":
        return distribution.max >= minimum
    # "coverage_above_threshold" -- the safe default (plan review
    # correction 2): a single high-confidence outlier can never carry a
    # low-confidence population past the bar.
    return distribution.coverage_above(minimum) >= minimum_coverage_ratio


def _evaluate_currency_safety(pack: IntelligencePackDefinition, index: CaseCapabilityIndex) -> bool:
    """True means VIOLATED. currency_agnostic packs never touch a
    monetary aggregation, so they can never violate currency safety by
    construction. single_currency_only (the house default, mirrors
    calculation_registry.py's own convention) is violated by more than
    one distinct currency observed among the pack's required canonical
    measures, or by a required measure with zero currency information at
    all when the pack's own measures actually need one."""
    if pack.currency_behavior == "currency_agnostic":
        return False
    if pack.currency_behavior == "multi_currency_aware":
        # explicit opt-in; this milestone builds no FX conversion, but
        # never blocks on it either
        return False
    relevant_currencies: set[str] = set()
    for measure_code in pack.required_canonical_measures:
        measure = index.canonical_measures.get(measure_code)
        if measure is not None:
            relevant_currencies |= measure.currencies_observed
    if not relevant_currencies:
        relevant_currencies = set(index.distinct_currencies_observed)
    return len(relevant_currencies) > 1


def _evaluate_unit_safety(pack: IntelligencePackDefinition, index: CaseCapabilityIndex) -> bool:
    """True means VIOLATED. Mirrors _evaluate_currency_safety's shape --
    no silent incompatible-unit aggregation (spec rule 17)."""
    if pack.unit_behavior in ("unit_agnostic", "unit_aware"):
        return False
    # "single_unit_only"
    for measure_code in pack.required_canonical_measures:
        units = index.distinct_units_observed_by_measure.get(measure_code, frozenset())
        if len(units) > 1:
            return True
    return False


def evaluate_readiness(
    pack: IntelligencePackDefinition, index: CaseCapabilityIndex
) -> IntelligenceReadinessResult:
    """Explainable readiness -- never a generic 'engine unavailable'.
    Every requirement category is checked independently (step A);
    everything found is preserved on the result (step B); status is
    derived once, at the end, from the complete picture (step C) -- see
    this module's own header comment."""
    # --- A. evaluate every requirement category independently ---
    missing_domains = pack.required_domains - index.available_domains
    missing_fields = pack.required_canonical_fields - index.available_canonical_fields
    missing_entities = pack.required_entities - index.resolved_entity_types
    # P3.xxI.2C: mirrors alternative_canonical_measure_sets immediately
    # below -- when alternatives are declared, readiness is satisfied by
    # any ONE alternative entity-type set being fully present, not the
    # primary required_canonical_entities set specifically. satisfied_
    # canonical_entities is the SPECIFIC set that satisfied readiness (the
    # primary set when no alternatives apply or none are satisfied),
    # carried forward so the confidence-threshold check below evaluates
    # the entity type(s) that actually matter for this case, never a
    # type that happens to be absent merely because a different
    # alternative won.
    missing_canonical_entities: frozenset[str]
    if pack.alternative_canonical_entity_sets:
        satisfied_canonical_entities = next(
            (
                entity_set
                for entity_set in pack.alternative_canonical_entity_sets
                if entity_set <= index.canonical_entity_types_present
            ),
            None,
        )
        if satisfied_canonical_entities is not None:
            missing_canonical_entities = frozenset()
        else:
            missing_canonical_entities = (
                pack.required_canonical_entities - index.canonical_entity_types_present
            )
            satisfied_canonical_entities = (
                pack.required_canonical_entities - missing_canonical_entities
            )
    else:
        missing_canonical_entities = (
            pack.required_canonical_entities - index.canonical_entity_types_present
        )
        satisfied_canonical_entities = pack.required_canonical_entities - missing_canonical_entities
    missing_relationships = pack.required_relationships - index.canonical_relationship_types_present
    missing_activities = pack.required_activities - index.activity_types_present
    missing_activity_sequences = pack.required_activity_sequences - index.precedes_pairs_present
    missing_states = pack.required_states - index.named_states_present
    available_measure_codes = frozenset(index.canonical_measures)
    missing_canonical_measures: frozenset[str]
    if pack.alternative_canonical_measure_sets and any(
        measure_set <= available_measure_codes
        for measure_set in pack.alternative_canonical_measure_sets
    ):
        missing_canonical_measures = frozenset()
    else:
        missing_canonical_measures = pack.required_canonical_measures - available_measure_codes
    unresolved_currency = pack.currency_required and index.currency_unresolved
    currency_violation = _evaluate_currency_safety(pack, index)
    unit_violation = _evaluate_unit_safety(pack, index)
    missing_resolved_trust_domains = (
        pack.required_resolved_trust_domains - index.domains_with_resolved_trust
    )

    below_confidence_threshold: set[str] = set()
    for entity_type in satisfied_canonical_entities:
        distribution = index.canonical_entity_identity_confidence_by_type.get(
            entity_type, EMPTY_CONFIDENCE_DISTRIBUTION
        )
        if not _meets_confidence(
            distribution,
            pack.minimum_entity_identity_confidence,
            pack.confidence_aggregation_policy,
            pack.minimum_coverage_ratio,
        ):
            below_confidence_threshold.add(f"entity_identity.{entity_type}")
    for relationship_type in pack.required_relationships - missing_relationships:
        distribution = index.canonical_relationship_confidence_by_type.get(
            relationship_type, EMPTY_CONFIDENCE_DISTRIBUTION
        )
        if not _meets_confidence(
            distribution,
            pack.minimum_relationship_confidence,
            pack.confidence_aggregation_policy,
            pack.minimum_coverage_ratio,
        ):
            below_confidence_threshold.add(f"relationship.{relationship_type}")
    for activity_type in pack.required_activities - missing_activities:
        distribution = index.activity_type_confidence_by_type.get(
            activity_type, EMPTY_CONFIDENCE_DISTRIBUTION
        )
        if not _meets_confidence(
            distribution,
            pack.minimum_activity_confidence,
            pack.confidence_aggregation_policy,
            pack.minimum_coverage_ratio,
        ):
            below_confidence_threshold.add(f"activity.{activity_type}")
    for pair in pack.required_activity_sequences - missing_activity_sequences:
        distribution = index.precedes_pair_confidence.get(pair, EMPTY_CONFIDENCE_DISTRIBUTION)
        if not _meets_confidence(
            distribution,
            pack.minimum_process_confidence,
            pack.confidence_aggregation_policy,
            pack.minimum_coverage_ratio,
        ):
            below_confidence_threshold.add(f"activity_sequence.{pair[0]}->{pair[1]}")
    for state in pack.required_states - missing_states:
        distribution = index.state_meaning_confidence_by_state.get(
            state, EMPTY_CONFIDENCE_DISTRIBUTION
        )
        if not _meets_confidence(
            distribution,
            pack.minimum_process_confidence,
            pack.confidence_aggregation_policy,
            pack.minimum_coverage_ratio,
        ):
            below_confidence_threshold.add(f"state.{state}")

    # --- B. nothing above is discarded -- every field below is populated
    # from the independent checks, regardless of which one(s) end up
    # deciding `status`. ---

    # --- C. derive the final status once, from the complete picture ---
    if pack.is_disabled:
        status = _STATUS_DISABLED
    elif (
        missing_domains
        or missing_fields
        or missing_entities
        or missing_canonical_entities
        or missing_relationships
        or missing_activities
        or missing_activity_sequences
        or missing_states
        or missing_canonical_measures
        or unresolved_currency
        or currency_violation
        or unit_violation
        or missing_resolved_trust_domains
    ):
        status = _STATUS_BLOCKED
    elif below_confidence_threshold:
        status = _STATUS_PARTIAL
    else:
        status = _STATUS_READY

    reasons = []
    if missing_domains:
        reasons.append(f"missing domains: {', '.join(sorted(missing_domains))}")
    if missing_fields:
        reasons.append(f"missing canonical fields: {', '.join(sorted(missing_fields))}")
    if missing_entities:
        reasons.append(f"missing resolved entities: {', '.join(sorted(missing_entities))}")
    if missing_canonical_entities:
        reasons.append(
            f"missing canonical entity types: {', '.join(sorted(missing_canonical_entities))}"
        )
    if missing_relationships:
        reasons.append(f"missing relationship types: {', '.join(sorted(missing_relationships))}")
    if missing_activities:
        reasons.append(f"missing activity types: {', '.join(sorted(missing_activities))}")
    if missing_activity_sequences:
        reasons.append(
            "missing activity sequences: "
            + ", ".join(f"{a}->{b}" for a, b in sorted(missing_activity_sequences))
        )
    if missing_states:
        reasons.append(f"missing states: {', '.join(sorted(missing_states))}")
    if missing_canonical_measures:
        reasons.append(
            f"missing canonical measures: {', '.join(sorted(missing_canonical_measures))}"
        )
    if unresolved_currency:
        reasons.append("currency required but unresolved")
    if currency_violation:
        reasons.append(f"currency safety violated ({pack.currency_behavior})")
    if unit_violation:
        reasons.append(f"unit safety violated ({pack.unit_behavior})")
    if missing_resolved_trust_domains:
        reasons.append(
            "unresolved Trust assessment for domain(s): "
            + ", ".join(sorted(missing_resolved_trust_domains))
        )
    if below_confidence_threshold:
        reasons.append(
            f"below confidence threshold: {', '.join(sorted(below_confidence_threshold))}"
        )
    reason = "; ".join(reasons) if reasons else "all requirements satisfied"

    return IntelligenceReadinessResult(
        pack=pack,
        status=status,
        missing_domains=frozenset(missing_domains),
        missing_fields=frozenset(missing_fields),
        missing_entities=frozenset(missing_entities),
        unresolved_currency=unresolved_currency,
        missing_canonical_entities=frozenset(missing_canonical_entities),
        missing_relationships=frozenset(missing_relationships),
        missing_activities=frozenset(missing_activities),
        missing_activity_sequences=frozenset(missing_activity_sequences),
        missing_states=frozenset(missing_states),
        missing_canonical_measures=frozenset(missing_canonical_measures),
        below_confidence_threshold=frozenset(below_confidence_threshold),
        currency_violation=currency_violation,
        unit_violation=unit_violation,
        missing_resolved_trust_domains=frozenset(missing_resolved_trust_domains),
        reason=reason,
    )
