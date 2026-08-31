"""P3.xxE.4 section 37: the validation-only process-interpretation
calibration benchmark. Runs each hand-labeled case
(tests/process_calibration_fixtures.py) through the REAL production
app.process.process_interpretation.interpret_process_for_case, then
checks the resulting process instances against hand-written expectations.

This file lives entirely under tests/ -- no app/ module imports it, and
it imports nothing from app.ground_truth_validation."""

from process_calibration_fixtures import (
    CALIBRATION_CASES,
    NOT_AVAILABLE_CATEGORIES,
    ProcessCalibrationCase,
)

from app.process.process_interpretation import (
    ProcessInterpretationOutcome,
    interpret_process_for_case,
)


def _run(case: ProcessCalibrationCase) -> ProcessInterpretationOutcome:
    return interpret_process_for_case(case.dataset_inputs, case.entity_candidates)


def test_calibration_cases_produce_the_expected_edge_shapes() -> None:
    failures = []
    for case in CALIBRATION_CASES:
        outcome = _run(case)
        observed_shapes = {
            (e.edge_type, e.status) for inst in outcome.process_instances for e in inst.edges
        }
        if case.expected_edge_shapes and not (case.expected_edge_shapes & observed_shapes):
            failures.append(
                f"{case.name}: expected one of {case.expected_edge_shapes}, "
                f"observed {observed_shapes} ({case.notes})"
            )
        if not case.expected_edge_shapes and observed_shapes:
            failures.append(
                f"{case.name}: expected NO edges, observed {observed_shapes} ({case.notes})"
            )
    assert not failures, "\n".join(failures)


def test_calibration_cases_produce_the_expected_boundary_statuses() -> None:
    failures = []
    for case in CALIBRATION_CASES:
        if not case.expected_boundary_statuses:
            continue
        outcome = _run(case)
        observed = {inst.boundary_status for inst in outcome.process_instances}
        if not (case.expected_boundary_statuses & observed):
            failures.append(
                f"{case.name}: expected one of {case.expected_boundary_statuses}, "
                f"observed {observed} ({case.notes})"
            )
    assert not failures, "\n".join(failures)


def test_contradictory_case_never_picks_a_silent_winner() -> None:
    """Direct, single-case proof mirroring E.3's own
    test_calibration_conflicting_case_never_picks_a_silent_winner: every
    edge in the deliberately contradictory fixture must land CONFLICTED/
    ORDER_UNRESOLVED, never a fabricated PRECEDES direction."""
    case = next(c for c in CALIBRATION_CASES if c.name == "contradictory_timestamps")
    outcome = _run(case)
    edges = [e for inst in outcome.process_instances for e in inst.edges]
    assert edges, "expected the contradictory fixture to produce at least one edge"
    for edge in edges:
        assert edge.status == "CONFLICTED", f"expected CONFLICTED, got {edge.status}"
        assert edge.edge_type == "ORDER_UNRESOLVED"


def test_multiple_anchor_instances_are_each_independently_scored() -> None:
    """Multiple-anchor scenario: every work order in the clear_sequence
    fixture becomes its OWN process instance, each independently scored
    -- never collapsed into one aggregate row."""
    case = next(c for c in CALIBRATION_CASES if c.name == "clear_sequence")
    outcome = _run(case)
    assert len(outcome.process_instances) == len(case.entity_candidates)
    anchor_ids = {inst.anchor_entity_id for inst in outcome.process_instances}
    assert len(anchor_ids) == len(case.entity_candidates)


def test_not_available_categories_are_explicitly_documented_not_fabricated() -> None:
    """Branching and multi-step loop/rework have no dedicated detection
    mechanism this milestone -- honestly absent from CALIBRATION_CASES
    rather than fabricated with a fake passing assertion."""
    assert NOT_AVAILABLE_CATEGORIES == ("branching", "loop_rework_beyond_two_state_cycle")
    case_names = {c.name for c in CALIBRATION_CASES}
    assert "branching" not in case_names
