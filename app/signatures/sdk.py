from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from app.signatures.catalog import definition_hash

SIGNATURE_CODE_PATTERN = re.compile(r"^[A-Z0-9]+(?:[._-][A-Z0-9]+)+$")
REQUIRED_DEFINITION_FIELDS = frozenset(
    {
        "name",
        "description",
        "signature_type",
        "industry",
        "applicable_pack_versions",
        "required_canonical_objects",
        "required_features",
        "required_events",
        "required_conditions",
        "exclusion_conditions",
        "evidence_requirements",
        "confidence_model",
        "economic_impact_policy",
        "expected_outcome",
        "monitoring_policy",
        "known_limitations",
        "owner",
    }
)


class SignatureDefinitionError(ValueError):
    """A signature extension violates the stable SDK definition contract."""


@runtime_checkable
class SignatureExtension(Protocol):
    code: str
    semantic_version: str

    def definition(self) -> Mapping[str, object]: ...


def validate_extension(extension: SignatureExtension) -> dict[str, object]:
    if not SIGNATURE_CODE_PATTERN.fullmatch(extension.code):
        raise SignatureDefinitionError("Signature code must be a namespaced uppercase code")
    if not re.fullmatch(r"\d+\.\d+\.\d+", extension.semantic_version):
        raise SignatureDefinitionError("Signature version must use semantic versioning")
    definition = dict(extension.definition())
    missing = REQUIRED_DEFINITION_FIELDS - definition.keys()
    if missing:
        raise SignatureDefinitionError(
            f"Signature definition is missing required fields: {', '.join(sorted(missing))}"
        )
    if not definition["required_conditions"]:
        raise SignatureDefinitionError("A signature requires at least one governed condition")
    if not definition["evidence_requirements"]:
        raise SignatureDefinitionError("A signature requires an evidence contract")
    definition["definition_hash"] = definition_hash(definition)
    return definition
