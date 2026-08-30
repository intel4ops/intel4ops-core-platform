from __future__ import annotations

from app.semantic.candidate import EvidenceComponentType, InterpretationEvidence, SemanticCandidate
from app.semantic.case_context import CaseSemanticContext
from app.semantic.concept_registry import CanonicalConceptRegistry
from app.semantic.profiler import FieldProfile

# ---------------------------------------------------------------------------
# P3.xxE.2 section 12: cross-dataset semantic corroboration, order-
# independent by construction (see app/semantic/case_context.py). This is
# semantic EVIDENCE only -- a bounded, reusable building block, never a
# full canonical-relationship resolver (that remains P3.xxE.3's job).
#
# Deliberately concept-agnostic about the SIBLING dataset's own resolved
# interpretation: this module never reads another dataset's
# SemanticInterpretationDecision (which would depend on Pass-2 execution
# order for that sibling). Instead it corroborates the CURRENT field's own
# already-generated candidate concepts by checking whether a sibling
# dataset's field independently aliases to the same concept AND shows
# structural overlap (values or value-pattern signature) -- both checks
# use only Pass-1 profile data, which is fully order-independent.
# ---------------------------------------------------------------------------

CROSS_DATASET_OVERLAP_WEIGHT = 0.15
_MIN_SHARED_VALUES = 1


def _values_overlap(a: list[str], b: list[str]) -> bool:
    a_set = {v.strip().lower() for v in a if v}
    b_set = {v.strip().lower() for v in b if v}
    return len(a_set & b_set) >= _MIN_SHARED_VALUES


def generate_cross_dataset_evidence(
    current_dataset_key: str,
    field_profile: FieldProfile,
    candidate_concepts: set[str],
    case_context: CaseSemanticContext | None,
    registry: CanonicalConceptRegistry,
) -> list[SemanticCandidate]:
    """Returns pseudo-candidates (one per corroborated concept) carrying a
    single CROSS_DATASET_OVERLAP evidence component each -- these are
    concatenated alongside deterministic/AI candidates in interpret_dataset()
    and folded into the matching concept's candidate by the confidence
    engine's existing merge-by-concept step (app/semantic/confidence_engine.py),
    exactly like an AI proposal would be. No new merge mechanism needed."""
    if case_context is None or not field_profile.is_candidate_identifier or not candidate_concepts:
        return []

    pseudo_candidates: list[SemanticCandidate] = []
    seen_concepts: set[str] = set()
    for other_key, other_profile in case_context.profiles.items():
        if other_key == current_dataset_key:
            continue
        for other_field in other_profile.fields:
            if not other_field.is_candidate_identifier:
                continue
            structurally_similar = _values_overlap(
                field_profile.sample_values, other_field.sample_values
            ) or bool(set(field_profile.value_patterns) & set(other_field.value_patterns))
            if not structurally_similar:
                continue
            other_alias_matches = {
                concept.concept_code for concept in registry.find_by_alias(other_field.source_field)
            }
            for concept_code in (candidate_concepts & other_alias_matches) - seen_concepts:
                seen_concepts.add(concept_code)
                pseudo_candidates.append(
                    SemanticCandidate(
                        source_dataset_id=current_dataset_key,
                        source_field=field_profile.source_field,
                        candidate_concept=concept_code,
                        confidence=CROSS_DATASET_OVERLAP_WEIGHT,
                        evidence_components=[
                            InterpretationEvidence(
                                component_type=EvidenceComponentType.CROSS_DATASET_OVERLAP.value,
                                weight=CROSS_DATASET_OVERLAP_WEIGHT,
                                description=(
                                    f"identifier-like values overlap with "
                                    f"{other_profile.dataset_label}.{other_field.source_field}, "
                                    f"which independently aliases to {concept_code!r}"
                                ),
                                supports_concept=concept_code,
                            )
                        ],
                        candidate_rank=50,
                        generated_by="cross_dataset_context_v1",
                    )
                )
    return pseudo_candidates
