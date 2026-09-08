import pandas as pd

from app.services.customer_native_semantics_service import (
    analyze_customer_native_datasets,
    infer_dataset_semantics,
    infer_relationships,
)


def _decision(result: dict[str, object], rule_code: str) -> dict[str, object]:
    decisions = result["capability_routing"]
    assert isinstance(decisions, list)
    return next(item for item in decisions if item["rule_code"] == rule_code)


def test_generic_customer_field_names_infer_operational_concepts() -> None:
    frame = pd.DataFrame(
        {
            "Equipment Number": ["EQ-1", "EQ-2"],
            "Service Order Number": ["SO-10", "SO-11"],
            "Fault Code": ["LEAK", "VIB"],
            "Outage Hours": [2.5, 1.0],
            "Repair Amount": [350.0, 125.0],
        }
    )

    profile = infer_dataset_semantics("customer_upload.csv", frame)

    concepts = profile.available_concepts
    assert {
        "asset_id",
        "work_order_id",
        "failure_code",
        "downtime_hours",
        "repair_cost",
    } <= concepts
    assert "maintenance" in profile.inferred_domains
    assert "operations" in profile.inferred_domains


def test_cross_dataset_relationships_are_evidence_backed_by_shared_identifiers() -> None:
    work = pd.DataFrame(
        {
            "Service Order Number": ["SO-1", "SO-2", "SO-3"],
            "Equipment Number": ["EQ-1", "EQ-2", "EQ-3"],
            "Work Type": ["inspect", "repair", "inspect"],
        }
    )
    billing = pd.DataFrame(
        {
            "Service Order Number": ["SO-2", "SO-3", "SO-4"],
            "Invoice Number": ["INV-2", "INV-3", "INV-4"],
            "Billing Amount": [200.0, 300.0, 400.0],
        }
    )
    profiles = [
        ("work.csv", work, infer_dataset_semantics("work.csv", work)),
        ("billing.csv", billing, infer_dataset_semantics("billing.csv", billing)),
    ]

    relationships = infer_relationships(profiles)

    assert any(
        relationship.canonical_concept == "work_order_id"
        and relationship.left_dataset == "work.csv"
        and relationship.right_dataset == "billing.csv"
        and relationship.confidence >= 0.70
        for relationship in relationships
    )


def test_existing_maintenance_capability_becomes_eligible_from_customer_native_aliases() -> None:
    frame = pd.DataFrame(
        {
            "Equipment ID": ["EQ-1", "EQ-1", "EQ-2"],
            "Fault Code": ["A", "A", "B"],
            "Outage Hours": [3.0, 2.0, 1.0],
            "Repair Amount": [500.0, 250.0, 100.0],
        }
    )

    result = analyze_customer_native_datasets([("maintenance_export.csv", frame)])
    decision = _decision(result, "MAINT-001-REPEATED-FAILURE")

    assert decision["status"] == "ELIGIBLE"
    assert decision["missing_domains"] == ()
    assert decision["missing_canonical_fields"] == ()


def test_missing_customer_fields_are_not_synthesized_to_force_capability_eligibility() -> None:
    frame = pd.DataFrame(
        {
            "Equipment ID": ["EQ-1"],
            "Fault Code": ["A"],
            "Outage Hours": [3.0],
        }
    )

    result = analyze_customer_native_datasets([("maintenance_export.csv", frame)])
    decision = _decision(result, "MAINT-001-REPEATED-FAILURE")

    assert decision["status"] == "PARTIAL"
    assert "repair_cost" in decision["missing_canonical_fields"]


def test_unrelated_schema_remains_uncertain_instead_of_guessing() -> None:
    frame = pd.DataFrame({"alpha": [1, 2], "beta": ["x", "y"]})

    profile = infer_dataset_semantics("unknown.csv", frame)

    assert not profile.available_concepts
    assert "NO_HIGH_CONFIDENCE_CANONICAL_CONCEPTS" in profile.warnings
    assert "NO_HIGH_CONFIDENCE_OPERATIONAL_DOMAIN" in profile.warnings
