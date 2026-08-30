from __future__ import annotations

from app.entities.case_entity_context import CaseEntityContext
from app.entities.entity_candidate import EntityCandidate, EntityObservation
from app.entities.entity_resolution_tiers import ResolutionTier
from app.entities.identifier_normalization import NORMALIZATION_POLICY_VERSION

# ---------------------------------------------------------------------------
# P3.xxE.3 section 13: entity deduplication within one run. One
# EntityCandidate per (entity_type, normalized_key) -- collapses all
# observations across all datasets and all matching identifier concepts.
# Never merges across entity_type even if two normalized_keys happen to
# collide as strings -- entity_type is always part of the identity.
#
# Confidence model (plan-review-corrected -- no universal ceiling, section
# "Confidence model"): entity_type_confidence and entity_identity_confidence
# are computed INDEPENDENTLY. Strong, well-corroborated identifier evidence
# can produce a very high entity_identity_confidence even when the
# upstream semantic-type confidence was only moderate -- e.g. semantic
# confidence 0.62 on an unfamiliar alias, but the exact identifier occurs
# consistently across five datasets, legitimately yields
# entity_type_confidence=0.62, entity_identity_confidence=0.99. Neither
# value caps the other; both persist unmerged on CanonicalEntity.
# ---------------------------------------------------------------------------

# Identity-confidence base per resolution tier (how strong is the raw
# identifier match itself, before any cross-dataset corroboration) plus a
# per-additional-distinct-dataset step. A single, uncorroborated
# observation is plausible-but-unconfirmed; corroboration across several
# independent datasets is what earns near-certainty. Constants chosen so
# an exact match corroborated across 5 datasets lands at the cap (0.99),
# matching the plan review's own worked example.
_TIER_BASE_IDENTITY_CONFIDENCE: dict[str, float] = {
    ResolutionTier.EXACT.value: 0.65,
    ResolutionTier.NORMALIZED.value: 0.55,
    ResolutionTier.COMPOSITE.value: 0.45,
}
_TIER_CORROBORATION_STEP: dict[str, float] = {
    ResolutionTier.EXACT.value: 0.085,
    ResolutionTier.NORMALIZED.value: 0.08,
    ResolutionTier.COMPOSITE.value: 0.07,
}
_TIER_IDENTITY_CONFIDENCE_CAP: dict[str, float] = {
    ResolutionTier.EXACT.value: 0.99,
    ResolutionTier.NORMALIZED.value: 0.95,
    ResolutionTier.COMPOSITE.value: 0.90,
}


def _resolution_method_for_group(observations: list[EntityObservation]) -> str:
    if all(obs.raw_value == observations[0].raw_value for obs in observations):
        return ResolutionTier.EXACT.value
    return ResolutionTier.NORMALIZED.value


def deduplicate(context: CaseEntityContext) -> list[EntityCandidate]:
    grouped: dict[tuple[str, str], list[EntityObservation]] = {}
    for obs in context.observations:
        if not obs.normalized_value:
            continue
        key = (obs.entity_type, obs.normalized_value)
        grouped.setdefault(key, []).append(obs)

    candidates: list[EntityCandidate] = []
    for (entity_type, normalized_key), observations in grouped.items():
        resolution_method = _resolution_method_for_group(observations)
        distinct_datasets = {obs.analysis_case_dataset_id for obs in observations}

        entity_type_confidence = round(
            sum(obs.semantic_confidence for obs in observations) / len(observations), 4
        )

        base = _TIER_BASE_IDENTITY_CONFIDENCE[resolution_method]
        step = _TIER_CORROBORATION_STEP[resolution_method]
        cap = _TIER_IDENTITY_CONFIDENCE_CAP[resolution_method]
        entity_identity_confidence = round(min(base + step * (len(distinct_datasets) - 1), cap), 4)

        display_label = observations[0].raw_value
        evidence_summary = [
            f"{len(observations)} observation(s) across {len(distinct_datasets)} "
            f"distinct dataset(s), resolved via {resolution_method} identifier match",
        ]
        if len(distinct_datasets) == 1:
            evidence_summary.append(
                "single-dataset observation -- not yet corroborated across datasets"
            )
        candidates.append(
            EntityCandidate(
                entity_type=entity_type,
                normalized_key=normalized_key,
                display_label=display_label,
                resolution_method=resolution_method,
                observations=observations,
                entity_type_confidence=entity_type_confidence,
                entity_identity_confidence=entity_identity_confidence,
                evidence_summary=evidence_summary,
            )
        )
    return candidates


__all__ = ["deduplicate", "NORMALIZATION_POLICY_VERSION"]
