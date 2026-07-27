from decimal import Decimal
from uuid import uuid4

import pytest

from app.validation.simulation import (
    ORACLE_REGISTRY,
    SCENARIO_CODES,
    SCENARIO_REGISTRY,
    AssertionKind,
    OracleAssertion,
    OracleComparator,
    ScenarioOracle,
    SimulationGenerator,
)


def test_required_inventory_is_registered_and_pack_aware() -> None:
    assert len(SCENARIO_REGISTRY) == 36
    assert set(SCENARIO_REGISTRY) == {code for codes in SCENARIO_CODES.values() for code in codes}
    for scenario in SCENARIO_REGISTRY.values():
        assert scenario.industry_pack_code in SCENARIO_CODES
        assert scenario.required_capabilities
        assert scenario.scenario_id == ORACLE_REGISTRY[scenario.scenario_code].scenario_id


def test_simulation_is_deterministic_and_seed_sensitive() -> None:
    generator = SimulationGenerator()
    organization_id = uuid4()
    first = generator.generate("PORT-CRANE-001", organization_id, seed=42)
    replay = generator.generate("PORT-CRANE-001", organization_id, seed=42)
    variation = generator.generate("PORT-CRANE-001", organization_id, seed=43)

    assert first == replay
    assert first.content_hash == replay.content_hash
    assert first.content_hash != variation.content_hash
    assert first.records != variation.records


def test_clean_scenarios_have_no_defects_and_defective_scenarios_do() -> None:
    generator = SimulationGenerator()
    organization_id = uuid4()
    for pack_prefix in ("J2C", "MFG", "PORT", "MOB"):
        clean = generator.generate(f"{pack_prefix}-BASELINE-001", organization_id)
        assert clean.defects == ()
    assert generator.generate("MOB-GPS-QUALITY-001", organization_id).defects


def test_oilfield_profile_has_full_inventory_defects_and_event_contract() -> None:
    artifact = SimulationGenerator().generate("J2C-OILFIELD-001", uuid4())
    record_types = {record["record_type"] for record in artifact.records}

    assert len(artifact.defects) >= 10
    assert {"contract", "rate_sheet", "field_job", "invoice", "payment", "reversal"} <= record_types
    event_window = artifact.manifest["event_window"]
    assert event_window["ordered_event_sequence"][-2:] == [
        "verified_recovery",
        "credit_adjustment",
    ]


def test_servo_scenario_preserves_signature_readiness_sequence() -> None:
    artifact = SimulationGenerator().generate("MFG-SERVO-DEGRADATION-001", uuid4())
    event_window = artifact.manifest["event_window"]
    assert event_window["ordered_event_sequence"] == [
        "rising_load_adjusted_current_variance",
        "increasing_temperature_slope",
        "repeated_position_correction",
        "cycle_time_drift",
        "intermittent_alarm",
        "maintenance_intervention",
    ]
    assert event_window["signature_candidate_identifier"]


def test_oracle_exact_tolerance_range_required_and_forbidden() -> None:
    scenario_id = SCENARIO_REGISTRY["J2C-CNI-001"].scenario_id
    oracle = ScenarioOracle(
        oracle_id=uuid4(),
        scenario_id=scenario_id,
        assertions=(
            OracleAssertion(kind=AssertionKind.EXACT, path="status", expected="passed"),
            OracleAssertion(
                kind=AssertionKind.TOLERANCE,
                path="exposure",
                expected="100",
                tolerance=Decimal("0.01"),
            ),
            OracleAssertion(
                kind=AssertionKind.RANGE,
                path="confidence",
                minimum=Decimal("0.8"),
                maximum=Decimal("1"),
            ),
            OracleAssertion(kind=AssertionKind.REQUIRED, path="evidence"),
            OracleAssertion(kind=AssertionKind.FORBIDDEN, path="forbidden_finding"),
        ),
    )
    result = OracleComparator().compare(
        {
            "status": "passed",
            "exposure": "100.005",
            "confidence": "0.9",
            "evidence": ["source_record"],
            "forbidden_finding": None,
        },
        oracle,
    )
    assert result.passed
    assert result.assertion_count == 5


def test_invalid_scenario_and_cross_tenant_identity_are_safe() -> None:
    generator = SimulationGenerator()
    first_tenant = uuid4()
    second_tenant = uuid4()
    first = generator.generate("J2C-CNI-001", first_tenant, seed=8)
    second = generator.generate("J2C-CNI-001", second_tenant, seed=8)

    assert {record["organization_id"] for record in first.records} == {str(first_tenant)}
    assert {record["organization_id"] for record in second.records} == {str(second_tenant)}
    assert first.content_hash != second.content_hash
    with pytest.raises(ValueError, match="Unknown validation scenario"):
        generator.generate("NOT-A-SCENARIO", first_tenant)
