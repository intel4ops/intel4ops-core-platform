"""Governed, static customer-facing industry taxonomy.

This is descriptive onboarding metadata only -- plain Python reference data,
not a database table, and not tied to the paid, entitlement-gated
IndustryPackDefinition catalog (app/models/commercial.py). Selecting an
industry here never grants, implies, or requires an industry pack.

recommended_objective_codes / recommended_challenge_codes are declarative
hints only; nothing in this package branches platform behavior by industry.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class IndustryDefinition:
    code: str
    display_name: str
    description: str
    operational_archetype: str | None = None
    typical_system_categories: tuple[str, ...] = ()
    recommended_objective_codes: tuple[str, ...] = ()
    recommended_challenge_codes: tuple[str, ...] = ()


INDUSTRIES: tuple[IndustryDefinition, ...] = (
    IndustryDefinition(
        "oil_and_gas",
        "Oil & Gas",
        "Upstream, midstream, or downstream oil and gas operations.",
        operational_archetype="asset_intensive_field_operations",
        typical_system_categories=("erp", "cmms_eam", "scada"),
        recommended_objective_codes=("reduce_downtime", "improve_reliability"),
        recommended_challenge_codes=("downtime", "maintenance_backlog"),
    ),
    IndustryDefinition(
        "oilfield_services",
        "Oilfield Services",
        "Service and equipment providers supporting oil and gas operators.",
        operational_archetype="asset_intensive_field_operations",
        typical_system_categories=("erp", "cmms_eam", "wms"),
        recommended_objective_codes=("improve_asset_utilization", "reduce_fuel_loss"),
        recommended_challenge_codes=("fuel_loss", "poor_asset_utilization"),
    ),
    IndustryDefinition(
        "manufacturing",
        "Manufacturing",
        "Discrete or process manufacturing operations.",
        operational_archetype="production_operations",
        typical_system_categories=("erp", "mes", "cmms_eam"),
        recommended_objective_codes=("improve_maintenance", "improve_reliability"),
        recommended_challenge_codes=("maintenance_backlog", "quality_or_rework"),
    ),
    IndustryDefinition(
        "mining",
        "Mining",
        "Surface or underground mineral extraction operations.",
        operational_archetype="asset_intensive_field_operations",
        typical_system_categories=("erp", "cmms_eam", "scada"),
        recommended_objective_codes=("reduce_downtime", "improve_asset_utilization"),
        recommended_challenge_codes=("downtime", "poor_asset_utilization"),
    ),
    IndustryDefinition(
        "ports_and_logistics",
        "Ports & Logistics",
        "Port, terminal, and logistics operations.",
        operational_archetype="throughput_operations",
        typical_system_categories=("erp", "wms", "tms"),
        recommended_objective_codes=("improve_asset_utilization", "improve_service_delivery"),
        recommended_challenge_codes=("scheduling", "service_delivery"),
    ),
    IndustryDefinition(
        "public_transportation",
        "Public Transportation",
        "Public transit and mobility operations.",
        operational_archetype="fleet_and_schedule_operations",
        typical_system_categories=("cmms_eam", "scada"),
        recommended_objective_codes=("reduce_downtime", "improve_service_delivery"),
        recommended_challenge_codes=("downtime", "scheduling"),
    ),
    IndustryDefinition(
        "utilities",
        "Utilities",
        "Electric, water, or gas utility operations.",
        operational_archetype="asset_intensive_field_operations",
        typical_system_categories=("erp", "cmms_eam", "scada"),
        recommended_objective_codes=("improve_reliability", "reduce_operational_risk"),
        recommended_challenge_codes=("reliability", "operational_risk"),
    ),
    IndustryDefinition(
        "retail",
        "Retail",
        "Retail and consumer-facing commerce operations.",
        operational_archetype="commerce_operations",
        typical_system_categories=("erp", "accounting", "wms"),
        recommended_objective_codes=("increase_revenue", "reduce_inventory_leakage"),
        recommended_challenge_codes=("inventory_leakage", "revenue_leakage"),
    ),
    IndustryDefinition(
        "construction",
        "Construction",
        "Construction and project-based field operations.",
        operational_archetype="project_field_operations",
        typical_system_categories=("erp", "cmms_eam"),
        recommended_objective_codes=("improve_procurement", "reduce_operational_risk"),
        recommended_challenge_codes=("procurement_delay", "workforce_constraints"),
    ),
    IndustryDefinition(
        "healthcare",
        "Healthcare",
        "Healthcare provider and facility operations.",
        operational_archetype="service_delivery_operations",
        typical_system_categories=("erp", "cmms_eam"),
        recommended_objective_codes=("improve_service_delivery", "reduce_operational_risk"),
        recommended_challenge_codes=("service_delivery", "operational_risk"),
    ),
    IndustryDefinition(
        "other",
        "Other",
        "An industry not yet represented in the governed list.",
    ),
)

_INDUSTRIES_BY_CODE: dict[str, IndustryDefinition] = {item.code: item for item in INDUSTRIES}


def get_industry(code: str) -> IndustryDefinition | None:
    return _INDUSTRIES_BY_CODE.get(code)


def is_valid_industry_code(code: str) -> bool:
    return code in _INDUSTRIES_BY_CODE


def list_industries() -> tuple[IndustryDefinition, ...]:
    return INDUSTRIES
