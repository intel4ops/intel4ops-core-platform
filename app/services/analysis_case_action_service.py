from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis_case import AnalysisCaseAction, AnalysisCaseActionFinding
from app.models.entities import Finding


class AnalysisCaseActionServiceError(ValueError):
    def __init__(self, message: str, *, code: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class AnalysisCaseActionService:
    def create(
        self,
        db: Session,
        organization_id: UUID,
        analysis_case_id: UUID,
        finding_ids: list[UUID],
        title: str,
        description: str | None,
        owner: str | None,
        priority: str | None,
        due_date: object,
        actor_user_id: UUID,
    ) -> AnalysisCaseAction:
        for finding_id in finding_ids:
            finding = db.scalar(
                select(Finding).where(
                    Finding.id == finding_id, Finding.organization_id == organization_id
                )
            )
            if finding is None:
                raise AnalysisCaseActionServiceError(
                    "Finding not found", code="finding_not_found", status=404
                )
        action = AnalysisCaseAction(
            organization_id=organization_id,
            analysis_case_id=analysis_case_id,
            title=title,
            description=description,
            owner=owner,
            priority=priority,
            due_date=due_date,
            created_by_user_id=actor_user_id,
        )
        db.add(action)
        db.flush()
        for finding_id in finding_ids:
            db.add(
                AnalysisCaseActionFinding(
                    organization_id=organization_id, action_id=action.id, finding_id=finding_id
                )
            )
        db.commit()
        db.refresh(action)
        return action

    def list(
        self, db: Session, organization_id: UUID, analysis_case_id: UUID
    ) -> list[AnalysisCaseAction]:
        return list(
            db.scalars(
                select(AnalysisCaseAction)
                .where(
                    AnalysisCaseAction.organization_id == organization_id,
                    AnalysisCaseAction.analysis_case_id == analysis_case_id,
                )
                .order_by(AnalysisCaseAction.created_at.desc())
            ).all()
        )

    def update_status(
        self,
        db: Session,
        organization_id: UUID,
        action_id: UUID,
        status: str,
        owner: str | None = None,
    ) -> AnalysisCaseAction:
        action = db.scalar(
            select(AnalysisCaseAction).where(
                AnalysisCaseAction.id == action_id,
                AnalysisCaseAction.organization_id == organization_id,
            )
        )
        if action is None:
            raise AnalysisCaseActionServiceError(
                "Action not found", code="action_not_found", status=404
            )
        action.status = status
        if owner is not None:
            action.owner = owner
        db.commit()
        db.refresh(action)
        return action


analysis_case_action_service = AnalysisCaseActionService()
