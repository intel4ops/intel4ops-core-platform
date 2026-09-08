from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Registry/config-driven domain detection and canonical-field aliasing.
# Adding a new industry's vocabulary is a data change here, never a
# migration or a change to domain_detection_service.py's matching logic.
# ---------------------------------------------------------------------------

CANONICAL_DOMAINS = (
    "asset_master",
    "maintenance",
    "operations",
    "jobs_work_orders",
    "production",
    "service_events",
    "fuel_energy",
    "revenue",
    "billing",
    "inventory",
    "workforce",
    "quality",
    "logistics",
    "customer",
    "reference",
    "unknown",
)

# canonical entity/field concept -> raw source column aliases across
# industries. Matching is case-insensitive and separator-insensitive. The
# entries below are generic operational vocabulary only; no customer,
# simulation, filename, record, or scenario vocabulary belongs here.
CANONICAL_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "asset_id": (
        "asset_id",
        "asset_ref",
        "asset_number",
        "vehicle_id",
        "vehicle_ref",
        "vehicle_number",
        "equipment_id",
        "equipment_ref",
        "equipment_number",
        "machine_id",
        "machine_ref",
        "machine_number",
        "unit_id",
        "unit_ref",
        "pump_id",
        "compressor_id",
        "bus_number",
    ),
    "failure_code": (
        "failure_code",
        "failure_type",
        "defect_code",
        "fault_code",
        "issue_code",
    ),
    "downtime_hours": (
        "downtime_hours",
        "downtime_hrs",
        "down_hours",
        "downtime",
        "outage_hours",
        "outage_hrs",
    ),
    "repair_cost": (
        "repair_cost",
        "repair_amount",
        "maintenance_cost",
        "maintenance_cost_cfa",
        "maintenance_amount",
        "service_cost",
    ),
    "operational_event_id": (
        "operational_event_id",
        "trip_id",
        "job_id",
        "job_ref",
        "job_number",
        "service_ticket_id",
        "service_order_id",
        "production_order_id",
        "work_order_id",
        "work_order_ref",
        "work_order_number",
        "dispatch_id",
        "dispatch_ref",
    ),
    "operational_event_status": ("status", "trip_status", "job_status", "work_order_status"),
    "activity_category": (
        "event_type",
        "activity_type",
        "service_type",
        "maintenance_type",
        "work_type",
    ),
    "operational_event_start": (
        "start_time",
        "start_date",
        "started_at",
        "scheduled_start",
        "trip_start",
        "job_start",
        "dispatch_date",
    ),
    "operational_event_end": (
        "end_time",
        "end_date",
        "ended_at",
        "completed_at",
        "scheduled_end",
        "trip_end",
        "job_end",
        "return_date",
    ),
    "fuel_quantity": (
        "fuel_quantity",
        "fuel_qty",
        "fuel_volume",
        "fuel_liters",
        "fuel_gallons",
    ),
    "transaction_amount": (
        "amount",
        "revenue_amount",
        "fare",
        "invoice_amount",
        "invoice_total",
        "billed_amount",
        "bill_amount",
        "customer_invoice",
    ),
    "route_id": ("route_id", "route_ref", "route"),
    "depot_id": ("depot_id", "depot_ref", "depot", "location_id", "location_ref"),
    # Single canonical date/timestamp concept shared across every domain.
    "event_date": (
        "event_date",
        "date",
        "occurred_at",
        "failure_date",
        "transaction_date",
        "invoice_date",
        "service_date",
        "work_date",
        "event_timestamp",
        "timestamp",
    ),
    # Additional customer-native concepts already supported by the semantic
    # and governed-intelligence layers. They do not independently create a
    # legacy domain signature; exposing them in canonical frames simply
    # makes their meaning and lineage available to existing downstream
    # capability/readiness logic.
    "invoice_id": ("invoice_id", "invoice_ref", "invoice_number", "bill_id", "bill_number"),
    "customer_id": ("customer_id", "customer_ref", "client_id", "client_ref", "account_id"),
    "employee_id": (
        "employee_id",
        "employee_ref",
        "technician_id",
        "technician_ref",
        "worker_id",
        "worker_ref",
    ),
    "labor_hours": ("labor_hours", "labor_hrs", "worked_hours", "hours_worked", "time_hours"),
    "quantity": ("quantity", "qty", "units", "unit_count"),
    "unit_rate": ("unit_rate", "hourly_rate", "labor_rate", "rate_per_hour", "unit_price"),
    "cost_amount": ("cost_amount", "total_cost", "actual_cost"),
}


_TOKEN_SYNONYMS: dict[str, str] = {
    "reference": "id",
    "ref": "id",
    "number": "id",
    "num": "id",
    "no": "id",
    "identifier": "id",
    "hrs": "hours",
    "hr": "hours",
    "qty": "quantity",
    "amt": "amount",
}

_SAFE_EXTRA_TOKENS = frozenset({"actual", "reported", "recorded", "source", "customer"})


def _split_tokens(name: str) -> tuple[str, ...]:
    # Convert camelCase/PascalCase before normalizing separators. This lets
    # ordinary customer fields such as EquipmentRef or WorkOrderNumber use
    # the same governed vocabulary as equipment_ref/work_order_number.
    camel_split = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name.strip())
    raw = [token for token in re.split(r"[^A-Za-z0-9]+", camel_split.lower()) if token]
    return tuple(_TOKEN_SYNONYMS.get(token, token) for token in raw)


def _normalize(name: str) -> str:
    return "_".join(_split_tokens(name))


def _infer_unique_token_match(source_field: str) -> str | None:
    """Conservative name-shape inference for ordinary customer variants.

    Exact alias matching remains authoritative. This fallback only accepts a
    unique canonical concept when normalized semantic tokens are identical,
    or when the source carries only a harmless qualifier in addition to a
    known alias. Ambiguous matches abstain rather than guessing.
    """
    source_tokens = frozenset(_split_tokens(source_field))
    if not source_tokens:
        return None

    candidates: set[str] = set()
    for canonical, aliases in CANONICAL_FIELD_ALIASES.items():
        names = (canonical, *aliases)
        for alias in names:
            alias_tokens = frozenset(_split_tokens(alias))
            if not alias_tokens:
                continue
            if source_tokens == alias_tokens:
                candidates.add(canonical)
                break
            extra = source_tokens - alias_tokens
            if alias_tokens < source_tokens and extra <= _SAFE_EXTRA_TOKENS:
                candidates.add(canonical)
                break
    return next(iter(candidates)) if len(candidates) == 1 else None


def canonicalize_field(source_field: str) -> str | None:
    """Resolve a raw customer field to one governed canonical concept.

    Resolution is deterministic and conservative: exact normalized aliases
    first, then unique token-shape inference. If two concepts remain
    plausible, return None so mapping/semantic interpretation can surface
    uncertainty rather than silently routing data to an analyzer.
    """
    normalized = _normalize(source_field)
    if normalized in CANONICAL_FIELD_ALIASES:
        return normalized
    for canonical, aliases in CANONICAL_FIELD_ALIASES.items():
        if normalized in {_normalize(alias) for alias in aliases}:
            return canonical
    return _infer_unique_token_match(source_field)


# Generic entity/context signals shared across domains. None independently
# confirms a specialized domain.
GENERIC_CANONICAL_FIELDS: frozenset[str] = frozenset(
    {"asset_id", "event_date", "depot_id", "activity_category"}
)


@dataclass(frozen=True)
class DomainSignature:
    domain: str
    required_canonical_fields: frozenset[str]


DOMAIN_SIGNATURES: tuple[DomainSignature, ...] = (
    DomainSignature(
        "maintenance",
        frozenset({"asset_id", "failure_code", "downtime_hours"}),
    ),
    DomainSignature(
        "maintenance",
        frozenset({"asset_id", "operational_event_id", "activity_category"}),
    ),
    DomainSignature(
        "operations",
        frozenset({"operational_event_id", "asset_id"}),
    ),
    DomainSignature(
        "fuel_energy",
        frozenset({"asset_id", "fuel_quantity"}),
    ),
    DomainSignature(
        "revenue",
        frozenset({"transaction_amount", "event_date"}),
    ),
    DomainSignature(
        "asset_master",
        frozenset({"asset_id"}),
    ),
)

BASE_CANONICAL_ENTITY_TYPES = frozenset(
    {
        "organization",
        "asset",
        "location",
        "operational_event",
        "work_order",
        "customer",
        "product_service",
        "employee_crew",
        "material",
        "transaction",
        "time_period",
    }
)
