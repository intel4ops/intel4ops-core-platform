from dataclasses import dataclass
from decimal import Decimal

from app.engines.arithmetic_engine import ArithmeticEvaluationError, decimal_value
from app.registries.rule_registry import RuleDefinition, RuleOperator


@dataclass(frozen=True)
class RuleOutcome:
    breached: bool
    value: Decimal
    comparison_value: Decimal | None
    threshold_value: Decimal | None


class RuleEvaluator:
    def execute(self, definition: RuleDefinition, parameters: dict[str, object]) -> RuleOutcome:
        missing = [item for item in definition.required_parameters if item not in parameters]
        if missing:
            raise ArithmeticEvaluationError(
                f"Missing rule parameters: {', '.join(sorted(missing))}"
            )
        value = decimal_value(parameters["value"])
        operator = definition.operator
        comparison: Decimal | None = None
        threshold: Decimal | None = None
        if operator in {RuleOperator.BETWEEN, RuleOperator.OUTSIDE}:
            lower = decimal_value(parameters["lower"])
            upper = decimal_value(parameters["upper"])
            if lower > upper:
                raise ArithmeticEvaluationError("Lower bound must not exceed upper bound")
            breached = lower <= value <= upper
            if operator == RuleOperator.OUTSIDE:
                breached = not breached
        else:
            threshold = decimal_value(parameters["threshold"])
            comparison = threshold
            breached = {
                RuleOperator.EQUALS: value == threshold,
                RuleOperator.NOT_EQUALS: value != threshold,
                RuleOperator.GREATER_THAN: value > threshold,
                RuleOperator.GREATER_THAN_OR_EQUAL: value >= threshold,
                RuleOperator.LESS_THAN: value < threshold,
                RuleOperator.LESS_THAN_OR_EQUAL: value <= threshold,
            }[operator]
        return RuleOutcome(breached, value, comparison, threshold)
