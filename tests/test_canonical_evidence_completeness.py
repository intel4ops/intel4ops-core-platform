"""P3.xxV.2D: CanonicalEvidenceCompletenessRule -- pure, framework-free unit
tests for evaluate_canonical_evidence_completeness. No DB, no orchestrator;
app/services/analysis_case_orchestration_service.py's
_evaluate_canonical_evidence_completeness is the (separately, end-to-end
tested) adapter that builds RawFieldSemanticEvidence from persisted
AnalysisCaseFieldMapping/SemanticInterpretationDecision rows and calls into
this module -- these tests exercise the authority logic itself directly."""

from app.services.canonical_evidence_completeness import (
    RawFieldSemanticEvidence,
    evaluate_canonical_evidence_completeness,
)


def _evidence(
    canonical_field: str,
    source_field: str,
    status: str,
    confidence: float,
    selected_concept: str | None = None,
) -> RawFieldSemanticEvidence:
    return RawFieldSemanticEvidence(
        canonical_field=canonical_field,
        source_field=source_field,
        machine_status=status,
        machine_selected_concept=selected_concept or source_field,
        machine_confidence=confidence,
    )


def test_a_exact_canonical_named_field_passes() -> None:
    """A/Section 9: a raw field already literally named like the canonical
    concept, auto_accepted, satisfies the requirement -- existing direct
    behavior must keep working."""
    result = evaluate_canonical_evidence_completeness(
        frozenset({"operational_event_id"}),
        [_evidence("operational_event_id", "operational_event_id", "auto_accepted", 0.95)],
    )
    assert result.satisfied is True
    assert result.fields[0].satisfied is True
    assert result.fields[0].source_field == "operational_event_id"


def test_b_authoritative_alias_mapped_field_passes() -> None:
    """B/Section 8's worked example: dispatch_id, mapped to
    operational_event_id, with sufficient (auto_accepted) semantic
    authority -- satisfies the requirement. No XDOM-specific branching
    anywhere in the module being tested."""
    result = evaluate_canonical_evidence_completeness(
        frozenset({"operational_event_id"}),
        [_evidence("operational_event_id", "dispatch_id", "auto_accepted", 0.9)],
    )
    assert result.satisfied is True


def test_c_lineage_is_preserved_back_to_the_raw_field() -> None:
    """C -- provenance (source field, semantic status/confidence) is
    reported alongside the canonical concept, never discarded."""
    result = evaluate_canonical_evidence_completeness(
        frozenset({"operational_event_id"}),
        [_evidence("operational_event_id", "dispatch_id", "auto_accepted", 0.9)],
    )
    field = result.fields[0]
    assert field.canonical_field == "operational_event_id"
    assert field.source_field == "dispatch_id"
    assert field.semantic_status == "auto_accepted"
    assert field.semantic_confidence == 0.9


def test_d_missing_canonical_concept_fails() -> None:
    """D -- no candidate at all for a required concept -- FAIL, no
    fabrication."""
    result = evaluate_canonical_evidence_completeness(
        frozenset({"operational_event_id"}),
        [],
    )
    assert result.satisfied is False
    assert result.missing_canonical_fields == ("operational_event_id",)
    assert result.fields[0].satisfied is False
    assert result.fields[0].source_field is None


def test_e_review_required_does_not_independently_satisfy() -> None:
    """E -- an alias candidate exists but sits at review_required: existing
    governed policy (resolve_effective_decision) does not grant it
    authority, so it must not silently pass."""
    result = evaluate_canonical_evidence_completeness(
        frozenset({"operational_event_id"}),
        [_evidence("operational_event_id", "dispatch_id", "review_required", 0.6)],
    )
    assert result.satisfied is False


def test_f_unresolved_fails() -> None:
    result = evaluate_canonical_evidence_completeness(
        frozenset({"operational_event_id"}),
        [_evidence("operational_event_id", "dispatch_id", "unresolved", 0.0)],
    )
    assert result.satisfied is False


def test_g_accepted_with_flag_alone_does_not_satisfy() -> None:
    """G -- ACCEPTED_WITH_FLAG (the tier a field with weak/partial evidence,
    e.g. a mostly-empty or ambiguous column, would land at) does not
    independently satisfy either, matching resolve_effective_decision's
    existing, unmodified policy -- the same bar entity formation already
    uses."""
    result = evaluate_canonical_evidence_completeness(
        frozenset({"asset_id"}),
        [_evidence("asset_id", "asset_id", "accepted_with_flag", 0.8)],
    )
    assert result.satisfied is False


def test_h_candidate_for_a_different_canonical_field_does_not_satisfy() -> None:
    """H -- a raw field's mapping/semantic evidence for a DIFFERENT
    canonical concept never satisfies an unrelated required concept, even
    if it has full authority -- no accidental cross-satisfaction."""
    result = evaluate_canonical_evidence_completeness(
        frozenset({"operational_event_id"}),
        [_evidence("asset_id", "asset_id", "auto_accepted", 0.95)],
    )
    assert result.satisfied is False
    assert result.missing_canonical_fields == ("operational_event_id",)


def test_multiple_required_fields_all_must_be_satisfied() -> None:
    result = evaluate_canonical_evidence_completeness(
        frozenset({"operational_event_id", "asset_id"}),
        [
            _evidence("operational_event_id", "work_order_id", "auto_accepted", 0.98),
            _evidence("asset_id", "asset_id", "accepted_with_flag", 0.8),
        ],
    )
    assert result.satisfied is False
    assert result.missing_canonical_fields == ("asset_id",)
    by_field = {f.canonical_field: f for f in result.fields}
    assert by_field["operational_event_id"].satisfied is True
    assert by_field["asset_id"].satisfied is False


def test_no_required_fields_is_trivially_satisfied() -> None:
    result = evaluate_canonical_evidence_completeness(frozenset(), [])
    assert result.satisfied is True
    assert result.fields == ()
    assert result.missing_canonical_fields == ()
