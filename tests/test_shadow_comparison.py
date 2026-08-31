"""P3.xxE.5 Phase 1 (SHADOW): derive_legacy_activation() faithfully
re-derives the pre-existing cross_domain_intelligence stage's own
activation condition; compare_shadow() pairs it against the new generic
readiness evaluator without changing what actually runs."""

from dataclasses import replace

from app.intelligence_packs.case_capability_index import CaseCapabilityIndex
from app.intelligence_packs.confidence_distribution import ConfidenceDistribution
from app.intelligence_packs.registry import default_intelligence_pack_registry
from app.intelligence_packs.shadow_comparison import compare_shadow, derive_legacy_activation

_XDOM_A = "XDOM-A-ASSET-FAILURE-LOST-ACTIVITY"
_XDOM_B = "XDOM-B-LOST-ACTIVITY-REVENUE-GAP"

_BASE_INDEX = CaseCapabilityIndex(
    organization_id="org1",
    analysis_case_id="case1",
    run_id="run1",
    available_domains=frozenset(),
    domains_with_resolved_trust=frozenset(),
)


def _index(**overrides: object) -> CaseCapabilityIndex:
    return replace(_BASE_INDEX, **overrides)  # type: ignore[arg-type]


def test_domain_presence_alone_is_not_sufficient_for_legacy_activation() -> None:
    """Domain name alone cannot activate XDOM-A -- trust must also be
    resolved for the anchor domain, exactly matching the pre-existing
    orchestration stage's own condition."""
    index = _index(available_domains=frozenset({"maintenance", "operations"}))
    result = derive_legacy_activation(_XDOM_A, index)
    assert result.activated is False
    assert "trust" in result.reason


def test_domain_and_resolved_trust_together_activate_legacy() -> None:
    index = _index(
        available_domains=frozenset({"maintenance", "operations"}),
        domains_with_resolved_trust=frozenset({"maintenance"}),
    )
    result = derive_legacy_activation(_XDOM_A, index)
    assert result.activated is True


def test_dataset_filename_alone_is_not_sufficient_for_governed_readiness() -> None:
    """CaseCapabilityIndex has no filename/label field at all -- a
    dataset's filename can never influence readiness by construction,
    regardless of what it's named."""
    assert "filename" not in CaseCapabilityIndex.__dataclass_fields__
    assert "dataset_label" not in CaseCapabilityIndex.__dataclass_fields__
    assert "source_label" not in CaseCapabilityIndex.__dataclass_fields__


def test_compare_shadow_agrees_when_both_paths_reach_the_same_conclusion() -> None:
    registry = default_intelligence_pack_registry()
    pack = next(p for p in registry.all() if p.rule_code == _XDOM_A)
    index = _index(
        available_domains=frozenset({"maintenance", "operations"}),
        available_canonical_fields=frozenset(
            {"asset_id", "downtime_hours", "operational_event_id"}
        ),
        resolved_entity_types=frozenset({"asset", "operational_event"}),
        domains_with_resolved_trust=frozenset({"maintenance"}),
        canonical_entity_types_present=frozenset({"ASSET"}),
        canonical_entity_identity_confidence_by_type={
            "ASSET": ConfidenceDistribution((0.9, 0.9, 0.9))
        },
    )
    result = compare_shadow(pack, index)
    assert result.legacy.activated is True
    assert result.governed.status == "READY"
    assert result.agree is True


def test_compare_shadow_disagrees_when_legacy_activates_but_governed_blocks() -> None:
    """Legacy only checks domain+trust; the governed evaluator additionally
    requires the canonical entity to actually be resolved -- a real,
    expected disagreement case this milestone's shadow run should surface."""
    registry = default_intelligence_pack_registry()
    pack = next(p for p in registry.all() if p.rule_code == _XDOM_A)
    index = _index(
        available_domains=frozenset({"maintenance", "operations"}),
        available_canonical_fields=frozenset(
            {"asset_id", "downtime_hours", "operational_event_id"}
        ),
        resolved_entity_types=frozenset({"asset", "operational_event"}),
        domains_with_resolved_trust=frozenset({"maintenance"}),
        # canonical_entity_types_present deliberately left empty
    )
    result = compare_shadow(pack, index)
    assert result.legacy.activated is True
    assert result.governed.status == "BLOCKED"
    assert result.agree is False


def test_xdom_b_unresolved_operations_trust_now_agrees_blocked() -> None:
    """F -- P3.xxE.5 corrected shadow certification: the exact fixture
    shape that produced the original corpus-wide disagreement on
    FIELDMAINT-004/005 (every structural XDOM-B requirement satisfied, but
    'operations' Trust unresolved). With required_resolved_trust_domains
    now populated on the real registry pack, legacy and governed agree:
    both withhold activation."""
    registry = default_intelligence_pack_registry()
    pack = next(p for p in registry.all() if p.rule_code == _XDOM_B)
    index = _index(
        available_domains=frozenset({"operations", "revenue"}),
        available_canonical_fields=frozenset(
            {"operational_event_id", "operational_event_status", "transaction_amount"}
        ),
        resolved_entity_types=frozenset({"operational_event"}),
        domains_with_resolved_trust=frozenset(),  # 'operations' deliberately unresolved
    )
    result = compare_shadow(pack, index)
    assert result.legacy.activated is False
    assert "trust" in result.legacy.reason
    assert result.governed.status == "BLOCKED"
    assert result.governed.missing_resolved_trust_domains == frozenset({"operations"})
    assert result.agree is True


def test_xdom_b_resolved_operations_trust_reaches_ready() -> None:
    """G -- the positive counterpart: once 'operations' Trust is resolved
    and every other XDOM-B requirement is satisfied, governed reaches
    READY (and agrees with legacy, which also activates)."""
    registry = default_intelligence_pack_registry()
    pack = next(p for p in registry.all() if p.rule_code == _XDOM_B)
    index = _index(
        available_domains=frozenset({"operations", "revenue"}),
        available_canonical_fields=frozenset(
            {"operational_event_id", "operational_event_status", "transaction_amount"}
        ),
        resolved_entity_types=frozenset({"operational_event"}),
        domains_with_resolved_trust=frozenset({"operations"}),
    )
    result = compare_shadow(pack, index)
    assert result.legacy.activated is True
    assert result.governed.status == "READY"
    assert result.agree is True


def test_unknown_rule_code_never_activates_legacy() -> None:
    index = _index(
        available_domains=frozenset({"maintenance", "operations", "revenue"}),
        domains_with_resolved_trust=frozenset({"maintenance", "operations"}),
    )
    result = derive_legacy_activation("UNKNOWN-RULE-CODE", index)
    assert result.activated is False
