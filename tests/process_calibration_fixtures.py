"""P3.xxE.4 section 37: hand-labeled process-interpretation calibration
fixtures. Mirrors entity_relationship_calibration_fixtures.py's own flat-
file convention.

Scoping note (deliberate, not an oversight): unlike E.3's calibration
benchmark -- which must run the REAL semantic interpreter end-to-end,
since entity TYPING is literally "did the semantic layer correctly
classify this field" -- E.4's interesting, testable logic is the
SEQUENCING/ACTIVITY-DISCOVERY behavior given ALREADY-CLASSIFIED semantic
decisions. These fixtures therefore construct InterpretationDecision/
EntityCandidate objects directly and drive
app.process.process_interpretation.interpret_process_for_case, exactly
the same semi-integration level as test_process_order_independence.py.
Re-certifying the semantic layer itself is E.1/E.1A/E.2's own job, not
E.4's.

Ten categories are attempted, matching spec section 37's own list. Two
(branching, true loop/rework beyond a simple 2-state cycle) have NO
mechanism this milestone that specifically detects them as a distinct
outcome from ORDER_UNRESOLVED/CONFLICTED -- honestly marked
NOT_AVAILABLE in the benchmark rather than fabricated.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from app.entities.entity_candidate import EntityCandidate, EntityObservation
from app.process.process_interpretation import CaseDatasetProcessInput
from app.semantic.candidate import InterpretationDecision


def _decision(
    field_name: str, concept: str, status: str = "auto_accepted", confidence: float = 0.9
) -> InterpretationDecision:
    return InterpretationDecision(
        source_dataset_id="ds",
        source_field=field_name,
        selected_concept=concept,
        confidence=confidence,
        status=status,
        evidence_summary=[],
        alternative_candidates=[],
        decision_source="deterministic",
        decision_version="v1",
    )


def _work_order_entities(ids: list[str], dataset_ids: list[str]) -> list[EntityCandidate]:
    candidates = []
    for wo in ids:
        key = wo.lower()
        candidates.append(
            EntityCandidate(
                entity_type="WORK_ORDER",
                normalized_key=key,
                display_label=wo,
                resolution_method="exact_identifier",
                observations=[
                    EntityObservation(
                        analysis_case_dataset_id=ds_id,
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
                    for ds_id in dataset_ids
                ],
                entity_type_confidence=0.9,
                entity_identity_confidence=0.9,
            )
        )
    return candidates


@dataclass(frozen=True)
class ProcessCalibrationCase:
    name: str
    dataset_inputs: list[CaseDatasetProcessInput]
    entity_candidates: list[EntityCandidate]
    # Expected (edge_type, status) pairs the run must contain at least one of.
    expected_edge_shapes: set[tuple[str, str]] = field(default_factory=set)
    expected_boundary_statuses: set[str] = field(default_factory=set)
    notes: str = ""


def _clear_sequence_case() -> ProcessCalibrationCase:
    """Category A: clear timestamps -> correct A->B precedence."""
    ids = [f"WO-{i}" for i in range(1, 6)]
    df = pd.DataFrame(
        {
            "wo_id": ids,
            "scheduled_at": [f"2026-01-0{i}T08:00:00" for i in range(1, 6)],
            "completed_at": [f"2026-01-0{i}T17:00:00" for i in range(1, 6)],
        }
    )
    decisions = [
        _decision("wo_id", "work_order_id"),
        _decision("scheduled_at", "scheduled_timestamp"),
        _decision("completed_at", "completed_timestamp"),
    ]
    dataset_input = CaseDatasetProcessInput(
        analysis_case_dataset_id="cds1",
        dataset_label="wo",
        dataset_role="event",
        decisions=decisions,
        raw_dataframe=df,
    )
    return ProcessCalibrationCase(
        name="clear_sequence",
        dataset_inputs=[dataset_input],
        entity_candidates=_work_order_entities(ids, ["cds1"]),
        expected_edge_shapes={("PRECEDES", "AUTO_ACCEPTED")},
        expected_boundary_statuses={"COMPLETE"},
        notes="test A: clear timestamps -> correct A->B precedence",
    )


def _missing_timestamp_case() -> ProcessCalibrationCase:
    """Category E: missing timestamp -> no fabricated order. Only one of
    the two temporal fields is ever populated -- no PRECEDES edge should
    exist at all (no comparable pair)."""
    ids = [f"WO-{i}" for i in range(1, 4)]
    df = pd.DataFrame(
        {"wo_id": ids, "scheduled_at": [f"2026-01-0{i}T08:00:00" for i in range(1, 4)]}
    )
    decisions = [
        _decision("wo_id", "work_order_id"),
        _decision("scheduled_at", "scheduled_timestamp"),
    ]
    dataset_input = CaseDatasetProcessInput(
        analysis_case_dataset_id="cds1",
        dataset_label="wo",
        dataset_role="event",
        decisions=decisions,
        raw_dataframe=df,
    )
    return ProcessCalibrationCase(
        name="missing_timestamp",
        dataset_inputs=[dataset_input],
        entity_candidates=_work_order_entities(ids, ["cds1"]),
        expected_edge_shapes=set(),  # no second activity type -> no edge at all
        notes="test E: missing timestamp -> never fabricates an order",
    )


def _contradictory_timestamps_case() -> ProcessCalibrationCase:
    """Category F: contradictory timestamps -> downgrade/conflict."""
    ids = [f"WO-{i}" for i in range(1, 5)]
    # Half the work orders show scheduled-before-completed, half the reverse.
    scheduled = [
        "2026-01-01T08:00:00",
        "2026-01-02T08:00:00",
        "2026-01-03T17:00:00",
        "2026-01-04T17:00:00",
    ]
    completed = [
        "2026-01-01T17:00:00",
        "2026-01-02T17:00:00",
        "2026-01-03T08:00:00",
        "2026-01-04T08:00:00",
    ]
    df = pd.DataFrame({"wo_id": ids, "scheduled_at": scheduled, "completed_at": completed})
    decisions = [
        _decision("wo_id", "work_order_id"),
        _decision("scheduled_at", "scheduled_timestamp"),
        _decision("completed_at", "completed_timestamp"),
    ]
    dataset_input = CaseDatasetProcessInput(
        analysis_case_dataset_id="cds1",
        dataset_label="wo",
        dataset_role="event",
        decisions=decisions,
        raw_dataframe=df,
    )
    return ProcessCalibrationCase(
        name="contradictory_timestamps",
        dataset_inputs=[dataset_input],
        entity_candidates=_work_order_entities(ids, ["cds1"]),
        expected_edge_shapes={("ORDER_UNRESOLVED", "CONFLICTED")},
        notes="test F: contradictory timestamps -> downgrade/conflict, never a silent winner",
    )


def _concurrent_events_case() -> ProcessCalibrationCase:
    """Category G: concurrent events -> no false sequence."""
    ids = [f"WO-{i}" for i in range(1, 4)]
    same_time = [f"2026-01-0{i}T12:00:00" for i in range(1, 4)]
    df = pd.DataFrame({"wo_id": ids, "scheduled_at": same_time, "completed_at": same_time})
    decisions = [
        _decision("wo_id", "work_order_id"),
        _decision("scheduled_at", "scheduled_timestamp"),
        _decision("completed_at", "completed_timestamp"),
    ]
    dataset_input = CaseDatasetProcessInput(
        analysis_case_dataset_id="cds1",
        dataset_label="wo",
        dataset_role="event",
        decisions=decisions,
        raw_dataframe=df,
    )
    return ProcessCalibrationCase(
        name="concurrent_events",
        dataset_inputs=[dataset_input],
        entity_candidates=_work_order_entities(ids, ["cds1"]),
        expected_edge_shapes={("CONCURRENT", "REVIEW_REQUIRED")},
        notes="test G: concurrent events -> CONCURRENT, never a fabricated PRECEDES",
    )


def _optional_step_case() -> ProcessCalibrationCase:
    """Category H: optional step -> optional not required. Only some work
    orders have an inspection timestamp alongside the always-present
    schedule/complete pair -- the process must not treat INSPECT as
    mandatory: every instance (with or without the optional inspection)
    must still reach the COMPLETE boundary off schedule/complete alone."""
    ids = [f"WO-{i}" for i in range(1, 5)]
    inspected_at = [
        "2026-01-01T12:00:00",
        None,  # WO-2 has no inspection step -- optional, not required
        "2026-01-03T12:00:00",
        None,  # WO-4 has no inspection step either
    ]
    df = pd.DataFrame(
        {
            "wo_id": ids,
            "scheduled_at": [f"2026-01-0{i}T08:00:00" for i in range(1, 5)],
            "inspected_at": inspected_at,
            "completed_at": [f"2026-01-0{i}T17:00:00" for i in range(1, 5)],
        }
    )
    decisions = [
        _decision("wo_id", "work_order_id"),
        _decision("scheduled_at", "scheduled_timestamp"),
        _decision("inspected_at", "event_timestamp"),
        _decision("completed_at", "completed_timestamp"),
    ]
    dataset_input = CaseDatasetProcessInput(
        analysis_case_dataset_id="cds1",
        dataset_label="wo",
        dataset_role="event",
        decisions=decisions,
        raw_dataframe=df,
    )
    return ProcessCalibrationCase(
        name="optional_step",
        dataset_inputs=[dataset_input],
        entity_candidates=_work_order_entities(ids, ["cds1"]),
        expected_edge_shapes={("PRECEDES", "AUTO_ACCEPTED")},
        expected_boundary_statuses={"COMPLETE"},
        notes="test H: optional step absent for some instances never blocks the COMPLETE boundary",
    )


def _unknown_boundary_case() -> ProcessCalibrationCase:
    """No opening/closing NAMED activity type at all (GENERIC only, via
    review_required tier) -> UNKNOWN, never fabricated COMPLETE. Distinct
    from partial_process (which has a real, non-boundary NAMED type)."""
    ids = [f"WO-{i}" for i in range(1, 4)]
    df = pd.DataFrame(
        {"wo_id": ids, "last_seen_at": [f"2026-01-0{i}T12:00:00" for i in range(1, 4)]}
    )
    decisions = [
        _decision("wo_id", "work_order_id"),
        _decision("last_seen_at", "event_timestamp", status="review_required", confidence=0.5),
    ]
    dataset_input = CaseDatasetProcessInput(
        analysis_case_dataset_id="cds1",
        dataset_label="wo",
        dataset_role="event",
        decisions=decisions,
        raw_dataframe=df,
    )
    return ProcessCalibrationCase(
        name="unknown_boundary",
        dataset_inputs=[dataset_input],
        entity_candidates=_work_order_entities(ids, ["cds1"]),
        expected_boundary_statuses={"UNKNOWN"},
        notes="REVIEW_REQUIRED-only evidence -> GENERIC-only activities -> UNKNOWN boundary",
    )


def _partial_process_case() -> ProcessCalibrationCase:
    """Category K: partial process -> PARTIAL/censored. No opening or
    closing activity type is ever observed."""
    ids = [f"WO-{i}" for i in range(1, 4)]
    df = pd.DataFrame(
        {"wo_id": ids, "inspected_at": [f"2026-01-0{i}T12:00:00" for i in range(1, 4)]}
    )
    decisions = [
        _decision("wo_id", "work_order_id"),
        _decision("inspected_at", "event_timestamp"),
    ]
    dataset_input = CaseDatasetProcessInput(
        analysis_case_dataset_id="cds1",
        dataset_label="wo",
        dataset_role="event",
        decisions=decisions,
        raw_dataframe=df,
    )
    return ProcessCalibrationCase(
        name="partial_process",
        dataset_inputs=[dataset_input],
        entity_candidates=_work_order_entities(ids, ["cds1"]),
        expected_boundary_statuses={"PARTIAL"},
        notes="test K: a real, non-boundary activity type -> PARTIAL, never a fabricated COMPLETE",
    )


def _state_sequence_case() -> ProcessCalibrationCase:
    """Category D: same-entity state sequence -> correct transitions."""
    df = pd.DataFrame(
        {
            "wo_id": ["WO-1", "WO-1", "WO-1"],
            "observed_at": ["2026-01-01T08:00:00", "2026-01-01T10:00:00", "2026-01-01T17:00:00"],
            "status": ["open", "in_progress", "completed"],
        }
    )
    decisions = [
        _decision("wo_id", "work_order_id"),
        _decision("observed_at", "event_timestamp"),
        _decision("status", "status"),
    ]
    dataset_input = CaseDatasetProcessInput(
        analysis_case_dataset_id="cds1",
        dataset_label="wo",
        dataset_role="event",
        decisions=decisions,
        raw_dataframe=df,
    )
    return ProcessCalibrationCase(
        name="state_sequence",
        dataset_inputs=[dataset_input],
        entity_candidates=_work_order_entities(["WO-1"], ["cds1"]),
        expected_edge_shapes={
            ("STATE_TRANSITION", "AUTO_ACCEPTED"),
        },
        notes="test D: same-entity state sequence -> correct OPEN->IN_PROGRESS->COMPLETED",
    )


CALIBRATION_CASES: list[ProcessCalibrationCase] = [
    _clear_sequence_case(),
    _missing_timestamp_case(),
    _contradictory_timestamps_case(),
    _concurrent_events_case(),
    _optional_step_case(),
    _partial_process_case(),
    _unknown_boundary_case(),
    _state_sequence_case(),
]

# Spec section 37 categories with NO distinct mechanism this milestone --
# branching (test I) and true multi-step loop/rework (test J) beyond a
# simple two-node cycle both collapse into ORDER_UNRESOLVED/CONFLICTED
# rather than a dedicated OPTIONAL_BRANCH/LOOP classification (those edge
# types are forward-declared in app/process/activity_type.py but
# unreachable this milestone, matching relationship_type.py's own
# documented "some values forward-declared" precedent). Multiple-anchor
# scenarios (test M-adjacent) ARE exercised implicitly by every multi-
# work-order fixture above (one process instance per anchor entity).
NOT_AVAILABLE_CATEGORIES = ("branching", "loop_rework_beyond_two_state_cycle")
