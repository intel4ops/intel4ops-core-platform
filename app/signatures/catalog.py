from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID, uuid5

SIGNATURE_NAMESPACE = UUID("4aa23db2-6598-446f-900d-a8ef9f70c90b")


def asset_id(kind: str, code: str, version: str = "1.0.0") -> UUID:
    return uuid5(SIGNATURE_NAMESPACE, f"{kind}:{code}:{version}")


def definition_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


FEATURE_CATALOG: dict[str, dict[str, Any]] = {
    "SHARED.FEATURE.COMPLETION_TO_INVOICE_DAYS": {
        "name": "Completion to Invoice",
        "description": "Elapsed days from governed operational completion to invoice issue.",
        "owner": "revenue-operations",
        "entity_grain": "job",
        "time_grain": "event_interval",
        "value_type": "decimal",
        "unit_behavior": "days",
        "currency_behavior": "not_applicable",
        "required_canonical_objects": ["job", "invoice"],
        "input_contract": {"required": ["job.completed_at", "invoice.issued_at"]},
        "computation_reference": {"type": "oikb", "code": "SHARED.TIME.ELAPSED_DURATION"},
    },
    "SHARED.FEATURE.FUEL_VARIANCE": {
        "name": "Fuel Variance",
        "description": "Actual fuel consumption variance from governed expected consumption.",
        "owner": "mobility-operations",
        "entity_grain": "asset_period",
        "time_grain": "declared",
        "value_type": "decimal",
        "unit_behavior": "same_unit",
        "currency_behavior": "not_applicable",
        "required_canonical_objects": ["asset", "fuel_observation"],
        "input_contract": {"required": ["actual_fuel", "expected_fuel", "unit"]},
        "computation_reference": {"type": "oikb", "code": "SHARED.VARIANCE.ABSOLUTE"},
    },
    "SHARED.FEATURE.CYCLE_TIME": {
        "name": "Cycle Time",
        "description": "Elapsed duration for one governed process cycle.",
        "owner": "manufacturing-operations",
        "entity_grain": "asset_cycle",
        "time_grain": "cycle",
        "value_type": "decimal",
        "unit_behavior": "duration",
        "currency_behavior": "not_applicable",
        "required_canonical_objects": ["asset", "cycle_event"],
        "input_contract": {"required": ["cycle.started_at", "cycle.completed_at"]},
        "computation_reference": {"type": "oikb", "code": "SHARED.TIME.ELAPSED_DURATION"},
    },
    "SHARED.FEATURE.EQUIPMENT_UTILIZATION": {
        "name": "Equipment Utilization",
        "description": "Productive equipment time divided by available equipment time.",
        "owner": "asset-operations",
        "entity_grain": "asset_period",
        "time_grain": "declared",
        "value_type": "ratio",
        "unit_behavior": "ratio",
        "currency_behavior": "not_applicable",
        "required_canonical_objects": ["asset", "operating_interval"],
        "input_contract": {"required": ["productive_time", "available_time"]},
        "computation_reference": {"type": "oikb", "code": "SHARED.RATIO.SAFE_DIVIDE"},
    },
    "SHARED.FEATURE.LABOR_EFFICIENCY": {
        "name": "Labor Efficiency",
        "description": "Governed standard labor hours relative to actual labor hours.",
        "owner": "workforce-operations",
        "entity_grain": "work_order",
        "time_grain": "work_order",
        "value_type": "ratio",
        "unit_behavior": "ratio",
        "currency_behavior": "not_applicable",
        "required_canonical_objects": ["work_order", "labor_entry"],
        "input_contract": {"required": ["standard_hours", "actual_hours"]},
        "computation_reference": {"type": "oikb", "code": "SHARED.RATIO.SAFE_DIVIDE"},
    },
    "SHARED.FEATURE.CONTRACT_COMPLIANCE": {
        "name": "Contract Compliance",
        "description": "Conformance of operational charges and terms to the effective contract.",
        "owner": "commercial-operations",
        "entity_grain": "transaction",
        "time_grain": "event",
        "value_type": "boolean",
        "unit_behavior": "not_applicable",
        "currency_behavior": "preserve_declared",
        "required_canonical_objects": ["contract", "transaction"],
        "input_contract": {"required": ["contract_reference", "effective_at", "actual_terms"]},
        "computation_reference": {"type": "rule", "code": "CONTRACT.COMPLIANCE"},
    },
    "SHARED.FEATURE.EXPECTED_BILLING": {
        "name": "Expected Billing",
        "description": "Evidence-backed billing expected under governed contract terms.",
        "owner": "revenue-operations",
        "entity_grain": "job",
        "time_grain": "job",
        "value_type": "decimal",
        "unit_behavior": "currency",
        "currency_behavior": "single_currency",
        "required_canonical_objects": ["contract", "job", "rate_sheet"],
        "input_contract": {"required": ["contract", "rate_sheet", "billable_activity"]},
        "computation_reference": {"type": "engine", "code": "job_to_cash"},
    },
}

for feature in FEATURE_CATALOG.values():
    feature["validation_contract"] = {
        "reproducible": True,
        "lineage_required": True,
        "unit_safe": True,
    }
    feature["known_limitations"] = ["Requires governed canonical inputs and readiness."]


SIGNATURE_CATALOG: dict[str, dict[str, Any]] = {
    "J2C.SIGNATURE.OILFIELD.BILLING_LEAKAGE": {
        "name": "Oilfield Billing Leakage",
        "description": "Detects completed work with delayed evidence and incomplete billing.",
        "signature_type": "leakage",
        "industry": "oilfield_services",
        "owner": "revenue-operations",
        "applicable_pack_versions": ["PACK-J2C@1.0.0"],
        "required_canonical_objects": [
            "contract",
            "purchase_order",
            "field_job",
            "field_ticket",
            "invoice",
        ],
        "required_features": [
            {"code": "SHARED.FEATURE.COMPLETION_TO_INVOICE_DAYS", "version": "1.0.0"},
            {"code": "SHARED.FEATURE.EXPECTED_BILLING", "version": "1.0.0"},
            {"code": "SHARED.FEATURE.CONTRACT_COMPLIANCE", "version": "1.0.0"},
        ],
        "required_events": [
            "job_completed",
            "documentation_delayed",
            "equipment_record_posted_late",
            "incomplete_invoice",
        ],
        "required_conditions": [
            {"path": "billing_variance", "operator": "greater_than", "value": "0"},
            {"path": "documentation_complete", "operator": "equals", "value": False},
        ],
        "exclusion_conditions": [
            {"path": "job_cancelled", "operator": "equals", "value": True},
        ],
        "evidence_requirements": [
            "contract",
            "field_ticket",
            "expected_billing_trace",
            "invoice",
        ],
        "confidence_model": {
            "base": "0.70",
            "evidence_increment": "0.05",
            "maximum": "0.98",
        },
        "economic_impact_policy": {
            "type": "billing_variance",
            "currency_behavior": "single_currency",
        },
        "expected_outcome": {
            "finding_type": "revenue_leakage",
            "recovery": "supplemental_invoice",
        },
        "supporting_algorithms": ["job_to_cash"],
        "supporting_rules": ["J2C-CNI-001", "J2C-UNDERBILL"],
        "supporting_models": [],
        "dependencies": [],
        "scenario_code": "J2C-OILFIELD-001",
    },
    "MFG.SIGNATURE.SERVO.DEGRADATION": {
        "name": "Servo Degradation Sequence",
        "description": "Detects a governed multi-event sequence preceding servo degradation.",
        "signature_type": "predictive",
        "industry": "manufacturing",
        "owner": "reliability-engineering",
        "applicable_pack_versions": ["PACK-MFG@1.0.0"],
        "required_canonical_objects": ["asset", "sensor_observation", "maintenance_event"],
        "required_features": [
            {"code": "SHARED.FEATURE.CYCLE_TIME", "version": "1.0.0"},
            {"code": "SHARED.FEATURE.EQUIPMENT_UTILIZATION", "version": "1.0.0"},
        ],
        "required_events": [
            "rising_load_adjusted_current_variance",
            "increasing_temperature_slope",
            "repeated_position_correction",
            "cycle_time_drift",
            "intermittent_alarm",
        ],
        "required_conditions": [
            {"path": "ordered_sequence", "operator": "equals", "value": True},
            {"path": "observation_window_days", "operator": "less_or_equal", "value": 30},
        ],
        "exclusion_conditions": [
            {"path": "maintenance_completed", "operator": "equals", "value": True},
        ],
        "evidence_requirements": [
            "current_observation",
            "temperature_observation",
            "position_correction",
            "cycle_time",
            "alarm",
        ],
        "confidence_model": {
            "base": "0.60",
            "evidence_increment": "0.07",
            "maximum": "0.95",
        },
        "economic_impact_policy": {
            "type": "failure_exposure",
            "currency_behavior": "organization_default",
        },
        "expected_outcome": {
            "finding_type": "asset_degradation_risk",
            "intervention": "maintenance_inspection",
        },
        "supporting_algorithms": ["reliability.condition_deterioration"],
        "supporting_rules": ["MFG-MAINT"],
        "supporting_models": ["reliability.failure_risk"],
        "dependencies": [],
        "scenario_code": "MFG-SERVO-DEGRADATION-001",
    },
}

for signature in SIGNATURE_CATALOG.values():
    signature["monitoring_policy"] = {
        "minimum_sample_size": 30,
        "warning_false_positive_rate": "0.15",
        "suspend_false_positive_rate": "0.30",
        "revalidation_period_days": 90,
    }
    signature["known_limitations"] = [
        "A match is evidence for governed investigation, not proof of causation or misconduct."
    ]
    signature["definition_hash"] = definition_hash(signature)
