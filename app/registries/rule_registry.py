from dataclasses import dataclass
from enum import StrEnum

from app.registries.calculation_registry import (
    DefinitionNotFoundError,
    DuplicateDefinitionError,
)


class RuleOperator(StrEnum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    GREATER_THAN = "greater_than"
    GREATER_THAN_OR_EQUAL = "greater_than_or_equal"
    LESS_THAN = "less_than"
    LESS_THAN_OR_EQUAL = "less_than_or_equal"
    BETWEEN = "between"
    OUTSIDE = "outside"


@dataclass(frozen=True)
class RuleDefinition:
    code: str
    version: str
    name: str
    description: str
    operator: RuleOperator
    required_parameters: tuple[str, ...]
    analytical_level: str = "arithmetic"
    status: str = "active"


class RuleRegistry:
    def __init__(self, definitions: list[RuleDefinition] | None = None) -> None:
        self._definitions: dict[tuple[str, str], RuleDefinition] = {}
        for definition in definitions or []:
            self.register(definition)

    def register(self, definition: RuleDefinition) -> None:
        key = (definition.code, definition.version)
        if key in self._definitions:
            raise DuplicateDefinitionError(
                f"Rule {definition.code} version {definition.version} is registered"
            )
        self._definitions[key] = definition

    def get(self, code: str, version: str) -> RuleDefinition:
        try:
            return self._definitions[(code, version)]
        except KeyError as exc:
            raise DefinitionNotFoundError(
                f"Rule {code} version {version} is not registered"
            ) from exc

    def list(self) -> list[RuleDefinition]:
        return [self._definitions[key] for key in sorted(self._definitions)]


def default_rule_registry() -> RuleRegistry:
    return RuleRegistry(
        [
            RuleDefinition(
                "threshold_exceeded",
                "1.0",
                "Threshold exceeded",
                "Value is greater than the configured threshold.",
                RuleOperator.GREATER_THAN,
                ("value", "threshold"),
            ),
            RuleDefinition(
                "threshold_not_met",
                "1.0",
                "Threshold not met",
                "Value is less than the configured threshold.",
                RuleOperator.LESS_THAN,
                ("value", "threshold"),
            ),
            RuleDefinition(
                "outside_range",
                "1.0",
                "Outside range",
                "Value is outside the inclusive configured range.",
                RuleOperator.OUTSIDE,
                ("value", "lower", "upper"),
            ),
            RuleDefinition(
                "reconciliation_mismatch",
                "1.0",
                "Reconciliation mismatch",
                "Reconciliation difference is not zero.",
                RuleOperator.NOT_EQUALS,
                ("value", "threshold"),
            ),
            RuleDefinition(
                "mapping_completeness_below_threshold",
                "1.0",
                "Mapping completeness below threshold",
                "Mapped-record coverage is below the governed readiness threshold.",
                RuleOperator.LESS_THAN,
                ("value", "threshold"),
            ),
            RuleDefinition(
                "mapping_unresolved_ratio_exceeded",
                "1.0",
                "Unresolved mapping ratio exceeded",
                "Unresolved canonical mappings exceed the governed threshold.",
                RuleOperator.GREATER_THAN,
                ("value", "threshold"),
            ),
            RuleDefinition(
                "mapping_ambiguous_ratio_exceeded",
                "1.0",
                "Ambiguous mapping ratio exceeded",
                "Ambiguous entity mappings exceed the governed threshold.",
                RuleOperator.GREATER_THAN,
                ("value", "threshold"),
            ),
            RuleDefinition(
                "mapping_conflict_count_exceeded",
                "1.0",
                "Mapping conflict count exceeded",
                "Conflicting canonical mappings exceed the governed threshold.",
                RuleOperator.GREATER_THAN,
                ("value", "threshold"),
            ),
            RuleDefinition(
                "mapping_required_field_failures",
                "1.0",
                "Required canonical fields missing",
                "Required canonical fields are missing from mapped records.",
                RuleOperator.GREATER_THAN,
                ("value", "threshold"),
            ),
            RuleDefinition(
                "mapping_lineage_completeness_below_threshold",
                "1.0",
                "Mapping lineage completeness below threshold",
                "Canonical records with complete source lineage are below threshold.",
                RuleOperator.LESS_THAN,
                ("value", "threshold"),
            ),
        ]
    )
