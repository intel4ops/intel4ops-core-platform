from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Finding, FindingEvidence, Organization, OrganizationStatus
from app.schemas.contracts import FindingCreate


class FindingService:
    def create(self, db: Session, organization_id: UUID, payload: FindingCreate) -> Finding:
        organization = db.scalar(
            select(Organization).where(
                Organization.id == organization_id,
                Organization.status == OrganizationStatus.ACTIVE.value,
            )
        )
        if organization is None:
            raise ValueError("Active organization not found")
        finding = Finding(
            organization_id=organization_id, **payload.model_dump(exclude={"evidence"})
        )
        for item in payload.evidence:
            finding.evidence.append(
                FindingEvidence(organization_id=organization_id, **item.model_dump())
            )
        db.add(finding)
        db.commit()
        db.refresh(finding)
        return finding

    def list(self, db: Session, organization_id: UUID) -> list[Finding]:
        statement = (
            select(Finding)
            .where(Finding.organization_id == organization_id)
            .order_by(Finding.created_at.desc())
        )
        return list(db.scalars(statement).all())
