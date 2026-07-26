from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class ActionEngineError(ValueError):
    pass


class ActionStatus(StrEnum):
    PROPOSED = "proposed"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    ASSIGNED = "assigned"
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    VERIFICATION_PENDING = "verification_pending"
    VERIFIED = "verified"
    VERIFICATION_REJECTED = "verification_rejected"
    CANCELLED = "cancelled"


ALLOWED_TRANSITIONS: dict[ActionStatus, frozenset[ActionStatus]] = {
    ActionStatus.PROPOSED: frozenset(
        {ActionStatus.PENDING_APPROVAL, ActionStatus.APPROVED, ActionStatus.CANCELLED}
    ),
    ActionStatus.PENDING_APPROVAL: frozenset(
        {ActionStatus.APPROVED, ActionStatus.REJECTED, ActionStatus.CANCELLED}
    ),
    ActionStatus.APPROVED: frozenset({ActionStatus.ASSIGNED, ActionStatus.CANCELLED}),
    ActionStatus.ASSIGNED: frozenset(
        {ActionStatus.SCHEDULED, ActionStatus.IN_PROGRESS, ActionStatus.CANCELLED}
    ),
    ActionStatus.SCHEDULED: frozenset({ActionStatus.IN_PROGRESS, ActionStatus.CANCELLED}),
    ActionStatus.IN_PROGRESS: frozenset(
        {ActionStatus.BLOCKED, ActionStatus.COMPLETED, ActionStatus.CANCELLED}
    ),
    ActionStatus.BLOCKED: frozenset({ActionStatus.IN_PROGRESS, ActionStatus.CANCELLED}),
    ActionStatus.COMPLETED: frozenset({ActionStatus.VERIFICATION_PENDING, ActionStatus.CANCELLED}),
    ActionStatus.VERIFICATION_PENDING: frozenset(
        {ActionStatus.VERIFIED, ActionStatus.VERIFICATION_REJECTED}
    ),
    ActionStatus.VERIFICATION_REJECTED: frozenset(
        {ActionStatus.IN_PROGRESS, ActionStatus.COMPLETED, ActionStatus.CANCELLED}
    ),
    ActionStatus.REJECTED: frozenset(),
    ActionStatus.VERIFIED: frozenset(),
    ActionStatus.CANCELLED: frozenset(),
}


def require_transition(current: ActionStatus, requested: ActionStatus) -> None:
    if requested not in ALLOWED_TRANSITIONS[current]:
        raise ActionEngineError(f"Transition {current.value} -> {requested.value} is not allowed")


@dataclass(frozen=True)
class PriorityInput:
    failure_probability: Decimal | None = None
    severity: int = 1
    horizon_days: int | None = None
    confidence: Decimal | None = None
    financial_exposure: Decimal | None = None
    resource_ready: bool = False
    dependencies_ready: bool = False


@dataclass(frozen=True)
class PriorityResult:
    score: Decimal
    classification: str
    components: dict[str, str]
    reason_codes: tuple[str, ...]
    limitations: tuple[str, ...]


def calculate_priority(value: PriorityInput) -> PriorityResult:
    probability = value.failure_probability or Decimal("0")
    confidence = value.confidence or Decimal("0")
    urgency = (
        Decimal("1")
        if value.horizon_days is not None and value.horizon_days <= 7
        else Decimal("0.6")
        if value.horizon_days is not None and value.horizon_days <= 30
        else Decimal("0.2")
    )
    exposure = min(Decimal("1"), (value.financial_exposure or Decimal("0")) / Decimal("100000"))
    readiness = (
        Decimal("1") if value.resource_ready and value.dependencies_ready else Decimal("0.4")
    )
    score = (
        probability * Decimal("35")
        + Decimal(value.severity) / Decimal("5") * Decimal("25")
        + urgency * Decimal("15")
        + confidence * Decimal("10")
        + exposure * Decimal("10")
        + readiness * Decimal("5")
    ).quantize(Decimal("0.01"))
    classification = (
        "critical" if score >= 80 else "high" if score >= 60 else "medium" if score >= 35 else "low"
    )
    missing = tuple(
        name
        for name, item in (
            ("MISSING_FAILURE_PROBABILITY", value.failure_probability),
            ("MISSING_HORIZON", value.horizon_days),
            ("MISSING_CONFIDENCE", value.confidence),
            ("MISSING_FINANCIAL_EXPOSURE", value.financial_exposure),
        )
        if item is None
    )
    return PriorityResult(
        score=score,
        classification=classification,
        components={
            "probability": str(probability),
            "severity": str(value.severity),
            "urgency": str(urgency),
            "confidence": str(confidence),
            "exposure": str(exposure),
            "readiness": str(readiness),
        },
        reason_codes=("BOUNDED_WEIGHTED_PRIORITY",),
        limitations=missing,
    )


@dataclass(frozen=True)
class ApprovalResult:
    required: bool
    level: str
    role: str
    reasons: tuple[str, ...]


def calculate_approval(
    *, intervention_cost: Decimal, avoided_cost: Decimal, confidence: Decimal, sensitive: bool
) -> ApprovalResult:
    reasons: list[str] = []
    if intervention_cost >= Decimal("10000"):
        reasons.append("HIGH_INTERVENTION_COST")
    if avoided_cost >= Decimal("50000"):
        reasons.append("HIGH_EXPECTED_EXPOSURE")
    if confidence < Decimal("0.6"):
        reasons.append("LOW_CONFIDENCE")
    if sensitive:
        reasons.append("SENSITIVE_OPERATIONAL_IMPACT")
    required = bool(reasons)
    return ApprovalResult(
        required=required,
        level="organization_admin" if required else "none",
        role="organization_admin" if required else "operator",
        reasons=tuple(reasons),
    )


def idempotency_fingerprint(
    organization_id: object,
    source_type: str,
    source_id: object,
    recommendation_type: str,
    rule_version: str,
) -> str:
    value = {
        "organization_id": str(organization_id),
        "source_type": source_type,
        "source_id": str(source_id),
        "recommendation_type": recommendation_type,
        "rule_version": rule_version,
    }
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def dependencies_ready(items: list[tuple[bool, bool]]) -> bool:
    return all(resolved or not mandatory for mandatory, resolved in items)


def resources_ready(items: list[tuple[bool, bool]]) -> bool:
    return all(available or not mandatory for mandatory, available in items)


def realized_value_eligible(status: ActionStatus, verified_evidence_count: int) -> bool:
    return status == ActionStatus.VERIFIED and verified_evidence_count > 0


def classify_feedback(
    *,
    predicted_positive: bool,
    failure_occurred: bool,
    intervention_performed: bool,
    observation_window_complete: bool,
) -> str:
    if not observation_window_complete:
        return "insufficient_observation_window"
    if predicted_positive and intervention_performed and not failure_occurred:
        return "prevented_event"
    if predicted_positive:
        return "true_positive" if failure_occurred else "false_positive"
    return "false_negative" if failure_occurred else "true_negative"
