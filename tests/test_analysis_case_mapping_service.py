from uuid import uuid4

import pandas as pd

from app.models.analysis_case import MappingStatus
from app.services.analysis_case_mapping_service import analysis_case_mapping_service


def test_auto_maps_all_required_fields_present() -> None:
    df = pd.DataFrame({"vehicle_id": ["V1"], "failure_type": ["brake"], "downtime_hours": [4]})
    result = analysis_case_mapping_service.apply(uuid4(), uuid4(), df, "maintenance")
    assert result.overall_status == MappingStatus.AUTO_MAPPED.value
    assert list(result.canonical_dataframe.columns) == [
        "asset_id",
        "failure_code",
        "downtime_hours",
    ]
    statuses = {m.source_field: m.mapping_status for m in result.field_mappings}
    assert statuses["vehicle_id"] == MappingStatus.AUTO_MAPPED.value


def test_needs_review_when_a_required_field_is_missing() -> None:
    df = pd.DataFrame({"vehicle_id": ["V1"], "failure_type": ["brake"]})  # no downtime_hours
    result = analysis_case_mapping_service.apply(uuid4(), uuid4(), df, "maintenance")
    assert result.overall_status == MappingStatus.NEEDS_REVIEW.value
    missing = [
        m
        for m in result.field_mappings
        if m.mapping_status == MappingStatus.MISSING_REQUIRED_FIELD.value
    ]
    assert any(m.canonical_field == "downtime_hours" for m in missing)


def test_unmapped_columns_are_marked_ignored_not_dropped_silently() -> None:
    df = pd.DataFrame(
        {"vehicle_id": ["V1"], "failure_type": ["brake"], "downtime_hours": [4], "notes": ["x"]}
    )
    result = analysis_case_mapping_service.apply(uuid4(), uuid4(), df, "maintenance")
    ignored = [m for m in result.field_mappings if m.source_field == "notes"]
    assert len(ignored) == 1
    assert ignored[0].mapping_status == MappingStatus.IGNORED.value
    assert "notes" in result.canonical_dataframe.columns
