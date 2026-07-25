from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

from app.registries.calculation_registry import CalculationDefinition, CalculationOperation

DEFAULT_QUANTUM = Decimal("0.000001")


class ArithmeticEvaluationError(ValueError):
    pass


class DivisionByZeroEvaluationError(ArithmeticEvaluationError):
    pass


@dataclass(frozen=True)
class ArithmeticOutcome:
    value: Decimal
    checked_count: int
    excluded_count: int


def decimal_value(value: object) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ArithmeticEvaluationError("Operand must be a finite numeric value")
    try:
        converted = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ArithmeticEvaluationError("Operand must be a finite numeric value") from exc
    if not converted.is_finite():
        raise ArithmeticEvaluationError("Operand must be a finite numeric value")
    return converted


class ArithmeticEvaluator:
    def execute(
        self,
        definition: CalculationDefinition,
        records: list[dict[str, object]],
        parameters: dict[str, object],
    ) -> ArithmeticOutcome:
        missing = [item for item in definition.required_parameters if item not in parameters]
        if missing:
            raise ArithmeticEvaluationError(
                f"Missing calculation parameters: {', '.join(sorted(missing))}"
            )
        operation = definition.operation
        if operation == CalculationOperation.COUNT:
            return ArithmeticOutcome(Decimal(len(records)), len(records), 0)
        if operation == CalculationOperation.DISTINCT_COUNT:
            field = str(parameters["field"])
            values = {str(record[field]) for record in records if record.get(field) is not None}
            return ArithmeticOutcome(Decimal(len(values)), len(records), len(records) - len(values))
        if operation in {
            CalculationOperation.SUM,
            CalculationOperation.AVERAGE,
            CalculationOperation.MINIMUM,
            CalculationOperation.MAXIMUM,
        }:
            return self._aggregate(operation, records, str(parameters["field"]))
        left_key, right_key = {
            CalculationOperation.RATIO: ("numerator", "denominator"),
            CalculationOperation.PERCENTAGE: ("numerator", "denominator"),
            CalculationOperation.ABSOLUTE_VARIANCE: ("actual", "comparison"),
            CalculationOperation.PERCENTAGE_VARIANCE: ("actual", "comparison"),
            CalculationOperation.RECONCILIATION: ("left", "right"),
        }[operation]
        left = decimal_value(parameters[left_key])
        right = decimal_value(parameters[right_key])
        if (
            operation
            in {
                CalculationOperation.RATIO,
                CalculationOperation.PERCENTAGE,
                CalculationOperation.PERCENTAGE_VARIANCE,
            }
            and right == 0
        ):
            raise DivisionByZeroEvaluationError("Division by zero is not permitted")
        if operation == CalculationOperation.RATIO:
            value = left / right
        elif operation == CalculationOperation.PERCENTAGE:
            value = left * Decimal(100) / right
        elif operation in {
            CalculationOperation.ABSOLUTE_VARIANCE,
            CalculationOperation.RECONCILIATION,
        }:
            value = left - right
        else:
            value = (left - right) * Decimal(100) / right
        return ArithmeticOutcome(value.quantize(DEFAULT_QUANTUM, ROUND_HALF_EVEN), 0, 0)

    def _aggregate(
        self,
        operation: CalculationOperation,
        records: list[dict[str, object]],
        field: str,
    ) -> ArithmeticOutcome:
        values = [
            decimal_value(record[field])
            for record in records
            if field in record and record[field] is not None
        ]
        excluded = len(records) - len(values)
        if not values:
            raise ArithmeticEvaluationError(f"No numeric values available for field {field}")
        if operation == CalculationOperation.SUM:
            result = sum(values, Decimal(0))
        elif operation == CalculationOperation.AVERAGE:
            result = sum(values, Decimal(0)) / Decimal(len(values))
        elif operation == CalculationOperation.MINIMUM:
            result = min(values)
        else:
            result = max(values)
        return ArithmeticOutcome(
            result.quantize(DEFAULT_QUANTUM, ROUND_HALF_EVEN), len(records), excluded
        )
