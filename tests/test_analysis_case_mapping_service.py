from uuid import uuid4

import pandas as pd

from app.models.analysis_case import DetectionStatus, MappingStatus
from app.services.analysis_case_mapping_service import analysis_case_mapping_service


def test_auto_maps_all_required_fields_present() -> None:
    df = pd.DataFrame({"vehicle_id": ["V1"], "failure_type": ["brake"], "downtime_hours": [4]})
    result = analysis_case_mapping_service.apply(
        uuid4(), uuid4(), df, "maintenance", DetectionStatus.CONFIRMED.value
    )
    assert result.overall_status == MappingStatus.AUTO_MAPPED.value
    assert list(result.canonical_dataframe.columns) == [
        "asset_id",
        "failure_code",
        "downtime_hours",
    ]
    statuses = {m.source_field: m.mapping_status for m in result.field_mappings}
    assert statuses["vehicle_id"] == MappingStatus.AUTO_MAPPED.value


def test_needs_review_when_a_required_field_is_missing_on_confirmed_domain() -> None:
    """The MAPPING_REVIEW_REQUIRED safety net: even on an already-CONFIRMED
    domain, a still-missing required field is flagged. In ordinary
    operation this cannot happen (see P3.xxC.2E: CONFIRMED means every
    required field was already found during detection), so this exercises
    the mechanism directly at the unit level rather than relying on
    reaching it through the full pipeline."""
    df = pd.DataFrame({"vehicle_id": ["V1"], "failure_type": ["brake"]})  # no downtime_hours
    result = analysis_case_mapping_service.apply(
        uuid4(), uuid4(), df, "maintenance", DetectionStatus.CONFIRMED.value
    )
    assert result.overall_status == MappingStatus.NEEDS_REVIEW.value
    missing = [
        m
        for m in result.field_mappings
        if m.mapping_status == MappingStatus.MISSING_REQUIRED_FIELD.value
    ]
    assert any(m.canonical_field == "downtime_hours" for m in missing)


def test_unconfirmed_domain_never_creates_missing_required_field_rows() -> None:
    """F. An uncertain (NEEDS_REVIEW) or unresolved (None/UNKNOWN) domain
    must never be enforced against that domain's required fields -- doing
    so is exactly the false-positive review_required this correction
    removes. Same missing-downtime_hours data as the CONFIRMED case above,
    but with a NEEDS_REVIEW detection status, must not produce any
    MISSING_REQUIRED_FIELD rows or a NEEDS_REVIEW mapping status."""
    df = pd.DataFrame({"vehicle_id": ["V1"], "failure_type": ["brake"]})
    result = analysis_case_mapping_service.apply(
        uuid4(), uuid4(), df, "maintenance", DetectionStatus.NEEDS_REVIEW.value
    )
    assert result.overall_status != MappingStatus.NEEDS_REVIEW.value
    assert not any(
        m.mapping_status == MappingStatus.MISSING_REQUIRED_FIELD.value
        for m in result.field_mappings
    )

    # Also true when detection_status is entirely absent/None (e.g. no
    # domain was ever assigned) -- required-field enforcement never
    # silently defaults back on.
    result_no_status = analysis_case_mapping_service.apply(
        uuid4(), uuid4(), df, "maintenance", None
    )
    assert result_no_status.overall_status != MappingStatus.NEEDS_REVIEW.value


def test_unmapped_columns_are_marked_ignored_not_dropped_silently() -> None:
    df = pd.DataFrame(
        {"vehicle_id": ["V1"], "failure_type": ["brake"], "downtime_hours": [4], "notes": ["x"]}
    )
    result = analysis_case_mapping_service.apply(
        uuid4(), uuid4(), df, "maintenance", DetectionStatus.CONFIRMED.value
    )
    ignored = [m for m in result.field_mappings if m.source_field == "notes"]
    assert len(ignored) == 1
    assert ignored[0].mapping_status == MappingStatus.IGNORED.value
    assert "notes" in result.canonical_dataframe.columns
