"""P3.xxE.1A: SemanticReviewService transition tests -- confirm, correct,
reject, mark_unresolved, revisit transitions, stale-version conflicts,
and immutability of historical rows. Uses a real AnalysisCase run (same
pattern as tests/test_analysis_case_semantic_orchestration.py) so the
SemanticInterpretationDecision rows under review are genuine, not
hand-built fixtures."""

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.entities import Organization
from app.models.semantic import SemanticInterpretationDecision
from app.models.semantic_review import SemanticDecisionVersion
from app.schemas.contracts import OrganizationCreate
from app.services.analysis_case_orchestration_service import analysis_case_orchestration_service
from app.services.analysis_case_service import AnalysisCaseService, UploadedFile
from app.services.organization_service import OrganizationService
from app.services.semantic_review_service import (
    SemanticReviewServiceError,
    semantic_review_service,
)
from app.storage.local_storage import LocalFileStorage

MAINT_CSV = (
    b"asset_id,failure_code,downtime_hours,repair_cost,event_date\n"
    b"V1,brake,4,10000,2026-08-01T08:00:00\n"
    b"V1,brake,5,11000,2026-08-05T08:00:00\n"
    b"V1,brake,6,12000,2026-08-10T08:00:00\n"
)


def _organization(db: Session, slug: str) -> Organization:
    return OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug.title(), slug=slug, country_code="US", default_currency="USD", timezone="UTC"
        ),
    )


def _run_case(db: Session, tmp_path: Path, slug: str) -> tuple[UUID, UUID]:
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    org = _organization(db, slug)
    actor = uuid4()
    case = service.create(db, org.id, "Case", "single", actor)
    service.register_artifacts(
        db, org.id, case.id, [UploadedFile("maintenance_events.csv", MAINT_CSV)], actor
    )
    run = analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org.id, case.id, run.id, actor)
    return org.id, run.id


def _decision(db: Session, run_id: UUID, source_field: str) -> SemanticInterpretationDecision:
    decision = db.scalar(
        select(SemanticInterpretationDecision).where(
            SemanticInterpretationDecision.run_id == run_id,
            SemanticInterpretationDecision.source_field == source_field,
        )
    )
    assert decision is not None
    return decision


def _force_status(db: Session, decision_id: UUID, status: str, confidence: float) -> None:
    """Test-only: directly set a machine decision's status/confidence to
    exercise a specific queue bucket, mirroring how confidence-threshold
    boundaries would naturally place a real field there. This never
    touches the review/version tables' immutability guard -- only the
    SemanticInterpretationDecision row, which P3.xxE.1 already documents
    as recomputed fresh (not itself immutable)."""
    db.execute(
        update(SemanticInterpretationDecision)
        .where(SemanticInterpretationDecision.id == decision_id)
        .values(status=status, confidence=confidence)
    )
    db.commit()


def test_confirm_creates_version_one_with_human_confirmed(db: Session, tmp_path: Path) -> None:
    org_id, run_id = _run_case(db, tmp_path, "sr-confirm")
    decision = _decision(db, run_id, "asset_id")
    _force_status(db, decision.id, "review_required", 0.5)

    review, version = semantic_review_service.submit_review(
        db,
        org_id,
        decision.id,
        action="confirm",
        corrected_concept=None,
        notes="looks right",
        expected_version=0,
        reviewer_user_id=uuid4(),
        reviewer_role="analyst",
    )
    assert version.version_number == 1
    assert version.effective_status == "human_confirmed"
    assert version.supersedes_version_id is None
    assert review.action == "confirm"


def test_correct_requires_a_known_canonical_concept(db: Session, tmp_path: Path) -> None:
    org_id, run_id = _run_case(db, tmp_path, "sr-correct-unknown")
    decision = _decision(db, run_id, "asset_id")
    _force_status(db, decision.id, "review_required", 0.5)

    with pytest.raises(SemanticReviewServiceError) as exc_info:
        semantic_review_service.submit_review(
            db,
            org_id,
            decision.id,
            action="correct",
            corrected_concept="totally_not_a_real_concept",
            notes=None,
            expected_version=0,
            reviewer_user_id=uuid4(),
            reviewer_role="analyst",
        )
    assert exc_info.value.code == "SEMANTIC_REVIEW_INVALID_CONCEPT"
    assert exc_info.value.status == 400


def test_correct_with_a_known_concept_succeeds(db: Session, tmp_path: Path) -> None:
    org_id, run_id = _run_case(db, tmp_path, "sr-correct-known")
    decision = _decision(db, run_id, "failure_code")
    _force_status(db, decision.id, "review_required", 0.5)

    _, version = semantic_review_service.submit_review(
        db,
        org_id,
        decision.id,
        action="correct",
        corrected_concept="asset_id",
        notes=None,
        expected_version=0,
        reviewer_user_id=uuid4(),
        reviewer_role="analyst",
    )
    assert version.effective_status == "human_corrected"
    assert version.effective_concept == "asset_id"


def test_reject_produces_no_effective_concept(db: Session, tmp_path: Path) -> None:
    org_id, run_id = _run_case(db, tmp_path, "sr-reject")
    decision = _decision(db, run_id, "asset_id")
    _force_status(db, decision.id, "review_required", 0.5)

    _, version = semantic_review_service.submit_review(
        db,
        org_id,
        decision.id,
        action="reject",
        corrected_concept=None,
        notes="wrong",
        expected_version=0,
        reviewer_user_id=uuid4(),
        reviewer_role="analyst",
    )
    assert version.effective_status == "human_rejected"
    assert version.effective_concept is None


def test_mark_unresolved_produces_no_effective_concept(db: Session, tmp_path: Path) -> None:
    org_id, run_id = _run_case(db, tmp_path, "sr-unresolved")
    decision = _decision(db, run_id, "asset_id")
    _force_status(db, decision.id, "unresolved", 0.1)

    _, version = semantic_review_service.submit_review(
        db,
        org_id,
        decision.id,
        action="mark_unresolved",
        corrected_concept=None,
        notes=None,
        expected_version=0,
        reviewer_user_id=uuid4(),
        reviewer_role="analyst",
    )
    assert version.effective_status == "human_unresolved"


# H, T-W: a second (and third) human review creates a new version,
# chained via supersedes_version_id, and every legal revisit transition
# from the approved clarification succeeds.
@pytest.mark.parametrize(
    "first_action,second_action,second_concept",
    [
        ("confirm", "correct", "cost_amount"),  # HUMAN_CONFIRMED -> HUMAN_CORRECTED
        ("correct", "confirm", None),  # HUMAN_CORRECTED -> HUMAN_CONFIRMED
        ("reject", "correct", "cost_amount"),  # HUMAN_REJECTED -> HUMAN_CORRECTED
        ("mark_unresolved", "confirm", None),  # HUMAN_UNRESOLVED -> HUMAN_CONFIRMED
    ],
)
def test_every_approved_revisit_transition_is_legal(
    db: Session, tmp_path: Path, first_action: str, second_action: str, second_concept: str | None
) -> None:
    slug = f"sr-revisit-{first_action}-{second_action}".replace("_", "-")
    org_id, run_id = _run_case(db, tmp_path, slug)
    decision = _decision(db, run_id, "asset_id")
    _force_status(db, decision.id, "review_required", 0.5)

    first_concept = "asset_id" if first_action == "correct" else None
    _, v1 = semantic_review_service.submit_review(
        db,
        org_id,
        decision.id,
        action=first_action,
        corrected_concept=first_concept,
        notes=None,
        expected_version=0,
        reviewer_user_id=uuid4(),
        reviewer_role="analyst",
    )
    assert v1.version_number == 1

    _, v2 = semantic_review_service.submit_review(
        db,
        org_id,
        decision.id,
        action=second_action,
        corrected_concept=second_concept,
        notes="revisited",
        expected_version=1,
        reviewer_user_id=uuid4(),
        reviewer_role="analyst",
    )
    assert v2.version_number == 2
    assert v2.supersedes_version_id == v1.id

    # I/O: the first version and the original machine decision are both
    # unchanged by the second review.
    reloaded_v1 = db.get(SemanticDecisionVersion, v1.id)
    assert reloaded_v1 is not None
    assert reloaded_v1.version_number == 1
    assert reloaded_v1.effective_status == v1.effective_status
    reloaded_decision = db.get(SemanticInterpretationDecision, decision.id)
    assert reloaded_decision is not None
    assert reloaded_decision.status == "review_required"


# J / X: stale expected_version -> 409, including after a revisit already
# landed (the original expected_version=0/1 is now stale).
def test_stale_expected_version_returns_conflict(db: Session, tmp_path: Path) -> None:
    org_id, run_id = _run_case(db, tmp_path, "sr-stale-version")
    decision = _decision(db, run_id, "asset_id")
    _force_status(db, decision.id, "review_required", 0.5)

    semantic_review_service.submit_review(
        db,
        org_id,
        decision.id,
        action="reject",
        corrected_concept=None,
        notes=None,
        expected_version=0,
        reviewer_user_id=uuid4(),
        reviewer_role="analyst",
    )
    with pytest.raises(SemanticReviewServiceError) as exc_info:
        semantic_review_service.submit_review(
            db,
            org_id,
            decision.id,
            action="correct",
            corrected_concept="asset_id",
            notes=None,
            expected_version=0,  # stale -- version 1 already exists
            reviewer_user_id=uuid4(),
            reviewer_role="analyst",
        )
    assert exc_info.value.code == "SEMANTIC_REVIEW_VERSION_CONFLICT"
    assert exc_info.value.status == 409


# I: historical review/version rows are immutable at the ORM level.
def test_semantic_review_row_is_immutable(db: Session, tmp_path: Path) -> None:
    org_id, run_id = _run_case(db, tmp_path, "sr-immutable-review")
    decision = _decision(db, run_id, "asset_id")
    _force_status(db, decision.id, "review_required", 0.5)
    review, _ = semantic_review_service.submit_review(
        db,
        org_id,
        decision.id,
        action="reject",
        corrected_concept=None,
        notes=None,
        expected_version=0,
        reviewer_user_id=uuid4(),
        reviewer_role="analyst",
    )
    review.notes = "tampered"
    with pytest.raises(ValueError, match="immutable"):
        db.commit()
    db.rollback()


def test_semantic_decision_version_row_is_immutable(db: Session, tmp_path: Path) -> None:
    org_id, run_id = _run_case(db, tmp_path, "sr-immutable-version")
    decision = _decision(db, run_id, "asset_id")
    _force_status(db, decision.id, "review_required", 0.5)
    _, version = semantic_review_service.submit_review(
        db,
        org_id,
        decision.id,
        action="reject",
        corrected_concept=None,
        notes=None,
        expected_version=0,
        reviewer_user_id=uuid4(),
        reviewer_role="analyst",
    )
    version.effective_status = "human_confirmed"
    with pytest.raises(ValueError, match="immutable"):
        db.commit()
    db.rollback()


def test_unknown_action_is_rejected(db: Session, tmp_path: Path) -> None:
    org_id, run_id = _run_case(db, tmp_path, "sr-unknown-action")
    decision = _decision(db, run_id, "asset_id")
    with pytest.raises(SemanticReviewServiceError) as exc_info:
        semantic_review_service.submit_review(
            db,
            org_id,
            decision.id,
            action="approve",  # old vocabulary, no longer valid
            corrected_concept=None,
            notes=None,
            expected_version=0,
            reviewer_user_id=uuid4(),
            reviewer_role="analyst",
        )
    assert exc_info.value.code == "SEMANTIC_REVIEW_INVALID_ACTION"


def test_review_of_unknown_decision_returns_not_found(db: Session, tmp_path: Path) -> None:
    org_id, _ = _run_case(db, tmp_path, "sr-not-found")
    with pytest.raises(SemanticReviewServiceError) as exc_info:
        semantic_review_service.submit_review(
            db,
            org_id,
            uuid4(),
            action="confirm",
            corrected_concept=None,
            notes=None,
            expected_version=0,
            reviewer_user_id=uuid4(),
            reviewer_role="analyst",
        )
    assert exc_info.value.code == "SEMANTIC_DECISION_NOT_FOUND"
    assert exc_info.value.status == 404
