"""P3.xxE.1A: pure, framework-free tests of the effective-decision
resolver and review-group classifier (app/semantic/review.py). No DB
needed -- these are the precedence rules the plan's section 9/State Model
specify, proven directly against StoredVersionView inputs."""

from app.semantic.candidate import InterpretationDecisionStatus
from app.semantic.review import (
    ReviewGroup,
    SemanticDecisionEffectiveStatus,
    SemanticReviewAction,
    StoredVersionView,
    classify_review_group,
    resolve_effective_decision,
    validate_action_payload,
)


def _version(
    status: SemanticDecisionEffectiveStatus, concept: str | None = None
) -> StoredVersionView:
    return StoredVersionView(
        version_number=1,
        effective_status=status,
        effective_concept=concept,
        effective_confidence=None,
    )


# A. auto_accepted machine result, no review -> effective, human_validated=false
def test_auto_accepted_with_no_review_is_effective_but_not_human_validated() -> None:
    result = resolve_effective_decision(
        machine_status=InterpretationDecisionStatus.AUTO_ACCEPTED.value,
        machine_selected_concept="asset_id",
        machine_confidence=0.95,
        latest_version=None,
    )
    assert result.effective_concept == "asset_id"
    assert result.human_validated is False
    assert result.source == "deterministic_confidence_engine"


# B. review_required, no review -> no effective concept
def test_review_required_with_no_review_has_no_effective_concept() -> None:
    result = resolve_effective_decision(
        machine_status=InterpretationDecisionStatus.REVIEW_REQUIRED.value,
        machine_selected_concept="maybe_asset",
        machine_confidence=0.5,
        latest_version=None,
    )
    assert result.effective_concept is None
    assert result.effective_status == "review_required"
    assert result.human_validated is False


# C. confirm -> effective concept = machine proposal, human_validated=true
def test_confirm_makes_the_machine_proposal_effective_and_human_validated() -> None:
    result = resolve_effective_decision(
        machine_status=InterpretationDecisionStatus.ACCEPTED_WITH_FLAG.value,
        machine_selected_concept="work_order_id",
        machine_confidence=0.75,
        latest_version=_version(SemanticDecisionEffectiveStatus.HUMAN_CONFIRMED),
    )
    assert result.effective_concept == "work_order_id"
    assert result.human_validated is True
    assert result.source == "human_confirmation"


# D. correct -> effective concept = corrected canonical concept
def test_correct_makes_the_corrected_concept_effective() -> None:
    result = resolve_effective_decision(
        machine_status=InterpretationDecisionStatus.REVIEW_REQUIRED.value,
        machine_selected_concept="wrong_guess",
        machine_confidence=0.5,
        latest_version=_version(SemanticDecisionEffectiveStatus.HUMAN_CORRECTED, "work_order_id"),
    )
    assert result.effective_concept == "work_order_id"
    assert result.human_validated is True
    assert result.source == "human_correction"


# E. reject -> no effective concept
def test_reject_has_no_effective_concept() -> None:
    result = resolve_effective_decision(
        machine_status=InterpretationDecisionStatus.REVIEW_REQUIRED.value,
        machine_selected_concept="wrong_guess",
        machine_confidence=0.5,
        latest_version=_version(SemanticDecisionEffectiveStatus.HUMAN_REJECTED),
    )
    assert result.effective_concept is None
    assert result.human_validated is True


# F. mark_unresolved -> no effective concept
def test_mark_unresolved_has_no_effective_concept() -> None:
    result = resolve_effective_decision(
        machine_status=InterpretationDecisionStatus.UNRESOLVED.value,
        machine_selected_concept=None,
        machine_confidence=0.1,
        latest_version=_version(SemanticDecisionEffectiveStatus.HUMAN_UNRESOLVED),
    )
    assert result.effective_concept is None
    assert result.human_validated is True


# G. rejected never falls back to the machine proposal automatically
def test_rejected_decision_never_falls_back_to_machine_proposal() -> None:
    result = resolve_effective_decision(
        machine_status=InterpretationDecisionStatus.AUTO_ACCEPTED.value,
        machine_selected_concept="asset_id",
        machine_confidence=0.99,
        latest_version=_version(SemanticDecisionEffectiveStatus.HUMAN_REJECTED),
    )
    # Even though the raw machine status is auto_accepted with a concept,
    # an explicit human rejection wins and produces no effective concept.
    assert result.effective_concept is None
    assert result.effective_status == "human_rejected"


def test_confidence_alone_does_not_constitute_approval() -> None:
    """accepted_with_flag / review_required, regardless of how close the
    confidence is to auto_accept_min, never become effective without an
    explicit human action or the machine's own auto_accepted status."""
    result = resolve_effective_decision(
        machine_status=InterpretationDecisionStatus.ACCEPTED_WITH_FLAG.value,
        machine_selected_concept="asset_id",
        machine_confidence=0.89,
        latest_version=None,
    )
    assert result.effective_concept is None
    assert result.human_validated is False


# T-W: revisit transitions -- the resolver always reads whatever version
# is currently latest, so proving "the latest version determines the
# outcome" IS proving every transition is legal from a pure-resolver
# standpoint (the service layer additionally proves the version-chain
# mechanics in test_semantic_review_transitions.py).
def test_human_confirmed_can_be_superseded_by_a_later_human_corrected() -> None:
    result = resolve_effective_decision(
        machine_status=InterpretationDecisionStatus.ACCEPTED_WITH_FLAG.value,
        machine_selected_concept="asset_id",
        machine_confidence=0.75,
        latest_version=_version(SemanticDecisionEffectiveStatus.HUMAN_CORRECTED, "technician_id"),
    )
    assert result.effective_concept == "technician_id"


def test_human_rejected_can_be_superseded_by_a_later_human_corrected() -> None:
    result = resolve_effective_decision(
        machine_status=InterpretationDecisionStatus.REVIEW_REQUIRED.value,
        machine_selected_concept="wrong_guess",
        machine_confidence=0.5,
        latest_version=_version(SemanticDecisionEffectiveStatus.HUMAN_CORRECTED, "work_order_id"),
    )
    assert result.effective_concept == "work_order_id"
    assert result.human_validated is True


def test_human_unresolved_can_be_superseded_by_a_later_human_confirmed() -> None:
    result = resolve_effective_decision(
        machine_status=InterpretationDecisionStatus.UNRESOLVED.value,
        machine_selected_concept=None,
        machine_confidence=0.1,
        latest_version=_version(SemanticDecisionEffectiveStatus.HUMAN_CONFIRMED),
    )
    assert result.human_validated is True


# Review group classification -- Y: NEEDS_RESOLUTION includes both machine
# unresolved and HUMAN_REJECTED/HUMAN_UNRESOLVED.
def test_needs_resolution_group_includes_machine_unresolved_with_no_version() -> None:
    group = classify_review_group(
        machine_status=InterpretationDecisionStatus.UNRESOLVED.value, latest_version=None
    )
    assert group == ReviewGroup.NEEDS_RESOLUTION


def test_needs_resolution_group_includes_human_rejected() -> None:
    group = classify_review_group(
        machine_status=InterpretationDecisionStatus.REVIEW_REQUIRED.value,
        latest_version=_version(SemanticDecisionEffectiveStatus.HUMAN_REJECTED),
    )
    assert group == ReviewGroup.NEEDS_RESOLUTION


def test_needs_resolution_group_includes_human_unresolved() -> None:
    group = classify_review_group(
        machine_status=InterpretationDecisionStatus.UNRESOLVED.value,
        latest_version=_version(SemanticDecisionEffectiveStatus.HUMAN_UNRESOLVED),
    )
    assert group == ReviewGroup.NEEDS_RESOLUTION


def test_resolved_group_includes_human_confirmed_and_corrected() -> None:
    assert (
        classify_review_group(
            machine_status=InterpretationDecisionStatus.ACCEPTED_WITH_FLAG.value,
            latest_version=_version(SemanticDecisionEffectiveStatus.HUMAN_CONFIRMED),
        )
        == ReviewGroup.RESOLVED
    )
    assert (
        classify_review_group(
            machine_status=InterpretationDecisionStatus.REVIEW_REQUIRED.value,
            latest_version=_version(SemanticDecisionEffectiveStatus.HUMAN_CORRECTED, "x"),
        )
        == ReviewGroup.RESOLVED
    )


def test_pending_review_group_covers_accepted_with_flag_and_review_required() -> None:
    assert (
        classify_review_group(
            machine_status=InterpretationDecisionStatus.ACCEPTED_WITH_FLAG.value,
            latest_version=None,
        )
        == ReviewGroup.PENDING_REVIEW
    )
    assert (
        classify_review_group(
            machine_status=InterpretationDecisionStatus.REVIEW_REQUIRED.value, latest_version=None
        )
        == ReviewGroup.PENDING_REVIEW
    )


def test_auto_accepted_with_no_version_is_not_in_any_queue_group() -> None:
    assert (
        classify_review_group(
            machine_status=InterpretationDecisionStatus.AUTO_ACCEPTED.value, latest_version=None
        )
        is None
    )


# K-equivalent at this layer: action-payload validation.
def test_correct_requires_a_corrected_concept() -> None:
    assert validate_action_payload(SemanticReviewAction.CORRECT, None) is not None
    assert validate_action_payload(SemanticReviewAction.CORRECT, "work_order_id") is None


def test_confirm_reject_mark_unresolved_forbid_a_corrected_concept() -> None:
    for action in (
        SemanticReviewAction.CONFIRM,
        SemanticReviewAction.REJECT,
        SemanticReviewAction.MARK_UNRESOLVED,
    ):
        assert validate_action_payload(action, "should_not_be_here") is not None
        assert validate_action_payload(action, None) is None
