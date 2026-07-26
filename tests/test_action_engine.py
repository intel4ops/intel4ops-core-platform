from decimal import Decimal
from uuid import uuid4

import pytest

from app.engines.action_engine import (
    ActionEngineError,
    ActionStatus,
    PriorityInput,
    calculate_approval,
    calculate_priority,
    classify_feedback,
    dependencies_ready,
    idempotency_fingerprint,
    realized_value_eligible,
    require_transition,
    resources_ready,
)


@pytest.mark.parametrize(
    ("current", "requested"),
    [
        (ActionStatus.PROPOSED, ActionStatus.PENDING_APPROVAL),
        (ActionStatus.PROPOSED, ActionStatus.APPROVED),
        (ActionStatus.PENDING_APPROVAL, ActionStatus.APPROVED),
        (ActionStatus.APPROVED, ActionStatus.ASSIGNED),
        (ActionStatus.ASSIGNED, ActionStatus.SCHEDULED),
        (ActionStatus.SCHEDULED, ActionStatus.IN_PROGRESS),
        (ActionStatus.IN_PROGRESS, ActionStatus.BLOCKED),
        (ActionStatus.BLOCKED, ActionStatus.IN_PROGRESS),
        (ActionStatus.IN_PROGRESS, ActionStatus.COMPLETED),
        (ActionStatus.COMPLETED, ActionStatus.VERIFICATION_PENDING),
        (ActionStatus.VERIFICATION_PENDING, ActionStatus.VERIFIED),
        (ActionStatus.VERIFICATION_REJECTED, ActionStatus.IN_PROGRESS),
    ],
)
def test_allowed_transitions(current: ActionStatus, requested: ActionStatus) -> None:
    require_transition(current, requested)


@pytest.mark.parametrize(
    ("current", "requested"),
    [
        (ActionStatus.PROPOSED, ActionStatus.VERIFIED),
        (ActionStatus.REJECTED, ActionStatus.COMPLETED),
        (ActionStatus.COMPLETED, ActionStatus.APPROVED),
        (ActionStatus.COMPLETED, ActionStatus.VERIFIED),
        (ActionStatus.VERIFIED, ActionStatus.IN_PROGRESS),
    ],
)
def test_invalid_transitions_are_rejected(current: ActionStatus, requested: ActionStatus) -> None:
    with pytest.raises(ActionEngineError):
        require_transition(current, requested)


def test_priority_is_explainable_bounded_and_reports_missing_inputs() -> None:
    high = calculate_priority(
        PriorityInput(
            failure_probability=Decimal("0.82"),
            severity=5,
            horizon_days=18,
            confidence=Decimal("0.85"),
            financial_exposure=Decimal("125000"),
            resource_ready=True,
            dependencies_ready=True,
        )
    )
    assert Decimal("0") <= high.score <= Decimal("100")
    assert high.classification in {"high", "critical"}
    assert high.components["probability"] == "0.82"
    assert high.limitations == ()
    limited = calculate_priority(PriorityInput())
    assert "MISSING_FAILURE_PROBABILITY" in limited.limitations
    assert "MISSING_HORIZON" in limited.limitations


def test_approval_is_deterministic_and_conservative() -> None:
    result = calculate_approval(
        intervention_cost=Decimal("12000"),
        avoided_cost=Decimal("80000"),
        confidence=Decimal("0.5"),
        sensitive=True,
    )
    assert result.required
    assert result.role == "organization_admin"
    assert set(result.reasons) == {
        "HIGH_INTERVENTION_COST",
        "HIGH_EXPECTED_EXPOSURE",
        "LOW_CONFIDENCE",
        "SENSITIVE_OPERATIONAL_IMPACT",
    }


def test_readiness_value_and_feedback_rules() -> None:
    assert dependencies_ready([(True, True), (False, False)])
    assert not dependencies_ready([(True, False)])
    assert resources_ready([(True, True), (False, False)])
    assert not resources_ready([(True, False)])
    assert not realized_value_eligible(ActionStatus.COMPLETED, 1)
    assert not realized_value_eligible(ActionStatus.VERIFIED, 0)
    assert realized_value_eligible(ActionStatus.VERIFIED, 1)
    assert (
        classify_feedback(
            predicted_positive=True,
            failure_occurred=False,
            intervention_performed=True,
            observation_window_complete=True,
        )
        == "prevented_event"
    )
    assert (
        classify_feedback(
            predicted_positive=True,
            failure_occurred=False,
            intervention_performed=False,
            observation_window_complete=False,
        )
        == "insufficient_observation_window"
    )


def test_idempotency_fingerprint_is_stable_and_tenant_sensitive() -> None:
    organization_id, source_id = uuid4(), uuid4()
    first = idempotency_fingerprint(organization_id, "reliability", source_id, "inspection", "1.0")
    assert first == idempotency_fingerprint(
        organization_id, "reliability", source_id, "inspection", "1.0"
    )
    assert first != idempotency_fingerprint(uuid4(), "reliability", source_id, "inspection", "1.0")
