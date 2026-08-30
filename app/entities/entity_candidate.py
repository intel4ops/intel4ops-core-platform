from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# P3.xxE.3 sections 5/6: ephemeral entity observation + candidate objects.
# Mirrors app/semantic/candidate.py's convention exactly -- cheap, in-memory
# dataclasses; only the resolved CanonicalEntity + a bounded evidence
# summary are durable (see app/models/entities_canonical.py). Named
# EntityObservation here (ephemeral) vs. CanonicalEntityObservation (the
# ORM row it maps onto) -- deliberately distinct names, same pattern as
# InterpretationDecision (ephemeral) vs. SemanticInterpretationDecision
# (ORM).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EntityObservation:
    """One field's contribution toward a candidate entity. Framework-free
    (no UUID import) -- all identifiers are strings, matching
    app/semantic/case_context.py's own convention."""

    analysis_case_dataset_id: str
    dataset_label: str
    source_field: str
    concept_code: str
    entity_type: str
    raw_value: str
    normalized_value: str
    semantic_confidence: float
    semantic_source: str
    human_validated: bool


@dataclass(frozen=True)
class EntityCandidate:
    """One resolved entity within a case -- all observations grouped under
    a single (entity_type, normalized_key) identity. entity_type_confidence
    and entity_identity_confidence are DISTINCT and neither caps the other
    (see app/entities/confidence_decomposition.py)."""

    entity_type: str
    normalized_key: str
    display_label: str
    resolution_method: str
    observations: list[EntityObservation] = field(default_factory=list)
    entity_type_confidence: float = 0.0
    entity_identity_confidence: float = 0.0
    evidence_summary: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FuzzyCandidateScore:
    """Contracts + scoring only (P3.xxE.3 section 12's explicit escape
    hatch) -- never merged into an EntityCandidate, never persisted as a
    row. Only its count/summary is logged for observability. See
    app/entities/entity_resolution_tiers.py::score_fuzzy_candidates."""

    entity_type: str
    left_key: str
    right_key: str
    score: float
    fields_compared: list[str]
