from app.models.analysis_case import DetectionStatus
from app.services.domain_detection_service import detect_domain


def test_confirms_maintenance_domain_from_sotra_style_columns() -> None:
    result = detect_domain(["vehicle_id", "failure_type", "downtime_hours", "maintenance_cost_cfa"])
    assert result.domain == "maintenance"
    assert result.status == DetectionStatus.CONFIRMED.value
    assert set(result.basis) == {"vehicle_id", "failure_type", "downtime_hours"}


def test_confirms_maintenance_domain_from_non_transport_columns() -> None:
    """Industry-agnostic requirement: equipment_id/failure_code must resolve
    identically to vehicle_id/failure_type -- the detector must never
    depend on public-transport naming."""
    result = detect_domain(["equipment_id", "failure_code", "downtime_hours"])
    assert result.domain == "maintenance"
    assert result.status == DetectionStatus.CONFIRMED.value


def test_confirms_operations_domain() -> None:
    result = detect_domain(["trip_id", "vehicle_id", "route_id", "status"])
    assert result.domain == "operations"
    assert result.status == DetectionStatus.CONFIRMED.value


def test_confirms_revenue_domain() -> None:
    result = detect_domain(["route_id", "event_date", "amount"])
    assert result.domain == "revenue"
    assert result.status == DetectionStatus.CONFIRMED.value


def test_needs_review_on_partial_signature_match() -> None:
    result = detect_domain(["vehicle_id", "failure_type"])  # missing downtime_hours
    assert result.domain == "maintenance"
    assert result.status == DetectionStatus.NEEDS_REVIEW.value


def test_unknown_domain_when_nothing_matches() -> None:
    result = detect_domain(["random_col_a", "random_col_b"])
    assert result.domain is None
    assert result.status == DetectionStatus.UNKNOWN.value
    assert result.basis == []


def test_never_fabricates_a_confidence_score() -> None:
    result = detect_domain(["vehicle_id", "failure_type", "downtime_hours"])
    assert not hasattr(result, "confidence")


# ---------------------------------------------------------------------------
# P3.xxC.2E: generic identifiers (asset_id and its aliases, event_date,
# depot_id) must not independently confirm a specialized domain -- see
# GENERIC_CANONICAL_FIELDS in app/domain_registry.py.
# ---------------------------------------------------------------------------


def test_asset_id_alone_is_not_maintenance() -> None:
    """A. asset_id only -> not maintenance confirmed. It fully satisfies
    the single-field asset_master signature instead, which is preferred
    over being coerced into a 3-field maintenance signature it only
    1/3 satisfies."""
    result = detect_domain(["asset_id"])
    assert result.domain != "maintenance"
    assert result.domain == "asset_master"
    assert result.status == DetectionStatus.CONFIRMED.value


def test_asset_id_and_maintenance_signal_confirms_maintenance() -> None:
    """B. asset_id + failure_type + downtime_hours -> maintenance
    confirmed (the genuine, evidence-backed case, contrasted with A)."""
    result = detect_domain(["asset_id", "failure_type", "downtime_hours"])
    assert result.domain == "maintenance"
    assert result.status == DetectionStatus.CONFIRMED.value


def test_asset_id_and_fuel_quantity_confirms_fuel_domain() -> None:
    """C. asset_id + fuel_quantity -> fuel_energy domain."""
    result = detect_domain(["asset_id", "fuel_quantity"])
    assert result.domain == "fuel_energy"
    assert result.status == DetectionStatus.CONFIRMED.value


def test_asset_id_and_dispatch_fields_confirms_operations() -> None:
    """D. asset_id + dispatch/job fields -> operations. work_order_id is
    a genuinely generic-industry alias of operational_event_id, not a
    SOTRA-specific field name."""
    result = detect_domain(["asset_id", "work_order_id"])
    assert result.domain == "operations"
    assert result.status == DetectionStatus.CONFIRMED.value


def test_asset_id_and_rental_dispatch_id_confirms_operations() -> None:
    """P3.xxV.1B Wave 1 remediation: dispatch_id is the equipment-rental
    industry's own equally standard name for the same operational-event
    concept work_order_id/trip_id/job_id already cover -- confirmed absent
    from the alias table by the Wave 1 finding that every rental
    simulation's dispatch.csv (dispatch_id, asset_id, dispatch_date,
    return_date) never classified as operations at all."""
    result = detect_domain(["asset_id", "dispatch_id", "dispatch_date", "return_date"])
    assert result.domain == "operations"
    assert result.status == DetectionStatus.CONFIRMED.value
    assert set(result.basis) == {"asset_id", "dispatch_id"}


def test_ambiguous_generic_schema_is_unknown_not_a_domain_guess() -> None:
    """E. ambiguous generic schema -> unknown. event_date alone overlaps
    revenue's signature, but event_date is itself a generic field, so no
    domain is confirmed or guessed."""
    result = detect_domain(["event_date"])
    assert result.domain is None
    assert result.status == DetectionStatus.UNKNOWN.value
    assert "revenue" in result.candidate_domains


def test_candidate_domains_exposes_genuine_ties() -> None:
    """Multiple domains plausibly explained by the same generic-only
    evidence are all surfaced, not silently collapsed into one guess."""
    result = detect_domain(["asset_id"])
    assert set(result.candidate_domains) >= {"maintenance", "operations", "fuel_energy"}


# ---------------------------------------------------------------------------
# P3.xxV.2K (Fix #8, DC-4): a second, equally legitimate maintenance
# evidence bundle -- asset + operational-event reference + an explicit
# category of activity performed -- for maintenance data shaped as an
# event/work log (no discrete failure-code or downtime-duration column).
# See app/domain_registry.py's second "maintenance" DomainSignature.
# ---------------------------------------------------------------------------


def test_asset_work_order_and_activity_category_confirms_maintenance() -> None:
    """A. asset + maintenance work order + an explicit category of work
    performed -> maintenance recognized, industry-agnostic naming."""
    result = detect_domain(["asset_id", "work_order_id", "event_type"])
    assert result.domain == "maintenance"
    assert result.status == DetectionStatus.CONFIRMED.value
    assert set(result.basis) == {"asset_id", "work_order_id", "event_type"}


def test_real_maintenance_event_log_shape_confirms_maintenance() -> None:
    """B. The exact real-world shape this fix targets: an asset + work
    order + activity-category log with scheduled/completed dates but no
    discrete failure-code or downtime-hours column."""
    result = detect_domain(
        ["event_id", "asset_id", "work_order_id", "event_type", "scheduled_date", "completed_date"]
    )
    assert result.domain == "maintenance"
    assert result.status == DetectionStatus.CONFIRMED.value


def test_alternate_activity_category_aliases_all_confirm_maintenance() -> None:
    """C. activity_type/service_type/maintenance_type/work_type must all
    resolve identically -- generic vocabulary, not one lucky spelling."""
    for alias in ("activity_type", "service_type", "maintenance_type", "work_type"):
        result = detect_domain(["asset_id", "job_id", alias])
        assert result.domain == "maintenance", alias
        assert result.status == DetectionStatus.CONFIRMED.value, alias


# --- negative / false-positive safety (mission Section 15) ---------------


def test_work_order_without_activity_category_stays_operations() -> None:
    """A. A generic work_order dataset with no activity/failure evidence
    must not automatically become maintenance -- unchanged from the
    pre-existing operations behavior (see
    test_asset_id_and_dispatch_fields_confirms_operations above)."""
    result = detect_domain(["asset_id", "work_order_id", "status", "opened_date", "closed_date"])
    assert result.domain == "operations"
    assert result.status == DetectionStatus.CONFIRMED.value


def test_dispatch_only_stays_operations_not_maintenance() -> None:
    """C. Dispatch/job execution data alone -> operations, never
    automatically maintenance, even with a plausible-looking asset link."""
    result = detect_domain(["asset_id", "dispatch_id", "dispatch_date", "return_date"])
    assert result.domain == "operations"


def test_invoice_with_asset_id_is_not_maintenance() -> None:
    """D. Invoice/contract data is not maintenance merely because it also
    references an asset -- resolves to revenue, on revenue's own evidence,
    never coerced into maintenance."""
    result = detect_domain(["invoice_id", "work_order_id", "asset_id", "invoice_date", "amount"])
    assert result.domain != "maintenance"


def test_activity_category_alone_with_asset_is_ambiguous_not_confirmed() -> None:
    """E. Weak/ambiguous evidence (asset + a category label, but no
    operational-event reference at all) must preserve uncertainty rather
    than confirming maintenance on a partial 2-of-3 match. asset_id and
    activity_category are both generic-only signals in combination (see
    GENERIC_CANONICAL_FIELDS), so this resolves to UNKNOWN rather than a
    silently-guessed maintenance NEEDS_REVIEW."""
    result = detect_domain(["asset_id", "event_type"])
    assert result.status != DetectionStatus.CONFIRMED.value
    assert result.domain is None
    assert result.status == DetectionStatus.UNKNOWN.value


def test_event_type_column_alone_confirms_nothing() -> None:
    """A bare activity-category-shaped column with no asset or event
    reference at all is not, by itself, evidence of any domain."""
    result = detect_domain(["event_type"])
    assert result.domain is None
    assert result.status == DetectionStatus.UNKNOWN.value
