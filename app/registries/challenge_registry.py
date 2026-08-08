"""Governed, static operational-challenge taxonomy.

A challenge is an explicit customer statement ("this is hurting us today"),
never inferred from objective selections -- selecting an objective never
implies a challenge, and vice versa. This is customer-context knowledge
only; no analysis or detection logic is implemented here.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ChallengeDefinition:
    code: str
    display_name: str
    description: str
    recommended_objective_codes: tuple[str, ...] = ()
    recommended_data_categories: tuple[str, ...] = ()


CHALLENGES: tuple[ChallengeDefinition, ...] = (
    ChallengeDefinition(
        "revenue_leakage",
        "Revenue Leakage",
        "Revenue is being lost through billing gaps, missed charges, or errors.",
        recommended_objective_codes=("increase_revenue",),
        recommended_data_categories=("sales", "invoices"),
    ),
    ChallengeDefinition(
        "late_invoicing",
        "Late Invoicing",
        "Invoices go out later than they should, delaying payment.",
        recommended_objective_codes=("improve_job_to_cash", "improve_cash_flow"),
        recommended_data_categories=("invoices", "work_orders"),
    ),
    ChallengeDefinition(
        "downtime",
        "Downtime",
        "Assets or operations experience more unplanned downtime than desired.",
        recommended_objective_codes=("reduce_downtime", "improve_reliability"),
        recommended_data_categories=("maintenance", "assets"),
    ),
    ChallengeDefinition(
        "maintenance_backlog",
        "Maintenance Backlog",
        "Maintenance work is piling up faster than it can be completed.",
        recommended_objective_codes=("improve_maintenance",),
        recommended_data_categories=("maintenance", "work_orders"),
    ),
    ChallengeDefinition(
        "poor_asset_utilization",
        "Poor Asset Utilization",
        "Assets are underused relative to their capacity.",
        recommended_objective_codes=("improve_asset_utilization",),
        recommended_data_categories=("assets", "operations"),
    ),
    ChallengeDefinition(
        "fuel_loss",
        "Fuel Loss",
        "Fuel is being consumed or lost more than expected.",
        recommended_objective_codes=("reduce_fuel_loss",),
        recommended_data_categories=("fuel", "gps"),
    ),
    ChallengeDefinition(
        "inventory_leakage",
        "Inventory Leakage",
        "Inventory is disappearing or being lost without explanation.",
        recommended_objective_codes=("reduce_inventory_leakage",),
        recommended_data_categories=("inventory",),
    ),
    ChallengeDefinition(
        "procurement_delay",
        "Procurement Delay",
        "Procurement cycles take longer than they should.",
        recommended_objective_codes=("improve_procurement",),
        recommended_data_categories=("procurement", "suppliers"),
    ),
    ChallengeDefinition(
        "cash_flow",
        "Cash Flow",
        "Cash-flow timing or predictability is a problem.",
        recommended_objective_codes=("improve_cash_flow",),
        recommended_data_categories=("cash", "general_ledger"),
    ),
    ChallengeDefinition(
        "scheduling",
        "Scheduling",
        "Scheduling of work, crews, or assets is difficult or inefficient.",
        recommended_objective_codes=("improve_service_delivery",),
        recommended_data_categories=("scheduling", "dispatch"),
    ),
    ChallengeDefinition(
        "workforce_constraints",
        "Workforce Constraints",
        "Workforce availability or skill constraints limit operations.",
        recommended_objective_codes=("improve_service_delivery",),
        recommended_data_categories=("workforce",),
    ),
    ChallengeDefinition(
        "quality_or_rework",
        "Quality or Rework",
        "Quality issues are causing rework or waste.",
        recommended_objective_codes=("improve_reliability",),
        recommended_data_categories=("quality",),
    ),
    ChallengeDefinition(
        "reliability",
        "Reliability",
        "Assets or processes are less reliable than they should be.",
        recommended_objective_codes=("improve_reliability",),
        recommended_data_categories=("maintenance", "assets"),
    ),
    ChallengeDefinition(
        "service_delivery",
        "Service Delivery",
        "Service is delivered slower or less consistently than desired.",
        recommended_objective_codes=("improve_service_delivery",),
        recommended_data_categories=("dispatch", "scheduling"),
    ),
    ChallengeDefinition(
        "operational_risk",
        "Operational Risk",
        "Safety, compliance, or operational risk exposure is a concern.",
        recommended_objective_codes=("reduce_operational_risk",),
        recommended_data_categories=("safety", "quality"),
    ),
)

_CHALLENGES_BY_CODE: dict[str, ChallengeDefinition] = {item.code: item for item in CHALLENGES}


def get_challenge(code: str) -> ChallengeDefinition | None:
    return _CHALLENGES_BY_CODE.get(code)


def is_valid_challenge_code(code: str) -> bool:
    return code in _CHALLENGES_BY_CODE


def list_challenges() -> tuple[ChallengeDefinition, ...]:
    return CHALLENGES
