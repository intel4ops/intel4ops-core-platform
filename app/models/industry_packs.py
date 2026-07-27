from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.entities import portable_json, utc_now


class IndustryPackVersion(Base):
    __tablename__ = "industry_pack_versions"
    __table_args__ = (
        UniqueConstraint("pack_id", "semantic_version", name="uq_industry_pack_version"),
        CheckConstraint(
            "lifecycle_status IN "
            "('draft','validated','approved','published','deprecated','retired')",
            name="ck_industry_pack_version_lifecycle",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    pack_id: Mapped[UUID] = mapped_column(
        ForeignKey("industry_pack_definitions.id", ondelete="RESTRICT")
    )
    semantic_version: Mapped[str] = mapped_column(String(30))
    lifecycle_status: Mapped[str] = mapped_column(String(20))
    manifest_json: Mapped[dict[str, object]] = mapped_column(portable_json)
    minimum_platform_revision: Mapped[str] = mapped_column(String(32))
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_user_id: Mapped[UUID | None] = mapped_column(Uuid)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class IndustryPackComponent(Base):
    __tablename__ = "industry_pack_components"
    __table_args__ = (
        UniqueConstraint("pack_version_id", "component_type", "code", name="uq_pack_component"),
        CheckConstraint(
            "component_type IN "
            "('ontology_mapping','canonical_extension','metric_definition','rule_binding',"
            "'evidence_policy','economic_mapping','recovery_playbook','command_capability',"
            "'usage_meter_binding')",
            name="ck_pack_component_type",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    pack_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("industry_pack_versions.id", ondelete="CASCADE")
    )
    component_type: Mapped[str] = mapped_column(String(40))
    code: Mapped[str] = mapped_column(String(150))
    universal_parent: Mapped[str] = mapped_column(String(180))
    configuration: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class IndustryPackValidationResult(Base):
    __tablename__ = "industry_pack_validation_results"
    __table_args__ = (Index("ix_pack_validation_version_time", "pack_version_id", "created_at"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    pack_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("industry_pack_versions.id", ondelete="CASCADE")
    )
    valid: Mapped[bool] = mapped_column(Boolean)
    errors_json: Mapped[list[object]] = mapped_column(portable_json, default=list)
    validator_version: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class IndustryPackAssignmentState(Base):
    __tablename__ = "industry_pack_assignment_states"
    __table_args__ = (
        UniqueConstraint("assignment_id", name="uq_pack_assignment_state"),
        Index("ix_pack_assignment_state_org_status", "organization_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    assignment_id: Mapped[UUID] = mapped_column(
        ForeignKey("industry_pack_assignments.id", ondelete="CASCADE")
    )
    pack_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("industry_pack_versions.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(30))
    configuration_overrides: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    entitlement_snapshot: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IndustryPackExecution(Base):
    __tablename__ = "industry_pack_executions"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_pack_execution_key"),
        Index("ix_pack_execution_org_time", "organization_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    assignment_id: Mapped[UUID] = mapped_column(
        ForeignKey("industry_pack_assignments.id", ondelete="RESTRICT")
    )
    pack_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("industry_pack_versions.id", ondelete="RESTRICT")
    )
    idempotency_key: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30))
    readiness: Mapped[str] = mapped_column(String(30))
    input_json: Mapped[dict[str, object]] = mapped_column(portable_json)
    result_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IndustryPackGovernanceEvent(Base):
    __tablename__ = "industry_pack_governance_events"
    __table_args__ = (Index("ix_pack_governance_version_time", "pack_version_id", "created_at"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    pack_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("industry_pack_versions.id", ondelete="RESTRICT")
    )
    event_type: Mapped[str] = mapped_column(String(50))
    actor_user_id: Mapped[UUID] = mapped_column(Uuid)
    reason: Mapped[str] = mapped_column(String(1000))
    event_payload: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


def _guard_published(*args: object) -> None:
    target = args[-1]
    if isinstance(target, IndustryPackVersion) and target.lifecycle_status in {
        "published",
        "deprecated",
        "retired",
    }:
        raise ValueError("published industry-pack versions are immutable")


def _immutable(*_: object) -> None:
    raise ValueError("industry-pack governance events are immutable")


event.listen(IndustryPackVersion, "before_delete", _guard_published)
event.listen(IndustryPackGovernanceEvent, "before_update", _immutable)
event.listen(IndustryPackGovernanceEvent, "before_delete", _immutable)
