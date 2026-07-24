from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import Organization, utc_now
from app.models.source_system import (
    DataClassification,
    IntegrationMethod,
    SourceEnvironment,
    SourceHealthStatus,
    SourceSystem,
    SourceSystemStatus,
    SourceSystemType,
)
from app.schemas.source_systems import SourceSystemCreate, SourceSystemUpdate


class SourceSystemNotFoundError(ValueError):
    pass


class SourceSystemOrganizationNotFoundError(ValueError):
    pass


class DuplicateSourceSystemCodeError(ValueError):
    pass


class InvalidSourceSystemTransitionError(ValueError):
    pass


ALLOWED_TRANSITIONS: dict[SourceSystemStatus, set[SourceSystemStatus]] = {
    SourceSystemStatus.DRAFT: {
        SourceSystemStatus.CONFIGURED,
        SourceSystemStatus.DECOMMISSIONED,
    },
    SourceSystemStatus.CONFIGURED: {
        SourceSystemStatus.VALIDATING,
        SourceSystemStatus.DECOMMISSIONED,
    },
    SourceSystemStatus.VALIDATING: {
        SourceSystemStatus.ACTIVE,
        SourceSystemStatus.FAILED,
    },
    SourceSystemStatus.ACTIVE: {
        SourceSystemStatus.PAUSED,
        SourceSystemStatus.FAILED,
        SourceSystemStatus.DECOMMISSIONED,
    },
    SourceSystemStatus.PAUSED: {
        SourceSystemStatus.ACTIVE,
        SourceSystemStatus.DECOMMISSIONED,
    },
    SourceSystemStatus.FAILED: {
        SourceSystemStatus.VALIDATING,
        SourceSystemStatus.PAUSED,
        SourceSystemStatus.DECOMMISSIONED,
    },
    SourceSystemStatus.DECOMMISSIONED: set(),
}


class SourceSystemService:
    def create(
        self,
        db: Session,
        organization_id: UUID,
        payload: SourceSystemCreate,
        actor_user_id: UUID,
    ) -> SourceSystem:
        if db.get(Organization, organization_id) is None:
            raise SourceSystemOrganizationNotFoundError("Organization not found")
        duplicate = db.scalar(
            select(SourceSystem.id).where(
                SourceSystem.organization_id == organization_id,
                SourceSystem.code == payload.code,
            )
        )
        if duplicate is not None:
            raise DuplicateSourceSystemCodeError("Source system code already exists")
        values = payload.model_dump(mode="json")
        source_system = SourceSystem(
            organization_id=organization_id,
            created_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
            **values,
        )
        db.add(source_system)
        self._commit(db, source_system)
        return source_system

    def list(
        self,
        db: Session,
        organization_id: UUID,
        *,
        system_type: SourceSystemType | None = None,
        provider: str | None = None,
        integration_method: IntegrationMethod | None = None,
        environment: SourceEnvironment | None = None,
        status: SourceSystemStatus | None = None,
        health_status: SourceHealthStatus | None = None,
        data_classification: DataClassification | None = None,
        is_active: bool | None = None,
        search: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[SourceSystem]:
        statement = select(SourceSystem).where(SourceSystem.organization_id == organization_id)
        filters = {
            SourceSystem.system_type: system_type,
            SourceSystem.provider: provider.lower() if provider else None,
            SourceSystem.integration_method: integration_method,
            SourceSystem.environment: environment,
            SourceSystem.status: status,
            SourceSystem.health_status: health_status,
            SourceSystem.data_classification: data_classification,
            SourceSystem.is_active: is_active,
        }
        for column, value in filters.items():
            if value is not None:
                normalized = value.value if hasattr(value, "value") else value
                statement = statement.where(column == normalized)
        if search:
            term = f"%{search.strip()}%"
            statement = statement.where(
                or_(SourceSystem.name.ilike(term), SourceSystem.code.ilike(term))
            )
        statement = (
            statement.order_by(SourceSystem.name, SourceSystem.id).offset(offset).limit(limit)
        )
        return list(db.scalars(statement).all())

    def get(
        self,
        db: Session,
        organization_id: UUID,
        source_system_id: UUID,
        *,
        for_update: bool = False,
    ) -> SourceSystem:
        statement = select(SourceSystem).where(
            SourceSystem.id == source_system_id,
            SourceSystem.organization_id == organization_id,
        )
        if for_update:
            statement = statement.with_for_update()
        source_system = db.scalar(statement)
        if source_system is None:
            raise SourceSystemNotFoundError("Source system not found")
        return source_system

    def update(
        self,
        db: Session,
        organization_id: UUID,
        source_system_id: UUID,
        payload: SourceSystemUpdate,
        actor_user_id: UUID,
    ) -> SourceSystem:
        source_system = self.get(db, organization_id, source_system_id, for_update=True)
        changes = payload.model_dump(exclude_unset=True, mode="json")
        requested_status = changes.pop("status", None)
        if requested_status is not None:
            self._transition(source_system, SourceSystemStatus(requested_status))
        for field, value in changes.items():
            setattr(source_system, field, value)
        source_system.updated_by_user_id = actor_user_id
        self._commit(db, source_system)
        return source_system

    def pause(
        self, db: Session, organization_id: UUID, source_system_id: UUID, actor_user_id: UUID
    ) -> SourceSystem:
        return self._change_status(
            db, organization_id, source_system_id, SourceSystemStatus.PAUSED, actor_user_id
        )

    def reactivate(
        self, db: Session, organization_id: UUID, source_system_id: UUID, actor_user_id: UUID
    ) -> SourceSystem:
        return self._change_status(
            db, organization_id, source_system_id, SourceSystemStatus.ACTIVE, actor_user_id
        )

    def decommission(
        self, db: Session, organization_id: UUID, source_system_id: UUID, actor_user_id: UUID
    ) -> SourceSystem:
        source_system = self.get(db, organization_id, source_system_id, for_update=True)
        self._transition(source_system, SourceSystemStatus.DECOMMISSIONED)
        source_system.is_active = False
        source_system.deactivated_at = utc_now()
        source_system.updated_by_user_id = actor_user_id
        self._commit(db, source_system)
        return source_system

    def record_connection_success(
        self, db: Session, organization_id: UUID, source_system_id: UUID, actor_user_id: UUID
    ) -> SourceSystem:
        source_system = self.get(db, organization_id, source_system_id, for_update=True)
        self._ensure_not_decommissioned(source_system)
        now = utc_now()
        source_system.last_connection_attempt_at = now
        source_system.last_connection_success_at = now
        source_system.last_health_check_at = now
        source_system.failure_count = 0
        source_system.health_status = SourceHealthStatus.HEALTHY.value
        if SourceSystemStatus(source_system.status) in {
            SourceSystemStatus.VALIDATING,
            SourceSystemStatus.PAUSED,
        }:
            self._transition(source_system, SourceSystemStatus.ACTIVE)
        source_system.updated_by_user_id = actor_user_id
        self._commit(db, source_system)
        return source_system

    def record_connection_failure(
        self, db: Session, organization_id: UUID, source_system_id: UUID, actor_user_id: UUID
    ) -> SourceSystem:
        source_system = self.get(db, organization_id, source_system_id, for_update=True)
        self._ensure_not_decommissioned(source_system)
        now = utc_now()
        source_system.last_connection_attempt_at = now
        source_system.last_connection_failure_at = now
        source_system.last_health_check_at = now
        source_system.failure_count += 1
        source_system.health_status = (
            SourceHealthStatus.UNHEALTHY.value
            if source_system.failure_count >= 3
            else SourceHealthStatus.DEGRADED.value
        )
        source_system.updated_by_user_id = actor_user_id
        self._commit(db, source_system)
        return source_system

    def update_health(
        self,
        db: Session,
        organization_id: UUID,
        source_system_id: UUID,
        health_status: SourceHealthStatus,
        actor_user_id: UUID,
    ) -> SourceSystem:
        source_system = self.get(db, organization_id, source_system_id, for_update=True)
        self._ensure_not_decommissioned(source_system)
        source_system.health_status = health_status.value
        source_system.last_health_check_at = utc_now()
        source_system.updated_by_user_id = actor_user_id
        self._commit(db, source_system)
        return source_system

    def _change_status(
        self,
        db: Session,
        organization_id: UUID,
        source_system_id: UUID,
        target: SourceSystemStatus,
        actor_user_id: UUID,
    ) -> SourceSystem:
        source_system = self.get(db, organization_id, source_system_id, for_update=True)
        self._transition(source_system, target)
        source_system.updated_by_user_id = actor_user_id
        self._commit(db, source_system)
        return source_system

    @staticmethod
    def _transition(source_system: SourceSystem, target: SourceSystemStatus) -> None:
        current = SourceSystemStatus(source_system.status)
        if target not in ALLOWED_TRANSITIONS[current]:
            raise InvalidSourceSystemTransitionError(
                f"Cannot transition source system from {current.value} to {target.value}"
            )
        source_system.status = target.value

    @staticmethod
    def _ensure_not_decommissioned(source_system: SourceSystem) -> None:
        if source_system.status == SourceSystemStatus.DECOMMISSIONED.value:
            raise InvalidSourceSystemTransitionError(
                "Decommissioned source systems cannot be changed"
            )

    @staticmethod
    def _commit(db: Session, source_system: SourceSystem) -> None:
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise DuplicateSourceSystemCodeError("Source system code already exists") from exc
        db.refresh(source_system)


source_system_service = SourceSystemService()
