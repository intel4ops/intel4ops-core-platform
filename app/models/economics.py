from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.engines.economics_engine import OpportunityStatus
from app.models.entities import portable_json, utc_now
from app.models.source_system import enum_values


class RecoveryOpportunity(Base):
    __tablename__ = "recovery_opportunities"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "idempotency_key", name="uq_recovery_opportunity_idempotency"
        ),
        UniqueConstraint(
            "organization_id", "economic_source_key", name="uq_recovery_opportunity_source"
        ),
        CheckConstraint(
            f"status IN ({enum_values(OpportunityStatus)})", name="ck_recovery_opportunity_status"
        ),
        Index("ix_recovery_opportunity_org_status", "organization_id", "status"),
        Index("ix_recovery_opportunity_org_priority", "organization_id", "priority_category"),
        Index("ix_recovery_opportunity_org_currency", "organization_id", "currency_code"),
        Index("ix_recovery_opportunity_org_domain", "organization_id", "business_domain"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    opportunity_code: Mapped[str] = mapped_column(String(40), unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(255))
    economic_source_key: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(250))
    description: Mapped[str] = mapped_column(Text)
    business_domain: Mapped[str | None] = mapped_column(String(100), nullable=True)
    site_reference: Mapped[str | None] = mapped_column(String(150), nullable=True)
    industry_pack_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    capability_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    owner_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default=OpportunityStatus.DRAFT.value)
    priority_category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    selected_scenario_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    current_baseline_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency_code: Mapped[str] = mapped_column(String(3))
    limitations: Mapped[list[str]] = mapped_column(portable_json, default=list)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class OpportunityFinding(Base):
    __tablename__ = "opportunity_findings"
    __table_args__ = (
        UniqueConstraint("opportunity_id", "finding_id", name="uq_opportunity_finding"),
        Index("ix_opportunity_finding_org", "organization_id", "opportunity_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    opportunity_id: Mapped[UUID] = mapped_column(
        ForeignKey("recovery_opportunities.id", ondelete="CASCADE")
    )
    finding_id: Mapped[UUID] = mapped_column(ForeignKey("findings.id", ondelete="RESTRICT"))
    allocation_percentage: Mapped[Decimal] = mapped_column(Numeric(8, 7), default=Decimal("1"))
    relationship_type: Mapped[str] = mapped_column(String(40), default="contributes")
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OpportunityAction(Base):
    __tablename__ = "opportunity_actions"
    __table_args__ = (
        UniqueConstraint("opportunity_id", "action_id", name="uq_opportunity_action"),
        Index("ix_opportunity_action_org", "organization_id", "opportunity_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    opportunity_id: Mapped[UUID] = mapped_column(
        ForeignKey("recovery_opportunities.id", ondelete="CASCADE")
    )
    action_id: Mapped[UUID] = mapped_column(
        ForeignKey("operational_actions.id", ondelete="RESTRICT")
    )
    relationship_type: Mapped[str] = mapped_column(String(40), default="proposed")
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EconomicScenario(Base):
    __tablename__ = "economic_scenarios"
    __table_args__ = (
        UniqueConstraint("opportunity_id", "scenario_code", "version", name="uq_scenario_version"),
        CheckConstraint(
            "lower_exposure <= gross_exposure AND gross_exposure <= upper_exposure",
            name="ck_scenario_exposure_bounds",
        ),
        CheckConstraint(
            "addressability_rate BETWEEN 0 AND 1 AND recoverability_rate BETWEEN 0 AND 1 "
            "AND success_probability BETWEEN 0 AND 1 AND scenario_probability BETWEEN 0 AND 1",
            name="ck_scenario_rates",
        ),
        Index("ix_economic_scenario_org_opportunity", "organization_id", "opportunity_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    opportunity_id: Mapped[UUID] = mapped_column(
        ForeignKey("recovery_opportunities.id", ondelete="CASCADE")
    )
    scenario_code: Mapped[str] = mapped_column(String(40))
    version: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(150))
    currency_code: Mapped[str] = mapped_column(String(3))
    lower_exposure: Mapped[Decimal] = mapped_column(Numeric(38, 12))
    gross_exposure: Mapped[Decimal] = mapped_column(Numeric(38, 12))
    upper_exposure: Mapped[Decimal] = mapped_column(Numeric(38, 12))
    addressability_rate: Mapped[Decimal] = mapped_column(Numeric(8, 7))
    recoverability_rate: Mapped[Decimal] = mapped_column(Numeric(8, 7))
    success_probability: Mapped[Decimal] = mapped_column(Numeric(8, 7))
    recovery_cost: Mapped[Decimal] = mapped_column(Numeric(38, 12))
    benefit_period_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scenario_probability: Mapped[Decimal] = mapped_column(Numeric(8, 7), default=Decimal("1"))
    measurement_period: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mutually_exclusive_group: Mapped[str | None] = mapped_column(String(100), nullable=True)
    assumptions_summary: Mapped[list[str]] = mapped_column(portable_json, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EconomicAssumption(Base):
    __tablename__ = "economic_assumptions"
    __table_args__ = (
        UniqueConstraint(
            "opportunity_id", "assumption_code", "version", name="uq_assumption_version"
        ),
        Index("ix_economic_assumption_org_opportunity", "organization_id", "opportunity_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    opportunity_id: Mapped[UUID] = mapped_column(
        ForeignKey("recovery_opportunities.id", ondelete="CASCADE")
    )
    scenario_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("economic_scenarios.id", ondelete="CASCADE"), nullable=True
    )
    assumption_code: Mapped[str] = mapped_column(String(100))
    version: Mapped[int] = mapped_column(Integer)
    value: Mapped[Decimal] = mapped_column(Numeric(38, 12))
    unit: Mapped[str] = mapped_column(String(50))
    currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    source: Mapped[str] = mapped_column(String(100))
    source_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    evidence_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(8, 7))
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    model_version: Mapped[str] = mapped_column(String(30))
    superseded: Mapped[bool] = mapped_column(Boolean, default=False)
    entered_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    approved_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EconomicCalculation(Base):
    __tablename__ = "economic_calculations"
    __table_args__ = (
        UniqueConstraint(
            "opportunity_id", "idempotency_key", name="uq_economic_calculation_idempotency"
        ),
        Index("ix_economic_calculation_org_opportunity", "organization_id", "opportunity_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    opportunity_id: Mapped[UUID] = mapped_column(
        ForeignKey("recovery_opportunities.id", ondelete="CASCADE")
    )
    scenario_id: Mapped[UUID] = mapped_column(
        ForeignKey("economic_scenarios.id", ondelete="RESTRICT")
    )
    idempotency_key: Mapped[str] = mapped_column(String(255))
    calculation_version: Mapped[str] = mapped_column(String(30))
    currency_code: Mapped[str] = mapped_column(String(3))
    gross_exposure: Mapped[Decimal] = mapped_column(Numeric(38, 12))
    addressable_exposure: Mapped[Decimal] = mapped_column(Numeric(38, 12))
    expected_recoverable_value: Mapped[Decimal] = mapped_column(Numeric(38, 12))
    probability_adjusted_value: Mapped[Decimal] = mapped_column(Numeric(38, 12))
    recovery_cost: Mapped[Decimal] = mapped_column(Numeric(38, 12))
    expected_net_benefit: Mapped[Decimal] = mapped_column(Numeric(38, 12))
    expected_roi: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    payback_period_days: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    zero_cost_policy: Mapped[str] = mapped_column(String(40))
    input_snapshot: Mapped[dict[str, object]] = mapped_column(portable_json)
    limitations: Mapped[list[str]] = mapped_column(portable_json, default=list)
    calculated_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PrioritizationAssessment(Base):
    __tablename__ = "prioritization_assessments"
    __table_args__ = (
        UniqueConstraint("opportunity_id", "idempotency_key", name="uq_prioritization_idempotency"),
        Index("ix_prioritization_org_score", "organization_id", "priority_score"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    opportunity_id: Mapped[UUID] = mapped_column(
        ForeignKey("recovery_opportunities.id", ondelete="CASCADE")
    )
    calculation_id: Mapped[UUID] = mapped_column(
        ForeignKey("economic_calculations.id", ondelete="RESTRICT")
    )
    idempotency_key: Mapped[str] = mapped_column(String(255))
    profile_code: Mapped[str] = mapped_column(String(100))
    model_name: Mapped[str] = mapped_column(String(100))
    model_version: Mapped[str] = mapped_column(String(30))
    factor_weights: Mapped[dict[str, str]] = mapped_column(portable_json)
    normalized_factors: Mapped[dict[str, str]] = mapped_column(portable_json)
    factor_contributions: Mapped[dict[str, str]] = mapped_column(portable_json)
    priority_score: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    priority_category: Mapped[str] = mapped_column(String(40))
    calculation_reason: Mapped[str] = mapped_column(Text)
    limitations: Mapped[list[str]] = mapped_column(portable_json, default=list)
    source_references: Mapped[list[dict[str, object]]] = mapped_column(portable_json, default=list)
    calculated_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OpportunityOverlapGroup(Base):
    __tablename__ = "opportunity_overlap_groups"
    __table_args__ = (
        UniqueConstraint("organization_id", "overlap_key", name="uq_opportunity_overlap_group_key"),
        Index("ix_overlap_group_org_status", "organization_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    overlap_key: Mapped[str] = mapped_column(String(255))
    overlap_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(30), default="active")
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class OpportunityOverlapMember(Base):
    __tablename__ = "opportunity_overlap_members"
    __table_args__ = (
        UniqueConstraint("overlap_group_id", "opportunity_id", name="uq_overlap_member"),
        CheckConstraint(
            "allocation_percentage BETWEEN 0 AND 1", name="ck_overlap_member_allocation"
        ),
        Index("ix_overlap_member_org_group", "organization_id", "overlap_group_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    overlap_group_id: Mapped[UUID] = mapped_column(
        ForeignKey("opportunity_overlap_groups.id", ondelete="CASCADE")
    )
    opportunity_id: Mapped[UUID] = mapped_column(
        ForeignKey("recovery_opportunities.id", ondelete="RESTRICT")
    )
    parent_opportunity_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("recovery_opportunities.id", ondelete="RESTRICT"), nullable=True
    )
    allocation_percentage: Mapped[Decimal] = mapped_column(Numeric(8, 7))
    inclusion_status: Mapped[str] = mapped_column(String(30), default="included")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OpportunityDecision(Base):
    __tablename__ = "opportunity_decisions"
    __table_args__ = (
        UniqueConstraint(
            "opportunity_id", "idempotency_key", name="uq_opportunity_decision_idempotency"
        ),
        Index("ix_opportunity_decision_org_opportunity", "organization_id", "opportunity_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    opportunity_id: Mapped[UUID] = mapped_column(
        ForeignKey("recovery_opportunities.id", ondelete="CASCADE")
    )
    idempotency_key: Mapped[str] = mapped_column(String(255))
    prior_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    decision: Mapped[str] = mapped_column(String(40))
    decision_reason: Mapped[str] = mapped_column(Text)
    actor_user_id: Mapped[UUID] = mapped_column(Uuid)
    actor_role: Mapped[str] = mapped_column(String(50))
    scenario_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("economic_scenarios.id", ondelete="RESTRICT"), nullable=True
    )
    baseline_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conditions: Mapped[list[str]] = mapped_column(portable_json, default=list)
    review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EconomicAuditEvent(Base):
    __tablename__ = "economic_audit_events"
    __table_args__ = (
        UniqueConstraint("opportunity_id", "idempotency_key", name="uq_economic_audit_idempotency"),
        Index("ix_economic_audit_org_opportunity", "organization_id", "opportunity_id"),
        Index("ix_economic_audit_event_type", "organization_id", "event_type"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    opportunity_id: Mapped[UUID] = mapped_column(
        ForeignKey("recovery_opportunities.id", ondelete="CASCADE")
    )
    event_type: Mapped[str] = mapped_column(String(60))
    actor_user_id: Mapped[UUID] = mapped_column(Uuid)
    idempotency_key: Mapped[str] = mapped_column(String(255))
    reason: Mapped[str] = mapped_column(Text)
    event_payload: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EconomicBaselineVersion(Base):
    __tablename__ = "economic_baseline_versions"
    __table_args__ = (
        UniqueConstraint("opportunity_id", "version", name="uq_economic_baseline_version"),
        UniqueConstraint(
            "opportunity_id", "idempotency_key", name="uq_economic_baseline_idempotency"
        ),
        Index("ix_economic_baseline_org_opportunity", "organization_id", "opportunity_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    opportunity_id: Mapped[UUID] = mapped_column(
        ForeignKey("recovery_opportunities.id", ondelete="RESTRICT")
    )
    scenario_id: Mapped[UUID] = mapped_column(
        ForeignKey("economic_scenarios.id", ondelete="RESTRICT")
    )
    calculation_id: Mapped[UUID] = mapped_column(
        ForeignKey("economic_calculations.id", ondelete="RESTRICT")
    )
    prioritization_id: Mapped[UUID] = mapped_column(
        ForeignKey("prioritization_assessments.id", ondelete="RESTRICT")
    )
    version: Mapped[int] = mapped_column(Integer)
    idempotency_key: Mapped[str] = mapped_column(String(255))
    currency_code: Mapped[str] = mapped_column(String(3))
    economic_snapshot: Mapped[dict[str, object]] = mapped_column(portable_json)
    assumption_versions: Mapped[list[dict[str, object]]] = mapped_column(portable_json)
    approved_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    supersedes_baseline_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("economic_baseline_versions.id", ondelete="RESTRICT"), nullable=True
    )
