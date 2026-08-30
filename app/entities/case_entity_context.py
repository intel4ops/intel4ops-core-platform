from __future__ import annotations

from dataclasses import dataclass, field

from app.entities.entity_candidate import EntityObservation

# ---------------------------------------------------------------------------
# P3.xxE.3: case-level entity observation context. Mirrors
# app/semantic/case_context.py's CaseSemanticContext role exactly -- all
# observations across every dataset in the case are gathered into one
# flat, unordered structure BEFORE any grouping/dedup happens, which is
# what makes entity resolution order-independent: no observation's
# treatment ever depends on which dataset was processed first.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CaseEntityContext:
    observations: list[EntityObservation] = field(default_factory=list)

    def by_entity_type(self) -> dict[str, list[EntityObservation]]:
        grouped: dict[str, list[EntityObservation]] = {}
        for obs in self.observations:
            grouped.setdefault(obs.entity_type, []).append(obs)
        return grouped
