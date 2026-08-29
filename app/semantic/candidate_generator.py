from __future__ import annotations

from app.semantic.candidate import EvidenceComponentType, InterpretationEvidence, SemanticCandidate
from app.semantic.concept_registry import (
    CanonicalConceptRegistry,
    default_canonical_concept_registry,
)
from app.semantic.profiler import DatasetProfile, FieldProfile
from app.semantic.role_classifier import DatasetRoleInterpretation

# ---------------------------------------------------------------------------
# Deterministic evidence generation only (section 6/10) -- this module never
# calls a SemanticReasoningProvider itself; app/semantic/interpreter.py
# combines this deterministic pass with an optional AI proposal before
# handing everything to the confidence engine. No branch here on a
# simulation identifier, industry, or specific client field name -- every
# piece of "known terminology" comes from the CanonicalConceptRegistry.
# ---------------------------------------------------------------------------


def generate_candidates(
    dataset_id: str,
    dataset_profile: DatasetProfile,
    role_interpretation: DatasetRoleInterpretation,
    field_profile: FieldProfile,
    registry: CanonicalConceptRegistry | None = None,
) -> list[SemanticCandidate]:
    registry = registry or default_canonical_concept_registry
    alias_matches = registry.find_by_alias(field_profile.source_field)

    scored: dict[str, tuple[float, list[InterpretationEvidence]]] = {}

    for concept in alias_matches:
        evidence = [
            InterpretationEvidence(
                component_type=EvidenceComponentType.FIELD_NAME_ALIAS_MATCH.value,
                weight=0.5,
                description=(
                    f"source field {field_profile.source_field!r} matches a known alias "
                    f"of {concept.concept_code!r}"
                ),
                supports_concept=concept.concept_code,
            )
        ]
        weight = 0.5

        if (
            concept.expected_value_patterns
            and set(field_profile.value_patterns) & concept.expected_value_patterns
        ):
            evidence.append(
                InterpretationEvidence(
                    component_type=EvidenceComponentType.VALUE_PATTERN_MATCH.value,
                    weight=0.2,
                    description=(
                        f"observed value pattern(s) {field_profile.value_patterns} match "
                        f"expected pattern(s) for {concept.concept_code!r}"
                    ),
                    supports_concept=concept.concept_code,
                )
            )
            weight += 0.2

        if (
            concept.compatible_dataset_roles
            and role_interpretation.primary_role in concept.compatible_dataset_roles
        ):
            evidence.append(
                InterpretationEvidence(
                    component_type=EvidenceComponentType.DATASET_ROLE_COMPATIBILITY.value,
                    weight=0.15,
                    description=(
                        f"dataset role {role_interpretation.primary_role!r} is compatible "
                        f"with {concept.concept_code!r}"
                    ),
                    supports_concept=concept.concept_code,
                )
            )
            weight += 0.15

        datatype_ok = _datatype_compatible(concept.concept_type, field_profile)
        if datatype_ok:
            evidence.append(
                InterpretationEvidence(
                    component_type=EvidenceComponentType.DATATYPE_COMPATIBILITY.value,
                    weight=0.1,
                    description=(
                        f"physical type {field_profile.physical_type!r} is compatible "
                        f"with concept type {concept.concept_type!r}"
                    ),
                    supports_concept=concept.concept_code,
                )
            )
            weight += 0.1

        scored[concept.concept_code] = (min(weight, 0.98), evidence)

    ranked = sorted(scored.items(), key=lambda item: item[1][0], reverse=True)
    return [
        SemanticCandidate(
            source_dataset_id=dataset_id,
            source_field=field_profile.source_field,
            candidate_concept=concept_code,
            confidence=confidence,
            evidence_components=evidence,
            candidate_rank=rank,
        )
        for rank, (concept_code, (confidence, evidence)) in enumerate(ranked)
    ]


def _datatype_compatible(concept_type: str, field_profile: FieldProfile) -> bool:
    if concept_type in {"quantity", "monetary_amount"}:
        return field_profile.is_numeric_like or field_profile.is_currency_like
    if concept_type == "timestamp":
        return field_profile.is_date_like
    if concept_type == "identifier":
        return field_profile.is_candidate_identifier
    if concept_type == "status":
        return field_profile.is_candidate_categorical
    return True
