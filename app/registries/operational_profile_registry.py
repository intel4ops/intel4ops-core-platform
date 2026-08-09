"""Bounded P3.03B inference vocabulary; it never mutates P3.02 registries."""

INFERENCE_TYPES: tuple[str, ...] = (
    "INDUSTRY",
    "SUB_INDUSTRY",
    "OPERATIONAL_ARCHETYPE",
    "BUSINESS_MODEL",
    "OPERATING_PROCESS",
    "SYSTEM_IN_USE",
    "BUSINESS_OBJECTIVE",
    "OPERATIONAL_CHALLENGE",
    "CLARIFICATION_QUESTION",
    "ASSET_INTENSITY",
    "LABOR_INTENSITY",
    "FIELD_SERVICE_CHARACTERISTICS",
    "MAINTENANCE_CHARACTERISTICS",
    "INVENTORY_CHARACTERISTICS",
    "JOB_TO_CASH_CHARACTERISTICS",
)

OPERATIONAL_ARCHETYPE_CODES = {
    "asset_intensive_field_operations",
    "production_operations",
    "throughput_operations",
    "fleet_and_schedule_operations",
    "commerce_operations",
    "project_field_operations",
    "service_delivery_operations",
}

BUSINESS_MODEL_CODES = {
    "field_service",
    "project_based",
    "product_sales",
    "recurring_service",
    "rental_or_leasing",
    "manufacturing",
    "logistics_or_throughput",
    "regulated_service",
    "mixed",
    "unknown",
}

OPERATING_PROCESS_CODES = {
    "job_to_cash",
    "maintenance",
    "asset_management",
    "inventory",
    "procurement",
    "production",
    "dispatch",
    "scheduling",
    "logistics",
    "quality",
    "workforce",
    "fuel_management",
    "service_delivery",
}

CHARACTERISTIC_CODES = {
    "high",
    "medium",
    "low",
    "present",
    "not_observed",
    "unknown",
    "internal",
    "outsourced",
    "both",
}

QUESTION_TARGET_TYPES = {
    "INDUSTRY",
    "SUB_INDUSTRY",
    "OPERATIONAL_ARCHETYPE",
    "BUSINESS_MODEL",
    "OPERATING_PROCESS",
    "SYSTEM_IN_USE",
    "BUSINESS_OBJECTIVE",
    "OPERATIONAL_CHALLENGE",
    "MAINTENANCE_CHARACTERISTICS",
}

REGISTRY_BACKED_TYPES = {
    "INDUSTRY",
    "SYSTEM_IN_USE",
    "BUSINESS_OBJECTIVE",
    "OPERATIONAL_CHALLENGE",
}


def is_valid_inference_type(value: str) -> bool:
    return value in INFERENCE_TYPES


def is_valid_local_code(inference_type: str, code: str | None) -> bool:
    if code is None:
        return inference_type in {"SUB_INDUSTRY", "CLARIFICATION_QUESTION"}
    if inference_type == "OPERATIONAL_ARCHETYPE":
        return code in OPERATIONAL_ARCHETYPE_CODES
    if inference_type == "BUSINESS_MODEL":
        return code in BUSINESS_MODEL_CODES
    if inference_type == "OPERATING_PROCESS":
        return code in OPERATING_PROCESS_CODES
    if inference_type.endswith("CHARACTERISTICS") or inference_type in {
        "ASSET_INTENSITY",
        "LABOR_INTENSITY",
    }:
        return code in CHARACTERISTIC_CODES
    return True
