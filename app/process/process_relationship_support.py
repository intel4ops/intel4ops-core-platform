from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# P3.xxE.4 section 15 (tests O/P): the explicit corroboration gate. A
# CanonicalCaseRelationship (E.3) NEVER by itself asserts process sequence
# or process semantics -- a relationship type or an entity-type pair alone
# is structural/associative evidence, not temporal evidence. It may only
# ever RAISE confidence in an already-temporally-evidenced precedence claim
# (a supporting signal, per correction 2's corroboration-signal list),
# never independently manufacture one. Isolated into its own module so
# this invariant is independently testable, not buried inline in
# sequence_discovery.py/precedence_confidence.py.
# ---------------------------------------------------------------------------

_STRUCTURAL_SUPPORT_BOOST = 0.05


@dataclass(frozen=True)
class RelationshipSupportSignal:
    """A minimal, already-resolved view of one E.3 CanonicalCaseRelationship
    relevant to a candidate precedence pair -- built by the caller, never
    re-derived here."""

    entity_id_a: str
    entity_id_b: str
    relationship_confidence: float


def relationship_corroborates_pair(
    *,
    signals: list[RelationshipSupportSignal],
    entity_id_a: str,
    entity_id_b: str,
) -> bool:
    """True only when at least one relationship connects the SAME two
    entities already tied to this precedence pair by temporal evidence --
    never inferred from relationship TYPE or entity TYPE alone (test P)."""
    pair = {entity_id_a, entity_id_b}
    return any({s.entity_id_a, s.entity_id_b} == pair for s in signals)


def apply_structural_corroboration(
    *,
    precedence_confidence: float,
    has_temporal_evidence: bool,
    is_relationship_corroborated: bool,
) -> float:
    """A relationship signal may only ever ADD to a claim that already has
    real temporal evidence behind it (has_temporal_evidence=True, i.e.
    support_count > 0 upstream) -- with no temporal evidence at all, a
    relationship's mere existence is never sufficient to assert PRECEDES
    (test O: relationship type alone never asserts process sequence)."""
    if not has_temporal_evidence or not is_relationship_corroborated:
        return precedence_confidence
    return round(min(precedence_confidence + _STRUCTURAL_SUPPORT_BOOST, 0.98), 4)
