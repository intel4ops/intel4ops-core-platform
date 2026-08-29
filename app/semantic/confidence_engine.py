from __future__ import annotations

from dataclasses import dataclass

from app.semantic.candidate import (
    InterpretationDecision,
    InterpretationDecisionStatus,
    SemanticCandidate,
)

# ---------------------------------------------------------------------------
# Section 8/9: confidence reconciliation. This is INTERPRETATION confidence
# ("how certain are we what this field means"), never DATA TRUST ("is the
# source data reliable/complete/valid" -- that is Trust's job, computed
# entirely separately by app/services/trust_service.py and never read or
# blended in here). A perfectly complete, 100%-trusted dataset can still
# produce a low-confidence semantic interpretation, and this module has no
# mechanism that could ever collapse the two into one score.
#
# Thresholds are versioned configuration (section 8), not permanent
# constants -- ConfidenceThresholds can be swapped/tuned without touching
# the reconciliation logic itself.
# ---------------------------------------------------------------------------

DECISION_SOURCE = "deterministic_confidence_engine"
DECISION_VERSION = "v1"


@dataclass(frozen=True)
class ConfidenceThresholds:
    version: str = "v1"
    auto_accept_min: float = 0.90
    accepted_with_flag_min: float = 0.70
    review_required_min: float = 0.40

    def status_for(self, confidence: float) -> str:
        if confidence >= self.auto_accept_min:
            return InterpretationDecisionStatus.AUTO_ACCEPTED.value
        if confidence >= self.accepted_with_flag_min:
            return InterpretationDecisionStatus.ACCEPTED_WITH_FLAG.value
        if confidence >= self.review_required_min:
            return InterpretationDecisionStatus.REVIEW_REQUIRED.value
        return InterpretationDecisionStatus.UNRESOLVED.value


default_confidence_thresholds = ConfidenceThresholds()


def reconcile(
    source_dataset_id: str,
    source_field: str,
    candidates: list[SemanticCandidate],
    thresholds: ConfidenceThresholds | None = None,
) -> InterpretationDecision:
    """Combines independent evidence components already baked into each
    candidate's confidence (see candidate_generator.py) -- never a single
    AI confidence value taken at face value (section 8: "Do not hard-code
    ... Confidence must not be based solely on LLM confidence")."""
    thresholds = thresholds or default_confidence_thresholds

    if not candidates:
        return InterpretationDecision(
            source_dataset_id=source_dataset_id,
            source_field=source_field,
            selected_concept=None,
            confidence=0.0,
            status=InterpretationDecisionStatus.UNRESOLVED.value,
            evidence_summary=["no candidate concept was proposed by any generator"],
            alternative_candidates=[],
            decision_source=DECISION_SOURCE,
            decision_version=DECISION_VERSION,
        )

    ranked = sorted(candidates, key=lambda c: c.confidence, reverse=True)
    best = ranked[0]
    status = thresholds.status_for(best.confidence)

    # Genuine ambiguity is real evidence, not noise: two well-supported,
    # closely-scored candidates for the same field should never be
    # silently auto-accepted just because one edges out the other.
    if (
        len(ranked) > 1
        and (best.confidence - ranked[1].confidence) < 0.1
        and status == InterpretationDecisionStatus.AUTO_ACCEPTED.value
    ):
        status = InterpretationDecisionStatus.ACCEPTED_WITH_FLAG.value

    evidence_summary = [e.description for e in best.evidence_components]

    return InterpretationDecision(
        source_dataset_id=source_dataset_id,
        source_field=source_field,
        selected_concept=best.candidate_concept,
        confidence=best.confidence,
        status=status,
        evidence_summary=evidence_summary,
        alternative_candidates=ranked[1:5],
        decision_source=DECISION_SOURCE,
        decision_version=f"{DECISION_VERSION}+thresholds:{thresholds.version}",
    )
