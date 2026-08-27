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
