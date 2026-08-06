from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
    inspect,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.entities import portable_json, utc_now
from app.models.source_system import enum_values


class DecisionScopeType(StrEnum):
    SHARED_CORE = "shared_core"
    INDUSTRY = "industry"
    REGIONAL = "regional"
    ORGANIZATION = "organization"


class DecisionDefinitionStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


class DecisionProblemStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


class DecisionProblemVersionStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    SUPERSEDED = "superseded"
    RETIRED = "retired"


class DecisionScenarioStatus(StrEnum):
    DRAFT = "draft"
    VALIDATING = "validating"
    READY = "ready"
    BLOCKED = "blocked"
    EXECUTING = "executing"
    COMPLETED = "completed"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"


class DecisionExecutionStatus(StrEnum):
    QUEUED = "queued"
    VALIDATING = "validating"
    BLOCKED = "blocked"
    RUNNING = "running"
    SOLVED_OPTIMAL = "solved_optimal"
    SOLVED_FEASIBLE = "solved_feasible"
    INFEASIBLE = "infeasible"
    UNBOUNDED = "unbounded"
    TIMED_OUT = "timed_out"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DecisionRecommendationStatus(StrEnum):
    PROPOSED = "proposed"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    REJECTED = "rejected"
    CONVERTED_TO_ACTION = "converted_to_action"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"


class DecisionApprovalDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    DEFER = "defer"
    REQUEST_CHANGES = "request_changes"


class DecisionMethodDefinition(Base):
    __tablename__ = "decision_method_definitions"
    __table_args__ = (
        UniqueConstraint(
            "method_code",
            "method_version",
            "scope_key",
            name="uq_decision_method_code_version_scope",
        ),
        CheckConstraint(
            f"scope_type IN ({enum_values(DecisionScopeType)})",
            name="ck_decision_method_scope_type",
        ),
        CheckConstraint(
            f"lifecycle_status IN ({enum_values(DecisionDefinitionStatus)})",
            name="ck_decision_method_status",
        ),
        Index("ix_decision_method_code", "method_code"),
        Index("ix_decision_method_class", "method_class"),
        Index("ix_decision_method_owner", "owner_organization_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    method_code: Mapped[str] = mapped_column(String(150))
    method_name: Mapped[str] = mapped_column(String(250))
    method_class: Mapped[str] = mapped_column(String(80))
    method_version: Mapped[str] = mapped_column(String(30))
    solver_adapter: Mapped[str] = mapped_column(String(100))
    solver_adapter_version: Mapped[str] = mapped_column(String(30))
    supported_variable_types: Mapped[list[str]] = mapped_column(portable_json, default=list)
    supported_constraint_types: Mapped[list[str]] = mapped_column(portable_json, default=list)
    supported_objective_types: Mapped[list[str]] = mapped_column(portable_json, default=list)
    parameter_schema: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    deterministic: Mapped[bool] = mapped_column(Boolean, default=True)
    exact_or_heuristic: Mapped[str] = mapped_column(String(30))
    optimality_guarantee: Mapped[str] = mapped_column(String(120))
    default_time_limit_seconds: Mapped[int] = mapped_column(Integer)
    max_supported_problem_size: Mapped[int] = mapped_column(Integer)
    lifecycle_status: Mapped[str] = mapped_column(String(30), default="draft")
    scope_type: Mapped[str] = mapped_column(String(30), default="shared_core")
    scope_key: Mapped[str] = mapped_column(String(180), default="shared_core")
    owner_organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True
    )
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class DecisionProblem(Base):
    __tablename__ = "decision_problems"
    __table_args__ = (
        UniqueConstraint("problem_code", "scope_key", name="uq_decision_problem_code_scope"),
        CheckConstraint(
            f"scope_type IN ({enum_values(DecisionScopeType)})",
            name="ck_decision_problem_scope_type",
        ),
        CheckConstraint(
            f"lifecycle_status IN ({enum_values(DecisionProblemStatus)})",
            name="ck_decision_problem_status",
        ),
        Index("ix_decision_problem_code", "problem_code"),
        Index("ix_decision_problem_owner", "owner_organization_id"),
        Index("ix_decision_problem_status", "lifecycle_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    problem_code: Mapped[str] = mapped_column(String(150))
    problem_name: Mapped[str] = mapped_column(String(250))
    use_case_code: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    scope_type: Mapped[str] = mapped_column(String(30))
    scope_key: Mapped[str] = mapped_column(String(180))
    owner_organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True
    )
    lifecycle_status: Mapped[str] = mapped_column(String(30), default="draft")
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class DecisionProblemVersion(Base):
    __tablename__ = "decision_problem_versions"
    __table_args__ = (
        UniqueConstraint("problem_id", "version", name="uq_decision_problem_version"),
        CheckConstraint(
            f"lifecycle_status IN ({enum_values(DecisionProblemVersionStatus)})",
            name="ck_decision_problem_version_status",
        ),
        Index("ix_decision_problem_version_problem", "problem_id", "lifecycle_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    problem_id: Mapped[UUID] = mapped_column(
        ForeignKey("decision_problems.id", ondelete="RESTRICT")
    )
    version: Mapped[str] = mapped_column(String(30))
    lifecycle_status: Mapped[str] = mapped_column(String(30), default="draft")
    objective_strategy: Mapped[str] = mapped_column(String(50))
    input_contract: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    output_contract: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    assumptions: Mapped[list[str]] = mapped_column(portable_json, default=list)
    limitations: Mapped[list[str]] = mapped_column(portable_json, default=list)
    content_hash: Mapped[str] = mapped_column(String(64))
    supersedes_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("decision_problem_versions.id", ondelete="RESTRICT"), nullable=True
    )
    published_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DecisionObjective(Base):
    __tablename__ = "decision_objectives"
    __table_args__ = (
        UniqueConstraint("problem_version_id", "objective_code", name="uq_decision_objective_code"),
        CheckConstraint("weight >= 0", name="ck_decision_objective_weight"),
        Index("ix_decision_objective_problem_version", "problem_version_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    problem_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("decision_problem_versions.id", ondelete="CASCADE")
    )
    objective_code: Mapped[str] = mapped_column(String(120))
    objective_type: Mapped[str] = mapped_column(String(50))
    direction: Mapped[str] = mapped_column(String(20))
    source_metric: Mapped[str] = mapped_column(String(150))
    weight: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=Decimal("1"))
    priority_order: Mapped[int] = mapped_column(Integer, default=1)
    unit_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    parameters: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DecisionConstraint(Base):
    __tablename__ = "decision_constraints"
    __table_args__ = (
        UniqueConstraint(
            "problem_version_id", "constraint_code", name="uq_decision_constraint_code"
        ),
        Index("ix_decision_constraint_problem_version", "problem_version_id"),
        Index("ix_decision_constraint_type", "constraint_type"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    problem_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("decision_problem_versions.id", ondelete="CASCADE")
    )
    constraint_code: Mapped[str] = mapped_column(String(120))
    constraint_type: Mapped[str] = mapped_column(String(80))
    operator: Mapped[str] = mapped_column(String(10))
    right_hand_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    hard_constraint: Mapped[bool] = mapped_column(Boolean, default=True)
    unit_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    expression: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DecisionVariableDefinition(Base):
    __tablename__ = "decision_variable_definitions"
    __table_args__ = (
        UniqueConstraint("problem_version_id", "variable_code", name="uq_decision_variable_code"),
        Index("ix_decision_variable_problem_version", "problem_version_id"),
        Index("ix_decision_variable_type", "variable_type"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    problem_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("decision_problem_versions.id", ondelete="CASCADE")
    )
    variable_code: Mapped[str] = mapped_column(String(120))
    variable_type: Mapped[str] = mapped_column(String(40))
    lower_bound: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    upper_bound: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    unit_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    domain_contract: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DecisionScenario(Base):
    __tablename__ = "decision_scenarios"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_decision_scenarios_org_id"),
        UniqueConstraint(
            "organization_id", "idempotency_key", name="uq_decision_scenario_idempotency"
        ),
        CheckConstraint(
            f"lifecycle_status IN ({enum_values(DecisionScenarioStatus)})",
            name="ck_decision_scenario_status",
        ),
        Index("ix_decision_scenario_org_status", "organization_id", "lifecycle_status"),
        Index(
            "ix_decision_scenario_org_problem",
            "organization_id",
            "problem_version_id",
        ),
        Index("ix_decision_scenario_fingerprint", "organization_id", "scenario_fingerprint"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    problem_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("decision_problem_versions.id", ondelete="RESTRICT")
    )
    method_definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("decision_method_definitions.id", ondelete="RESTRICT")
    )
    scenario_name: Mapped[str] = mapped_column(String(250))
    lifecycle_status: Mapped[str] = mapped_column(String(30), default="draft")
    scenario_horizon_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scenario_horizon_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(80))
    currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    scenario_fingerprint: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    validation_status: Mapped[str] = mapped_column(String(30), default="pending")
    gate_reasons: Mapped[list[dict[str, object]]] = mapped_column(portable_json, default=list)
    superseded_by_scenario_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class DecisionScenarioInput(Base):
    __tablename__ = "decision_scenario_inputs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "scenario_id"],
            ["decision_scenarios.organization_id", "decision_scenarios.id"],
            name="fk_decision_scenario_inputs_org_scenario",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "scenario_id", "input_kind", "source_id", name="uq_decision_scenario_input_source"
        ),
        Index("ix_decision_scenario_input_org_scenario", "organization_id", "scenario_id"),
        Index(
            "ix_decision_scenario_input_kind",
            "organization_id",
            "scenario_id",
            "input_kind",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    scenario_id: Mapped[UUID] = mapped_column(Uuid)
    input_kind: Mapped[str] = mapped_column(String(80))
    source_id: Mapped[UUID] = mapped_column(Uuid)
    source_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_fingerprint: Mapped[str] = mapped_column(String(64))
    mapping_confidence: Mapped[Decimal | None] = mapped_column(Numeric(6, 5), nullable=True)
    trust_readiness_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    input_payload: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    validation_flags: Mapped[list[str]] = mapped_column(portable_json, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DecisionExecution(Base):
    __tablename__ = "decision_executions"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_decision_executions_org_id"),
        UniqueConstraint(
            "organization_id", "idempotency_key", name="uq_decision_execution_idempotency"
        ),
        CheckConstraint(
            f"status IN ({enum_values(DecisionExecutionStatus)})",
            name="ck_decision_execution_status",
        ),
        ForeignKeyConstraint(
            ["organization_id", "scenario_id"],
            ["decision_scenarios.organization_id", "decision_scenarios.id"],
            name="fk_decision_executions_org_scenario",
            ondelete="RESTRICT",
        ),
        Index("ix_decision_execution_org_scenario", "organization_id", "scenario_id"),
        Index("ix_decision_execution_org_status", "organization_id", "status"),
        Index(
            "ix_decision_execution_input_fingerprint",
            "organization_id",
            "input_fingerprint",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    scenario_id: Mapped[UUID] = mapped_column(Uuid)
    method_code: Mapped[str] = mapped_column(String(150))
    method_version: Mapped[str] = mapped_column(String(30))
    solver_adapter: Mapped[str] = mapped_column(String(100))
    solver_adapter_version: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    scenario_fingerprint: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    random_seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    time_limit_seconds: Mapped[int] = mapped_column(Integer)
    optimality_gap: Mapped[Decimal | None] = mapped_column(Numeric(18, 10), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    objective_values: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    violations: Mapped[list[dict[str, object]]] = mapped_column(portable_json, default=list)
    warnings: Mapped[list[str]] = mapped_column(portable_json, default=list)
    assumptions: Mapped[list[str]] = mapped_column(portable_json, default=list)
    reproducibility_metadata: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    gate_reasons: Mapped[list[dict[str, object]]] = mapped_column(portable_json, default=list)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DecisionSolution(Base):
    __tablename__ = "decision_solutions"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_decision_solutions_org_id"),
        UniqueConstraint("execution_id", "solution_number", name="uq_decision_solution_number"),
        ForeignKeyConstraint(
            ["organization_id", "execution_id"],
            ["decision_executions.organization_id", "decision_executions.id"],
            name="fk_decision_solutions_org_execution",
            ondelete="RESTRICT",
        ),
        Index("ix_decision_solution_org_execution", "organization_id", "execution_id"),
        Index(
            "ix_decision_solution_org_feasibility",
            "organization_id",
            "feasibility_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    execution_id: Mapped[UUID] = mapped_column(Uuid)
    solution_number: Mapped[int] = mapped_column(Integer, default=1)
    feasibility_status: Mapped[str] = mapped_column(String(30))
    solver_status: Mapped[str] = mapped_column(String(50))
    objective_values: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    variable_values: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    binding_constraints: Mapped[list[str]] = mapped_column(portable_json, default=list)
    violations: Mapped[list[dict[str, object]]] = mapped_column(portable_json, default=list)
    solver_metadata: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DecisionAlternative(Base):
    __tablename__ = "decision_alternatives"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_decision_alternatives_org_id"),
        UniqueConstraint("solution_id", "rank", name="uq_decision_alternative_rank"),
        ForeignKeyConstraint(
            ["organization_id", "solution_id"],
            ["decision_solutions.organization_id", "decision_solutions.id"],
            name="fk_decision_alternatives_org_solution",
            ondelete="CASCADE",
        ),
        Index("ix_decision_alternative_org_solution", "organization_id", "solution_id"),
        Index("ix_decision_alternative_org_rank", "organization_id", "solution_id", "rank"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    solution_id: Mapped[UUID] = mapped_column(Uuid)
    rank: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(250))
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    feasible: Mapped[bool] = mapped_column(Boolean)
    objective_values: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    expected_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    expected_recovery: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    expected_cost: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    expected_risk: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    expected_duration_hours: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    binding_constraints: Mapped[list[str]] = mapped_column(portable_json, default=list)
    soft_constraint_violations: Mapped[list[dict[str, object]]] = mapped_column(
        portable_json, default=list
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    tradeoff_narrative: Mapped[str] = mapped_column(Text)
    assumptions: Mapped[list[str]] = mapped_column(portable_json, default=list)
    supporting_evidence: Mapped[list[dict[str, object]]] = mapped_column(
        portable_json, default=list
    )
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DecisionRecommendation(Base):
    __tablename__ = "decision_recommendations"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_decision_recommendations_org_id"),
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_decision_recommendation_idempotency",
        ),
        ForeignKeyConstraint(
            ["organization_id", "solution_id"],
            ["decision_solutions.organization_id", "decision_solutions.id"],
            name="fk_decision_recommendations_org_solution",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "selected_alternative_id"],
            ["decision_alternatives.organization_id", "decision_alternatives.id"],
            name="fk_decision_recommendations_org_alternative",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "approved_by_approval_id"],
            ["decision_approvals.organization_id", "decision_approvals.id"],
            name="fk_decision_recommendations_org_approval",
            ondelete="RESTRICT",
            use_alter=True,
        ).ddl_if(dialect="postgresql"),
        ForeignKeyConstraint(
            ["organization_id", "converted_action_id"],
            ["operational_actions.organization_id", "operational_actions.id"],
            name="fk_decision_recommendations_org_action",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"lifecycle_status IN ({enum_values(DecisionRecommendationStatus)})",
            name="ck_decision_recommendation_status",
        ),
        CheckConstraint(
            "lifecycle_status <> 'converted_to_action' OR "
            "(approved_by_approval_id IS NOT NULL AND converted_action_id IS NOT NULL)",
            name="ck_decision_recommendation_conversion",
        ),
        Index("ix_decision_recommendation_org_status", "organization_id", "lifecycle_status"),
        Index("ix_decision_recommendation_org_solution", "organization_id", "solution_id"),
        Index(
            "ix_decision_recommendation_org_alternative",
            "organization_id",
            "selected_alternative_id",
        ),
        Index(
            "ix_decision_recommendation_org_approval",
            "organization_id",
            "approved_by_approval_id",
        ),
        Index(
            "ix_decision_recommendation_org_action",
            "organization_id",
            "converted_action_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    solution_id: Mapped[UUID] = mapped_column(Uuid)
    selected_alternative_id: Mapped[UUID] = mapped_column(Uuid)
    approved_by_approval_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    converted_action_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    lifecycle_status: Mapped[str] = mapped_column(String(30), default="proposed")
    title: Mapped[str] = mapped_column(String(250))
    rationale: Mapped[str] = mapped_column(Text)
    objective_explanation: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    constraint_explanation: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    evidence_summary: Mapped[list[dict[str, object]]] = mapped_column(portable_json, default=list)
    idempotency_key: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class DecisionRecommendationEvidence(Base):
    __tablename__ = "decision_recommendation_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "recommendation_id"],
            ["decision_recommendations.organization_id", "decision_recommendations.id"],
            name="fk_decision_recommendation_evidence_org_recommendation",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "recommendation_id",
            "evidence_kind",
            "evidence_id",
            name="uq_decision_recommendation_evidence_reference",
        ),
        Index(
            "ix_decision_rec_evidence_org_recommendation",
            "organization_id",
            "recommendation_id",
        ),
        Index(
            "ix_decision_rec_evidence_reference",
            "organization_id",
            "evidence_kind",
            "evidence_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    recommendation_id: Mapped[UUID] = mapped_column(Uuid)
    evidence_kind: Mapped[str] = mapped_column(String(80))
    evidence_id: Mapped[UUID] = mapped_column(Uuid)
    evidence_fingerprint: Mapped[str] = mapped_column(String(64))
    relevance: Mapped[str] = mapped_column(String(30))
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DecisionSensitivityResult(Base):
    __tablename__ = "decision_sensitivity_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "solution_id"],
            ["decision_solutions.organization_id", "decision_solutions.id"],
            name="fk_decision_sensitivity_results_org_solution",
            ondelete="CASCADE",
        ),
        Index("ix_decision_sensitivity_org_solution", "organization_id", "solution_id"),
        Index(
            "ix_decision_sensitivity_factor",
            "organization_id",
            "solution_id",
            "parameter_code",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    solution_id: Mapped[UUID] = mapped_column(Uuid)
    parameter_code: Mapped[str] = mapped_column(String(120))
    perturbation_type: Mapped[str] = mapped_column(String(50))
    original_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    perturbed_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    objective_change: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    recommendation_stable: Mapped[bool] = mapped_column(Boolean)
    break_even_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    shadow_price: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    result_metadata: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DecisionApproval(Base):
    __tablename__ = "decision_approvals"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_decision_approvals_org_id"),
        UniqueConstraint(
            "organization_id", "idempotency_key", name="uq_decision_approval_idempotency"
        ),
        ForeignKeyConstraint(
            ["organization_id", "recommendation_id"],
            ["decision_recommendations.organization_id", "decision_recommendations.id"],
            name="fk_decision_approvals_org_recommendation",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"decision IN ({enum_values(DecisionApprovalDecision)})",
            name="ck_decision_approval_decision",
        ),
        Index(
            "ix_decision_approval_org_recommendation",
            "organization_id",
            "recommendation_id",
            "created_at",
        ),
        Index("ix_decision_approval_org_decision", "organization_id", "decision"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    recommendation_id: Mapped[UUID] = mapped_column(Uuid)
    decision: Mapped[str] = mapped_column(String(30))
    rationale: Mapped[str] = mapped_column(Text)
    reviewer_user_id: Mapped[UUID] = mapped_column(Uuid)
    reviewer_role: Mapped[str] = mapped_column(String(50))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DecisionOutcomeLink(Base):
    __tablename__ = "decision_outcome_links"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "recommendation_id"],
            ["decision_recommendations.organization_id", "decision_recommendations.id"],
            name="fk_decision_outcome_links_org_recommendation",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "operational_action_id"],
            ["operational_actions.organization_id", "operational_actions.id"],
            name="fk_decision_outcome_links_org_action",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "action_outcome_id"],
            ["action_outcomes.organization_id", "action_outcomes.id"],
            name="fk_decision_outcome_links_org_action_outcome",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "recommendation_id",
            "outcome_evidence_kind",
            "outcome_evidence_id",
            name="uq_decision_outcome_evidence",
        ),
        Index(
            "ix_decision_outcome_org_recommendation",
            "organization_id",
            "recommendation_id",
        ),
        Index("ix_decision_outcome_org_action", "organization_id", "operational_action_id"),
        Index(
            "ix_decision_outcome_org_action_outcome",
            "organization_id",
            "action_outcome_id",
        ),
        Index(
            "ix_decision_outcome_evidence",
            "organization_id",
            "outcome_evidence_kind",
            "outcome_evidence_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    recommendation_id: Mapped[UUID] = mapped_column(Uuid)
    operational_action_id: Mapped[UUID] = mapped_column(Uuid)
    action_outcome_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    outcome_evidence_kind: Mapped[str | None] = mapped_column(String(80), nullable=True)
    outcome_evidence_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    evidence_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(40), default="pending_verification")
    reconciliation_status: Mapped[str] = mapped_column(String(40), default="pending")
    expected_value_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actual_value_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DecisionAuditEvent(Base):
    __tablename__ = "decision_audit_events"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "idempotency_key", name="uq_decision_audit_idempotency"
        ),
        Index("ix_decision_audit_org_time", "organization_id", "occurred_at"),
        Index(
            "ix_decision_audit_org_entity",
            "organization_id",
            "entity_type",
            "entity_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    event_type: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[UUID] = mapped_column(Uuid)
    actor_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    summary: Mapped[str] = mapped_column(Text)
    event_metadata: Mapped[dict[str, object]] = mapped_column(portable_json, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(255))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


@event.listens_for(DecisionProblemVersion, "before_update")
def _protect_published_problem_version_update(
    _mapper: object, _connection: object, target: DecisionProblemVersion
) -> None:
    previous = inspect(target).attrs.lifecycle_status.history.deleted
    if previous and previous[0] in {"published", "superseded", "retired"}:
        raise ValueError("published decision problem versions are immutable")


@event.listens_for(DecisionProblemVersion, "before_delete")
def _protect_published_problem_version_delete(
    _mapper: object, _connection: object, target: DecisionProblemVersion
) -> None:
    if target.lifecycle_status in {"published", "superseded", "retired"}:
        raise ValueError("published decision problem versions are immutable")


def _immutable_result(*_: object) -> None:
    raise ValueError("decision result records are immutable")


for _model in (
    DecisionSolution,
    DecisionAlternative,
    DecisionApproval,
    DecisionRecommendationEvidence,
    DecisionOutcomeLink,
):
    event.listen(_model, "before_update", _immutable_result)
    event.listen(_model, "before_delete", _immutable_result)
