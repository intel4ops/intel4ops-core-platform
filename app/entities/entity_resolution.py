from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from app.entities.case_entity_context import CaseEntityContext
from app.entities.entity_candidate import EntityCandidate, EntityObservation, FuzzyCandidateScore
from app.entities.entity_deduplication import deduplicate
from app.entities.entity_resolution_tiers import score_fuzzy_candidates
from app.entities.entity_type_inference import infer_entity_type
from app.entities.identifier_normalization import normalize_identifier
from app.semantic.candidate import InterpretationDecision
from app.semantic.concept_registry import CanonicalConceptRegistry
from app.semantic.review import resolve_effective_decision

# ---------------------------------------------------------------------------
# P3.xxE.3: top-level entity-resolution entry point. Consumes P3.xxE.1A
# EFFECTIVE semantic decisions (Invariant C/D: semantic-first, human
# governance authoritative when present) -- never raw source field names
# for typing. resolve_effective_decision is called with latest_version=
# None always: entity resolution runs within the SAME run that just
# persisted these SemanticInterpretationDecision rows, so no
# SemanticDecisionVersion can exist yet for them (an asynchronous, post-hoc
# review action) -- this makes the human-governed tier structurally dead
# code THIS run by construction, not a bug. It is still implemented
# correctly so a future milestone that carries prior review forward across
# runs gets the right behavior for free, without touching this module.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CaseDatasetEntityInput:
    """One dataset's contribution to case-level entity resolution.
    analysis_case_dataset_id is a plain string (str(UUID)) -- framework-
    free, matching app/semantic/case_context.py's own convention."""

    analysis_case_dataset_id: str
    dataset_label: str
    decisions: list[InterpretationDecision]
    raw_dataframe: pd.DataFrame


@dataclass(frozen=True)
class EntityResolutionOutcome:
    candidates: list[EntityCandidate] = field(default_factory=list)
    fuzzy_scores: list[FuzzyCandidateScore] = field(default_factory=list)
    fields_considered: int = 0
    fields_typed: int = 0


def _observations_for_dataset(
    dataset_input: CaseDatasetEntityInput,
    registry: CanonicalConceptRegistry,
) -> tuple[list[EntityObservation], int, int]:
    observations: list[EntityObservation] = []
    fields_considered = 0
    fields_typed = 0

    for decision in dataset_input.decisions:
        fields_considered += 1
        effective = resolve_effective_decision(
            machine_status=decision.status,
            machine_selected_concept=decision.selected_concept,
            machine_confidence=decision.confidence,
            latest_version=None,
        )
        if effective.effective_concept is None:
            continue
        entity_type = infer_entity_type(effective.effective_concept, registry)
        if entity_type is None:
            continue
        if decision.source_field not in dataset_input.raw_dataframe.columns:
            continue
        fields_typed += 1

        series = dataset_input.raw_dataframe[decision.source_field].dropna().astype(str)
        for raw_value in series.unique():
            normalized_value = normalize_identifier(raw_value)
            if not normalized_value:
                continue
            observations.append(
                EntityObservation(
                    analysis_case_dataset_id=dataset_input.analysis_case_dataset_id,
                    dataset_label=dataset_input.dataset_label,
                    source_field=decision.source_field,
                    concept_code=effective.effective_concept,
                    entity_type=entity_type,
                    raw_value=str(raw_value),
                    normalized_value=normalized_value,
                    semantic_confidence=effective.effective_confidence or 0.0,
                    semantic_source=effective.source,
                    human_validated=effective.human_validated,
                )
            )
    return observations, fields_considered, fields_typed


def resolve_entities_for_case(
    dataset_inputs: list[CaseDatasetEntityInput],
    registry: CanonicalConceptRegistry,
) -> EntityResolutionOutcome:
    all_observations: list[EntityObservation] = []
    fields_considered = 0
    fields_typed = 0

    # Every dataset's observations are gathered into one flat collection
    # BEFORE any grouping/dedup happens -- the structural argument for
    # order independence (matches CaseSemanticContext's Pass-1 role).
    for dataset_input in dataset_inputs:
        observations, considered, typed = _observations_for_dataset(dataset_input, registry)
        all_observations.extend(observations)
        fields_considered += considered
        fields_typed += typed

    context = CaseEntityContext(observations=all_observations)
    candidates = deduplicate(context)
    fuzzy_scores = score_fuzzy_candidates(all_observations)

    return EntityResolutionOutcome(
        candidates=candidates,
        fuzzy_scores=fuzzy_scores,
        fields_considered=fields_considered,
        fields_typed=fields_typed,
    )
