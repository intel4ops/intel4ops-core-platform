from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Finding, FindingEvidence
from app.schemas.contracts import FindingCreate


class FindingService:
    def create(self, db: Session, payload: FindingCreate) -> Finding:
        finding = Finding(**payload.model_dump(exclude={"evidence"}))
        for item in payload.evidence:
            finding.evidence.append(FindingEvidence(**item.model_dump()))
        db.add(finding)
        db.commit()
        db.refresh(finding)
        return finding

    def list(self, db: Session) -> list[Finding]:
        return list(db.scalars(select(Finding).order_by(Finding.created_at.desc())).all())
