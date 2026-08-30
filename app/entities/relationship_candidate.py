from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# P3.xxE.3: ephemeral relationship candidate objects. Confidence is
# decomposed into named components, all persisted separately on
# CanonicalRelationship (plan review correction 1) -- see
# app/entities/confidence_decomposition.py for how relationship_confidence
# is composed from these without a universal semantic-confidence ceiling.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RelationshipConfidence:
    left_entity_identity_confidence: float
    right_entity_identity_confidence: float
    structural_evidence_confidence: float
    relationship_confidence: float


@dataclass(frozen=True)
class RelationshipCandidate:
    left_entity_type: str
    left_normalized_key: str
    right_entity_type: str
    right_normalized_key: str
    relationship_type: str
    cardinality: str
    confidence: RelationshipConfidence
    status: str
    evidence_summary: list[str] = field(default_factory=list)
    conflict_reason: str | None = None
