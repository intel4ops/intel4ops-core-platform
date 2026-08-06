from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.actions import ActionOutcome, ActionPlanStep, OperationalAction
from app.models.causal_intelligence import CausalOutcomeAssessment
from app.models.decision_intelligence import (
    DecisionAlternative,
    DecisionApproval,
    DecisionAuditEvent,
    DecisionConstraint,
    DecisionExecution,
    DecisionMethodDefinition,
    DecisionObjective,
    DecisionOutcomeLink,
    DecisionProblem,
    DecisionProblemVersion,
    DecisionRecommendation,
    DecisionScenario,
    DecisionScenarioInput,
    DecisionSensitivityResult,
    DecisionSolution,
    DecisionVariableDefinition,
)
from app.models.recovery_ledger import (
    RecoveryCase,
    RecoveryExecution,
    VerifiedValueLedgerEntry,
)
from app.registries.decision_method_registry import DECISION_METHOD_PROFILES
from app.schemas.decision_intelligence import (
    DecisionApprovalCreate,
    DecisionConstraintCreate,
    DecisionExecutionCreate,
    DecisionObjectiveCreate,
    DecisionOutcomeCreate,
    DecisionProblemCreate,
    DecisionProblemVersionCreate,
    DecisionRecommendationCreate,
    DecisionScenarioCreate,
    DecisionScenarioInputCreate,
    DecisionSensitivityCreate,
    DecisionVariableCreate,
)
from app.services.solver_adapter_service import (
    AssignmentDemand,
    AssignmentResource,
    PortfolioItem,
    SequencingTask,
    SolverInputError,
    SolverResult,
    optimize_assignment,
    optimize_recovery_portfolio,
    sequence_work,
)


class DecisionIntelligenceServiceError(ValueError):
    def __init__(self, message: str, *, code: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _get_tenant(
    db: Session,
    model: type[Any],
    organization_id: UUID,
    entity_id: UUID,
    *,
    code: str,
) -> Any:
    entity = db.get(model, entity_id)
    if entity is None or entity.organization_id != organization_id:
        raise DecisionIntelligenceServiceError("decision record not found", code=code, status=404)
    return entity


def _audit(
    db: Session,
    organization_id: UUID,
    event_type: str,
    entity_type: str,
    entity_id: UUID,
    actor_user_id: UUID | None,
    summary: str,
    *,
    idempotency_key: str,
    metadata: dict[str, object] | None = None,
) -> DecisionAuditEvent:
    event = DecisionAuditEvent(
        organization_id=organization_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        actor_role=None,
        summary=summary,
        event_metadata=metadata or {},
        idempotency_key=idempotency_key,
    )
    db.add(event)
    return event


class DecisionMethodRegistryService:
    def list_methods(self) -> tuple[object, ...]:
        return DECISION_METHOD_PROFILES


class DecisionProblemService:
    def _require_editable_version(
        self, db: Session, organization_id: UUID, version_id: UUID
    ) -> DecisionProblemVersion:
        version = db.get(DecisionProblemVersion, version_id)
        problem = None if version is None else db.get(DecisionProblem, version.problem_id)
        if (
            version is None
            or problem is None
            or (
                problem.owner_organization_id is not None
                and problem.owner_organization_id != organization_id
            )
        ):
            raise DecisionIntelligenceServiceError(
                "decision problem version not found",
                code="problem_version_not_found",
                status=404,
            )
        if version.lifecycle_status != "draft":
            raise DecisionIntelligenceServiceError(
                "published decision problem versions are immutable",
                code="problem_version_immutable",
                status=409,
            )
        return version

    def create(
        self,
        db: Session,
        organization_id: UUID,
        payload: DecisionProblemCreate,
        actor_user_id: UUID,
    ) -> DecisionProblem:
        owner = organization_id if payload.scope_type == "organization" else None
        existing = db.scalar(
            select(DecisionProblem).where(
                DecisionProblem.problem_code == payload.problem_code,
                DecisionProblem.scope_key == payload.scope_key,
            )
        )
        if existing is not None:
            raise DecisionIntelligenceServiceError(
                "decision problem code already exists in scope",
                code="problem_conflict",
                status=409,
            )
        problem = DecisionProblem(
            **payload.model_dump(),
            owner_organization_id=owner,
            lifecycle_status="draft",
            created_by_user_id=actor_user_id,
        )
        db.add(problem)
        db.flush()
        _audit(
            db,
            organization_id,
            "problem_created",
            "decision_problem",
            problem.id,
            actor_user_id,
            "Decision problem created",
            idempotency_key=f"problem:{problem.id}",
        )
        db.commit()
        db.refresh(problem)
        return problem

    def add_version(
        self,
        db: Session,
        organization_id: UUID,
        problem_id: UUID,
        payload: DecisionProblemVersionCreate,
        actor_user_id: UUID,
    ) -> DecisionProblemVersion:
        problem = db.get(DecisionProblem, problem_id)
        if problem is None or (
            problem.owner_organization_id is not None
            and problem.owner_organization_id != organization_id
        ):
            raise DecisionIntelligenceServiceError(
                "decision problem not found", code="problem_not_found", status=404
            )
        content = payload.model_dump(mode="json")
        version = DecisionProblemVersion(
            problem_id=problem.id,
            **payload.model_dump(),
            lifecycle_status="draft",
            content_hash=_hash(content),
        )
        db.add(version)
        db.flush()
        _audit(
            db,
            organization_id,
            "problem_version_created",
            "decision_problem_version",
            version.id,
            actor_user_id,
            "Decision problem version created",
            idempotency_key=f"problem-version:{version.id}",
        )
        db.commit()
        db.refresh(version)
        return version

    def publish_version(
        self,
        db: Session,
        organization_id: UUID,
        version_id: UUID,
        actor_user_id: UUID,
    ) -> DecisionProblemVersion:
        version = db.get(DecisionProblemVersion, version_id)
        if version is None:
            raise DecisionIntelligenceServiceError(
                "decision problem version not found",
                code="problem_version_not_found",
                status=404,
            )
        problem = db.get(DecisionProblem, version.problem_id)
        if problem is None or (
            problem.owner_organization_id is not None
            and problem.owner_organization_id != organization_id
        ):
            raise DecisionIntelligenceServiceError(
                "decision problem version not found",
                code="problem_version_not_found",
                status=404,
            )
        if version.lifecycle_status != "draft":
            raise DecisionIntelligenceServiceError(
                "only draft problem versions can be published",
                code="invalid_problem_version_transition",
                status=409,
            )
        version.lifecycle_status = "published"
        version.published_by_user_id = actor_user_id
        version.published_at = datetime.now(UTC)
        problem.lifecycle_status = "active"
        db.commit()
        db.refresh(version)
        return version

    def add_objective(
        self,
        db: Session,
        organization_id: UUID,
        version_id: UUID,
        payload: DecisionObjectiveCreate,
    ) -> DecisionObjective:
        self._require_editable_version(db, organization_id, version_id)
        objective = DecisionObjective(problem_version_id=version_id, **payload.model_dump())
        db.add(objective)
        db.commit()
        db.refresh(objective)
        return objective

    def add_constraint(
        self,
        db: Session,
        organization_id: UUID,
        version_id: UUID,
        payload: DecisionConstraintCreate,
    ) -> DecisionConstraint:
        self._require_editable_version(db, organization_id, version_id)
        constraint = DecisionConstraint(problem_version_id=version_id, **payload.model_dump())
        db.add(constraint)
        db.commit()
        db.refresh(constraint)
        return constraint

    def add_variable(
        self,
        db: Session,
        organization_id: UUID,
        version_id: UUID,
        payload: DecisionVariableCreate,
    ) -> DecisionVariableDefinition:
        self._require_editable_version(db, organization_id, version_id)
        variable = DecisionVariableDefinition(problem_version_id=version_id, **payload.model_dump())
        db.add(variable)
        db.commit()
        db.refresh(variable)
        return variable


class DecisionScenarioService:
    def create(
        self,
        db: Session,
        organization_id: UUID,
        payload: DecisionScenarioCreate,
        actor_user_id: UUID,
    ) -> DecisionScenario:
        existing = db.scalar(
            select(DecisionScenario).where(
                DecisionScenario.organization_id == organization_id,
                DecisionScenario.idempotency_key == payload.idempotency_key,
            )
        )
        fingerprint_payload = payload.model_dump(mode="json", exclude={"idempotency_key"})
        fingerprint = _hash(fingerprint_payload)
        if existing is not None:
            if existing.scenario_fingerprint != fingerprint:
                raise DecisionIntelligenceServiceError(
                    "idempotency key was reused with a different scenario",
                    code="idempotency_conflict",
                    status=409,
                )
            return existing
        version = db.get(DecisionProblemVersion, payload.problem_version_id)
        method = db.get(DecisionMethodDefinition, payload.method_definition_id)
        if version is None or version.lifecycle_status != "published":
            raise DecisionIntelligenceServiceError(
                "published decision problem version is required",
                code="problem_version_not_ready",
                status=409,
            )
        problem = db.get(DecisionProblem, version.problem_id)
        if problem is None or (
            problem.owner_organization_id is not None
            and problem.owner_organization_id != organization_id
        ):
            raise DecisionIntelligenceServiceError(
                "problem version is outside tenant scope",
                code="problem_outside_tenant",
                status=403,
            )
        if method is None or (
            method.owner_organization_id is not None
            and method.owner_organization_id != organization_id
        ):
            raise DecisionIntelligenceServiceError(
                "decision method is outside tenant scope",
                code="method_outside_tenant",
                status=403,
            )
        scenario = DecisionScenario(
            organization_id=organization_id,
            **payload.model_dump(),
            lifecycle_status="draft",
            scenario_fingerprint=fingerprint,
            validation_status="pending",
            gate_reasons=[],
            created_by_user_id=actor_user_id,
        )
        db.add(scenario)
        db.commit()
        db.refresh(scenario)
        return cast(DecisionScenario, scenario)

    def add_input(
        self,
        db: Session,
        organization_id: UUID,
        scenario_id: UUID,
        payload: DecisionScenarioInputCreate,
    ) -> DecisionScenarioInput:
        scenario = _get_tenant(
            db,
            DecisionScenario,
            organization_id,
            scenario_id,
            code="scenario_not_found",
        )
        if scenario.lifecycle_status not in {"draft", "blocked"}:
            raise DecisionIntelligenceServiceError(
                "scenario inputs are immutable after validation",
                code="scenario_inputs_immutable",
                status=409,
            )
        item = DecisionScenarioInput(
            organization_id=organization_id,
            scenario_id=scenario_id,
            **payload.model_dump(),
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item


class DecisionValidationService:
    allowed_readiness = {"supported", "ready", "conditionally_ready", "approved"}
    blocking_flags = {
        "unresolved",
        "ambiguous",
        "conflicting",
        "missing_required_fields",
        "stale",
        "superseded",
        "insufficient_causal_state",
        "missing_economic_assumptions",
        "unit_mismatch",
        "currency_mismatch",
        "timezone_mismatch",
        "infeasible_constraint",
    }

    def validate(self, db: Session, organization_id: UUID, scenario_id: UUID) -> DecisionScenario:
        scenario = _get_tenant(
            db,
            DecisionScenario,
            organization_id,
            scenario_id,
            code="scenario_not_found",
        )
        inputs = list(
            db.scalars(
                select(DecisionScenarioInput).where(
                    DecisionScenarioInput.organization_id == organization_id,
                    DecisionScenarioInput.scenario_id == scenario_id,
                )
            )
        )
        reasons: list[dict[str, object]] = []
        if not inputs:
            reasons.append({"code": "missing_inputs", "message": "scenario has no inputs"})
        for item in inputs:
            if item.mapping_confidence is not None and item.mapping_confidence < Decimal("0.8"):
                reasons.append(
                    {
                        "code": "mapping_confidence_below_threshold",
                        "input_id": str(item.id),
                    }
                )
            if (
                item.trust_readiness_status is not None
                and item.trust_readiness_status not in self.allowed_readiness
            ):
                reasons.append({"code": "trust_readiness_blocked", "input_id": str(item.id)})
            for flag in sorted(set(item.validation_flags) & self.blocking_flags):
                reasons.append(
                    {"code": flag, "input_id": str(item.id), "message": "hard gate failed"}
                )
            if item.observed_at is not None and not (
                scenario.scenario_horizon_start <= item.observed_at <= scenario.scenario_horizon_end
            ):
                reasons.append({"code": "outside_scenario_horizon", "input_id": str(item.id)})
        scenario.gate_reasons = reasons
        scenario.validation_status = "blocked" if reasons else "passed"
        scenario.lifecycle_status = "blocked" if reasons else "ready"
        db.commit()
        db.refresh(scenario)
        return cast(DecisionScenario, scenario)


class SolverAdapterService:
    def solve(self, use_case_code: str, payload: dict[str, object]) -> SolverResult:
        try:
            if use_case_code == "recovery_portfolio_selection":
                items = cast(Iterable[PortfolioItem], payload["items"])
                budget_limit = cast(float | int | str, payload["budget_limit"])
                workforce_limit = cast(float | int | str, payload["workforce_limit"])
                time_limit = cast(float | int | str, payload["time_limit"])
                solver_limit = cast(float | int | str, payload.get("solver_time_limit_seconds", 30))
                return optimize_recovery_portfolio(
                    list(items),
                    budget_limit=float(budget_limit),
                    workforce_limit=float(workforce_limit),
                    time_limit=float(time_limit),
                    solver_time_limit_seconds=int(solver_limit),
                )
            if use_case_code == "technician_resource_assignment":
                demands = cast(Iterable[AssignmentDemand], payload["demands"])
                resources = cast(Iterable[AssignmentResource], payload["resources"])
                return optimize_assignment(
                    list(demands),
                    list(resources),
                )
            if use_case_code == "work_maintenance_sequencing":
                tasks = cast(Iterable[SequencingTask], payload["tasks"])
                raw_dependencies = cast(Iterable[tuple[str, str]], payload.get("dependencies", []))
                return sequence_work(
                    list(tasks),
                    list(raw_dependencies),
                )
        except (KeyError, TypeError, ValueError, SolverInputError) as exc:
            raise DecisionIntelligenceServiceError(
                f"invalid solver input: {exc}", code="invalid_solver_input", status=422
            ) from exc
        raise DecisionIntelligenceServiceError(
            "use case is not certified for execution",
            code="unsupported_use_case",
            status=422,
        )


class DecisionExecutionService:
    def execute(
        self,
        db: Session,
        organization_id: UUID,
        scenario_id: UUID,
        payload: DecisionExecutionCreate,
        actor_user_id: UUID,
    ) -> DecisionExecution:
        scenario = db.scalar(
            select(DecisionScenario)
            .where(
                DecisionScenario.id == scenario_id,
                DecisionScenario.organization_id == organization_id,
            )
            .with_for_update()
        )
        if scenario is None:
            raise DecisionIntelligenceServiceError(
                "scenario not found", code="scenario_not_found", status=404
            )
        existing = db.scalar(
            select(DecisionExecution).where(
                DecisionExecution.organization_id == organization_id,
                DecisionExecution.idempotency_key == payload.idempotency_key,
            )
        )
        if existing is not None:
            if existing.scenario_id != scenario_id:
                raise DecisionIntelligenceServiceError(
                    "idempotency key was reused for another scenario",
                    code="idempotency_conflict",
                    status=409,
                )
            return existing
        if scenario.validation_status != "passed" or scenario.lifecycle_status != "ready":
            execution = DecisionExecution(
                organization_id=organization_id,
                scenario_id=scenario.id,
                method_code="blocked",
                method_version="0.0.0",
                solver_adapter="none",
                solver_adapter_version="none",
                status="blocked",
                input_fingerprint=_hash([]),
                scenario_fingerprint=scenario.scenario_fingerprint,
                idempotency_key=payload.idempotency_key,
                random_seed=payload.random_seed,
                time_limit_seconds=payload.time_limit_seconds,
                gate_reasons=scenario.gate_reasons,
                created_by_user_id=actor_user_id,
            )
            db.add(execution)
            db.commit()
            db.refresh(execution)
            return execution
        inputs = list(
            db.scalars(
                select(DecisionScenarioInput).where(
                    DecisionScenarioInput.organization_id == organization_id,
                    DecisionScenarioInput.scenario_id == scenario_id,
                )
            )
        )
        version = db.get(DecisionProblemVersion, scenario.problem_version_id)
        problem = None if version is None else db.get(DecisionProblem, version.problem_id)
        method = db.get(DecisionMethodDefinition, scenario.method_definition_id)
        if problem is None or method is None:
            raise DecisionIntelligenceServiceError(
                "governed problem or method is unavailable",
                code="governed_definition_unavailable",
                status=409,
            )
        input_fingerprint = _hash(sorted(item.source_fingerprint for item in inputs))
        duplicate = db.scalar(
            select(DecisionExecution).where(
                DecisionExecution.organization_id == organization_id,
                DecisionExecution.scenario_fingerprint == scenario.scenario_fingerprint,
                DecisionExecution.input_fingerprint == input_fingerprint,
                DecisionExecution.status.in_(
                    ["queued", "validating", "running", "solved_optimal", "solved_feasible"]
                ),
            )
        )
        if duplicate is not None:
            return duplicate
        solver_payload: dict[str, object] = {}
        for item in inputs:
            solver_payload.update(item.input_payload)
        execution = DecisionExecution(
            organization_id=organization_id,
            scenario_id=scenario.id,
            method_code=method.method_code,
            method_version=method.method_version,
            solver_adapter=method.solver_adapter,
            solver_adapter_version=method.solver_adapter_version,
            status="running",
            input_fingerprint=input_fingerprint,
            scenario_fingerprint=scenario.scenario_fingerprint,
            idempotency_key=payload.idempotency_key,
            random_seed=payload.random_seed,
            time_limit_seconds=payload.time_limit_seconds,
            reproducibility_metadata={
                "scenario_fingerprint": scenario.scenario_fingerprint,
                "input_fingerprint": input_fingerprint,
                "deterministic": method.deterministic,
            },
            started_at=datetime.now(UTC),
            created_by_user_id=actor_user_id,
        )
        db.add(execution)
        scenario.lifecycle_status = "executing"
        db.flush()
        result = solver_adapter_service.solve(problem.use_case_code, solver_payload)
        execution.status = result.status
        duration_value = result.metadata.get("duration_ms", 0)
        execution.duration_ms = (
            int(duration_value) if isinstance(duration_value, (int, float)) else 0
        )
        execution.objective_values = {"primary": result.objective_value}
        execution.violations = [{"code": item} for item in result.violations]
        execution.reproducibility_metadata = {
            **execution.reproducibility_metadata,
            **result.metadata,
        }
        execution.completed_at = datetime.now(UTC)
        scenario.lifecycle_status = "completed"
        solution = DecisionSolution(
            organization_id=organization_id,
            execution_id=execution.id,
            solution_number=1,
            feasibility_status=(
                "feasible"
                if result.status in {"solved_optimal", "solved_feasible"}
                else result.status
            ),
            solver_status=result.status,
            objective_values={"primary": result.objective_value},
            variable_values=result.variable_values,
            binding_constraints=[],
            violations=[{"code": item} for item in result.violations],
            solver_metadata=result.metadata,
            content_hash=_hash(result.variable_values),
        )
        db.add(solution)
        db.flush()
        if result.status in {"solved_optimal", "solved_feasible"}:
            alternative = DecisionAlternative(
                organization_id=organization_id,
                solution_id=solution.id,
                rank=1,
                title="Recommended governed solution",
                selected=True,
                feasible=True,
                objective_values={"primary": result.objective_value},
                expected_value=(
                    None if result.objective_value is None else Decimal(str(result.objective_value))
                ),
                expected_recovery=None,
                expected_cost=None,
                expected_risk=None,
                expected_duration_hours=None,
                currency_code=scenario.currency_code,
                binding_constraints=[],
                soft_constraint_violations=[{"code": item} for item in result.violations],
                rejection_reason=None,
                tradeoff_narrative="Selected by the certified governed optimization method.",
                assumptions=version.assumptions if version is not None else [],
                supporting_evidence=[
                    {"input_id": str(item.id), "fingerprint": item.source_fingerprint}
                    for item in inputs
                ],
                content_hash=_hash(result.variable_values),
            )
            db.add(alternative)
        _audit(
            db,
            organization_id,
            "execution_completed",
            "decision_execution",
            execution.id,
            actor_user_id,
            f"Decision execution completed with status {execution.status}",
            idempotency_key=f"execution:{execution.id}:completed",
        )
        db.commit()
        db.refresh(execution)
        return execution


class RecommendationService:
    def create(
        self,
        db: Session,
        organization_id: UUID,
        payload: DecisionRecommendationCreate,
        actor_user_id: UUID,
    ) -> DecisionRecommendation:
        solution = _get_tenant(
            db,
            DecisionSolution,
            organization_id,
            payload.solution_id,
            code="solution_not_found",
        )
        alternative = _get_tenant(
            db,
            DecisionAlternative,
            organization_id,
            payload.selected_alternative_id,
            code="alternative_not_found",
        )
        if alternative.solution_id != solution.id:
            raise DecisionIntelligenceServiceError(
                "alternative does not belong to solution",
                code="alternative_solution_mismatch",
                status=409,
            )
        existing = db.scalar(
            select(DecisionRecommendation).where(
                DecisionRecommendation.organization_id == organization_id,
                DecisionRecommendation.idempotency_key == payload.idempotency_key,
            )
        )
        if existing is not None:
            if (
                existing.solution_id != payload.solution_id
                or existing.selected_alternative_id != payload.selected_alternative_id
            ):
                raise DecisionIntelligenceServiceError(
                    "idempotency key was reused for a different recommendation",
                    code="idempotency_conflict",
                    status=409,
                )
            return existing
        recommendation = DecisionRecommendation(
            organization_id=organization_id,
            **payload.model_dump(),
            lifecycle_status="proposed",
            objective_explanation=alternative.objective_values,
            constraint_explanation={
                "binding": alternative.binding_constraints,
                "soft_violations": alternative.soft_constraint_violations,
            },
            evidence_summary=alternative.supporting_evidence,
            created_by_user_id=actor_user_id,
        )
        db.add(recommendation)
        db.commit()
        db.refresh(recommendation)
        return recommendation


class DecisionApprovalService:
    def decide(
        self,
        db: Session,
        organization_id: UUID,
        recommendation_id: UUID,
        payload: DecisionApprovalCreate,
        actor_user_id: UUID,
        actor_role: str,
    ) -> DecisionApproval:
        recommendation = db.scalar(
            select(DecisionRecommendation)
            .where(
                DecisionRecommendation.id == recommendation_id,
                DecisionRecommendation.organization_id == organization_id,
            )
            .with_for_update()
        )
        if recommendation is None:
            raise DecisionIntelligenceServiceError(
                "recommendation not found", code="recommendation_not_found", status=404
            )
        existing = db.scalar(
            select(DecisionApproval).where(
                DecisionApproval.organization_id == organization_id,
                DecisionApproval.idempotency_key == payload.idempotency_key,
            )
        )
        if existing is not None:
            if (
                existing.recommendation_id != recommendation_id
                or existing.decision != payload.decision
            ):
                raise DecisionIntelligenceServiceError(
                    "idempotency key was reused for a different approval",
                    code="idempotency_conflict",
                    status=409,
                )
            return existing
        if recommendation.lifecycle_status in {
            "converted_to_action",
            "superseded",
            "expired",
        }:
            raise DecisionIntelligenceServiceError(
                "recommendation is terminal", code="terminal_recommendation", status=409
            )
        approval = DecisionApproval(
            organization_id=organization_id,
            recommendation_id=recommendation.id,
            **payload.model_dump(),
            reviewer_user_id=actor_user_id,
            reviewer_role=actor_role,
        )
        db.add(approval)
        db.flush()
        if payload.decision == "approve":
            recommendation.approved_by_approval_id = approval.id
            recommendation.lifecycle_status = "approved"
        elif payload.decision == "reject":
            recommendation.lifecycle_status = "rejected"
        else:
            recommendation.lifecycle_status = "reviewed"
        _audit(
            db,
            organization_id,
            "recommendation_decided",
            "decision_recommendation",
            recommendation.id,
            actor_user_id,
            f"Recommendation decision: {payload.decision}",
            idempotency_key=f"approval:{approval.id}",
        )
        db.commit()
        db.refresh(approval)
        return approval

    def convert_to_action(
        self,
        db: Session,
        organization_id: UUID,
        recommendation_id: UUID,
        actor_user_id: UUID,
    ) -> OperationalAction:
        recommendation = db.scalar(
            select(DecisionRecommendation)
            .where(
                DecisionRecommendation.id == recommendation_id,
                DecisionRecommendation.organization_id == organization_id,
            )
            .with_for_update()
        )
        if recommendation is None:
            raise DecisionIntelligenceServiceError(
                "recommendation not found", code="recommendation_not_found", status=404
            )
        if recommendation.converted_action_id is not None:
            action = _get_tenant(
                db,
                OperationalAction,
                organization_id,
                recommendation.converted_action_id,
                code="converted_action_not_found",
            )
            return cast(OperationalAction, action)
        if recommendation.approved_by_approval_id is None:
            raise DecisionIntelligenceServiceError(
                "approved recommendation is required",
                code="approval_required",
                status=409,
            )
        approval = db.scalar(
            select(DecisionApproval)
            .where(
                DecisionApproval.id == recommendation.approved_by_approval_id,
                DecisionApproval.organization_id == organization_id,
            )
            .with_for_update()
        )
        if (
            approval is None
            or approval.recommendation_id != recommendation.id
            or approval.decision != "approve"
        ):
            raise DecisionIntelligenceServiceError(
                "valid approval for this recommendation is required",
                code="approval_mismatch",
                status=409,
            )
        alternative = _get_tenant(
            db,
            DecisionAlternative,
            organization_id,
            recommendation.selected_alternative_id,
            code="alternative_not_found",
        )
        action_fingerprint = _hash(
            {
                "organization_id": organization_id,
                "recommendation_id": recommendation.id,
                "approval_id": approval.id,
            }
        )
        action = OperationalAction(
            organization_id=organization_id,
            source_type="decision_recommendation",
            source_reference=str(recommendation.id),
            recommendation_type="decision_optimization",
            recommendation_rule_version="WP-2.14B",
            title=recommendation.title,
            description=recommendation.rationale,
            rationale=recommendation.rationale,
            priority="high",
            priority_score=Decimal("75"),
            priority_components={"decision_alternative_rank": alternative.rank},
            status="approved",
            approval_required=True,
            approval_level="organization",
            approval_role="organization_admin",
            approval_status="approved",
            verification_required=True,
            expected_avoided_cost=alternative.expected_value,
            expected_intervention_cost=alternative.expected_cost,
            currency_code=alternative.currency_code,
            confidence_score=None,
            limitations=[],
            evidence_references=recommendation.evidence_summary,
            idempotency_fingerprint=action_fingerprint,
            created_by_user_id=actor_user_id,
        )
        db.add(action)
        db.flush()
        solution = _get_tenant(
            db,
            DecisionSolution,
            organization_id,
            recommendation.solution_id,
            code="solution_not_found",
        )
        ordered = solution.variable_values.get("ordered_task_ids")
        if isinstance(ordered, list):
            for sequence, task_id in enumerate(ordered, start=1):
                db.add(
                    ActionPlanStep(
                        organization_id=organization_id,
                        action_id=action.id,
                        sequence_number=sequence,
                        title=f"Execute task {task_id}",
                        description="Sequenced by the governed decision solution.",
                        status="planned",
                    )
                )
        recommendation.converted_action_id = action.id
        recommendation.lifecycle_status = "converted_to_action"
        db.add(
            DecisionOutcomeLink(
                organization_id=organization_id,
                recommendation_id=recommendation.id,
                operational_action_id=action.id,
                action_outcome_id=None,
                outcome_evidence_kind=None,
                outcome_evidence_id=None,
                evidence_fingerprint=None,
                verification_status="pending_verification",
                reconciliation_status="pending",
                expected_value_reference=f"decision_alternative:{alternative.id}",
                actual_value_reference=None,
            )
        )
        _audit(
            db,
            organization_id,
            "recommendation_converted",
            "decision_recommendation",
            recommendation.id,
            actor_user_id,
            "Approved recommendation converted to an operational action",
            idempotency_key=f"recommendation:{recommendation.id}:converted",
            metadata={"approval_id": str(approval.id), "action_id": str(action.id)},
        )
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            existing_action = db.scalar(
                select(OperationalAction).where(
                    OperationalAction.organization_id == organization_id,
                    OperationalAction.idempotency_fingerprint == action_fingerprint,
                )
            )
            if existing_action is not None:
                return existing_action
            raise DecisionIntelligenceServiceError(
                "concurrent action conversion conflict",
                code="conversion_conflict",
                status=409,
            ) from exc
        db.refresh(action)
        return action


class SensitivityAnalysisService:
    def record(
        self,
        db: Session,
        organization_id: UUID,
        solution_id: UUID,
        payload: DecisionSensitivityCreate,
    ) -> DecisionSensitivityResult:
        _get_tenant(db, DecisionSolution, organization_id, solution_id, code="solution_not_found")
        result = DecisionSensitivityResult(
            organization_id=organization_id,
            solution_id=solution_id,
            **payload.model_dump(),
            objective_change=None,
            recommendation_stable=True,
            break_even_value=None,
            shadow_price=None,
            result_metadata={"bounded": True, "shadow_price_supported": False},
        )
        db.add(result)
        db.commit()
        db.refresh(result)
        return result


class DecisionOutcomeService:
    target_models = {
        "recovery_case": RecoveryCase,
        "recovery_execution": RecoveryExecution,
        "verified_value_ledger_entry": VerifiedValueLedgerEntry,
        "causal_outcome_assessment": CausalOutcomeAssessment,
    }

    def record(
        self,
        db: Session,
        organization_id: UUID,
        recommendation_id: UUID,
        payload: DecisionOutcomeCreate,
    ) -> DecisionOutcomeLink:
        recommendation = _get_tenant(
            db,
            DecisionRecommendation,
            organization_id,
            recommendation_id,
            code="recommendation_not_found",
        )
        action = _get_tenant(
            db,
            OperationalAction,
            organization_id,
            payload.operational_action_id,
            code="action_not_found",
        )
        if recommendation.converted_action_id != action.id:
            raise DecisionIntelligenceServiceError(
                "action is not the converted recommendation action",
                code="action_recommendation_mismatch",
                status=409,
            )
        if payload.action_outcome_id is not None:
            outcome = _get_tenant(
                db,
                ActionOutcome,
                organization_id,
                payload.action_outcome_id,
                code="action_outcome_not_found",
            )
            if outcome.action_id != action.id:
                raise DecisionIntelligenceServiceError(
                    "action outcome does not belong to action",
                    code="action_outcome_mismatch",
                    status=409,
                )
        target_model = self.target_models[payload.outcome_evidence_kind]
        target = _get_tenant(
            db,
            target_model,
            organization_id,
            payload.outcome_evidence_id,
            code="outcome_evidence_not_found",
        )
        actual_reference = None
        verification_status = "pending_verification"
        if isinstance(target, VerifiedValueLedgerEntry):
            actual_reference = f"verified_value_ledger_entry:{target.id}"
            verification_status = "verified"
        existing_kinds = set(
            db.scalars(
                select(DecisionOutcomeLink.outcome_evidence_kind).where(
                    DecisionOutcomeLink.organization_id == organization_id,
                    DecisionOutcomeLink.recommendation_id == recommendation_id,
                )
            )
        )
        reconciliation_status = (
            "reconciliation_required"
            if existing_kinds and payload.outcome_evidence_kind not in existing_kinds
            else "reconciled"
            if verification_status == "verified"
            else "pending"
        )
        link = DecisionOutcomeLink(
            organization_id=organization_id,
            recommendation_id=recommendation_id,
            **payload.model_dump(),
            verification_status=verification_status,
            reconciliation_status=reconciliation_status,
            expected_value_reference=f"decision_recommendation:{recommendation.id}",
            actual_value_reference=actual_reference,
        )
        db.add(link)
        db.commit()
        db.refresh(link)
        return link


decision_method_registry_service = DecisionMethodRegistryService()
decision_problem_service = DecisionProblemService()
decision_scenario_service = DecisionScenarioService()
decision_validation_service = DecisionValidationService()
solver_adapter_service = SolverAdapterService()
decision_execution_service = DecisionExecutionService()
recommendation_service = RecommendationService()
decision_approval_service = DecisionApprovalService()
sensitivity_analysis_service = SensitivityAnalysisService()
decision_outcome_service = DecisionOutcomeService()
