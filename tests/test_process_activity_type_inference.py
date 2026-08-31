"""P3.xxE.4 plan review correction 1: the 5-tier semantic evidence
eligibility hierarchy for activity typing. accepted_with_flag and
review_required are NOT equivalent."""

from app.process.activity_type import ActivityType
from app.process.activity_type_inference import (
    candidate_activity_type_for_concept,
    infer_activity_type,
)


def test_auto_accepted_produces_a_named_type_at_full_confidence() -> None:
    activity_type, confidence = infer_activity_type(
        machine_status="auto_accepted",
        concept_code="completed_timestamp",
        machine_confidence=0.9,
        is_independently_corroborated=False,
    )
    assert activity_type == ActivityType.COMPLETE.value
    assert confidence == 0.9


def test_human_confirmed_produces_a_named_type_at_full_confidence() -> None:
    activity_type, confidence = infer_activity_type(
        machine_status="human_confirmed",
        concept_code="scheduled_timestamp",
        machine_confidence=0.85,
        is_independently_corroborated=False,
    )
    assert activity_type == ActivityType.SCHEDULE.value
    assert confidence == 0.85


def test_accepted_with_flag_uncorroborated_stays_generic_and_discounted() -> None:
    activity_type, confidence = infer_activity_type(
        machine_status="accepted_with_flag",
        concept_code="completed_timestamp",
        machine_confidence=0.7,
        is_independently_corroborated=False,
    )
    assert activity_type == ActivityType.GENERIC.value
    assert confidence < 0.7


def test_accepted_with_flag_corroborated_produces_a_named_type() -> None:
    activity_type, confidence = infer_activity_type(
        machine_status="accepted_with_flag",
        concept_code="completed_timestamp",
        machine_confidence=0.7,
        is_independently_corroborated=True,
    )
    assert activity_type == ActivityType.COMPLETE.value
    assert confidence == 0.7


def test_review_required_never_independently_produces_a_named_type() -> None:
    """Correction 1's required test: REVIEW_REQUIRED evidence alone can
    never independently produce a high-confidence named activity type,
    with or without corroboration."""
    for corroborated in (True, False):
        activity_type, confidence = infer_activity_type(
            machine_status="review_required",
            concept_code="completed_timestamp",
            machine_confidence=0.95,
            is_independently_corroborated=corroborated,
        )
        assert activity_type == ActivityType.GENERIC.value
        assert confidence <= 0.35


def test_unresolved_never_produces_a_named_type_or_nonzero_confidence() -> None:
    activity_type, confidence = infer_activity_type(
        machine_status="unresolved",
        concept_code="completed_timestamp",
        machine_confidence=0.5,
        is_independently_corroborated=True,
    )
    assert activity_type == ActivityType.GENERIC.value
    assert confidence == 0.0


def test_event_timestamp_concept_is_deliberately_ambiguous() -> None:
    """The event_timestamp alias set is broad (includes "timestamp"/"date")
    -- it must never confidently name a specific activity, only OTHER,
    regardless of tier."""
    assert candidate_activity_type_for_concept("event_timestamp") == ActivityType.OTHER.value
    assert candidate_activity_type_for_concept("completed_timestamp") == ActivityType.COMPLETE.value
    assert candidate_activity_type_for_concept("scheduled_timestamp") == ActivityType.SCHEDULE.value
    assert candidate_activity_type_for_concept("some_unknown_concept") == ActivityType.OTHER.value
