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
    # P3.xxV.2K (Fix #8, DC-4): a generic "what kind of activity was this"
    # label -- distinct from operational_event_status (which tracks
    # open/closed/lifecycle state, not the nature of the work performed).
    # Deliberately narrow aliases: no "order_type"/"contract_type" (those
    # belong to commercial documents, not operational activity logs) and
    # no "trip_type"/"job_type" (already ambiguous with pure dispatch/
    # logistics events) -- this concept exists to let a maintenance-shaped
    # activity log (event/work log carrying a category of work performed)
    # be recognized as such without requiring a discrete failure-code or
    # duration column, which many legitimate maintenance exports never
    # carry (see DOMAIN_SIGNATURES below).
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
# P3.xxV.2K (Fix #8): activity_category joins this set for the same
# reason -- a bare "type of activity" column, alone or alongside only
# other generic fields, is too generic to independently suggest maintenance
# (or any domain) on its own; it only becomes real evidence in combination
# with a non-generic operational-event reference, per the maintenance
# DomainSignature below.
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
    # P3.xxV.2K (Fix #8, DC-4): an alternate, equally legitimate maintenance
    # evidence bundle -- an asset-linked work/event log that also carries an
    # explicit category of what activity occurred. Requires the SAME field
    # count (3) as the original signature, so it never wins by being an
    # easier bar to clear; it wins only when this specific combination of
    # evidence is genuinely present. A dataset with only asset_id +
    # operational_event_id (no activity_category) still resolves to
    # "operations", exactly as before this change -- see
    # tests/test_domain_detection_maintenance_activity.py's negative cases.
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
