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
    event,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.entities import portable_json, utc_now

SIGNATURE_LIFECYCLE = (
    "hypothesis",
    "candidate",
    "observed",
    "validated",
    "approved",
    "production",
    "suspended",
    "deprecated",
    "retired",
)


class OperationalFeatureDefinition(Base):
    __tablename__ = "operational_feature_definitions"
    __table_args__ = (
        CheckConstraint(
            "lifecycle_status IN "
            "('draft','under_review','approved','active','suspended','deprecated','retired')",
            name="ck_operational_feature_lifecycle",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(180), unique=True)
    name: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text)
    lifecycle_status: Mapped[str] = mapped_column(String(30), default="draft")
    owner: Mapped[str] = mapped_column(String(120))
    tags: Mapped[list[str]] = mapped_column(portable_json, default=list)
    documentation_reference: Mapped[str] = mapped_column(String(500))
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OperationalFeatureVersion(Base):
    __tablename__ = "operational_feature_versions"
    __table_args__ = (
        UniqueConstraint("feature_id", "semantic_version", name="uq_operational_feature_version"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    feature_id: Mapped[UUID] = mapped_column(
        ForeignKey("operational_feature_definitions.id", ondelete="RESTRICT")
    )
    semantic_version: Mapped[str] = mapped_column(String(30))
    entity_grain: Mapped[str] = mapped_column(String(100))
    time_grain: Mapped[str | None] = mapped_column(String(50))
    value_type: Mapped[str] = mapped_column(String(40))
    unit_behavior: Mapped[str] = mapped_column(String(40))
    currency_behavior: Mapped[str] = mapped_column(String(40))
    required_canonical_objects: Mapped[list[str]] = mapped_column(portable_json)
    input_contract: Mapped[dict[str, object]] = mapped_column(portable_json)
    computation_reference: Mapped[dict[str, object]] = mapped_column(portable_json)
    validation_contract: Mapped[dict[str, object]] = mapped_column(portable_json)
    known_limitations: Mapped[list[str]] = mapped_column(portable_json, default=list)
    approved_by_user_id: Mapped[UUID | None] = mapped_column(Uuid)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OperationalSignatureDefinition(Base):
    __tablename__ = "operational_signature_definitions"
    __table_args__ = (
        CheckConstraint(
            "signature_type IN "
            "('failure','leakage','fraud','recovery','operational_performance','behavioral',"
            "'predictive','prescriptive','composite','cross_domain','industry_specific')",
            name="ck_operational_signature_type",
        ),
        CheckConstraint(
            "lifecycle_status IN "
            "('hypothesis','candidate','observed','validated','approved','production',"
            "'suspended','deprecated','retired')",
            name="ck_operational_signature_lifecycle",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(180), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    signature_type: Mapped[str] = mapped_column(String(40))
    industry: Mapped[str] = mapped_column(String(100))
    lifecycle_status: Mapped[str] = mapped_column(String(30), default="hypothesis")
    canonical_governance_status: Mapped[str] = mapped_column(String(30), default="draft")
    owner: Mapped[str] = mapped_column(String(120))
    tags: Mapped[list[str]] = mapped_column(portable_json, default=list)
    documentation_reference: Mapped[str] = mapped_column(String(500))
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OperationalSignatureVersion(Base):
    __tablename__ = "operational_signature_versions"
    __table_args__ = (
        UniqueConstraint("signature_id", "semantic_version", name="uq_signature_version"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    signature_id: Mapped[UUID] = mapped_column(
        ForeignKey("operational_signature_definitions.id", ondelete="RESTRICT")
    )
    semantic_version: Mapped[str] = mapped_column(String(30))
    applicable_pack_versions: Mapped[list[str]] = mapped_column(portable_json)
    required_canonical_objects: Mapped[list[str]] = mapped_column(portable_json)
    required_features: Mapped[list[object]] = mapped_column(portable_json)
    required_events: Mapped[list[object]] = mapped_column(portable_json)
    required_conditions: Mapped[list[object]] = mapped_column(portable_json)
    exclusion_conditions: Mapped[list[object]] = mapped_column(portable_json)
    evidence_requirements: Mapped[list[object]] = mapped_column(portable_json)
    confidence_model: Mapped[dict[str, object]] = mapped_column(portable_json)
    economic_impact_policy: Mapped[dict[str, object]] = mapped_column(portable_json)
    expected_outcome: Mapped[dict[str, object]] = mapped_column(portable_json)
    supporting_algorithms: Mapped[list[str]] = mapped_column(portable_json, default=list)
    supporting_rules: Mapped[list[str]] = mapped_column(portable_json, default=list)
    supporting_models: Mapped[list[str]] = mapped_column(portable_json, default=list)
    dependencies: Mapped[list[object]] = mapped_column(portable_json, default=list)
    monitoring_policy: Mapped[dict[str, object]] = mapped_column(portable_json)
    known_limitations: Mapped[list[str]] = mapped_column(portable_json)
    definition_hash: Mapped[str] = mapped_column(String(64), unique=True)
    approved_by_user_id: Mapped[UUID | None] = mapped_column(Uuid)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OperationalSignatureValidation(Base):
    __tablename__ = "operational_signature_validations"
    __table_args__ = (
        UniqueConstraint(
            "signature_version_id", "validation_run_id", name="uq_signature_validation_run"
        ),
        Index("ix_signature_validation_version_time", "signature_version_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    signature_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("operational_signature_versions.id", ondelete="CASCADE")
    )
    validation_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("validation_runs.id", ondelete="SET NULL")
    )
    scenario_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("validation_scenario_versions.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(30))
    metrics: Mapped[dict[str, object]] = mapped_column(portable_json)
    false_positive_count: Mapped[int] = mapped_column(Integer, default=0)
    false_negative_count: Mapped[int] = mapped_column(Integer, default=0)
    evidence_references: Mapped[list[object]] = mapped_column(portable_json)
    limitations: Mapped[list[str]] = mapped_column(portable_json, default=list)
    reviewer_user_id: Mapped[UUID | None] = mapped_column(Uuid)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OperationalSignatureLifecycleEvent(Base):
    __tablename__ = "operational_signature_lifecycle_events"
    __table_args__ = (
        UniqueConstraint("signature_id", "idempotency_key", name="uq_signature_lifecycle_key"),
        Index("ix_signature_lifecycle_time", "signature_id", "occurred_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    signature_id: Mapped[UUID] = mapped_column(
        ForeignKey("operational_signature_definitions.id", ondelete="RESTRICT")
    )
    prior_status: Mapped[str | None] = mapped_column(String(30))
    new_status: Mapped[str] = mapped_column(String(30))
    actor_user_id: Mapped[UUID] = mapped_column(Uuid)
    actor_role: Mapped[str] = mapped_column(String(50))
    reason: Mapped[str] = mapped_column(Text)
    approval_reference: Mapped[str | None] = mapped_column(String(255))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OperationalSignatureDeployment(Base):
    __tablename__ = "operational_signature_deployments"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "signature_version_id",
            "environment",
            name="uq_signature_deployment",
        ),
        Index("ix_signature_deployment_org_status", "organization_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    signature_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("operational_signature_versions.id", ondelete="RESTRICT")
    )
    environment: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30))
    calibration: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    entitlement_snapshot: Mapped[dict[str, object]] = mapped_column(portable_json)
    deployed_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    deployed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OperationalSignatureExecution(Base):
    __tablename__ = "operational_signature_executions"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_signature_execution_key"),
        Index("ix_signature_execution_org_time", "organization_id", "started_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    deployment_id: Mapped[UUID] = mapped_column(
        ForeignKey("operational_signature_deployments.id", ondelete="RESTRICT")
    )
    signature_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("operational_signature_versions.id", ondelete="RESTRICT")
    )
    orchestration_request_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("intelligence_orchestration_requests.id", ondelete="SET NULL")
    )
    idempotency_key: Mapped[str] = mapped_column(String(255))
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30))
    matched: Mapped[bool | None] = mapped_column(Boolean)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(8, 7))
    result_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    explanation: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    finding_id: Mapped[UUID | None] = mapped_column(ForeignKey("findings.id", ondelete="SET NULL"))
    error_code: Mapped[str | None] = mapped_column(String(80))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OperationalSignatureExecutionEvidence(Base):
    __tablename__ = "operational_signature_execution_evidence"
    __table_args__ = (
        Index("ix_signature_execution_evidence_org", "organization_id", "execution_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("operational_signature_executions.id", ondelete="CASCADE")
    )
    evidence_type: Mapped[str] = mapped_column(String(60))
    source_type: Mapped[str] = mapped_column(String(60))
    source_identifier: Mapped[str] = mapped_column(String(500))
    lineage_node_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("lineage_nodes.id", ondelete="SET NULL")
    )
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    integrity_fingerprint: Mapped[str] = mapped_column(String(128))
    metadata_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OperationalSignaturePerformanceSnapshot(Base):
    __tablename__ = "operational_signature_performance_history"
    __table_args__ = (
        UniqueConstraint(
            "signature_version_id",
            "organization_id",
            "period_start",
            "period_end",
            name="uq_signature_performance_period",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    signature_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("operational_signature_versions.id", ondelete="RESTRICT")
    )
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    execution_count: Mapped[int] = mapped_column(Integer)
    match_count: Mapped[int] = mapped_column(Integer)
    confirmed_positive_count: Mapped[int] = mapped_column(Integer)
    false_positive_count: Mapped[int] = mapped_column(Integer)
    false_negative_count: Mapped[int] = mapped_column(Integer)
    precision: Mapped[Decimal | None] = mapped_column(Numeric(8, 7))
    recall: Mapped[Decimal | None] = mapped_column(Numeric(8, 7))
    economic_impact: Mapped[Decimal | None] = mapped_column(Numeric(38, 12))
    currency_code: Mapped[str | None] = mapped_column(String(3))
    metrics_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OperationalSignatureMonitoringResult(Base):
    __tablename__ = "operational_signature_monitoring_results"
    __table_args__ = (
        Index("ix_signature_monitoring_version_time", "signature_version_id", "evaluated_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    signature_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("operational_signature_versions.id", ondelete="RESTRICT")
    )
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    metric_code: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30))
    observed_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12))
    threshold_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12))
    sample_size: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(40))
    evidence_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


def _immutable(*_: object) -> None:
    raise ValueError("published operational intelligence history is immutable")


for immutable_model in (
    OperationalFeatureVersion,
    OperationalSignatureVersion,
    OperationalSignatureValidation,
    OperationalSignatureLifecycleEvent,
    OperationalSignatureExecutionEvidence,
    OperationalSignaturePerformanceSnapshot,
    OperationalSignatureMonitoringResult,
):
    event.listen(immutable_model, "before_update", _immutable)
    event.listen(immutable_model, "before_delete", _immutable)
