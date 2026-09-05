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
            # P3.xxC.1 Analysis Case domain and cross-domain intelligence
            # rules. Registered here (not a parallel registry) so governed
            # finding publication can resolve definition_code/version to an
            # active definition exactly like every other rule-based finding.
            RuleDefinition(
                "MAINT-001-REPEATED-FAILURE",
                "1.0",
                "Repeated asset failure",
                "An asset has multiple recorded failure events within the analysis window.",
                RuleOperator.GREATER_THAN,
                ("failure_count", "threshold"),
                analytical_level="arithmetic",
            ),
            RuleDefinition(
                "XDOM-A-ASSET-FAILURE-LOST-ACTIVITY",
                "1.0",
                "Asset failure interrupted operational activity",
                "A maintenance downtime window overlaps one or more operational events "
                "for the same resolved asset.",
                RuleOperator.GREATER_THAN,
                ("affected_event_count", "threshold"),
                analytical_level="arithmetic",
            ),
            RuleDefinition(
                "XDOM-B-LOST-ACTIVITY-REVENUE-GAP",
                "1.0",
                "Completed activity without linked revenue",
                "A completed operational event has no matching transaction/revenue record.",
                RuleOperator.GREATER_THAN,
                ("unmatched_event_count", "threshold"),
                analytical_level="arithmetic",
            ),
            RuleDefinition(
                "XDOM-DATA-LINKAGE-ISSUE",
                "1.0",
                "Cross-domain data linkage issue",
                "Operational activity could not be reliably matched to a related domain "
                "record -- a data/semantic reconciliation issue, not a leakage claim.",
                RuleOperator.GREATER_THAN,
                ("unmatched_event_count", "threshold"),
                analytical_level="arithmetic",
            ),
            # P3.xxI.2: additive third P3.xxC.1 rule -- additive governed
            # sibling to XDOM-B, never a modification of it.
            RuleDefinition(
                "REVENUE-AMOUNT-VARIANCE",
                "1.0",
                "Revenue amount shortfall",
                "A work order's actual billed amount is materially below the amount "
                "expected from governed consumption/rate or reference-cost evidence.",
                RuleOperator.GREATER_THAN,
                ("expected_minus_actual_amount", "tolerance"),
                analytical_level="arithmetic",
            ),
            RuleDefinition(
                "CONTRACT-RATE-COMPLIANCE",
                "1.0",
                "Contract rate mismatch",
                "An explicitly applied transaction rate differs from the uniquely applicable "
                "governed contract rate for the same subject, UOM, currency, and time.",
                RuleOperator.NOT_EQUALS,
                ("actual_applied_rate", "applicable_contract_rate"),
                analytical_level="arithmetic",
            ),
            # P3.xxI.5A-R: additive sibling version -- the same rule, evaluated
            # against an actual applied rate DERIVED from attributable billed
            # amount, governed non-target components, and governed target
            # quantity, when no explicit actual_applied_rate column exists.
            # "1.0" is never modified or superseded; a subject with a valid
            # explicit rate always uses "1.0" and never also "1.1".
            RuleDefinition(
                "CONTRACT-RATE-COMPLIANCE",
                "1.1",
                "Contract rate mismatch (derived actual rate)",
                "A derived actual applied rate -- attributable billed amount minus governed "
                "non-target components, divided by governed target quantity -- differs from "
                "the uniquely applicable governed contract rate for the same subject, UOM, "
                "currency, and time.",
                RuleOperator.NOT_EQUALS,
                ("derived_actual_applied_rate", "applicable_contract_rate"),
                analytical_level="arithmetic",
            ),
        ]
    )
