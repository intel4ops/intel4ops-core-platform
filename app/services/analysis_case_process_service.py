from __future__ import annotations

from collections import Counter
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis_case import AnalysisCaseRun
from app.models.process_canonical import (
    CanonicalOperationalProcess,
    CanonicalProcessActivity,
    CanonicalProcessEdge,
)

# ---------------------------------------------------------------------------
# P3.xxE.4: read-only aggregator for Navigator's window into process
# interpretation -- styled directly on analysis_case_entities_service.py.
# Writes nothing; every row here was persisted by
# AnalysisCaseOrchestrationService during execute() (see
# _run_case_level_process_interpretation).
# ---------------------------------------------------------------------------


def _resolve_run_id(db: Session, organization_id: UUID, analysis_case_id: UUID) -> UUID | None:
    """When no run_id is supplied, use the case's latest run -- process
    instances are recomputed fresh per run (never accumulated), so "no
    run_id" must mean one specific run, not a cross-run blend."""
    return db.scalar(
        select(AnalysisCaseRun.id)
        .where(
            AnalysisCaseRun.organization_id == organization_id,
            AnalysisCaseRun.analysis_case_id == analysis_case_id,
        )
        .order_by(AnalysisCaseRun.run_number.desc())
        .limit(1)
    )


class AnalysisCaseProcessService:
    def list_processes(
        self,
        db: Session,
        organization_id: UUID,
        analysis_case_id: UUID,
        run_id: UUID | None = None,
    ) -> tuple[UUID | None, list[CanonicalOperationalProcess]]:
        resolved_run_id = run_id or _resolve_run_id(db, organization_id, analysis_case_id)
        if resolved_run_id is None:
            return None, []
        processes = list(
            db.scalars(
                select(CanonicalOperationalProcess).where(
                    CanonicalOperationalProcess.organization_id == organization_id,
                    CanonicalOperationalProcess.analysis_case_id == analysis_case_id,
                    CanonicalOperationalProcess.run_id == resolved_run_id,
                )
            ).all()
        )
        return resolved_run_id, processes

    def get_process(
        self, db: Session, organization_id: UUID, analysis_case_id: UUID, process_id: UUID
    ) -> (
        tuple[
            CanonicalOperationalProcess, list[CanonicalProcessActivity], list[CanonicalProcessEdge]
        ]
        | None
    ):
        process = db.scalar(
            select(CanonicalOperationalProcess).where(
                CanonicalOperationalProcess.organization_id == organization_id,
                CanonicalOperationalProcess.analysis_case_id == analysis_case_id,
                CanonicalOperationalProcess.id == process_id,
            )
        )
        if process is None:
            return None
        activities, edges = self._activities_and_edges(db, organization_id, process_id)
        return process, activities, edges

    def _activities_and_edges(
        self, db: Session, organization_id: UUID, process_id: UUID
    ) -> tuple[list[CanonicalProcessActivity], list[CanonicalProcessEdge]]:
        activities = list(
            db.scalars(
                select(CanonicalProcessActivity).where(
                    CanonicalProcessActivity.organization_id == organization_id,
                    CanonicalProcessActivity.process_id == process_id,
                )
            ).all()
        )
        edges = list(
            db.scalars(
                select(CanonicalProcessEdge).where(
                    CanonicalProcessEdge.organization_id == organization_id,
                    CanonicalProcessEdge.process_id == process_id,
                )
            ).all()
        )
        return activities, edges

    def list_activities(
        self, db: Session, organization_id: UUID, process_id: UUID
    ) -> list[CanonicalProcessActivity]:
        activities, _ = self._activities_and_edges(db, organization_id, process_id)
        return activities

    def get_activity(
        self, db: Session, organization_id: UUID, analysis_case_id: UUID, activity_id: UUID
    ) -> CanonicalProcessActivity | None:
        return db.scalar(
            select(CanonicalProcessActivity)
            .join(
                CanonicalOperationalProcess,
                CanonicalProcessActivity.process_id == CanonicalOperationalProcess.id,
            )
            .where(
                CanonicalProcessActivity.organization_id == organization_id,
                CanonicalOperationalProcess.analysis_case_id == analysis_case_id,
                CanonicalProcessActivity.id == activity_id,
            )
        )

    def list_edges(
        self, db: Session, organization_id: UUID, process_id: UUID
    ) -> list[CanonicalProcessEdge]:
        _, edges = self._activities_and_edges(db, organization_id, process_id)
        return edges

    def get_edge(
        self, db: Session, organization_id: UUID, analysis_case_id: UUID, edge_id: UUID
    ) -> CanonicalProcessEdge | None:
        return db.scalar(
            select(CanonicalProcessEdge)
            .join(
                CanonicalOperationalProcess,
                CanonicalProcessEdge.process_id == CanonicalOperationalProcess.id,
            )
            .where(
                CanonicalProcessEdge.organization_id == organization_id,
                CanonicalOperationalProcess.analysis_case_id == analysis_case_id,
                CanonicalProcessEdge.id == edge_id,
            )
        )

    def get_process_graph(
        self,
        db: Session,
        organization_id: UUID,
        analysis_case_id: UUID,
        run_id: UUID | None = None,
    ) -> tuple[UUID | None, list[CanonicalProcessActivity], list[CanonicalProcessEdge]]:
        resolved_run_id, processes = self.list_processes(
            db, organization_id, analysis_case_id, run_id
        )
        if resolved_run_id is None:
            return None, [], []
        process_ids = [p.id for p in processes]
        if not process_ids:
            return resolved_run_id, [], []
        activities = list(
            db.scalars(
                select(CanonicalProcessActivity).where(
                    CanonicalProcessActivity.organization_id == organization_id,
                    CanonicalProcessActivity.process_id.in_(process_ids),
                )
            ).all()
        )
        edges = list(
            db.scalars(
                select(CanonicalProcessEdge).where(
                    CanonicalProcessEdge.organization_id == organization_id,
                    CanonicalProcessEdge.process_id.in_(process_ids),
                )
            ).all()
        )
        return resolved_run_id, activities, edges

    def get_process_graph_summary(
        self,
        db: Session,
        organization_id: UUID,
        analysis_case_id: UUID,
        run_id: UUID | None = None,
    ) -> tuple[UUID | None, int, int, int, dict[str, int], dict[str, int], dict[str, int]]:
        resolved_run_id, processes = self.list_processes(
            db, organization_id, analysis_case_id, run_id
        )
        if resolved_run_id is None:
            return None, 0, 0, 0, {}, {}, {}
        _, activities, edges = self.get_process_graph(
            db, organization_id, analysis_case_id, resolved_run_id
        )
        boundary_status_counts = Counter(p.boundary_status for p in processes)
        status_counts = Counter(p.status for p in processes)
        activity_type_counts = Counter(a.activity_type for a in activities)
        return (
            resolved_run_id,
            len(processes),
            len(activities),
            len(edges),
            dict(boundary_status_counts),
            dict(status_counts),
            dict(activity_type_counts),
        )


analysis_case_process_service = AnalysisCaseProcessService()
