from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from time import perf_counter
from typing import TypedDict

import numpy as np
from scipy.optimize import (  # type: ignore[import-untyped]
    Bounds,
    LinearConstraint,
    linear_sum_assignment,
    linprog,
    milp,
)


class PortfolioItem(TypedDict):
    item_id: str
    expected_net_benefit: float
    required_budget: float
    required_workforce: float
    required_time: float


class AssignmentDemand(TypedDict):
    demand_id: str
    required_skill: str
    priority: float
    expected_value: float
    location: str | None


class AssignmentResource(TypedDict):
    resource_id: str
    skills: list[str]
    available: bool
    location: str | None


class SequencingTask(TypedDict):
    task_id: str
    duration: float
    deadline: float | None


@dataclass(frozen=True)
class SolverResult:
    status: str
    objective_value: float | None
    variable_values: dict[str, object]
    violations: tuple[str, ...]
    metadata: dict[str, object]


class SolverInputError(ValueError):
    pass


def solve_linear_program(
    objective: list[float],
    *,
    maximize: bool = False,
    upper_matrix: list[list[float]] | None = None,
    upper_bounds: list[float] | None = None,
    bounds: list[tuple[float | None, float | None]] | None = None,
    time_limit_seconds: int = 30,
) -> SolverResult:
    if not objective:
        raise SolverInputError("objective must contain at least one coefficient")
    coefficients = np.asarray(objective, dtype=float)
    started = perf_counter()
    result = linprog(
        -coefficients if maximize else coefficients,
        A_ub=None if upper_matrix is None else np.asarray(upper_matrix, dtype=float),
        b_ub=None if upper_bounds is None else np.asarray(upper_bounds, dtype=float),
        bounds=bounds,
        method="highs",
        options={"time_limit": float(time_limit_seconds)},
    )
    status = {
        0: "solved_optimal",
        1: "timed_out",
        2: "infeasible",
        3: "unbounded",
    }.get(result.status, "failed")
    objective_value = None
    values: dict[str, object] = {}
    if result.x is not None and result.fun is not None:
        objective_value = float(-result.fun if maximize else result.fun)
        values = {f"x_{index}": float(value) for index, value in enumerate(result.x)}
    return SolverResult(
        status=status,
        objective_value=objective_value,
        variable_values=values,
        violations=(),
        metadata={
            "solver": "scipy.optimize.linprog",
            "solver_status": int(result.status),
            "message": str(result.message),
            "duration_ms": round((perf_counter() - started) * 1000),
            "deterministic": True,
        },
    )


def optimize_recovery_portfolio(
    items: list[PortfolioItem],
    *,
    budget_limit: float,
    workforce_limit: float,
    time_limit: float,
    solver_time_limit_seconds: int = 30,
) -> SolverResult:
    if not items:
        raise SolverInputError("portfolio requires at least one opportunity")
    ordered = sorted(items, key=lambda item: item["item_id"])
    benefits = np.asarray([item["expected_net_benefit"] for item in ordered], dtype=float)
    consumption = np.asarray(
        [
            [item["required_budget"] for item in ordered],
            [item["required_workforce"] for item in ordered],
            [item["required_time"] for item in ordered],
        ],
        dtype=float,
    )
    limits = np.asarray([budget_limit, workforce_limit, time_limit], dtype=float)
    if np.any(limits < 0) or np.any(consumption < 0):
        raise SolverInputError("portfolio limits and resource requirements must be non-negative")
    started = perf_counter()
    result = milp(
        c=-benefits,
        integrality=np.ones(len(ordered), dtype=int),
        bounds=Bounds(np.zeros(len(ordered)), np.ones(len(ordered))),
        constraints=LinearConstraint(consumption, np.zeros(3), limits),
        options={"time_limit": float(solver_time_limit_seconds)},
    )
    status = {
        0: "solved_optimal",
        1: "timed_out",
        2: "infeasible",
        3: "unbounded",
    }.get(result.status, "failed")
    selected: list[str] = []
    objective_value: float | None = None
    if result.x is not None:
        selected = [
            item["item_id"] for item, value in zip(ordered, result.x, strict=True) if value >= 0.5
        ]
        objective_value = float(
            sum(item["expected_net_benefit"] for item in ordered if item["item_id"] in selected)
        )
    return SolverResult(
        status=status,
        objective_value=objective_value,
        variable_values={"selected_item_ids": selected},
        violations=(),
        metadata={
            "solver": "scipy.optimize.milp",
            "solver_status": int(result.status),
            "message": str(result.message),
            "duration_ms": round((perf_counter() - started) * 1000),
            "deterministic_order": [item["item_id"] for item in ordered],
            "source_fields": [
                "expected_net_benefit",
                "required_budget",
                "required_workforce",
                "required_time",
            ],
        },
    )


def optimize_assignment(
    demands: list[AssignmentDemand],
    resources: list[AssignmentResource],
) -> SolverResult:
    if not demands:
        raise SolverInputError("assignment requires at least one demand")
    ordered_demands = sorted(demands, key=lambda demand: demand["demand_id"])
    ordered_resources = sorted(
        (resource for resource in resources if resource["available"]),
        key=lambda resource: resource["resource_id"],
    )
    if not ordered_resources:
        return SolverResult(
            status="infeasible",
            objective_value=None,
            variable_values={
                "assignments": [],
                "unassigned_demand_ids": [item["demand_id"] for item in ordered_demands],
            },
            violations=("no available resources",),
            metadata={"solver": "scipy.optimize.linear_sum_assignment", "deterministic": True},
        )
    unavailable_cost = 1e12
    columns = max(len(ordered_resources), len(ordered_demands))
    cost = np.full((len(ordered_demands), columns), unavailable_cost, dtype=float)
    for row, demand in enumerate(ordered_demands):
        for column, resource in enumerate(ordered_resources):
            if demand["required_skill"] not in resource["skills"]:
                continue
            location_penalty = (
                0.0
                if not demand["location"]
                or not resource["location"]
                or demand["location"] == resource["location"]
                else 1_000.0
            )
            cost[row, column] = (
                -float(demand["expected_value"])
                - float(demand["priority"]) * 100.0
                + location_penalty
                + column * 1e-6
            )
    started = perf_counter()
    rows, cols = linear_sum_assignment(cost)
    assignments: list[dict[str, str]] = []
    assigned_demands: set[str] = set()
    for row, column in zip(rows, cols, strict=True):
        if column >= len(ordered_resources) or cost[row, column] >= unavailable_cost:
            continue
        demand = ordered_demands[row]
        resource = ordered_resources[column]
        assignments.append(
            {"demand_id": demand["demand_id"], "resource_id": resource["resource_id"]}
        )
        assigned_demands.add(demand["demand_id"])
    unassigned = [
        demand["demand_id"]
        for demand in ordered_demands
        if demand["demand_id"] not in assigned_demands
    ]
    status = "solved_optimal" if not unassigned else "solved_feasible"
    return SolverResult(
        status=status,
        objective_value=float(
            sum(
                demand["expected_value"]
                for demand in ordered_demands
                if demand["demand_id"] in assigned_demands
            )
        ),
        variable_values={"assignments": assignments, "unassigned_demand_ids": unassigned},
        violations=tuple(f"unassigned:{item_id}" for item_id in unassigned),
        metadata={
            "solver": "scipy.optimize.linear_sum_assignment",
            "duration_ms": round((perf_counter() - started) * 1000),
            "deterministic": True,
        },
    )


def sequence_work(
    tasks: list[SequencingTask],
    dependencies: list[tuple[str, str]],
) -> SolverResult:
    if not tasks:
        raise SolverInputError("sequencing requires at least one task")
    ordered = sorted(tasks, key=lambda task: task["task_id"])
    task_map = {task["task_id"]: task for task in ordered}
    if len(task_map) != len(tasks):
        raise SolverInputError("task identifiers must be unique")
    predecessors: dict[str, set[str]] = defaultdict(set)
    successors: dict[str, set[str]] = defaultdict(set)
    for task_id, prerequisite_id in dependencies:
        if task_id not in task_map or prerequisite_id not in task_map:
            raise SolverInputError("dependency references an unknown task")
        if task_id == prerequisite_id:
            raise SolverInputError("task cannot depend on itself")
        predecessors[task_id].add(prerequisite_id)
        successors[prerequisite_id].add(task_id)
    ready = deque(sorted(task_id for task_id in task_map if not predecessors[task_id]))
    order: list[str] = []
    earliest_finish: dict[str, float] = {}
    critical_predecessor: dict[str, str | None] = {}
    while ready:
        task_id = ready.popleft()
        order.append(task_id)
        predecessor_ids = predecessors[task_id]
        critical = (
            max(predecessor_ids, key=lambda candidate: earliest_finish[candidate])
            if predecessor_ids
            else None
        )
        earliest_start = 0.0 if critical is None else earliest_finish[critical]
        earliest_finish[task_id] = earliest_start + float(task_map[task_id]["duration"])
        critical_predecessor[task_id] = critical
        for successor in sorted(successors[task_id]):
            if all(predecessor in order for predecessor in predecessors[successor]):
                if successor not in ready and successor not in order:
                    ready.append(successor)
        ready = deque(sorted(ready))
    if len(order) != len(task_map):
        raise SolverInputError("dependency graph contains a cycle")
    terminal = max(order, key=lambda item: earliest_finish[item])
    critical_path: list[str] = []
    cursor: str | None = terminal
    while cursor is not None:
        critical_path.append(cursor)
        cursor = critical_predecessor[cursor]
    critical_path.reverse()
    deadline_violations: list[str] = []
    for task_id, finish in earliest_finish.items():
        deadline = task_map[task_id]["deadline"]
        if deadline is not None and finish > deadline:
            deadline_violations.append(task_id)
    return SolverResult(
        status="solved_optimal" if not deadline_violations else "solved_feasible",
        objective_value=earliest_finish[terminal],
        variable_values={
            "ordered_task_ids": order,
            "critical_path_task_ids": critical_path,
            "earliest_finish": earliest_finish,
        },
        violations=tuple(f"deadline:{task_id}" for task_id in deadline_violations),
        metadata={"solver": "pure_python_critical_path", "deterministic": True},
    )
