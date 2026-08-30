from __future__ import annotations

from dataclasses import dataclass

from app.semantic.candidate import (
    EvidenceComponentType,
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


def _is_ai_evidence(component_type: str) -> bool:
    return component_type == EvidenceComponentType.AI_PROPOSAL.value


def _merge_candidates_by_concept(candidates: list[SemanticCandidate]) -> list[SemanticCandidate]:
    """P3.xxE.2: when a deterministic candidate and an AI proposal (or
    several AI proposals) agree on the same candidate_concept for the same
    field, they are merged into one candidate with combined evidence --
    never left as separate competing entries, since that would let a
    numerically-higher AI confidence silently outrank a well-evidenced
    deterministic candidate under plain max(confidence) ranking. Merging
    is also what makes AI corroboration meaningful: the merged confidence
    is always taken from the field's non-AI evidence when any exists (see
    below) -- AI's own confidence number never inflates the merged score,
    it only ever unlocks eligibility for the corroboration check in
    reconcile()."""
    grouped: dict[str, list[SemanticCandidate]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.candidate_concept, []).append(candidate)

    merged: list[SemanticCandidate] = []
    for concept, group in grouped.items():
        if len(group) == 1:
            merged.append(group[0])
            continue
        all_evidence = [
            evidence for candidate in group for evidence in candidate.evidence_components
        ]
        non_ai_evidence = [e for e in all_evidence if not _is_ai_evidence(e.component_type)]
        if non_ai_evidence:
            # Additive by distinct evidence type, same philosophy as the
            # deterministic weight ladder in candidate_generator.py (each
            # independent evidence source genuinely strengthens
            # confidence) -- keep the strongest weight seen per type so a
            # duplicated component (e.g. two merged candidates both citing
            # FIELD_NAME_ALIAS_MATCH) doesn't double-count. AI's own
            # confidence number never enters this sum.
            best_weight_by_type: dict[str, float] = {}
            for evidence in non_ai_evidence:
                best_weight_by_type[evidence.component_type] = max(
                    best_weight_by_type.get(evidence.component_type, 0.0), evidence.weight
                )
            confidence = min(0.98, sum(best_weight_by_type.values()))
        else:
            # All-AI group (multiple AI proposals for the same concept, no
            # independent corroboration) -- use their own confidence, but
            # the AI-only corroboration cap in reconcile() still applies.
            confidence = min(0.98, max(candidate.confidence for candidate in group))
        sources = sorted({candidate.generated_by for candidate in group})
        merged.append(
            SemanticCandidate(
                source_dataset_id=group[0].source_dataset_id,
                source_field=group[0].source_field,
                candidate_concept=concept,
                confidence=confidence,
                evidence_components=all_evidence,
                candidate_rank=min(candidate.candidate_rank for candidate in group),
                generated_by="+".join(sources),
            )
        )
    return merged


def _ai_provenance_for(candidate: SemanticCandidate) -> dict[str, object] | None:
    ai_components = [e for e in candidate.evidence_components if _is_ai_evidence(e.component_type)]
    if not ai_components:
        return None
    source = next((s for s in candidate.generated_by.split("+") if ":" in s), None)
    if source is None:
        return {"ai_used": True}
    provider_code, _, model_version = source.partition(":")
    return {"ai_used": True, "provider_code": provider_code, "model_version": model_version}


def reconcile(
    source_dataset_id: str,
    source_field: str,
    candidates: list[SemanticCandidate],
    thresholds: ConfidenceThresholds | None = None,
) -> InterpretationDecision:
    """Combines independent evidence components already baked into each
    candidate's confidence (see candidate_generator.py) -- never a single
    AI confidence value taken at face value (section 8: "Do not hard-code
    ... Confidence must not be based solely on LLM confidence").

    P3.xxE.2 corroboration policy: an AI-only winning candidate (every
    evidence component is an AI_PROPOSAL) can reach ACCEPTED_WITH_FLAG at
    most -- it can only reach AUTO_ACCEPTED when at least one independent
    non-AI evidence component (field-name/alias, datatype, value-pattern,
    dataset-role, neighbor-field, cross-dataset, or identifier/cardinality)
    also supports the same concept. AI never single-handedly clears the
    auto-accept bar."""
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

    merged = _merge_candidates_by_concept(candidates)
    ranked = sorted(merged, key=lambda c: c.confidence, reverse=True)
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

    # AI corroboration cap: an uncorroborated AI-only candidate never
    # reaches AUTO_ACCEPTED, regardless of its raw confidence.
    is_ai_only = bool(best.evidence_components) and all(
        _is_ai_evidence(e.component_type) for e in best.evidence_components
    )
    if is_ai_only and status == InterpretationDecisionStatus.AUTO_ACCEPTED.value:
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
        ai_provenance=_ai_provenance_for(best),
    )
