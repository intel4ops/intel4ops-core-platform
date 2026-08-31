from __future__ import annotations

from dataclasses import dataclass

from app.intelligence_packs.case_capability_index import CaseCapabilityIndex
from app.intelligence_packs.registry import IntelligencePackDefinition
from app.services.intelligence_readiness_service import (
    IntelligenceReadinessResult,
    evaluate_readiness,
)

# ---------------------------------------------------------------------------
# P3.xxE.5 Phase 1 (SHADOW): compares the pre-existing, hard-coded
# cross_domain_intelligence stage's own activation condition against the
# new generic registry/readiness evaluator, WITHOUT changing what actually
# runs. derive_legacy_activation() is deliberately rule-code-specific --
# it exists only to faithfully re-derive what the OLD, already-hard-coded
# orchestration logic does today, which is inherently per-rule by
# definition. This is NOT the generic evaluator (evaluate_readiness in
# intelligence_readiness_service.py) that must stay model-code-agnostic --
# see tests/test_capability_architecture_guardrails.py for the AST-level
# guardrail that enforces that distinction.
# ---------------------------------------------------------------------------

_XDOM_A_RULE_CODE = "XDOM-A-ASSET-FAILURE-LOST-ACTIVITY"
_XDOM_B_RULE_CODE = "XDOM-B-LOST-ACTIVITY-REVENUE-GAP"


@dataclass(frozen=True)
class LegacyActivationResult:
    activated: bool
    reason: str


@dataclass(frozen=True)
class ShadowComparisonResult:
    pack: IntelligencePackDefinition
    legacy: LegacyActivationResult
    governed: IntelligenceReadinessResult
    agree: bool
    evidence_summary: list[str]


def derive_legacy_activation(rule_code: str, index: CaseCapabilityIndex) -> LegacyActivationResult:
    """Faithfully re-derives the EXACT condition
    analysis_case_orchestration_service.py's existing cross_domain_intelligence
    stage already uses today to decide whether to call
    run_asset_failure_to_lost_activity / run_lost_activity_to_revenue_gap:
    both required domains present in by_domain, and at least one dataset
    of the anchor domain has a resolved trust_assessment_id. Does not
    read, call, or modify that stage -- this is a read-only re-derivation
    against the same CaseCapabilityIndex signals, computed independently."""
    if rule_code == _XDOM_A_RULE_CODE:
        required_domains = {"maintenance", "operations"}
        trust_domain = "maintenance"
    elif rule_code == _XDOM_B_RULE_CODE:
        required_domains = {"operations", "revenue"}
        trust_domain = "operations"
    else:
        return LegacyActivationResult(
            activated=False,
            reason=f"no legacy re-derivation defined for rule_code {rule_code!r}",
        )

    missing = required_domains - index.available_domains
    if missing:
        return LegacyActivationResult(
            activated=False, reason=f"missing domain(s): {', '.join(sorted(missing))}"
        )
    if trust_domain not in index.domains_with_resolved_trust:
        return LegacyActivationResult(
            activated=False,
            reason=f"no resolved trust assessment for domain {trust_domain!r}",
        )
    return LegacyActivationResult(
        activated=True, reason="required domain(s) present and trust resolved"
    )


def compare_shadow(
    pack: IntelligencePackDefinition, index: CaseCapabilityIndex
) -> ShadowComparisonResult:
    legacy = derive_legacy_activation(pack.rule_code, index)
    governed = evaluate_readiness(pack, index)
    agree = legacy.activated == (governed.status == "READY")
    evidence_summary = [
        f"legacy: activated={legacy.activated} ({legacy.reason})",
        f"governed: status={governed.status} ({governed.reason})",
        f"agree={agree}",
    ]
    return ShadowComparisonResult(
        pack=pack,
        legacy=legacy,
        governed=governed,
        agree=agree,
        evidence_summary=evidence_summary,
    )
