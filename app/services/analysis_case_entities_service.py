from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis_case import AnalysisCaseRun
from app.models.entities_canonical import (
    CanonicalCaseEntity,
    CanonicalCaseRelationship,
    CanonicalEntityObservation,
)

# ---------------------------------------------------------------------------
# P3.xxE.3: read-only aggregator for Navigator's window into canonical
# entity/relationship resolution -- styled on
# analysis_case_semantic_service.py. Writes nothing; every row here was
# persisted by AnalysisCaseOrchestrationService during execute() (see
# _run_case_level_entity_resolution / _run_case_level_relationship_discovery).
#
# Never blends in legacy AnalysisCaseEntityLink rows -- that system has no
# read API and gains none here (plan review correction 3: the two systems'
# outputs must never be presented as one apparent canonical truth).
# ---------------------------------------------------------------------------


def _resolve_run_id(db: Session, organization_id: UUID, analysis_case_id: UUID) -> UUID | None:
    """When no run_id is supplied, use the case's latest run -- entities/
    relationships are recomputed fresh per run (never accumulated), so
    "no run_id" must mean one specific run, not a cross-run blend."""
    return db.scalar(
        select(AnalysisCaseRun.id)
        .where(
            AnalysisCaseRun.organization_id == organization_id,
            AnalysisCaseRun.analysis_case_id == analysis_case_id,
        )
        .order_by(AnalysisCaseRun.run_number.desc())
        .limit(1)
    )


class AnalysisCaseEntitiesService:
    def list_entities(
        self,
        db: Session,
        organization_id: UUID,
        analysis_case_id: UUID,
        run_id: UUID | None = None,
    ) -> tuple[UUID | None, list[CanonicalCaseEntity]]:
        resolved_run_id = run_id or _resolve_run_id(db, organization_id, analysis_case_id)
        if resolved_run_id is None:
            return None, []
        entities = list(
            db.scalars(
                select(CanonicalCaseEntity).where(
                    CanonicalCaseEntity.organization_id == organization_id,
                    CanonicalCaseEntity.analysis_case_id == analysis_case_id,
                    CanonicalCaseEntity.run_id == resolved_run_id,
                )
            ).all()
        )
        return resolved_run_id, entities

    def get_entity(
        self, db: Session, organization_id: UUID, analysis_case_id: UUID, entity_id: UUID
    ) -> tuple[CanonicalCaseEntity, list[CanonicalEntityObservation]] | None:
        entity = db.scalar(
            select(CanonicalCaseEntity).where(
                CanonicalCaseEntity.organization_id == organization_id,
                CanonicalCaseEntity.analysis_case_id == analysis_case_id,
                CanonicalCaseEntity.id == entity_id,
            )
        )
        if entity is None:
            return None
        observations = list(
            db.scalars(
                select(CanonicalEntityObservation).where(
                    CanonicalEntityObservation.organization_id == organization_id,
                    CanonicalEntityObservation.canonical_entity_id == entity_id,
                )
            ).all()
        )
        return entity, observations

    def list_relationships(
        self,
        db: Session,
        organization_id: UUID,
        analysis_case_id: UUID,
        run_id: UUID | None = None,
    ) -> tuple[UUID | None, list[CanonicalCaseRelationship]]:
        resolved_run_id = run_id or _resolve_run_id(db, organization_id, analysis_case_id)
        if resolved_run_id is None:
            return None, []
        relationships = list(
            db.scalars(
                select(CanonicalCaseRelationship).where(
                    CanonicalCaseRelationship.organization_id == organization_id,
                    CanonicalCaseRelationship.analysis_case_id == analysis_case_id,
                    CanonicalCaseRelationship.run_id == resolved_run_id,
                )
            ).all()
        )
        return resolved_run_id, relationships

    def get_relationship(
        self,
        db: Session,
        organization_id: UUID,
        analysis_case_id: UUID,
        relationship_id: UUID,
    ) -> CanonicalCaseRelationship | None:
        return db.scalar(
            select(CanonicalCaseRelationship).where(
                CanonicalCaseRelationship.organization_id == organization_id,
                CanonicalCaseRelationship.analysis_case_id == analysis_case_id,
                CanonicalCaseRelationship.id == relationship_id,
            )
        )

    def get_entity_graph(
        self,
        db: Session,
        organization_id: UUID,
        analysis_case_id: UUID,
        run_id: UUID | None = None,
    ) -> tuple[UUID | None, list[CanonicalCaseEntity], list[CanonicalCaseRelationship]]:
        resolved_run_id, entities = self.list_entities(
            db, organization_id, analysis_case_id, run_id
        )
        if resolved_run_id is None:
            return None, [], []
        _, relationships = self.list_relationships(
            db, organization_id, analysis_case_id, resolved_run_id
        )
        return resolved_run_id, entities, relationships


analysis_case_entities_service = AnalysisCaseEntitiesService()
