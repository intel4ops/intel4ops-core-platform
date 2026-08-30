from __future__ import annotations

from app.semantic.concept_registry import CanonicalConceptRegistry

# ---------------------------------------------------------------------------
# P3.xxE.3 section 7: entity type inference -- semantic-first (Invariant C),
# NEVER from raw source field names. The only input is a governed
# effective semantic concept code; the only output vocabulary is
# app/entities/entity_type.py::EntityType.
# ---------------------------------------------------------------------------


def infer_entity_type(
    effective_concept: str | None,
    registry: CanonicalConceptRegistry,
) -> str | None:
    """Returns None (never a guessed default) when:
    - there is no effective concept at all (unresolved/review-required field)
    - the concept is unknown or inactive in the registry
    - the concept's compatible_entity_types is empty or has more than one
      value (genuine ambiguity is never silently resolved to one type --
      matches CanonicalConceptRegistry.find_by_alias's own philosophy)
    """
    if effective_concept is None:
        return None
    concept = registry.get(effective_concept)
    if concept is None or not concept.active:
        return None
    if len(concept.compatible_entity_types) != 1:
        return None
    return next(iter(concept.compatible_entity_types))
