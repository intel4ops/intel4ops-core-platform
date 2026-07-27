from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SignatureEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True)

    matched: bool
    confidence: Decimal = Field(ge=0, le=1)
    matched_conditions: tuple[str, ...]
    failed_conditions: tuple[str, ...]
    evidence_used: tuple[str, ...]
    limitations: tuple[str, ...]
    input_fingerprint: str


class SignatureEvaluator:
    def evaluate(
        self,
        definition: dict[str, Any],
        observations: dict[str, Any],
        evidence_types: set[str],
    ) -> SignatureEvaluation:
        matched: list[str] = []
        failed: list[str] = []
        for index, condition in enumerate(definition["required_conditions"]):
            label = f"condition:{index + 1}"
            if self._condition(condition, observations):
                matched.append(label)
            else:
                failed.append(label)
        excluded = any(
            self._condition(condition, observations)
            for condition in definition["exclusion_conditions"]
        )
        required_evidence = set(definition["evidence_requirements"])
        evidence_complete = required_evidence <= evidence_types
        base = Decimal(str(definition["confidence_model"]["base"]))
        increment = Decimal(str(definition["confidence_model"]["evidence_increment"]))
        maximum = Decimal(str(definition["confidence_model"]["maximum"]))
        confidence = min(maximum, base + increment * len(required_evidence & evidence_types))
        is_match = not failed and not excluded and evidence_complete
        if not is_match:
            confidence = min(confidence, Decimal("0.49"))
        canonical = json.dumps(
            {
                "observations": observations,
                "evidence_types": sorted(evidence_types),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        limitations = tuple(str(item) for item in definition.get("known_limitations", []))
        return SignatureEvaluation(
            matched=is_match,
            confidence=confidence,
            matched_conditions=tuple(matched),
            failed_conditions=tuple(failed),
            evidence_used=tuple(sorted(required_evidence & evidence_types)),
            limitations=limitations,
            input_fingerprint=hashlib.sha256(canonical.encode()).hexdigest(),
        )

    @staticmethod
    def _condition(condition: dict[str, Any], observations: dict[str, Any]) -> bool:
        actual = observations.get(str(condition["path"]))
        expected = condition["value"]
        operator = condition["operator"]
        if operator == "equals":
            return bool(actual == expected)
        if actual is None:
            return False
        left = Decimal(str(actual))
        right = Decimal(str(expected))
        if operator == "greater_than":
            return left > right
        if operator == "less_or_equal":
            return left <= right
        raise ValueError(f"Unsupported signature condition operator: {operator}")
