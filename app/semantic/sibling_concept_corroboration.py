from __future__ import annotations

from app.semantic.candidate import EvidenceComponentType, InterpretationEvidence, SemanticCandidate
from app.semantic.concept_registry import CanonicalConceptRegistry
from app.semantic.profiler import DatasetProfile, FieldProfile

# ---------------------------------------------------------------------------
# P3.xxI.2A: generic sibling-concept corroboration. Distinct from
# app/semantic/neighbor_context.py, which corroborates via ROLE overlap
# between a candidate concept and whatever ANY sibling field happens to
# resolve to -- deliberately coarse, so structurally similar concepts that
# share nearly identical compatible_dataset_roles (unit_price/invoice_amount/
# cost_amount, all MONETARY_AMOUNT-typed and all sharing the raw alias
# "amount") receive that corroboration equally and it can never separate
# them.
#
# This module instead checks each concept's own declared EXACT required or
# alternative sibling sets and exclusions (app/semantic/concept_registry.py)
# against the OTHER fields' alias-matched concept
# codes on the SAME dataset -- entirely data-driven, no hard-coded field
# names, filenames, or industry branch here. A concept with no such
# requirement declared (the default for most concepts) never participates.
# ---------------------------------------------------------------------------

SIBLING_CONCEPT_CORROBORATION_WEIGHT = 0.25


def generate_sibling_concept_corroboration_evidence(
    dataset_id: str,
    dataset_profile: DatasetProfile,
    field_profile: FieldProfile,
    candidate_concepts: set[str],
    registry: CanonicalConceptRegistry,
) -> list[SemanticCandidate]:
    """Returns pseudo-candidates (one per corroborated concept) carrying a
    single SIBLING_CONCEPT_CORROBORATION evidence component each, folded
    into the matching concept's candidate by the confidence engine's
    existing merge-by-concept step -- same mechanism neighbor_context.py
    and cross_dataset_context.py already use."""
    if not candidate_concepts:
        return []

    sibling_concept_codes: set[str] = set()
    for sibling in dataset_profile.fields:
        if sibling.source_field == field_profile.source_field:
            continue
        for sibling_alias_match in registry.find_by_alias(sibling.source_field):
            sibling_concept_codes.add(sibling_alias_match.concept_code)
    if not sibling_concept_codes:
        return []

    pseudo_candidates: list[SemanticCandidate] = []
    for concept_code in candidate_concepts:
        concept = registry.get(concept_code)
        if concept is None:
            continue
        required_sets = concept.alternative_sibling_concept_sets or (
            (concept.requires_sibling_concepts,) if concept.requires_sibling_concepts else ()
        )
        satisfied_set = next(
            (required for required in required_sets if required <= sibling_concept_codes), None
        )
        if satisfied_set is None:
            continue
        if concept.excludes_sibling_concepts & sibling_concept_codes:
            continue
        pseudo_candidates.append(
            SemanticCandidate(
                source_dataset_id=dataset_id,
                source_field=field_profile.source_field,
                candidate_concept=concept_code,
                confidence=SIBLING_CONCEPT_CORROBORATION_WEIGHT,
                evidence_components=[
                    InterpretationEvidence(
                        component_type=EvidenceComponentType.SIBLING_CONCEPT_CORROBORATION.value,
                        weight=SIBLING_CONCEPT_CORROBORATION_WEIGHT,
                        description=(
                            f"co-occurs with sibling field(s) resolving to "
                            f"{sorted(satisfied_set)}, exactly the context "
                            f"{concept_code!r} declares it needs"
                            + (
                                f" (and none of {sorted(concept.excludes_sibling_concepts)}, "
                                "which would rule it out)"
                                if concept.excludes_sibling_concepts
                                else ""
                            )
                        ),
                        supports_concept=concept_code,
                    )
                ],
                candidate_rank=61,
                generated_by="sibling_concept_corroboration_v1",
            )
        )
    return pseudo_candidates
