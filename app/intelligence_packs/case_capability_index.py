from __future__ import annotations

from dataclasses import dataclass, field

from app.intelligence_packs.confidence_distribution import ConfidenceDistribution

# ---------------------------------------------------------------------------
# P3.xxE.5: the run-scoped, tenant-scoped snapshot of everything a pack's
# declared requirements can be checked against. Built ONCE per run by the
# caller (app/services/case_capability_index_service.py, the one file that
# necessarily touches the database) from data already resolved by E.1-E.4:
# legacy domain/field/entity-link signals (compatibility with the existing
# 4-field applicable()/evaluate_readiness() check) plus E.3's
# CanonicalCaseEntity/CanonicalCaseRelationship and E.4's
# CanonicalProcessActivity/CanonicalProcessEdge tables for this run_id.
#
# Framework-free by construction (no SQLAlchemy import here) -- mirrors
# app/entities/case_entity_context.py's own convention: the DATA object is
# pure, only the builder touches a Session.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MeasureCapability:
    """Plan review correction 5: enough shape to support safe future
    readiness evaluation without building a full measure subsystem --
    presence, coverage, currency/unit shape, and confidence where
    available for one canonical measure concept observed in this run."""

    measure_code: str
    count: int = 0
    coverage: float = 0.0  # fraction of the relevant record population carrying a non-null value
    currencies_observed: frozenset[str] = field(default_factory=frozenset)
    units_observed: frozenset[str] = field(default_factory=frozenset)
    confidence: ConfidenceDistribution = field(default_factory=ConfidenceDistribution)


@dataclass(frozen=True)
class CaseCapabilityIndex:
    organization_id: str
    analysis_case_id: str
    run_id: str

    # --- legacy compatibility signals (inputs to the pre-existing 4-field check) ---
    available_domains: frozenset[str] = field(default_factory=frozenset)
    available_canonical_fields: frozenset[str] = field(default_factory=frozenset)
    resolved_entity_types: frozenset[str] = field(default_factory=frozenset)
    currency_unresolved: bool = False
    # domains where >=1 case_dataset has a resolved trust_assessment_id --
    # the exact signal the pre-existing cross_domain_intelligence stage
    # already gates on today (see shadow_comparison.py's re-derivation).
    domains_with_resolved_trust: frozenset[str] = field(default_factory=frozenset)

    # --- E.3 canonical-layer signals (CanonicalCaseEntity / CanonicalCaseRelationship) ---
    canonical_entity_types_present: frozenset[str] = field(default_factory=frozenset)
    canonical_entity_identity_confidence_by_type: dict[str, ConfidenceDistribution] = field(
        default_factory=dict
    )
    canonical_relationship_types_present: frozenset[str] = field(default_factory=frozenset)
    canonical_relationship_confidence_by_type: dict[str, ConfidenceDistribution] = field(
        default_factory=dict
    )

    # --- E.4 canonical-layer signals (CanonicalProcessActivity / CanonicalProcessEdge) ---
    activity_types_present: frozenset[str] = field(default_factory=frozenset)
    activity_type_confidence_by_type: dict[str, ConfidenceDistribution] = field(
        default_factory=dict
    )
    precedes_pairs_present: frozenset[tuple[str, str]] = field(default_factory=frozenset)
    precedes_pair_confidence: dict[tuple[str, str], ConfidenceDistribution] = field(
        default_factory=dict
    )
    named_states_present: frozenset[str] = field(default_factory=frozenset)
    state_meaning_confidence_by_state: dict[str, ConfidenceDistribution] = field(
        default_factory=dict
    )
    process_confidence_by_anchor_type: dict[str, ConfidenceDistribution] = field(
        default_factory=dict
    )

    # --- canonical measures (deliberately minimal -- correction 5) ---
    canonical_measures: dict[str, MeasureCapability] = field(default_factory=dict)

    # --- currency/unit safety signals ---
    distinct_currencies_observed: frozenset[str] = field(default_factory=frozenset)
    distinct_units_observed_by_measure: dict[str, frozenset[str]] = field(default_factory=dict)
