from __future__ import annotations

from uuid import uuid4

import pandas as pd

from app.domain_registry import canonicalize_field
from app.models.analysis_case import DetectionStatus, MappingStatus
from app.services.analysis_case_mapping_service import analysis_case_mapping_service
from app.services.domain_detection_service import detect_domain
from app.services.entity_resolution_service import DatasetEntityInput, entity_resolution_service


def test_customer_native_maintenance_schema_routes_without_legacy_column_names() -> None:
    frame = pd.DataFrame(
        {
            "EquipmentRef": ["EQ-10", "EQ-10", "EQ-10"],
            "Issue Code": ["SEAL", "SEAL", "SEAL"],
            "Downtime Hrs": [2.0, 3.5, 1.0],
            "Repair Amount": [120.0, 80.0, 40.0],
            "Work Date": ["2026-01-01", "2026-01-10", "2026-01-20"],
        }
    )

    detection = detect_domain([str(column) for column in frame.columns])
    assert detection.domain == "maintenance"
    assert detection.status == DetectionStatus.CONFIRMED

    result = analysis_case_mapping_service.apply(
        uuid4(), uuid4(), frame, detection.domain, detection.status
    )

    assert result.overall_status == MappingStatus.AUTO_MAPPED
    assert {"asset_id", "failure_code", "downtime_hours", "repair_cost", "event_date"} <= set(
        result.canonical_dataframe.columns
    )
    lineage = {mapping.source_field: mapping.canonical_field for mapping in result.field_mappings}
    assert lineage["EquipmentRef"] == "asset_id"
    assert lineage["Issue Code"] == "failure_code"
    assert lineage["Downtime Hrs"] == "downtime_hours"
    assert lineage["Repair Amount"] == "repair_cost"


def test_customer_native_work_order_schema_routes_to_operations() -> None:
    columns = ["Work Order Number", "Asset Ref", "Started At", "Work Order Status"]
    detection = detect_domain(columns)

    assert detection.domain == "operations"
    assert detection.status == DetectionStatus.CONFIRMED
    assert canonicalize_field("WorkOrderNumber") == "operational_event_id"
    assert canonicalize_field("AssetRef") == "asset_id"


def test_customer_native_invoice_schema_routes_to_revenue() -> None:
    columns = ["Invoice Number", "Invoice Date", "Billed Amount", "Customer Ref"]
    detection = detect_domain(columns)

    assert detection.domain == "revenue"
    assert detection.status == DetectionStatus.CONFIRMED
    assert canonicalize_field("Invoice Number") == "invoice_id"
    assert canonicalize_field("Customer Ref") == "customer_id"


def test_common_labor_quantity_rate_and_cost_concepts_are_canonicalized() -> None:
    assert canonicalize_field("Technician Ref") == "employee_id"
    assert canonicalize_field("Labor Hrs") == "labor_hours"
    assert canonicalize_field("Qty") == "quantity"
    assert canonicalize_field("Rate Per Hour") == "unit_rate"
    assert canonicalize_field("Actual Cost") == "cost_amount"


def test_cross_dataset_asset_relationship_uses_governed_canonical_identifier() -> None:
    maintenance = pd.DataFrame(
        {
            "Equipment Ref": ["EQ-10", "EQ-20"],
            "Issue Code": ["SEAL", "VALVE"],
            "Downtime Hrs": [2.0, 4.0],
        }
    )
    work_orders = pd.DataFrame(
        {
            "Asset Number": ["EQ-10", "EQ-30"],
            "Work Order Ref": ["WO-1", "WO-2"],
        }
    )

    maint_detection = detect_domain(list(maintenance.columns))
    work_detection = detect_domain(list(work_orders.columns))
    maint_mapping = analysis_case_mapping_service.apply(
        uuid4(), uuid4(), maintenance, maint_detection.domain, maint_detection.status
    )
    work_mapping = analysis_case_mapping_service.apply(
        uuid4(), uuid4(), work_orders, work_detection.domain, work_detection.status
    )

    dataset_a = uuid4()
    dataset_b = uuid4()
    links = entity_resolution_service.resolve(
        [
            DatasetEntityInput(uuid4(), dataset_a, maint_mapping.canonical_dataframe),
            DatasetEntityInput(uuid4(), dataset_b, work_mapping.canonical_dataframe),
        ]
    )

    eq10 = next(link for link in links if link.entity_type == "asset" and link.canonical_key == "EQ-10")
    assert eq10.status == "matched"
    assert set(eq10.source_dataset_ids) == {str(dataset_a), str(dataset_b)}


def test_ambiguous_or_unknown_customer_field_abstains_instead_of_guessing() -> None:
    assert canonicalize_field("Reference") is None
    assert canonicalize_field("Total") is None
    assert canonicalize_field("Metric Value") is None

    detection = detect_domain(["Reference", "Total", "Metric Value"])
    assert detection.domain is None
    assert detection.status == DetectionStatus.UNKNOWN
