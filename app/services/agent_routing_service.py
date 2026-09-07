"""AGENTIC-CONTROL-001 Phase D: the Agent Router.

Routing is policy-driven and centralized here -- never hard-coded at
each call site. Two decision points:

1. `route(risk_class, ...)` -- called at job creation, decides the
   initial worker profile, whether local processing is allowed, and
   whether an owner gate is required before any work happens at all
   (R2/R3).
2. `evaluate_worker_result(risk_class, confidence, safety_flags)` --
   called after a worker returns a structured result, decides whether to
   accept it or escalate, per the mission's explicit confidence
   thresholds.

Nothing here calls a model provider directly -- this module only ever
returns a *decision*. Actually dispatching to a provider (LM Studio for
local profiles, an external API for premium profiles) is
`app.services.agent_job_service`'s job for local profiles, and remains a
manual/human-invoked step for premium profiles in this v1 (see
docs/agentic-control-architecture.md's "v1 boundary" section) -- R2/R3
explicitly forbid automatic implementation regardless.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.agent_jobs import AgentJobRiskClass, AgentWorkerProfile

# Fast-worker fixed profiles (mission: "Store profile names/version, not
# random parameters on every call"). LM Studio model identifiers and
# inference parameters are frozen here, not scattered through call sites.
QWEN_MODEL_IDENTIFIER = "qwen/qwen3.5-9b"
DEVSTRAL_MODEL_IDENTIFIER = "mistralai/devstral-small-2-2512"

MODEL_PROFILE_PARAMETERS: dict[str, dict[str, object]] = {
    AgentWorkerProfile.QWEN_R0.value: {
        "model": QWEN_MODEL_IDENTIFIER,
        "reasoning": False,
        "max_output_tokens": 180,
        "temperature": 0,
    },
    AgentWorkerProfile.QWEN_R1.value: {
        "model": QWEN_MODEL_IDENTIFIER,
        "reasoning": False,
        "max_output_tokens": 500,
        "temperature": 0,
    },
    AgentWorkerProfile.DEVSTRAL_SPECIALIST.value: {
        "model": DEVSTRAL_MODEL_IDENTIFIER,
        "reasoning": True,
        "max_output_tokens": 2000,
        "temperature": 0,
    },
    # Premium profiles carry no LM Studio parameters -- they are not
    # locally dispatchable (see RoutingRule.local_allowed below).
    AgentWorkerProfile.GEMINI_SYNTHESIS.value: {},
    AgentWorkerProfile.CLAUDE_PLATFORM_REVIEW.value: {},
    AgentWorkerProfile.CODEX_IMPLEMENTATION.value: {},
}


@dataclass(frozen=True)
class RoutingRule:
    default_profile: AgentWorkerProfile
    local_allowed: bool
    owner_gate_required: bool


@dataclass(frozen=True)
class RoutingDecision:
    risk_class: str
    worker_profile: AgentWorkerProfile
    local_allowed: bool
    premium_escalation_required: bool
    owner_gate_required: bool
    reasoning: str


@dataclass(frozen=True)
class EscalationDecision:
    accept: bool
    escalate: bool
    next_profile: AgentWorkerProfile | None
    owner_gate_required: bool
    reason: str


class AgentRoutingPolicy:
    """The single source of routing truth (mission Phase D: "Routing
    must be policy-driven, not hard-coded throughout the codebase.")."""

    _RULES: dict[str, RoutingRule] = {
        AgentJobRiskClass.R0.value: RoutingRule(
            default_profile=AgentWorkerProfile.QWEN_R0,
            local_allowed=True,
            owner_gate_required=False,
        ),
        AgentJobRiskClass.R1.value: RoutingRule(
            default_profile=AgentWorkerProfile.QWEN_R1,
            local_allowed=True,
            owner_gate_required=False,
        ),
        AgentJobRiskClass.R2.value: RoutingRule(
            default_profile=AgentWorkerProfile.CLAUDE_PLATFORM_REVIEW,
            local_allowed=False,
            owner_gate_required=True,
        ),
        AgentJobRiskClass.R3.value: RoutingRule(
            default_profile=AgentWorkerProfile.CLAUDE_PLATFORM_REVIEW,
            local_allowed=False,
            owner_gate_required=True,
        ),
    }

    # Mandatory R3 triggers -- any one present forces R3 regardless of the
    # risk_class a caller requested (mission: "Mandatory Claude + owner
    # gate if any: predicted FP explosion, ground-truth isolation risk,
    # evidence-gate weakening, arbitrary policy proposal, canonical
    # architecture conflict, cross-currency unsafe aggregation, destructive
    # data/model migration, security/authentication boundary change").
    R3_SAFETY_FLAGS = frozenset(
        {
            "fp_explosion_risk",
            "truth_isolation_risk",
            "evidence_gate_weakening",
            "arbitrary_policy_proposal",
            "canonical_architecture_conflict",
            "cross_currency_unsafe_aggregation",
            "destructive_migration",
            "security_boundary_change",
        }
    )

    def classify_risk(
        self, requested_risk_class: str, safety_flags: frozenset[str] = frozenset()
    ) -> str:
        if safety_flags & self.R3_SAFETY_FLAGS:
            return AgentJobRiskClass.R3.value
        return requested_risk_class

    def route(
        self,
        requested_risk_class: str,
        safety_flags: frozenset[str] = frozenset(),
    ) -> RoutingDecision:
        risk_class = self.classify_risk(requested_risk_class, safety_flags)
        rule = self._RULES.get(risk_class)
        if rule is None:
            raise ValueError(f"unknown risk class: {risk_class!r}")
        reasoning = f"risk_class={risk_class}"
        if risk_class != requested_risk_class:
            reasoning += (
                f" (escalated from requested {requested_risk_class} due to safety flags: "
                f"{sorted(safety_flags & self.R3_SAFETY_FLAGS)})"
            )
        return RoutingDecision(
            risk_class=risk_class,
            worker_profile=rule.default_profile,
            local_allowed=rule.local_allowed,
            premium_escalation_required=not rule.local_allowed,
            owner_gate_required=rule.owner_gate_required,
            reasoning=reasoning,
        )

    def evaluate_worker_result(
        self,
        risk_class: str,
        confidence: int,
        architecture_impact: bool = False,
        policy_dependency: bool = False,
        worker_requested_escalation: bool = False,
    ) -> EscalationDecision:
        """Applies the mission's exact confidence thresholds per risk
        class. Called after a worker (local or premium) returns a
        structured result."""
        has_safety_flag = architecture_impact or policy_dependency

        if risk_class == AgentJobRiskClass.R0.value:
            if worker_requested_escalation or confidence < 90:
                return EscalationDecision(
                    accept=False,
                    escalate=True,
                    next_profile=AgentWorkerProfile.QWEN_R1,
                    owner_gate_required=False,
                    reason=f"R0 confidence {confidence} < 90 (or worker requested escalation)",
                )
            return EscalationDecision(
                accept=True,
                escalate=False,
                next_profile=None,
                owner_gate_required=False,
                reason="R0 accepted",
            )

        if risk_class == AgentJobRiskClass.R1.value:
            if worker_requested_escalation or confidence < 70:
                return EscalationDecision(
                    accept=False,
                    escalate=True,
                    next_profile=AgentWorkerProfile.CLAUDE_PLATFORM_REVIEW,
                    owner_gate_required=True,
                    reason=f"R1 confidence {confidence} < 70 -- Claude escalation required",
                )
            if confidence < 90 or has_safety_flag:
                return EscalationDecision(
                    accept=False,
                    escalate=True,
                    next_profile=AgentWorkerProfile.DEVSTRAL_SPECIALIST,
                    owner_gate_required=False,
                    reason=(
                        f"R1 confidence {confidence} in [70,90) or an architecture/policy flag "
                        "was set -- Devstral/Gemini review required"
                    ),
                )
            return EscalationDecision(
                accept=True,
                escalate=False,
                next_profile=None,
                owner_gate_required=False,
                reason="R1 accepted",
            )

        # R2/R3: never auto-accepted regardless of confidence -- the
        # worker's result is evidence *for* the mandatory Claude+owner
        # review, never a substitute for it.
        return EscalationDecision(
            accept=False,
            escalate=True,
            next_profile=AgentWorkerProfile.CLAUDE_PLATFORM_REVIEW,
            owner_gate_required=True,
            reason=(
                f"{risk_class} always requires Claude review and owner approval -- "
                "no automatic acceptance"
            ),
        )

    def model_parameters(self, profile: AgentWorkerProfile) -> dict[str, object]:
        return dict(MODEL_PROFILE_PARAMETERS[profile.value])


agent_routing_policy = AgentRoutingPolicy()
