from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from app.entities.identifier_normalization import normalize_identifier
from app.process.activity_candidate import ActivityCandidate, ActivityObservation
from app.process.activity_type import ActivityType
from app.process.activity_type_inference import infer_activity_type
from app.process.state_normalization import normalize_state_value
from app.semantic.candidate import InterpretationDecision

_STATUS_TIER_RANK = {
    "human_confirmed": 4,
    "human_corrected": 4,
    "auto_accepted": 3,
    "accepted_with_flag": 2,
    "review_required": 1,
    "unresolved": 0,
}

# ---------------------------------------------------------------------------
# P3.xxE.4 sections 6/8/13 + plan review correction 2: builds
# ActivityObservations from per-dataset semantic decisions and raw
# dataframes. A bare temporal-concept field is NEVER sufficient on its own
# to spawn an activity observation -- at least one corroborating signal
# (see _corroboration_signals) is required. Entity attachment REUSES
# P3.xxE.3's own resolved entities (via entity_lookup_by_field, built by
# the caller from already-persisted CanonicalCaseEntity/observation data)
# -- this module never re-resolves or rewrites entity identity
# (Invariant E: E.3 canonical entity identity is not rewritten).
# ---------------------------------------------------------------------------

_REFERENCE_DATASET_ROLES = frozenset({"master", "reference"})
_TEMPORAL_CONCEPTS = frozenset({"event_timestamp", "scheduled_timestamp", "completed_timestamp"})
_INHERENTLY_OPERATIONAL_TEMPORAL_CONCEPTS = frozenset(
    {"completed_timestamp", "scheduled_timestamp"}
)
_STATE_CONCEPT = "status"


@dataclass(frozen=True)
class DatasetActivityInput:
    analysis_case_dataset_id: str
    dataset_label: str
    dataset_role: str
    decisions: list[InterpretationDecision]
    raw_dataframe: pd.DataFrame
    # source_field -> {normalized_value -> (entity_type, canonical_key)},
    # built by the caller from entities ALREADY resolved by P3.xxE.3 in
    # this dataset -- never re-resolved here.
    entity_lookup_by_field: dict[str, dict[str, tuple[str, str]]]


def _corroboration_signals(
    *,
    concept_code: str,
    dataset_role: str,
    has_cooccurring_status_field: bool,
    has_grain_entity_field: bool,
) -> list[str]:
    """Plan review correction 2: the generic, computable gate. A bare
    timestamp with an empty signal list here is never persisted as an
    activity -- see discover_activity_observations."""
    signals: list[str] = []
    if dataset_role not in _REFERENCE_DATASET_ROLES and dataset_role != "unknown":
        signals.append("event_shaped_dataset_role")
    if has_cooccurring_status_field:
        signals.append("cooccurring_status_field")
    if has_grain_entity_field:
        signals.append("cooccurring_entity_grain_field")
    if concept_code in _INHERENTLY_OPERATIONAL_TEMPORAL_CONCEPTS:
        signals.append("inherently_operational_temporal_concept")
    return signals


def _lookup_primary_entity(
    row: pd.Series, entity_lookup_by_field: dict[str, dict[str, tuple[str, str]]]
) -> tuple[str | None, str | None]:
    for field_name, lookup in entity_lookup_by_field.items():
        if field_name not in row.index:
            continue
        raw_val = row[field_name]
        if pd.isna(raw_val):
            continue
        match = lookup.get(normalize_identifier(raw_val))
        if match is not None:
            entity_type, canonical_key = match
            return canonical_key, entity_type
    return None, None


def discover_temporal_observations(
    dataset_input: DatasetActivityInput,
) -> list[ActivityObservation]:
    temporal_decisions = [
        d for d in dataset_input.decisions if d.selected_concept in _TEMPORAL_CONCEPTS
    ]
    if not temporal_decisions:
        return []

    has_status_field = any(d.selected_concept == _STATE_CONCEPT for d in dataset_input.decisions)
    has_grain_entity_field = bool(dataset_input.entity_lookup_by_field)

    observations: list[ActivityObservation] = []
    for decision in temporal_decisions:
        concept_code = decision.selected_concept
        if concept_code is None or decision.source_field not in dataset_input.raw_dataframe.columns:
            continue

        signals = _corroboration_signals(
            concept_code=concept_code,
            dataset_role=dataset_input.dataset_role,
            has_cooccurring_status_field=has_status_field,
            has_grain_entity_field=has_grain_entity_field,
        )
        if not signals:
            continue

        parsed = pd.to_datetime(
            dataset_input.raw_dataframe[decision.source_field], errors="coerce", format="mixed"
        )
        for idx in dataset_input.raw_dataframe.index:
            raw_ts = parsed.loc[idx]
            if pd.isna(raw_ts):
                continue
            row = dataset_input.raw_dataframe.loc[idx]
            primary_entity_id, primary_entity_type = _lookup_primary_entity(
                row, dataset_input.entity_lookup_by_field
            )
            occurred_at = raw_ts.to_pydatetime()
            observations.append(
                ActivityObservation(
                    analysis_case_dataset_id=dataset_input.analysis_case_dataset_id,
                    dataset_label=dataset_input.dataset_label,
                    dataset_role=dataset_input.dataset_role,
                    source_field=decision.source_field,
                    concept_code=concept_code,
                    semantic_status=decision.status,
                    semantic_confidence=decision.confidence,
                    primary_entity_id=primary_entity_id,
                    primary_entity_type=primary_entity_type,
                    occurred_at=occurred_at,
                    occurred_at_precision="exact",
                    timezone_source="source_provided" if occurred_at.tzinfo else "unspecified",
                    raw_state_value=None,
                    corroboration_signals=signals,
                    is_explicit_event=(dataset_input.dataset_role == "event"),
                )
            )
    return observations


def discover_state_observations(dataset_input: DatasetActivityInput) -> list[ActivityObservation]:
    """Status-concept observations require an attachable entity (a state
    with no subject is not useful process evidence) but are not subject
    to correction 2's temporal-corroboration gate -- a status value is
    itself already meaningful entity-lifecycle evidence, not a bare
    timestamp."""
    state_decisions = [d for d in dataset_input.decisions if d.selected_concept == _STATE_CONCEPT]
    if not state_decisions or not dataset_input.entity_lookup_by_field:
        return []

    # A state observation borrows a same-row timestamp (if any temporal
    # concept is ALSO present in this dataset) purely as a time anchor for
    # later sequencing -- this does not spawn a temporal activity of its
    # own and is not subject to correction 2's corroboration gate, since
    # the state observation's OWN existence-evidence is the status value
    # itself, not the borrowed timestamp.
    anchor_fields = [
        d.source_field
        for d in dataset_input.decisions
        if d.selected_concept in _TEMPORAL_CONCEPTS
        and d.source_field in dataset_input.raw_dataframe.columns
    ]
    anchor_parsed = {
        field_name: pd.to_datetime(
            dataset_input.raw_dataframe[field_name], errors="coerce", format="mixed"
        )
        for field_name in anchor_fields
    }

    observations: list[ActivityObservation] = []
    for decision in state_decisions:
        if decision.source_field not in dataset_input.raw_dataframe.columns:
            continue
        for idx in dataset_input.raw_dataframe.index:
            row = dataset_input.raw_dataframe.loc[idx]
            raw_val = row[decision.source_field]
            if pd.isna(raw_val):
                continue
            primary_entity_id, primary_entity_type = _lookup_primary_entity(
                row, dataset_input.entity_lookup_by_field
            )
            if primary_entity_id is None:
                continue

            occurred_at = None
            for field_name in anchor_fields:
                candidate_ts = anchor_parsed[field_name].loc[idx]
                if not pd.isna(candidate_ts):
                    occurred_at = candidate_ts.to_pydatetime()
                    break

            observations.append(
                ActivityObservation(
                    analysis_case_dataset_id=dataset_input.analysis_case_dataset_id,
                    dataset_label=dataset_input.dataset_label,
                    dataset_role=dataset_input.dataset_role,
                    source_field=decision.source_field,
                    concept_code=_STATE_CONCEPT,
                    semantic_status=decision.status,
                    semantic_confidence=decision.confidence,
                    primary_entity_id=primary_entity_id,
                    primary_entity_type=primary_entity_type,
                    occurred_at=occurred_at,
                    occurred_at_precision="exact" if occurred_at else "unknown",
                    timezone_source="unspecified",
                    raw_state_value=str(raw_val),
                    corroboration_signals=["cooccurring_entity_grain_field"],
                    is_explicit_event=False,
                )
            )
    return observations


def _best_status_and_confidence(observations: list[ActivityObservation]) -> tuple[str, float]:
    best = max(
        observations,
        key=lambda o: (_STATUS_TIER_RANK.get(o.semantic_status, 0), o.semantic_confidence),
    )
    return best.semantic_status, best.semantic_confidence


def _existence_confidence(
    signals: set[str], distinct_dataset_count: int, base: float = 0.5
) -> float:
    return round(min(base + 0.1 * len(signals) + 0.1 * (distinct_dataset_count - 1), 0.95), 4)


def _temporal_confidence_for_activity(
    occurred_at: object, precision: str, distinct_dataset_count: int
) -> float:
    if occurred_at is None:
        return 0.0
    base = 0.7 if precision == "exact" else 0.4
    return round(min(base + 0.05 * (distinct_dataset_count - 1), 0.95), 4)


def assemble_activity_candidates(
    observations: list[ActivityObservation],
) -> list[ActivityCandidate]:
    """Groups observations into deduplicated ActivityCandidates -- flat,
    order-independent grouping by (entity, concept, value/time), never by
    dataset-processing order. Temporal observations key on
    (entity, concept, occurred_at) so cross-dataset corroboration of the
    SAME real event merges into one candidate; state observations key on
    (entity, concept, raw_state_value) so repeated corroborating
    observations of the same status merge, never duplicate."""
    temporal_groups: dict[tuple[str, str, datetime], list[ActivityObservation]] = {}
    state_groups: dict[tuple[str, str, str], list[ActivityObservation]] = {}

    for obs in observations:
        if obs.primary_entity_id is None:
            continue
        if obs.concept_code == _STATE_CONCEPT:
            state_key = (obs.primary_entity_id, obs.concept_code, obs.raw_state_value or "")
            state_groups.setdefault(state_key, []).append(obs)
        elif obs.occurred_at is not None:
            temporal_key = (obs.primary_entity_id, obs.concept_code, obs.occurred_at)
            temporal_groups.setdefault(temporal_key, []).append(obs)

    candidates: list[ActivityCandidate] = []

    for (entity_id, concept_code, occurred_at), group in temporal_groups.items():
        distinct_datasets = {o.analysis_case_dataset_id for o in group}
        signals: set[str] = set()
        for o in group:
            signals.update(o.corroboration_signals)
        status, confidence = _best_status_and_confidence(group)
        is_corroborated = len(distinct_datasets) >= 2
        activity_type, type_confidence = infer_activity_type(
            machine_status=status,
            concept_code=concept_code,
            machine_confidence=confidence,
            is_independently_corroborated=is_corroborated,
        )
        existence_confidence = _existence_confidence(signals, len(distinct_datasets))
        temporal_confidence = _temporal_confidence_for_activity(
            occurred_at, group[0].occurred_at_precision, len(distinct_datasets)
        )
        activity_confidence = round(
            0.35 * existence_confidence
            + 0.25 * type_confidence
            + 0.25 * temporal_confidence
            + 0.15 * 0.0,
            4,
        )
        candidates.append(
            ActivityCandidate(
                activity_type=activity_type,
                activity_label=None,
                state_value=None,
                primary_entity_id=entity_id,
                primary_entity_type=group[0].primary_entity_type,
                observations=group,
                activity_type_confidence=type_confidence,
                activity_existence_confidence=existence_confidence,
                temporal_confidence=temporal_confidence,
                participation_confidence=0.0,
                activity_confidence=activity_confidence,
                state_existence_confidence=0.0,
                state_meaning_confidence=0.0,
                temporal_evidence_tier="STRONG" if len(distinct_datasets) >= 2 else "WEAK",
                occurred_at=occurred_at,
                occurred_at_precision=group[0].occurred_at_precision,
                timezone_source=group[0].timezone_source,
                is_explicit_event=any(o.is_explicit_event for o in group),
                corroboration_signals=sorted(signals),
                alternative_activity_types=[],
                participation=[],
                evidence_summary=[
                    f"{len(group)} observation(s) across {len(distinct_datasets)} dataset(s) "
                    f"for concept {concept_code!r}, corroboration: {sorted(signals)}"
                ],
            )
        )

    for (entity_id, concept_code, raw_state_value), group in state_groups.items():
        distinct_datasets = {o.analysis_case_dataset_id for o in group}
        status, confidence = _best_status_and_confidence(group)
        is_corroborated = len(distinct_datasets) >= 2
        state_value, state_existence_confidence, state_meaning_confidence = normalize_state_value(
            raw_value=raw_state_value,
            machine_status=status,
            machine_confidence=confidence,
            is_independently_corroborated=is_corroborated,
        )
        state_occurred_at = next((o.occurred_at for o in group if o.occurred_at is not None), None)
        temporal_confidence = _temporal_confidence_for_activity(
            state_occurred_at, "exact" if state_occurred_at else "unknown", len(distinct_datasets)
        )
        existence_confidence = _existence_confidence(
            {"cooccurring_entity_grain_field"}, len(distinct_datasets)
        )
        activity_confidence = round(
            0.4 * existence_confidence + 0.4 * state_meaning_confidence + 0.2 * temporal_confidence,
            4,
        )
        candidates.append(
            ActivityCandidate(
                activity_type=ActivityType.GENERIC.value,
                activity_label=None,
                state_value=state_value,
                primary_entity_id=entity_id,
                primary_entity_type=group[0].primary_entity_type,
                observations=group,
                activity_type_confidence=0.0,
                activity_existence_confidence=existence_confidence,
                temporal_confidence=temporal_confidence,
                participation_confidence=0.0,
                activity_confidence=activity_confidence,
                state_existence_confidence=state_existence_confidence,
                state_meaning_confidence=state_meaning_confidence,
                temporal_evidence_tier="WEAK" if state_occurred_at else "NONE",
                occurred_at=state_occurred_at,
                occurred_at_precision="exact" if state_occurred_at else "unknown",
                timezone_source="unspecified",
                is_explicit_event=False,
                corroboration_signals=["cooccurring_entity_grain_field"],
                alternative_activity_types=[],
                participation=[],
                evidence_summary=[
                    f"{len(group)} observation(s) across {len(distinct_datasets)} dataset(s) "
                    f"for state value {raw_state_value!r}"
                ],
            )
        )

    return candidates
