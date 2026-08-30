"""P3.xxE.2 section 27/required correction: the validation-only semantic
calibration benchmark. Runs each hand-labeled fixture
(tests/semantic_calibration_fixtures.py) through the REAL, production
interpret_dataset()/AnalysisCase orchestration pipeline, then compares
persisted results against the hand-written expectations to compute
SEMANTIC_FIELD_ACCURACY / HIGH_CONFIDENCE_SEMANTIC_ACCURACY /
FALSE_AUTO_ACCEPT_RATE / FALSE_UNRESOLVED_RATE / DATASET_ROLE_ACCURACY.

This file lives entirely under tests/ -- no app/ module imports it, and it
imports nothing from app.ground_truth_validation (see
tests/test_validation_import_boundary.py, which this file's own imports
are also subject to via ast-scanning of production modules only -- this
file itself is test code, outside that scan's scope by design)."""

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from semantic_calibration_fixtures import CALIBRATION_FIXTURES, CalibrationFixture
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.semantic import SemanticInterpretationDecision, SemanticRoleInterpretation
from app.schemas.contracts import OrganizationCreate
from app.services.analysis_case_orchestration_service import analysis_case_orchestration_service
from app.services.analysis_case_service import AnalysisCaseService, UploadedFile
from app.services.organization_service import OrganizationService
from app.storage.local_storage import LocalFileStorage


@dataclass
class _CalibrationResult:
    field_decisions: list[SemanticInterpretationDecision]
    role: SemanticRoleInterpretation | None
    fixture: CalibrationFixture


def _run_fixture(db: Session, tmp_path: Path, fixture: CalibrationFixture) -> _CalibrationResult:
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    org = OrganizationService().create(
        db,
        OrganizationCreate(
            name=fixture.name.replace("_", " ").title(),
            slug=f"calib-{fixture.name}".replace("_", "-"),
            country_code="US",
            default_currency="USD",
            timezone="UTC",
        ),
    )
    actor = uuid4()
    case = service.create(db, org.id, "Calibration Case", "single", actor)
    csv_bytes = fixture.dataframe.to_csv(index=False).encode("utf-8")
    service.register_artifacts(
        db, org.id, case.id, [UploadedFile(fixture.filename, csv_bytes)], actor
    )
    run = analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org.id, case.id, run.id, actor)

    decisions = list(
        db.scalars(
            select(SemanticInterpretationDecision).where(
                SemanticInterpretationDecision.run_id == run.id
            )
        ).all()
    )
    role = db.scalar(
        select(SemanticRoleInterpretation).where(SemanticRoleInterpretation.run_id == run.id)
    )
    return _CalibrationResult(field_decisions=decisions, role=role, fixture=fixture)


def _compute_metrics(results: list[_CalibrationResult]) -> dict[str, float | None]:
    fields_with_expected = 0
    fields_correct = 0
    high_confidence_fields_with_expected = 0
    high_confidence_correct = 0
    auto_accepted_total = 0
    auto_accepted_wrong = 0
    unresolved_denominator = 0
    false_unresolved = 0
    datasets_with_expected_role = 0
    correct_roles = 0

    for result in results:
        expected_concepts = result.fixture.expected_field_concepts
        decisions_by_field = {d.source_field: d for d in result.field_decisions}

        if result.role is not None:
            datasets_with_expected_role += 1
            if result.role.primary_role == result.fixture.expected_dataset_role:
                correct_roles += 1

        for field_name, expected_concept in expected_concepts.items():
            decision = decisions_by_field.get(field_name)
            if decision is None:
                continue

            if decision.status == "auto_accepted":
                auto_accepted_total += 1
                if decision.selected_concept != expected_concept:
                    auto_accepted_wrong += 1

            if expected_concept is not None:
                fields_with_expected += 1
                if decision.selected_concept == expected_concept:
                    fields_correct += 1
                if decision.status in {"auto_accepted", "accepted_with_flag"}:
                    high_confidence_fields_with_expected += 1
                    if decision.selected_concept == expected_concept:
                        high_confidence_correct += 1

                unresolved_denominator += 1
                if decision.status == "unresolved":
                    false_unresolved += 1

    return {
        "SEMANTIC_FIELD_ACCURACY": (
            fields_correct / fields_with_expected if fields_with_expected else None
        ),
        "HIGH_CONFIDENCE_SEMANTIC_ACCURACY": (
            high_confidence_correct / high_confidence_fields_with_expected
            if high_confidence_fields_with_expected
            else None
        ),
        "FALSE_AUTO_ACCEPT_RATE": (
            auto_accepted_wrong / auto_accepted_total if auto_accepted_total else None
        ),
        "FALSE_UNRESOLVED_RATE": (
            false_unresolved / unresolved_denominator if unresolved_denominator else None
        ),
        "DATASET_ROLE_ACCURACY": (
            correct_roles / datasets_with_expected_role if datasets_with_expected_role else None
        ),
    }


def test_calibration_benchmark_computes_all_five_metrics(db: Session, tmp_path: Path) -> None:
    results = [_run_fixture(db, tmp_path, fixture) for fixture in CALIBRATION_FIXTURES]
    metrics = _compute_metrics(results)

    # FALSE_AUTO_ACCEPT_RATE is legitimately N/A (not a fabricated 0.0) in
    # this small fixture set: none of the fixture's foreign-key-shaped
    # columns (repeating values, uniqueness < 0.95) qualify as
    # is_candidate_identifier, so none reach the datatype-compatibility
    # evidence needed to clear the 0.90 auto_accept threshold at all --
    # there are zero AUTO_ACCEPTED decisions to measure correctness of.
    # Per spec section 2: report NOT_AVAILABLE, never fabricate zero.
    for metric_name, value in metrics.items():
        if metric_name == "FALSE_AUTO_ACCEPT_RATE":
            continue
        assert value is not None, f"{metric_name} should be computable from the fixture set"

    assert metrics["DATASET_ROLE_ACCURACY"] == 1.0
    if metrics["FALSE_AUTO_ACCEPT_RATE"] is not None:
        assert metrics["FALSE_AUTO_ACCEPT_RATE"] == 0.0


def test_calibration_never_auto_accepts_the_intentionally_ambiguous_field(
    db: Session, tmp_path: Path
) -> None:
    ambiguous_fixture = next(f for f in CALIBRATION_FIXTURES if f.name == "ambiguous_amount")
    result = _run_fixture(db, tmp_path, ambiguous_fixture)
    amount_decision = next(d for d in result.field_decisions if d.source_field == "amount")
    assert amount_decision.status != "auto_accepted"


def test_calibration_intentionally_unresolvable_fields_are_recorded_as_such(
    db: Session, tmp_path: Path
) -> None:
    """Fields with expected_field_concepts[field] is None should genuinely
    reflect real, honest engine behavior -- this test documents (not
    asserts a hard requirement on) what the engine currently does with
    them, so a future E.2 iteration's regression is visible here."""
    work_order_fixture = next(
        f for f in CALIBRATION_FIXTURES if f.name == "work_order_unfamiliar_aliases"
    )
    result = _run_fixture(db, tmp_path, work_order_fixture)
    decisions_by_field = {d.source_field: d for d in result.field_decisions}
    batch_code_decision = decisions_by_field["internal_batch_code"]
    # A proprietary internal code should never be auto-accepted to
    # anything -- that would be a genuine false-positive semantic claim.
    assert batch_code_decision.status != "auto_accepted"
