from __future__ import annotations

from dataclasses import dataclass

from app.entities.entity_type import EntityType


@dataclass(frozen=True)
class IntelligencePackDefinition:
    """Metadata declared by every P3.xxC.1 domain/cross-domain rule.
    Modeled on this codebase's existing EngineRegistry/TrustRuleRegistry
    pattern -- the orchestrator asks the registry what's applicable given
    what's actually present in a case, never hardcoding "if maintenance
    then MAINT-001". Actual detection/publication logic lives in dedicated
    service functions (analysis_case_intelligence_service.py,
    cross_domain_intelligence_service.py), not a generic callback here --
    with only 3 rules this pass, a callback-based execution abstraction
    would add indirection without real benefit; the registry's job is
    readiness/applicability, not execution."""

    pack_code: str
    rule_code: str
    version: str
    required_domains: frozenset[str]
    required_canonical_fields: frozenset[str]
    required_entities: frozenset[str]
    supported_industry_contexts: frozenset[str] | None  # None = industry-agnostic
    currency_required: bool
    output_domains: frozenset[str]

    # P3.xxE.5: additive fields extending readiness onto E.3/E.4's canonical
    # layer -- all defaulted so MAINT-001/XDOM-A/XDOM-B's pre-existing
    # registrations above need no changes unless they opt into a new check.
    # "model/rule version" is deliberately NOT duplicated here -- the
    # existing `version` field above already is that; activation_policy_version
    # below versions the READINESS-EVALUATION POLICY itself, a distinct
    # concept, mirroring app/entities/*_policy_version /
    # app/process/*_policy_version's own convention.
    required_canonical_entities: frozenset[str] = (
        frozenset()
    )  # app.entities.entity_type.EntityType values
    required_relationships: frozenset[str] = (
        frozenset()
    )  # app.entities.relationship_type.RelationshipType values
    required_activities: frozenset[str] = (
        frozenset()
    )  # app.process.activity_type.ActivityType values
    required_activity_sequences: frozenset[tuple[str, str]] = (
        frozenset()
    )  # (from_type, to_type) PRECEDES pairs
    required_states: frozenset[str] = (
        frozenset()
    )  # canonical state names (app.process.state_normalization)
    required_canonical_measures: frozenset[str] = (
        frozenset()
    )  # concept codes for quantity/monetary_amount fields

    # P3.xxE.5 corrected shadow certification: domains whose Trust
    # assessment must be RESOLVED (not merely present -- see
    # CaseCapabilityIndex.domains_with_resolved_trust) before this pack can
    # ever reach READY. Generic and rule-code-agnostic by construction: the
    # evaluator only ever compares this set against
    # index.domains_with_resolved_trust, exactly like every other
    # required_*/available_* pair above -- see
    # tests/test_capability_architecture_guardrails.py for the AST-level
    # guardrail against any pack_code/rule_code branch reading this field.
    required_resolved_trust_domains: frozenset[str] = frozenset()

    minimum_entity_identity_confidence: float = 0.0
    minimum_relationship_confidence: float = 0.0
    minimum_activity_confidence: float = 0.0
    minimum_process_confidence: float = 0.0

    # Plan review correction 2: HOW a ConfidenceDistribution is reduced
    # against a declared minimum before deciding PARTIAL vs not.
    # "coverage_above_threshold" (the safe default) means: at least
    # minimum_coverage_ratio of the matching population must individually
    # clear the relevant minimum_*_confidence -- one high-confidence
    # outlier can never carry a low-confidence population to READY.
    confidence_aggregation_policy: str = "coverage_above_threshold"  # | "min" | "median" | "max"
    minimum_coverage_ratio: float = 1.0

    # Plan review correction 6 / spec: mirrors calculation_registry.py's own
    # already-established house convention (single ISO currency per
    # execution, no FX, mixed/missing required currency blocks) rather than
    # inventing new vocabulary.
    currency_behavior: str = (
        "single_currency_only"  # | "multi_currency_aware" | "currency_agnostic"
    )
    unit_behavior: str = "unit_agnostic"  # | "single_unit_only" | "unit_aware"

    evidence_requirements: frozenset[str] = frozenset()
    activation_policy_version: str = "v1"
    is_disabled: bool = False


class IntelligencePackRegistry:
    def __init__(self) -> None:
        self._packs: list[IntelligencePackDefinition] = []

    def register(self, pack: IntelligencePackDefinition) -> None:
        self._packs.append(pack)

    def all(self) -> list[IntelligencePackDefinition]:
        return list(self._packs)

    def get(self, rule_code: str) -> IntelligencePackDefinition | None:
        return next((p for p in self._packs if p.rule_code == rule_code), None)

    def applicable(
        self, available_domains: set[str], available_fields: set[str], industry_code: str | None
    ) -> list[IntelligencePackDefinition]:
        result = []
        for pack in self._packs:
            if not pack.required_domains <= available_domains:
                continue
            if not pack.required_canonical_fields <= available_fields:
                continue
            if pack.supported_industry_contexts is not None and industry_code is not None:
                if industry_code not in pack.supported_industry_contexts:
                    continue
            result.append(pack)
        return result


def default_intelligence_pack_registry() -> IntelligencePackRegistry:
    registry = IntelligencePackRegistry()
    registry.register(
        IntelligencePackDefinition(
            pack_code="MAINT",
            rule_code="MAINT-001-REPEATED-FAILURE",
            version="1.0",
            required_domains=frozenset({"maintenance"}),
            required_canonical_fields=frozenset(
                {"asset_id", "failure_code", "downtime_hours", "repair_cost"}
            ),
            required_entities=frozenset({"asset"}),
            supported_industry_contexts=None,
            currency_required=False,
            output_domains=frozenset({"maintenance"}),
        )
    )
    registry.register(
        IntelligencePackDefinition(
            pack_code="XDOM",
            rule_code="XDOM-A-ASSET-FAILURE-LOST-ACTIVITY",
            version="1.0",
            required_domains=frozenset({"maintenance", "operations"}),
            required_canonical_fields=frozenset(
                {"asset_id", "downtime_hours", "operational_event_id"}
            ),
            required_entities=frozenset({"asset", "operational_event"}),
            supported_industry_contexts=None,
            currency_required=False,
            output_domains=frozenset({"maintenance", "operations"}),
            # P3.xxE.5: ASSET is backed by a real semantic concept
            # (app/entities/entity_type.py) so E.3 entity resolution can
            # actually produce it -- a real, checkable enrichment of this
            # already-registered rule's requirements, not a new rule.
            # "operational_event" has NO canonical-entity-type analog
            # (EntityType.EVENT has no backing concept registered yet, per
            # entity_type.py's own documented gap) -- deliberately left out
            # of required_canonical_entities rather than mapped to a type
            # that could never actually be produced.
            required_canonical_entities=frozenset({EntityType.ASSET.value}),
            minimum_entity_identity_confidence=0.70,
            # P3.xxV.2H (Fix #5): XDOM-A is a PER_ENTITY / candidate-local
            # model, confirmed directly from run_asset_failure_to_lost_activity's
            # own implementation -- it iterates a pre-filtered, per-asset
            # candidate set and publishes one finding per independently
            # qualifying asset (app/services/cross_domain_intelligence_service.py).
            # "coverage_above_threshold" @ ratio=1.0 (the E.5-era generic
            # default, never reasoned about per-model -- see
            # docs/p3xxv2g-entity-population-coverage-diagnosis-report.md,
            # Section B) required the ENTIRE case-global ASSET population to
            # individually clear the confidence floor, incorrectly blocking
            # this rule on unrelated single-dataset tail entities it would
            # never evaluate as candidates anyway. "max" is an existing,
            # already-generic evaluator option (app/services/
            # intelligence_readiness_service.py's own _meets_confidence) --
            # unchanged here, only selected: it answers exactly the question
            # a candidate-local model needs, "does at least one eligible
            # entity exist," never "does every entity in the case clear the
            # bar." minimum_coverage_ratio is therefore left at its class
            # default (unused by the "max" policy).
            confidence_aggregation_policy="max",
            # Rule A compares downtime-hour windows only -- never sums or
            # compares a monetary amount across records.
            currency_behavior="currency_agnostic",
            unit_behavior="unit_agnostic",
            # P3.xxE.5 corrected shadow certification: the pre-existing
            # cross_domain_intelligence stage's own activation condition
            # for this rule requires a resolved Trust assessment for its
            # anchor domain, 'maintenance' -- verified directly against
            # shadow_comparison.py's derive_legacy_activation() re-derivation.
            required_resolved_trust_domains=frozenset({"maintenance"}),
        )
    )
    registry.register(
        IntelligencePackDefinition(
            pack_code="XDOM",
            rule_code="XDOM-B-LOST-ACTIVITY-REVENUE-GAP",
            version="1.0",
            required_domains=frozenset({"operations", "revenue"}),
            required_canonical_fields=frozenset(
                {"operational_event_id", "operational_event_status", "transaction_amount"}
            ),
            required_entities=frozenset({"operational_event"}),
            supported_industry_contexts=None,
            currency_required=False,
            output_domains=frozenset({"operations", "revenue"}),
            # P3.xxE.5: no required_canonical_entities set -- "operational_event"
            # has no EntityType analog reachable by E.3 today (see XDOM-A's
            # comment above). Rule B only checks whether a matching revenue
            # RECORD exists, never sums transaction_amount across records,
            # so it is currency-agnostic despite transaction_amount being a
            # required canonical field.
            currency_behavior="currency_agnostic",
            unit_behavior="unit_agnostic",
            # P3.xxE.5 corrected shadow certification: the pre-existing
            # cross_domain_intelligence stage's own activation condition
            # for this rule requires a resolved Trust assessment for its
            # anchor domain, 'operations' -- verified directly against
            # shadow_comparison.py's derive_legacy_activation() re-derivation
            # (this is exactly the disagreement the first shadow run found:
            # XDOM-B reached governed READY on FIELDMAINT-004/005 despite
            # legacy withholding activation for unresolved 'operations'
            # Trust).
            required_resolved_trust_domains=frozenset({"operations"}),
        )
    )
    return registry
