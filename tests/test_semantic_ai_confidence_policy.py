"""P3.xxE.2: AI corroboration policy in app/semantic/confidence_engine.py --
an AI-only candidate never reaches AUTO_ACCEPTED on its own; any
independent non-AI evidence (not just literal field-name match) for the
same concept unlocks full-tier scoring. Pure unit tests against reconcile(),
no DB/orchestration needed."""

from app.semantic.candidate import EvidenceComponentType, InterpretationEvidence, SemanticCandidate
from app.semantic.confidence_engine import reconcile


def _evidence(
    component_type: EvidenceComponentType, weight: float, concept: str
) -> InterpretationEvidence:
    return InterpretationEvidence(
        component_type=component_type.value,
        weight=weight,
        description=f"{component_type.value} supports {concept}",
        supports_concept=concept,
    )


def _ai_candidate(concept: str, confidence: float, field: str = "f") -> SemanticCandidate:
    return SemanticCandidate(
        source_dataset_id="ds",
        source_field=field,
        candidate_concept=concept,
        confidence=confidence,
        evidence_components=[_evidence(EvidenceComponentType.AI_PROPOSAL, confidence, concept)],
        candidate_rank=99,
        generated_by="openai:gpt-test",
    )


def _deterministic_candidate(
    concept: str, confidence: float, field: str = "f"
) -> SemanticCandidate:
    return SemanticCandidate(
        source_dataset_id="ds",
        source_field=field,
        candidate_concept=concept,
        confidence=confidence,
        evidence_components=[
            _evidence(EvidenceComponentType.FIELD_NAME_ALIAS_MATCH, confidence, concept)
        ],
        candidate_rank=0,
        generated_by="deterministic_evidence_v1",
    )


# C. AI-only weak (or even very high) proposal never auto-accepts.
def test_ai_only_candidate_never_reaches_auto_accepted_even_at_high_confidence() -> None:
    decision = reconcile("ds", "f", [_ai_candidate("work_order_id", 0.99)])
    assert decision.status == "accepted_with_flag"
    assert decision.selected_concept == "work_order_id"
    assert decision.ai_provenance == {
        "ai_used": True,
        "provider_code": "openai",
        "model_version": "gpt-test",
    }


def test_ai_only_moderate_confidence_stays_below_accepted_with_flag_naturally() -> None:
    decision = reconcile("ds", "f", [_ai_candidate("work_order_id", 0.5)])
    assert decision.status == "review_required"


# D. AI proposal contradicted by deterministic evidence for a DIFFERENT
# concept is downgraded -- it may still win the ranking (it IS evidence,
# just never authoritative), but the uncorroborated-AI cap prevents it
# from reaching AUTO_ACCEPTED, and the deterministic hypothesis for the
# other concept remains visible as an alternative for governance, never
# silently discarded.
def test_ai_proposal_contradicted_by_deterministic_evidence_is_capped_and_alt_preserved() -> None:
    candidates = [
        _deterministic_candidate("technician_id", 0.85),
        _ai_candidate("customer_id", 0.9),
    ]
    decision = reconcile("ds", "f", candidates)
    assert decision.selected_concept == "customer_id"
    assert decision.status == "accepted_with_flag"
    assert decision.status != "auto_accepted"
    alternative_concepts = {c.candidate_concept for c in decision.alternative_candidates}
    assert "technician_id" in alternative_concepts


# Corroboration: independent non-AI evidence (not just literal field-name
# match) for the SAME concept unlocks AUTO_ACCEPTED.
def test_ai_corroborated_by_neighbor_evidence_can_reach_auto_accepted() -> None:
    neighbor = SemanticCandidate(
        source_dataset_id="ds",
        source_field="f",
        candidate_concept="work_order_id",
        confidence=0.1,
        evidence_components=[
            _evidence(EvidenceComponentType.NEIGHBOR_FIELD_CONTEXT, 0.1, "work_order_id")
        ],
        candidate_rank=60,
        generated_by="neighbor_context_v1",
    )
    deterministic = _deterministic_candidate("work_order_id", 0.85)
    ai = _ai_candidate("work_order_id", 0.95)
    decision = reconcile("ds", "f", [deterministic, neighbor, ai])
    assert decision.status == "auto_accepted"
    assert decision.ai_provenance is not None
    assert decision.ai_provenance["ai_used"] is True


def test_ai_corroborated_by_cross_dataset_evidence_can_reach_auto_accepted() -> None:
    cross_dataset = SemanticCandidate(
        source_dataset_id="ds",
        source_field="f",
        candidate_concept="asset_id",
        confidence=0.15,
        evidence_components=[
            _evidence(EvidenceComponentType.CROSS_DATASET_OVERLAP, 0.15, "asset_id")
        ],
        candidate_rank=50,
        generated_by="cross_dataset_context_v1",
    )
    deterministic = _deterministic_candidate("asset_id", 0.85)
    ai = _ai_candidate("asset_id", 0.92)
    decision = reconcile("ds", "f", [deterministic, cross_dataset, ai])
    assert decision.status == "auto_accepted"


def test_decision_version_never_carries_provider_identity() -> None:
    decision = reconcile("ds", "f", [_ai_candidate("work_order_id", 0.99)])
    assert "openai" not in decision.decision_version
    assert "gpt" not in decision.decision_version
    assert decision.decision_version.startswith("v1+thresholds:")


def test_purely_deterministic_decision_has_no_ai_provenance() -> None:
    decision = reconcile("ds", "f", [_deterministic_candidate("asset_id", 0.95)])
    assert decision.ai_provenance is None
