from __future__ import annotations

from hashlib import sha256
from uuid import UUID, uuid5

GRAPH_NAMESPACE = UUID("6d65718b-4171-4c81-8ce1-e0065198d605")

ENTITY_TYPE_CODES = (
    "source_system",
    "ingestion_batch",
    "dataset",
    "dataset_version",
    "lineage_node",
    "trust_assessment",
    "feature_version",
    "oikb_definition_version",
    "analytical_execution",
    "signature_version",
    "signature_execution",
    "finding",
    "finding_evidence_bundle",
    "recommendation",
    "operational_action",
    "action_outcome",
    "recovery_opportunity",
    "recovery_case",
    "recovery_execution",
    "recovery_measurement",
    "finance_verification",
    "verified_value_ledger_entry",
    "industry_pack_version",
    "industry_pack_assignment",
    "job_to_cash_run",
)

RELATIONSHIP_TYPE_CODES = (
    "originated_from",
    "derived_from",
    "validated_by",
    "supported_by",
    "describes",
    "affects",
    "occurred_on",
    "participates_in",
    "detected_by",
    "produced_finding",
    "explained_by",
    "recommended",
    "addressed_by",
    "executed_as",
    "resulted_in",
    "measured_by",
    "verified_by",
    "posted_as",
    "uses_feature",
    "uses_rule",
    "uses_model",
    "uses_signature",
    "belongs_to_process",
    "governed_by_pack",
    "supersedes",
    "correlated_with",
)

RELATIONSHIP_ENDPOINTS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "originated_from": (
        ("ingestion_batch", "dataset", "dataset_version", "finding"),
        ("source_system", "ingestion_batch", "dataset", "lineage_node"),
    ),
    "derived_from": (ENTITY_TYPE_CODES, ENTITY_TYPE_CODES),
    "validated_by": (
        ("dataset_version", "analytical_execution", "finding", "recovery_measurement"),
        ("trust_assessment", "finance_verification"),
    ),
    "supported_by": (
        ("finding", "operational_action", "action_outcome", "recovery_measurement"),
        ("finding_evidence_bundle", "lineage_node", "analytical_execution"),
    ),
    "describes": (
        ("finding_evidence_bundle", "finding", "recovery_measurement"),
        ("finding", "operational_action", "action_outcome", "recovery_case"),
    ),
    "affects": (
        ("finding", "operational_action", "recovery_opportunity"),
        ("dataset", "dataset_version", "recovery_case", "job_to_cash_run"),
    ),
    "occurred_on": (
        ("analytical_execution", "signature_execution", "action_outcome"),
        ("dataset_version", "job_to_cash_run"),
    ),
    "participates_in": (
        ("finding", "operational_action", "recovery_measurement"),
        ("recovery_case", "job_to_cash_run"),
    ),
    "detected_by": (
        ("finding",),
        ("analytical_execution", "signature_execution"),
    ),
    "produced_finding": (
        ("analytical_execution", "signature_execution", "job_to_cash_run"),
        ("finding",),
    ),
    "explained_by": (
        ("finding", "action_outcome"),
        ("analytical_execution", "signature_execution", "finding_evidence_bundle"),
    ),
    "recommended": (
        ("finding", "recovery_opportunity"),
        ("recommendation", "operational_action"),
    ),
    "addressed_by": (
        ("finding", "recovery_opportunity"),
        ("operational_action", "recovery_case"),
    ),
    "executed_as": (
        ("recommendation", "operational_action", "recovery_case"),
        ("operational_action", "recovery_execution"),
    ),
    "resulted_in": (
        ("operational_action", "recovery_execution"),
        ("action_outcome", "recovery_measurement"),
    ),
    "measured_by": (
        ("action_outcome", "recovery_case", "recovery_execution"),
        ("recovery_measurement",),
    ),
    "verified_by": (
        ("recovery_measurement",),
        ("finance_verification",),
    ),
    "posted_as": (
        ("finance_verification",),
        ("verified_value_ledger_entry",),
    ),
    "uses_feature": (
        ("analytical_execution", "signature_version", "signature_execution"),
        ("feature_version",),
    ),
    "uses_rule": (
        ("analytical_execution", "signature_version", "signature_execution"),
        ("oikb_definition_version",),
    ),
    "uses_model": (
        ("analytical_execution", "signature_version", "signature_execution"),
        ("oikb_definition_version",),
    ),
    "uses_signature": (
        ("signature_execution", "finding"),
        ("signature_version",),
    ),
    "belongs_to_process": (
        ("finding", "operational_action", "recovery_case"),
        ("job_to_cash_run",),
    ),
    "governed_by_pack": (
        ("analytical_execution", "signature_version", "finding", "job_to_cash_run"),
        ("industry_pack_version", "industry_pack_assignment"),
    ),
    "supersedes": (ENTITY_TYPE_CODES, ENTITY_TYPE_CODES),
    "correlated_with": (ENTITY_TYPE_CODES, ENTITY_TYPE_CODES),
}

ENTITY_SOURCE_REGISTRIES = {
    "source_system": "source_systems",
    "ingestion_batch": "ingestion_batches",
    "dataset": "datasets",
    "dataset_version": "dataset_versions",
    "lineage_node": "lineage_nodes",
    "trust_assessment": "trust_assessments",
    "feature_version": "operational_feature_versions",
    "oikb_definition_version": "oikb_definition_versions",
    "analytical_execution": "intelligence_executions",
    "signature_version": "operational_signature_versions",
    "signature_execution": "operational_signature_executions",
    "finding": "findings",
    "finding_evidence_bundle": "finding_evidence_bundles",
    "recommendation": "recommendations",
    "operational_action": "operational_actions",
    "action_outcome": "action_outcomes",
    "recovery_opportunity": "recovery_opportunities",
    "recovery_case": "recovery_cases",
    "recovery_execution": "recovery_executions",
    "recovery_measurement": "recovery_value_measurements",
    "finance_verification": "recovery_finance_verifications",
    "verified_value_ledger_entry": "verified_value_ledger_entries",
    "industry_pack_version": "industry_pack_versions",
    "industry_pack_assignment": "industry_pack_assignment_states",
    "job_to_cash_run": "job_to_cash_runs",
}
SOURCE_REGISTRIES = frozenset(ENTITY_SOURCE_REGISTRIES.values())

EVIDENCE_SOURCE_TYPES = frozenset(
    {
        "lineage_node",
        "finding_evidence_bundle",
        "finding_evidence_item",
        "signature_execution",
        "signature_execution_evidence",
        "analytical_execution",
        "analytical_execution_evidence",
        "trust_assessment",
        "trust_evidence",
        "action_evidence",
        "action_outcome",
        "recovery_evidence",
        "recovery_measurement",
        "finance_verification",
        "verified_value_ledger_entry",
        "validation_result",
    }
)


def graph_id(kind: str, code: str) -> UUID:
    return uuid5(GRAPH_NAMESPACE, f"{kind}:{code}")


def definition_hash(kind: str, code: str) -> str:
    return sha256(f"wp-3.01:{kind}:{code}:1.0.0".encode()).hexdigest()
