"""Proves the domain/mapping/entity-resolution layer does not depend on
public-transport naming -- the explicit test requested by the industry-
agnostic architecture amendment. Uses equipment_id/job_id/customer_invoice
in place of vehicle_id/trip_id/fare and asserts identical behavior."""

from uuid import uuid4

import pandas as pd

from app.models.analysis_case import DetectionStatus, EntityLinkStatus, MappingStatus
from app.services.analysis_case_mapping_service import analysis_case_mapping_service
from app.services.domain_detection_service import detect_domain
from app.services.entity_resolution_service import DatasetEntityInput, entity_resolution_service


def test_non_transport_maintenance_schema_detects_and_maps_identically() -> None:
    columns = ["equipment_id", "failure_code", "downtime_hours"]
    detection = detect_domain(columns)
    assert detection.domain == "maintenance"
    assert detection.status == DetectionStatus.CONFIRMED.value

    df = pd.DataFrame({"equipment_id": ["E1"], "failure_code": ["seal"], "downtime_hours": [6]})
    mapping = analysis_case_mapping_service.apply(uuid4(), uuid4(), df, detection.domain)
    assert mapping.overall_status == MappingStatus.AUTO_MAPPED.value
    assert "asset_id" in mapping.canonical_dataframe.columns


def test_non_transport_operations_schema_detects_correctly() -> None:
    detection = detect_domain(["job_id", "equipment_id", "job_status"])
    assert detection.domain == "operations"
    assert detection.status == DetectionStatus.CONFIRMED.value


def test_non_transport_revenue_schema_detects_correctly() -> None:
    detection = detect_domain(["job_id", "customer_invoice", "invoice_date"])
    assert detection.domain == "revenue"
    assert detection.status == DetectionStatus.CONFIRMED.value


def test_equipment_id_links_across_datasets_same_as_vehicle_id_would() -> None:
    maint_df = pd.DataFrame({"equipment_id": ["E1"]})
    ops_df = pd.DataFrame({"equipment_id": ["E1"]})
    maint_mapped = analysis_case_mapping_service.apply(uuid4(), uuid4(), maint_df, "maintenance")
    ops_mapped = analysis_case_mapping_service.apply(uuid4(), uuid4(), ops_df, "operations")
    links = entity_resolution_service.resolve(
        [
            DatasetEntityInput(uuid4(), uuid4(), maint_mapped.canonical_dataframe),
            DatasetEntityInput(uuid4(), uuid4(), ops_mapped.canonical_dataframe),
        ]
    )
    asset_links = [link for link in links if link.entity_type == "asset"]
    assert len(asset_links) == 1
    assert asset_links[0].canonical_key == "E1"
    assert asset_links[0].status == EntityLinkStatus.MATCHED.value
