from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Finding, FindingStatus, RecoveryAction
from app.schemas.contracts import RecoveryActionCreate


class RecoveryService:
    def create(
        self, db: Session, organization_id: UUID, payload: RecoveryActionCreate
    ) -> RecoveryAction:
        finding = db.scalar(
            select(Finding).where(
                Finding.id == payload.finding_id,
                Finding.organization_id == organization_id,
            )
        )
        if not finding:
            raise ValueError("Finding not found")
        action = RecoveryAction(organization_id=organization_id, **payload.model_dump())
        finding.status = FindingStatus.IN_RECOVERY.value
        db.add(action)
        db.commit()
        db.refresh(action)
        return action
