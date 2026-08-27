from __future__ import annotations

from dataclasses import dataclass


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


class IntelligencePackRegistry:
    def __init__(self) -> None:
        self._packs: list[IntelligencePackDefinition] = []

    def register(self, pack: IntelligencePackDefinition) -> None:
        self._packs.append(pack)

    def all(self) -> list[IntelligencePackDefinition]:
        return list(self._packs)

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
        )
    )
    return registry
