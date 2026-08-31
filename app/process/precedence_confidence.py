from __future__ import annotations

from dataclasses import dataclass

from app.process.activity_type import ProcessEdgeType, ProcessStatus
from app.process.sequence_discovery import PairTally, tally_temporal_evidence_tier
from app.process.temporal_evidence import temporal_confidence_for_tier

# ---------------------------------------------------------------------------
# P3.xxE.4 section 17: precedence confidence decomposition (never blind
# multiplication -- mirrors app/entities/confidence_decomposition.py's
# compose_relationship_confidence shape: a semantic floor, weighted
# supporting components, a conflict penalty, capped at 0.98) plus section
# 16's required per-pair contradiction pass, mirroring E.3's
# _flag_contradictory_many_to_one_pairs but for precedence direction
# instead of cardinality: a pair where BOTH directions clear a minimum
# strength is CONFLICTED regardless of aggregate confidence, never averaged
# away into a fabricated single direction.
# ---------------------------------------------------------------------------

_CONFIDENCE_CAP = 0.98
_MIN_DIRECTIONAL_STRENGTH_FOR_CONTRADICTION = 0.30
_MIN_SUPPORT_FOR_CONTRADICTION_CHECK = 2

_STRUCTURAL_ONLY_PRECEDENCE_CAP = 0.5


def _repetition_confidence(tally: PairTally) -> float:
    return (
        round(min(0.15 + 0.05 * (tally.support_count - 1), 0.5), 4) if tally.support_count else 0.0
    )


def _consistency_confidence(tally: PairTally) -> float:
    if tally.support_count == 0:
        return 0.0
    dominant = max(tally.a_before_b_count, tally.b_before_a_count)
    return round(dominant / tally.support_count, 4)


def _conflict_penalty(tally: PairTally) -> float:
    if tally.support_count < _MIN_SUPPORT_FOR_CONTRADICTION_CHECK:
        return 0.0
    a_strength = tally.a_before_b_count / tally.support_count
    b_strength = tally.b_before_a_count / tally.support_count
    if (
        a_strength >= _MIN_DIRECTIONAL_STRENGTH_FOR_CONTRADICTION
        and b_strength >= _MIN_DIRECTIONAL_STRENGTH_FOR_CONTRADICTION
    ):
        return round(min(a_strength, b_strength), 4)
    return 0.0


def is_contradictory(tally: PairTally) -> bool:
    """Section 16's required per-pair contradiction check: BOTH directions
    clearing a minimum strength threshold is a genuine contradiction, not
    an averaging problem -- reclassified to CONFLICTED regardless of how
    high the aggregate confidence would otherwise compute."""
    return _conflict_penalty(tally) > 0.0


@dataclass(frozen=True)
class PrecedenceConfidenceResult:
    """Every component persisted separately on CanonicalProcessEdge --
    never collapsed to one opaque number (spec section 17)."""

    precedence_confidence: float
    temporal_evidence_tier: str
    status: str
    semantic_confidence: float
    entity_participation_confidence: float
    temporal_confidence: float
    repetition_confidence: float
    consistency_confidence: float
    conflict_penalty: float


def compose_precedence_confidence(
    tally: PairTally,
    *,
    weaker_activity_type_confidence: float,
    entity_participation_confidence: float,
) -> PrecedenceConfidenceResult:
    """semantic_confidence (the floor) is the WEAKER side's
    activity_type_confidence -- a precedence claim between two activities
    can never be more confident than the less-certain of the two activity
    types it connects (mirrors E.3's own weaker-side-is-the-floor rule)."""
    tier = tally_temporal_evidence_tier(tally)
    temporal_confidence = temporal_confidence_for_tier(tier, tally.support_count)
    repetition_confidence = _repetition_confidence(tally)
    consistency_confidence = _consistency_confidence(tally)
    conflict_penalty = _conflict_penalty(tally)
    semantic_floor = weaker_activity_type_confidence

    def _result(confidence: float, status: str) -> PrecedenceConfidenceResult:
        return PrecedenceConfidenceResult(
            precedence_confidence=confidence,
            temporal_evidence_tier=tier,
            status=status,
            semantic_confidence=semantic_floor,
            entity_participation_confidence=entity_participation_confidence,
            temporal_confidence=temporal_confidence,
            repetition_confidence=repetition_confidence,
            consistency_confidence=consistency_confidence,
            conflict_penalty=conflict_penalty,
        )

    if tally.support_count == 0:
        return _result(0.0, ProcessStatus.REVIEW_REQUIRED.value)

    if is_contradictory(tally):
        return _result(round(semantic_floor * 0.3, 4), ProcessStatus.CONFLICTED.value)

    raw_confidence = (
        semantic_floor * 0.35
        + temporal_confidence * 0.30
        + entity_participation_confidence * 0.15
        + repetition_confidence * 0.10
        + consistency_confidence * 0.10
        - conflict_penalty
    )
    precedence_confidence = round(max(min(raw_confidence, _CONFIDENCE_CAP), 0.0), 4)

    if tier == "WEAK":
        precedence_confidence = min(precedence_confidence, _STRUCTURAL_ONLY_PRECEDENCE_CAP)

    if (
        tally.same_time_count > tally.a_before_b_count
        and tally.same_time_count > tally.b_before_a_count
    ):
        return _result(precedence_confidence, ProcessStatus.REVIEW_REQUIRED.value)

    status = (
        ProcessStatus.AUTO_ACCEPTED.value
        if precedence_confidence >= 0.75
        else ProcessStatus.ACCEPTED_WITH_FLAG.value
        if precedence_confidence >= 0.4
        else ProcessStatus.REVIEW_REQUIRED.value
    )
    return _result(precedence_confidence, status)


def detect_precedence_cycles(precedes_edges: list[tuple[str, str]]) -> set[tuple[str, str]]:
    """Cycle-detection pass over the instance's directed PRECEDES graph
    (activity_type -> activity_type edges only, i.e. edges already
    resolved to PRECEDES by resolve_edge_type -- CONCURRENT/
    ORDER_UNRESOLVED edges are not graph edges here). Returns every edge
    that participates in at least one cycle, so the caller can downgrade
    those specific edges to CONFLICTED/ORDER_UNRESOLVED rather than
    presenting an impossible directed loop as authoritative precedence."""
    graph: dict[str, set[str]] = {}
    for src, dst in precedes_edges:
        graph.setdefault(src, set()).add(dst)

    edges_in_cycles: set[tuple[str, str]] = set()

    def find_path(start: str, target: str, visited: set[str]) -> list[str] | None:
        if start == target and visited:
            return [start]
        for neighbor in graph.get(start, ()):
            if neighbor in visited:
                continue
            path = find_path(neighbor, target, visited | {start})
            if path is not None:
                return [start, *path]
        return None

    for src, dst in precedes_edges:
        path = find_path(dst, src, set())
        if path is not None:
            full_cycle = [src, dst, *path[1:]]
            for k in range(len(full_cycle) - 1):
                edges_in_cycles.add((full_cycle[k], full_cycle[k + 1]))

    return edges_in_cycles


def resolve_edge_type(tally: PairTally, status: str) -> str:
    """CONCURRENT/ORDER_UNRESOLVED are real, distinct outcomes -- an edge is
    never forced into a fabricated PRECEDES direction (test G)."""
    if status == ProcessStatus.CONFLICTED.value:
        return ProcessEdgeType.ORDER_UNRESOLVED.value
    if tally.support_count == 0:
        return ProcessEdgeType.ORDER_UNRESOLVED.value
    if (
        tally.same_time_count >= tally.a_before_b_count
        and tally.same_time_count >= tally.b_before_a_count
        and tally.same_time_count > 0
    ):
        return ProcessEdgeType.CONCURRENT.value
    return ProcessEdgeType.PRECEDES.value
