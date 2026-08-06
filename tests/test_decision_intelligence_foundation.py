from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from uuid import UUID, uuid4

import pytest
from sqlalchemy import UniqueConstraint
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, configure_mappers

from app.db.session import Base
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
    DecisionRecommendationEvidence,
    DecisionScenario,
    DecisionScenarioInput,
    DecisionSensitivityResult,
    DecisionSolution,
    DecisionVariableDefinition,
)
from app.schemas.contracts import OrganizationCreate
from app.schemas.decision_intelligence import (
    DecisionApprovalCreate,
    DecisionScenarioInputCreate,
)
from app.services.decision_intelligence_service import (
    DecisionIntelligenceServiceError,
    decision_approval_service,
    decision_scenario_service,
    decision_validation_service,
)
from app.services.organization_service import OrganizationService
from app.services.solver_adapter_service import (
    PortfolioItem,
    SequencingTask,
    SolverInputError,
    optimize_assignment,
    optimize_recovery_portfolio,
    sequence_work,
    solve_linear_program,
)

DECISION_TABLES = {
    "decision_method_definitions",
    "decision_problems",
    "decision_problem_versions",
    "decision_objectives",
    "decision_constraints",
    "decision_variable_definitions",
    "decision_scenarios",
    "decision_scenario_inputs",
    "decision_executions",
    "decision_solutions",
    "decision_alternatives",
    "decision_recommendations",
    "decision_recommendation_evidence",
    "decision_sensitivity_results",
    "decision_approvals",
    "decision_outcome_links",
    "decision_audit_events",
}
GOVERNED_TABLES = {
    "decision_method_definitions",
    "decision_problems",
    "decision_problem_versions",
    "decision_objectives",
    "decision_constraints",
    "decision_variable_definitions",
}
TENANT_TABLES = DECISION_TABLES - GOVERNED_TABLES
DECISION_MODELS = (
    DecisionMethodDefinition,
    DecisionProblem,
    DecisionProblemVersion,
    DecisionObjective,
    DecisionConstraint,
    DecisionVariableDefinition,
    DecisionScenario,
    DecisionScenarioInput,
    DecisionExecution,
    DecisionSolution,
    DecisionAlternative,
    DecisionRecommendation,
    DecisionRecommendationEvidence,
    DecisionSensitivityResult,
    DecisionApproval,
    DecisionOutcomeLink,
    DecisionAuditEvent,
)


def make_org(db: Session, slug: str) -> tuple[UUID, UUID]:
    organization = OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug,
            slug=slug,
            country_code="US",
            default_currency="USD",
            timezone="UTC",
        ),
    )
    return organization.id, uuid4()


def add_graph(
    db: Session, organization_id: UUID, actor_id: UUID
) -> tuple[DecisionRecommendation, DecisionAlternative]:
    method = DecisionMethodDefinition(
        method_code=f"test_method_{str(organization_id)[:8]}",
        method_name="Test Method",
        method_class="mixed_integer_linear_programming",
        method_version="1.0.0",
        solver_adapter="scipy.optimize.milp",
        solver_adapter_version="1",
        supported_variable_types=["binary"],
        supported_constraint_types=["capacity"],
        supported_objective_types=["maximize"],
        parameter_schema={},
        deterministic=True,
        exact_or_heuristic="exact",
        optimality_guarantee="optimal when solved",
        default_time_limit_seconds=30,
        max_supported_problem_size=500,
        lifecycle_status="active",
        scope_type="organization",
        scope_key=f"organization:{organization_id}",
        owner_organization_id=organization_id,
        content_hash="a" * 64,
    )
    problem = DecisionProblem(
        problem_code=f"problem_{str(organization_id)[:8]}",
        problem_name="Test Problem",
        use_case_code="recovery_portfolio_selection",
        description="Test problem",
        scope_type="organization",
        scope_key=f"organization:{organization_id}",
        owner_organization_id=organization_id,
        lifecycle_status="active",
        created_by_user_id=actor_id,
    )
    db.add_all([method, problem])
    db.flush()
    version = DecisionProblemVersion(
        problem_id=problem.id,
        version="1.0.0",
        lifecycle_status="published",
        objective_strategy="single",
        input_contract={},
        output_contract={},
        assumptions=[],
        limitations=[],
        content_hash="b" * 64,
        published_by_user_id=actor_id,
        published_at=datetime.now(UTC),
    )
    db.add(version)
    db.flush()
    scenario = DecisionScenario(
        organization_id=organization_id,
        problem_version_id=version.id,
        method_definition_id=method.id,
        scenario_name="Scenario",
        lifecycle_status="completed",
        scenario_horizon_start=datetime.now(UTC),
        scenario_horizon_end=datetime.now(UTC) + timedelta(days=30),
        timezone="UTC",
        currency_code="USD",
        scenario_fingerprint="c" * 64,
        idempotency_key=f"scenario-{organization_id}",
        validation_status="passed",
        gate_reasons=[],
        created_by_user_id=actor_id,
    )
    db.add(scenario)
    db.flush()
    execution = DecisionExecution(
        organization_id=organization_id,
        scenario_id=scenario.id,
        method_code=method.method_code,
        method_version="1.0.0",
        solver_adapter=method.solver_adapter,
        solver_adapter_version="1",
        status="solved_optimal",
        input_fingerprint="d" * 64,
        scenario_fingerprint=scenario.scenario_fingerprint,
        idempotency_key=f"execution-{organization_id}",
        time_limit_seconds=30,
        objective_values={"primary": 100},
        violations=[],
        warnings=[],
        assumptions=[],
        reproducibility_metadata={"deterministic": True},
        gate_reasons=[],
        created_by_user_id=actor_id,
    )
    db.add(execution)
    db.flush()
    solution = DecisionSolution(
        organization_id=organization_id,
        execution_id=execution.id,
        solution_number=1,
        feasibility_status="feasible",
        solver_status="solved_optimal",
        objective_values={"primary": 100},
        variable_values={"selected_item_ids": ["one"]},
        binding_constraints=[],
        violations=[],
        solver_metadata={"solver": "test"},
        content_hash="e" * 64,
    )
    db.add(solution)
    db.flush()
    alternative = DecisionAlternative(
        organization_id=organization_id,
        solution_id=solution.id,
        rank=1,
        title="Best",
        selected=True,
        feasible=True,
        objective_values={"primary": 100},
        expected_value=Decimal("100"),
        expected_recovery=Decimal("100"),
        expected_cost=Decimal("10"),
        expected_risk=Decimal("0.1"),
        expected_duration_hours=Decimal("8"),
        currency_code="USD",
        binding_constraints=[],
        soft_constraint_violations=[],
        tradeoff_narrative="Best feasible value",
        assumptions=[],
        supporting_evidence=[],
        content_hash="f" * 64,
    )
    db.add(alternative)
    db.flush()
    recommendation = DecisionRecommendation(
        organization_id=organization_id,
        solution_id=solution.id,
        selected_alternative_id=alternative.id,
        lifecycle_status="proposed",
        title="Execute best option",
        rationale="Highest governed expected value",
        objective_explanation={"primary": 100},
        constraint_explanation={},
        evidence_summary=[],
        idempotency_key=f"recommendation-{organization_id}",
        created_by_user_id=actor_id,
    )
    db.add(recommendation)
    db.commit()
    return recommendation, alternative


def test_exact_decision_table_inventory_and_mapper_configuration() -> None:
    configure_mappers()
    assert {model.__tablename__ for model in DECISION_MODELS} == DECISION_TABLES
    assert len(GOVERNED_TABLES) == 6
    assert len(TENANT_TABLES) == 11
    assert DECISION_TABLES <= set(Base.metadata.tables)


def test_migration_is_static_deterministic_and_exact() -> None:
    path = (
        Path(__file__).parents[1]
        / "migrations"
        / "versions"
        / "20260807_0033_decision_intelligence_optimization.py"
    )
    source = path.read_text(encoding="utf-8")
    assert "from app." not in source
    assert "Base.metadata" not in source
    assert source.count("op.create_table(") == 17
    assert "20260806_0032" in source
    assert "findings" not in source


def test_tenant_parent_constraints_and_composite_foreign_keys() -> None:
    expected_parents = {
        "decision_scenarios",
        "decision_executions",
        "decision_solutions",
        "decision_alternatives",
        "decision_recommendations",
        "decision_approvals",
    }
    for table_name in expected_parents:
        table = Base.metadata.tables[table_name]
        assert any(
            set(constraint.columns.keys()) == {"organization_id", "id"}
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        )
    recommendation_fks = {
        constraint.name
        for constraint in Base.metadata.tables["decision_recommendations"].foreign_key_constraints
    }
    assert "fk_decision_recommendations_org_approval" in recommendation_fks
    assert "fk_decision_recommendations_org_action" in recommendation_fks


def test_cross_tenant_scenario_input_is_rejected(db: Session) -> None:
    organization_a, actor_a = make_org(db, "decision-tenant-a")
    organization_b, actor_b = make_org(db, "decision-tenant-b")
    recommendation, _ = add_graph(db, organization_a, actor_a)
    solution = db.get(DecisionSolution, recommendation.solution_id)
    assert solution is not None
    execution = db.get(DecisionExecution, solution.execution_id)
    assert execution is not None
    item = DecisionScenarioInput(
        organization_id=organization_b,
        scenario_id=execution.scenario_id,
        input_kind="test",
        source_id=uuid4(),
        source_fingerprint="1" * 64,
        input_payload={},
        validation_flags=[],
    )
    db.add(item)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    assert actor_b


def test_hard_gate_blocks_low_confidence_input(db: Session) -> None:
    organization_id, actor_id = make_org(db, "decision-hard-gate")
    recommendation, _ = add_graph(db, organization_id, actor_id)
    solution = db.get(DecisionSolution, recommendation.solution_id)
    assert solution is not None
    execution = db.get(DecisionExecution, solution.execution_id)
    assert execution is not None
    scenario = db.get(DecisionScenario, execution.scenario_id)
    assert scenario is not None
    scenario.lifecycle_status = "draft"
    scenario.validation_status = "pending"
    db.commit()
    decision_scenario_service.add_input(
        db,
        organization_id,
        scenario.id,
        DecisionScenarioInputCreate(
            input_kind="economic_opportunity",
            source_id=uuid4(),
            source_fingerprint="2" * 64,
            mapping_confidence=Decimal("0.79"),
            trust_readiness_status="ready",
            input_payload={},
        ),
    )
    validated = decision_validation_service.validate(db, organization_id, scenario.id)
    assert validated.lifecycle_status == "blocked"
    assert {reason["code"] for reason in validated.gate_reasons} == {
        "mapping_confidence_below_threshold"
    }


def test_known_optimal_portfolio_and_no_economics_recalculation() -> None:
    result = optimize_recovery_portfolio(
        [
            {
                "item_id": "a",
                "expected_net_benefit": 10,
                "required_budget": 5,
                "required_workforce": 1,
                "required_time": 1,
            },
            {
                "item_id": "b",
                "expected_net_benefit": 15,
                "required_budget": 6,
                "required_workforce": 1,
                "required_time": 1,
            },
            {
                "item_id": "c",
                "expected_net_benefit": 9,
                "required_budget": 4,
                "required_workforce": 1,
                "required_time": 1,
            },
        ],
        budget_limit=10,
        workforce_limit=2,
        time_limit=2,
    )
    assert result.status == "solved_optimal"
    assert result.variable_values["selected_item_ids"] == ["b", "c"]
    assert result.objective_value == 24
    assert "expected_net_benefit" in str(result.metadata["source_fields"])


def test_lp_optimal_and_unbounded_statuses() -> None:
    optimal = solve_linear_program(
        [1, 1],
        maximize=True,
        upper_matrix=[[1, 1]],
        upper_bounds=[4],
        bounds=[(0, None), (0, None)],
    )
    assert optimal.status == "solved_optimal"
    assert optimal.objective_value == pytest.approx(4)
    unbounded = solve_linear_program([-1], bounds=[(0, None)])
    assert unbounded.status == "unbounded"


def test_assignment_known_optimum_and_unassigned_demand() -> None:
    result = optimize_assignment(
        [
            {
                "demand_id": "one",
                "required_skill": "mechanic",
                "priority": 2,
                "expected_value": 10,
                "location": "A",
            },
            {
                "demand_id": "two",
                "required_skill": "electrician",
                "priority": 1,
                "expected_value": 8,
                "location": "B",
            },
        ],
        [
            {
                "resource_id": "r1",
                "skills": ["mechanic"],
                "available": True,
                "location": "A",
            }
        ],
    )
    assert result.status == "solved_feasible"
    assert result.variable_values["assignments"] == [{"demand_id": "one", "resource_id": "r1"}]
    assert result.variable_values["unassigned_demand_ids"] == ["two"]


def test_sequence_and_critical_path_are_deterministic() -> None:
    tasks: list[SequencingTask] = [
        {"task_id": "a", "duration": 2.0, "deadline": None},
        {"task_id": "b", "duration": 5.0, "deadline": None},
        {"task_id": "c", "duration": 1.0, "deadline": None},
    ]
    result = sequence_work(tasks, [("c", "a"), ("c", "b")])
    replay = sequence_work(tasks, [("c", "a"), ("c", "b")])
    assert result == replay
    assert result.variable_values["ordered_task_ids"] == ["a", "b", "c"]
    assert result.variable_values["critical_path_task_ids"] == ["b", "c"]
    assert result.objective_value == 6
    with pytest.raises(SolverInputError, match="cycle"):
        sequence_work(tasks, [("a", "b"), ("b", "a")])


def test_solver_performance_is_bounded() -> None:
    items: list[PortfolioItem] = [
        {
            "item_id": f"item-{index:03}",
            "expected_net_benefit": float(index + 1),
            "required_budget": 1.0,
            "required_workforce": 1.0,
            "required_time": 1.0,
        }
        for index in range(100)
    ]
    started = perf_counter()
    result = optimize_recovery_portfolio(items, budget_limit=50, workforce_limit=50, time_limit=50)
    assert result.status == "solved_optimal"
    assert perf_counter() - started < 5


def test_conversion_requires_exact_approved_row_and_is_idempotent(db: Session) -> None:
    organization_id, actor_id = make_org(db, "decision-approval")
    recommendation, _ = add_graph(db, organization_id, actor_id)
    with pytest.raises(DecisionIntelligenceServiceError) as error:
        decision_approval_service.convert_to_action(
            db, organization_id, recommendation.id, actor_id
        )
    assert error.value.code == "approval_required"
    rejected = decision_approval_service.decide(
        db,
        organization_id,
        recommendation.id,
        DecisionApprovalCreate(
            decision="reject",
            rationale="Rejected",
            idempotency_key="reject-decision-approval",
        ),
        actor_id,
        "organization_admin",
    )
    assert rejected.decision == "reject"
    with pytest.raises(DecisionIntelligenceServiceError):
        decision_approval_service.convert_to_action(
            db, organization_id, recommendation.id, actor_id
        )

    second_org, second_actor = make_org(db, "decision-approval-success")
    approved_recommendation, _ = add_graph(db, second_org, second_actor)
    approval = decision_approval_service.decide(
        db,
        second_org,
        approved_recommendation.id,
        DecisionApprovalCreate(
            decision="approve",
            rationale="Approved",
            idempotency_key="approve-decision-recommendation",
        ),
        second_actor,
        "organization_admin",
    )
    assert approval.recommendation_id == approved_recommendation.id
    action = decision_approval_service.convert_to_action(
        db, second_org, approved_recommendation.id, second_actor
    )
    replay = decision_approval_service.convert_to_action(
        db, second_org, approved_recommendation.id, second_actor
    )
    assert action.id == replay.id
    refreshed = db.get(DecisionRecommendation, approved_recommendation.id)
    assert refreshed is not None
    assert refreshed.lifecycle_status == "converted_to_action"
    assert refreshed.approved_by_approval_id == approval.id
