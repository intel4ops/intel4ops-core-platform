from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.intelligence_packs.registry import (
    IntelligencePackDefinition,
    default_intelligence_pack_registry,
)
from app.models.analysis_case import AnalysisCaseRun
from app.models.intelligence_activation import IntelligenceActivationDecision

# ---------------------------------------------------------------------------
# P3.xxE.5 Phase 1 (SHADOW): read-only aggregator for Navigator's window
# into capability declarations, readiness, activation decisions, and
# shadow comparisons -- styled directly on analysis_case_entities_service.py
# / analysis_case_process_service.py. Writes nothing; every persisted row
# here was written by AnalysisCaseOrchestrationService during execute()
# (see _run_case_level_capability_shadow_evaluation).
# ---------------------------------------------------------------------------


def _resolve_run_id(db: Session, organization_id: UUID, analysis_case_id: UUID) -> UUID | None:
    return db.scalar(
        select(AnalysisCaseRun.id)
        .where(
            AnalysisCaseRun.organization_id == organization_id,
            AnalysisCaseRun.analysis_case_id == analysis_case_id,
        )
        .order_by(AnalysisCaseRun.run_number.desc())
        .limit(1)
    )


class AnalysisCaseCapabilityService:
    def list_capabilities(self) -> list[IntelligencePackDefinition]:
        return default_intelligence_pack_registry().all()

    def list_activation_decisions(
        self,
        db: Session,
        organization_id: UUID,
        analysis_case_id: UUID,
        run_id: UUID | None = None,
    ) -> tuple[UUID | None, list[IntelligenceActivationDecision]]:
        resolved_run_id = run_id or _resolve_run_id(db, organization_id, analysis_case_id)
        if resolved_run_id is None:
            return None, []
        decisions = list(
            db.scalars(
                select(IntelligenceActivationDecision).where(
                    IntelligenceActivationDecision.organization_id == organization_id,
                    IntelligenceActivationDecision.analysis_case_id == analysis_case_id,
                    IntelligenceActivationDecision.run_id == resolved_run_id,
                )
            ).all()
        )
        return resolved_run_id, decisions

    def shadow_comparison_summary(
        self,
        db: Session,
        organization_id: UUID,
        analysis_case_id: UUID,
        run_id: UUID | None = None,
    ) -> tuple[UUID | None, list[IntelligenceActivationDecision]]:
        resolved_run_id, decisions = self.list_activation_decisions(
            db, organization_id, analysis_case_id, run_id
        )
        shadow_decisions = [d for d in decisions if d.mode == "shadow"]
        return resolved_run_id, shadow_decisions


analysis_case_capability_service = AnalysisCaseCapabilityService()
