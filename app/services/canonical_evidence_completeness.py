from __future__ import annotations

from dataclasses import dataclass

from app.semantic.review import resolve_effective_decision

# ---------------------------------------------------------------------------
# P3.xxV.2D: CanonicalEvidenceCompletenessRule -- the POST-SEMANTIC, POST-
# MAPPING evidence-completeness check governed finding publication actually
# needs, kept deliberately separate from Trust's early
# RequiredFieldCompletenessRule (app/engines/trust_engine.py), which
# continues checking RAW source-field presence for raw dataset quality,
# unchanged, before mapping/semantic interpretation have even run.
#
# The two rules answer two different questions:
#   RawFieldCompletenessRule (early Trust):
#       "does the raw record contain a non-blank value under this literal
#       key?" -- correct for its own purpose (source data quality), wrong
#       if reused to judge whether a MODEL received the canonical evidence
#       it declared it needs.
#   CanonicalEvidenceCompletenessRule (this module, governed publication):
#       "does this finding candidate have GOVERNED evidence -- a raw field
#       that both (a) mapping resolved to this canonical concept, and (b)
#       carries sufficient semantic authority -- for every required
#       canonical concept?"
#
# Authority is deliberately delegated to the EXISTING P3.xxE.1A contract,
# resolve_effective_decision, the exact function app/entities/entity_resolution.py
# already uses to decide whether a semantic decision may name an entity's
# type. No second authority model is introduced: HUMAN_CONFIRMED/
# HUMAN_CORRECTED/AUTO_ACCEPTED grant effective evidence; ACCEPTED_WITH_FLAG
# and REVIEW_REQUIRED do not (resolve_effective_decision collapses both to
# "no effective concept" today -- unchanged by this module); UNRESOLVED
# never does. This module does not touch, weaken, or reinterpret that
# contract -- it only routes canonical-concept completeness through it.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RawFieldSemanticEvidence:
    """One (source_field -> canonical_field) mapping candidate, paired with
    that SAME raw field's own machine semantic decision. Framework-free --
    the orchestration layer adapts persisted AnalysisCaseFieldMapping +
    SemanticInterpretationDecision rows into this before calling
    evaluate_canonical_evidence_completeness, so this module has zero
    ORM/DB dependency and is directly unit-testable."""

    canonical_field: str
    source_field: str
    machine_status: str
    machine_selected_concept: str | None
    machine_confidence: float


@dataclass(frozen=True)
class CanonicalFieldEvidenceResult:
    canonical_field: str
    satisfied: bool
    # Provenance back to the raw field/value this canonical concept's
    # evidence came from -- never discarded, per instruction (Section 3).
    source_field: str | None
    semantic_status: str | None
    semantic_confidence: float | None


@dataclass(frozen=True)
class CanonicalEvidenceCompletenessResult:
    satisfied: bool
    fields: tuple[CanonicalFieldEvidenceResult, ...]
    missing_canonical_fields: tuple[str, ...]


def evaluate_canonical_evidence_completeness(
    required_canonical_fields: frozenset[str],
    candidates: list[RawFieldSemanticEvidence],
) -> CanonicalEvidenceCompletenessResult:
    """A required canonical field is satisfied only when at least one raw
    field mapping resolved to it ALSO has sufficient semantic authority
    under resolve_effective_decision -- never merely because a raw column
    exists, and never merely because mapping renamed it (mapping alone is
    not treated as universal semantic authority, per instruction). No
    simulation ID, dataset filename, or business-family branch appears
    here -- purely generic evidence-authority evaluation."""
    by_canonical: dict[str, list[RawFieldSemanticEvidence]] = {}
    for candidate in candidates:
        by_canonical.setdefault(candidate.canonical_field, []).append(candidate)

    results: list[CanonicalFieldEvidenceResult] = []
    missing: list[str] = []
    for canonical_field in sorted(required_canonical_fields):
        satisfied_result: CanonicalFieldEvidenceResult | None = None
        for candidate in by_canonical.get(canonical_field, []):
            effective = resolve_effective_decision(
                machine_status=candidate.machine_status,
                machine_selected_concept=candidate.machine_selected_concept,
                machine_confidence=candidate.machine_confidence,
                latest_version=None,
            )
            if effective.effective_concept is not None:
                satisfied_result = CanonicalFieldEvidenceResult(
                    canonical_field=canonical_field,
                    satisfied=True,
                    source_field=candidate.source_field,
                    semantic_status=candidate.machine_status,
                    semantic_confidence=candidate.machine_confidence,
                )
                break
        if satisfied_result is None:
            missing.append(canonical_field)
            satisfied_result = CanonicalFieldEvidenceResult(
                canonical_field=canonical_field,
                satisfied=False,
                source_field=None,
                semantic_status=None,
                semantic_confidence=None,
            )
        results.append(satisfied_result)

    return CanonicalEvidenceCompletenessResult(
        satisfied=not missing,
        fields=tuple(results),
        missing_canonical_fields=tuple(missing),
    )
