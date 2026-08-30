from __future__ import annotations

from app.semantic.candidate import EvidenceComponentType, InterpretationEvidence, SemanticCandidate
from app.semantic.concept_registry import CanonicalConceptRegistry
from app.semantic.profiler import DatasetProfile, FieldProfile

# ---------------------------------------------------------------------------
# P3.xxE.2 section 11: generic neighboring-field semantic context. No
# hard-coded field names or examples in production code -- the mechanism is
# purely: do OTHER fields in the SAME dataset also alias to concepts that
# share a compatible_dataset_role with this field's candidate concept? A
# work-order-shaped table (siblings recognized as technician_id,
# scheduled_timestamp, status) corroborates a work_order_id candidate; a
# sensor-reading-shaped table (siblings that alias to nothing registered)
# does not -- entirely derived from CanonicalConceptRegistry data, never a
# simulation- or industry-specific branch.
# ---------------------------------------------------------------------------

NEIGHBOR_FIELD_CONTEXT_WEIGHT = 0.1


def generate_neighbor_context_evidence(
    dataset_id: str,
    dataset_profile: DatasetProfile,
    field_profile: FieldProfile,
    candidate_concepts: set[str],
    registry: CanonicalConceptRegistry,
) -> list[SemanticCandidate]:
    """Returns pseudo-candidates (one per corroborated concept) carrying a
    single NEIGHBOR_FIELD_CONTEXT evidence component each, folded into the
    matching concept's candidate by the confidence engine's existing
    merge-by-concept step -- same mechanism as cross-dataset evidence."""
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
        if concept is None or not concept.compatible_dataset_roles:
            continue
        corroborating = sorted(
            {
                sibling_code
                for sibling_code in sibling_concept_codes
                if sibling_code != concept_code
                and (sibling_concept := registry.get(sibling_code)) is not None
                and sibling_concept.compatible_dataset_roles & concept.compatible_dataset_roles
            }
        )
        if not corroborating:
            continue
        pseudo_candidates.append(
            SemanticCandidate(
                source_dataset_id=dataset_id,
                source_field=field_profile.source_field,
                candidate_concept=concept_code,
                confidence=NEIGHBOR_FIELD_CONTEXT_WEIGHT,
                evidence_components=[
                    InterpretationEvidence(
                        component_type=EvidenceComponentType.NEIGHBOR_FIELD_CONTEXT.value,
                        weight=NEIGHBOR_FIELD_CONTEXT_WEIGHT,
                        description=(
                            f"co-occurs with sibling field(s) recognized as "
                            f"{', '.join(corroborating)}, compatible with "
                            f"{concept_code!r}'s role context"
                        ),
                        supports_concept=concept_code,
                    )
                ],
                candidate_rank=60,
                generated_by="neighbor_context_v1",
            )
        )
    return pseudo_candidates
