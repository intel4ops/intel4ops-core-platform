"""AGENTIC-CONTROL-001 Phase D/P: routing policy tests -- R0/R1 route to
Qwen profiles, confidence-based escalation follows the mission's exact
thresholds, and R2/R3 always require Claude review + an owner gate,
never automatic acceptance regardless of confidence."""

from app.models.agent_jobs import AgentWorkerProfile
from app.services.agent_routing_service import agent_routing_policy


def test_r0_routes_to_qwen_r0_profile_local_allowed() -> None:
    decision = agent_routing_policy.route("R0")
    assert decision.worker_profile == AgentWorkerProfile.QWEN_R0
    assert decision.local_allowed is True
    assert decision.owner_gate_required is False


def test_r1_routes_to_qwen_r1_profile_local_allowed() -> None:
    decision = agent_routing_policy.route("R1")
    assert decision.worker_profile == AgentWorkerProfile.QWEN_R1
    assert decision.local_allowed is True
    assert decision.owner_gate_required is False


def test_r2_requires_claude_review_and_owner_gate_not_local() -> None:
    decision = agent_routing_policy.route("R2")
    assert decision.worker_profile == AgentWorkerProfile.CLAUDE_PLATFORM_REVIEW
    assert decision.local_allowed is False
    assert decision.owner_gate_required is True


def test_r3_requires_claude_review_and_owner_gate_not_local() -> None:
    decision = agent_routing_policy.route("R3")
    assert decision.worker_profile == AgentWorkerProfile.CLAUDE_PLATFORM_REVIEW
    assert decision.local_allowed is False
    assert decision.owner_gate_required is True


def test_safety_flag_forces_r3_even_when_r0_was_requested() -> None:
    decision = agent_routing_policy.route("R0", safety_flags=frozenset({"truth_isolation_risk"}))
    assert decision.risk_class == "R3"
    assert decision.owner_gate_required is True


def test_r0_high_confidence_is_accepted() -> None:
    decision = agent_routing_policy.evaluate_worker_result("R0", confidence=95)
    assert decision.accept is True
    assert decision.escalate is False


def test_r0_low_confidence_escalates_to_r1_profile() -> None:
    decision = agent_routing_policy.evaluate_worker_result("R0", confidence=80)
    assert decision.accept is False
    assert decision.escalate is True
    assert decision.next_profile == AgentWorkerProfile.QWEN_R1
    assert decision.owner_gate_required is False


def test_r1_high_confidence_no_flags_is_accepted() -> None:
    decision = agent_routing_policy.evaluate_worker_result("R1", confidence=92)
    assert decision.accept is True


def test_r1_mid_confidence_escalates_to_devstral_review() -> None:
    decision = agent_routing_policy.evaluate_worker_result("R1", confidence=80)
    assert decision.accept is False
    assert decision.next_profile == AgentWorkerProfile.DEVSTRAL_SPECIALIST
    assert decision.owner_gate_required is False


def test_r1_architecture_flag_escalates_even_at_high_confidence() -> None:
    decision = agent_routing_policy.evaluate_worker_result(
        "R1", confidence=95, architecture_impact=True
    )
    assert decision.accept is False
    assert decision.next_profile == AgentWorkerProfile.DEVSTRAL_SPECIALIST


def test_r1_low_confidence_escalates_to_claude_with_owner_gate() -> None:
    decision = agent_routing_policy.evaluate_worker_result("R1", confidence=50)
    assert decision.accept is False
    assert decision.next_profile == AgentWorkerProfile.CLAUDE_PLATFORM_REVIEW
    assert decision.owner_gate_required is True


def test_r2_never_auto_accepted_even_at_max_confidence() -> None:
    decision = agent_routing_policy.evaluate_worker_result("R2", confidence=100)
    assert decision.accept is False
    assert decision.owner_gate_required is True


def test_r3_never_auto_accepted_even_at_max_confidence() -> None:
    decision = agent_routing_policy.evaluate_worker_result("R3", confidence=100)
    assert decision.accept is False
    assert decision.owner_gate_required is True


def test_model_parameters_match_frozen_profiles() -> None:
    r0_params = agent_routing_policy.model_parameters(AgentWorkerProfile.QWEN_R0)
    assert r0_params == {
        "model": "qwen/qwen3.5-9b",
        "reasoning": False,
        "max_output_tokens": 180,
        "temperature": 0,
    }
    r1_params = agent_routing_policy.model_parameters(AgentWorkerProfile.QWEN_R1)
    assert r1_params["max_output_tokens"] == 500
    assert r1_params["reasoning"] is False
