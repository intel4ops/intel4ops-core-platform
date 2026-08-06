from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid5

DECISION_METHOD_NAMESPACE = UUID("d15c1510-2b14-4b00-a000-000000000001")


@dataclass(frozen=True)
class DecisionMethodProfile:
    method_code: str
    method_name: str
    method_class: str
    solver_adapter: str
    exact_or_heuristic: str
    deterministic: bool
    certified_use_cases: tuple[str, ...]

    @property
    def id(self) -> UUID:
        return uuid5(DECISION_METHOD_NAMESPACE, self.method_code)

    @property
    def method_version(self) -> str:
        return "1.0.0"

    @property
    def solver_adapter_version(self) -> str:
        return "bounded-v1"


DECISION_METHOD_PROFILES: tuple[DecisionMethodProfile, ...] = (
    DecisionMethodProfile(
        "scipy_milp_portfolio",
        "SciPy MILP Portfolio Selection",
        "mixed_integer_linear_programming",
        "scipy.optimize.milp",
        "exact",
        True,
        ("recovery_portfolio_selection",),
    ),
    DecisionMethodProfile(
        "scipy_linear_program",
        "SciPy Linear Programming",
        "linear_programming",
        "scipy.optimize.linprog",
        "exact",
        True,
        (),
    ),
    DecisionMethodProfile(
        "scipy_hungarian_assignment",
        "SciPy Hungarian Assignment",
        "assignment",
        "scipy.optimize.linear_sum_assignment",
        "exact",
        True,
        ("technician_resource_assignment",),
    ),
    DecisionMethodProfile(
        "python_critical_path",
        "Deterministic Critical Path",
        "critical_path",
        "pure_python",
        "exact",
        True,
        ("work_maintenance_sequencing",),
    ),
    DecisionMethodProfile(
        "deterministic_greedy",
        "Deterministic Governed Greedy",
        "deterministic_greedy",
        "pure_python",
        "heuristic",
        True,
        (),
    ),
    DecisionMethodProfile(
        "weighted_scoring",
        "Governed Weighted Scoring",
        "weighted_scoring",
        "pure_python",
        "heuristic",
        True,
        (),
    ),
    DecisionMethodProfile(
        "lexicographic_optimization",
        "Lexicographic Optimization",
        "lexicographic_optimization",
        "scipy.optimize.milp",
        "exact",
        True,
        (),
    ),
    DecisionMethodProfile(
        "bounded_scheduling",
        "Bounded Scheduling",
        "scheduling",
        "pure_python",
        "exact",
        True,
        ("work_maintenance_sequencing",),
    ),
    DecisionMethodProfile(
        "bounded_sequencing",
        "Bounded Sequencing",
        "sequencing",
        "pure_python",
        "exact",
        True,
        ("work_maintenance_sequencing",),
    ),
    DecisionMethodProfile(
        "bounded_resource_allocation",
        "Bounded Resource Allocation",
        "resource_allocation",
        "scipy.optimize.linear_sum_assignment",
        "exact",
        True,
        ("technician_resource_assignment",),
    ),
    DecisionMethodProfile(
        "bounded_portfolio_selection",
        "Bounded Portfolio Selection",
        "portfolio_selection",
        "scipy.optimize.milp",
        "exact",
        True,
        ("recovery_portfolio_selection",),
    ),
    DecisionMethodProfile(
        "bounded_constraint_satisfaction",
        "Bounded Constraint Satisfaction",
        "constraint_satisfaction",
        "pure_python",
        "heuristic",
        True,
        (),
    ),
)


INDUSTRY_DECISION_PROFILES: dict[str, tuple[str, ...]] = {
    "job_to_cash": (
        "recovery_portfolio_selection",
        "collection_prioritization_framework_only",
        "technician_resource_assignment",
    ),
    "oilfield_services": (
        "work_maintenance_sequencing",
        "spare_allocation_framework_only",
        "service_job_assignment",
    ),
}


def get_decision_method_profile(method_code: str) -> DecisionMethodProfile:
    for profile in DECISION_METHOD_PROFILES:
        if profile.method_code == method_code:
            return profile
    raise KeyError(method_code)
