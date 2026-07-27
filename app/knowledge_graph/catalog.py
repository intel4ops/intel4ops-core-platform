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


def graph_id(kind: str, code: str) -> UUID:
    return uuid5(GRAPH_NAMESPACE, f"{kind}:{code}")


def definition_hash(kind: str, code: str) -> str:
    return sha256(f"wp-3.01:{kind}:{code}:1.0.0".encode()).hexdigest()
