from dataclasses import dataclass
from enum import StrEnum


class CalculationOperation(StrEnum):
    COUNT = "count"
    DISTINCT_COUNT = "distinct_count"
    SUM = "sum"
    AVERAGE = "average"
    MINIMUM = "minimum"
    MAXIMUM = "maximum"
    RATIO = "ratio"
    PERCENTAGE = "percentage"
    ABSOLUTE_VARIANCE = "absolute_variance"
    PERCENTAGE_VARIANCE = "percentage_variance"
    RECONCILIATION = "reconciliation"


@dataclass(frozen=True)
class CalculationDefinition:
    code: str
    version: str
    name: str
    description: str
    operation: CalculationOperation
    required_parameters: tuple[str, ...]
    output_unit: str | None = None
    supports_currency: bool = False
    analytical_level: str = "arithmetic"
    status: str = "active"


class DefinitionNotFoundError(ValueError):
    pass


class DuplicateDefinitionError(ValueError):
    pass


class CalculationRegistry:
    def __init__(self, definitions: list[CalculationDefinition] | None = None) -> None:
        self._definitions: dict[tuple[str, str], CalculationDefinition] = {}
        for definition in definitions or []:
            self.register(definition)

    def register(self, definition: CalculationDefinition) -> None:
        key = (definition.code, definition.version)
        if key in self._definitions:
            raise DuplicateDefinitionError(
                f"Calculation {definition.code} version {definition.version} is registered"
            )
        self._definitions[key] = definition

    def get(self, code: str, version: str) -> CalculationDefinition:
        try:
            return self._definitions[(code, version)]
        except KeyError as exc:
            raise DefinitionNotFoundError(
                f"Calculation {code} version {version} is not registered"
            ) from exc

    def list(self) -> list[CalculationDefinition]:
        return [self._definitions[key] for key in sorted(self._definitions)]


def default_calculation_registry() -> CalculationRegistry:
    definitions = [
        CalculationDefinition(
            "record_count",
            "1.0",
            "Record count",
            "Count submitted records.",
            CalculationOperation.COUNT,
            (),
        ),
        CalculationDefinition(
            "distinct_count",
            "1.0",
            "Distinct count",
            "Count distinct non-null field values.",
            CalculationOperation.DISTINCT_COUNT,
            ("field",),
        ),
        CalculationDefinition(
            "sum",
            "1.0",
            "Sum",
            "Sum non-null numeric field values.",
            CalculationOperation.SUM,
            ("field",),
            supports_currency=True,
        ),
        CalculationDefinition(
            "average",
            "1.0",
            "Average",
            "Arithmetic mean of non-null numeric values.",
            CalculationOperation.AVERAGE,
            ("field",),
            supports_currency=True,
        ),
        CalculationDefinition(
            "minimum",
            "1.0",
            "Minimum",
            "Minimum non-null numeric field value.",
            CalculationOperation.MINIMUM,
            ("field",),
            supports_currency=True,
        ),
        CalculationDefinition(
            "maximum",
            "1.0",
            "Maximum",
            "Maximum non-null numeric field value.",
            CalculationOperation.MAXIMUM,
            ("field",),
            supports_currency=True,
        ),
        CalculationDefinition(
            "ratio",
            "1.0",
            "Ratio",
            "Divide numerator by denominator.",
            CalculationOperation.RATIO,
            ("numerator", "denominator"),
            output_unit="ratio",
        ),
        CalculationDefinition(
            "percentage",
            "1.0",
            "Percentage",
            "Numerator as a percentage of denominator.",
            CalculationOperation.PERCENTAGE,
            ("numerator", "denominator"),
            output_unit="percent",
        ),
        CalculationDefinition(
            "absolute_variance",
            "1.0",
            "Absolute variance",
            "Actual minus comparison value.",
            CalculationOperation.ABSOLUTE_VARIANCE,
            ("actual", "comparison"),
            supports_currency=True,
        ),
        CalculationDefinition(
            "percentage_variance",
            "1.0",
            "Percentage variance",
            "Actual minus comparison as a percentage of comparison.",
            CalculationOperation.PERCENTAGE_VARIANCE,
            ("actual", "comparison"),
            output_unit="percent",
        ),
        CalculationDefinition(
            "reconciliation",
            "1.0",
            "Reconciliation difference",
            "Left total minus right total.",
            CalculationOperation.RECONCILIATION,
            ("left", "right"),
            supports_currency=True,
        ),
    ]
    return CalculationRegistry(definitions)
