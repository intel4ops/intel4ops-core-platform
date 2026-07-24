from sqlalchemy.orm import Session

from app.models.entities import Finding, FindingStatus, RecoveryAction
from app.schemas.contracts import RecoveryActionCreate


class RecoveryService:
    def create(self, db: Session, payload: RecoveryActionCreate) -> RecoveryAction:
        finding = db.get(Finding, payload.finding_id)
        if not finding:
            raise ValueError("Finding not found")
        action = RecoveryAction(**payload.model_dump())
        finding.status = FindingStatus.IN_RECOVERY.value
        db.add(action)
        db.commit()
        db.refresh(action)
        return action
