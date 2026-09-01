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
# industries. Matching is case-insensitive, underscore/space-insensitive.
CANONICAL_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "asset_id": (
        "asset_id",
        "vehicle_id",
        "equipment_id",
        "machine_id",
        "machine_number",
        "pump_id",
        "compressor_id",
        "bus_number",
    ),
    "failure_code": ("failure_code", "failure_type", "defect_code"),
    "downtime_hours": ("downtime_hours", "downtime", "outage_hours"),
    "repair_cost": ("repair_cost", "maintenance_cost", "maintenance_cost_cfa", "repair_amount"),
    "operational_event_id": (
        "operational_event_id",
        "trip_id",
        "job_id",
        "service_ticket_id",
        "production_order_id",
        "work_order_id",
        "dispatch_id",
    ),
    "operational_event_status": ("status", "trip_status", "job_status"),
    "operational_event_start": (
        "start_time",
        "start_date",
        "scheduled_start",
        "trip_start",
        "job_start",
        "dispatch_date",
    ),
    "operational_event_end": (
        "end_time",
        "end_date",
        "scheduled_end",
        "trip_end",
        "job_end",
        "return_date",
    ),
    "fuel_quantity": ("fuel_quantity", "fuel_volume", "fuel_liters", "fuel_gallons"),
    "transaction_amount": (
        "amount",
        "revenue_amount",
        "fare",
        "invoice_amount",
        "customer_invoice",
    ),
    "route_id": ("route_id", "route"),
    "depot_id": ("depot_id", "depot", "location_id"),
    # Single canonical date/timestamp concept shared across every domain
    # (maintenance failure date, operational event date, transaction date)
    # -- deliberately not split into per-domain date fields, since the
    # cross-domain rules match on this shared concept directly.
    "event_date": (
        "event_date",
        "date",
        "occurred_at",
        "failure_date",
        "transaction_date",
        "invoice_date",
        "event_timestamp",
        "timestamp",
    ),
}


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def canonicalize_field(source_field: str) -> str | None:
    """Return the canonical field name a raw source column maps to via the
    alias table, or None if no alias matches. A column already named
    exactly like the canonical concept always matches, regardless of
    whether that exact spelling was also listed in its own alias tuple --
    the alias tuples are for *additional* spellings, not a substitute for
    the canonical name itself."""
    normalized = _normalize(source_field)
    if normalized in CANONICAL_FIELD_ALIASES:
        return normalized
    for canonical, aliases in CANONICAL_FIELD_ALIASES.items():
        if normalized in {_normalize(alias) for alias in aliases}:
            return canonical
    return None


# P3.xxC.2E: canonical concepts that are generic entity/context signals
# shared across virtually every domain (asset_id also covers its aliases
# equipment_id/vehicle_id/etc via CANONICAL_FIELD_ALIASES; event_date
# covers date/timestamp; depot_id covers location_id). None of these may
# independently CONFIRM a specialized domain -- a dataset carrying only
# generic fields is UNKNOWN, not a false-positive match on whichever
# domain signature happens to require that field. Drawn from the existing
# alias registry above, not a new vocabulary.
GENERIC_CANONICAL_FIELDS: frozenset[str] = frozenset({"asset_id", "event_date", "depot_id"})


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
