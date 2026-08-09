from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from app.narrative.claim_policy import (
    ClaimType,
    contains_generated_number,
    contains_prohibited_truth_claim,
)
from app.schemas.executive_narrative import NarrativeClaimDraft, StructuredNarrativeDraft


class NarrativeValidationError(ValueError):
    pass


def _all_claims(draft: StructuredNarrativeDraft) -> list[NarrativeClaimDraft]:
    claims = [draft.headline, *draft.executive_summary, *draft.key_messages]
    claims.extend(item.narrative for item in draft.opportunities)
    claims.extend(draft.context_summary)
    claims.extend(draft.limitations)
    claims.extend(draft.data_gaps)
    if draft.recommended_next_step is not None:
        claims.append(draft.recommended_next_step)
    return claims


def validate_narrative_draft(
    draft: StructuredNarrativeDraft,
    organization_id: UUID,
    scan_id: UUID,
    allowed_claim_types: Mapping[str, set[ClaimType]],
    allowed_value_references: set[str],
    next_investigation_reference: str | None,
) -> None:
    if draft.organization_id != organization_id or draft.scan_id != scan_id:
        raise NarrativeValidationError("provider output crossed the governed tenant boundary")
    if draft.headline.claim_type is ClaimType.UNKNOWN:
        raise NarrativeValidationError("unknown claims cannot be rendered")
    word_count = sum(len(item.wording.split()) for item in draft.executive_summary)
    if word_count > 120:
        raise NarrativeValidationError("executive summary exceeds the word limit")
    if draft.recommended_next_step is not None:
        if next_investigation_reference is None:
            raise NarrativeValidationError("provider invented a next investigation")
        if next_investigation_reference not in draft.recommended_next_step.source_reference_ids:
            raise NarrativeValidationError("provider replaced the governed next investigation")

    for claim in _all_claims(draft):
        if claim.claim_type is ClaimType.UNKNOWN:
            raise NarrativeValidationError("unknown claims cannot be rendered")
        if contains_generated_number(claim.wording):
            raise NarrativeValidationError("provider wording contains an unauthorized number")
        if contains_prohibited_truth_claim(claim.wording):
            raise NarrativeValidationError("provider wording contains a prohibited truth claim")
        lowered = claim.wording.casefold()
        if claim.claim_type is ClaimType.AI_INFERENCE and not any(
            marker in lowered
            for marker in ("may", "might", "suggest", "appears", "tentative", "possible", "could")
        ):
            raise NarrativeValidationError("AI inference wording is not tentative")
        if any(
            phrase in lowered
            for phrase in (
                "certainly",
                "definitively",
                "conclusively",
                "no problems found",
                "no leakage",
                "clean bill of health",
                "high confidence",
                "medium confidence",
                "moderate confidence",
                "low confidence",
            )
        ):
            raise NarrativeValidationError("provider wording overstates governed support")
        for reference in claim.source_reference_ids:
            permitted = allowed_claim_types.get(reference)
            if permitted is None:
                raise NarrativeValidationError("provider returned an unknown source reference")
            if claim.claim_type not in permitted:
                raise NarrativeValidationError("claim type is incompatible with its source")
        unknown_evidence = [
            reference
            for reference in claim.evidence_reference_ids
            if reference not in allowed_claim_types
            or ClaimType.GOVERNED_FINDING not in allowed_claim_types[reference]
        ]
        if unknown_evidence:
            raise NarrativeValidationError("provider returned an unknown evidence reference")
        if set(claim.value_reference_ids) - allowed_value_references:
            raise NarrativeValidationError("provider returned an unknown value reference")
        if claim.value_reference_ids and claim.claim_type is not ClaimType.POTENTIAL_EXPOSURE:
            raise NarrativeValidationError("governed values require a potential-exposure claim")

    opportunity_refs = set(allowed_claim_types)
    if any(item.opportunity_reference_id not in opportunity_refs for item in draft.opportunities):
        raise NarrativeValidationError("provider returned an unknown opportunity reference")
