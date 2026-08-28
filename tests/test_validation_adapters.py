"""P3.xxD.1E: proves the Ground-Truth Package Interpreter / normalized
ontology / integrity checker are schema-general, not SIM-005-specific
(section 20). SIM-OFS-FIELDMAINT-005 is exercised here as ONE reference
fixture among several deliberately-different authored schemas -- none of
app/ground_truth_validation/{ontology,integrity,matcher,leakage_matcher,
causal_matcher,dq_matcher,service}.py contain any conditional on a
simulation identifier; this file is where SIM-005-shaped values are
allowed to live (section 0's explicit carve-out: "except inside
tests/fixtures").

The counts below (387 expected findings / 387 leakage records / 387
causal records / 60 data-quality defects) are SIM-005's real authored
manifest totals (section 19). This test generates a synthetic package at
that exact scale, matching SIM-005's schema and structure -- it is not a
copy of the real authored file, which this repository does not have; it
proves the pipeline handles the real fixture's shape and volume."""

from decimal import Decimal

from fixtures.nested_test_adapter import nested_test_adapter

from app.ground_truth_validation.adapters.registry import default_adapter_registry
from app.ground_truth_validation.adapters.simple_v1 import simple_v1_adapter
from app.ground_truth_validation.adapters.simulation_truth_v1 import simulation_truth_v1_adapter
from app.ground_truth_validation.integrity import validate_package_integrity

SCENARIO_FAMILIES = (
    "preventive_maintenance_missed",
    "overtime_leakage",
    "unbilled_parts",
)
DETECTION_FAMILIES = (
    "MAINTENANCE_ECONOMICS",
    "WORKFORCE_PRODUCTIVITY",
    "REVENUE_RECOGNITION",
)


def _build_sim_005_scale_package(finding_count: int = 387, dq_count: int = 60) -> dict[str, object]:
    """A synthetic package matching SIM-OFS-FIELDMAINT-005's real schema
    (section 3) and real authored totals (section 19), at the real scale."""
    expected_findings = []
    leakage_truth = []
    causal_truth = []
    total_true_value = Decimal("0")
    total_recoverable_value = Decimal("0")

    for i in range(finding_count):
        leakage_id = f"LK-{i + 1}"
        finding_id = f"EF-{leakage_id}"
        scenario = SCENARIO_FAMILIES[i % len(SCENARIO_FAMILIES)]
        family = DETECTION_FAMILIES[i % len(DETECTION_FAMILIES)]
        value = Decimal("557.36") + Decimal(i)
        recoverable_value = value * Decimal("0.25")
        total_true_value += value
        total_recoverable_value += recoverable_value

        expected_findings.append(
            {
                "finding_id": finding_id,
                "scenario_id": scenario,
                "affected_records": [f"R-{i + 1}"],
                "expected_severity": "high" if i % 5 == 0 else "medium",
                "expected_value": float(value),
                "expected_detection_family": family,
                "asset_id": f"V{(i % 20) + 1}",
            }
        )
        leakage_truth.append(
            {
                "leakage_id": leakage_id,
                "scenario_id": scenario,
                "business_type": "field_maintenance",
                "affected_records": [f"R-{i + 1}"],
                "time_window": {"start": "2026-01-01", "end": "2026-06-30"},
                "root_cause": f"root cause {i + 1}",
                "causal_chain": [f"step_{i + 1}_a", f"step_{i + 1}_b"],
                "severity": "high" if i % 5 == 0 else "medium",
                "recoverable": True,
                "expected_detection_family": family,
                "expected_evidence": [f"source_{i + 1}.csv"],
                "true_leakage_value": float(value),
                "recoverable_value": float(recoverable_value),
                "currency": "USD",
                "asset_id": f"V{(i % 20) + 1}",
            }
        )
        causal_truth.append(
            {
                "leakage_id": leakage_id,
                "scenario_id": scenario,
                "causal_chain": [f"step_{i + 1}_a", f"step_{i + 1}_b"],
                "root_cause": f"root cause {i + 1}",
            }
        )

    data_quality_truth = [
        {
            "defect_id": f"DQ-{i + 1}",
            "record_id": f"R-{i + 1}",
            "detail": f"data quality issue {i + 1}",
            "severity": "low",
        }
        for i in range(dq_count)
    ]

    return {
        "schema_version": "intel4ops_simulation_truth_v1",
        "manifest": {
            "simulation_id": "SIM-OFS-FIELDMAINT-005",
            "sealed_at": "2026-08-01T00:00:00Z",
            "summary": {
                "total_true_leakage_value": float(total_true_value),
                "recoverable_value": float(total_recoverable_value),
                "leakage_count": finding_count,
                "data_quality_defect_count": dq_count,
            },
            "files": [
                {"file": "expected_findings.json", "sha256": "a" * 64},
                {"file": "leakage_truth.json", "sha256": "b" * 64},
                {"file": "causal_truth.json", "sha256": "c" * 64},
                {"file": "data_quality_truth.json", "sha256": "d" * 64},
            ],
        },
        "documents": {
            "expected_findings": expected_findings,
            "leakage_truth": leakage_truth,
            "causal_truth": causal_truth,
            "data_quality_truth": data_quality_truth,
        },
    }


def test_registry_selects_simulation_truth_v1_for_sim_005_shaped_package() -> None:
    registry = default_adapter_registry()
    package = _build_sim_005_scale_package(finding_count=3, dq_count=1)
    metadata: dict[str, object] = {
        "schema_version": package["schema_version"],
        "manifest": package["manifest"],
        "documents": package["documents"],
    }
    adapter = registry.select(metadata)
    assert adapter is not None
    assert adapter.adapter_code == "intel4ops_simulation_truth_v1"


def test_registry_selects_simple_v1_for_flat_v1_payload() -> None:
    registry = default_adapter_registry()
    metadata: dict[str, object] = {
        "expected_findings": [
            {"expected_finding_code": "EXP-1", "domain": "maintenance", "severity": "high"}
        ]
    }
    adapter = registry.select(metadata)
    assert adapter is not None
    assert adapter.adapter_code == "intel4ops_simple_v1"


def test_registry_returns_none_for_unrecognized_shape() -> None:
    registry = default_adapter_registry()
    assert registry.select({"nope": True}) is None


def test_sim_005_scale_package_normalizes_to_exact_authored_counts() -> None:
    """Section 19: SIM-005's real manifest totals -- 387/387/387/60 -- pass
    through the generic adapter with no code conditional on
    "SIM-OFS-FIELDMAINT-005" anywhere in the engine."""
    package = _build_sim_005_scale_package(finding_count=387, dq_count=60)
    normalized = simulation_truth_v1_adapter.normalize(package)

    assert len(normalized.expected_findings) == 387
    assert len(normalized.leakage_truth) == 387
    assert len(normalized.causal_truth) == 387
    assert len(normalized.data_quality_truth) == 60

    assert normalized.manifest is not None
    assert normalized.manifest.simulation_code == "SIM-OFS-FIELDMAINT-005"
    assert normalized.manifest.summary["leakage_count"] == 387
    assert normalized.manifest.summary["data_quality_defect_count"] == 60

    # The EF-<leakage_id> deterministic join (section 9) resolved for every
    # expected finding, and every finding's family is one of the fixture's
    # declared detection families -- resolved via ontology fields, never
    # source JSON keys.
    assert all(f.linked_leakage_id is not None for f in normalized.expected_findings)
    assert {f.expected_detection_family for f in normalized.expected_findings} == set(
        DETECTION_FAMILIES
    )
    assert {leakage.scenario_code for leakage in normalized.leakage_truth} == set(SCENARIO_FAMILIES)

    issues = validate_package_integrity(normalized)
    errors = [i for i in issues if i.severity == "error"]
    assert errors == [], f"unexpected integrity errors at SIM-005 scale: {errors}"


def test_sim_005_scale_package_has_no_dangling_or_duplicate_references() -> None:
    package = _build_sim_005_scale_package(finding_count=50, dq_count=5)
    normalized = simulation_truth_v1_adapter.normalize(package)
    leakage_ids = {leakage.truth_leakage_id for leakage in normalized.leakage_truth}
    linked_ids = {f.linked_leakage_id for f in normalized.expected_findings}
    assert linked_ids <= leakage_ids


def test_fixture_a_flat_findings_with_no_causal_truth() -> None:
    """Section 20 fixture A: flat expected findings, no causal truth
    document at all -- an optional dimension must not be forced."""
    package: dict[str, object] = {
        "schema_version": "intel4ops_simulation_truth_v1",
        "documents": {
            "expected_findings": [
                {
                    "finding_id": "EF-LK-1",
                    "scenario_id": "overtime_leakage",
                    "expected_severity": "medium",
                    "expected_value": 500,
                    "expected_detection_family": "WORKFORCE_PRODUCTIVITY",
                    "technician_id": "T-9",
                }
            ],
            "leakage_truth": [
                {
                    "leakage_id": "LK-1",
                    "scenario_id": "overtime_leakage",
                    "severity": "medium",
                    "expected_detection_family": "WORKFORCE_PRODUCTIVITY",
                    "true_leakage_value": 500,
                    "currency": "USD",
                    "technician_id": "T-9",
                }
            ],
            # no "causal_truth" key at all
        },
    }
    normalized = simulation_truth_v1_adapter.normalize(package)
    assert len(normalized.expected_findings) == 1
    assert normalized.causal_truth == []
    # Generic entity inference picked up technician_id -- a name never
    # hard-coded anywhere in the adapter or engine.
    assert normalized.expected_findings[0].entities == [
        {"entity_type": "technician", "canonical_key": "T-9"}
    ]
    issues = validate_package_integrity(normalized)
    assert [i for i in issues if i.severity == "error"] == []


def test_fixture_b_nested_records_and_different_field_names() -> None:
    """Section 20 fixture B: a genuinely different authored schema
    (nested container, id/sev/fam/who instead of finding_id/
    expected_severity/expected_detection_family/entities), handled by an
    entirely separate, tiny adapter -- proving a new schema is a new
    adapter, never new central-engine code."""
    package: dict[str, object] = {
        "schema_version": "test_nested_v1",
        "documents": {
            "expected_findings": {
                "case_findings": [
                    {
                        "id": "F-1",
                        "sev": "high",
                        "fam": "REVENUE_RECOGNITION",
                        "who": [{"kind": "asset", "key": "PUMP-4"}],
                    },
                    {"id": "F-2", "sev": "low", "fam": "REVENUE_RECOGNITION", "who": []},
                ]
            }
        },
    }
    assert nested_test_adapter.can_handle({"schema_version": "test_nested_v1"})
    normalized = nested_test_adapter.normalize(package)
    assert len(normalized.expected_findings) == 2
    assert normalized.expected_findings[0].truth_finding_id == "F-1"
    assert normalized.expected_findings[0].severity == "high"
    assert normalized.expected_findings[0].expected_detection_family == "REVENUE_RECOGNITION"
    assert normalized.expected_findings[0].entities == [
        {"entity_type": "asset", "canonical_key": "PUMP-4"}
    ]

    # The SAME central integrity checker works unmodified against output
    # from this brand-new adapter.
    issues = validate_package_integrity(normalized)
    assert [i for i in issues if i.severity == "error"] == []


def test_fixture_c_object_map_records_keyed_by_id() -> None:
    """Section 20 fixture C: records as an object map keyed by id, not an
    array -- reuses the SAME simulation_truth_v1 adapter (section 4E's
    "role detection" / _as_record_list already tolerates both shapes),
    proving one adapter can flexibly interpret more than one container
    shape without a second adapter being required."""
    package: dict[str, object] = {
        "schema_version": "intel4ops_simulation_truth_v1",
        "documents": {
            "expected_findings": {
                "EF-LK-1": {
                    "finding_id": "EF-LK-1",
                    "scenario_id": "unbilled_parts",
                    "expected_severity": "critical",
                    "expected_value": 1200,
                    "expected_detection_family": "REVENUE_RECOGNITION",
                }
            },
            "leakage_truth": {
                "LK-1": {
                    "leakage_id": "LK-1",
                    "scenario_id": "unbilled_parts",
                    "severity": "critical",
                    "expected_detection_family": "REVENUE_RECOGNITION",
                    "true_leakage_value": 1200,
                    "currency": "USD",
                }
            },
        },
    }
    normalized = simulation_truth_v1_adapter.normalize(package)
    assert len(normalized.expected_findings) == 1
    assert normalized.expected_findings[0].truth_finding_id == "EF-LK-1"
    assert len(normalized.leakage_truth) == 1
    issues = validate_package_integrity(normalized)
    assert [i for i in issues if i.severity == "error"] == []


def test_integrity_detects_duplicate_truth_ids() -> None:
    package: dict[str, object] = {
        "schema_version": "intel4ops_simulation_truth_v1",
        "documents": {
            "leakage_truth": [
                {"leakage_id": "LK-1", "severity": "high"},
                {"leakage_id": "LK-1", "severity": "low"},
            ]
        },
    }
    normalized = simulation_truth_v1_adapter.normalize(package)
    issues = validate_package_integrity(normalized)
    duplicate_issues = [i for i in issues if i.code == "duplicate_truth_id"]
    assert len(duplicate_issues) == 1
    assert duplicate_issues[0].severity == "error"


def test_integrity_detects_dangling_leakage_reference() -> None:
    package: dict[str, object] = {
        "schema_version": "intel4ops_simulation_truth_v1",
        "documents": {
            "expected_findings": [
                {
                    "finding_id": "EF-LK-999",
                    "expected_severity": "high",
                    "expected_value": 100,
                }
            ],
            "leakage_truth": [{"leakage_id": "LK-1", "severity": "high"}],
        },
    }
    normalized = simulation_truth_v1_adapter.normalize(package)
    issues = validate_package_integrity(normalized)
    dangling = [i for i in issues if i.code == "dangling_leakage_reference"]
    assert len(dangling) == 1
    assert dangling[0].severity == "error"
    assert dangling[0].truth_ref == "EF-LK-999"


def test_simple_v1_adapter_still_matches_original_flat_shape() -> None:
    """Backward compatibility (section 15): the original P3.xxD.1B shape
    is still recognized and normalizes identically."""
    registry = default_adapter_registry()
    payload = {
        "expected_findings": [
            {"expected_finding_code": "EXP-001", "domain": "maintenance", "severity": "high"}
        ],
        "expected_clean_areas": ["revenue"],
        "tolerance": {"economic_variance_pct": 10},
    }
    adapter = registry.select(payload)
    assert adapter is simple_v1_adapter
    normalized = adapter.normalize(payload)
    assert len(normalized.expected_findings) == 1
    assert normalized.expected_findings[0].domain == "maintenance"
    assert normalized.expected_clean_areas == ["revenue"]
