from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis_case import AnalysisCaseDataset
from app.models.semantic import (
    SemanticDatasetProfile,
    SemanticInterpretationDecision,
    SemanticRoleInterpretation,
)

# Read-only aggregator (styled on analysis_case_command_service.py) --
# Navigator's window into P3.xxE.1 semantic interpretation results. Writes
# nothing; every row here was persisted by AnalysisCaseOrchestrationService
# during execute() (see _run_semantic_interpretation).


@dataclass(frozen=True)
class DatasetSemanticView:
    analysis_case_dataset_id: UUID
    dataset_id: UUID
    source_label: str
    profile: SemanticDatasetProfile | None
    role: SemanticRoleInterpretation | None
    field_decisions: list[SemanticInterpretationDecision]


class AnalysisCaseSemanticService:
    def get_case_semantic_view(
        self, db: Session, organization_id: UUID, analysis_case_id: UUID, run_id: UUID | None = None
    ) -> list[DatasetSemanticView]:
        case_datasets = list(
            db.scalars(
                select(AnalysisCaseDataset).where(
                    AnalysisCaseDataset.organization_id == organization_id,
                    AnalysisCaseDataset.analysis_case_id == analysis_case_id,
                )
            ).all()
        )
        views = []
        for case_dataset in case_datasets:
            profile_stmt = select(SemanticDatasetProfile).where(
                SemanticDatasetProfile.organization_id == organization_id,
                SemanticDatasetProfile.analysis_case_dataset_id == case_dataset.id,
            )
            role_stmt = select(SemanticRoleInterpretation).where(
                SemanticRoleInterpretation.organization_id == organization_id,
                SemanticRoleInterpretation.analysis_case_dataset_id == case_dataset.id,
            )
            decisions_stmt = select(SemanticInterpretationDecision).where(
                SemanticInterpretationDecision.organization_id == organization_id,
                SemanticInterpretationDecision.analysis_case_dataset_id == case_dataset.id,
            )
            if run_id is not None:
                profile_stmt = profile_stmt.where(SemanticDatasetProfile.run_id == run_id)
                role_stmt = role_stmt.where(SemanticRoleInterpretation.run_id == run_id)
                decisions_stmt = decisions_stmt.where(
                    SemanticInterpretationDecision.run_id == run_id
                )
            else:
                profile_stmt = profile_stmt.order_by(SemanticDatasetProfile.computed_at.desc())
                role_stmt = role_stmt.order_by(SemanticRoleInterpretation.computed_at.desc())
                decisions_stmt = decisions_stmt.order_by(
                    SemanticInterpretationDecision.created_at.desc()
                )

            profile = db.scalars(profile_stmt).first()
            role = db.scalars(role_stmt).first()
            decisions = list(db.scalars(decisions_stmt).all())
            if run_id is None:
                # Latest-run-only view: keep just the most recent decision
                # per field (mirrors AnalysisCaseDataset.mapping_status's
                # own "recomputed fresh, never accumulated" convention).
                latest_by_field: dict[str, SemanticInterpretationDecision] = {}
                for decision in decisions:
                    if decision.source_field not in latest_by_field:
                        latest_by_field[decision.source_field] = decision
                decisions = list(latest_by_field.values())

            views.append(
                DatasetSemanticView(
                    analysis_case_dataset_id=case_dataset.id,
                    dataset_id=case_dataset.dataset_id,
                    source_label=case_dataset.source_label,
                    profile=profile,
                    role=role,
                    field_decisions=decisions,
                )
            )
        return views


analysis_case_semantic_service = AnalysisCaseSemanticService()
