from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, model_validator

SIMULATION_NAMESPACE = UUID("9f0b08b6-f7bb-4f38-bb15-0f5c1e030a42")


class ScenarioLifecycle(StrEnum):
    DRAFT = "draft"
    VALIDATED = "validated"
    APPROVED = "approved"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


class AssertionKind(StrEnum):
    EXACT = "exact"
    TOLERANCE = "tolerance"
    RANGE = "range"
    REQUIRED = "required"
    FORBIDDEN = "forbidden"


class EventWindow(BaseModel):
    model_config = ConfigDict(frozen=True)

    ordered_event_sequence: tuple[str, ...]
    observation_window: str
    feature_window: str
    prediction_horizon: str
    target_outcome: str
    context_constraints: tuple[str, ...] = ()
    exclusion_conditions: tuple[str, ...] = ()
    intervention: str | None = None
    confirmed_outcome: str | None = None
    false_positive_classification: str = "not_observed"
    false_negative_classification: str = "not_observed"
    validation_split: str = "certification"
    holdout_designation: str = "synthetic_holdout"
    signature_candidate_identifier: str | None = None
    artifact_version: str = "1.0.0"


class ScenarioDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    scenario_id: UUID
    scenario_code: str
    scenario_version: str = "1.0.0"
    industry_pack_code: str
    industry_pack_version: str = "1.0.0"
    display_name: str
    description: str
    seed: int
    generator_reference: str = "intel4ops.validation.deterministic.v1"
    required_capabilities: tuple[str, ...]
    defect_codes: tuple[str, ...] = ()
    lifecycle_status: ScenarioLifecycle = ScenarioLifecycle.ACTIVE
    owner: str = "platform-validation"
    maximum_execution_duration_ms: int = 5_000
    event_window: EventWindow | None = None


class OracleAssertion(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: AssertionKind
    path: str
    expected: Any = None
    tolerance: Decimal | None = None
    minimum: Decimal | None = None
    maximum: Decimal | None = None

    @model_validator(mode="after")
    def valid_parameters(self) -> OracleAssertion:
        if self.kind is AssertionKind.TOLERANCE and self.tolerance is None:
            raise ValueError("tolerance assertion requires tolerance")
        if self.kind is AssertionKind.RANGE and (self.minimum is None or self.maximum is None):
            raise ValueError("range assertion requires minimum and maximum")
        return self


class ScenarioOracle(BaseModel):
    model_config = ConfigDict(frozen=True)

    oracle_id: UUID
    scenario_id: UUID
    version: str = "1.0.0"
    assertions: tuple[OracleAssertion, ...]
    required_evidence_types: tuple[str, ...] = ("source_record", "calculation_trace")
    approved: bool = True
    owner: str = "platform-validation"


class SimulationArtifact(BaseModel):
    model_config = ConfigDict(frozen=True)

    scenario_code: str
    scenario_version: str
    seed: int
    organization_id: UUID
    pack_code: str
    records: tuple[dict[str, Any], ...]
    defects: tuple[str, ...]
    manifest: dict[str, Any]
    content_hash: str


class OracleComparison(BaseModel):
    passed: bool
    failures: tuple[str, ...]
    assertion_count: int


def _stable_id(kind: str, code: str, version: str = "1.0.0") -> UUID:
    return uuid5(SIMULATION_NAMESPACE, f"{kind}:{code}:{version}")


SCENARIO_CODES: dict[str, tuple[str, ...]] = {
    "PACK-J2C": (
        "J2C-BASELINE-001",
        "J2C-CNI-001",
        "J2C-UNDERBILL-001",
        "J2C-DOCUMENT-001",
        "J2C-MARGIN-001",
        "J2C-PAYMENT-001",
        "J2C-REWORK-001",
        "J2C-CONTRADICTION-001",
        "J2C-OILFIELD-001",
    ),
    "PACK-MFG": (
        "MFG-BASELINE-001",
        "MFG-DOWNTIME-001",
        "MFG-SCRAP-001",
        "MFG-YIELD-001",
        "MFG-MAINTENANCE-001",
        "MFG-INVENTORY-001",
        "MFG-ENERGY-001",
        "MFG-SERVO-DEGRADATION-001",
        "MFG-DATA-QUALITY-001",
    ),
    "PACK-PORTS": (
        "PORT-BASELINE-001",
        "PORT-BERTH-001",
        "PORT-CRANE-001",
        "PORT-GATE-001",
        "PORT-DWELL-001",
        "PORT-EQUIPMENT-001",
        "PORT-BILLING-001",
        "PORT-LATE-EVENTS-001",
        "PORT-CONTRADICTION-001",
    ),
    "PACK-MOB": (
        "MOB-BASELINE-001",
        "MOB-TRIP-001",
        "MOB-FUEL-001",
        "MOB-FARE-001",
        "MOB-MAINTENANCE-001",
        "MOB-STAFFING-001",
        "MOB-AVAILABILITY-001",
        "MOB-GPS-QUALITY-001",
        "MOB-CONTRADICTION-001",
    ),
}

CAPABILITIES = {
    "PACK-J2C": ("industry.job_to_cash", "recovery.scenarios"),
    "PACK-MFG": ("industry.manufacturing",),
    "PACK-PORTS": ("industry.ports",),
    "PACK-MOB": ("industry.mobility",),
}

DEFECTS = {
    "BASELINE": (),
    "CNI": ("completed_without_invoice",),
    "UNDERBILL": ("missing_billing_line",),
    "DOCUMENT": ("missing_required_document",),
    "MARGIN": ("margin_threshold_breach",),
    "PAYMENT": ("partial_payment",),
    "REWORK": ("duplicate_business_event",),
    "CONTRADICTION": ("contradictory_source_record",),
    "DOWNTIME": ("unplanned_downtime",),
    "SCRAP": ("scrap_threshold_breach",),
    "YIELD": ("yield_loss",),
    "MAINTENANCE": ("late_maintenance",),
    "INVENTORY": ("inventory_mismatch",),
    "ENERGY": ("wrong_unit",),
    "DATA-QUALITY": ("missing_value", "broken_foreign_key", "schema_drift"),
    "BERTH": ("berth_delay",),
    "CRANE": ("crane_bottleneck",),
    "GATE": ("gate_congestion",),
    "DWELL": ("excess_dwell",),
    "EQUIPMENT": ("equipment_unavailable",),
    "BILLING": ("missing_billing_line",),
    "LATE-EVENTS": ("late_arriving_record", "out_of_order_event"),
    "TRIP": ("missed_trip",),
    "FUEL": ("fuel_variance",),
    "FARE": ("fare_leakage",),
    "STAFFING": ("staffing_shortfall",),
    "AVAILABILITY": ("availability_loss",),
    "GPS-QUALITY": ("wrong_timestamp", "invalid_reference"),
}

OILFIELD_DEFECTS = (
    "completed_without_invoice",
    "missing_overtime",
    "missing_equipment_charge",
    "incorrect_contract_rate",
    "missing_mobilization",
    "missing_customer_signature",
    "exhausted_purchase_order",
    "unbilled_change_order",
    "partial_payment",
    "duplicate_field_ticket",
    "late_time_entry",
    "currency_mismatch",
    "credit_after_recovery",
    "cross_tenant_reference_attempt",
)


def _event_window(code: str) -> EventWindow | None:
    if code == "MFG-SERVO-DEGRADATION-001":
        return EventWindow(
            ordered_event_sequence=(
                "rising_load_adjusted_current_variance",
                "increasing_temperature_slope",
                "repeated_position_correction",
                "cycle_time_drift",
                "intermittent_alarm",
                "maintenance_intervention",
            ),
            observation_window="P30D",
            feature_window="P7D",
            prediction_horizon="P3D",
            target_outcome="confirmed_servo_degradation",
            intervention="maintenance_intervention",
            confirmed_outcome="degradation_confirmed",
            signature_candidate_identifier="MFG.SERVO.DEGRADATION.CANDIDATE",
        )
    if code == "J2C-OILFIELD-001":
        return EventWindow(
            ordered_event_sequence=(
                "job_completed",
                "documentation_delayed",
                "equipment_record_posted_late",
                "incomplete_invoice",
                "leakage_finding",
                "supplemental_billing",
                "payment",
                "verified_recovery",
                "credit_adjustment",
            ),
            observation_window="P90D",
            feature_window="P30D",
            prediction_horizon="P14D",
            target_outcome="finance_verified_recovery",
            intervention="supplemental_invoice",
            confirmed_outcome="payment_verified_then_adjusted",
            signature_candidate_identifier="J2C.OILFIELD.LEAKAGE.CANDIDATE",
        )
    return None


def _scenario_definitions() -> dict[str, ScenarioDefinition]:
    definitions: dict[str, ScenarioDefinition] = {}
    for pack_code, codes in SCENARIO_CODES.items():
        for index, code in enumerate(codes, 1):
            subject = "-".join(code.split("-")[1:-1])
            defects = OILFIELD_DEFECTS if code == "J2C-OILFIELD-001" else DEFECTS.get(subject, ())
            definitions[code] = ScenarioDefinition(
                scenario_id=_stable_id("scenario", code),
                scenario_code=code,
                industry_pack_code=pack_code,
                display_name=code.replace("-", " ").title(),
                description=f"Deterministic {pack_code} validation scenario for {subject.lower()}.",
                seed=(list(SCENARIO_CODES).index(pack_code) + 1) * 10_000 + index,
                required_capabilities=CAPABILITIES[pack_code],
                defect_codes=defects,
                event_window=_event_window(code),
            )
    return definitions


SCENARIO_REGISTRY = _scenario_definitions()


def _oracles() -> dict[str, ScenarioOracle]:
    return {
        code: ScenarioOracle(
            oracle_id=_stable_id("oracle", code),
            scenario_id=scenario.scenario_id,
            assertions=(
                OracleAssertion(
                    kind=AssertionKind.EXACT,
                    path="scenario_code",
                    expected=code,
                ),
                OracleAssertion(
                    kind=AssertionKind.EXACT,
                    path="defect_count",
                    expected=len(scenario.defect_codes),
                ),
                OracleAssertion(
                    kind=AssertionKind.EXACT,
                    path="pack_code",
                    expected=scenario.industry_pack_code,
                ),
            ),
        )
        for code, scenario in SCENARIO_REGISTRY.items()
    }


ORACLE_REGISTRY = _oracles()


class SimulationGenerator:
    def generate(
        self,
        scenario_code: str,
        organization_id: UUID,
        *,
        seed: int | None = None,
    ) -> SimulationArtifact:
        try:
            scenario = SCENARIO_REGISTRY[scenario_code]
        except KeyError as exc:
            raise ValueError(f"Unknown validation scenario: {scenario_code}") from exc
        selected_seed = scenario.seed if seed is None else seed
        rng = random.Random(selected_seed)
        records = self._records(scenario, organization_id, rng)
        manifest: dict[str, Any] = {
            "schema_version": "1.0",
            "scenario_id": str(scenario.scenario_id),
            "scenario_code": scenario.scenario_code,
            "scenario_version": scenario.scenario_version,
            "pack_code": scenario.industry_pack_code,
            "pack_version": scenario.industry_pack_version,
            "organization_id": str(organization_id),
            "seed": selected_seed,
            "record_count": len(records),
            "defect_count": len(scenario.defect_codes),
            "defects": list(scenario.defect_codes),
            "oracle_id": str(ORACLE_REGISTRY[scenario_code].oracle_id),
            "event_window": (
                scenario.event_window.model_dump(mode="json") if scenario.event_window else None
            ),
        }
        canonical = json.dumps(
            {"manifest": manifest, "records": records},
            sort_keys=True,
            separators=(",", ":"),
        )
        return SimulationArtifact(
            scenario_code=scenario_code,
            scenario_version=scenario.scenario_version,
            seed=selected_seed,
            organization_id=organization_id,
            pack_code=scenario.industry_pack_code,
            records=tuple(records),
            defects=scenario.defect_codes,
            manifest=manifest,
            content_hash=hashlib.sha256(canonical.encode()).hexdigest(),
        )

    def _records(
        self,
        scenario: ScenarioDefinition,
        organization_id: UUID,
        rng: random.Random,
    ) -> list[dict[str, Any]]:
        if scenario.scenario_code == "J2C-OILFIELD-001":
            types: tuple[str, ...] = (
                "branch",
                "branch",
                "customer",
                "customer",
                "customer",
                "contract",
                "rate_sheet",
                "purchase_order",
                "field_job",
                "field_ticket",
                "customer_approval",
                "labor_regular",
                "labor_overtime",
                "equipment_unit",
                "equipment_deployment",
                "material",
                "mobilization",
                "demobilization",
                "standby",
                "change_order",
                "invoice",
                "invoice_line",
                "payment",
                "credit",
                "dispute",
                "recovery_action",
                "verified_value",
                "reversal",
            )
        else:
            types = ("source_record", "business_event", "measurement", "reference")
        return [
            {
                "record_id": str(
                    uuid5(
                        SIMULATION_NAMESPACE,
                        f"{scenario.scenario_code}:{organization_id}:{index}:{rng.random()}",
                    )
                ),
                "organization_id": str(organization_id),
                "record_type": record_type,
                "sequence": index,
                "value": str(Decimal(rng.randrange(1_000, 100_000)) / Decimal("100")),
                "currency_code": "USD",
            }
            for index, record_type in enumerate(types, 1)
        ]


@dataclass(frozen=True)
class OracleComparator:
    def compare(self, actual: dict[str, Any], oracle: ScenarioOracle) -> OracleComparison:
        failures: list[str] = []
        for assertion in oracle.assertions:
            value = _resolve(actual, assertion.path)
            if assertion.kind is AssertionKind.EXACT and value != assertion.expected:
                failures.append(f"{assertion.path}: expected {assertion.expected!r}, got {value!r}")
            elif assertion.kind is AssertionKind.TOLERANCE:
                difference = abs(Decimal(str(value)) - Decimal(str(assertion.expected)))
                if difference > assertion.tolerance:  # type: ignore[operator]
                    failures.append(f"{assertion.path}: tolerance exceeded")
            elif assertion.kind is AssertionKind.RANGE:
                numeric = Decimal(str(value))
                if not assertion.minimum <= numeric <= assertion.maximum:  # type: ignore[operator]
                    failures.append(f"{assertion.path}: outside expected range")
            elif assertion.kind is AssertionKind.REQUIRED and not value:
                failures.append(f"{assertion.path}: required value missing")
            elif assertion.kind is AssertionKind.FORBIDDEN and value:
                failures.append(f"{assertion.path}: forbidden value present")
        return OracleComparison(
            passed=not failures,
            failures=tuple(failures),
            assertion_count=len(oracle.assertions),
        )


def _resolve(payload: dict[str, Any], path: str) -> Any:
    value: Any = payload
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value
