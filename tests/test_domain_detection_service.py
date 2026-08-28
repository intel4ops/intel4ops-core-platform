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
