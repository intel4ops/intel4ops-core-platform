from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from app.entities.entity_candidate import EntityCandidate
from app.process.activity_candidate import (
    ActivityCandidate,
    ActivityObservation,
    ProcessEdgeCandidate,
)
from app.process.activity_discovery import (
    DatasetActivityInput,
    assemble_activity_candidates,
    discover_state_observations,
    discover_temporal_observations,
)
from app.process.activity_type import ActivityType, BoundaryStatus, ProcessEdgeType, ProcessStatus
from app.process.case_process_context import CaseProcessContext
from app.process.precedence_confidence import (
    PrecedenceConfidenceResult,
    compose_precedence_confidence,
    resolve_edge_type,
)
from app.process.process_anchor_discovery import (
    EntityTypeActivityStats,
    score_anchor_candidates,
    select_anchor_entity_type,
)
from app.process.process_boundary import classify_boundary
from app.process.process_confidence import (
    compute_process_confidence_components,
    rollup_process_confidence,
)
from app.process.sequence_discovery import (
    PairTally,
    TimedActivity,
    merge_pair_tallies,
    tally_pairwise_precedence,
)
from app.process.state_normalization import find_state_sequence
from app.semantic.candidate import InterpretationDecision

# ---------------------------------------------------------------------------
# P3.xxE.4: top-level process-interpretation entry point, mirroring
# app/entities/entity_resolution.py's own shape -- a pure, framework-free
# function that gathers per-dataset evidence into one flat, order-
# independent CaseProcessContext BEFORE any grouping/sequencing happens
# (Invariant: order independence, tests B/C/T), then discovers process
# instances anchored on whichever entity type wins process_anchor_discovery's
# scoring, falling back to a single case-level UNKNOWN_PROCESS instance
# when nothing clears the minimal anchor threshold.
#
# Pairwise precedence tallying is ALWAYS computed per-entity first (never
# pooling different entities' activities into one tally_pairwise_precedence
# call -- that module's own contract is "all activities for ONE anchor
# entity"), then aggregated case-level per activity-type pair via
# merge_pair_tallies, mirroring app/entities/relationship_discovery.py's own
# "decide shape once per type-pair at case level, reapply per instance"
# precedent. This is also what makes the STRONG temporal-evidence tier's
# "repeating across >=3 rows" threshold meaningful: it climbs only when
# multiple DIFFERENT anchor entities each contribute their own same-row
# observation of the same activity-type pair.
#
# Reads app.entities.entity_candidate.EntityCandidate and
# app.process.activity_candidate.ActivityCandidate ONLY -- never writes
# back to E.3's canonical entity identity (Invariant N: E.3 canonical
# entity identity is not rewritten).
# ---------------------------------------------------------------------------

_SUBJECT_PARTICIPATION_CONFIDENCE = 0.8
_MIN_MULTI_DATASET_OBSERVATIONS = 2

# Persisted alongside every CanonicalOperationalProcess/CanonicalProcessActivity/
# CanonicalProcessEdge row (mirrors app/entities/identifier_normalization.py's
# NORMALIZATION_POLICY_VERSION / app/entities/confidence_decomposition.py's
# RELATIONSHIP_POLICY_VERSION) -- bump whenever this module's scoring/
# grouping algorithm changes in a way that would make old and new rows not
# directly comparable.
PROCESS_POLICY_VERSION = "v1"
ACTIVITY_POLICY_VERSION = "v1"
EDGE_POLICY_VERSION = "v1"


@dataclass(frozen=True)
class CaseDatasetProcessInput:
    """One dataset's contribution to case-level process interpretation --
    mirrors CaseDatasetEntityInput's shape with the addition of
    dataset_role (needed by activity_discovery.py's corroboration gate)."""

    analysis_case_dataset_id: str
    dataset_label: str
    dataset_role: str
    decisions: list[InterpretationDecision]
    raw_dataframe: pd.DataFrame


@dataclass(frozen=True)
class ProcessInstanceCandidate:
    anchor_entity_type: str | None
    anchor_entity_id: str | None
    anchor_confidence: float
    process_type: str | None
    process_label: str | None
    process_family: str | None
    boundary_status: str
    status: str
    activities: list[ActivityCandidate] = field(default_factory=list)
    edges: list[ProcessEdgeCandidate] = field(default_factory=list)
    coverage_confidence: float = 0.0
    activity_confidence: float = 0.0
    entity_participation_confidence: float = 0.0
    temporal_confidence: float = 0.0
    precedence_consistency_confidence: float = 0.0
    state_transition_confidence: float = 0.0
    overall_confidence: float = 0.0
    evidence_summary: list[str] = field(default_factory=list)
    conflict_reason: str | None = None


@dataclass(frozen=True)
class ProcessInterpretationOutcome:
    process_instances: list[ProcessInstanceCandidate] = field(default_factory=list)
    activities_discovered: int = 0
    entity_types_considered: int = 0


def _entity_lookup_by_dataset(
    entity_candidates: list[EntityCandidate],
) -> dict[str, dict[str, dict[str, tuple[str, str]]]]:
    """dataset_id -> {source_field: {normalized_value: (entity_type, canonical_key)}} --
    built from entities ALREADY resolved by P3.xxE.3, never re-resolved
    here (mirrors relationship_discovery.py's own field-lookup builder)."""
    result: dict[str, dict[str, dict[str, tuple[str, str]]]] = {}
    for candidate in entity_candidates:
        for obs in candidate.observations:
            by_field = result.setdefault(obs.analysis_case_dataset_id, {})
            by_value = by_field.setdefault(obs.source_field, {})
            by_value[obs.normalized_value] = (candidate.entity_type, candidate.normalized_key)
    return result


def _entity_type_stats(
    entity_candidates: list[EntityCandidate],
    activities_by_entity: dict[str, list[ActivityCandidate]],
) -> list[EntityTypeActivityStats]:
    total_entity_count_in_case = len(entity_candidates)
    by_type: dict[str, list[EntityCandidate]] = {}
    for candidate in entity_candidates:
        by_type.setdefault(candidate.entity_type, []).append(candidate)

    stats: list[EntityTypeActivityStats] = []
    for entity_type, candidates in by_type.items():
        entities_with_activity = 0
        total_activity_count = 0
        multi_dataset_entity_count = 0
        for candidate in candidates:
            distinct_datasets = {obs.analysis_case_dataset_id for obs in candidate.observations}
            if len(distinct_datasets) >= _MIN_MULTI_DATASET_OBSERVATIONS:
                multi_dataset_entity_count += 1
            activities = activities_by_entity.get(candidate.normalized_key, [])
            if activities:
                entities_with_activity += 1
                total_activity_count += len(activities)
        stats.append(
            EntityTypeActivityStats(
                entity_type=entity_type,
                entity_count=len(candidates),
                entities_with_activity=entities_with_activity,
                total_activity_count=total_activity_count,
                multi_dataset_entity_count=multi_dataset_entity_count,
                total_entity_count_in_case=total_entity_count_in_case,
            )
        )
    return stats


def _timed_activities(activities: list[ActivityCandidate]) -> list[TimedActivity]:
    return [
        TimedActivity(
            index=i,
            activity_type=a.activity_type,
            occurred_at=a.occurred_at,
            analysis_case_dataset_id=(
                a.observations[0].analysis_case_dataset_id if a.observations else ""
            ),
            is_explicit_event=a.is_explicit_event,
        )
        for i, a in enumerate(activities)
    ]


def _type_confidence_by_type(activities: list[ActivityCandidate]) -> dict[str, float]:
    """Case-level (across every activity contributing to the pool, not
    just one instance): the strongest observed activity_type_confidence
    for each named type, used as the semantic floor input for that
    type-pair's case-level precedence composition."""
    result: dict[str, float] = {}
    for a in activities:
        result[a.activity_type] = max(result.get(a.activity_type, 0.0), a.activity_type_confidence)
    return result


def _case_level_pair_results(
    per_entity_activities: list[list[ActivityCandidate]],
) -> dict[tuple[str, str], tuple[PrecedenceConfidenceResult, PairTally]]:
    """Tallies pairwise precedence PER ENTITY first (tally_pairwise_precedence's
    own contract: one entity's activities per call, never pooled), then
    aggregates case-level per activity-type pair -- mirrors
    relationship_discovery.py's "decide shape once per type-pair, reapply
    per instance" precedent, and is what gives the STRONG temporal tier's
    repeat-count threshold real cross-entity meaning."""
    per_entity_tallies = [
        tally_pairwise_precedence(_timed_activities(a)) for a in per_entity_activities
    ]
    case_level_tallies = merge_pair_tallies(per_entity_tallies)

    all_activities = [a for activities in per_entity_activities for a in activities]
    type_confidence = _type_confidence_by_type(all_activities)

    results: dict[tuple[str, str], tuple[PrecedenceConfidenceResult, PairTally]] = {}
    for (type_a, type_b), tally in case_level_tallies.items():
        weaker = min(type_confidence.get(type_a, 0.0), type_confidence.get(type_b, 0.0))
        result = compose_precedence_confidence(
            tally,
            weaker_activity_type_confidence=weaker,
            entity_participation_confidence=_SUBJECT_PARTICIPATION_CONFIDENCE,
        )
        results[(type_a, type_b)] = (result, tally)
    return results


def _build_state_transition_edges(
    activities: list[ActivityCandidate],
) -> list[ProcessEdgeCandidate]:
    """Section 10: state-transition edges (STATE_TRANSITION + from_state/
    to_state) for one entity instance's own observed state history --
    always ordered by real occurred_at VALUES (find_state_sequence's own
    contract), never by activities-list position. Per-instance, not
    case-level-aggregated like the activity-type-pair edges above: each
    entity's state history is its own timeline, not a pattern pooled
    across different entities."""
    dated: list[tuple[int, str, datetime]] = [
        (i, a.state_value, a.occurred_at)
        for i, a in enumerate(activities)
        if a.state_value is not None and a.occurred_at is not None
    ]
    if len(dated) < 2:
        return []
    dated.sort(key=lambda triple: triple[2])
    index_by_state_time: dict[tuple[str, datetime], int] = {
        (state_value, occurred_at): i for i, state_value, occurred_at in dated
    }
    ordered_states = [(state_value, occurred_at) for _, state_value, occurred_at in dated]
    transitions = find_state_sequence(ordered_states)

    edges: list[ProcessEdgeCandidate] = []
    for from_state, to_state, from_time, to_time in transitions:
        from_index = index_by_state_time.get((from_state, from_time))
        to_index = index_by_state_time.get((to_state, to_time))
        if from_index is None or to_index is None:
            continue
        from_activity = activities[from_index]
        to_activity = activities[to_index]
        semantic_floor = min(
            from_activity.state_meaning_confidence, to_activity.state_meaning_confidence
        )
        existence_floor = min(
            from_activity.state_existence_confidence, to_activity.state_existence_confidence
        )
        # A single, real, chronologically-ordered pair of observations for
        # THIS entity -- never row order. Not cross-entity-aggregated, so
        # temporal confidence stays at a fixed, modest single-observation
        # level rather than climbing with repeat count (mirrors WEAK/
        # single-support treatment elsewhere in this package).
        temporal_confidence = 0.6
        precedence_confidence = round(
            min(0.5 * semantic_floor + 0.3 * existence_floor + 0.2 * temporal_confidence, 0.98), 4
        )
        status = (
            ProcessStatus.AUTO_ACCEPTED.value
            if precedence_confidence >= 0.75
            else ProcessStatus.ACCEPTED_WITH_FLAG.value
            if precedence_confidence >= 0.4
            else ProcessStatus.REVIEW_REQUIRED.value
        )
        edges.append(
            ProcessEdgeCandidate(
                left_index=from_index,
                right_index=to_index,
                edge_type=ProcessEdgeType.STATE_TRANSITION.value,
                from_state=from_state,
                to_state=to_state,
                support_count=1,
                a_before_b_count=1,
                b_before_a_count=0,
                same_time_count=0,
                unknown_order_count=0,
                observation_count=1,
                temporal_evidence_tier="WEAK",
                semantic_confidence=semantic_floor,
                entity_participation_confidence=_SUBJECT_PARTICIPATION_CONFIDENCE,
                temporal_confidence=temporal_confidence,
                repetition_confidence=0.0,
                consistency_confidence=1.0,
                conflict_penalty=0.0,
                precedence_confidence=precedence_confidence,
                contradiction_count=0,
                status=status,
                evidence_summary=[
                    f"state transition {from_state!r} -> {to_state!r} observed at "
                    f"{from_time.isoformat()} -> {to_time.isoformat()} for this entity"
                ],
                conflict_reason=None,
            )
        )
    return edges


def _build_process_instance(
    *,
    anchor_entity_type: str | None,
    anchor_entity_id: str | None,
    anchor_confidence: float,
    activities: list[ActivityCandidate],
    forced_boundary_unknown: bool,
    pair_results: dict[tuple[str, str], tuple[PrecedenceConfidenceResult, PairTally]],
) -> ProcessInstanceCandidate:
    named_types = {
        a.activity_type for a in activities if a.activity_type != ActivityType.GENERIC.value
    }
    boundary_status = (
        BoundaryStatus.UNKNOWN.value if forced_boundary_unknown else classify_boundary(named_types)
    )

    instance_types = {a.activity_type for a in activities}
    first_index_by_type: dict[str, int] = {}
    for i, a in enumerate(activities):
        first_index_by_type.setdefault(a.activity_type, i)

    edges: list[ProcessEdgeCandidate] = []
    for (type_a, type_b), (result, tally) in pair_results.items():
        # A case-level pair is only materialized as an edge on instances
        # that actually observed BOTH sides themselves -- the case-level
        # aggregate decides the pair's CONFIDENCE/TIER, never which
        # instances the pair applies to.
        if type_a not in instance_types or type_b not in instance_types:
            continue
        edge_type = resolve_edge_type(tally, result.status)
        edges.append(
            ProcessEdgeCandidate(
                left_index=first_index_by_type.get(type_a, 0),
                right_index=first_index_by_type.get(type_b, 0),
                edge_type=edge_type,
                from_state=None,
                to_state=None,
                support_count=tally.support_count,
                a_before_b_count=tally.a_before_b_count,
                b_before_a_count=tally.b_before_a_count,
                same_time_count=tally.same_time_count,
                unknown_order_count=tally.unknown_order_count,
                observation_count=tally.observation_count,
                temporal_evidence_tier=result.temporal_evidence_tier,
                semantic_confidence=result.semantic_confidence,
                entity_participation_confidence=result.entity_participation_confidence,
                temporal_confidence=result.temporal_confidence,
                repetition_confidence=result.repetition_confidence,
                consistency_confidence=result.consistency_confidence,
                conflict_penalty=result.conflict_penalty,
                precedence_confidence=result.precedence_confidence,
                contradiction_count=1 if result.status == ProcessStatus.CONFLICTED.value else 0,
                status=result.status,
                evidence_summary=[
                    f"{type_a} vs {type_b} (case-level): {tally.a_before_b_count} A-before-B, "
                    f"{tally.b_before_a_count} B-before-A, {tally.same_time_count} same-time, "
                    f"{tally.unknown_order_count} unknown-order across {tally.observation_count} "
                    "co-observation(s) pooled from every anchor entity in this run"
                ],
                conflict_reason=(
                    f"both directions independently supported for {type_a}/{type_b} "
                    "across the anchor entities in this run"
                    if result.status == ProcessStatus.CONFLICTED.value
                    else None
                ),
            )
        )

    state_transition_edges = _build_state_transition_edges(activities)
    edges.extend(state_transition_edges)

    components = compute_process_confidence_components(
        activity_confidences=[a.activity_confidence for a in activities],
        participation_confidences=[_SUBJECT_PARTICIPATION_CONFIDENCE for _ in activities],
        edge_temporal_confidences=[e.temporal_confidence for e in edges],
        edge_precedence_confidences=[e.precedence_confidence for e in edges],
        state_transition_meaning_confidences=(
            [e.precedence_confidence for e in state_transition_edges]
            if state_transition_edges
            else [a.state_meaning_confidence for a in activities if a.state_value is not None]
        ),
        activities_attached=len(activities),
    )
    overall_confidence = rollup_process_confidence(components)
    status = _resolve_process_status(edges, overall_confidence)

    return ProcessInstanceCandidate(
        anchor_entity_type=anchor_entity_type,
        anchor_entity_id=anchor_entity_id,
        anchor_confidence=anchor_confidence,
        process_type="UNKNOWN_PROCESS" if anchor_entity_type is None else None,
        process_label=None,
        process_family=None,
        boundary_status=boundary_status,
        status=status,
        activities=activities,
        edges=edges,
        coverage_confidence=components.coverage_confidence,
        activity_confidence=components.activity_confidence,
        entity_participation_confidence=components.entity_participation_confidence,
        temporal_confidence=components.temporal_confidence,
        precedence_consistency_confidence=components.precedence_consistency_confidence,
        state_transition_confidence=components.state_transition_confidence,
        overall_confidence=overall_confidence,
        evidence_summary=[
            f"{len(activities)} activit(y/ies), {len(edges)} pairwise precedence edge(s)"
        ],
        conflict_reason=None,
    )


def _resolve_process_status(edges: list[ProcessEdgeCandidate], overall_confidence: float) -> str:
    if any(e.status == ProcessStatus.CONFLICTED.value for e in edges):
        return ProcessStatus.CONFLICTED.value
    if overall_confidence >= 0.75:
        return ProcessStatus.AUTO_ACCEPTED.value
    if overall_confidence >= 0.4:
        return ProcessStatus.ACCEPTED_WITH_FLAG.value
    return ProcessStatus.REVIEW_REQUIRED.value


def interpret_process_for_case(
    dataset_inputs: list[CaseDatasetProcessInput],
    entity_candidates: list[EntityCandidate],
) -> ProcessInterpretationOutcome:
    entity_lookup = _entity_lookup_by_dataset(entity_candidates)

    observations: list[ActivityObservation] = []
    for dataset_input in dataset_inputs:
        activity_input = DatasetActivityInput(
            analysis_case_dataset_id=dataset_input.analysis_case_dataset_id,
            dataset_label=dataset_input.dataset_label,
            dataset_role=dataset_input.dataset_role,
            decisions=dataset_input.decisions,
            raw_dataframe=dataset_input.raw_dataframe,
            entity_lookup_by_field=entity_lookup.get(dataset_input.analysis_case_dataset_id, {}),
        )
        observations.extend(discover_temporal_observations(activity_input))
        observations.extend(discover_state_observations(activity_input))

    context = CaseProcessContext(observations=observations)
    activity_candidates = assemble_activity_candidates(context.observations)

    activities_by_entity: dict[str, list[ActivityCandidate]] = {}
    for candidate in activity_candidates:
        if candidate.primary_entity_id is None:
            continue
        activities_by_entity.setdefault(candidate.primary_entity_id, []).append(candidate)

    entity_by_key = {c.normalized_key: c for c in entity_candidates}
    stats = _entity_type_stats(entity_candidates, activities_by_entity)
    scores = score_anchor_candidates(stats)
    anchor_type = select_anchor_entity_type(scores)
    anchor_score_by_type = {s.entity_type: s.anchor_score for s in scores}

    process_instances: list[ProcessInstanceCandidate] = []

    if anchor_type is not None:
        anchor_entities = [
            (entity_id, activities)
            for entity_id, activities in activities_by_entity.items()
            if (entity := entity_by_key.get(entity_id)) is not None
            and entity.entity_type == anchor_type
        ]
        pair_results = _case_level_pair_results([activities for _, activities in anchor_entities])
        for entity_id, activities in anchor_entities:
            process_instances.append(
                _build_process_instance(
                    anchor_entity_type=anchor_type,
                    anchor_entity_id=entity_id,
                    anchor_confidence=anchor_score_by_type.get(anchor_type, 0.0),
                    activities=activities,
                    forced_boundary_unknown=False,
                    pair_results=pair_results,
                )
            )
    else:
        per_entity_activities = list(activities_by_entity.values())
        all_activities = [a for activities in per_entity_activities for a in activities]
        if all_activities:
            pair_results = _case_level_pair_results(per_entity_activities)
            process_instances.append(
                _build_process_instance(
                    anchor_entity_type=None,
                    anchor_entity_id=None,
                    anchor_confidence=0.0,
                    activities=all_activities,
                    forced_boundary_unknown=True,
                    pair_results=pair_results,
                )
            )

    return ProcessInterpretationOutcome(
        process_instances=process_instances,
        activities_discovered=len(activity_candidates),
        entity_types_considered=len(stats),
    )
