from __future__ import annotations

from dataclasses import dataclass, field

from app.process.activity_candidate import ActivityObservation

# ---------------------------------------------------------------------------
# P3.xxE.4: case-level activity observation context. Mirrors
# app/entities/case_entity_context.py's role exactly -- all observations
# across every dataset in the case are gathered into one flat, unordered
# structure BEFORE any grouping/sequencing happens, which is what makes
# process interpretation order-independent: no observation's treatment
# ever depends on which dataset was processed first, and (per plan review
# correction 2's row-order requirement) real timestamp VALUES are the only
# ordering signal ever consulted downstream -- never DataFrame row order.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CaseProcessContext:
    observations: list[ActivityObservation] = field(default_factory=list)

    def by_entity(self) -> dict[str, list[ActivityObservation]]:
        grouped: dict[str, list[ActivityObservation]] = {}
        for obs in self.observations:
            if obs.primary_entity_id is None:
                continue
            grouped.setdefault(obs.primary_entity_id, []).append(obs)
        return grouped

    def by_entity_type(self) -> dict[str, list[ActivityObservation]]:
        grouped: dict[str, list[ActivityObservation]] = {}
        for obs in self.observations:
            if obs.primary_entity_type is None:
                continue
            grouped.setdefault(obs.primary_entity_type, []).append(obs)
        return grouped
