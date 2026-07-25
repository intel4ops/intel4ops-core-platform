from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Protocol

from app.registries.calculation_registry import (
    CalculationDefinition,
    DefinitionNotFoundError,
    default_calculation_registry,
)
from app.registries.rule_registry import RuleDefinition, default_rule_registry
from app.schemas.intelligence import ExecutionType
from app.schemas.orchestration import OrchestrationAnalyticalLevel


class DefinitionKnowledgeClass(StrEnum):
    CALCULATION = "calculation"
    DETERMINISTIC_RULE = "deterministic_rule"


@dataclass(frozen=True)
class PolicyReference:
    code: str
    version: str


@dataclass(frozen=True)
class ResolvedDefinition:
    code: str
    version: str
    knowledge_class: DefinitionKnowledgeClass
    analytical_level: OrchestrationAnalyticalLevel
    required_readiness_level: OrchestrationAnalyticalLevel
    required_engine_capability: str
    is_active: bool
    publication_eligible: bool
    sufficiency_policy: PolicyReference
    escalation_policy: PolicyReference
    evidence_policy: PolicyReference
    scope_metadata: dict[str, object]
    definition_fingerprint: str


class DefinitionResolutionError(ValueError):
    pass


class DefinitionResolver(Protocol):
    def resolve(
        self,
        code: str,
        version: str,
        execution_type: ExecutionType,
    ) -> ResolvedDefinition: ...


def _fingerprint(value: object) -> str:
    encoded = json.dumps(value, default=str, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


class CodeBackedOIKBDefinitionResolver:
    """Temporary adapter over WP-2.07 registries.

    A persisted OIKB can replace this implementation without changing the
    orchestration service or its normalized definition contract.
    """

    def __init__(self) -> None:
        self.calculations = default_calculation_registry()
        self.rules = default_rule_registry()

    def resolve(
        self,
        code: str,
        version: str,
        execution_type: ExecutionType,
    ) -> ResolvedDefinition:
        try:
            if execution_type == ExecutionType.CALCULATION:
                calculation = self.calculations.get(code, version)
                return self._calculation(calculation)
            rule = self.rules.get(code, version)
            return self._rule(rule)
        except DefinitionNotFoundError as exc:
            raise DefinitionResolutionError("Definition is not eligible") from exc

    @staticmethod
    def _calculation(definition: CalculationDefinition) -> ResolvedDefinition:
        return ResolvedDefinition(
            code=definition.code,
            version=definition.version,
            knowledge_class=DefinitionKnowledgeClass.CALCULATION,
            analytical_level=OrchestrationAnalyticalLevel.ARITHMETIC,
            required_readiness_level=OrchestrationAnalyticalLevel.ARITHMETIC,
            required_engine_capability="bounded_arithmetic",
            is_active=definition.status == "active",
            publication_eligible=definition.status == "active",
            sufficiency_policy=PolicyReference("DETERMINISTIC_EXECUTION_SUFFICIENCY", "1.0"),
            escalation_policy=PolicyReference("OIKB_BOUNDED_ESCALATION", "1.0"),
            evidence_policy=PolicyReference(
                definition.evidence_contract or "WP207_EXECUTION_EVIDENCE",
                "1.0",
            ),
            scope_metadata={
                "canonical_fields": list(definition.canonical_fields),
                "unit_policy": definition.unit_policy,
                "currency_policy": definition.currency_policy,
                "scope_correction": definition.scope_correction,
                "domain_owner": definition.domain_owner,
            },
            definition_fingerprint=_fingerprint(asdict(definition)),
        )

    @staticmethod
    def _rule(definition: RuleDefinition) -> ResolvedDefinition:
        return ResolvedDefinition(
            code=definition.code,
            version=definition.version,
            knowledge_class=DefinitionKnowledgeClass.DETERMINISTIC_RULE,
            analytical_level=OrchestrationAnalyticalLevel.RULE_BASED,
            required_readiness_level=OrchestrationAnalyticalLevel.ARITHMETIC,
            required_engine_capability="bounded_deterministic_rule",
            is_active=definition.status == "active",
            publication_eligible=definition.status == "active",
            sufficiency_policy=PolicyReference("DETERMINISTIC_EXECUTION_SUFFICIENCY", "1.0"),
            escalation_policy=PolicyReference("OIKB_BOUNDED_ESCALATION", "1.0"),
            evidence_policy=PolicyReference("WP207_RULE_EXECUTION_EVIDENCE", "1.0"),
            scope_metadata={
                "required_parameters": list(definition.required_parameters),
                "operator": definition.operator.value,
            },
            definition_fingerprint=_fingerprint(asdict(definition)),
        )
