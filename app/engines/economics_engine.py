from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

MONEY_QUANTUM = Decimal("0.000000000001")
SCORE_QUANTUM = Decimal("0.01")
CALCULATION_VERSION = "1.0"
PRIORITY_MODEL_NAME = "transparent_weighted_recovery_priority"
PRIORITY_MODEL_VERSION = "1.0"


class EconomicsError(ValueError):
    pass


class OpportunityStatus(StrEnum):
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    ECONOMICALLY_QUALIFIED = "economically_qualified"
    APPROVED_FOR_ACTION = "approved_for_action"
    DEFERRED = "deferred"
    MONITOR = "monitor"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"


class PriorityCategory(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    MONITOR = "monitor"
    NOT_ECONOMIC = "not_economic"
    BLOCKED = "blocked"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


ALLOWED_STATUS_TRANSITIONS: dict[OpportunityStatus, frozenset[OpportunityStatus]] = {
    OpportunityStatus.DRAFT: frozenset(
        {
            OpportunityStatus.UNDER_REVIEW,
            OpportunityStatus.DEFERRED,
            OpportunityStatus.MONITOR,
            OpportunityStatus.REJECTED,
            OpportunityStatus.CANCELLED,
        }
    ),
    OpportunityStatus.UNDER_REVIEW: frozenset(
        {
            OpportunityStatus.ECONOMICALLY_QUALIFIED,
            OpportunityStatus.DEFERRED,
            OpportunityStatus.MONITOR,
            OpportunityStatus.REJECTED,
            OpportunityStatus.CANCELLED,
        }
    ),
    OpportunityStatus.ECONOMICALLY_QUALIFIED: frozenset(
        {
            OpportunityStatus.APPROVED_FOR_ACTION,
            OpportunityStatus.DEFERRED,
            OpportunityStatus.MONITOR,
            OpportunityStatus.REJECTED,
            OpportunityStatus.SUPERSEDED,
        }
    ),
    OpportunityStatus.APPROVED_FOR_ACTION: frozenset(
        {
            OpportunityStatus.DEFERRED,
            OpportunityStatus.SUPERSEDED,
            OpportunityStatus.CANCELLED,
        }
    ),
    OpportunityStatus.DEFERRED: frozenset(
        {OpportunityStatus.UNDER_REVIEW, OpportunityStatus.REJECTED}
    ),
    OpportunityStatus.MONITOR: frozenset(
        {OpportunityStatus.UNDER_REVIEW, OpportunityStatus.REJECTED}
    ),
    OpportunityStatus.REJECTED: frozenset(),
    OpportunityStatus.SUPERSEDED: frozenset(),
    OpportunityStatus.CANCELLED: frozenset(),
}


@dataclass(frozen=True)
class EconomicInput:
    gross_exposure: Decimal
    addressability_rate: Decimal
    recoverability_rate: Decimal
    success_probability: Decimal
    recovery_cost: Decimal
    benefit_period_days: int | None = None


@dataclass(frozen=True)
class EconomicResult:
    gross_exposure: Decimal
    addressable_exposure: Decimal
    expected_recoverable_value: Decimal
    probability_adjusted_value: Decimal
    recovery_cost: Decimal
    expected_net_benefit: Decimal
    expected_roi: Decimal | None
    payback_period_days: Decimal | None
    zero_cost_policy: str
    calculation_version: str = CALCULATION_VERSION


@dataclass(frozen=True)
class PriorityInput:
    probability_adjusted_value: Decimal
    expected_net_benefit: Decimal
    expected_roi: Decimal | None
    payback_period_days: Decimal | None
    urgency_score: Decimal
    confidence_score: Decimal
    feasibility_score: Decimal
    strategic_alignment_score: Decimal
    risk_score: Decimal
    dependency_ready: bool = True
    resource_ready: bool = True


@dataclass(frozen=True)
class PriorityResult:
    score: Decimal
    category: PriorityCategory
    normalized_factors: dict[str, str]
    contributions: dict[str, str]
    weights: dict[str, str]
    limitations: tuple[str, ...]
    model_name: str = PRIORITY_MODEL_NAME
    model_version: str = PRIORITY_MODEL_VERSION


DEFAULT_WEIGHTS: dict[str, Decimal] = {
    "economic_value": Decimal("0.25"),
    "net_benefit": Decimal("0.15"),
    "roi": Decimal("0.10"),
    "payback": Decimal("0.10"),
    "urgency": Decimal("0.15"),
    "confidence": Decimal("0.10"),
    "feasibility": Decimal("0.05"),
    "strategic_alignment": Decimal("0.05"),
    "risk": Decimal("0.05"),
}

WEIGHTING_PROFILES: dict[str, dict[str, Decimal]] = {
    "default_enterprise": DEFAULT_WEIGHTS,
    "cash_recovery": {
        **DEFAULT_WEIGHTS,
        "economic_value": Decimal("0.30"),
        "net_benefit": Decimal("0.20"),
        "urgency": Decimal("0.10"),
        "strategic_alignment": Decimal("0.00"),
    },
    "safety_critical": {
        **DEFAULT_WEIGHTS,
        "economic_value": Decimal("0.15"),
        "net_benefit": Decimal("0.10"),
        "urgency": Decimal("0.25"),
        "risk": Decimal("0.15"),
    },
}


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _rate(name: str, value: Decimal) -> Decimal:
    if value < 0 or value > 1:
        raise EconomicsError(f"{name} must be between 0 and 1")
    return value


def calculate_economics(values: EconomicInput) -> EconomicResult:
    if values.gross_exposure < 0 or values.recovery_cost < 0:
        raise EconomicsError("Exposure and recovery cost cannot be negative")
    addressability = _rate("addressability_rate", values.addressability_rate)
    recoverability = _rate("recoverability_rate", values.recoverability_rate)
    success = _rate("success_probability", values.success_probability)
    addressable = _money(values.gross_exposure * addressability)
    recoverable = _money(addressable * recoverability)
    probability_adjusted = _money(recoverable * success)
    net = _money(probability_adjusted - values.recovery_cost)
    roi = None if values.recovery_cost == 0 else _money(net / values.recovery_cost)
    payback = None
    if (
        values.benefit_period_days is not None
        and values.benefit_period_days > 0
        and probability_adjusted > 0
    ):
        payback = _money(
            values.recovery_cost / (probability_adjusted / Decimal(values.benefit_period_days))
        )
    return EconomicResult(
        gross_exposure=_money(values.gross_exposure),
        addressable_exposure=addressable,
        expected_recoverable_value=recoverable,
        probability_adjusted_value=probability_adjusted,
        recovery_cost=_money(values.recovery_cost),
        expected_net_benefit=net,
        expected_roi=roi,
        payback_period_days=payback,
        zero_cost_policy="roi_not_applicable" if values.recovery_cost == 0 else "standard",
    )


def normalize_weights(weights: dict[str, Decimal]) -> dict[str, Decimal]:
    missing = set(DEFAULT_WEIGHTS) - set(weights)
    if missing:
        raise EconomicsError(f"Missing priority weights: {', '.join(sorted(missing))}")
    if any(value < 0 for value in weights.values()):
        raise EconomicsError("Priority weights cannot be negative")
    total = sum(weights.values(), Decimal("0"))
    if total == 0:
        raise EconomicsError("Priority weights cannot total zero")
    return {name: value / total for name, value in weights.items()}


def _bounded(value: Decimal) -> Decimal:
    return min(Decimal("1"), max(Decimal("0"), value))


def calculate_priority(
    values: PriorityInput, weights: dict[str, Decimal] | None = None
) -> PriorityResult:
    normalized_weights = normalize_weights(weights or DEFAULT_WEIGHTS)
    limitations: list[str] = []
    factors = {
        "economic_value": _bounded(values.probability_adjusted_value / Decimal("100000")),
        "net_benefit": _bounded(max(Decimal("0"), values.expected_net_benefit) / Decimal("100000")),
        "roi": _bounded((values.expected_roi or Decimal("0")) / Decimal("5")),
        "payback": (
            Decimal("0.5")
            if values.payback_period_days is None
            else _bounded(Decimal("1") - values.payback_period_days / Decimal("365"))
        ),
        "urgency": _rate("urgency_score", values.urgency_score),
        "confidence": _rate("confidence_score", values.confidence_score),
        "feasibility": _rate("feasibility_score", values.feasibility_score),
        "strategic_alignment": _rate("strategic_alignment_score", values.strategic_alignment_score),
        "risk": Decimal("1") - _rate("risk_score", values.risk_score),
    }
    if values.confidence_score < Decimal("0.4"):
        limitations.append("LOW_CONFIDENCE")
    if not values.dependency_ready:
        limitations.append("DEPENDENCIES_BLOCKED")
    if not values.resource_ready:
        limitations.append("RESOURCES_BLOCKED")
    contributions = {name: factors[name] * normalized_weights[name] for name in normalized_weights}
    score = (sum(contributions.values(), Decimal("0")) * Decimal("100")).quantize(
        SCORE_QUANTUM, rounding=ROUND_HALF_UP
    )
    if not values.dependency_ready or not values.resource_ready:
        category = PriorityCategory.BLOCKED
    elif values.confidence_score < Decimal("0.2"):
        category = PriorityCategory.INSUFFICIENT_EVIDENCE
    elif values.expected_net_benefit < 0:
        category = PriorityCategory.NOT_ECONOMIC
    elif score >= 80:
        category = PriorityCategory.CRITICAL
    elif score >= 65:
        category = PriorityCategory.HIGH
    elif score >= 45:
        category = PriorityCategory.MEDIUM
    elif score >= 25:
        category = PriorityCategory.LOW
    else:
        category = PriorityCategory.MONITOR
    return PriorityResult(
        score=score,
        category=category,
        normalized_factors={key: str(value) for key, value in factors.items()},
        contributions={key: str(value) for key, value in contributions.items()},
        weights={key: str(value) for key, value in normalized_weights.items()},
        limitations=tuple(limitations),
    )


def require_transition(current: OpportunityStatus, requested: OpportunityStatus) -> None:
    if requested not in ALLOWED_STATUS_TRANSITIONS[current]:
        raise EconomicsError(f"Invalid opportunity transition: {current} -> {requested}")


def portfolio_included_value(
    probability_adjusted_value: Decimal,
    allocation_percentage: Decimal,
    inclusion_status: str,
) -> Decimal:
    if inclusion_status != "included":
        return Decimal("0")
    _rate("allocation_percentage", allocation_percentage)
    return _money(probability_adjusted_value * allocation_percentage)
