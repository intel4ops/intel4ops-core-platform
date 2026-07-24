from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import Organization, OrganizationStatus
from app.schemas.contracts import OrganizationCreate, OrganizationUpdate


class OrganizationNotFoundError(ValueError):
    pass


class DuplicateOrganizationSlugError(ValueError):
    pass


class OrganizationService:
    def create(self, db: Session, payload: OrganizationCreate) -> Organization:
        if db.scalar(select(Organization.id).where(Organization.slug == payload.slug)):
            raise DuplicateOrganizationSlugError("Organization slug already exists")
        organization = Organization(**payload.model_dump())
        db.add(organization)
        self._commit(db, organization)
        return organization

    def get(self, db: Session, organization_id: UUID) -> Organization:
        organization = db.get(Organization, organization_id)
        if organization is None:
            raise OrganizationNotFoundError("Organization not found")
        return organization

    def list(self, db: Session) -> list[Organization]:
        statement = select(Organization).order_by(Organization.name, Organization.id)
        return list(db.scalars(statement).all())

    def update(
        self, db: Session, organization_id: UUID, payload: OrganizationUpdate
    ) -> Organization:
        organization = self.get(db, organization_id)
        changes = payload.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(organization, field, value)
        self._commit(db, organization)
        return organization

    def deactivate(self, db: Session, organization_id: UUID) -> Organization:
        organization = self.get(db, organization_id)
        organization.status = OrganizationStatus.INACTIVE.value
        self._commit(db, organization)
        return organization

    @staticmethod
    def _commit(db: Session, organization: Organization) -> None:
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise DuplicateOrganizationSlugError("Organization slug already exists") from exc
        db.refresh(organization)
