"""P3.xxE.4 (tests B/C/T, required): process interpretation must be
invariant to both DATASET-processing order and, per plan review
correction 2's row-order requirement, source-row order within a dataset
-- only real timestamp VALUES are ever consulted for sequencing, never
DataFrame row position.

Unlike test_entities_order_independence.py (which must run the full
AnalysisCase orchestration end-to-end because it needs genuine semantic
typing to produce entities in the first place), this test operates
directly on app.process.process_interpretation.interpret_process_for_case
with synthetic-but-realistic entity_candidates/decisions -- process
interpretation's own order-independence properties don't depend on the
semantic layer, so testing at this level directly and cheaply proves the
same invariant for the code this milestone actually wrote."""

import pandas as pd

from app.entities.entity_candidate import EntityCandidate, EntityObservation
from app.process.process_interpretation import (
    CaseDatasetProcessInput,
    ProcessInterpretationOutcome,
    interpret_process_for_case,
)
from app.semantic.candidate import InterpretationDecision


def _decision(
    field: str, concept: str, status: str = "auto_accepted", confidence: float = 0.9
) -> InterpretationDecision:
    return InterpretationDecision(
        source_dataset_id="ds",
        source_field=field,
        selected_concept=concept,
        confidence=confidence,
        status=status,
        evidence_summary=[],
        alternative_candidates=[],
        decision_source="deterministic",
        decision_version="v1",
    )


def _entity_candidates(work_order_ids: list[str]) -> list[EntityCandidate]:
    candidates = []
    for wo in work_order_ids:
        key = wo.lower()
        candidates.append(
            EntityCandidate(
                entity_type="WORK_ORDER",
                normalized_key=key,
                display_label=wo,
                resolution_method="exact_identifier",
                observations=[
                    EntityObservation(
                        analysis_case_dataset_id="cds1",
                        dataset_label="wo",
                        source_field="wo_id",
                        concept_code="work_order_id",
                        entity_type="WORK_ORDER",
                        raw_value=wo,
                        normalized_value=key,
                        semantic_confidence=0.95,
                        semantic_source="deterministic_confidence_engine",
                        human_validated=False,
                    )
                ],
                entity_type_confidence=0.9,
                entity_identity_confidence=0.9,
            )
        )
    return candidates


def _summary(outcome: ProcessInterpretationOutcome) -> set[tuple]:
    """Content-keyed comparison, never id/list-position based."""
    summary: set[tuple] = set()
    for instance in outcome.process_instances:
        activity_types = tuple(sorted(a.activity_type for a in instance.activities))
        edge_shape = tuple(
            sorted(
                (e.edge_type, e.status, round(e.precedence_confidence, 4)) for e in instance.edges
            )
        )
        summary.add(
            (instance.anchor_entity_id, activity_types, edge_shape, instance.boundary_status)
        )
    return summary


def _dataset_inputs(
    work_order_ids: list[str], row_order: list[int]
) -> list[CaseDatasetProcessInput]:
    scheduled = [f"2026-01-0{i}T08:00:00" for i in range(1, len(work_order_ids) + 1)]
    completed = [f"2026-01-0{i}T17:00:00" for i in range(1, len(work_order_ids) + 1)]
    df = (
        pd.DataFrame(
            {"wo_id": work_order_ids, "scheduled_at": scheduled, "completed_at": completed}
        )
        .iloc[row_order]
        .reset_index(drop=True)
    )
    decisions = [
        _decision("wo_id", "work_order_id"),
        _decision("scheduled_at", "scheduled_timestamp"),
        _decision("completed_at", "completed_timestamp"),
    ]
    return [
        CaseDatasetProcessInput(
            analysis_case_dataset_id="cds1",
            dataset_label="wo",
            dataset_role="event",
            decisions=decisions,
            raw_dataframe=df,
        )
    ]


def test_process_interpretation_is_invariant_to_row_order() -> None:
    work_order_ids = ["WO-1", "WO-2", "WO-3", "WO-4"]
    entity_candidates = _entity_candidates(work_order_ids)

    forward = interpret_process_for_case(
        _dataset_inputs(work_order_ids, [0, 1, 2, 3]), entity_candidates
    )
    reversed_rows = interpret_process_for_case(
        _dataset_inputs(work_order_ids, [3, 2, 1, 0]), entity_candidates
    )

    forward_summary = _summary(forward)
    reversed_summary = _summary(reversed_rows)
    assert forward_summary, "expected at least one process instance"
    assert forward_summary == reversed_summary, (
        f"process interpretation differed by source ROW order: "
        f"{forward_summary} vs {reversed_summary}"
    )
    assert forward.activities_discovered == reversed_rows.activities_discovered


def test_process_interpretation_is_invariant_to_dataset_order() -> None:
    work_order_ids = ["WO-1", "WO-2", "WO-3", "WO-4"]
    schedule_df = pd.DataFrame(
        {
            "wo_id": work_order_ids,
            "scheduled_at": [f"2026-01-0{i}T08:00:00" for i in range(1, 5)],
        }
    )
    complete_df = pd.DataFrame(
        {
            "wo_id": work_order_ids,
            "completed_at": [f"2026-01-0{i}T17:00:00" for i in range(1, 5)],
        }
    )
    schedule_input = CaseDatasetProcessInput(
        analysis_case_dataset_id="cds_sched",
        dataset_label="wo_schedule",
        dataset_role="event",
        decisions=[
            _decision("wo_id", "work_order_id"),
            _decision("scheduled_at", "scheduled_timestamp"),
        ],
        raw_dataframe=schedule_df,
    )
    complete_input = CaseDatasetProcessInput(
        analysis_case_dataset_id="cds_complete",
        dataset_label="wo_complete",
        dataset_role="event",
        decisions=[
            _decision("wo_id", "work_order_id"),
            _decision("completed_at", "completed_timestamp"),
        ],
        raw_dataframe=complete_df,
    )
    entity_candidates_multi = _entity_candidates(work_order_ids)
    for candidate in entity_candidates_multi:
        candidate.observations.append(
            EntityObservation(
                analysis_case_dataset_id="cds_complete",
                dataset_label="wo_complete",
                source_field="wo_id",
                concept_code="work_order_id",
                entity_type="WORK_ORDER",
                raw_value=candidate.display_label,
                normalized_value=candidate.normalized_key,
                semantic_confidence=0.95,
                semantic_source="deterministic_confidence_engine",
                human_validated=False,
            )
        )

    forward = interpret_process_for_case([schedule_input, complete_input], entity_candidates_multi)
    reversed_datasets = interpret_process_for_case(
        [complete_input, schedule_input], entity_candidates_multi
    )

    forward_summary = _summary(forward)
    reversed_summary = _summary(reversed_datasets)
    assert forward_summary, "expected at least one process instance"
    assert forward_summary == reversed_summary, (
        f"process interpretation differed by DATASET-processing order: "
        f"{forward_summary} vs {reversed_summary}"
    )
