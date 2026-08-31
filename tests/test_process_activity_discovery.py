"""P3.xxE.4 plan review correction 2: a timestamp is evidence of time, not
automatically an operational activity. Requires >=1 corroborating signal
alongside any temporal observation before an ActivityCandidate is
created."""

import pandas as pd

from app.process.activity_discovery import (
    DatasetActivityInput,
    assemble_activity_candidates,
    discover_state_observations,
    discover_temporal_observations,
)
from app.semantic.candidate import InterpretationDecision


def _decision(
    field: str, concept: str, status: str = "auto_accepted", confidence: float = 0.9
) -> InterpretationDecision:
    return InterpretationDecision(
        source_dataset_id="ds1",
        source_field=field,
        selected_concept=concept,
        confidence=confidence,
        status=status,
        evidence_summary=[],
        alternative_candidates=[],
        decision_source="deterministic",
        decision_version="v1",
    )


def _entity_lookup() -> dict[str, dict[str, tuple[str, str]]]:
    return {"wo_id": {"wo-1": ("WORK_ORDER", "wo-1"), "wo-2": ("WORK_ORDER", "wo-2")}}


def test_uncorroborated_audit_timestamp_never_produces_an_activity() -> None:
    """Correction 2's required test: a bare last_updated_timestamp-style
    column with no event-shaped dataset role, no co-occurring status
    field, and no entity-grain field never spawns a fabricated activity."""
    df = pd.DataFrame({"last_updated_at": ["2026-01-01T00:00:00", "2026-01-02T00:00:00"]})
    decisions = [_decision("last_updated_at", "event_timestamp")]
    dataset_input = DatasetActivityInput(
        analysis_case_dataset_id="cds1",
        dataset_label="audit_log",
        dataset_role="reference",  # not event-shaped, no entity lookup, no status field
        decisions=decisions,
        raw_dataframe=df,
        entity_lookup_by_field={},
    )
    observations = discover_temporal_observations(dataset_input)
    assert observations == []


def test_event_shaped_role_alone_is_a_sufficient_corroborating_signal() -> None:
    df = pd.DataFrame({"wo_id": ["wo-1"], "completed_at": ["2026-01-01T17:00:00"]})
    decisions = [
        _decision("wo_id", "work_order_id"),
        _decision("completed_at", "completed_timestamp"),
    ]
    dataset_input = DatasetActivityInput(
        analysis_case_dataset_id="cds1",
        dataset_label="wo_completions",
        dataset_role="event",
        decisions=decisions,
        raw_dataframe=df,
        entity_lookup_by_field=_entity_lookup(),
    )
    observations = discover_temporal_observations(dataset_input)
    assert len(observations) == 1
    assert observations[0].corroboration_signals != []


def test_master_role_alone_is_not_event_shaped() -> None:
    # event_timestamp is deliberately the ambiguous alias set (correction
    # 2) -- it does NOT self-corroborate the way completed_timestamp/
    # scheduled_timestamp do, so a master-role dataset with no other
    # signal must produce nothing.
    df = pd.DataFrame({"last_seen_at": ["2026-01-01T08:00:00"]})
    decisions = [_decision("last_seen_at", "event_timestamp")]
    dataset_input = DatasetActivityInput(
        analysis_case_dataset_id="cds1",
        dataset_label="master_ref",
        dataset_role="master",
        decisions=decisions,
        raw_dataframe=df,
        entity_lookup_by_field={},
    )
    observations = discover_temporal_observations(dataset_input)
    assert observations == []


def test_inherently_operational_concept_corroborates_even_in_unknown_role_dataset() -> None:
    df = pd.DataFrame({"completed_at": ["2026-01-01T17:00:00"]})
    decisions = [_decision("completed_at", "completed_timestamp")]
    dataset_input = DatasetActivityInput(
        analysis_case_dataset_id="cds1",
        dataset_label="unlabeled",
        dataset_role="unknown",
        decisions=decisions,
        raw_dataframe=df,
        entity_lookup_by_field={},
    )
    observations = discover_temporal_observations(dataset_input)
    assert len(observations) == 1
    assert "inherently_operational_temporal_concept" in observations[0].corroboration_signals


def test_state_observations_require_an_attachable_entity() -> None:
    df = pd.DataFrame({"status": ["completed"]})
    decisions = [_decision("status", "status", status="review_required", confidence=0.5)]
    dataset_input = DatasetActivityInput(
        analysis_case_dataset_id="cds1",
        dataset_label="wo_status",
        dataset_role="event",
        decisions=decisions,
        raw_dataframe=df,
        entity_lookup_by_field={},  # no entity lookup -> no attachable entity
    )
    observations = discover_state_observations(dataset_input)
    assert observations == []


def test_assemble_activity_candidates_deduplicates_repeated_observations() -> None:
    df = pd.DataFrame({"wo_id": ["wo-1", "wo-2"], "completed_at": ["2026-01-01T17:00:00"] * 2})
    decisions = [
        _decision("wo_id", "work_order_id"),
        _decision("completed_at", "completed_timestamp"),
    ]
    dataset_input = DatasetActivityInput(
        analysis_case_dataset_id="cds1",
        dataset_label="wo_completions",
        dataset_role="event",
        decisions=decisions,
        raw_dataframe=df,
        entity_lookup_by_field={
            "wo_id": {"wo-1": ("WORK_ORDER", "wo-1"), "wo-2": ("WORK_ORDER", "wo-2")}
        },
    )
    observations = discover_temporal_observations(dataset_input)
    candidates = assemble_activity_candidates(observations)
    # Two distinct entities (wo-1, wo-2) -> two distinct candidates, never merged.
    assert len(candidates) == 2
    assert {c.primary_entity_id for c in candidates} == {"wo-1", "wo-2"}
