from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from app.narrative.claim_policy import (
    CONFIDENCE_LANGUAGE,
    PARTIAL_SCAN_MESSAGE,
    REFUSED_SCAN_MESSAGE,
    ZERO_OPPORTUNITY_MESSAGE,
    ClaimConfidence,
    ClaimType,
)
from app.schemas.executive_narrative import (
    NarrativeClaim,
    NarrativeClaimDraft,
    NarrativeOpportunity,
    NarrativeOpportunityDraft,
    NarrativeValue,
    StructuredNarrative,
    StructuredNarrativeDraft,
)


def _render_claim(
    draft: NarrativeClaimDraft,
    sequence: int,
    values: Mapping[str, dict[str, object]],
) -> NarrativeClaim:
    governed_values = [
        NarrativeValue(
            reference_id=reference,
            classification="POTENTIAL_EXPOSURE",
            value=values[reference],
        )
        for reference in draft.value_reference_ids
    ]
    return NarrativeClaim(
        claim_id=f"claim-{sequence:03d}",
        claim_type=draft.claim_type,
        text=draft.wording,
        source_reference_ids=draft.source_reference_ids,
        evidence_reference_ids=draft.evidence_reference_ids,
        confidence=draft.confidence,
        confidence_language=CONFIDENCE_LANGUAGE[draft.confidence],
        limitations=draft.limitations,
        governed_values=governed_values,
    )


def render_narrative(
    draft: StructuredNarrativeDraft,
    values: Mapping[str, dict[str, object]],
) -> StructuredNarrative:
    sequence = 0

    def claim(item: NarrativeClaimDraft) -> NarrativeClaim:
        nonlocal sequence
        sequence += 1
        return _render_claim(item, sequence, values)

    def opportunity(item: NarrativeOpportunityDraft) -> NarrativeOpportunity:
        return NarrativeOpportunity(
            opportunity_reference_id=item.opportunity_reference_id,
            narrative=claim(item.narrative),
        )

    return StructuredNarrative(
        organization_id=draft.organization_id,
        scan_id=draft.scan_id,
        audience=draft.audience,
        headline=claim(draft.headline),
        executive_summary=[claim(item) for item in draft.executive_summary],
        key_messages=[claim(item) for item in draft.key_messages],
        opportunities=[opportunity(item) for item in draft.opportunities],
        context_summary=[claim(item) for item in draft.context_summary],
        limitations=[claim(item) for item in draft.limitations],
        data_gaps=[claim(item) for item in draft.data_gaps],
        recommended_next_step=(
            claim(draft.recommended_next_step) if draft.recommended_next_step is not None else None
        ),
        provider_limitations=draft.provider_limitations,
    )


def deterministic_fallback(
    organization_id: UUID,
    scan_id: UUID,
    source_snapshot: dict[str, object],
    values: Mapping[str, dict[str, object]],
) -> StructuredNarrative:
    scan_ref = f"scan:{scan_id}"
    status = str(source_snapshot.get("status", "refused"))
    opportunities = source_snapshot.get("opportunities", [])
    opportunity_rows = opportunities if isinstance(opportunities, list) else []
    gaps = source_snapshot.get("data_gaps", [])
    gap_rows = gaps if isinstance(gaps, list) else []

    if status == "refused":
        headline_text = "The available governed data does not yet support an opportunity view."
        summary_text = REFUSED_SCAN_MESSAGE
    elif not opportunity_rows:
        headline_text = "No governed eligible opportunities are currently supported."
        summary_text = ZERO_OPPORTUNITY_MESSAGE
    elif status == "partial":
        headline_text = "Governed opportunities are visible, with incomplete analytical coverage."
        summary_text = PARTIAL_SCAN_MESSAGE
    else:
        headline_text = "Governed operational opportunities are ready for executive review."
        summary_text = (
            "The current analysis contains supported operational opportunities. Review each "
            "opportunity with its governed evidence, confidence, and limitations."
        )

    def draft(
        claim_type: ClaimType,
        wording: str,
        references: list[str],
        *,
        confidence: ClaimConfidence = ClaimConfidence.NOT_ASSESSED,
        evidence: list[str] | None = None,
        value_refs: list[str] | None = None,
        limitations: list[str] | None = None,
    ) -> NarrativeClaimDraft:
        return NarrativeClaimDraft(
            claim_type=claim_type,
            wording=wording,
            source_reference_ids=references,
            evidence_reference_ids=evidence or [],
            confidence=confidence,
            limitations=limitations or [],
            value_reference_ids=value_refs or [],
        )

    opportunity_drafts: list[NarrativeOpportunityDraft] = []
    rows_to_render = [] if status == "refused" else opportunity_rows
    for row in rows_to_render[:5]:
        if not isinstance(row, dict):
            continue
        rank = int(str(row.get("rank") or len(opportunity_drafts) + 1))
        opportunity_ref = f"opportunity:{scan_id}:{rank}"
        finding_ref = f"finding:{row.get('finding_id')}"
        evidence = [str(item) for item in row.get("evidence_reference_ids", [])][:10]
        confidence_value = str(row.get("confidence", "NOT_ASSESSED"))
        confidence = (
            ClaimConfidence(confidence_value)
            if confidence_value in {item.value for item in ClaimConfidence}
            else ClaimConfidence.NOT_ASSESSED
        )
        value_ref = f"value:{scan_id}:{rank}:potential_exposure"
        value_refs = [value_ref] if value_ref in values else []
        title = str(row.get("title") or "Governed operational finding")
        opportunity_drafts.append(
            NarrativeOpportunityDraft(
                opportunity_reference_id=opportunity_ref,
                narrative=draft(
                    ClaimType.POTENTIAL_EXPOSURE if value_refs else ClaimType.GOVERNED_FINDING,
                    title,
                    [opportunity_ref, finding_ref],
                    confidence=confidence,
                    evidence=evidence,
                    value_refs=value_refs,
                ),
            )
        )

    gap_claims: list[NarrativeClaimDraft] = []
    for row in gap_rows[:5]:
        if not isinstance(row, dict):
            continue
        code = str(row.get("gap_code") or "UNSPECIFIED")
        text = str(row.get("remediation_guidance") or "Resolve the governed data gap.")
        gap_claims.append(draft(ClaimType.LIMITATION, text, [f"gap:{scan_id}:{code}"]))

    next_snapshot = source_snapshot.get("next_investigation")
    next_claim = None
    if isinstance(next_snapshot, dict):
        text = str(next_snapshot.get("text") or "Complete the governed next investigation.")
        next_claim = draft(
            ClaimType.RECOMMENDATION,
            text,
            [f"next-investigation:{scan_id}"],
        )

    raw_limitations = source_snapshot.get("limitations", [])
    limitation_items = raw_limitations if isinstance(raw_limitations, list) else []
    limitations = [
        draft(ClaimType.LIMITATION, str(item), [scan_ref]) for item in limitation_items[:5]
    ]
    fallback_draft = StructuredNarrativeDraft(
        organization_id=organization_id,
        scan_id=scan_id,
        audience="EXECUTIVE",
        headline=draft(ClaimType.GOVERNED_SCAN_FACT, headline_text, [scan_ref]),
        executive_summary=[draft(ClaimType.GOVERNED_SCAN_FACT, summary_text, [scan_ref])],
        key_messages=[],
        opportunities=opportunity_drafts,
        context_summary=[],
        limitations=limitations,
        data_gaps=gap_claims,
        recommended_next_step=next_claim,
        provider_limitations=[],
    )
    return render_narrative(fallback_draft, values)
