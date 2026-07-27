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
    Text,
    UniqueConstraint,
    Uuid,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.entities import portable_json, utc_now


class ValidationScenarioVersion(Base):
    __tablename__ = "validation_scenario_versions"
    __table_args__ = (
        UniqueConstraint("scenario_code", "version", name="uq_validation_scenario_version"),
        CheckConstraint(
            "lifecycle_status IN ('draft','validated','approved','active','deprecated','retired')",
            name="ck_validation_scenario_lifecycle",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    scenario_code: Mapped[str] = mapped_column(String(80))
    version: Mapped[str] = mapped_column(String(30))
    industry_pack_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("industry_pack_versions.id", ondelete="RESTRICT")
    )
    display_name: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text)
    seed: Mapped[int]
    generator_reference: Mapped[str] = mapped_column(String(255))
    manifest_json: Mapped[dict[str, object]] = mapped_column(portable_json)
    lifecycle_status: Mapped[str] = mapped_column(String(20))
    owner: Mapped[str] = mapped_column(String(120))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ValidationOracleVersion(Base):
    __tablename__ = "validation_oracle_versions"
    __table_args__ = (
        UniqueConstraint("scenario_version_id", "version", name="uq_validation_oracle_version"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    scenario_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("validation_scenario_versions.id", ondelete="CASCADE")
    )
    version: Mapped[str] = mapped_column(String(30))
    assertions_json: Mapped[list[object]] = mapped_column(portable_json)
    evidence_contract_json: Mapped[dict[str, object]] = mapped_column(portable_json)
    approved: Mapped[bool] = mapped_column(Boolean)
    owner: Mapped[str] = mapped_column(String(120))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ValidationSuite(Base):
    __tablename__ = "validation_suites"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(80), unique=True)
    display_name: Mapped[str] = mapped_column(String(160))
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    configuration: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)


class ValidationRun(Base):
    __tablename__ = "validation_runs"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_validation_run_key"),
        Index("ix_validation_run_org_commit", "organization_id", "commit_sha"),
        CheckConstraint(
            "status IN ('queued','running','passed','passed_with_warning','failed','blocked',"
            "'cancelled')",
            name="ck_validation_run_status",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    suite_id: Mapped[UUID] = mapped_column(ForeignKey("validation_suites.id", ondelete="RESTRICT"))
    scenario_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("validation_scenario_versions.id", ondelete="RESTRICT")
    )
    release_candidate_id: Mapped[UUID | None] = mapped_column(Uuid)
    idempotency_key: Mapped[str] = mapped_column(String(255))
    environment: Mapped[str] = mapped_column(String(40))
    commit_sha: Mapped[str] = mapped_column(String(64))
    branch: Mapped[str] = mapped_column(String(255))
    migration_head: Mapped[str] = mapped_column(String(64))
    versions_json: Mapped[dict[str, object]] = mapped_column(portable_json)
    database_engine: Mapped[str] = mapped_column(String(30))
    seed: Mapped[int | None]
    status: Mapped[str] = mapped_column(String(30))
    result_json: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    evidence_references: Mapped[list[object]] = mapped_column(portable_json, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AnalyticalArtifactVersion(Base):
    __tablename__ = "analytical_artifact_versions"
    __table_args__ = (
        UniqueConstraint("artifact_type", "artifact_key", "version", name="uq_artifact_version"),
        CheckConstraint(
            "lifecycle_status IN ('draft','under_review','validated','approved','active',"
            "'suspended','deprecated','retired')",
            name="ck_artifact_governance_lifecycle",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    artifact_type: Mapped[str] = mapped_column(String(50))
    artifact_key: Mapped[str] = mapped_column(String(180))
    version: Mapped[str] = mapped_column(String(30))
    lifecycle_status: Mapped[str] = mapped_column(String(20))
    owner: Mapped[str] = mapped_column(String(120))
    business_purpose: Mapped[str] = mapped_column(Text)
    target_outcome: Mapped[str] = mapped_column(Text)
    governance_json: Mapped[dict[str, object]] = mapped_column(portable_json)
    validation_evidence: Mapped[list[object]] = mapped_column(portable_json, default=list)
    monitoring_policy: Mapped[dict[str, object]] = mapped_column(portable_json)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ReleaseCandidate(Base):
    __tablename__ = "release_candidates"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "commit_sha", "environment", name="uq_release_candidate"
        ),
        Index("ix_release_candidate_org_status", "organization_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    commit_sha: Mapped[str] = mapped_column(String(64))
    branch: Mapped[str] = mapped_column(String(255))
    environment: Mapped[str] = mapped_column(String(40))
    migration_head: Mapped[str] = mapped_column(String(64))
    platform_version: Mapped[str] = mapped_column(String(30))
    configuration_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default="draft")
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ReleaseGateDefinition(Base):
    __tablename__ = "release_gate_definitions"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(100), unique=True)
    suite_code: Mapped[str] = mapped_column(String(80))
    mandatory: Mapped[bool] = mapped_column(Boolean)
    waivable: Mapped[bool] = mapped_column(Boolean)
    failure_policy: Mapped[str] = mapped_column(String(30))
    configuration: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)


class ReleaseGateResult(Base):
    __tablename__ = "release_gate_results"
    __table_args__ = (
        UniqueConstraint("release_candidate_id", "gate_id", name="uq_release_gate_result"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    release_candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("release_candidates.id", ondelete="CASCADE")
    )
    gate_id: Mapped[UUID] = mapped_column(
        ForeignKey("release_gate_definitions.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(30))
    summary: Mapped[str] = mapped_column(Text)
    evidence_hash: Mapped[str] = mapped_column(String(64))
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ReleaseWaiver(Base):
    __tablename__ = "release_waivers"
    __table_args__ = (
        UniqueConstraint("release_candidate_id", "gate_id", name="uq_release_waiver_gate"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    release_candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("release_candidates.id", ondelete="CASCADE")
    )
    gate_id: Mapped[UUID] = mapped_column(
        ForeignKey("release_gate_definitions.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(30))
    justification: Mapped[str] = mapped_column(Text)
    compensating_control: Mapped[str] = mapped_column(Text)
    approved_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ReleaseCertification(Base):
    __tablename__ = "release_certifications"
    __table_args__ = (
        UniqueConstraint("release_candidate_id", name="uq_release_certification_candidate"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    release_candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("release_candidates.id", ondelete="RESTRICT")
    )
    decision: Mapped[str] = mapped_column(String(40))
    report_json: Mapped[dict[str, object]] = mapped_column(portable_json)
    report_hash: Mapped[str] = mapped_column(String(64))
    issued_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


def _immutable(*_: object) -> None:
    raise ValueError("governed certification records are immutable")


for immutable_model in (
    ValidationScenarioVersion,
    ValidationOracleVersion,
    ValidationRun,
    ReleaseGateResult,
    ReleaseCertification,
):
    event.listen(immutable_model, "before_update", _immutable)
    event.listen(immutable_model, "before_delete", _immutable)
