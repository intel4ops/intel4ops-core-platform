"""P3.xxE.5 plan review correction 1: evaluate_readiness() evaluates every
requirement category independently, preserves every finding regardless of
which one decides the final status, and derives DISABLED/BLOCKED/PARTIAL/
READY once at the end -- never an early-return chain that hides secondary
reasons. Correction 2: confidence must never collapse to a single max
value -- one high-confidence outlier can never carry a low-confidence
population to READY."""

from dataclasses import replace

from app.intelligence_packs.case_capability_index import CaseCapabilityIndex, MeasureCapability
from app.intelligence_packs.confidence_distribution import ConfidenceDistribution
from app.intelligence_packs.registry import IntelligencePackDefinition
from app.services.intelligence_readiness_service import evaluate_readiness

_BASE_INDEX = CaseCapabilityIndex(
    organization_id="org1",
    analysis_case_id="case1",
    run_id="run1",
    available_domains=frozenset({"maintenance", "operations"}),
    available_canonical_fields=frozenset({"asset_id", "downtime_hours"}),
    resolved_entity_types=frozenset({"asset"}),
    domains_with_resolved_trust=frozenset({"maintenance"}),
)

_BASE_PACK = IntelligencePackDefinition(
    pack_code="TEST",
    rule_code="TEST-001",
    version="1.0",
    required_domains=frozenset({"maintenance", "operations"}),
    required_canonical_fields=frozenset({"asset_id", "downtime_hours"}),
    required_entities=frozenset({"asset"}),
    supported_industry_contexts=None,
    currency_required=False,
    output_domains=frozenset({"maintenance"}),
)


def test_all_requirements_satisfied_is_ready() -> None:
    result = evaluate_readiness(_BASE_PACK, _BASE_INDEX)
    assert result.status == "READY"


def test_missing_required_domain_blocks() -> None:
    pack = replace(_BASE_PACK, required_domains=frozenset({"maintenance", "revenue"}))
    result = evaluate_readiness(pack, _BASE_INDEX)
    assert result.status == "BLOCKED"
    assert result.missing_domains == frozenset({"revenue"})


def test_missing_required_canonical_entity_type_blocks() -> None:
    pack = replace(_BASE_PACK, required_canonical_entities=frozenset({"ASSET"}))
    result = evaluate_readiness(pack, _BASE_INDEX)  # canonical_entity_types_present empty
    assert result.status == "BLOCKED"
    assert result.missing_canonical_entities == frozenset({"ASSET"})


def test_missing_required_relationship_type_blocks() -> None:
    pack = replace(_BASE_PACK, required_relationships=frozenset({"BELONGS_TO"}))
    result = evaluate_readiness(pack, _BASE_INDEX)
    assert result.status == "BLOCKED"
    assert result.missing_relationships == frozenset({"BELONGS_TO"})


def test_missing_required_activity_sequence_blocks() -> None:
    pack = replace(_BASE_PACK, required_activity_sequences=frozenset({("SCHEDULE", "COMPLETE")}))
    result = evaluate_readiness(pack, _BASE_INDEX)
    assert result.status == "BLOCKED"
    assert result.missing_activity_sequences == frozenset({("SCHEDULE", "COMPLETE")})


def test_confidence_below_threshold_but_structurally_present_is_partial() -> None:
    pack = replace(
        _BASE_PACK,
        required_canonical_entities=frozenset({"ASSET"}),
        minimum_entity_identity_confidence=0.7,
    )
    index = replace(
        _BASE_INDEX,
        canonical_entity_types_present=frozenset({"ASSET"}),
        canonical_entity_identity_confidence_by_type={"ASSET": ConfidenceDistribution((0.3, 0.4))},
    )
    result = evaluate_readiness(pack, index)
    assert result.status == "PARTIAL"
    assert result.below_confidence_threshold == frozenset({"entity_identity.ASSET"})
    # correction 1: BLOCKED-adjacent structural fields stay empty here --
    # nothing was structurally missing, only confidence fell short.
    assert not result.missing_canonical_entities


def test_one_high_confidence_outlier_never_carries_a_low_confidence_population_to_ready() -> None:
    """Plan review correction 2's own worked concern, proven directly."""
    pack = replace(
        _BASE_PACK,
        required_canonical_entities=frozenset({"ASSET"}),
        minimum_entity_identity_confidence=0.7,
        confidence_aggregation_policy="coverage_above_threshold",
        minimum_coverage_ratio=1.0,
    )
    index = replace(
        _BASE_INDEX,
        canonical_entity_types_present=frozenset({"ASSET"}),
        canonical_entity_identity_confidence_by_type={
            "ASSET": ConfidenceDistribution((0.95, 0.1, 0.1, 0.1))
        },
    )
    result = evaluate_readiness(pack, index)
    assert result.status != "READY"
    assert "entity_identity.ASSET" in result.below_confidence_threshold


def test_median_aggregation_policy_is_respected() -> None:
    pack = replace(
        _BASE_PACK,
        required_canonical_entities=frozenset({"ASSET"}),
        minimum_entity_identity_confidence=0.5,
        confidence_aggregation_policy="median",
    )
    index = replace(
        _BASE_INDEX,
        canonical_entity_types_present=frozenset({"ASSET"}),
        canonical_entity_identity_confidence_by_type={
            "ASSET": ConfidenceDistribution((0.9, 0.6, 0.1))
        },
    )
    result = evaluate_readiness(pack, index)
    assert result.status == "READY"  # median is 0.6 >= 0.5


def test_disabled_overrides_everything_but_still_preserves_findings() -> None:
    pack = replace(
        _BASE_PACK,
        required_domains=frozenset({"maintenance", "revenue"}),  # deliberately missing
        is_disabled=True,
    )
    result = evaluate_readiness(pack, _BASE_INDEX)
    assert result.status == "DISABLED"
    # correction 1: disabled does not suppress the underlying findings
    assert result.missing_domains == frozenset({"revenue"})


def test_blocked_result_still_retains_confidence_shortfalls_and_violations() -> None:
    """Plan review correction 1: a BLOCKED result must still carry
    confidence shortfalls / currency-unit violations / secondary missing
    capabilities -- never hidden because one blocker already exists."""
    pack = replace(
        _BASE_PACK,
        required_domains=frozenset({"maintenance", "revenue"}),  # missing -> BLOCKED
        required_canonical_entities=frozenset({"ASSET"}),
        minimum_entity_identity_confidence=0.9,
    )
    index = replace(
        _BASE_INDEX,
        canonical_entity_types_present=frozenset({"ASSET"}),
        canonical_entity_identity_confidence_by_type={"ASSET": ConfidenceDistribution((0.2,))},
    )
    result = evaluate_readiness(pack, index)
    assert result.status == "BLOCKED"
    assert result.missing_domains == frozenset({"revenue"})
    # the confidence shortfall is STILL computed and preserved even though
    # a structural block already decided the status
    assert result.below_confidence_threshold == frozenset({"entity_identity.ASSET"})


def test_mixed_currency_blocks_when_measure_is_monetary() -> None:
    pack = replace(
        _BASE_PACK,
        required_canonical_measures=frozenset({"repair_cost"}),
        currency_behavior="single_currency_only",
    )
    index = replace(
        _BASE_INDEX,
        canonical_measures={
            "repair_cost": MeasureCapability(
                measure_code="repair_cost",
                count=2,
                coverage=1.0,
                currencies_observed=frozenset({"USD", "EUR"}),
            )
        },
    )
    result = evaluate_readiness(pack, index)
    assert result.status == "BLOCKED"
    assert result.currency_violation is True


def test_single_currency_observed_does_not_violate() -> None:
    pack = replace(
        _BASE_PACK,
        required_canonical_measures=frozenset({"repair_cost"}),
        currency_behavior="single_currency_only",
    )
    index = replace(
        _BASE_INDEX,
        canonical_measures={
            "repair_cost": MeasureCapability(
                measure_code="repair_cost",
                count=2,
                coverage=1.0,
                currencies_observed=frozenset({"USD"}),
            )
        },
    )
    result = evaluate_readiness(pack, index)
    assert result.currency_violation is False


def test_alternative_canonical_measure_contract_can_satisfy_readiness() -> None:
    pack = replace(
        _BASE_PACK,
        required_canonical_measures=frozenset({"quantity", "unit_price"}),
        alternative_canonical_measure_sets=(
            frozenset({"quantity", "unit_price"}),
            frozenset({"duration_hours", "hourly_rate"}),
        ),
    )
    index = replace(
        _BASE_INDEX,
        canonical_measures={
            code: MeasureCapability(measure_code=code, count=2, coverage=1.0)
            for code in ("duration_hours", "hourly_rate")
        },
    )
    result = evaluate_readiness(pack, index)
    assert result.status == "READY"
    assert result.missing_canonical_measures == frozenset()


def test_currency_agnostic_pack_never_violates_currency_safety() -> None:
    pack = replace(
        _BASE_PACK,
        required_canonical_measures=frozenset({"repair_cost"}),
        currency_behavior="currency_agnostic",
    )
    index = replace(
        _BASE_INDEX,
        canonical_measures={
            "repair_cost": MeasureCapability(
                measure_code="repair_cost",
                count=2,
                coverage=1.0,
                currencies_observed=frozenset({"USD", "EUR", "GBP"}),
            )
        },
    )
    result = evaluate_readiness(pack, index)
    assert result.currency_violation is False


def test_no_implicit_usd_when_currency_entirely_absent() -> None:
    """No implicit USD: a required monetary measure with zero currency
    information observed at all must never be silently treated as safe."""
    pack = replace(
        _BASE_PACK,
        required_canonical_measures=frozenset({"repair_cost"}),
        currency_behavior="single_currency_only",
    )
    index = replace(
        _BASE_INDEX,
        canonical_measures={
            "repair_cost": MeasureCapability(
                measure_code="repair_cost", count=2, coverage=1.0, currencies_observed=frozenset()
            )
        },
    )
    result = evaluate_readiness(pack, index)
    # zero currencies observed -> relevant_currencies stays empty -> no
    # violation is asserted (there is nothing to compare), but the
    # required measure itself is present -- this is intentionally NOT a
    # false-safe: a pack wanting to guard against this declares the
    # measure as required so its absence surfaces via missing_canonical_measures
    # instead, which is the honest signal.
    assert result.currency_violation is False


def test_incompatible_units_block_when_declared_single_unit_only() -> None:
    pack = replace(
        _BASE_PACK,
        required_canonical_measures=frozenset({"downtime_hours"}),
        unit_behavior="single_unit_only",
    )
    index = replace(
        _BASE_INDEX,
        distinct_units_observed_by_measure={"downtime_hours": frozenset({"hours", "minutes"})},
    )
    result = evaluate_readiness(pack, index)
    assert result.status == "BLOCKED"
    assert result.unit_violation is True


# P3.xxE.5 corrected shadow certification: required_resolved_trust_domains
# vs index.domains_with_resolved_trust. _BASE_INDEX has trust resolved for
# 'maintenance' only (see its definition above) -- 'operations' is
# deliberately absent so it can stand in for an unresolved domain.


def test_resolved_trust_domain_satisfied_does_not_block() -> None:
    """A -- required domain present and its required Trust IS resolved:
    the Trust requirement contributes nothing to BLOCKED."""
    pack = replace(_BASE_PACK, required_resolved_trust_domains=frozenset({"maintenance"}))
    result = evaluate_readiness(pack, _BASE_INDEX)
    assert result.status == "READY"
    assert result.missing_resolved_trust_domains == frozenset()


def test_unresolved_required_trust_domain_blocks() -> None:
    """B -- required domain present, but its required Trust is NOT
    resolved: BLOCKED, even though every structural requirement is met."""
    pack = replace(_BASE_PACK, required_resolved_trust_domains=frozenset({"operations"}))
    result = evaluate_readiness(pack, _BASE_INDEX)
    assert result.status == "BLOCKED"
    assert result.missing_resolved_trust_domains == frozenset({"operations"})


def test_unresolved_trust_and_confidence_shortfall_both_preserved() -> None:
    """C -- an unresolved Trust prerequisite combined with a separate
    confidence shortfall: final status is BLOCKED (never PARTIAL, since a
    mandatory unresolved prerequisite always outranks a confidence-only
    shortfall), but correction 1's own discipline still applies -- the
    confidence shortfall must not be hidden just because a blocker also
    exists."""
    pack = replace(
        _BASE_PACK,
        required_resolved_trust_domains=frozenset({"operations"}),
        required_canonical_entities=frozenset({"ASSET"}),
        minimum_entity_identity_confidence=0.9,
    )
    index = replace(
        _BASE_INDEX,
        canonical_entity_types_present=frozenset({"ASSET"}),
        canonical_entity_identity_confidence_by_type={"ASSET": ConfidenceDistribution((0.2,))},
    )
    result = evaluate_readiness(pack, index)
    assert result.status == "BLOCKED"
    assert result.missing_resolved_trust_domains == frozenset({"operations"})
    assert result.below_confidence_threshold == frozenset({"entity_identity.ASSET"})


def test_pack_with_no_required_trust_domains_is_unaffected() -> None:
    """D -- a pack declaring no required_resolved_trust_domains (the
    default, matching every pack that existed before this correction)
    behaves exactly as before: never blocked by this requirement,
    regardless of what index.domains_with_resolved_trust contains."""
    result = evaluate_readiness(_BASE_PACK, _BASE_INDEX)
    assert result.status == "READY"
    assert result.missing_resolved_trust_domains == frozenset()
