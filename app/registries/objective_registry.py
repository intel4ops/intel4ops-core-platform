"""Governed, static business-objective taxonomy.

Customer-context knowledge only -- this registry describes what a customer
says they care about. It is a distinct concept from the mathematical
optimization objectives used by Decision Intelligence
(app/models/decision_intelligence.py's DecisionObjective); no code or table
is shared between the two. This package does not implement the KPIs,
analysis, or models any of these codes reference -- only the taxonomy.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ObjectiveDefinition:
    code: str
    display_name: str
    description: str
    recommended_kpi_codes: tuple[str, ...] = ()
    recommended_data_categories: tuple[str, ...] = ()
    recommended_analysis_categories: tuple[str, ...] = ()


OBJECTIVES: tuple[ObjectiveDefinition, ...] = (
    ObjectiveDefinition(
        "increase_revenue",
        "Increase Revenue",
        "Grow top-line revenue.",
        recommended_data_categories=("sales", "customers"),
    ),
    ObjectiveDefinition(
        "improve_job_to_cash",
        "Improve Job-to-Cash",
        "Shorten and de-risk the path from completed work to collected cash.",
        recommended_data_categories=("work_orders", "invoices", "cash"),
    ),
    ObjectiveDefinition(
        "reduce_downtime",
        "Reduce Downtime",
        "Reduce unplanned asset or operational downtime.",
        recommended_data_categories=("maintenance", "assets"),
    ),
    ObjectiveDefinition(
        "improve_maintenance",
        "Improve Maintenance",
        "Improve the effectiveness of maintenance programs.",
        recommended_data_categories=("maintenance", "work_orders"),
    ),
    ObjectiveDefinition(
        "improve_asset_utilization",
        "Improve Asset Utilization",
        "Get more productive use out of existing assets.",
        recommended_data_categories=("assets", "operations"),
    ),
    ObjectiveDefinition(
        "reduce_fuel_loss",
        "Reduce Fuel Loss",
        "Reduce fuel consumption or loss in field operations.",
        recommended_data_categories=("fuel", "gps"),
    ),
    ObjectiveDefinition(
        "reduce_inventory_leakage",
        "Reduce Inventory Leakage",
        "Reduce unexplained inventory loss or shrinkage.",
        recommended_data_categories=("inventory",),
    ),
    ObjectiveDefinition(
        "improve_procurement",
        "Improve Procurement",
        "Improve procurement cost, cycle time, or supplier performance.",
        recommended_data_categories=("procurement", "suppliers"),
    ),
    ObjectiveDefinition(
        "improve_reliability",
        "Improve Reliability",
        "Improve the reliability of critical assets or processes.",
        recommended_data_categories=("maintenance", "assets"),
    ),
    ObjectiveDefinition(
        "improve_cash_flow",
        "Improve Cash Flow",
        "Improve overall cash-flow position and predictability.",
        recommended_data_categories=("cash", "general_ledger"),
    ),
    ObjectiveDefinition(
        "reduce_operational_risk",
        "Reduce Operational Risk",
        "Reduce safety, compliance, or operational risk exposure.",
        recommended_data_categories=("safety", "quality"),
    ),
    ObjectiveDefinition(
        "improve_service_delivery",
        "Improve Service Delivery",
        "Improve the speed or quality of service delivered to customers.",
        recommended_data_categories=("dispatch", "scheduling"),
    ),
)

_OBJECTIVES_BY_CODE: dict[str, ObjectiveDefinition] = {item.code: item for item in OBJECTIVES}


def get_objective(code: str) -> ObjectiveDefinition | None:
    return _OBJECTIVES_BY_CODE.get(code)


def is_valid_objective_code(code: str) -> bool:
    return code in _OBJECTIVES_BY_CODE


def list_objectives() -> tuple[ObjectiveDefinition, ...]:
    return OBJECTIVES
