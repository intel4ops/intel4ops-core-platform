from uuid import uuid4

import pytest

from app.narrative.claim_policy import ClaimConfidence, ClaimType
from app.narrative.validator import NarrativeValidationError, validate_narrative_draft
from app.schemas.executive_narrative import NarrativeClaimDraft, StructuredNarrativeDraft


def _draft(
    wording: str, claim_type: ClaimType = ClaimType.GOVERNED_SCAN_FACT
) -> tuple[StructuredNarrativeDraft, dict[str, set[ClaimType]]]:
    organization_id = uuid4()
    scan_id = uuid4()
    scan_ref = f"scan:{scan_id}"
    return (
        StructuredNarrativeDraft(
            organization_id=organization_id,
            scan_id=scan_id,
            headline=NarrativeClaimDraft(
                claim_type=claim_type,
                wording=wording,
                source_reference_ids=[scan_ref],
                confidence=ClaimConfidence.NOT_ASSESSED,
            ),
            executive_summary=[],
        ),
        {scan_ref: {ClaimType.GOVERNED_SCAN_FACT, ClaimType.LIMITATION}},
    )


@pytest.mark.parametrize(
    "wording",
    [
        "Exposure is $5M.",
        "Exposure is 5000000.",
        "Performance improved 10%.",
        "Exposure is USD five million.",
        "Exposure is five million.",
        "These are verified savings.",
        "The root cause is identified.",
        "This intervention will prevent future loss.",
        "A guaranteed outcome is available.",
        "The result is definitively correct.",
        "The result has high confidence.",
        "The issue caused the loss.",
        "A forecast is available.",
    ],
)
def test_unsafe_provider_wording_is_rejected(wording: str) -> None:
    draft, allowed = _draft(wording)
    with pytest.raises(NarrativeValidationError):
        validate_narrative_draft(
            draft,
            draft.organization_id,
            draft.scan_id,
            allowed,
            set(),
            None,
        )


def test_unknown_reference_and_unknown_claim_are_rejected() -> None:
    draft, allowed = _draft("Governed review is available.")
    draft.headline.source_reference_ids = ["finding:invented"]
    with pytest.raises(NarrativeValidationError):
        validate_narrative_draft(draft, draft.organization_id, draft.scan_id, allowed, set(), None)
    draft.headline.source_reference_ids = list(allowed)
    draft.headline.claim_type = ClaimType.UNKNOWN
    with pytest.raises(NarrativeValidationError):
        validate_narrative_draft(draft, draft.organization_id, draft.scan_id, allowed, set(), None)


def test_inference_cannot_be_promoted_to_confirmed_context() -> None:
    draft, allowed = _draft("Governed review is available.")
    inference_ref = f"profile-inference:{uuid4()}"
    draft.headline = NarrativeClaimDraft(
        claim_type=ClaimType.CUSTOMER_CONFIRMED_CONTEXT,
        wording="The customer context is confirmed.",
        source_reference_ids=[inference_ref],
    )
    allowed[inference_ref] = {ClaimType.AI_INFERENCE}
    with pytest.raises(NarrativeValidationError):
        validate_narrative_draft(draft, draft.organization_id, draft.scan_id, allowed, set(), None)


def test_provider_cannot_replace_next_investigation() -> None:
    draft, allowed = _draft("Governed review is available.")
    next_ref = f"next-investigation:{draft.scan_id}"
    allowed[next_ref] = {ClaimType.RECOMMENDATION}
    draft.recommended_next_step = NarrativeClaimDraft(
        claim_type=ClaimType.RECOMMENDATION,
        wording="Begin an unrelated action.",
        source_reference_ids=[list(allowed)[0]],
    )
    with pytest.raises(NarrativeValidationError):
        validate_narrative_draft(
            draft,
            draft.organization_id,
            draft.scan_id,
            allowed,
            set(),
            next_ref,
        )
