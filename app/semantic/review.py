from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.semantic.candidate import InterpretationDecisionStatus

# ---------------------------------------------------------------------------
# P3.xxE.1A Semantic Review & Governance Foundation. Pure, framework-free
# enums and the effective-decision resolver -- no persistence, no FastAPI,
# no SQLAlchemy here, matching the existing app/semantic/* convention of
# keeping business logic out of the service layer (see
# app/semantic/confidence_engine.py for the analogous machine-side rule).
#
# Explicitly NOT in this milestone (see the approved P3.xxE.1A plan's "Out
# of scope" section): compatibility_signature, cross-run reuse/inheritance,
# reuse ambiguity resolution. Every SemanticDecisionVersion this resolver
# reasons about is scoped to exactly one SemanticInterpretationDecision.id --
# there is no cross-run identity concept here at all.
# ---------------------------------------------------------------------------


class SemanticReviewAction(StrEnum):
    """Reviewer-facing actions only. "supersede" is deliberately absent --
    it is the automatic, unstored, purely positional consequence of a new
    version existing for a decision that already has one, never a distinct
    action a reviewer submits (see the plan's Review Action Model)."""

    CONFIRM = "confirm"
    CORRECT = "correct"
    REJECT = "reject"
    MARK_UNRESOLVED = "mark_unresolved"


class SemanticDecisionEffectiveStatus(StrEnum):
    """The four states a SemanticDecisionVersion row can actually store.
    MACHINE_AUTO_ACCEPTED is deliberately absent from this enum -- it is a
    resolver-computed state only (see resolve_effective_decision), never
    persisted, so it can never appear as a stored effective_status value."""

    HUMAN_CONFIRMED = "human_confirmed"
    HUMAN_CORRECTED = "human_corrected"
    HUMAN_REJECTED = "human_rejected"
    HUMAN_UNRESOLVED = "human_unresolved"


class SemanticDecisionSource(StrEnum):
    """Sources a SemanticDecisionVersion row can store. The machine-side
    source (deterministic_confidence_engine) is intentionally absent here
    too -- it is only ever resolver-computed, never written to a version
    row, matching SemanticDecisionEffectiveStatus above."""

    HUMAN_CONFIRMATION = "human_confirmation"
    HUMAN_CORRECTION = "human_correction"
    HUMAN_REJECTION = "human_rejection"
    HUMAN_UNRESOLVED = "human_unresolved"


# The one machine-side source string used only in resolver output, never
# stored on a SemanticDecisionVersion row.
DETERMINISTIC_CONFIDENCE_ENGINE_SOURCE = "deterministic_confidence_engine"
MACHINE_AUTO_ACCEPTED_STATUS = "machine_auto_accepted"


_ACTION_TO_EFFECTIVE_STATUS: dict[SemanticReviewAction, SemanticDecisionEffectiveStatus] = {
    SemanticReviewAction.CONFIRM: SemanticDecisionEffectiveStatus.HUMAN_CONFIRMED,
    SemanticReviewAction.CORRECT: SemanticDecisionEffectiveStatus.HUMAN_CORRECTED,
    SemanticReviewAction.REJECT: SemanticDecisionEffectiveStatus.HUMAN_REJECTED,
    SemanticReviewAction.MARK_UNRESOLVED: SemanticDecisionEffectiveStatus.HUMAN_UNRESOLVED,
}

_ACTION_TO_SOURCE: dict[SemanticReviewAction, SemanticDecisionSource] = {
    SemanticReviewAction.CONFIRM: SemanticDecisionSource.HUMAN_CONFIRMATION,
    SemanticReviewAction.CORRECT: SemanticDecisionSource.HUMAN_CORRECTION,
    SemanticReviewAction.REJECT: SemanticDecisionSource.HUMAN_REJECTION,
    SemanticReviewAction.MARK_UNRESOLVED: SemanticDecisionSource.HUMAN_UNRESOLVED,
}


class ReviewGroup(StrEnum):
    """The three logical governance groups (never a stored column --
    always derived from machine status + latest version's
    effective_status). HUMAN_REJECTED/HUMAN_UNRESOLVED live in
    NEEDS_RESOLUTION, not a dead-end -- they remain revisitable forever
    (see the plan's State Model)."""

    PENDING_REVIEW = "pending_review"
    NEEDS_RESOLUTION = "needs_resolution"
    RESOLVED = "resolved"


def effective_status_and_source_for_action(
    action: SemanticReviewAction,
) -> tuple[SemanticDecisionEffectiveStatus, SemanticDecisionSource]:
    return _ACTION_TO_EFFECTIVE_STATUS[action], _ACTION_TO_SOURCE[action]


def validate_action_payload(
    action: SemanticReviewAction, corrected_concept: str | None
) -> str | None:
    """Returns an error message if the payload is invalid for this action,
    else None. CORRECT requires corrected_concept; every other action
    forbids it (see the plan's Review Action Model)."""
    if action == SemanticReviewAction.CORRECT:
        if not corrected_concept:
            return "corrected_concept is required for the correct action"
        return None
    if corrected_concept is not None:
        return f"corrected_concept must not be supplied for the {action.value} action"
    return None


@dataclass(frozen=True)
class StoredVersionView:
    """Minimal, framework-free view of the latest SemanticDecisionVersion
    for a decision -- decoupled from the ORM model so this module stays
    importable without SQLAlchemy (matching app/semantic/*'s existing
    style)."""

    version_number: int
    effective_status: SemanticDecisionEffectiveStatus
    effective_concept: str | None
    effective_confidence: float | None


@dataclass(frozen=True)
class EffectiveDecision:
    effective_status: str
    effective_concept: str | None
    source: str
    effective_confidence: float | None
    human_validated: bool
    explanation: str


def resolve_effective_decision(
    *,
    machine_status: str,
    machine_selected_concept: str | None,
    machine_confidence: float,
    latest_version: StoredVersionView | None,
) -> EffectiveDecision:
    """Precedence, exactly as approved in the P3.xxE.1A plan:

    1. A human-governance version exists -> its effective_status/concept
       wins outright (HUMAN_CONFIRMED/HUMAN_CORRECTED carry an effective
       concept; HUMAN_REJECTED/HUMAN_UNRESOLVED carry none, and NEVER fall
       back to the machine proposal automatically).
    2. Else, if the raw machine decision is auto_accepted -> effective,
       but explicitly NOT human_validated.
    3. Else -> no effective concept (review_required or unresolved).
    """
    if latest_version is not None:
        if latest_version.effective_status == SemanticDecisionEffectiveStatus.HUMAN_CONFIRMED:
            return EffectiveDecision(
                effective_status=SemanticDecisionEffectiveStatus.HUMAN_CONFIRMED.value,
                effective_concept=machine_selected_concept,
                source=SemanticDecisionSource.HUMAN_CONFIRMATION.value,
                effective_confidence=latest_version.effective_confidence,
                human_validated=True,
                explanation="A reviewer confirmed the machine proposal as-is.",
            )
        if latest_version.effective_status == SemanticDecisionEffectiveStatus.HUMAN_CORRECTED:
            return EffectiveDecision(
                effective_status=SemanticDecisionEffectiveStatus.HUMAN_CORRECTED.value,
                effective_concept=latest_version.effective_concept,
                source=SemanticDecisionSource.HUMAN_CORRECTION.value,
                effective_confidence=latest_version.effective_confidence,
                human_validated=True,
                explanation="A reviewer corrected the machine proposal to a different concept.",
            )
        if latest_version.effective_status == SemanticDecisionEffectiveStatus.HUMAN_REJECTED:
            return EffectiveDecision(
                effective_status=SemanticDecisionEffectiveStatus.HUMAN_REJECTED.value,
                effective_concept=None,
                source=SemanticDecisionSource.HUMAN_REJECTION.value,
                effective_confidence=None,
                human_validated=True,
                explanation=(
                    "A reviewer explicitly rejected this field; it does not fall back to the "
                    "machine proposal. A later confirm/correct can restore an effective "
                    "interpretation."
                ),
            )
        return EffectiveDecision(
            effective_status=SemanticDecisionEffectiveStatus.HUMAN_UNRESOLVED.value,
            effective_concept=None,
            source=SemanticDecisionSource.HUMAN_UNRESOLVED.value,
            effective_confidence=None,
            human_validated=True,
            explanation=(
                "A reviewer explicitly marked this field unresolved. A later confirm/correct "
                "can restore an effective interpretation."
            ),
        )

    if machine_status == InterpretationDecisionStatus.AUTO_ACCEPTED.value:
        return EffectiveDecision(
            effective_status=MACHINE_AUTO_ACCEPTED_STATUS,
            effective_concept=machine_selected_concept,
            source=DETERMINISTIC_CONFIDENCE_ENGINE_SOURCE,
            effective_confidence=machine_confidence,
            human_validated=False,
            explanation=(
                "The deterministic confidence engine auto-accepted this proposal; no human has "
                "reviewed it."
            ),
        )

    if machine_status == InterpretationDecisionStatus.UNRESOLVED.value:
        return EffectiveDecision(
            effective_status="unresolved",
            effective_concept=None,
            source="none",
            effective_confidence=None,
            human_validated=False,
            explanation="The machine could not produce an actionable proposal for this field.",
        )

    return EffectiveDecision(
        effective_status="review_required",
        effective_concept=None,
        source="none",
        effective_confidence=None,
        human_validated=False,
        explanation="The machine proposal has not yet been reviewed by a human.",
    )


def classify_review_group(
    *, machine_status: str, latest_version: StoredVersionView | None
) -> ReviewGroup | None:
    """None means "not a queue item at all" -- a pure machine auto_accept
    with no human governance version is already effective without review
    (see resolve_effective_decision) and is deliberately never surfaced in
    any of the three groups, matching the plan's group table exactly."""
    if latest_version is not None:
        if latest_version.effective_status in (
            SemanticDecisionEffectiveStatus.HUMAN_CONFIRMED,
            SemanticDecisionEffectiveStatus.HUMAN_CORRECTED,
        ):
            return ReviewGroup.RESOLVED
        return ReviewGroup.NEEDS_RESOLUTION
    if machine_status == InterpretationDecisionStatus.UNRESOLVED.value:
        return ReviewGroup.NEEDS_RESOLUTION
    if machine_status in (
        InterpretationDecisionStatus.ACCEPTED_WITH_FLAG.value,
        InterpretationDecisionStatus.REVIEW_REQUIRED.value,
    ):
        return ReviewGroup.PENDING_REVIEW
    return None
