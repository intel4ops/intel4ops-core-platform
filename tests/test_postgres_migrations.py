import ast
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from importlib import import_module
from pathlib import Path
from threading import Barrier, Event
from typing import Any, cast
from unittest.mock import patch
from urllib.parse import urlparse
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from governed_provenance_helpers import add_eligible_dataset_version
from sqlalchemy import Table, create_engine, delete, func, insert, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.interfaces import ReflectedForeignKeyConstraint
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_ai_operational_profile_service import FakeProvider
from test_ai_operational_profile_service import item as ai_profile_item
from test_canonical_mapping_foundation import discovered_schema as cm01_discovered_schema
from test_canonical_mapping_foundation import foundation as canonical_mapping_foundation
from test_canonical_mapping_foundation import (
    published_entity_mapping as cm01_published_entity_mapping,
)
from test_causal_intelligence_foundation import confirm_hypothesis as confirm_causal_hypothesis
from test_causal_intelligence_foundation import make_org as make_causal_org
from test_cm03_field_mapping_idempotency import _mapping_context as cm03_mapping_context
from test_cm03_field_mapping_idempotency import _payload as cm03_payload
from test_decision_intelligence_foundation import add_graph as add_decision_graph
from test_decision_intelligence_foundation import make_org as make_decision_org
from test_executive_narrative_service import FakeNarrativeProvider
from test_executive_narrative_service import organization as narrative_organization
from test_executive_narrative_service import scan as narrative_scan
from test_forecasting_service import foundation as forecasting_foundation
from test_forecasting_service import payload as forecasting_payload
from test_ingestion_service import batch_payload as ingestion_batch_payload
from test_ingestion_service import foundation as ingestion_foundation
from test_operational_memory_service import field_candidate as memory_field_candidate
from test_operational_memory_service import memory_foundation
from test_progressive_orchestrator import foundation as orchestration_foundation
from test_progressive_orchestrator import request as orchestration_payload
from test_reliability_service import (
    add_reliability_definition,
    reliability_foundation,
    reliability_payload,
)
from test_statistical_service import execution_payload, statistical_foundation
from test_ti_a_referential_integrity import (
    PARENT_CONSTRAINTS as TI_A_PARENT_CONSTRAINTS,
)
from test_ti_a_referential_integrity import TENANT_FOREIGN_KEYS as TI_A_FOREIGN_KEYS
from test_ti_a_referential_integrity import TENANT_INDEXES as TI_A_INDEXES
from test_ti_b1_referential_integrity import (
    PARENT_CONSTRAINTS as TI_B1_PARENT_CONSTRAINTS,
)
from test_ti_b1_referential_integrity import TENANT_FOREIGN_KEYS as TI_B1_FOREIGN_KEYS
from test_ti_b1_referential_integrity import TENANT_INDEXES as TI_B1_INDEXES
from test_ti_b2_referential_integrity import NEW_INDEXES as TI_B2_INDEXES
from test_ti_b2_referential_integrity import (
    PARENT_CONSTRAINTS as TI_B2_PARENT_CONSTRAINTS,
)
from test_ti_b2_referential_integrity import REUSED_INDEXES as TI_B2_REUSED_INDEXES
from test_ti_b2_referential_integrity import TENANT_FOREIGN_KEYS as TI_B2_FOREIGN_KEYS
from test_ti_b3_referential_integrity import NEW_INDEXES as TI_B3_INDEXES
from test_ti_b3_referential_integrity import (
    PARENT_CONSTRAINTS as TI_B3_PARENT_CONSTRAINTS,
)
from test_ti_b3_referential_integrity import REUSED_INDEXES as TI_B3_REUSED_INDEXES
from test_ti_b3_referential_integrity import TENANT_FOREIGN_KEYS as TI_B3_FOREIGN_KEYS
from test_ti_c1_referential_integrity import NEW_INDEXES as TI_C1_INDEXES
from test_ti_c1_referential_integrity import (
    PARENT_CONSTRAINTS as TI_C1_PARENT_CONSTRAINTS,
)
from test_ti_c1_referential_integrity import REUSED_INDEXES as TI_C1_REUSED_INDEXES
from test_ti_c1_referential_integrity import TENANT_FOREIGN_KEYS as TI_C1_FOREIGN_KEYS
from test_ti_c1_referential_integrity import _lineage_request as ti_c1_lineage_request
from test_ti_c1_referential_integrity import (
    _orchestration_graph as ti_c1_orchestration_graph,
)
from test_ti_c2_referential_integrity import NEW_INDEXES as TI_C2_INDEXES
from test_ti_c2_referential_integrity import (
    PARENT_CONSTRAINTS as TI_C2_PARENT_CONSTRAINTS,
)
from test_ti_c2_referential_integrity import RELATIONSHIPS as TI_C2_RELATIONSHIPS
from test_ti_c2_referential_integrity import REUSED_INDEXES as TI_C2_REUSED_INDEXES
from test_ti_c2_referential_integrity import TENANT_FOREIGN_KEYS as TI_C2_FOREIGN_KEYS
from test_ti_c2_referential_integrity import _action as ti_c2_action
from test_ti_c2_referential_integrity import _organization as ti_c2_organization
from test_trust_service import trust_foundation

from app.core.config import Settings
from app.models.access import InvitationStatus, OrganizationInvitation
from app.models.actions import ActionPlanStep
from app.models.canonical_mapping import (
    FieldMapping,
    MappingRecordResult,
    MappingRun,
    MappingRunInput,
    MappingRunStatus,
)
from app.models.causal_intelligence import CausalEvidenceLink, CausalHypothesis
from app.models.decision_intelligence import DecisionApproval, DecisionRecommendation
from app.models.entities import (
    Finding,
    FindingGovernanceTier,
    MembershipRole,
    MembershipStatus,
    Organization,
    OrganizationMembership,
)
from app.models.executive_narrative import GroundedExecutiveNarrative
from app.models.forecasting import (
    ForecastBacktest,
    ForecastCandidate,
    ForecastExecution,
    ForecastExecutionStep,
    ForecastMetric,
    ForecastPoint,
)
from app.models.ingestion import Dataset, DatasetVersion, IngestionBatch
from app.models.oikb import OIKBDefinition, OIKBDefinitionVersion
from app.models.operational_memory import (
    OperationalMemoryItem,
    OperationalMemoryReuseEvent,
    OperationalMemoryVersion,
)
from app.models.orchestration import (
    IntelligenceOrchestrationDecision,
    IntelligenceOrchestrationRequest,
    IntelligenceOrchestrationStep,
)
from app.models.reliability import (
    ReliabilityExecution,
    ReliabilityExecutionStep,
    ReliabilityMetric,
    ReliabilityModelResult,
    ReliabilityReviewFeedback,
)
from app.models.statistics import (
    AnomalyReviewFeedback,
    StatisticalExecution,
    StatisticalObservation,
)
from app.models.trust import (
    AnalyticalReadinessDecision,
    TrustAssessment,
    TrustRuleResult,
)
from app.models.value_scan import DirectionalValueScan
from app.models.workspace import OrganizationObjective
from app.schemas.access import InvitationCreate
from app.schemas.canonical_mapping import (
    MappingInputRecord,
    MappingRunCreate,
    MappingRunRetryCreate,
    SourceFieldCreate,
    SourceSchemaDiscover,
)
from app.schemas.causal_intelligence import CausalReviewCreate
from app.schemas.contracts import FindingCreate, OrganizationCreate
from app.schemas.decision_intelligence import DecisionApprovalCreate
from app.schemas.executive_narrative import ExecutiveNarrativeCreate
from app.schemas.findings import CandidateFindingCreate
from app.schemas.forecasting import ForecastExecutionCreate
from app.schemas.ingestion import (
    DatasetCreate,
    DatasetVersionCountsUpdate,
    DatasetVersionCreate,
    IngestionBatchCreate,
)
from app.schemas.intelligence import IntelligenceExecutionCreate
from app.schemas.memberships import MembershipCreate
from app.schemas.operational_memory import (
    MemoryCandidateCreate,
    MemoryContext,
    MemoryDecisionRequest,
    MemoryProvenance,
    MemoryRetrieveRequest,
)
from app.schemas.orchestration import OrchestrationCreate
from app.schemas.raw_lineage import RawStorageObjectCreate
from app.schemas.reliability import CensoringStatus, ReliabilityExecutionCreate
from app.schemas.source_systems import SourceSystemCreate
from app.schemas.trust import TrustAssessmentCreate
from app.services.access_context_service import (
    OrganizationProvisioningError,
    create_organization_with_owner,
)
from app.services.ai_operational_profile_service import AIOperationalProfileService
from app.services.canonical_mapping_service import (
    CanonicalMappingServiceError,
    mapping_execution_service,
    mapping_template_service,
    schema_discovery_service,
)
from app.services.causal_intelligence_service import (
    CausalIntelligenceServiceError,
    causal_review_service,
)
from app.services.decision_intelligence_service import (
    DecisionIntelligenceServiceError,
    decision_approval_service,
)
from app.services.executive_narrative_service import ExecutiveNarrativeService
from app.services.finding_platform_service import (
    FindingPublicationService,
    FindingQueryService,
)
from app.services.finding_service import FindingService
from app.services.forecasting_service import ForecastExecutionService, ForecastingServiceError
from app.services.ingestion_service import (
    DatasetService,
    DatasetVersionService,
    IngestionBatchService,
)
from app.services.intelligence_service import IntelligenceExecutionService
from app.services.invitation_service import InvitationServiceError, invitation_service
from app.services.membership_service import (
    DuplicateMembershipError,
    LastActiveOrganizationAdminError,
    OrganizationMembershipService,
)
from app.services.operational_memory_service import (
    OperationalMemoryServiceError,
    operational_memory_service,
)
from app.services.orchestration_service import OrchestrationService
from app.services.organization_service import OrganizationService
from app.services.raw_lineage_service import RawStorageObjectService
from app.services.reliability_service import (
    ReliabilityExecutionService,
    ReliabilityServiceError,
    reliability_execution_service,
)
from app.services.source_system_service import (
    DuplicateSourceSystemCodeError,
    SourceSystemService,
)
from app.services.statistical_service import (
    StatisticalExecutionService,
    statistical_execution_service,
)
from app.services.trust_service import TrustAssessmentService
from app.services.value_scan_service import directional_value_scan_service
from app.services.workspace_service import list_objectives, replace_objectives

WP_301_MAPPING_TABLES = {
    "canonical_entity_types",
    "canonical_field_definitions",
    "canonical_event_types",
    "canonical_metric_types",
    "mapping_templates",
    "mapping_template_versions",
    "field_mappings",
    "mapping_transformations",
    "value_crosswalks",
    "value_crosswalk_entries",
    "entity_match_rules",
    "source_schemas",
    "source_fields",
    "mapping_runs",
    "mapping_record_results",
    "mapping_exceptions",
    "mapping_reviews",
    "canonical_entities",
    "canonical_events",
    "canonical_metrics",
    "source_canonical_links",
    "entity_match_candidates",
    "mapping_audit_events",
}

P3_03A_TABLES = {"directional_value_scans"}
P3_03B_TABLES = {"ai_operational_profiles", "ai_profile_inferences"}
P3_03C_TABLES = {"grounded_executive_narratives"}
P3_03DA_TABLES = {
    "operational_memory_items",
    "operational_memory_versions",
    "operational_memory_reuse_events",
}
P3_05B_TABLES = {"mapping_run_inputs"}
WP_214B_DECISION_TABLES = {
    "decision_method_definitions",
    "decision_problems",
    "decision_problem_versions",
    "decision_objectives",
    "decision_constraints",
    "decision_variable_definitions",
    "decision_scenarios",
    "decision_scenario_inputs",
    "decision_executions",
    "decision_solutions",
    "decision_alternatives",
    "decision_recommendations",
    "decision_recommendation_evidence",
    "decision_sensitivity_results",
    "decision_approvals",
    "decision_outcome_links",
    "decision_audit_events",
}

MANAGED_TABLES = {
    "organizations",
    "findings",
    "finding_evidence",
    "recovery_actions",
    "organization_members",
    "source_systems",
    "ingestion_batches",
    "datasets",
    "dataset_versions",
    "raw_storage_objects",
    "raw_record_references",
    "processing_runs",
    "lineage_nodes",
    "lineage_edges",
    "lineage_events",
    "trust_assessments",
    "trust_rule_results",
    "trust_evidence",
    "analytical_readiness_decisions",
    "intelligence_executions",
    "intelligence_execution_evidence",
    "finding_evidence_bundles",
    "finding_evidence_items",
    "finding_calculation_traces",
    "finding_rule_traces",
    "finding_reviews",
    "finding_status_history",
    "industry_pack_versions",
    "industry_pack_assignment_states",
    "industry_pack_components",
    "industry_pack_validation_results",
    "industry_pack_executions",
    "industry_pack_governance_events",
    "validation_scenario_versions",
    "validation_oracle_versions",
    "validation_suites",
    "analytical_artifact_versions",
    "release_candidates",
    "validation_runs",
    "release_gate_definitions",
    "release_gate_results",
    "release_waivers",
    "release_certifications",
    "operational_feature_definitions",
    "operational_feature_versions",
    "operational_signature_definitions",
    "operational_signature_versions",
    "operational_signature_validations",
    "operational_signature_lifecycle_events",
    "operational_signature_deployments",
    "operational_signature_executions",
    "operational_signature_execution_evidence",
    "operational_signature_performance_history",
    "operational_signature_monitoring_results",
    "intelligence_orchestration_requests",
    "intelligence_orchestration_decisions",
    "intelligence_orchestration_steps",
    "intelligence_engine_registrations",
    "intelligence_orchestration_status_history",
    "oikb_definitions",
    "oikb_definition_versions",
    "oikb_parameters",
    "oikb_input_requirements",
    "oikb_evidence_requirements",
    "oikb_sources",
    "oikb_definition_sources",
    "oikb_validation_cases",
    "oikb_validation_results",
    "oikb_approvals",
    "oikb_change_log",
    "oikb_relationships",
    "statistical_executions",
    "statistical_baselines",
    "statistical_observations",
    "statistical_score_components",
    "statistical_execution_steps",
    "statistical_method_registry",
    "anomaly_suppression_records",
    "anomaly_review_feedback",
    "forecast_executions",
    "forecast_candidates",
    "forecast_backtests",
    "forecast_metrics",
    "forecast_points",
    "forecast_scenarios",
    "forecast_revisions",
    "forecast_actuals",
    "forecast_accuracy_results",
    "forecast_method_registry",
    "forecast_execution_steps",
    "reliability_executions",
    "reliability_metrics",
    "reliability_model_results",
    "reliability_execution_steps",
    "reliability_method_registry",
    "reliability_review_feedback",
    "operational_actions",
    "action_plan_steps",
    "action_dependencies",
    "action_resource_requirements",
    "action_events",
    "action_evidence",
    "action_outcomes",
    "action_model_feedback",
    "recovery_opportunities",
    "opportunity_findings",
    "opportunity_actions",
    "economic_scenarios",
    "economic_assumptions",
    "economic_calculations",
    "prioritization_assessments",
    "opportunity_overlap_groups",
    "opportunity_overlap_members",
    "opportunity_decisions",
    "economic_audit_events",
    "economic_baseline_versions",
    "recovery_cases",
    "recovery_executions",
    "recovery_value_measurements",
    "recovery_evidence_links",
    "recovery_finance_verifications",
    "verified_value_ledger_entries",
    "recovery_audit_events",
    "products",
    "product_versions",
    "features",
    "plans",
    "plan_versions",
    "plan_version_entitlements",
    "subscriptions",
    "contracts",
    "contract_overrides",
    "entitlements",
    "usage_meter_definitions",
    "usage_events",
    "usage_periods",
    "industry_pack_definitions",
    "industry_pack_assignments",
    "feature_flags",
    "limit_definitions",
    "limit_evaluations",
    "commercial_audit_events",
    "application_clients",
    "api_request_audit_events",
    "job_to_cash_runs",
    "job_to_cash_records",
    "knowledge_graph_entity_types",
    "knowledge_graph_entity_type_versions",
    "knowledge_graph_relationship_types",
    "knowledge_graph_relationship_type_versions",
    "knowledge_graph_governance_events",
    "knowledge_graph_versions",
    "knowledge_graph_nodes",
    "knowledge_graph_edges",
    "knowledge_graph_edge_evidence",
    "knowledge_graph_changes",
    "knowledge_graph_query_runs",
    "knowledge_graph_query_steps",
    "knowledge_graph_projection_checkpoints",
} | WP_301_MAPPING_TABLES
MANAGED_TABLES |= WP_214B_DECISION_TABLES
MANAGED_TABLES |= P3_03A_TABLES
MANAGED_TABLES |= P3_03B_TABLES
MANAGED_TABLES |= P3_03C_TABLES
MANAGED_TABLES |= P3_03DA_TABLES
MANAGED_TABLES |= P3_05B_TABLES
DISPOSABLE_NAME_MARKERS = ("test", "testing", "disposable", "validation")


def require_disposable_postgres_url() -> str:
    database_url = os.getenv("TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("Set TEST_POSTGRES_URL to a disposable PostgreSQL database")
    if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        pytest.fail("TEST_POSTGRES_URL must be a PostgreSQL URL")
    if database_url == os.getenv("DATABASE_URL"):
        pytest.fail("TEST_POSTGRES_URL must not match the runtime DATABASE_URL")
    database_name = urlparse(database_url.replace("postgresql+psycopg://", "postgresql://")).path
    if not any(marker in database_name.lower() for marker in DISPOSABLE_NAME_MARKERS):
        pytest.fail("Disposable PostgreSQL database name must contain a safety marker")
    if os.getenv("CONFIRM_DISPOSABLE_POSTGRES") != "1":
        pytest.fail("Set CONFIRM_DISPOSABLE_POSTGRES=1 to permit destructive migration tests")
    return database_url


@pytest.fixture
def postgres_engine() -> Iterator[Engine]:
    engine = create_engine(require_disposable_postgres_url())
    try:
        yield engine
    finally:
        engine.dispose()


def alembic_config(database_url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    return config


ORIGINAL_ACTION_UNIQUES = {
    "uq_action_idempotency",
    "uq_action_plan_step_sequence",
    "uq_action_dependency_pair",
    "uq_action_event_idempotency",
    "uq_action_outcome_type",
    "uq_action_feedback",
}

ORIGINAL_ACTION_INDEXES = {
    "ix_action_org_status",
    "ix_action_org_source",
    "ix_action_org_due",
    "ix_action_plan_step_org_action",
    "ix_action_dependency_org_action",
    "ix_action_resource_org_action",
    "ix_action_event_org_action",
    "ix_action_evidence_org_action",
    "ix_action_outcome_org_action",
    "ix_action_feedback_org_action",
}

ACTION_TABLES_AT_0014 = {
    "operational_actions",
    "action_plan_steps",
    "action_dependencies",
    "action_resource_requirements",
    "action_events",
    "action_evidence",
    "action_outcomes",
    "action_model_feedback",
}

ORIGINAL_ACTION_COLUMN_CONTRACT = {
    "operational_actions": (
        "id organization_id source_type source_reference reliability_execution_id "
        "finding_id forecast_execution_id orchestration_request_id recommendation_type "
        "recommendation_rule_version title description rationale asset_reference "
        "component_reference failure_mode priority priority_score priority_components status "
        "approval_required approval_level approval_role approval_status assigned_user_id "
        "assigned_role assigned_team verification_required verification_owner_id due_at "
        "scheduled_start scheduled_finish completed_at verified_at expected_avoided_cost "
        "expected_intervention_cost currency_code confidence_score limitations "
        "evidence_references idempotency_fingerprint created_by_user_id created_at updated_at",
        "reliability_execution_id finding_id forecast_execution_id orchestration_request_id "
        "asset_reference component_reference failure_mode assigned_user_id assigned_role "
        "assigned_team verification_owner_id due_at scheduled_start scheduled_finish "
        "completed_at verified_at expected_avoided_cost expected_intervention_cost "
        "currency_code confidence_score",
    ),
    "action_plan_steps": (
        "id organization_id action_id sequence_number title description required_skill "
        "labor_category estimated_labor_hours required_tools required_permits "
        "work_order_reference external_system_reference status created_at",
        "required_skill labor_category estimated_labor_hours work_order_reference "
        "external_system_reference",
    ),
    "action_dependencies": (
        "id organization_id action_id prerequisite_action_id dependency_type mandatory status "
        "blocking_reason resolved_at created_at",
        "blocking_reason resolved_at",
    ),
    "action_resource_requirements": (
        "id organization_id action_id resource_type resource_identifier description "
        "required_quantity available_quantity mandatory inventory_check_status "
        "reservation_status reservation_reference source_system_reference required_by "
        "shortage limitation created_at",
        "available_quantity reservation_reference source_system_reference required_by limitation",
    ),
    "action_events": (
        "id organization_id action_id event_type prior_status new_status actor_user_id actor_role "
        "reason_code note metadata_json idempotency_key occurred_at",
        "prior_status new_status note",
    ),
    "action_evidence": (
        "id organization_id action_id lifecycle_stage evidence_type source_type "
        "source_identifier document_reference measurement_value measurement_unit observed_at "
        "actor_user_id notes metadata_json integrity_fingerprint created_at",
        "document_reference measurement_value measurement_unit observed_at notes "
        "integrity_fingerprint",
    ),
    "action_outcomes": (
        "id organization_id action_id outcome_type avoided_cost intervention_cost "
        "downtime_avoided production_preserved risk_reduction currency_code confidence_score "
        "calculation_method verification_method verified_by_user_id verified_at assumptions "
        "limitations created_at",
        "avoided_cost intervention_cost downtime_avoided production_preserved risk_reduction "
        "currency_code confidence_score verification_method verified_by_user_id verified_at",
    ),
    "action_model_feedback": (
        "id organization_id action_id reliability_execution_id "
        "prediction_outcome_classification intervention_performed failure_occurred failure_at "
        "risk_reduced predicted_probability predicted_horizon_days actual_time_to_event_days "
        "recommendation_accepted recommendation_executed calibration_feedback "
        "human_review_status notes created_at",
        "failure_at risk_reduced predicted_probability predicted_horizon_days "
        "actual_time_to_event_days notes",
    ),
}


def _schema_object_names(engine: Engine) -> tuple[set[str], set[str], set[str]]:
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    return (
        {
            str(item["name"])
            for table_name in tables
            for item in inspector.get_unique_constraints(table_name)
            if item["name"] is not None
        },
        {
            str(item["name"])
            for table_name in tables
            for item in inspector.get_foreign_keys(table_name)
            if item["name"] is not None
        },
        {
            str(item["name"])
            for table_name in tables
            for item in inspector.get_indexes(table_name)
            if item["name"] is not None
        },
    )


def _assert_original_action_schema_at_0014(engine: Engine) -> None:
    inspector = inspect(engine)
    assert ACTION_TABLES_AT_0014 <= set(inspector.get_table_names())

    for table_name, (column_names, nullable_names) in ORIGINAL_ACTION_COLUMN_CONTRACT.items():
        columns = inspector.get_columns(table_name)
        assert tuple(str(column["name"]) for column in columns) == tuple(column_names.split())
        assert {str(column["name"]) for column in columns if bool(column["nullable"])} == set(
            nullable_names.split()
        )
        assert all(column["default"] is None for column in columns)

    unique_names = {
        str(item["name"])
        for table_name in ACTION_TABLES_AT_0014
        for item in inspector.get_unique_constraints(table_name)
        if item["name"] is not None
    }
    reflected_indexes = [
        item
        for table_name in ACTION_TABLES_AT_0014
        for item in inspector.get_indexes(table_name)
        if item["name"] is not None
    ]
    if any("duplicates_constraint" in item for item in reflected_indexes):
        index_names = {
            str(item["name"])
            for item in reflected_indexes
            if item.get("duplicates_constraint") is None
        }
    else:
        index_names = {str(item["name"]) for item in reflected_indexes} - ORIGINAL_ACTION_UNIQUES
    foreign_keys = [
        item
        for table_name in ACTION_TABLES_AT_0014
        for item in inspector.get_foreign_keys(table_name)
    ]

    assert unique_names == ORIGINAL_ACTION_UNIQUES
    assert index_names == ORIGINAL_ACTION_INDEXES
    assert len(foreign_keys) == 21
    assert all(len(item["constrained_columns"]) == 1 for item in foreign_keys)

    all_unique_names, all_foreign_key_names, all_index_names = _schema_object_names(engine)
    assert set(TI_B2_PARENT_CONSTRAINTS.values()).isdisjoint(all_unique_names)
    assert set(TI_B3_PARENT_CONSTRAINTS.values()).isdisjoint(all_unique_names)
    assert set(TI_C1_PARENT_CONSTRAINTS.values()).isdisjoint(all_unique_names)
    assert set(TI_C2_PARENT_CONSTRAINTS.values()).isdisjoint(all_unique_names)
    assert TI_B2_FOREIGN_KEYS.isdisjoint(all_foreign_key_names)
    assert TI_B3_FOREIGN_KEYS.isdisjoint(all_foreign_key_names)
    assert TI_C1_FOREIGN_KEYS.isdisjoint(all_foreign_key_names)
    assert TI_C2_FOREIGN_KEYS.isdisjoint(all_foreign_key_names)
    assert TI_C2_INDEXES.isdisjoint(all_index_names)


def _assert_tenant_integrity_revision_boundaries(engine: Engine, config: Config) -> None:
    command.upgrade(config, "20260725_0014")
    _assert_original_action_schema_at_0014(engine)

    command.upgrade(config, "20260801_0027")
    unique_names, foreign_key_names, _ = _schema_object_names(engine)
    assert set(TI_B2_PARENT_CONSTRAINTS.values()) <= unique_names
    assert TI_B2_FOREIGN_KEYS <= foreign_key_names
    assert set(TI_B3_PARENT_CONSTRAINTS.values()).isdisjoint(unique_names)
    assert TI_B3_FOREIGN_KEYS.isdisjoint(foreign_key_names)
    assert TI_C1_FOREIGN_KEYS.isdisjoint(foreign_key_names)
    assert TI_C2_FOREIGN_KEYS.isdisjoint(foreign_key_names)

    command.upgrade(config, "20260801_0028")
    unique_names, foreign_key_names, _ = _schema_object_names(engine)
    assert set(TI_B3_PARENT_CONSTRAINTS.values()) <= unique_names
    assert TI_B3_FOREIGN_KEYS <= foreign_key_names
    assert TI_C1_FOREIGN_KEYS.isdisjoint(foreign_key_names)
    assert TI_C2_FOREIGN_KEYS.isdisjoint(foreign_key_names)

    command.upgrade(config, "20260801_0029")
    unique_names, foreign_key_names, _ = _schema_object_names(engine)
    assert set(TI_C1_PARENT_CONSTRAINTS.values()) <= unique_names
    assert TI_C1_FOREIGN_KEYS <= foreign_key_names
    assert set(TI_C2_PARENT_CONSTRAINTS.values()).isdisjoint(unique_names)
    assert TI_C2_FOREIGN_KEYS.isdisjoint(foreign_key_names)

    command.upgrade(config, "20260802_0030")
    unique_names, foreign_key_names, index_names = _schema_object_names(engine)
    assert set(TI_C2_PARENT_CONSTRAINTS.values()) <= unique_names
    assert TI_C2_FOREIGN_KEYS <= foreign_key_names
    assert TI_C2_INDEXES <= index_names

    command.downgrade(config, "20260725_0014")
    _assert_original_action_schema_at_0014(engine)
    command.upgrade(config, "head")


def test_predictive_action_migration_is_static_and_revision_scoped(
    tmp_path: Path,
) -> None:
    migration_path = Path("migrations/versions/20260725_0014_predictive_action_orchestration.py")
    source = migration_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert all(not module.startswith("app") for module in imported_modules)
    assert "Base.metadata" not in source

    database_path = tmp_path / "migration-determinism.sqlite"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    config = alembic_config(database_url)
    engine = create_engine(database_url)
    try:
        _assert_tenant_integrity_revision_boundaries(engine, config)
    finally:
        engine.dispose()


@pytest.mark.postgres
def test_postgres_tenant_integrity_objects_appear_only_at_owning_revisions(
    postgres_engine: Engine,
) -> None:
    config = alembic_config(require_disposable_postgres_url())
    command.downgrade(config, "base")
    _assert_tenant_integrity_revision_boundaries(postgres_engine, config)


@pytest.mark.postgres
def test_grounded_narrative_concurrent_duplicate_generation_has_one_winner(
    postgres_engine: Engine,
) -> None:
    config = alembic_config(require_disposable_postgres_url())
    command.upgrade(config, "head")
    with Session(postgres_engine) as setup:
        organization = narrative_organization(setup, "narrative-concurrency")
        source = narrative_scan(setup, organization.id, "concurrent")
        organization_id = organization.id
        scan_id = source.id

    barrier = Barrier(2)

    class ConcurrentProvider(FakeNarrativeProvider):
        def generate_narrative(self, request: Any) -> Any:
            barrier.wait(timeout=30)
            return super().generate_narrative(request)

    provider = ConcurrentProvider()
    settings = Settings(ai_enabled=True, ai_api_key="fake", ai_model="fake-model")

    def generate() -> UUID:
        service = ExecutiveNarrativeService(settings)
        service.set_provider_for_testing(provider)
        with Session(postgres_engine) as session:
            row = service.create(
                session,
                organization_id,
                uuid4(),
                ExecutiveNarrativeCreate(
                    scan_id=scan_id,
                    idempotency_key="concurrent-duplicate",
                ),
            )
            return row.id

    with ThreadPoolExecutor(max_workers=2) as pool:
        identifiers = list(pool.map(lambda _: generate(), range(2)))

    assert len(set(identifiers)) == 1
    with Session(postgres_engine) as verification:
        assert (
            verification.scalar(
                select(func.count())
                .select_from(GroundedExecutiveNarrative)
                .where(GroundedExecutiveNarrative.organization_id == organization_id)
            )
            == 1
        )
        verification.execute(
            delete(GroundedExecutiveNarrative).where(
                GroundedExecutiveNarrative.organization_id == organization_id
            )
        )
        verification.execute(
            delete(DirectionalValueScan).where(
                DirectionalValueScan.organization_id == organization_id
            )
        )
        verification.execute(delete(Organization).where(Organization.id == organization_id))
        verification.commit()


def assert_schema_at_head(engine: Engine) -> None:
    inspector = inspect(engine)
    assert MANAGED_TABLES <= set(inspector.get_table_names())

    organization_columns = {
        column["name"]: column for column in inspector.get_columns("organizations")
    }
    assert set(organization_columns) == {
        "id",
        "name",
        "slug",
        "legal_name",
        "industry",
        "sub_industry",
        "country_code",
        "default_currency",
        "timezone",
        "status",
        "description",
        "is_demo",
        "employee_count_range",
        "annual_revenue_range",
        "operating_site_count",
        "created_at",
        "updated_at",
    }
    assert str(organization_columns["id"]["type"]) == "UUID"
    assert organization_columns["id"]["nullable"] is False

    organization_indexes = {
        index["name"]: index for index in inspector.get_indexes("organizations")
    }
    assert organization_indexes["ix_organizations_slug"]["unique"] is True
    assert organization_indexes["ix_organizations_slug"]["column_names"] == ["slug"]
    assert {
        constraint["name"] for constraint in inspector.get_check_constraints("organizations")
    } >= {
        "ck_organizations_status",
        "ck_organizations_operating_site_count_non_negative",
    }

    membership_columns = {
        column["name"]: column for column in inspector.get_columns("organization_members")
    }
    assert set(membership_columns) == {
        "id",
        "organization_id",
        "user_id",
        "role",
        "status",
        "invited_by_user_id",
        "joined_at",
        "created_at",
        "updated_at",
    }
    assert str(membership_columns["id"]["type"]) == "UUID"
    assert str(membership_columns["organization_id"]["type"]) == "UUID"
    assert str(membership_columns["user_id"]["type"]) == "UUID"

    membership_indexes = {
        index["name"]: index for index in inspector.get_indexes("organization_members")
    }
    assert {
        "ix_organization_members_organization_id",
        "ix_organization_members_user_id",
        "ix_organization_members_role",
        "ix_organization_members_status",
    } <= set(membership_indexes)
    membership_unique_constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("organization_members")
    }
    assert "uq_organization_members_organization_user" in membership_unique_constraints
    membership_checks = {
        constraint["name"] for constraint in inspector.get_check_constraints("organization_members")
    }
    assert {
        "ck_organization_members_role",
        "ck_organization_members_status",
    } <= membership_checks
    membership_foreign_keys = inspector.get_foreign_keys("organization_members")
    assert len(membership_foreign_keys) == 1
    assert membership_foreign_keys[0]["constrained_columns"] == ["organization_id"]
    assert membership_foreign_keys[0]["referred_table"] == "organizations"
    assert membership_foreign_keys[0]["options"]["ondelete"] == "CASCADE"

    source_columns = {column["name"]: column for column in inspector.get_columns("source_systems")}
    assert {
        "id",
        "organization_id",
        "code",
        "credential_reference",
        "configuration_metadata",
        "capabilities",
        "failure_count",
        "created_by_user_id",
        "updated_by_user_id",
        "deactivated_at",
    } <= set(source_columns)
    assert str(source_columns["id"]["type"]) == "UUID"
    assert str(source_columns["organization_id"]["type"]) == "UUID"
    assert str(source_columns["configuration_metadata"]["type"]) == "JSONB"
    assert {
        "ix_source_systems_organization_id",
        "ix_source_systems_system_type",
        "ix_source_systems_status",
        "ix_source_systems_health_status",
        "ix_source_systems_provider",
        "ix_source_systems_is_active",
    } <= {index["name"] for index in inspector.get_indexes("source_systems")}
    assert "uq_source_systems_organization_code" in {
        constraint["name"] for constraint in inspector.get_unique_constraints("source_systems")
    }
    assert {
        "ck_source_systems_failure_count",
        "ck_source_systems_system_type",
        "ck_source_systems_integration_method",
        "ck_source_systems_environment",
        "ck_source_systems_status",
        "ck_source_systems_health_status",
        "ck_source_systems_data_classification",
    } <= {constraint["name"] for constraint in inspector.get_check_constraints("source_systems")}
    source_foreign_keys = inspector.get_foreign_keys("source_systems")
    assert len(source_foreign_keys) == 1
    assert source_foreign_keys[0]["referred_table"] == "organizations"
    assert source_foreign_keys[0]["options"]["ondelete"] == "RESTRICT"

    for table, json_column in (
        ("ingestion_batches", "manifest_metadata"),
        ("datasets", "metadata_json"),
        ("dataset_versions", "metadata_json"),
    ):
        columns = {column["name"]: column for column in inspector.get_columns(table)}
        assert str(columns["id"]["type"]) == "UUID"
        assert str(columns["organization_id"]["type"]) == "UUID"
        assert str(columns[json_column]["type"]) == "JSONB"
    assert "uq_ingestion_batches_organization_batch" in {
        constraint["name"] for constraint in inspector.get_unique_constraints("ingestion_batches")
    }
    assert "uq_ingestion_batches_organization_idempotency" in {
        constraint["name"] for constraint in inspector.get_unique_constraints("ingestion_batches")
    }
    assert "uq_datasets_organization_code" in {
        constraint["name"] for constraint in inspector.get_unique_constraints("datasets")
    }
    assert {
        "uq_dataset_versions_dataset_version",
        "uq_dataset_versions_batch_dataset",
    } <= {constraint["name"] for constraint in inspector.get_unique_constraints("dataset_versions")}
    assert {
        "ix_ingestion_batches_organization_id",
        "ix_ingestion_batches_source_system_id",
        "ix_ingestion_batches_status",
    } <= {index["name"] for index in inspector.get_indexes("ingestion_batches")}
    assert {
        "ix_datasets_organization_id",
        "ix_datasets_source_system_id",
        "ix_datasets_status",
    } <= {index["name"] for index in inspector.get_indexes("datasets")}
    assert {
        "ix_dataset_versions_organization_id",
        "ix_dataset_versions_dataset_id",
        "ix_dataset_versions_ingestion_batch_id",
    } <= {index["name"] for index in inspector.get_indexes("dataset_versions")}
    assert {
        foreign_key["referred_table"]
        for foreign_key in inspector.get_foreign_keys("dataset_versions")
    } == {"organizations", "datasets", "ingestion_batches"}

    wp_205_json_columns = {
        "raw_storage_objects": "metadata_json",
        "raw_record_references": "metadata_json",
        "processing_runs": "parameters_json",
        "lineage_nodes": "metadata_json",
        "lineage_edges": "metadata_json",
        "lineage_events": "metadata_json",
    }
    for table, json_column in wp_205_json_columns.items():
        columns = {column["name"]: column for column in inspector.get_columns(table)}
        assert str(columns["id"]["type"]) == "UUID"
        assert str(columns["organization_id"]["type"]) == "UUID"
        assert str(columns[json_column]["type"]) == "JSONB"
    assert "uq_raw_objects_organization_number" in {
        constraint["name"] for constraint in inspector.get_unique_constraints("raw_storage_objects")
    }
    assert "uq_raw_records_object_sequence" in {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("raw_record_references")
    }
    assert "uq_lineage_node_entity" in {
        constraint["name"] for constraint in inspector.get_unique_constraints("lineage_nodes")
    }
    assert {
        "organizations",
        "source_systems",
        "ingestion_batches",
        "dataset_versions",
        "raw_storage_objects",
    } == {
        foreign_key["referred_table"]
        for foreign_key in inspector.get_foreign_keys("raw_storage_objects")
    }

    execution_columns = {
        column["name"]: column for column in inspector.get_columns("intelligence_executions")
    }
    assert str(execution_columns["id"]["type"]) == "UUID"
    assert str(execution_columns["organization_id"]["type"]) == "UUID"
    assert str(execution_columns["parameters_json"]["type"]) == "JSONB"
    assert str(execution_columns["result_value"]["type"]) == "NUMERIC(38, 12)"
    assert {
        "ix_intelligence_executions_organization_id",
        "ix_intelligence_executions_dataset_id",
        "ix_intelligence_executions_trust_assessment_id",
        "ix_intelligence_executions_definition",
        "ix_intelligence_executions_status",
        "ix_intelligence_executions_created_at",
    } <= {index["name"] for index in inspector.get_indexes("intelligence_executions")}
    evidence_columns = {
        column["name"]: column
        for column in inspector.get_columns("intelligence_execution_evidence")
    }
    assert str(evidence_columns["aggregate_reference"]["type"]) == "JSONB"

    for table, json_columns in {
        "trust_rule_results": {"threshold_definition", "observed_value"},
        "trust_evidence": {"observed_value"},
        "analytical_readiness_decisions": {
            "blocking_rule_codes",
            "warning_rule_codes",
        },
    }.items():
        columns = {column["name"]: column for column in inspector.get_columns(table)}
        assert str(columns["id"]["type"]) == "UUID"
        assert str(columns["organization_id"]["type"]) == "UUID"
        assert all(str(columns[column]["type"]) == "JSONB" for column in json_columns)
    assert {
        "ix_trust_assessments_organization_id",
        "ix_trust_assessments_dataset_id",
        "ix_trust_assessments_status",
        "ix_trust_assessments_created_at",
    } <= {index["name"] for index in inspector.get_indexes("trust_assessments")}
    trust_columns = {
        column["name"]: column for column in inspector.get_columns("trust_assessments")
    }
    assert str(trust_columns["idempotency_key"]["type"]) == "VARCHAR(255)"
    assert str(trust_columns["request_fingerprint"]["type"]) == "VARCHAR(64)"
    assert {
        constraint["name"] for constraint in inspector.get_unique_constraints("trust_assessments")
    } >= {"uq_trust_assessments_organization_idempotency"}
    assert {
        foreign_key["referred_table"]
        for foreign_key in inspector.get_foreign_keys("trust_assessments")
    } == {"organizations", "datasets", "ingestion_batches"}

    expected_indexes = {
        "findings": {
            "ix_findings_domain",
            "ix_findings_organization_id",
            "ix_findings_rule_id",
            "ix_findings_organization_status",
            "ix_findings_organization_type",
            "ix_findings_organization_severity",
            "ix_findings_organization_detected",
            "ix_findings_organization_occurrence",
            "ix_findings_source_execution",
            "ix_findings_definition",
            "ix_findings_org_signature",
            "uq_findings_organization_deduplication",
        },
        "finding_evidence": {
            "ix_finding_evidence_finding_id",
            "ix_finding_evidence_organization_id",
        },
        "recovery_actions": {
            "ix_recovery_actions_finding_id",
            "ix_recovery_actions_organization_id",
        },
    }
    for table, names in expected_indexes.items():
        assert names <= {index["name"] for index in inspector.get_indexes(table)}

    expected_checks = {
        "organizations": {"ck_organizations_status"},
        "findings": {"ck_findings_severity", "ck_findings_status"},
        "recovery_actions": {"ck_recovery_actions_status"},
        "processing_runs": {"ck_processing_runs_data_anchor"},
        "trust_assessments": {"ck_trust_assessment_idempotency_pair"},
    }
    for table, names in expected_checks.items():
        assert names <= {
            constraint["name"] for constraint in inspector.get_check_constraints(table)
        }

    expected_foreign_keys = {
        "findings": {
            ("organization_id", "organizations", "id"),
            ("superseded_by_finding_id", "findings", "id"),
            ("source_execution_id", "intelligence_executions", "id"),
            ("source_result_id", "intelligence_executions", "id"),
            ("trust_assessment_id", "trust_assessments", "id"),
            (
                "analytical_readiness_id",
                "analytical_readiness_decisions",
                "id",
            ),
            ("dataset_id", "datasets", "id"),
            ("oikb_definition_id", "oikb_definitions", "id"),
            (
                "oikb_definition_version_id",
                "oikb_definition_versions",
                "id",
            ),
            (
                "signature_version_id",
                "operational_signature_versions",
                "id",
            ),
            (
                "signature_execution_id",
                "operational_signature_executions",
                "id",
            ),
        },
        "finding_evidence": {
            ("finding_id", "findings", "id"),
            ("organization_id", "organizations", "id"),
        },
        "recovery_actions": {
            ("finding_id", "findings", "id"),
            ("organization_id", "organizations", "id"),
        },
    }
    for table, expected in expected_foreign_keys.items():
        actual = {
            (
                foreign_key["constrained_columns"][0],
                foreign_key["referred_table"],
                foreign_key["referred_columns"][0],
            )
            for foreign_key in inspector.get_foreign_keys(table)
        }
        assert actual == expected

    finding_columns = {column["name"]: column for column in inspector.get_columns("findings")}
    assert str(finding_columns["measured_value"]["type"]) == "NUMERIC(38, 12)"
    assert str(finding_columns["exposure_value"]["type"]) == "NUMERIC(38, 12)"
    assert str(finding_columns["confidence_score"]["type"]) == "NUMERIC(6, 4)"
    assert str(finding_columns["severity_reason"]["type"]) == "JSONB"
    assert str(finding_columns["warnings"]["type"]) == "JSONB"
    assert str(finding_columns["limitations"]["type"]) == "JSONB"
    evidence_item_columns = {
        column["name"]: column for column in inspector.get_columns("finding_evidence_items")
    }
    assert str(evidence_item_columns["metadata_json"]["type"]) == "JSONB"
    assert str(evidence_item_columns["comparison_value"]["type"]) == "NUMERIC(38, 12)"

    orchestration_columns = {
        column["name"]: column
        for column in inspector.get_columns("intelligence_orchestration_requests")
    }
    assert str(orchestration_columns["id"]["type"]) == "UUID"
    assert str(orchestration_columns["organization_id"]["type"]) == "UUID"
    assert str(orchestration_columns["parameters_summary"]["type"]) == "JSONB"
    assert str(orchestration_columns["request_context"]["type"]) == "JSONB"
    assert {
        "ix_orchestration_requests_organization_status",
        "ix_orchestration_requests_organization_definition",
        "ix_orchestration_requests_organization_requested",
        "ix_orchestration_requests_dataset_id",
        "ix_orchestration_requests_trust_assessment_id",
        "ix_orchestration_requests_readiness_id",
    } <= {index["name"] for index in inspector.get_indexes("intelligence_orchestration_requests")}
    orchestration_uniques = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("intelligence_orchestration_requests")
    }
    assert {
        "uq_orchestration_requests_organization_idempotency",
        "uq_orchestration_requests_organization_correlation",
    } <= orchestration_uniques
    assert {
        foreign_key["referred_table"]
        for foreign_key in inspector.get_foreign_keys("intelligence_orchestration_requests")
    } == {
        "organizations",
        "datasets",
        "dataset_versions",
        "trust_assessments",
        "analytical_readiness_decisions",
    }
    step_columns = {
        column["name"]: column
        for column in inspector.get_columns("intelligence_orchestration_steps")
    }
    assert str(step_columns["input_reference_summary"]["type"]) == "JSONB"
    assert str(step_columns["source_execution_id"]["type"]) == "UUID"
    assert str(step_columns["source_result_id"]["type"]) == "UUID"
    assert str(step_columns["result_locator"]["type"]) == "VARCHAR(100)"
    assert str(step_columns["output_index"]["type"]) == "INTEGER"
    decision_columns = {
        column["name"]: column
        for column in inspector.get_columns("intelligence_orchestration_decisions")
    }
    assert str(decision_columns["warnings"]["type"]) == "JSONB"
    assert str(decision_columns["readiness_mapping_policy_code"]["type"]) == "VARCHAR(100)"
    assert {
        foreign_key["referred_table"]
        for foreign_key in inspector.get_foreign_keys("intelligence_orchestration_steps")
    } == {
        "organizations",
        "intelligence_orchestration_requests",
        "intelligence_executions",
        "findings",
    }
    definition_columns = {
        column["name"]: column for column in inspector.get_columns("oikb_definitions")
    }
    assert str(definition_columns["id"]["type"]) == "UUID"
    assert definition_columns["scope_key"]["nullable"] is False
    assert "uq_oikb_definition_scope" in {
        constraint["name"] for constraint in inspector.get_unique_constraints("oikb_definitions")
    }
    version_columns = {
        column["name"]: column for column in inspector.get_columns("oikb_definition_versions")
    }
    assert str(version_columns["expression_schema"]["type"]) == "JSONB"
    assert str(version_columns["fingerprint"]["type"]) == "VARCHAR(64)"
    assert {
        "uq_oikb_definition_semantic_version",
        "uq_oikb_definition_fingerprint",
    } <= {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("oikb_definition_versions")
    }
    finding_foreign_tables = {
        foreign_key["referred_table"] for foreign_key in inspector.get_foreign_keys("findings")
    }
    assert {"oikb_definitions", "oikb_definition_versions"} <= finding_foreign_tables
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT count(*) FROM oikb_definitions WHERE scope_key = 'shared_core'")
            )
            == 34
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM ("
                    "SELECT stable_code, count(*) "
                    "FROM oikb_definitions "
                    "WHERE scope_key = 'shared_core' "
                    "GROUP BY stable_code HAVING count(*) > 1"
                    ") duplicate_shared_core_codes"
                )
            )
            == 0
        )
        assert connection.scalar(text("SELECT count(*) FROM oikb_validation_cases")) == 320
        assert connection.scalar(text("SELECT count(*) FROM statistical_method_registry")) == 40
        assert connection.scalar(text("SELECT count(*) FROM forecast_method_registry")) == 19
    forecast_columns = {
        column["name"]: column for column in inspector.get_columns("forecast_executions")
    }
    assert str(forecast_columns["id"]["type"]) == "UUID"
    assert str(forecast_columns["readiness_snapshot"]["type"]) == "JSONB"
    assert {
        foreign_key["referred_table"]
        for foreign_key in inspector.get_foreign_keys("forecast_executions")
    } >= {
        "organizations",
        "oikb_definitions",
        "oikb_definition_versions",
        "trust_assessments",
        "analytical_readiness_decisions",
    }
    graph_node_columns = {
        column["name"]: column for column in inspector.get_columns("knowledge_graph_nodes")
    }
    graph_edge_columns = {
        column["name"]: column for column in inspector.get_columns("knowledge_graph_edges")
    }
    assert str(graph_node_columns["id"]["type"]) == "UUID"
    assert str(graph_node_columns["metadata_json"]["type"]) == "JSONB"
    assert str(graph_edge_columns["id"]["type"]) == "UUID"
    assert str(graph_edge_columns["properties_json"]["type"]) == "JSONB"
    assert "ck_kg_node_source_registry" in {
        item["name"] for item in inspector.get_check_constraints("knowledge_graph_nodes")
    }
    assert "ck_kg_edge_evidence_source_type" in {
        item["name"] for item in inspector.get_check_constraints("knowledge_graph_edge_evidence")
    }
    node_foreign_keys = {
        item["name"]: item for item in inspector.get_foreign_keys("knowledge_graph_nodes")
    }
    assert node_foreign_keys["fk_kg_node_org_graph_version"]["constrained_columns"] == [
        "organization_id",
        "graph_version_id",
    ]
    edge_foreign_keys = {
        item["name"]: item for item in inspector.get_foreign_keys("knowledge_graph_edges")
    }
    assert edge_foreign_keys["fk_kg_edge_from_node_tenant"]["constrained_columns"] == [
        "organization_id",
        "graph_version_id",
        "from_node_id",
    ]
    assert edge_foreign_keys["fk_kg_edge_to_node_tenant"]["constrained_columns"] == [
        "organization_id",
        "graph_version_id",
        "to_node_id",
    ]


@pytest.mark.postgres
def test_operating_site_count_database_constraint(postgres_engine: Engine) -> None:
    config = alembic_config(require_disposable_postgres_url())
    command.upgrade(config, "head")

    organization_table = cast(Table, Organization.__table__)
    valid_ids = [uuid4(), uuid4()]
    with postgres_engine.begin() as connection:
        for organization_id, site_count in zip(valid_ids, (0, 3), strict=True):
            connection.execute(
                insert(organization_table).values(
                    id=organization_id,
                    name=f"Site count {site_count}",
                    slug=f"site-count-{organization_id}",
                    country_code="US",
                    default_currency="USD",
                    timezone="UTC",
                    operating_site_count=site_count,
                )
            )

    with pytest.raises(IntegrityError):
        with postgres_engine.begin() as connection:
            invalid_id = uuid4()
            connection.execute(
                insert(organization_table).values(
                    id=invalid_id,
                    name="Invalid site count",
                    slug=f"site-count-{invalid_id}",
                    country_code="US",
                    default_currency="USD",
                    timezone="UTC",
                    operating_site_count=-1,
                )
            )

    with postgres_engine.begin() as connection:
        persisted_counts = connection.execute(
            select(Organization.operating_site_count).where(Organization.id.in_(valid_ids))
        ).scalars()
        assert set(persisted_counts) == {0, 3}
        connection.execute(organization_table.delete().where(Organization.id.in_(valid_ids)))


@pytest.mark.postgres
def test_migrations_on_disposable_postgres(postgres_engine: Engine) -> None:
    config = alembic_config(require_disposable_postgres_url())

    command.upgrade(config, "head")
    assert_schema_at_head(postgres_engine)

    memory_inspector = inspect(postgres_engine)
    assert P3_03DA_TABLES <= set(memory_inspector.get_table_names())
    assert {
        column["name"] for column in memory_inspector.get_columns("operational_memory_items")
    } == {
        "id",
        "organization_id",
        "category",
        "subject_kind",
        "normalized_subject",
        "source_system_family",
        "canonical_domain",
        "context_signature",
        "memory_fingerprint",
        "normalization_policy_code",
        "identity_policy_code",
        "current_version_number",
        "current_status",
        "support_count",
        "contradiction_count",
        "confirmation_count",
        "rejection_count",
        "is_stale",
        "stale_reason_code",
        "stale_detected_at",
        "last_confirmed_at",
        "last_validated_at",
        "valid_from",
        "valid_to",
        "security_classification",
        "retention_until",
        "created_at",
        "updated_at",
    }
    assert {
        name
        for table in P3_03DA_TABLES
        for name, column in {
            column["name"]: column for column in memory_inspector.get_columns(table)
        }.items()
        if str(column["type"]) == "JSONB"
    } == {"value_payload", "provenance_snapshot", "match_reasons"}
    assert {
        item["name"] for item in memory_inspector.get_unique_constraints("operational_memory_items")
    } == {
        "uq_operational_memory_items_org_id",
        "uq_operational_memory_items_org_fingerprint",
    }
    assert {
        item["name"] for item in memory_inspector.get_check_constraints("operational_memory_items")
    } == {
        "ck_operational_memory_items_category",
        "ck_operational_memory_items_subject_kind",
        "ck_operational_memory_items_category_subject",
        "ck_operational_memory_items_status",
        "ck_operational_memory_items_version",
        "ck_operational_memory_items_counts",
        "ck_operational_memory_items_validity",
        "ck_operational_memory_items_security",
        "ck_operational_memory_items_stale_projection",
        "ck_operational_memory_items_hashes",
    }
    assert {
        item["name"]
        for table in P3_03DA_TABLES
        for item in memory_inspector.get_indexes(table)
        if not item.get("duplicates_constraint")
    } >= {
        "ix_operational_memory_items_org_status_category",
        "ix_operational_memory_items_org_category_source_domain",
        "ix_operational_memory_items_org_category_subject",
        "ix_operational_memory_items_org_category_context",
        "ix_operational_memory_items_org_stale",
        "ix_operational_memory_items_org_retention",
        "ix_operational_memory_versions_org_source_schema",
        "ix_operational_memory_versions_org_mapping_result",
        "ix_operational_memory_versions_org_supersedes",
        "ix_operational_memory_reuse_org_consumer_time",
        "ix_operational_memory_reuse_org_memory_time",
    }
    assert {
        (
            item["name"],
            tuple(item["constrained_columns"]),
            item["referred_table"],
        )
        for table in P3_03DA_TABLES
        for item in memory_inspector.get_foreign_keys(table)
    } >= {
        (
            "fk_operational_memory_versions_org_memory",
            ("organization_id", "memory_id"),
            "operational_memory_items",
        ),
        (
            "fk_operational_memory_versions_org_supersedes",
            ("organization_id", "memory_id", "supersedes_version_id"),
            "operational_memory_versions",
        ),
        (
            "fk_operational_memory_reuse_org_version",
            ("organization_id", "memory_id", "memory_version_id"),
            "operational_memory_versions",
        ),
    }
    command.downgrade(config, "20260812_0038")
    assert not (P3_03DA_TABLES & set(inspect(postgres_engine).get_table_names()))
    assert P3_03C_TABLES <= set(inspect(postgres_engine).get_table_names())
    command.upgrade(config, "head")
    assert P3_03DA_TABLES <= set(inspect(postgres_engine).get_table_names())

    narrative_inspector = inspect(postgres_engine)
    assert P3_03C_TABLES <= set(narrative_inspector.get_table_names())
    narrative_columns = {
        column["name"]: column
        for column in narrative_inspector.get_columns("grounded_executive_narratives")
    }
    assert set(narrative_columns) == {
        "id",
        "organization_id",
        "scan_id",
        "profile_id",
        "requested_by_user_id",
        "idempotency_key",
        "audience",
        "status",
        "provider_code",
        "model_code",
        "model_version",
        "template_code",
        "template_version",
        "schema_version",
        "request_hash",
        "input_fingerprint",
        "execution_fingerprint",
        "source_scan_content_hash",
        "source_profile_fingerprint",
        "structured_source_snapshot",
        "structured_narrative_snapshot",
        "limitations",
        "observability_snapshot",
        "provider_failure_code",
        "content_hash",
        "generated_at",
        "created_at",
    }
    assert {
        name for name, column in narrative_columns.items() if str(column["type"]) == "JSONB"
    } == {
        "structured_source_snapshot",
        "structured_narrative_snapshot",
        "limitations",
        "observability_snapshot",
    }
    assert {
        item["name"]
        for item in narrative_inspector.get_unique_constraints("grounded_executive_narratives")
    } == {
        "uq_grounded_narratives_org_id",
        "uq_grounded_narratives_org_idempotency",
        "uq_grounded_narratives_org_execution_fingerprint",
    }
    assert {
        item["name"]
        for item in narrative_inspector.get_check_constraints("grounded_executive_narratives")
    } == {"ck_grounded_narratives_audience", "ck_grounded_narratives_status"}
    assert {
        (
            tuple(item["constrained_columns"]),
            item["referred_table"],
            item["options"].get("ondelete"),
        )
        for item in narrative_inspector.get_foreign_keys("grounded_executive_narratives")
    } == {
        (("organization_id",), "organizations", "RESTRICT"),
        (("organization_id", "scan_id"), "directional_value_scans", "RESTRICT"),
        (("organization_id", "profile_id"), "ai_operational_profiles", "RESTRICT"),
    }
    command.downgrade(config, "20260811_0037")
    assert not (P3_03C_TABLES & set(inspect(postgres_engine).get_table_names()))
    assert P3_03B_TABLES <= set(inspect(postgres_engine).get_table_names())
    command.upgrade(config, "head")
    assert P3_03C_TABLES <= set(inspect(postgres_engine).get_table_names())

    ai_inspector = inspect(postgres_engine)
    assert P3_03B_TABLES <= set(ai_inspector.get_table_names())
    profile_columns = {
        column["name"]: column for column in ai_inspector.get_columns("ai_operational_profiles")
    }
    inference_columns = {
        column["name"]: column for column in ai_inspector.get_columns("ai_profile_inferences")
    }
    assert {
        "profile_summary_snapshot",
        "input_provenance_snapshot",
        "observability_snapshot",
        "limitations",
    } <= {name for name, column in profile_columns.items() if str(column["type"]) == "JSONB"}
    assert {
        "evidence_references",
        "alternative_candidates",
        "provider_metadata",
    } <= {name for name, column in inference_columns.items() if str(column["type"]) == "JSONB"}
    assert {
        item["name"] for item in ai_inspector.get_unique_constraints("ai_operational_profiles")
    } == {
        "uq_ai_operational_profiles_org_id",
        "uq_ai_operational_profiles_org_idempotency",
        "uq_ai_operational_profiles_org_execution_fingerprint",
    }
    assert {
        item["name"] for item in ai_inspector.get_check_constraints("ai_profile_inferences")
    } == {
        "ck_ai_profile_inferences_confidence",
        "ck_ai_profile_inferences_status",
        "ck_ai_profile_inferences_sequence",
    }
    assert {
        (
            tuple(item["constrained_columns"]),
            item["referred_table"],
            item["options"].get("ondelete"),
        )
        for item in ai_inspector.get_foreign_keys("ai_profile_inferences")
    } == {
        (("organization_id",), "organizations", "RESTRICT"),
        (
            ("organization_id", "profile_id"),
            "ai_operational_profiles",
            "CASCADE",
        ),
    }
    command.downgrade(config, "20260810_0036")
    assert not (P3_03B_TABLES & set(inspect(postgres_engine).get_table_names()))
    assert P3_03A_TABLES <= set(inspect(postgres_engine).get_table_names())
    command.upgrade(config, "head")
    assert P3_03B_TABLES <= set(inspect(postgres_engine).get_table_names())

    value_scan_inspector = inspect(postgres_engine)
    assert P3_03A_TABLES <= set(value_scan_inspector.get_table_names())
    value_scan_columns = {
        column["name"]: column
        for column in value_scan_inspector.get_columns("directional_value_scans")
    }
    assert set(value_scan_columns) == {
        "id",
        "organization_id",
        "requested_by_user_id",
        "idempotency_key",
        "request_fingerprint",
        "input_fingerprint",
        "ranking_policy_code",
        "ranking_policy_version",
        "status",
        "generated_at",
        "candidate_finding_count",
        "opportunity_count",
        "data_gap_count",
        "data_coverage_snapshot",
        "trust_readiness_snapshot",
        "customer_context_snapshot",
        "opportunity_snapshot",
        "data_gap_snapshot",
        "next_investigation_snapshot",
        "provenance_snapshot",
        "limitations",
        "result_content_hash",
        "created_at",
    }
    assert str(value_scan_columns["id"]["type"]) == "UUID"
    for json_column in (
        "data_coverage_snapshot",
        "trust_readiness_snapshot",
        "customer_context_snapshot",
        "opportunity_snapshot",
        "data_gap_snapshot",
        "next_investigation_snapshot",
        "provenance_snapshot",
        "limitations",
    ):
        assert str(value_scan_columns[json_column]["type"]) == "JSONB"
    assert {
        item["name"]
        for item in value_scan_inspector.get_unique_constraints("directional_value_scans")
    } == {
        "uq_directional_value_scans_org_id",
        "uq_directional_value_scans_org_idempotency",
        "uq_directional_value_scans_org_input_fingerprint",
    }
    assert {
        item["name"]
        for item in value_scan_inspector.get_check_constraints("directional_value_scans")
    } == {
        "ck_directional_value_scans_status",
        "ck_directional_value_scans_candidate_count_non_negative",
        "ck_directional_value_scans_opportunity_count_non_negative",
        "ck_directional_value_scans_data_gap_count_non_negative",
        "ck_directional_value_scans_opportunity_within_candidates",
    }
    assert {
        item["name"]
        for item in value_scan_inspector.get_indexes("directional_value_scans")
        if item.get("duplicates_constraint") is None
    } == {
        "ix_directional_value_scans_org_generated_at",
        "ix_directional_value_scans_org_status",
    }
    value_scan_foreign_keys = value_scan_inspector.get_foreign_keys("directional_value_scans")
    assert len(value_scan_foreign_keys) == 1
    assert value_scan_foreign_keys[0]["referred_table"] == "organizations"
    assert value_scan_foreign_keys[0]["constrained_columns"] == ["organization_id"]
    command.downgrade(config, "20260809_0035")
    assert not (P3_03A_TABLES & set(inspect(postgres_engine).get_table_names()))
    command.upgrade(config, "head")
    assert P3_03A_TABLES <= set(inspect(postgres_engine).get_table_names())

    wp_214b_tables = WP_214B_DECISION_TABLES
    decision_inspector = inspect(postgres_engine)
    assert wp_214b_tables <= set(decision_inspector.get_table_names())
    assert {
        "fk_decision_recommendations_org_approval",
        "fk_decision_recommendations_org_action",
        "fk_decision_recommendations_org_alternative",
        "fk_decision_recommendations_org_solution",
    } <= {item["name"] for item in decision_inspector.get_foreign_keys("decision_recommendations")}
    command.downgrade(config, "20260806_0032")
    assert not (wp_214b_tables & set(inspect(postgres_engine).get_table_names()))
    command.upgrade(config, "head")
    assert_schema_at_head(postgres_engine)

    wp_217_tables = {
        "products",
        "product_versions",
        "features",
        "plans",
        "plan_versions",
        "plan_version_entitlements",
        "subscriptions",
        "contracts",
        "contract_overrides",
        "entitlements",
        "usage_meter_definitions",
        "usage_events",
        "usage_periods",
        "industry_pack_definitions",
        "industry_pack_assignments",
        "feature_flags",
        "limit_definitions",
        "limit_evaluations",
        "commercial_audit_events",
    }
    wp_218_tables = {
        "application_clients",
        "api_request_audit_events",
        "job_to_cash_runs",
        "job_to_cash_records",
    }
    wp_219_tables = {
        "industry_pack_versions",
        "industry_pack_assignment_states",
        "industry_pack_components",
        "industry_pack_validation_results",
        "industry_pack_executions",
        "industry_pack_governance_events",
    }
    wp_220_tables = {
        "validation_scenario_versions",
        "validation_oracle_versions",
        "validation_suites",
        "analytical_artifact_versions",
        "release_candidates",
        "validation_runs",
        "release_gate_definitions",
        "release_gate_results",
        "release_waivers",
        "release_certifications",
    }
    wp_221_tables = {
        "operational_feature_definitions",
        "operational_feature_versions",
        "operational_signature_definitions",
        "operational_signature_versions",
        "operational_signature_validations",
        "operational_signature_lifecycle_events",
        "operational_signature_deployments",
        "operational_signature_executions",
        "operational_signature_execution_evidence",
        "operational_signature_performance_history",
        "operational_signature_monitoring_results",
    }
    wp_301_tables = {
        "knowledge_graph_entity_types",
        "knowledge_graph_entity_type_versions",
        "knowledge_graph_relationship_types",
        "knowledge_graph_relationship_type_versions",
        "knowledge_graph_governance_events",
        "knowledge_graph_versions",
        "knowledge_graph_nodes",
        "knowledge_graph_edges",
        "knowledge_graph_edge_evidence",
        "knowledge_graph_changes",
        "knowledge_graph_query_runs",
        "knowledge_graph_query_steps",
        "knowledge_graph_projection_checkpoints",
    }
    mapping_inspector = inspect(postgres_engine)
    assert WP_301_MAPPING_TABLES <= set(mapping_inspector.get_table_names())
    assert "uq_raw_record_references_org_id" in {
        item["name"] for item in mapping_inspector.get_unique_constraints("raw_record_references")
    }
    assert {
        "fk_mapping_record_results_org_mapping_run",
        "fk_mapping_record_results_org_raw_record",
    } <= {item["name"] for item in mapping_inspector.get_foreign_keys("mapping_record_results")}
    assert "uq_value_crosswalk_entries_owner_id" in {
        item["name"] for item in mapping_inspector.get_unique_constraints("value_crosswalk_entries")
    }
    assert {
        "fk_value_crosswalk_entry_owner_crosswalk",
        "fk_value_crosswalk_entry_owner_supersedes",
    } <= {item["name"] for item in mapping_inspector.get_foreign_keys("value_crosswalk_entries")}
    assert (
        str(
            {
                column["name"]: column
                for column in mapping_inspector.get_columns("mapping_record_results")
            }["result_json"]["type"]
        )
        == "JSONB"
    )
    command.downgrade(config, "20260802_0030")
    mapping_inspector = inspect(postgres_engine)
    assert not (WP_301_MAPPING_TABLES & set(mapping_inspector.get_table_names()))
    assert "uq_raw_record_references_org_id" not in {
        item["name"] for item in mapping_inspector.get_unique_constraints("raw_record_references")
    }
    command.upgrade(config, "head")
    mapping_inspector = inspect(postgres_engine)
    assert WP_301_MAPPING_TABLES <= set(mapping_inspector.get_table_names())
    assert "uq_raw_record_references_org_id" in {
        item["name"] for item in mapping_inspector.get_unique_constraints("raw_record_references")
    }
    commercial_inspector = inspect(postgres_engine)
    usage_columns = {
        column["name"]: column for column in commercial_inspector.get_columns("usage_events")
    }
    assert str(usage_columns["id"]["type"]) == "UUID"
    assert str(usage_columns["quantity"]["type"]) == "NUMERIC(38, 12)"
    assert str(usage_columns["metadata_json"]["type"]) == "JSONB"
    assert {
        "organizations",
        "usage_meter_definitions",
    } <= {
        foreign_key["referred_table"]
        for foreign_key in commercial_inspector.get_foreign_keys("usage_events")
    }
    assert "uq_usage_event_key" in {
        item["name"] for item in commercial_inspector.get_unique_constraints("usage_events")
    }
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM products")) == 6
        assert connection.scalar(text("SELECT count(*) FROM plans")) == 5
        assert connection.scalar(text("SELECT count(*) FROM usage_meter_definitions")) == 22
        assert connection.scalar(text("SELECT count(*) FROM industry_pack_definitions")) == 7
        assert connection.scalar(text("SELECT count(*) FROM application_clients")) == 4
        assert connection.scalar(text("SELECT count(*) FROM industry_pack_versions")) == 4
        assert connection.scalar(text("SELECT count(*) FROM industry_pack_components")) == 76
        assert connection.scalar(text("SELECT count(*) FROM validation_scenario_versions")) == 36
        assert connection.scalar(text("SELECT count(*) FROM validation_oracle_versions")) == 36
        assert connection.scalar(text("SELECT count(*) FROM validation_suites")) == 14
        assert connection.scalar(text("SELECT count(*) FROM release_gate_definitions")) == 14
        assert connection.scalar(text("SELECT count(*) FROM operational_feature_definitions")) == 7
        assert (
            connection.scalar(text("SELECT count(*) FROM operational_signature_definitions")) == 2
        )
        assert (
            connection.scalar(text("SELECT count(*) FROM operational_signature_validations")) == 2
        )
        assert connection.scalar(text("SELECT count(*) FROM knowledge_graph_entity_types")) == 25
        assert (
            connection.scalar(text("SELECT count(*) FROM knowledge_graph_relationship_types")) == 26
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM knowledge_graph_relationship_types "
                    "WHERE code = 'caused_by'"
                )
            )
            == 0
        )
    provenance_columns = {
        "dataset_id",
        "dataset_version_id",
        "ingestion_batch_id",
        "source_system_id",
    }
    for table_name in (
        "reliability_executions",
        "statistical_executions",
        "forecast_executions",
        "forecast_actuals",
    ):
        assert provenance_columns <= {
            column["name"] for column in inspect(postgres_engine).get_columns(table_name)
        }
    command.downgrade(config, "20260728_0023")
    for table_name in (
        "reliability_executions",
        "statistical_executions",
        "forecast_executions",
        "forecast_actuals",
    ):
        assert provenance_columns.isdisjoint(
            {column["name"] for column in inspect(postgres_engine).get_columns(table_name)}
        )
    command.upgrade(config, "head")
    for table_name in (
        "reliability_executions",
        "statistical_executions",
        "forecast_executions",
        "forecast_actuals",
    ):
        assert provenance_columns <= {
            column["name"] for column in inspect(postgres_engine).get_columns(table_name)
        }
    command.downgrade(config, "20260728_0022")
    foundation_inspector = inspect(postgres_engine)
    assert {"idempotency_key", "request_fingerprint"}.isdisjoint(
        {column["name"] for column in foundation_inspector.get_columns("trust_assessments")}
    )
    assert "ck_organizations_status" not in {
        constraint["name"]
        for constraint in foundation_inspector.get_check_constraints("organizations")
    }
    command.upgrade(config, "head")
    foundation_inspector = inspect(postgres_engine)
    assert {"idempotency_key", "request_fingerprint"} <= {
        column["name"] for column in foundation_inspector.get_columns("trust_assessments")
    }
    assert "ck_organizations_status" in {
        constraint["name"]
        for constraint in foundation_inspector.get_check_constraints("organizations")
    }
    command.downgrade(config, "20260727_0021")
    assert not (wp_301_tables & set(inspect(postgres_engine).get_table_names()))
    assert wp_221_tables <= set(inspect(postgres_engine).get_table_names())
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM usage_meter_definitions")) == 19
        assert connection.scalar(text("SELECT count(*) FROM validation_suites")) == 13
        assert connection.scalar(text("SELECT count(*) FROM release_gate_definitions")) == 13
    command.upgrade(config, "head")
    assert wp_301_tables <= set(inspect(postgres_engine).get_table_names())
    command.downgrade(config, "20260727_0020")
    assert not (wp_221_tables & set(inspect(postgres_engine).get_table_names()))
    assert wp_220_tables <= set(inspect(postgres_engine).get_table_names())
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM usage_meter_definitions")) == 18
        assert connection.scalar(text("SELECT count(*) FROM validation_suites")) == 12
        assert connection.scalar(text("SELECT count(*) FROM release_gate_definitions")) == 12
    command.upgrade(config, "head")
    assert wp_221_tables <= set(inspect(postgres_engine).get_table_names())
    command.downgrade(config, "20260727_0019")
    assert not ((wp_220_tables | wp_221_tables) & set(inspect(postgres_engine).get_table_names()))
    assert wp_219_tables <= set(inspect(postgres_engine).get_table_names())
    command.upgrade(config, "head")
    assert wp_220_tables <= set(inspect(postgres_engine).get_table_names())
    command.downgrade(config, "20260726_0018")
    assert not ((wp_219_tables | wp_220_tables) & set(inspect(postgres_engine).get_table_names()))
    assert wp_218_tables <= set(inspect(postgres_engine).get_table_names())
    command.upgrade(config, "head")
    assert wp_219_tables <= set(inspect(postgres_engine).get_table_names())
    command.downgrade(config, "20260726_0017")
    assert not (wp_218_tables & set(inspect(postgres_engine).get_table_names()))
    assert wp_217_tables <= set(inspect(postgres_engine).get_table_names())
    command.upgrade(config, "head")
    assert wp_218_tables <= set(inspect(postgres_engine).get_table_names())
    command.downgrade(config, "20260726_0016")
    assert not (wp_217_tables & set(inspect(postgres_engine).get_table_names()))
    assert "verified_value_ledger_entries" in inspect(postgres_engine).get_table_names()
    command.upgrade(config, "head")
    assert wp_217_tables <= set(inspect(postgres_engine).get_table_names())

    wp_216_tables = {
        "recovery_cases",
        "recovery_executions",
        "recovery_value_measurements",
        "recovery_evidence_links",
        "recovery_finance_verifications",
        "verified_value_ledger_entries",
        "recovery_audit_events",
    }
    ledger_inspector = inspect(postgres_engine)
    ledger_columns = {
        column["name"]: column
        for column in ledger_inspector.get_columns("verified_value_ledger_entries")
    }
    measurement_columns = {
        column["name"]: column
        for column in ledger_inspector.get_columns("recovery_value_measurements")
    }
    assert str(ledger_columns["id"]["type"]) == "UUID"
    assert str(ledger_columns["amount"]["type"]) == "NUMERIC(38, 12)"
    assert str(measurement_columns["calculation_inputs"]["type"]) == "JSONB"
    assert {
        "recovery_cases",
        "recovery_value_measurements",
        "recovery_finance_verifications",
        "verified_value_ledger_entries",
    } <= {
        foreign_key["referred_table"]
        for foreign_key in ledger_inspector.get_foreign_keys("verified_value_ledger_entries")
    }
    assert "uq_verified_ledger_idempotency" in {
        item["name"]
        for item in ledger_inspector.get_unique_constraints("verified_value_ledger_entries")
    }
    command.downgrade(config, "20260726_0015")
    assert not (wp_216_tables & set(inspect(postgres_engine).get_table_names()))
    assert "economic_baseline_versions" in inspect(postgres_engine).get_table_names()
    command.upgrade(config, "head")
    assert wp_216_tables <= set(inspect(postgres_engine).get_table_names())

    wp_215_tables = {
        "recovery_opportunities",
        "opportunity_findings",
        "opportunity_actions",
        "economic_scenarios",
        "economic_assumptions",
        "economic_calculations",
        "prioritization_assessments",
        "opportunity_overlap_groups",
        "opportunity_overlap_members",
        "opportunity_decisions",
        "economic_audit_events",
        "economic_baseline_versions",
    }
    economics_inspector = inspect(postgres_engine)
    opportunity_columns = {
        column["name"]: column
        for column in economics_inspector.get_columns("recovery_opportunities")
    }
    calculation_columns = {
        column["name"]: column
        for column in economics_inspector.get_columns("economic_calculations")
    }
    assert str(opportunity_columns["id"]["type"]) == "UUID"
    assert str(opportunity_columns["organization_id"]["type"]) == "UUID"
    assert str(opportunity_columns["limitations"]["type"]) == "JSONB"
    assert str(calculation_columns["gross_exposure"]["type"]) == "NUMERIC(38, 12)"
    assert str(calculation_columns["expected_roi"]["type"]) == "NUMERIC(38, 12)"
    assert str(calculation_columns["input_snapshot"]["type"]) == "JSONB"
    assert {
        "uq_recovery_opportunity_idempotency",
        "uq_recovery_opportunity_source",
    } <= {
        item["name"]
        for item in economics_inspector.get_unique_constraints("recovery_opportunities")
    }
    assert "ck_scenario_rates" in {
        item["name"] for item in economics_inspector.get_check_constraints("economic_scenarios")
    }
    assert {
        "organizations",
        "findings",
        "recovery_opportunities",
    } <= {
        foreign_key["referred_table"]
        for table in ("recovery_opportunities", "opportunity_findings")
        for foreign_key in economics_inspector.get_foreign_keys(table)
    }
    command.downgrade(config, "20260725_0014")
    assert not (wp_215_tables & set(inspect(postgres_engine).get_table_names()))
    assert "operational_actions" in inspect(postgres_engine).get_table_names()
    command.upgrade(config, "head")
    assert_schema_at_head(postgres_engine)

    wp_214_tables = {
        "operational_actions",
        "action_plan_steps",
        "action_dependencies",
        "action_resource_requirements",
        "action_events",
        "action_evidence",
        "action_outcomes",
        "action_model_feedback",
    }
    action_columns = {
        column["name"]: column
        for column in inspect(postgres_engine).get_columns("operational_actions")
    }
    assert str(action_columns["id"]["type"]) == "UUID"
    assert str(action_columns["priority_components"]["type"]) == "JSONB"
    assert str(action_columns["expected_avoided_cost"]["type"]) == "NUMERIC(38, 12)"
    assert "uq_action_idempotency" in {
        item["name"]
        for item in inspect(postgres_engine).get_unique_constraints("operational_actions")
    }
    command.downgrade(config, "20260725_0013")
    assert not (wp_214_tables & set(inspect(postgres_engine).get_table_names()))
    assert "reliability_executions" in inspect(postgres_engine).get_table_names()
    command.upgrade(config, "head")
    assert_schema_at_head(postgres_engine)

    wp_213_tables = {
        "reliability_executions",
        "reliability_metrics",
        "reliability_model_results",
        "reliability_execution_steps",
        "reliability_method_registry",
        "reliability_review_feedback",
    }
    command.downgrade(config, "20260725_0012")
    tables_at_wp_212 = set(inspect(postgres_engine).get_table_names())
    assert not (wp_213_tables & tables_at_wp_212)
    assert {
        "forecast_executions",
        "forecast_method_registry",
        "forecast_execution_steps",
    } <= tables_at_wp_212
    command.upgrade(config, "head")
    assert_schema_at_head(postgres_engine)

    wp_212_tables = {
        "forecast_executions",
        "forecast_candidates",
        "forecast_backtests",
        "forecast_metrics",
        "forecast_points",
        "forecast_scenarios",
        "forecast_revisions",
        "forecast_actuals",
        "forecast_accuracy_results",
        "forecast_method_registry",
        "forecast_execution_steps",
    }
    command.downgrade(config, "20260725_0011")
    assert not (wp_212_tables & set(inspect(postgres_engine).get_table_names()))
    command.upgrade(config, "head")
    assert_schema_at_head(postgres_engine)

    wp_211_tables = {
        "statistical_executions",
        "statistical_baselines",
        "statistical_observations",
        "statistical_score_components",
        "statistical_execution_steps",
        "statistical_method_registry",
        "anomaly_suppression_records",
        "anomaly_review_feedback",
    }
    command.downgrade(config, "20260725_0010")
    assert not (wp_211_tables & set(inspect(postgres_engine).get_table_names()))
    command.upgrade(config, "head")
    assert_schema_at_head(postgres_engine)

    wp_210_tables = {
        "oikb_definitions",
        "oikb_definition_versions",
        "oikb_parameters",
        "oikb_input_requirements",
        "oikb_evidence_requirements",
        "oikb_sources",
        "oikb_definition_sources",
        "oikb_validation_cases",
        "oikb_validation_results",
        "oikb_approvals",
        "oikb_change_log",
        "oikb_relationships",
    }
    command.downgrade(config, "20260725_0009")
    assert not (wp_210_tables & set(inspect(postgres_engine).get_table_names()))
    assert "oikb_definition_id" not in {
        column["name"] for column in inspect(postgres_engine).get_columns("findings")
    }
    command.upgrade(config, "head")
    assert_schema_at_head(postgres_engine)

    wp_209_tables = {
        "intelligence_orchestration_requests",
        "intelligence_orchestration_decisions",
        "intelligence_orchestration_steps",
        "intelligence_engine_registrations",
        "intelligence_orchestration_status_history",
    }
    command.downgrade(config, "20260725_0008")
    assert not (wp_209_tables & set(inspect(postgres_engine).get_table_names()))
    command.upgrade(config, "head")
    assert_schema_at_head(postgres_engine)

    wp_208_tables = {
        "finding_evidence_bundles",
        "finding_evidence_items",
        "finding_calculation_traces",
        "finding_rule_traces",
        "finding_reviews",
        "finding_status_history",
    }
    command.downgrade(config, "20260724_0007")
    assert not (wp_208_tables & set(inspect(postgres_engine).get_table_names()))
    command.upgrade(config, "head")
    assert_schema_at_head(postgres_engine)

    wp_207_tables = {
        "intelligence_executions",
        "intelligence_execution_evidence",
    }
    command.downgrade(config, "20260724_0006")
    assert not (wp_207_tables & set(inspect(postgres_engine).get_table_names()))
    command.upgrade(config, "head")
    assert_schema_at_head(postgres_engine)

    wp_206_tables = {
        "trust_assessments",
        "trust_rule_results",
        "trust_evidence",
        "analytical_readiness_decisions",
    }
    command.downgrade(config, "20260724_0005")
    assert not (wp_206_tables & set(inspect(postgres_engine).get_table_names()))
    command.upgrade(config, "head")
    assert_schema_at_head(postgres_engine)

    command.downgrade(config, "20260724_0004")
    wp_205_tables = {
        "raw_storage_objects",
        "raw_record_references",
        "processing_runs",
        "lineage_nodes",
        "lineage_edges",
        "lineage_events",
    }
    assert not (wp_205_tables & set(inspect(postgres_engine).get_table_names()))
    command.upgrade(config, "head")
    assert_schema_at_head(postgres_engine)

    command.downgrade(config, "20260724_0003")
    wp_203_tables = set(inspect(postgres_engine).get_table_names())
    wp_204_tables = {"ingestion_batches", "datasets", "dataset_versions"}
    assert not (wp_204_tables & wp_203_tables)
    assert (
        MANAGED_TABLES
        - wp_204_tables
        - wp_205_tables
        - wp_206_tables
        - wp_207_tables
        - wp_208_tables
        - wp_209_tables
        - wp_210_tables
        - wp_211_tables
        - wp_212_tables
        - wp_213_tables
        - wp_214_tables
        - wp_215_tables
        - wp_216_tables
        - wp_217_tables
        - wp_218_tables
        - wp_219_tables
        - wp_220_tables
        - wp_221_tables
        - wp_301_tables
        - WP_301_MAPPING_TABLES
        - wp_214b_tables
        - P3_03A_TABLES
        - P3_03B_TABLES
        - P3_03C_TABLES
        - P3_03DA_TABLES
        - P3_05B_TABLES
        <= wp_203_tables
    )

    command.upgrade(config, "head")
    assert_schema_at_head(postgres_engine)

    command.downgrade(config, "base")
    assert not (MANAGED_TABLES & set(inspect(postgres_engine).get_table_names()))

    command.upgrade(config, "head")
    assert_schema_at_head(postgres_engine)


@pytest.mark.postgres
def test_directional_value_scan_constraints_and_concurrency_on_postgres(
    postgres_engine: Engine,
) -> None:
    config = alembic_config(require_disposable_postgres_url())
    command.upgrade(config, "head")

    def organization(session: Session, label: str) -> Organization:
        row = Organization(
            name=label,
            slug=f"{label}-{uuid4().hex[:8]}",
            country_code="US",
            default_currency="USD",
            timezone="UTC",
        )
        session.add(row)
        session.commit()
        return row

    def scan(
        organization_id: UUID,
        *,
        idempotency_key: str | None = None,
        input_fingerprint: str | None = None,
        candidate_count: int = 0,
        opportunity_count: int = 0,
        gap_count: int = 0,
    ) -> DirectionalValueScan:
        return DirectionalValueScan(
            organization_id=organization_id,
            requested_by_user_id=uuid4(),
            idempotency_key=idempotency_key or f"postgres:{uuid4()}",
            request_fingerprint=uuid4().hex + uuid4().hex,
            input_fingerprint=input_fingerprint or uuid4().hex + uuid4().hex,
            ranking_policy_code="P3.03A.DETERMINISTIC",
            ranking_policy_version="1.0",
            status="completed",
            candidate_finding_count=candidate_count,
            opportunity_count=opportunity_count,
            data_gap_count=gap_count,
            data_coverage_snapshot={},
            trust_readiness_snapshot={},
            customer_context_snapshot={},
            opportunity_snapshot=[],
            data_gap_snapshot=[],
            next_investigation_snapshot=None,
            provenance_snapshot={},
            limitations=[],
            result_content_hash=uuid4().hex + uuid4().hex,
        )

    with Session(postgres_engine) as session:
        org = organization(session, "p303a-constraint")
        for counts in ((-1, 0, 0), (0, -1, 0), (0, 0, -1), (1, 2, 0)):
            session.add(
                scan(
                    org.id,
                    candidate_count=counts[0],
                    opportunity_count=counts[1],
                    gap_count=counts[2],
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()

        stable_input = uuid4().hex + uuid4().hex
        session.add(
            scan(
                org.id,
                idempotency_key="postgres:unique",
                input_fingerprint=stable_input,
            )
        )
        session.commit()
        session.add(
            scan(
                org.id,
                idempotency_key="postgres:unique",
                input_fingerprint=uuid4().hex + uuid4().hex,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.add(
            scan(
                org.id,
                idempotency_key="postgres:different-key",
                input_fingerprint=stable_input,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    for repeat in range(5):
        with Session(postgres_engine) as session:
            org = organization(session, f"p303a-concurrency-{repeat}")
            organization_id = org.id
        actor_id = uuid4()
        key = f"postgres:concurrent:{repeat}"
        barrier = Barrier(2)

        def create_scan() -> UUID:
            with Session(postgres_engine) as worker_session:
                barrier.wait()
                row, _ = directional_value_scan_service.create(
                    worker_session,
                    organization_id,
                    actor_id,
                    key,
                )
                return row.id

        with ThreadPoolExecutor(max_workers=2) as executor:
            identifiers = list(executor.map(lambda _: create_scan(), range(2)))
        assert identifiers[0] == identifiers[1]
        with Session(postgres_engine) as session:
            assert (
                session.scalar(
                    select(func.count(DirectionalValueScan.id)).where(
                        DirectionalValueScan.organization_id == organization_id,
                        DirectionalValueScan.idempotency_key == key,
                    )
                )
                == 1
            )


@pytest.mark.postgres
def test_forecasting_downgrade_maps_readiness_to_supported_level(
    postgres_engine: Engine,
) -> None:
    config = alembic_config(require_disposable_postgres_url())
    command.upgrade(config, "head")
    with Session(postgres_engine) as session:
        organization_id, _, trust_id, _, _ = statistical_foundation(
            session, f"postgres-forecast-downgrade-{uuid4().hex[:8]}"
        )
        session.add(
            AnalyticalReadinessDecision(
                organization_id=organization_id,
                trust_assessment_id=trust_id,
                analytical_level="forecasting",
                readiness_status="ready",
                blocking_rule_codes=[],
                warning_rule_codes=[],
                explanation="Forecast-ready history.",
            )
        )
        session.commit()

    command.downgrade(config, "20260725_0011")
    with postgres_engine.connect() as connection:
        forecasting_count = connection.scalar(
            text(
                "SELECT count(*) FROM analytical_readiness_decisions "
                "WHERE analytical_level = 'forecasting'"
            )
        )
    assert forecasting_count == 0
    command.upgrade(config, "head")
    assert "forecast_executions" in inspect(postgres_engine).get_table_names()


@pytest.mark.postgres
def test_source_system_uuid_scope_and_constraints(postgres_engine: Engine) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    organization_service = OrganizationService()
    source_service = SourceSystemService()
    with Session(postgres_engine) as session:
        suffix = uuid4().hex[:10]
        first = organization_service.create(
            session,
            OrganizationCreate(
                name="PostgreSQL Source First",
                slug=f"postgres-source-first-{suffix}",
                country_code="US",
                default_currency="USD",
                timezone="UTC",
            ),
        )
        second = organization_service.create(
            session,
            OrganizationCreate(
                name="PostgreSQL Source Second",
                slug=f"postgres-source-second-{suffix}",
                country_code="US",
                default_currency="USD",
                timezone="UTC",
            ),
        )
        payload = SourceSystemCreate(
            name="PostgreSQL ERP",
            code="postgres-erp",
            system_type="erp",
            integration_method="database",
            configuration_metadata={"schema": "public"},
        )
        actor = uuid4()
        source = source_service.create(session, first.id, payload, actor)
        assert isinstance(source.id, UUID)
        assert source_service.list(session, first.id) == [source]
        assert source_service.list(session, second.id) == []
        with pytest.raises(DuplicateSourceSystemCodeError):
            source_service.create(session, first.id, payload, actor)
        source_service.create(session, second.id, payload, actor)


@pytest.mark.postgres
def test_ingestion_governance_on_postgres(postgres_engine: Engine) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    organization_service = OrganizationService()
    source_service = SourceSystemService()
    batch_service = IngestionBatchService()
    dataset_service = DatasetService()
    version_service = DatasetVersionService(dataset_service, batch_service)
    with Session(postgres_engine) as session:
        suffix = uuid4().hex[:10]
        organization = organization_service.create(
            session,
            OrganizationCreate(
                name="PostgreSQL Ingestion",
                slug=f"postgres-ingestion-{suffix}",
                country_code="US",
                default_currency="USD",
                timezone="UTC",
            ),
        )
        source = source_service.create(
            session,
            organization.id,
            SourceSystemCreate(
                name="PostgreSQL ERP",
                code="postgres-erp",
                system_type="erp",
                integration_method="api",
            ),
            uuid4(),
        )
        source.status = "active"
        session.commit()
        batch = batch_service.create(
            session,
            organization.id,
            IngestionBatchCreate(
                source_system_id=source.id,
                batch_number=f"postgres-batch-{suffix}",
                ingestion_method="database_extract",
                trigger_type="scheduled",
                idempotency_key=f"postgres-key-{suffix}",
                manifest_metadata={"schema": "public"},
            ),
            uuid4(),
        )
        dataset = dataset_service.create(
            session,
            organization.id,
            DatasetCreate(
                source_system_id=source.id,
                name="PostgreSQL Invoices",
                code=f"postgres-invoices-{suffix}",
                domain="invoices",
                dataset_type="transactional",
                metadata_json={"validated": True},
            ),
            uuid4(),
        )
        version = version_service.create(
            session,
            organization.id,
            dataset.id,
            DatasetVersionCreate(
                ingestion_batch_id=batch.id,
                source_file_name="invoices.csv",
                source_file_extension="csv",
            ),
        )
        version_service.update_counts(
            session,
            organization.id,
            dataset.id,
            version.id,
            DatasetVersionCountsUpdate(
                record_count=12,
                accepted_record_count=10,
                rejected_record_count=2,
            ),
        )
        reconciled = batch_service.get(session, organization.id, batch.id)
        assert isinstance(reconciled.id, UUID)
        assert (reconciled.actual_dataset_count, reconciled.actual_record_count) == (
            1,
            12,
        )


@pytest.mark.postgres
def test_raw_storage_uuid_scope_and_foreign_keys_on_postgres(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    organization_service = OrganizationService()
    source_service = SourceSystemService()
    batch_service = IngestionBatchService()
    dataset_service = DatasetService()
    version_service = DatasetVersionService(dataset_service, batch_service)
    raw_service = RawStorageObjectService()
    with Session(postgres_engine) as session:
        suffix = uuid4().hex[:10]
        organization = organization_service.create(
            session,
            OrganizationCreate(
                name="PostgreSQL Raw",
                slug=f"postgres-raw-{suffix}",
                country_code="US",
                default_currency="USD",
                timezone="UTC",
            ),
        )
        source = source_service.create(
            session,
            organization.id,
            SourceSystemCreate(
                name="Raw source",
                code="raw-source",
                system_type="erp",
                integration_method="file_upload",
            ),
            uuid4(),
        )
        source.status = "active"
        session.commit()
        batch = batch_service.create(
            session,
            organization.id,
            IngestionBatchCreate(
                source_system_id=source.id,
                batch_number=f"raw-batch-{suffix}",
                ingestion_method="file_upload",
                trigger_type="manual",
            ),
            uuid4(),
        )
        dataset = dataset_service.create(
            session,
            organization.id,
            DatasetCreate(
                source_system_id=source.id,
                name="Raw dataset",
                code=f"raw-dataset-{suffix}",
                domain="operations",
                dataset_type="transactional",
            ),
            uuid4(),
        )
        version = version_service.create(
            session,
            organization.id,
            dataset.id,
            DatasetVersionCreate(ingestion_batch_id=batch.id),
        )
        raw_object = raw_service.register(
            session,
            organization.id,
            RawStorageObjectCreate(
                source_system_id=source.id,
                ingestion_batch_id=batch.id,
                dataset_version_id=version.id,
                object_number=f"raw-object-{suffix}",
                object_type="file",
                storage_provider="local",
                storage_reference=f"opaque/raw-object-{suffix}",
                content_checksum_algorithm="sha256",
                content_checksum="a" * 64,
                size_bytes=42,
                received_at=datetime.now(UTC),
            ),
            uuid4(),
        )
        assert isinstance(raw_object.id, UUID)
        assert raw_service.list(session, organization.id) == [raw_object]
        trust_service = TrustAssessmentService()
        assessment = trust_service.create_and_execute(
            session,
            organization.id,
            dataset.id,
            TrustAssessmentCreate(
                ingestion_batch_id=batch.id,
                records=[{"id": "1", "amount": 42}],
                rule_configurations={
                    "required_field_completeness": {"required_fields": ["id", "amount"]},
                    "primary_identifier_uniqueness": {"identifier_field": "id"},
                },
            ),
        )
        assert isinstance(assessment.id, UUID)
        assert assessment.overall_score == 100
        assert len(trust_service.rule_results(session, organization.id, assessment.id)) == 2
        assert len(trust_service.readiness(session, organization.id, assessment.id)) == 7


@pytest.mark.postgres
def test_membership_constraints_and_organization_cascade(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    organization_service = OrganizationService()
    membership_service = OrganizationMembershipService()

    with Session(postgres_engine) as session:
        suffix = uuid4().hex[:10]
        organization = organization_service.create(
            session,
            OrganizationCreate(
                name="PostgreSQL Membership",
                slug=f"postgres-membership-{suffix}",
                country_code="US",
                default_currency="USD",
                timezone="UTC",
            ),
        )
        user_id = uuid4()
        payload = MembershipCreate(
            user_id=user_id,
            role=MembershipRole.ORGANIZATION_ADMIN,
            status=MembershipStatus.ACTIVE,
        )
        membership = membership_service.create(
            session,
            organization.id,
            payload,
            invited_by_user_id=uuid4(),
        )
        with pytest.raises(DuplicateMembershipError):
            membership_service.create(
                session,
                organization.id,
                payload,
                invited_by_user_id=uuid4(),
            )

        membership_id = membership.id
        session.delete(organization)
        session.commit()
        assert session.get(OrganizationMembership, membership_id) is None

        invalid_organization = organization_service.create(
            session,
            OrganizationCreate(
                name="PostgreSQL Invalid Membership",
                slug=f"postgres-invalid-membership-{suffix}",
                country_code="US",
                default_currency="USD",
                timezone="UTC",
            ),
        )
        session.add(
            OrganizationMembership(
                organization_id=invalid_organization.id,
                user_id=uuid4(),
                role="invalid_role",
                status=MembershipStatus.ACTIVE.value,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


@pytest.mark.postgres
def test_uuid_foreign_keys_and_finding_tenant_scope(postgres_engine: Engine) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    organization_service = OrganizationService()
    finding_service = FindingService()

    with Session(postgres_engine) as session:
        suffix = uuid4().hex[:10]
        first = organization_service.create(
            session,
            OrganizationCreate(
                name="PostgreSQL First",
                slug=f"postgres-first-{suffix}",
                country_code="US",
                default_currency="USD",
                timezone="UTC",
            ),
        )
        second = organization_service.create(
            session,
            OrganizationCreate(
                name="PostgreSQL Second",
                slug=f"postgres-second-{suffix}",
                country_code="US",
                default_currency="USD",
                timezone="UTC",
            ),
        )
        assert isinstance(first.id, UUID)
        assert isinstance(second.id, UUID)

        payload = FindingCreate(
            rule_id="POSTGRES-TEST",
            title="PostgreSQL tenant scope",
            summary="Verifies native UUID and organization filtering",
            domain="maintenance",
            exposure_low=1,
            exposure_high=2,
            confidence_score=0.9,
            evidence=[
                {
                    "source_system": "postgres_test",
                    "source_record_id": suffix,
                    "evidence_type": "validation",
                    "payload": {"validated": True},
                }
            ],
        )
        finding = finding_service.create(session, first.id, payload)
        assert isinstance(finding.id, UUID)
        assert [item.id for item in finding_service.list(session, first.id)] == [finding.id]
        assert finding_service.list(session, second.id) == []

        session.add(
            Finding(
                organization_id=uuid4(),
                governance_tier="LIGHTWEIGHT",
                rule_id="INVALID-FK",
                title="Invalid organization",
                summary="Must fail",
                domain="maintenance",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


@pytest.mark.postgres
def test_intelligence_decimal_and_tenant_scope_on_postgres(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    organization_service = OrganizationService()
    source_service = SourceSystemService()
    dataset_service = DatasetService()
    trust_service = TrustAssessmentService()
    intelligence_service = IntelligenceExecutionService()
    with Session(postgres_engine) as session:
        suffix = uuid4().hex[:10]
        actor = uuid4()
        organizations = [
            organization_service.create(
                session,
                OrganizationCreate(
                    name=f"Intelligence {name}",
                    slug=f"postgres-intelligence-{name}-{suffix}",
                    country_code="US",
                    default_currency="USD",
                    timezone="UTC",
                ),
            )
            for name in ("first", "second")
        ]
        source = source_service.create(
            session,
            organizations[0].id,
            SourceSystemCreate(
                name="Intelligence ERP",
                code="intelligence-erp",
                system_type="erp",
                integration_method="api",
            ),
            actor,
        )
        source.status = "active"
        session.commit()
        dataset = dataset_service.create(
            session,
            organizations[0].id,
            DatasetCreate(
                source_system_id=source.id,
                name="Canonical values",
                code=f"canonical-values-{suffix}",
                domain="finance",
                dataset_type="transactional",
                default_currency="USD",
            ),
            actor,
        )
        assessment = trust_service.create_and_execute(
            session,
            organizations[0].id,
            dataset.id,
            TrustAssessmentCreate(
                records=[{"id": "1", "amount": "0.10"}],
                rule_configurations={
                    "required_field_completeness": {"required_fields": ["id", "amount"]},
                    "numeric_range_validity": {"numeric_ranges": {"amount": {"minimum": 0}}},
                },
            ),
        )
        execution = intelligence_service.execute(
            session,
            organizations[0].id,
            IntelligenceExecutionCreate(
                dataset_id=dataset.id,
                trust_assessment_id=assessment.id,
                execution_type="calculation",
                definition_code="sum",
                records=[{"amount": "0.10"}, {"amount": "0.20"}],
                parameters={"field": "amount"},
                currency="USD",
            ),
            actor,
        )
        assert str(execution.result_value) == "0.300000000000"
        assert intelligence_service.list(session, organizations[0].id) == [execution]
        assert intelligence_service.list(session, organizations[1].id) == []
        finding = FindingPublicationService().publish_candidate_finding(
            session,
            organizations[0].id,
            CandidateFindingCreate(
                execution_id=execution.id,
                result_id=execution.id,
                finding_type="kpi",
                title="PostgreSQL exact arithmetic result",
                summary="Synthetic PostgreSQL finding publication.",
                domain_code="finance",
                measured_value=execution.result_value,
                measured_value_type="currency",
                measured_currency="USD",
                severity="info",
                severity_reason={"policy": "postgres-validation"},
                dataset_reference=f"{dataset.code}@postgres-validation",
                evidence_policy_code="WP208-POSTGRES",
                evidence_policy_version="1.0",
                calculation_traces=[
                    {
                        "operation_code": "sum",
                        "input_reference_summary": {"dataset_id": str(dataset.id)},
                        "parameter_summary": {"field": "amount"},
                    }
                ],
            ),
            actor,
        )
        assert str(finding.measured_value) == "0.300000000000"
        own, own_count = FindingQueryService().list(
            session,
            organizations[0].id,
            page=1,
            page_size=10,
        )
        other, other_count = FindingQueryService().list(
            session,
            organizations[1].id,
            page=1,
            page_size=10,
        )
        assert own == [finding]
        assert own_count == 1
        assert other == []
        assert other_count == 0


@pytest.mark.postgres
def test_orchestration_uuid_jsonb_idempotency_and_tenant_scope_on_postgres(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        suffix = uuid4().hex[:10]
        actor = uuid4()
        organizations = [
            OrganizationService().create(
                session,
                OrganizationCreate(
                    name=f"Orchestration {name}",
                    slug=f"postgres-orchestration-{name}-{suffix}",
                    country_code="US",
                    default_currency="USD",
                    timezone="UTC",
                ),
            )
            for name in ("first", "second")
        ]
        source = SourceSystemService().create(
            session,
            organizations[0].id,
            SourceSystemCreate(
                name="Orchestration ERP",
                code="orchestration-erp",
                system_type="erp",
                integration_method="api",
            ),
            actor,
        )
        source.status = "active"
        session.commit()
        dataset = DatasetService().create(
            session,
            organizations[0].id,
            DatasetCreate(
                source_system_id=source.id,
                name="Orchestration values",
                code=f"orchestration-values-{suffix}",
                domain="finance",
                dataset_type="transactional",
                default_currency="USD",
            ),
            actor,
        )
        from governed_provenance_helpers import add_eligible_dataset_version

        dataset_version = add_eligible_dataset_version(
            session, organizations[0].id, source.id, dataset.id, actor
        )
        assessment = TrustAssessmentService().create_and_execute(
            session,
            organizations[0].id,
            dataset.id,
            TrustAssessmentCreate(
                records=[{"id": "1", "amount": "0.10"}],
                rule_configurations={
                    "required_field_completeness": {"required_fields": ["id", "amount"]},
                    "numeric_range_validity": {"numeric_ranges": {"amount": {"minimum": 0}}},
                },
            ),
        )
        readiness = session.scalar(
            select(AnalyticalReadinessDecision).where(
                AnalyticalReadinessDecision.trust_assessment_id == assessment.id,
                AnalyticalReadinessDecision.analytical_level == "arithmetic",
            )
        )
        assert readiness is not None
        service = OrchestrationService()
        payload = OrchestrationCreate(
            definition_code="sum",
            definition_version="1.0",
            dataset_id=dataset.id,
            dataset_version_id=dataset_version.id,
            trust_assessment_id=assessment.id,
            analytical_readiness_id=readiness.id,
            execution_type="calculation",
            records=[{"amount": "0.10"}, {"amount": "0.20"}],
            parameters={"field": "amount"},
            currency="USD",
            request_context={"synthetic": True},
            correlation_id=f"postgres-correlation-{suffix}",
            idempotency_key=f"postgres-idempotency-{suffix}",
        )
        orchestration = service.orchestrate(session, organizations[0].id, payload, actor)
        duplicate = service.orchestrate(session, organizations[0].id, payload, actor)
        assert isinstance(orchestration.id, UUID)
        assert duplicate.id == orchestration.id
        assert orchestration.request_context == {"synthetic": True}
        own, own_count = service.list_requests(session, organizations[0].id, page=1, page_size=10)
        other, other_count = service.list_requests(
            session, organizations[1].id, page=1, page_size=10
        )
        assert own == [orchestration]
        assert own_count == 1
        assert other == []
        assert other_count == 0
        assert (
            session.scalar(
                select(IntelligenceOrchestrationRequest).where(
                    IntelligenceOrchestrationRequest.id == orchestration.id,
                    IntelligenceOrchestrationRequest.organization_id == organizations[1].id,
                )
            )
            is None
        )


@pytest.mark.postgres
def test_statistical_uuid_jsonb_tenancy_and_execution_on_postgres(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        organization_id, _, trust_id, readiness_id, actor = statistical_foundation(
            session, f"postgres-statistical-{uuid4().hex[:8]}"
        )
        execution = statistical_execution_service.execute(
            session,
            organization_id,
            execution_payload(
                trust_id,
                readiness_id,
                key=f"postgres-statistical-{uuid4().hex}",
            ),
            actor,
        )
        assert execution.status == "succeeded"
        observations = statistical_execution_service.observations_for(
            session, organization_id, execution.id
        )
        assert observations[0].is_anomaly
        metadata = observations[0].method_trace["metadata"]
        assert isinstance(metadata, dict)
        assert metadata["method_code"] == "MODIFIED_Z_SCORE"
        assert observations[0].evidence_references[0]["aggregate_only"] is True


@pytest.mark.postgres
def test_concurrent_admin_changes_cannot_remove_all_active_admins(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    service = OrganizationMembershipService()
    with Session(postgres_engine) as session:
        organization = OrganizationService().create(
            session,
            OrganizationCreate(
                name="Concurrent Admin Safety",
                slug=f"concurrent-admin-{uuid4().hex[:10]}",
                country_code="US",
                default_currency="USD",
                timezone="UTC",
            ),
        )
        admins = [
            service.create(
                session,
                organization.id,
                MembershipCreate(
                    user_id=uuid4(),
                    role=MembershipRole.ORGANIZATION_ADMIN,
                    status=MembershipStatus.ACTIVE,
                ),
                invited_by_user_id=uuid4(),
            )
            for _ in range(2)
        ]
        organization_id = organization.id
        admin_ids = [admin.id for admin in admins]

    barrier = Barrier(2)

    def demote(membership_id: UUID) -> str:
        with Session(postgres_engine) as session:
            barrier.wait()
            try:
                service.update_role(
                    session,
                    organization_id,
                    membership_id,
                    MembershipRole.ANALYST,
                )
            except LastActiveOrganizationAdminError:
                session.rollback()
                return "protected"
            return "changed"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(demote, admin_ids))
    assert sorted(outcomes) == ["changed", "protected"]
    with Session(postgres_engine) as session:
        active_admins = session.scalar(
            select(func.count())
            .select_from(OrganizationMembership)
            .where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.role == MembershipRole.ORGANIZATION_ADMIN.value,
                OrganizationMembership.status == MembershipStatus.ACTIVE.value,
            )
        )
        assert active_admins == 1


@pytest.mark.postgres
def test_concurrent_trust_idempotency_creates_one_assessment(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    actor = uuid4()
    with Session(postgres_engine) as session:
        organization = OrganizationService().create(
            session,
            OrganizationCreate(
                name="Concurrent Trust",
                slug=f"concurrent-trust-{uuid4().hex[:10]}",
                country_code="US",
                default_currency="USD",
                timezone="UTC",
            ),
        )
        source = SourceSystemService().create(
            session,
            organization.id,
            SourceSystemCreate(
                name="Concurrent Trust ERP",
                code="concurrent-trust-erp",
                system_type="erp",
                integration_method="api",
            ),
            actor,
        )
        source.status = "active"
        session.commit()
        dataset = DatasetService().create(
            session,
            organization.id,
            DatasetCreate(
                source_system_id=source.id,
                name="Concurrent Trust Records",
                code=f"concurrent-trust-{uuid4().hex[:8]}",
                domain="operations",
                dataset_type="transactional",
            ),
            actor,
        )
        organization_id = organization.id
        dataset_id = dataset.id

    payload = TrustAssessmentCreate(
        idempotency_key="concurrent-assessment",
        records=[{"id": "1"}],
        rule_configurations={"required_field_completeness": {"required_fields": ["id"]}},
    )
    barrier = Barrier(2)

    def execute() -> UUID:
        with Session(postgres_engine) as session:
            barrier.wait()
            return (
                TrustAssessmentService()
                .create_and_execute(
                    session,
                    organization_id,
                    dataset_id,
                    payload,
                )
                .id
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        assessment_ids = list(executor.map(lambda _: execute(), range(2)))
    assert assessment_ids[0] == assessment_ids[1]
    with Session(postgres_engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(TrustAssessment)
                .where(
                    TrustAssessment.organization_id == organization_id,
                    TrustAssessment.idempotency_key == "concurrent-assessment",
                )
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(TrustRuleResult)
                .where(TrustRuleResult.trust_assessment_id == assessment_ids[0])
            )
            == 1
        )


@pytest.mark.postgres
def test_reliability_behavior_on_disposable_postgres(postgres_engine: Engine) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        organization_id, trust_id, readiness_id, actor = reliability_foundation(
            session, f"pg-reliability-{uuid4().hex[:8]}"
        )
        basic = reliability_execution_service.execute(
            session,
            organization_id,
            reliability_payload(
                trust_id,
                readiness_id,
                dataset_fingerprint="7" * 64,
            ),
            actor,
        )
        assert basic.status == "succeeded"
        assert basic.explanation["human_review_required"] is True

        censored = reliability_payload(
            trust_id,
            readiness_id,
            method_code="WEIBULL_TWO_PARAMETER",
            dataset_fingerprint="8" * 64,
        )
        censored.observations[-1].event_observed = False
        censored.observations[-1].censoring_status = CensoringStatus.RIGHT_CENSORED
        with pytest.raises(ReliabilityServiceError, match="does not support censored"):
            reliability_execution_service.execute(session, organization_id, censored, actor)


@pytest.mark.postgres
def test_concurrent_reliability_definition_identity_idempotency(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        organization_id, trust_id, readiness_id, actor = reliability_foundation(
            session, f"pg-rel-concurrency-{uuid4().hex[:8]}"
        )
        second_definition, second_version = add_reliability_definition(
            session,
            organization_id,
            actor,
            stable_code="SHARED.RELIABILITY.CONCURRENT_ALTERNATE",
            fingerprint="r" * 64,
        )
        second_definition_id = second_definition.id
        second_definition_code = second_definition.stable_code
        second_version_id = second_version.id

    identical_payload = reliability_payload(
        trust_id,
        readiness_id,
        dataset_fingerprint="5" * 64,
    )
    identical_barrier = Barrier(2)

    def execute_identical() -> UUID:
        with Session(postgres_engine) as session:
            identical_barrier.wait()
            return (
                ReliabilityExecutionService()
                .execute(
                    session,
                    organization_id,
                    identical_payload,
                    actor,
                )
                .id
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        identical_ids = list(executor.map(lambda _: execute_identical(), range(2)))
    assert identical_ids[0] == identical_ids[1]

    class ForcedCollisionReliabilityService(ReliabilityExecutionService):
        def _reproducibility_fingerprint(self, *args: object, **kwargs: object) -> str:
            return "c" * 64

    first_payload = reliability_payload(
        trust_id,
        readiness_id,
        dataset_fingerprint="6" * 64,
    )
    second_payload = first_payload.model_copy(
        update={
            "definition_code": second_definition_code,
            "correlation_id": "rel-concurrent-conflict",
        }
    )
    collision_barrier = Barrier(2)

    def execute_collision(payload: ReliabilityExecutionCreate) -> tuple[str, UUID | str]:
        with Session(postgres_engine) as session:
            collision_barrier.wait()
            try:
                row = ForcedCollisionReliabilityService().execute(
                    session,
                    organization_id,
                    payload,
                    actor,
                )
                return "succeeded", row.id
            except ReliabilityServiceError as exc:
                return "conflict", exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        collision_results = list(executor.map(execute_collision, (first_payload, second_payload)))
    assert sorted(result[0] for result in collision_results) == ["conflict", "succeeded"]
    assert {result[1] for result in collision_results if result[0] == "conflict"} == {
        "IDEMPOTENCY_CONFLICT"
    }

    distinct_first = first_payload.model_copy(
        update={"dataset_fingerprint": "7" * 64, "correlation_id": "rel-distinct-first"}
    )
    distinct_second = second_payload.model_copy(
        update={"dataset_fingerprint": "7" * 64, "correlation_id": "rel-distinct-second"}
    )
    distinct_barrier = Barrier(2)

    def execute_distinct(payload: ReliabilityExecutionCreate) -> tuple[UUID, UUID, UUID]:
        with Session(postgres_engine) as session:
            distinct_barrier.wait()
            row = ReliabilityExecutionService().execute(
                session,
                organization_id,
                payload,
                actor,
            )
            return row.id, row.oikb_definition_id, row.oikb_definition_version_id

    with ThreadPoolExecutor(max_workers=2) as executor:
        distinct_results = list(executor.map(execute_distinct, (distinct_first, distinct_second)))
    assert distinct_results[0][0] != distinct_results[1][0]
    assert second_version_id in {result[2] for result in distinct_results}

    with Session(postgres_engine) as session:
        identical_rows = list(
            session.scalars(
                select(ReliabilityExecution).where(ReliabilityExecution.id.in_(identical_ids))
            )
        )
        assert len(identical_rows) == 1
        primary_definition_id = identical_rows[0].oikb_definition_id
        assert (
            session.scalar(
                select(func.count())
                .select_from(ReliabilityMetric)
                .where(ReliabilityMetric.reliability_execution_id == identical_rows[0].id)
            )
            or 0
        ) > 0
        assert (
            session.scalar(
                select(func.count())
                .select_from(ReliabilityModelResult)
                .where(ReliabilityModelResult.reliability_execution_id == identical_rows[0].id)
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(ReliabilityExecutionStep)
                .where(ReliabilityExecutionStep.reliability_execution_id == identical_rows[0].id)
            )
            == 1
        )
        assert {result[1] for result in distinct_results} == {
            primary_definition_id,
            second_definition_id,
        }
        collision_rows = list(
            session.scalars(
                select(ReliabilityExecution).where(
                    ReliabilityExecution.organization_id == organization_id,
                    ReliabilityExecution.reproducibility_fingerprint == "c" * 64,
                )
            )
        )
        assert len(collision_rows) == 1
        assert collision_rows[0].oikb_definition_id in {
            primary_definition_id,
            second_definition_id,
        }
        assert (
            session.scalar(
                select(func.count())
                .select_from(ReliabilityExecution)
                .where(
                    ReliabilityExecution.organization_id == organization_id,
                    ReliabilityExecution.id.in_([result[0] for result in distinct_results]),
                )
            )
            == 2
        )


@pytest.mark.postgres
def test_wp206a_legacy_provenance_backfill_is_deterministic(
    postgres_engine: Engine,
) -> None:
    config = alembic_config(require_disposable_postgres_url())
    command.upgrade(config, "head")
    execution_ids: dict[str, UUID] = {}

    with Session(postgres_engine) as session:
        for scenario in ("deterministic", "ambiguous", "fabricated", "cross-tenant"):
            organization_id, trust_id, readiness_id, actor = reliability_foundation(
                session, f"wp206a-{scenario}-{uuid4().hex[:8]}"
            )
            request = reliability_payload(trust_id, readiness_id)
            execution = reliability_execution_service.execute(
                session, organization_id, request, actor
            )
            execution_ids[scenario] = execution.id
            dataset = session.get(Dataset, request.dataset_id)
            assert dataset is not None
            if scenario == "ambiguous":
                add_eligible_dataset_version(
                    session,
                    organization_id,
                    dataset.source_system_id,
                    dataset.id,
                    actor,
                    checksum=execution.dataset_fingerprint,
                )
            elif scenario == "fabricated":
                execution.dataset_reference = "fabricated-dataset-reference"
                session.commit()
            elif scenario == "cross-tenant":
                original_code = dataset.code
                dataset.code = f"renamed-{uuid4().hex[:12]}"
                session.commit()
                other_organization_id, other_trust_id, _, _ = reliability_foundation(
                    session, f"wp206a-lookalike-{uuid4().hex[:8]}"
                )
                other_dataset = session.get(
                    Dataset,
                    reliability_payload(other_trust_id, uuid4()).dataset_id,
                )
                assert other_dataset is not None
                other_dataset.code = original_code
                session.commit()
                assert other_organization_id != organization_id

    command.downgrade(config, "20260728_0023")
    command.upgrade(config, "head")

    with Session(postgres_engine) as session:
        rows = {
            row.id: row
            for row in session.scalars(
                select(ReliabilityExecution).where(
                    ReliabilityExecution.id.in_(execution_ids.values())
                )
            )
        }
        assert len(rows) == 4
        assert rows[execution_ids["deterministic"]].dataset_id is not None
        assert rows[execution_ids["deterministic"]].dataset_version_id is not None
        for scenario in ("ambiguous", "fabricated", "cross-tenant"):
            assert rows[execution_ids[scenario]].dataset_id is None
            assert rows[execution_ids[scenario]].dataset_version_id is None
            assert rows[execution_ids[scenario]].ingestion_batch_id is None
            assert rows[execution_ids[scenario]].source_system_id is None


@pytest.mark.postgres
def test_wp206a_statistical_and_forecast_concurrency_and_governed_identity(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        stat_org, _, stat_trust, stat_readiness, stat_actor = statistical_foundation(
            session, f"wp206a-stat-{uuid4().hex[:8]}"
        )
        stat_request = execution_payload(
            stat_trust, stat_readiness, key=f"wp206a-stat-{uuid4().hex}"
        )
        forecast_org, forecast_trust, forecast_readiness, forecast_actor = forecasting_foundation(
            session, f"wp206a-forecast-{uuid4().hex[:8]}"
        )
        forecast_request = forecasting_payload(forecast_trust, forecast_readiness, "4" * 64)

    stat_barrier = Barrier(2)

    def execute_statistical() -> UUID:
        with Session(postgres_engine) as session:
            stat_barrier.wait()
            return (
                StatisticalExecutionService()
                .execute(session, stat_org, stat_request, stat_actor)
                .id
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        statistical_ids = list(executor.map(lambda _: execute_statistical(), range(2)))
    assert statistical_ids[0] == statistical_ids[1]

    forecast_barrier = Barrier(2)

    def execute_forecast() -> UUID:
        with Session(postgres_engine) as session:
            forecast_barrier.wait()
            return (
                ForecastExecutionService()
                .execute(session, forecast_org, forecast_request, forecast_actor)
                .id
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        forecast_ids = list(executor.map(lambda _: execute_forecast(), range(2)))
    assert forecast_ids[0] == forecast_ids[1]

    with Session(postgres_engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(StatisticalExecution)
                .where(StatisticalExecution.id.in_(statistical_ids))
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(ForecastExecution)
                .where(ForecastExecution.id.in_(forecast_ids))
            )
            == 1
        )


@pytest.mark.postgres
def test_wp206a_reliability_identity_collisions_never_cross_governed_boundaries(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        organization_id, trust_id, readiness_id, actor = reliability_foundation(
            session, f"wp206a-identity-{uuid4().hex[:8]}"
        )
        first_payload = reliability_payload(trust_id, readiness_id)
        dataset = session.get(Dataset, first_payload.dataset_id)
        assert dataset is not None
        second_version = add_eligible_dataset_version(
            session,
            organization_id,
            dataset.source_system_id,
            dataset.id,
            actor,
            checksum="a" * 64,
        )
        first_version = session.get(DatasetVersion, first_payload.dataset_version_id)
        assert first_version is not None
        first_batch = session.get(IngestionBatch, first_version.ingestion_batch_id)
        assert first_batch is not None
        first_batch.status = "processing"
        session.commit()
        with pytest.raises(ReliabilityServiceError) as batch_ineligible:
            reliability_execution_service.execute(session, organization_id, first_payload, actor)
        assert batch_ineligible.value.code == "INGESTION_BATCH_NOT_ELIGIBLE"
        first_batch.status = "completed"
        session.commit()

        mismatched_source = SourceSystemService().create(
            session,
            organization_id,
            SourceSystemCreate(
                name="WP-2.06A mismatched source",
                code=f"wp206a-mismatch-{uuid4().hex[:8]}",
                system_type="eam",
                integration_method="api",
            ),
            actor,
        )
        mismatched_source.status = "active"
        original_source_id = dataset.source_system_id
        dataset.source_system_id = mismatched_source.id
        session.commit()
        with pytest.raises(ReliabilityServiceError) as source_mismatch:
            reliability_execution_service.execute(session, organization_id, first_payload, actor)
        assert source_mismatch.value.code == "SOURCE_SYSTEM_MISMATCH"
        dataset.source_system_id = original_source_id
        session.commit()
        first = reliability_execution_service.execute(
            session, organization_id, first_payload, actor
        )
        second_payload = first_payload.model_copy(
            update={
                "dataset_version_id": second_version.id,
                "correlation_id": f"wp206a-second-version-{uuid4().hex}",
            }
        )
        second = reliability_execution_service.execute(
            session, organization_id, second_payload, actor
        )
        assert first.id != second.id

        other_dataset = DatasetService().create(
            session,
            organization_id,
            DatasetCreate(
                source_system_id=dataset.source_system_id,
                name="WP-2.06A collision dataset",
                code=f"wp206a-collision-{uuid4().hex[:8]}",
                domain="maintenance",
                dataset_type="time_series",
            ),
            actor,
        )
        other_version = add_eligible_dataset_version(
            session,
            organization_id,
            dataset.source_system_id,
            other_dataset.id,
            actor,
            checksum="a" * 64,
        )
        other_trust = TrustAssessment(
            organization_id=organization_id,
            dataset_id=other_dataset.id,
            status="completed",
            overall_score=95,
            assessed_row_count=10,
            passed_rule_count=3,
        )
        session.add(other_trust)
        session.flush()
        other_readiness = AnalyticalReadinessDecision(
            organization_id=organization_id,
            trust_assessment_id=other_trust.id,
            analytical_level="reliability",
            readiness_status="ready",
            blocking_rule_codes=[],
            warning_rule_codes=[],
            explanation="WP-2.06A governed collision test.",
        )
        session.add(other_readiness)
        session.commit()
        other_payload = first_payload.model_copy(
            update={
                "dataset_id": other_dataset.id,
                "dataset_version_id": other_version.id,
                "trust_assessment_id": other_trust.id,
                "readiness_assessment_id": other_readiness.id,
                "correlation_id": f"wp206a-other-dataset-{uuid4().hex}",
            }
        )
        other_execution = reliability_execution_service.execute(
            session, organization_id, other_payload, actor
        )
        assert other_execution.id not in {first.id, second.id}

        class ForcedGovernedCollisionService(ReliabilityExecutionService):
            def _reproducibility_fingerprint(self, *args: object, **kwargs: object) -> str:
                return "e" * 64

        collision_service = ForcedGovernedCollisionService()
        collision_first = collision_service.execute(
            session,
            organization_id,
            first_payload.model_copy(
                update={"correlation_id": f"wp206a-forced-first-{uuid4().hex}"}
            ),
            actor,
        )
        with pytest.raises(ReliabilityServiceError) as conflict:
            collision_service.execute(
                session,
                organization_id,
                second_payload.model_copy(
                    update={"correlation_id": f"wp206a-forced-second-{uuid4().hex}"}
                ),
                actor,
            )
        assert conflict.value.code == "IDEMPOTENCY_CONFLICT"
        assert (
            session.scalar(
                select(func.count())
                .select_from(ReliabilityExecution)
                .where(
                    ReliabilityExecution.organization_id == organization_id,
                    ReliabilityExecution.reproducibility_fingerprint == "e" * 64,
                )
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(ReliabilityMetric)
                .where(ReliabilityMetric.reliability_execution_id == collision_first.id)
            )
            or 0
        ) > 0

        other_organization_id, _, _, _ = reliability_foundation(
            session, f"wp206a-cross-tenant-{uuid4().hex[:8]}"
        )
        with pytest.raises(ReliabilityServiceError) as cross_tenant:
            reliability_execution_service.execute(
                session, other_organization_id, first_payload, actor
            )
        assert cross_tenant.value.code == "DATASET_NOT_FOUND"
        assert (
            session.scalar(
                select(func.count())
                .select_from(ReliabilityExecution)
                .where(ReliabilityExecution.organization_id == other_organization_id)
            )
            == 0
        )


@pytest.mark.postgres
def test_wp206a_forecast_replay_verifies_governed_identity(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    collision_fingerprint = "f" * 64

    def child_counts(session: Session, execution_id: UUID) -> tuple[int, ...]:
        return tuple(
            session.scalar(
                select(func.count())
                .select_from(model)
                .where(model.forecast_execution_id == execution_id)
            )
            or 0
            for model in (
                ForecastCandidate,
                ForecastBacktest,
                ForecastMetric,
                ForecastPoint,
                ForecastExecutionStep,
            )
        )

    with Session(postgres_engine) as session:
        organization_id, trust_id, readiness_id, actor = forecasting_foundation(
            session, f"wp206a-forecast-replay-{uuid4().hex[:8]}"
        )
        definition = session.scalar(
            select(OIKBDefinition).where(
                OIKBDefinition.owner_organization_id == organization_id,
                OIKBDefinition.analytical_level == "forecasting",
            )
        )
        assert definition is not None
        definition.stable_code = f"TEST.WP206A.FORECAST.{uuid4().hex.upper()}"
        session.commit()
        first_payload = forecasting_payload(trust_id, readiness_id, "5" * 64).model_copy(
            update={"definition_code": definition.stable_code}
        )
        dataset = session.get(Dataset, first_payload.dataset_id)
        assert dataset is not None
        second_version = add_eligible_dataset_version(
            session,
            organization_id,
            dataset.source_system_id,
            dataset.id,
            actor,
            checksum="5" * 64,
        )

        with patch("app.services.forecasting_service._hash", return_value=collision_fingerprint):
            first = ForecastExecutionService().execute(
                session, organization_id, first_payload, actor
            )
            baseline_counts = child_counts(session, first.id)
            replay = ForecastExecutionService().execute(
                session, organization_id, first_payload, actor
            )
            assert replay.id == first.id
            assert child_counts(session, first.id) == baseline_counts

            second_version_payload = first_payload.model_copy(
                update={"dataset_version_id": second_version.id}
            )
            with pytest.raises(ForecastingServiceError) as version_conflict:
                ForecastExecutionService().execute(
                    session, organization_id, second_version_payload, actor
                )
            assert version_conflict.value.code == "IDEMPOTENCY_CONFLICT"
            assert version_conflict.value.http_status == 409
            assert child_counts(session, first.id) == baseline_counts

            other_dataset = DatasetService().create(
                session,
                organization_id,
                DatasetCreate(
                    source_system_id=dataset.source_system_id,
                    name="WP-2.06A forecast collision dataset",
                    code=f"wp206a-forecast-collision-{uuid4().hex[:8]}",
                    domain="operations",
                    dataset_type="time_series",
                ),
                actor,
            )
            other_version = add_eligible_dataset_version(
                session,
                organization_id,
                dataset.source_system_id,
                other_dataset.id,
                actor,
                checksum="5" * 64,
            )
            other_trust = TrustAssessment(
                organization_id=organization_id,
                dataset_id=other_dataset.id,
                status="completed",
                overall_score=95,
                assessed_row_count=24,
                passed_rule_count=3,
            )
            session.add(other_trust)
            session.flush()
            other_readiness = AnalyticalReadinessDecision(
                organization_id=organization_id,
                trust_assessment_id=other_trust.id,
                analytical_level="forecasting",
                readiness_status="ready",
                blocking_rule_codes=[],
                warning_rule_codes=[],
                explanation="WP-2.06A replay collision test.",
            )
            session.add(other_readiness)
            session.commit()
            other_dataset_payload = first_payload.model_copy(
                update={
                    "dataset_id": other_dataset.id,
                    "dataset_version_id": other_version.id,
                    "trust_assessment_id": other_trust.id,
                    "readiness_assessment_id": other_readiness.id,
                }
            )
            with pytest.raises(ForecastingServiceError) as dataset_conflict:
                ForecastExecutionService().execute(
                    session, organization_id, other_dataset_payload, actor
                )
            assert dataset_conflict.value.code == "IDEMPOTENCY_CONFLICT"
            assert dataset_conflict.value.http_status == 409
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ForecastExecution)
                    .where(ForecastExecution.organization_id == organization_id)
                )
                == 1
            )
            assert child_counts(session, first.id) == baseline_counts

            other_organization_id, _, _, other_actor = forecasting_foundation(
                session, f"wp206a-forecast-tenant-{uuid4().hex[:8]}"
            )
            with pytest.raises(ForecastingServiceError) as cross_tenant:
                ForecastExecutionService().execute(
                    session, other_organization_id, first_payload, other_actor
                )
            assert cross_tenant.value.code == "DATASET_NOT_FOUND"
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ForecastExecution)
                    .where(ForecastExecution.organization_id == other_organization_id)
                )
                == 0
            )

    race_org = organization_id
    race_actor = actor
    race_payload = first_payload

    identical_barrier = Barrier(2)

    def execute_identical_forecast() -> tuple[str, UUID | str]:
        with Session(postgres_engine) as session:
            identical_barrier.wait()
            try:
                row = ForecastExecutionService().execute(
                    session, race_org, race_payload, race_actor
                )
                return "succeeded", row.id
            except ForecastingServiceError as exc:
                return "conflict", exc.code

    with patch("app.services.forecasting_service._hash", return_value="e" * 64):
        with ThreadPoolExecutor(max_workers=2) as executor:
            identical_results = list(executor.map(lambda _: execute_identical_forecast(), range(2)))
    assert {result[0] for result in identical_results} == {"succeeded"}
    assert len({result[1] for result in identical_results}) == 1

    mismatch_org = organization_id
    mismatch_actor = actor
    mismatch_first = first_payload
    mismatch_second = second_version_payload
    mismatch_barrier = Barrier(2)

    def execute_mismatched_forecast(
        payload: ForecastExecutionCreate,
    ) -> tuple[str, UUID | str]:
        with Session(postgres_engine) as session:
            mismatch_barrier.wait()
            try:
                row = ForecastExecutionService().execute(
                    session,
                    mismatch_org,
                    payload,
                    mismatch_actor,
                )
                return "succeeded", row.id
            except ForecastingServiceError as exc:
                return "conflict", exc.code

    with patch("app.services.forecasting_service._hash", return_value="d" * 64):
        with ThreadPoolExecutor(max_workers=2) as executor:
            mismatch_results = list(
                executor.map(
                    execute_mismatched_forecast,
                    (mismatch_first, mismatch_second),
                )
            )
    assert sorted(result[0] for result in mismatch_results) == [
        "conflict",
        "succeeded",
    ]
    assert {result[1] for result in mismatch_results if result[0] == "conflict"} == {
        "IDEMPOTENCY_CONFLICT"
    }


@pytest.mark.postgres
def test_ti_a_migration_round_trip_enforces_expected_schema(
    postgres_engine: Engine,
) -> None:
    config = alembic_config(require_disposable_postgres_url())
    command.upgrade(config, "head")

    def tenant_objects() -> tuple[set[str], set[str], set[str]]:
        inspector = inspect(postgres_engine)
        unique_names = {
            item["name"]
            for table_name in TI_A_PARENT_CONSTRAINTS
            for item in inspector.get_unique_constraints(table_name)
            if item["name"] is not None
        }
        foreign_key_names = {
            item["name"]
            for table_name in (
                "ingestion_batches",
                "datasets",
                "dataset_versions",
                "raw_storage_objects",
                "raw_record_references",
                "processing_runs",
                "lineage_edges",
                "lineage_events",
            )
            for item in inspector.get_foreign_keys(table_name)
            if item["name"] is not None
        }
        index_names = {
            item["name"]
            for table_name in (
                "ingestion_batches",
                "datasets",
                "dataset_versions",
                "raw_storage_objects",
                "raw_record_references",
                "processing_runs",
                "lineage_edges",
                "lineage_events",
            )
            for item in inspector.get_indexes(table_name)
            if item["name"] is not None
        }
        return unique_names, foreign_key_names, index_names

    unique_names, foreign_key_names, index_names = tenant_objects()
    assert set(TI_A_PARENT_CONSTRAINTS.values()) <= unique_names
    assert TI_A_FOREIGN_KEYS <= foreign_key_names
    assert TI_A_INDEXES <= index_names

    command.downgrade(config, "20260730_0024")
    unique_names, foreign_key_names, index_names = tenant_objects()
    assert set(TI_A_PARENT_CONSTRAINTS.values()).isdisjoint(unique_names)
    assert TI_A_FOREIGN_KEYS.isdisjoint(foreign_key_names)
    assert TI_A_INDEXES.isdisjoint(index_names)

    command.upgrade(config, "head")
    unique_names, foreign_key_names, index_names = tenant_objects()
    assert set(TI_A_PARENT_CONSTRAINTS.values()) <= unique_names
    assert TI_A_FOREIGN_KEYS <= foreign_key_names
    assert TI_A_INDEXES <= index_names


@pytest.mark.postgres
def test_ti_a_allows_bounded_concurrent_same_tenant_inserts(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        organization_id, source_id = ingestion_foundation(
            session, f"ti-a-concurrency-{uuid4().hex[:8]}"
        )
    barrier = Barrier(2)

    def create_batch(number: str) -> UUID:
        with Session(postgres_engine) as session:
            barrier.wait()
            return (
                IngestionBatchService()
                .create(
                    session,
                    organization_id,
                    ingestion_batch_payload(source_id, number),
                    uuid4(),
                )
                .id
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        batch_ids = list(executor.map(create_batch, ("batch-ti-a-1", "batch-ti-a-2")))
    assert len(set(batch_ids)) == 2


@pytest.mark.postgres
def test_ti_b1_migration_round_trip_enforces_expected_schema(
    postgres_engine: Engine,
) -> None:
    config = alembic_config(require_disposable_postgres_url())
    command.upgrade(config, "head")

    child_tables = (
        "trust_assessments",
        "trust_rule_results",
        "trust_evidence",
        "analytical_readiness_decisions",
    )

    def tenant_objects() -> tuple[
        dict[str, list[Any]],
        dict[str, list[Any]],
        dict[str, list[Any]],
    ]:
        inspector = inspect(postgres_engine)
        uniques = {
            table_name: inspector.get_unique_constraints(table_name)
            for table_name in TI_B1_PARENT_CONSTRAINTS
        }
        foreign_keys = {
            table_name: inspector.get_foreign_keys(table_name) for table_name in child_tables
        }
        indexes = {table_name: inspector.get_indexes(table_name) for table_name in child_tables}
        return uniques, foreign_keys, indexes

    def object_names() -> tuple[set[str], set[str], set[str]]:
        uniques, foreign_keys, indexes = tenant_objects()
        return (
            {
                str(item["name"])
                for values in uniques.values()
                for item in values
                if item["name"] is not None
            },
            {
                str(item["name"])
                for values in foreign_keys.values()
                for item in values
                if item["name"] is not None
            },
            {
                str(item["name"])
                for values in indexes.values()
                for item in values
                if item["name"] is not None
            },
        )

    unique_names, foreign_key_names, index_names = object_names()
    assert set(TI_B1_PARENT_CONSTRAINTS.values()) <= unique_names
    assert TI_B1_FOREIGN_KEYS <= foreign_key_names
    assert TI_B1_INDEXES <= index_names

    _, foreign_keys, _ = tenant_objects()
    new_foreign_keys = {
        str(item["name"]): item
        for values in foreign_keys.values()
        for item in values
        if item["name"] in TI_B1_FOREIGN_KEYS
    }
    assert set(new_foreign_keys) == TI_B1_FOREIGN_KEYS
    assert all(item["options"].get("ondelete") == "RESTRICT" for item in new_foreign_keys.values())
    assert all(
        item["constrained_columns"][0] == "organization_id"
        and item["referred_columns"] == ["organization_id", "id"]
        for item in new_foreign_keys.values()
    )

    existing_single_fk_targets: set[tuple[str, tuple[str, ...], str, tuple[str, ...]]] = {
        (
            table_name,
            tuple(item["constrained_columns"]),
            str(item["referred_table"]),
            tuple(item["referred_columns"]),
        )
        for table_name, values in foreign_keys.items()
        for item in values
        if len(item["constrained_columns"]) == 1
    }
    assert {
        ("trust_assessments", ("dataset_id",), "datasets", ("id",)),
        (
            "trust_assessments",
            ("ingestion_batch_id",),
            "ingestion_batches",
            ("id",),
        ),
        (
            "trust_rule_results",
            ("trust_assessment_id",),
            "trust_assessments",
            ("id",),
        ),
        (
            "trust_evidence",
            ("trust_rule_result_id",),
            "trust_rule_results",
            ("id",),
        ),
        ("trust_evidence", ("dataset_id",), "datasets", ("id",)),
        (
            "analytical_readiness_decisions",
            ("trust_assessment_id",),
            "trust_assessments",
            ("id",),
        ),
    } <= existing_single_fk_targets

    migration = import_module("migrations.versions.20260731_0026_ti_b1_trust_readiness_integrity")
    with (
        postgres_engine.connect() as connection,
        patch.object(migration.op, "get_bind", return_value=connection),
    ):
        migration._assert_clean_tenant_references()

    command.downgrade(config, "20260731_0025")
    unique_names, foreign_key_names, index_names = object_names()
    assert set(TI_B1_PARENT_CONSTRAINTS.values()).isdisjoint(unique_names)
    assert TI_B1_FOREIGN_KEYS.isdisjoint(foreign_key_names)
    assert TI_B1_INDEXES.isdisjoint(index_names)

    command.upgrade(config, "head")
    unique_names, foreign_key_names, index_names = object_names()
    assert set(TI_B1_PARENT_CONSTRAINTS.values()) <= unique_names
    assert TI_B1_FOREIGN_KEYS <= foreign_key_names
    assert TI_B1_INDEXES <= index_names


@pytest.mark.postgres
def test_ti_b1_allows_bounded_concurrent_same_tenant_inserts(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        organization_id, _, dataset_id = trust_foundation(
            session, f"ti-b1-concurrency-{uuid4().hex[:8]}"
        )
        assessment = TrustAssessment(
            organization_id=organization_id,
            dataset_id=dataset_id,
            status="pending",
        )
        session.add(assessment)
        session.commit()
        assessment_id = assessment.id

    barrier = Barrier(2)

    def create_result(suffix: str) -> UUID:
        with Session(postgres_engine) as session:
            barrier.wait()
            result = TrustRuleResult(
                organization_id=organization_id,
                trust_assessment_id=assessment_id,
                rule_code=f"ti-b1-concurrent-{suffix}",
                rule_version="1.0.0",
                rule_name="TI-B1 concurrent rule",
                dimension="validity",
                severity="warning",
                execution_status="completed",
                result_status="passed",
                message="TI-B1 concurrency",
            )
            session.add(result)
            session.commit()
            return result.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        result_ids = list(executor.map(create_result, ("one", "two")))
    assert len(set(result_ids)) == 2


@pytest.mark.postgres
def test_ti_b2_migration_round_trip_enforces_expected_schema(
    postgres_engine: Engine,
) -> None:
    config = alembic_config(require_disposable_postgres_url())
    command.upgrade(config, "head")
    child_tables = (
        "reliability_executions",
        "reliability_metrics",
        "reliability_model_results",
        "reliability_review_feedback",
        "statistical_executions",
        "statistical_baselines",
        "statistical_observations",
        "anomaly_review_feedback",
    )

    def tenant_objects() -> tuple[
        dict[str, list[Any]],
        dict[str, list[Any]],
        dict[str, list[Any]],
    ]:
        inspector = inspect(postgres_engine)
        return (
            {
                table_name: inspector.get_unique_constraints(table_name)
                for table_name in TI_B2_PARENT_CONSTRAINTS
            },
            {table_name: inspector.get_foreign_keys(table_name) for table_name in child_tables},
            {table_name: inspector.get_indexes(table_name) for table_name in child_tables},
        )

    def object_names() -> tuple[set[str], set[str], set[str]]:
        uniques, foreign_keys, indexes = tenant_objects()
        return (
            {
                str(item["name"])
                for values in uniques.values()
                for item in values
                if item["name"] is not None
            },
            {
                str(item["name"])
                for values in foreign_keys.values()
                for item in values
                if item["name"] is not None
            },
            {
                str(item["name"])
                for values in indexes.values()
                for item in values
                if item["name"] is not None
            },
        )

    unique_names, foreign_key_names, index_names = object_names()
    assert set(TI_B2_PARENT_CONSTRAINTS.values()) <= unique_names
    assert TI_B2_FOREIGN_KEYS <= foreign_key_names
    assert TI_B2_INDEXES <= index_names
    assert TI_B2_REUSED_INDEXES <= index_names

    _, foreign_keys, _ = tenant_objects()
    new_foreign_keys = {
        str(item["name"]): item
        for values in foreign_keys.values()
        for item in values
        if item["name"] in TI_B2_FOREIGN_KEYS
    }
    assert set(new_foreign_keys) == TI_B2_FOREIGN_KEYS
    assert all(
        item["options"].get("ondelete") in {"RESTRICT", "CASCADE"}
        for item in new_foreign_keys.values()
    )
    assert (
        sum(item["options"].get("ondelete") == "RESTRICT" for item in new_foreign_keys.values())
        == 12
    )
    assert (
        sum(item["options"].get("ondelete") == "CASCADE" for item in new_foreign_keys.values()) == 6
    )

    existing_single_foreign_keys = {
        (
            table_name,
            tuple(item["constrained_columns"]),
            str(item["referred_table"]),
            tuple(item["referred_columns"]),
        )
        for table_name, values in foreign_keys.items()
        for item in values
        if len(item["constrained_columns"]) == 1
    }
    for table_name, values in foreign_keys.items():
        for item in values:
            if item["name"] in TI_B2_FOREIGN_KEYS:
                parent_column = tuple(item["constrained_columns"])[1]
                assert any(
                    entry[0] == table_name
                    and entry[1] == (parent_column,)
                    and entry[2] == item["referred_table"]
                    and entry[3] == ("id",)
                    for entry in existing_single_foreign_keys
                )

    inspector = inspect(postgres_engine)
    for table_name in ("reliability_executions", "statistical_executions"):
        columns = {item["name"]: item for item in inspector.get_columns(table_name)}
        for column_name in (
            "dataset_id",
            "dataset_version_id",
            "ingestion_batch_id",
            "source_system_id",
        ):
            assert columns[column_name]["nullable"] is True

    migration = import_module(
        "migrations.versions.20260801_0027_ti_b2_reliability_statistical_integrity"
    )
    with (
        postgres_engine.connect() as connection,
        patch.object(migration.op, "get_bind", return_value=connection),
    ):
        migration._assert_clean_tenant_references()

    command.downgrade(config, "20260731_0026")
    unique_names, foreign_key_names, index_names = object_names()
    assert set(TI_B2_PARENT_CONSTRAINTS.values()).isdisjoint(unique_names)
    assert TI_B2_FOREIGN_KEYS.isdisjoint(foreign_key_names)
    assert TI_B2_INDEXES.isdisjoint(index_names)
    assert TI_B2_REUSED_INDEXES <= index_names

    command.upgrade(config, "head")
    unique_names, foreign_key_names, index_names = object_names()
    assert set(TI_B2_PARENT_CONSTRAINTS.values()) <= unique_names
    assert TI_B2_FOREIGN_KEYS <= foreign_key_names
    assert TI_B2_INDEXES <= index_names
    assert TI_B2_REUSED_INDEXES <= index_names


@pytest.mark.postgres
def test_ti_b2_allows_bounded_concurrent_same_tenant_inserts(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        reliability_org, reliability_trust, reliability_readiness, reliability_actor = (
            reliability_foundation(session, f"ti-b2-rel-concurrency-{uuid4().hex[:8]}")
        )
        reliability_execution = reliability_execution_service.execute(
            session,
            reliability_org,
            reliability_payload(reliability_trust, reliability_readiness),
            reliability_actor,
        )
        reliability_execution_id = reliability_execution.id

        statistical_org, _, statistical_trust, statistical_readiness, statistical_actor = (
            statistical_foundation(session, f"ti-b2-stat-concurrency-{uuid4().hex[:8]}")
        )
        statistical_execution = statistical_execution_service.execute(
            session,
            statistical_org,
            execution_payload(
                statistical_trust,
                statistical_readiness,
                key=f"ti-b2-concurrent-{uuid4().hex}",
            ),
            statistical_actor,
        )
        observation_id = session.scalar(
            select(StatisticalObservation.id).where(
                StatisticalObservation.statistical_execution_id == statistical_execution.id
            )
        )
        assert observation_id is not None

    reliability_barrier = Barrier(2)

    def create_reliability_review(suffix: str) -> UUID:
        with Session(postgres_engine) as session:
            reliability_barrier.wait()
            row = ReliabilityReviewFeedback(
                organization_id=reliability_org,
                reliability_execution_id=reliability_execution_id,
                assessment_type="human_review",
                assessment_reference=f"ti-b2:{suffix}",
                review_status="confirmed",
                reviewer_id=uuid4(),
                was_actionable=True,
                was_false_positive=False,
                notes="TI-B2 bounded concurrency",
            )
            session.add(row)
            session.commit()
            return row.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        reliability_ids = list(executor.map(create_reliability_review, ("one", "two")))
    assert len(set(reliability_ids)) == 2

    statistical_barrier = Barrier(2)

    def create_statistical_review(_: int) -> UUID:
        with Session(postgres_engine) as session:
            statistical_barrier.wait()
            row = AnomalyReviewFeedback(
                organization_id=statistical_org,
                statistical_observation_id=observation_id,
                review_status="confirmed",
                reviewer_id=uuid4(),
                classification="true_positive",
                was_actionable=True,
                was_false_positive=False,
                notes="TI-B2 bounded concurrency",
            )
            session.add(row)
            session.commit()
            return row.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        statistical_ids = list(executor.map(create_statistical_review, (1, 2)))
    assert len(set(statistical_ids)) == 2


@pytest.mark.postgres
def test_ti_b3_migration_round_trip_enforces_expected_schema(
    postgres_engine: Engine,
) -> None:
    config = alembic_config(require_disposable_postgres_url())
    command.upgrade(config, "head")
    child_tables = (
        "forecast_executions",
        "forecast_points",
        "forecast_scenarios",
        "forecast_revisions",
        "forecast_actuals",
        "forecast_accuracy_results",
    )

    def object_names() -> tuple[set[str], set[str], set[str]]:
        inspector = inspect(postgres_engine)
        return (
            {
                str(item["name"])
                for table_name in child_tables
                for item in inspector.get_unique_constraints(table_name)
                if item["name"] is not None
            },
            {
                str(item["name"])
                for table_name in child_tables
                for item in inspector.get_foreign_keys(table_name)
                if item["name"] is not None
            },
            {
                str(item["name"])
                for table_name in child_tables
                for item in inspector.get_indexes(table_name)
                if item["name"] is not None
            },
        )

    unique_names, foreign_key_names, index_names = object_names()
    assert set(TI_B3_PARENT_CONSTRAINTS.values()) <= unique_names
    assert TI_B3_FOREIGN_KEYS <= foreign_key_names
    assert TI_B3_INDEXES <= index_names
    assert TI_B3_REUSED_INDEXES <= unique_names | index_names

    inspector = inspect(postgres_engine)
    new_foreign_keys = {
        str(item["name"]): item
        for table_name in child_tables
        for item in inspector.get_foreign_keys(table_name)
        if item["name"] in TI_B3_FOREIGN_KEYS
    }
    assert set(new_foreign_keys) == TI_B3_FOREIGN_KEYS
    assert (
        sum(item["options"].get("ondelete") == "RESTRICT" for item in new_foreign_keys.values())
        == 13
    )
    assert (
        sum(item["options"].get("ondelete") == "CASCADE" for item in new_foreign_keys.values()) == 4
    )

    migration = import_module(
        "migrations.versions.20260801_0028_ti_b3_forecasting_actuals_integrity"
    )
    with (
        postgres_engine.connect() as connection,
        patch.object(migration.op, "get_bind", return_value=connection),
    ):
        migration._assert_clean_tenant_references()

    command.downgrade(config, "20260801_0027")
    unique_names, foreign_key_names, index_names = object_names()
    assert set(TI_B3_PARENT_CONSTRAINTS.values()).isdisjoint(unique_names)
    assert TI_B3_FOREIGN_KEYS.isdisjoint(foreign_key_names)
    assert TI_B3_INDEXES.isdisjoint(index_names)
    assert TI_B3_REUSED_INDEXES <= unique_names | index_names

    command.upgrade(config, "head")
    unique_names, foreign_key_names, index_names = object_names()
    assert set(TI_B3_PARENT_CONSTRAINTS.values()) <= unique_names
    assert TI_B3_FOREIGN_KEYS <= foreign_key_names
    assert TI_B3_INDEXES <= index_names
    assert TI_B3_REUSED_INDEXES <= unique_names | index_names


@pytest.mark.postgres
def test_ti_c1_migration_round_trip_enforces_expected_schema(
    postgres_engine: Engine,
) -> None:
    config = alembic_config(require_disposable_postgres_url())
    command.upgrade(config, "head")
    child_tables = (
        "intelligence_orchestration_requests",
        "intelligence_orchestration_decisions",
        "intelligence_orchestration_steps",
        "intelligence_orchestration_status_history",
        "reliability_executions",
        "statistical_executions",
        "forecast_executions",
    )

    def object_names() -> tuple[set[str], set[str], set[str]]:
        inspector = inspect(postgres_engine)
        return (
            {
                str(item["name"])
                for table_name in child_tables
                for item in inspector.get_unique_constraints(table_name)
                if item["name"] is not None
            },
            {
                str(item["name"])
                for table_name in child_tables
                for item in inspector.get_foreign_keys(table_name)
                if item["name"] is not None
            },
            {
                str(item["name"])
                for table_name in child_tables
                for item in inspector.get_indexes(table_name)
                if item["name"] is not None
            },
        )

    def execution_orchestration_foreign_keys() -> dict[str, list[ReflectedForeignKeyConstraint]]:
        inspector = inspect(postgres_engine)
        return {
            table_name: [
                item
                for item in inspector.get_foreign_keys(table_name)
                if "orchestration_request_id" in item["constrained_columns"]
            ]
            for table_name in (
                "reliability_executions",
                "statistical_executions",
                "forecast_executions",
            )
        }

    unique_names, foreign_key_names, index_names = object_names()
    assert set(TI_C1_PARENT_CONSTRAINTS.values()) <= unique_names
    assert TI_C1_FOREIGN_KEYS <= foreign_key_names
    assert TI_C1_INDEXES <= index_names
    assert TI_C1_REUSED_INDEXES <= index_names

    inspector = inspect(postgres_engine)
    new_foreign_keys = {
        str(item["name"]): item
        for table_name in child_tables
        for item in inspector.get_foreign_keys(table_name)
        if item["name"] in TI_C1_FOREIGN_KEYS
    }
    assert set(new_foreign_keys) == TI_C1_FOREIGN_KEYS
    assert (
        sum(item["options"].get("ondelete") == "CASCADE" for item in new_foreign_keys.values()) == 3
    )
    assert (
        sum(item["options"].get("ondelete") == "RESTRICT" for item in new_foreign_keys.values())
        == 7
    )

    for table_name in (
        "reliability_executions",
        "statistical_executions",
        "forecast_executions",
    ):
        orchestration_foreign_keys = [
            item
            for item in inspector.get_foreign_keys(table_name)
            if "orchestration_request_id" in item["constrained_columns"]
        ]
        assert len(orchestration_foreign_keys) == 1
        assert orchestration_foreign_keys[0]["constrained_columns"] == [
            "organization_id",
            "orchestration_request_id",
        ]
        assert orchestration_foreign_keys[0]["options"].get("ondelete") == "RESTRICT"

    migration = import_module("migrations.versions.20260801_0029_ti_c1_orchestration_integrity")
    with (
        postgres_engine.connect() as connection,
        patch.object(migration.op, "get_bind", return_value=connection),
    ):
        migration._assert_clean_tenant_references()

    command.downgrade(config, "20260801_0028")
    unique_names, foreign_key_names, index_names = object_names()
    assert set(TI_C1_PARENT_CONSTRAINTS.values()).isdisjoint(unique_names)
    assert TI_C1_FOREIGN_KEYS.isdisjoint(foreign_key_names)
    assert TI_C1_INDEXES.isdisjoint(index_names)
    assert TI_C1_REUSED_INDEXES <= index_names
    for values in execution_orchestration_foreign_keys().values():
        assert len(values) == 1
        assert values[0]["constrained_columns"] == ["orchestration_request_id"]
        assert values[0]["options"].get("ondelete") == "SET NULL"

    command.upgrade(config, "head")
    unique_names, foreign_key_names, index_names = object_names()
    assert set(TI_C1_PARENT_CONSTRAINTS.values()) <= unique_names
    assert TI_C1_FOREIGN_KEYS <= foreign_key_names
    assert TI_C1_INDEXES <= index_names
    assert TI_C1_REUSED_INDEXES <= index_names
    for values in execution_orchestration_foreign_keys().values():
        assert len(values) == 1
        assert values[0]["constrained_columns"] == [
            "organization_id",
            "orchestration_request_id",
        ]
        assert values[0]["options"].get("ondelete") == "RESTRICT"


@pytest.mark.postgres
def test_ti_c2_migration_round_trip_enforces_expected_schema(
    postgres_engine: Engine,
) -> None:
    config = alembic_config(require_disposable_postgres_url())
    command.upgrade(config, "head")
    child_tables = (
        "operational_actions",
        "action_plan_steps",
        "action_dependencies",
        "action_resource_requirements",
        "action_events",
        "action_evidence",
        "action_outcomes",
        "action_model_feedback",
    )

    def object_names() -> tuple[set[str], set[str], set[str]]:
        inspector = inspect(postgres_engine)
        return (
            {
                str(item["name"])
                for table_name in child_tables
                for item in inspector.get_unique_constraints(table_name)
                if item["name"] is not None
            },
            {
                str(item["name"])
                for table_name in child_tables
                for item in inspector.get_foreign_keys(table_name)
                if item["name"] is not None
            },
            {
                str(item["name"])
                for table_name in child_tables
                for item in inspector.get_indexes(table_name)
                if item["name"] is not None
            },
        )

    unique_names, foreign_key_names, index_names = object_names()
    assert set(TI_C2_PARENT_CONSTRAINTS.values()) <= unique_names
    assert TI_C2_FOREIGN_KEYS <= foreign_key_names
    assert TI_C2_INDEXES <= index_names
    assert TI_C2_REUSED_INDEXES <= index_names

    new_foreign_keys = {
        str(item["name"]): item
        for table_name in child_tables
        for item in inspect(postgres_engine).get_foreign_keys(table_name)
        if item["name"] in TI_C2_FOREIGN_KEYS
    }
    assert set(new_foreign_keys) == TI_C2_FOREIGN_KEYS
    assert (
        sum(item["options"].get("ondelete") == "CASCADE" for item in new_foreign_keys.values()) == 7
    )
    assert (
        sum(item["options"].get("ondelete") == "RESTRICT" for item in new_foreign_keys.values())
        == 5
    )

    for child, name, parent, parent_column, ondelete in TI_C2_RELATIONSHIPS:
        reflected = new_foreign_keys[name]
        assert reflected["constrained_columns"] == ["organization_id", parent_column]
        assert reflected["referred_table"] == parent
        assert reflected["referred_columns"] == ["organization_id", "id"]
        assert reflected["options"].get("ondelete") == ondelete

    migration = import_module("migrations.versions.20260802_0030_ti_c2_action_workflow_integrity")
    with (
        postgres_engine.connect() as connection,
        patch.object(migration.op, "get_bind", return_value=connection),
    ):
        migration._assert_clean_tenant_references()

    command.downgrade(config, "20260801_0029")
    unique_names, foreign_key_names, index_names = object_names()
    assert set(TI_C2_PARENT_CONSTRAINTS.values()).isdisjoint(unique_names)
    assert TI_C2_FOREIGN_KEYS.isdisjoint(foreign_key_names)
    assert TI_C2_INDEXES.isdisjoint(index_names)
    assert TI_C2_REUSED_INDEXES <= index_names

    command.upgrade(config, "head")
    unique_names, foreign_key_names, index_names = object_names()
    assert set(TI_C2_PARENT_CONSTRAINTS.values()) <= unique_names
    assert TI_C2_FOREIGN_KEYS <= foreign_key_names
    assert TI_C2_INDEXES <= index_names
    assert TI_C2_REUSED_INDEXES <= index_names


@pytest.mark.postgres
def test_ti_c2_postgres_enforces_tenant_boundary_and_concurrent_same_tenant_writes(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        first_org = ti_c2_organization(f"ti-c2-pg-first-{uuid4().hex[:8]}")
        second_org = ti_c2_organization(f"ti-c2-pg-second-{uuid4().hex[:8]}")
        session.add_all([first_org, second_org])
        session.flush()
        action = ti_c2_action(first_org.id, "pg-first")
        session.add(action)
        session.commit()
        organization_id = first_org.id
        action_id = action.id

        invalid = ActionPlanStep(
            organization_id=second_org.id,
            action_id=action_id,
            sequence_number=1,
            title="Invalid",
            description="Cross-tenant plan step.",
        )
        session.add(invalid)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        assert session.get(ActionPlanStep, invalid.id) is None

    barrier = Barrier(2)

    def create_step(sequence: int) -> UUID:
        with Session(postgres_engine) as session:
            row = ActionPlanStep(
                organization_id=organization_id,
                action_id=action_id,
                sequence_number=sequence,
                title=f"Concurrent {sequence}",
                description="Same-tenant concurrent insert.",
            )
            session.add(row)
            barrier.wait()
            session.commit()
            return row.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        step_ids = list(executor.map(create_step, (101, 102)))
    assert len(set(step_ids)) == 2


def _ti_c1_postgres_execution_lineages(
    session: Session,
) -> tuple[tuple[type[Any], UUID, IntelligenceOrchestrationRequest], ...]:
    reliability_org, reliability_trust, reliability_readiness, reliability_actor = (
        reliability_foundation(session, f"ti-c1r-pg-rel-{uuid4().hex[:8]}")
    )
    reliability = reliability_execution_service.execute(
        session,
        reliability_org,
        reliability_payload(reliability_trust, reliability_readiness),
        reliability_actor,
    )
    reliability_request = ti_c1_lineage_request(
        session,
        reliability_org,
        cast(UUID, reliability.dataset_id),
        reliability_trust,
        reliability_readiness,
    )
    reliability.orchestration_request_id = reliability_request.id
    session.commit()

    statistics_org, _, statistics_trust, statistics_readiness, statistics_actor = (
        statistical_foundation(session, f"ti-c1r-pg-stat-{uuid4().hex[:8]}")
    )
    statistics = statistical_execution_service.execute(
        session,
        statistics_org,
        execution_payload(
            statistics_trust,
            statistics_readiness,
            key=f"ti-c1r-pg-{uuid4().hex}",
        ),
        statistics_actor,
    )
    statistics_request = ti_c1_lineage_request(
        session,
        statistics_org,
        cast(UUID, statistics.dataset_id),
        statistics_trust,
        statistics_readiness,
    )
    statistics.orchestration_request_id = statistics_request.id
    session.commit()

    forecast_org, forecast_trust, forecast_readiness, forecast_actor = forecasting_foundation(
        session, f"ti-c1r-pg-forecast-{uuid4().hex[:8]}"
    )
    stable_code = f"ORG.FORECASTING.TI_C1R_{uuid4().hex.upper()}"
    definition = OIKBDefinition(
        stable_code=stable_code,
        name="TI-C1R tenant forecast",
        description="Tenant-owned forecasting fixture for delete-semantics certification.",
        knowledge_class="forecasting_method",
        analytical_level="forecasting",
        domain="forecasting",
        subdomain="tenant_integrity",
        owner_organization_id=forecast_org,
        scope_type="organization",
        scope_key=f"organization:{forecast_org}",
        is_system_definition=False,
        created_by=forecast_actor,
    )
    session.add(definition)
    session.flush()
    version = OIKBDefinitionVersion(
        definition_id=definition.id,
        semantic_version="1.0.0",
        lifecycle_status="active",
        quality_level="provisional",
        effective_from=datetime.now(UTC),
        expression_schema={"operation": "forecast", "candidate_methods": ["NAIVE"]},
        output_type="forecast_series",
        output_unit="count",
        rounding_policy={"decimal_places": 4},
        null_policy="structured_null",
        zero_denominator_policy="structured_null",
        trust_requirement={"minimum_status": "completed"},
        readiness_requirement={"analytical_level": "forecasting"},
        fingerprint=uuid4().hex * 2,
        validation_satisfied=True,
        created_by=forecast_actor,
        activated_by=forecast_actor,
        activated_at=datetime.now(UTC),
    )
    session.add(version)
    session.commit()
    assert definition.owner_organization_id == forecast_org
    assert definition.scope_key == f"organization:{forecast_org}"

    forecast = ForecastExecutionService().execute(
        session,
        forecast_org,
        forecasting_payload(
            forecast_trust,
            forecast_readiness,
            fingerprint=uuid4().hex * 2,
        ).model_copy(update={"definition_code": stable_code}),
        forecast_actor,
    )
    forecast_request = ti_c1_lineage_request(
        session,
        forecast_org,
        cast(UUID, forecast.dataset_id),
        forecast_trust,
        forecast_readiness,
    )
    forecast.orchestration_request_id = forecast_request.id
    session.commit()

    return (
        (ReliabilityExecution, reliability.id, reliability_request),
        (StatisticalExecution, statistics.id, statistics_request),
        (ForecastExecution, forecast.id, forecast_request),
    )


@pytest.mark.postgres
def test_ti_c1_execution_lineage_restricts_request_delete_on_postgres(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        for model, execution_id, request in _ti_c1_postgres_execution_lineages(session):
            with pytest.raises(IntegrityError):
                session.delete(request)
                session.commit()
            session.rollback()
            execution = session.get(model, execution_id)
            assert execution is not None
            assert execution.orchestration_request_id == request.id

        unreferenced, _ = ti_c1_orchestration_graph(
            session, f"ti-c1r-pg-unreferenced-{uuid4().hex[:8]}"
        )
        request_id = unreferenced.id
        session.delete(unreferenced)
        session.commit()
        assert session.get(IntelligenceOrchestrationRequest, request_id) is None


@pytest.mark.postgres
def test_ti_c1_allows_bounded_concurrent_same_tenant_child_inserts(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        organization_id, dataset_id, trust_id, readiness_id = orchestration_foundation(
            session, f"ti-c1-concurrency-{uuid4().hex[:8]}"
        )
        request_row = OrchestrationService().orchestrate(
            session,
            organization_id,
            orchestration_payload(
                dataset_id,
                trust_id,
                readiness_id,
                key=f"ti-c1-concurrency-{uuid4().hex}",
            ),
            uuid4(),
        )
        decision = session.scalar(
            select(IntelligenceOrchestrationDecision).where(
                IntelligenceOrchestrationDecision.orchestration_request_id == request_row.id
            )
        )
        step = session.scalar(
            select(IntelligenceOrchestrationStep).where(
                IntelligenceOrchestrationStep.orchestration_request_id == request_row.id
            )
        )
        assert decision is not None
        assert step is not None
        decision_values = dict(
            session.execute(
                select(IntelligenceOrchestrationDecision.__table__).where(
                    IntelligenceOrchestrationDecision.id == decision.id
                )
            )
            .mappings()
            .one()
        )
        step_values = dict(
            session.execute(
                select(IntelligenceOrchestrationStep.__table__).where(
                    IntelligenceOrchestrationStep.id == step.id
                )
            )
            .mappings()
            .one()
        )

    decision_barrier = Barrier(2)

    def create_decision(sequence: int) -> UUID:
        with Session(postgres_engine) as session:
            values = dict(decision_values)
            values["id"] = uuid4()
            values["decision_sequence"] = sequence
            values["content_hash"] = uuid4().hex * 2
            decision_barrier.wait()
            session.execute(
                insert(cast(Table, IntelligenceOrchestrationDecision.__table__)).values(**values)
            )
            session.commit()
            return cast(UUID, values["id"])

    with ThreadPoolExecutor(max_workers=2) as executor:
        decision_ids = list(executor.map(create_decision, (101, 102)))
    assert len(set(decision_ids)) == 2

    step_barrier = Barrier(2)

    def create_step(sequence: int) -> UUID:
        with Session(postgres_engine) as session:
            values = dict(step_values)
            values["id"] = uuid4()
            values["step_sequence"] = sequence
            values["content_hash"] = uuid4().hex * 2
            step_barrier.wait()
            session.execute(
                insert(cast(Table, IntelligenceOrchestrationStep.__table__)).values(**values)
            )
            session.commit()
            return cast(UUID, values["id"])

    with ThreadPoolExecutor(max_workers=2) as executor:
        step_ids = list(executor.map(create_step, (101, 102)))
    assert len(set(step_ids)) == 2


CAUSAL_INTELLIGENCE_TABLES = (
    "causal_method_definitions",
    "causal_nodes",
    "causal_hypotheses",
    "causal_evidence_links",
    "causal_reviews",
    "causal_edges",
    "causal_chains",
    "causal_chain_versions",
    "causal_interventions",
    "causal_outcome_assessments",
    "causal_audit_events",
)


@pytest.mark.postgres
def test_causal_intelligence_migration_round_trip_enforces_expected_schema(
    postgres_engine: Engine,
) -> None:
    config = alembic_config(require_disposable_postgres_url())
    command.upgrade(config, "head")

    inspector = inspect(postgres_engine)
    table_names = set(inspector.get_table_names())
    assert set(CAUSAL_INTELLIGENCE_TABLES) <= table_names

    action_outcome_uniques = {
        item["name"] for item in inspector.get_unique_constraints("action_outcomes")
    }
    assert "uq_action_outcomes_org_id" in action_outcome_uniques

    hypothesis_checks = {
        item["name"] for item in inspector.get_check_constraints("causal_hypotheses")
    }
    assert "ck_causal_hypothesis_association_not_confirmed" in hypothesis_checks

    intervention_checks = {
        item["name"] for item in inspector.get_check_constraints("causal_interventions")
    }
    assert "ck_causal_intervention_target_xor" in intervention_checks

    command.downgrade(config, "20260804_0031")
    table_names = set(inspect(postgres_engine).get_table_names())
    assert set(CAUSAL_INTELLIGENCE_TABLES).isdisjoint(table_names)
    action_outcome_uniques = {
        item["name"] for item in inspect(postgres_engine).get_unique_constraints("action_outcomes")
    }
    assert "uq_action_outcomes_org_id" not in action_outcome_uniques

    command.upgrade(config, "head")
    table_names = set(inspect(postgres_engine).get_table_names())
    assert set(CAUSAL_INTELLIGENCE_TABLES) <= table_names
    action_outcome_uniques = {
        item["name"] for item in inspect(postgres_engine).get_unique_constraints("action_outcomes")
    }
    assert "uq_action_outcomes_org_id" in action_outcome_uniques


@pytest.mark.postgres
def test_causal_intelligence_direct_sql_rejects_cross_tenant_hypothesis(
    postgres_engine: Engine,
) -> None:
    config = alembic_config(require_disposable_postgres_url())
    command.upgrade(config, "head")

    with Session(postgres_engine) as session:
        org_a = uuid4()
        org_b = uuid4()
        for org_id, slug in ((org_a, "causal-pg-tenant-a"), (org_b, "causal-pg-tenant-b")):
            session.execute(
                text(
                    "INSERT INTO organizations "
                    "(id, name, slug, country_code, default_currency, timezone, status, "
                    "is_demo, created_at, updated_at) "
                    "VALUES (:id, :slug, :slug, 'US', 'USD', 'UTC', 'active', false, now(), now())"
                ),
                {"id": org_id, "slug": slug},
            )
        method_id = uuid4()
        session.execute(
            text(
                "INSERT INTO causal_method_definitions "
                "(id, method_code, method_name, method_class, method_version, "
                "default_confidence_weight, parameters_schema, status, content_hash, "
                "scope_type, scope_key, created_at, updated_at) "
                "VALUES (:id, 'pg_direct_sql_method', 'PG Direct', 'sequence_pattern', '1.0.0', "
                "0.5, '{}', 'active', 'pg-direct-hash', 'shared_core', "
                "'shared_core:pg_direct_sql_method', now(), now())"
            ),
            {"id": method_id},
        )
        node_a = uuid4()
        node_b = uuid4()
        session.execute(
            text(
                "INSERT INTO causal_nodes "
                "(id, organization_id, node_type, content_fingerprint, created_at, updated_at) "
                "VALUES (:id, :org_id, 'external_factor', :fp, now(), now())"
            ),
            {"id": node_a, "org_id": org_a, "fp": "fp-pg-a"},
        )
        session.execute(
            text(
                "INSERT INTO causal_nodes "
                "(id, organization_id, node_type, content_fingerprint, created_at, updated_at) "
                "VALUES (:id, :org_id, 'external_factor', :fp, now(), now())"
            ),
            {"id": node_b, "org_id": org_a, "fp": "fp-pg-b"},
        )
        session.commit()

        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO causal_hypotheses "
                    "(id, organization_id, source_node_id, target_node_id, proposed_edge_type, "
                    "method_id, lifecycle_status, hard_gate_failure_reasons, content_hash, "
                    "evidence_count, contradiction_count, created_by_user_id, created_at, "
                    "updated_at) "
                    "VALUES (:id, :org_b, :node_a, :node_b, 'causes', :method_id, 'draft', "
                    "'[]', 'pg-cross-tenant-hash', 0, 0, :actor, now(), now())"
                ),
                {
                    "id": uuid4(),
                    "org_b": org_b,
                    "node_a": node_a,
                    "node_b": node_b,
                    "method_id": method_id,
                    "actor": uuid4(),
                },
            )
        session.rollback()


@pytest.mark.postgres
def test_causal_evidence_mutation_and_confirmation_are_serialized(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        organization_id, actor = make_causal_org(session, f"causal-concurrency-{uuid4().hex[:10]}")
        hypothesis, _node_a, _node_b, _method = confirm_causal_hypothesis(
            session, organization_id, actor
        )
        evidence_id = session.scalar(
            select(CausalEvidenceLink.id).where(CausalEvidenceLink.hypothesis_id == hypothesis.id),
        )
        assert evidence_id is not None
        hypothesis_id = hypothesis.id

    barrier = Barrier(2)

    def mutate_evidence() -> str:
        with Session(postgres_engine) as session:
            evidence = session.get(CausalEvidenceLink, evidence_id)
            assert evidence is not None
            barrier.wait()
            evidence.notes = "concurrent evidence change"
            try:
                session.commit()
            except ValueError:
                session.rollback()
                return "immutable"
            return "mutated"

    def confirm_hypothesis() -> str:
        with Session(postgres_engine) as session:
            barrier.wait()
            try:
                causal_review_service.review(
                    session,
                    organization_id,
                    hypothesis_id,
                    CausalReviewCreate(decision="confirm"),
                    actor,
                )
            except CausalIntelligenceServiceError as exc:
                session.rollback()
                return exc.code
            return "confirmed"

    with ThreadPoolExecutor(max_workers=2) as executor:
        mutation_future = executor.submit(mutate_evidence)
        review_future = executor.submit(confirm_hypothesis)
        mutation_result = mutation_future.result()
        review_result = review_future.result()

    with Session(postgres_engine) as session:
        final_hypothesis = session.get(CausalHypothesis, hypothesis_id)
        final_evidence = session.get(CausalEvidenceLink, evidence_id)
        assert final_hypothesis is not None
        assert final_evidence is not None
        if final_hypothesis.lifecycle_status == "confirmed":
            assert review_result == "confirmed"
            assert mutation_result == "immutable"
            assert final_evidence.notes is None
        else:
            assert final_hypothesis.lifecycle_status == "evidence_pending"
            assert mutation_result == "mutated"
            assert review_result in {
                "hypothesis_not_evaluated",
                "hypothesis_evaluation_stale",
            }
            assert final_evidence.notes == "concurrent evidence change"


@pytest.mark.postgres
def test_decision_reject_and_convert_race_cannot_produce_action_from_rejected_recommendation(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        organization_id, actor = make_decision_org(
            session, f"decision-race-reject-{uuid4().hex[:10]}"
        )
        recommendation, _alternative = add_decision_graph(session, organization_id, actor)
        recommendation_id = recommendation.id
        decision_approval_service.decide(
            session,
            organization_id,
            recommendation_id,
            DecisionApprovalCreate(
                decision="approve", rationale="Approved", idempotency_key="race-approve-1"
            ),
            actor,
            "organization_admin",
        )

    barrier = Barrier(2)

    def reject() -> str:
        with Session(postgres_engine) as session:
            barrier.wait()
            try:
                decision_approval_service.decide(
                    session,
                    organization_id,
                    recommendation_id,
                    DecisionApprovalCreate(
                        decision="reject",
                        rationale="Concurrent rejection",
                        idempotency_key="race-reject-1",
                    ),
                    actor,
                    "organization_admin",
                )
            except DecisionIntelligenceServiceError as exc:
                session.rollback()
                return exc.code
            return "rejected"

    def convert() -> str:
        with Session(postgres_engine) as session:
            barrier.wait()
            try:
                decision_approval_service.convert_to_action(
                    session, organization_id, recommendation_id, actor
                )
            except DecisionIntelligenceServiceError as exc:
                session.rollback()
                return exc.code
            return "converted"

    with ThreadPoolExecutor(max_workers=2) as executor:
        reject_future = executor.submit(reject)
        convert_future = executor.submit(convert)
        reject_result = reject_future.result()
        convert_result = convert_future.result()

    with Session(postgres_engine) as session:
        final_recommendation = session.get(DecisionRecommendation, recommendation_id)
        assert final_recommendation is not None
        if final_recommendation.lifecycle_status == "converted_to_action":
            assert convert_result == "converted"
            assert reject_result == "terminal_recommendation"
            assert final_recommendation.converted_action_id is not None
        else:
            assert final_recommendation.lifecycle_status == "rejected"
            assert reject_result == "rejected"
            assert convert_result == "recommendation_not_approved"
            assert final_recommendation.converted_action_id is None
            assert final_recommendation.approved_by_approval_id is None


@pytest.mark.postgres
def test_decision_concurrent_duplicate_conversions_create_exactly_one_action(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        organization_id, actor = make_decision_org(
            session, f"decision-race-convert-{uuid4().hex[:10]}"
        )
        recommendation, _alternative = add_decision_graph(session, organization_id, actor)
        recommendation_id = recommendation.id
        decision_approval_service.decide(
            session,
            organization_id,
            recommendation_id,
            DecisionApprovalCreate(
                decision="approve", rationale="Approved", idempotency_key="race-approve-2"
            ),
            actor,
            "organization_admin",
        )

    barrier = Barrier(2)

    def convert() -> UUID:
        with Session(postgres_engine) as session:
            barrier.wait()
            action = decision_approval_service.convert_to_action(
                session, organization_id, recommendation_id, actor
            )
            return cast(UUID, action.id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(convert)
        second_future = executor.submit(convert)
        first_action_id = first_future.result()
        second_action_id = second_future.result()

    assert first_action_id == second_action_id

    with Session(postgres_engine) as session:
        approval_count = session.scalar(
            select(func.count())
            .select_from(DecisionApproval)
            .where(DecisionApproval.recommendation_id == recommendation_id)
        )
        assert approval_count == 1


@pytest.mark.postgres
def test_concurrent_self_service_organization_creation_duplicate_slug(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    slug = f"race-org-{uuid4().hex[:10]}"
    payload = OrganizationCreate(
        name="Race Org",
        slug=slug,
        country_code="US",
        default_currency="USD",
        timezone="UTC",
    )

    barrier = Barrier(2)

    def provision() -> str:
        with Session(postgres_engine) as session:
            barrier.wait()
            try:
                create_organization_with_owner(session, payload, uuid4())
            except OrganizationProvisioningError:
                return "conflict"
            return "created"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: provision(), range(2)))
    assert sorted(outcomes) == ["conflict", "created"]

    with Session(postgres_engine) as session:
        organization = session.scalar(select(Organization).where(Organization.slug == slug))
        assert organization is not None
        active_admins = session.scalar(
            select(func.count())
            .select_from(OrganizationMembership)
            .where(
                OrganizationMembership.organization_id == organization.id,
                OrganizationMembership.role == MembershipRole.ORGANIZATION_ADMIN.value,
                OrganizationMembership.status == MembershipStatus.ACTIVE.value,
            )
        )
        assert active_admins == 1


@pytest.mark.postgres
def test_concurrent_invitation_acceptance_by_same_user_is_idempotent(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        organization = OrganizationService().create(
            session,
            OrganizationCreate(
                name="Race Invitation Accept",
                slug=f"race-invite-accept-{uuid4().hex[:10]}",
                country_code="US",
                default_currency="USD",
                timezone="UTC",
            ),
        )
        organization_id = organization.id
        _invitation, token = invitation_service.create(
            session,
            organization_id,
            InvitationCreate(email="race-accept@example.com", role=MembershipRole.ANALYST),
            invited_by_user_id=uuid4(),
        )

    accepting_user = uuid4()
    barrier = Barrier(2)

    def accept() -> UUID:
        with Session(postgres_engine) as session:
            barrier.wait()
            membership = invitation_service.accept(session, token, accepting_user)
            return cast(UUID, membership.id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(accept)
        second_future = executor.submit(accept)
        first_membership_id = first_future.result()
        second_membership_id = second_future.result()

    assert first_membership_id == second_membership_id

    with Session(postgres_engine) as session:
        membership_count = session.scalar(
            select(func.count())
            .select_from(OrganizationMembership)
            .where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.user_id == accepting_user,
            )
        )
        assert membership_count == 1


@pytest.mark.postgres
def test_concurrent_invitation_creation_for_same_email_yields_one_pending(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        organization = OrganizationService().create(
            session,
            OrganizationCreate(
                name="Race Invitation Create",
                slug=f"race-invite-create-{uuid4().hex[:10]}",
                country_code="US",
                default_currency="USD",
                timezone="UTC",
            ),
        )
        organization_id = organization.id

    barrier = Barrier(2)

    def invite() -> str:
        with Session(postgres_engine) as session:
            barrier.wait()
            try:
                invitation_service.create(
                    session,
                    organization_id,
                    InvitationCreate(email="race-create@example.com", role=MembershipRole.VIEWER),
                    invited_by_user_id=uuid4(),
                )
            except InvitationServiceError:
                return "conflict"
            return "created"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: invite(), range(2)))
    assert sorted(outcomes) == ["conflict", "created"]

    with Session(postgres_engine) as session:
        pending_count = session.scalar(
            select(func.count())
            .select_from(OrganizationInvitation)
            .where(
                OrganizationInvitation.organization_id == organization_id,
                OrganizationInvitation.email == "race-create@example.com",
                OrganizationInvitation.status == InvitationStatus.PENDING.value,
            )
        )
        assert pending_count == 1


@pytest.mark.postgres
def test_cm03_concurrent_identical_field_mapping_creation_is_idempotent(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        organization_id, version_id, field_id, _ = cm03_mapping_context(
            session, f"cm03-pg-identical-{uuid4().hex[:8]}"
        )
    payload = cm03_payload(field_id)
    barrier = Barrier(2)

    def create() -> tuple[UUID, bool, int]:
        with Session(postgres_engine) as session:
            barrier.wait()
            result = mapping_template_service.add_field_mapping_with_status(
                session, version_id, payload, organization_id
            )
            usable_count = session.scalar(
                select(func.count())
                .select_from(FieldMapping)
                .where(FieldMapping.template_version_id == version_id)
            )
            assert usable_count is not None
            return result.field_mapping.id, result.created, usable_count

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(create)
        second_future = executor.submit(create)
        results = [first_future.result(), second_future.result()]

    assert {created for _, created, _ in results} == {False, True}
    assert results[0][0] == results[1][0]
    assert all(count == 1 for _, _, count in results)
    with Session(postgres_engine) as session:
        rows = list(
            session.scalars(
                select(FieldMapping).where(FieldMapping.template_version_id == version_id)
            )
        )
        assert len(rows) == 1
        assert rows[0].origin_memory_version_id is None


@pytest.mark.postgres
def test_cm03_concurrent_conflicting_field_mapping_creation_has_typed_loser(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        organization_id, version_id, field_id, _ = cm03_mapping_context(
            session, f"cm03-pg-conflict-{uuid4().hex[:8]}"
        )
    barrier = Barrier(2)

    def create(default_value: str) -> tuple[str, UUID | None, str | None, int]:
        with Session(postgres_engine) as session:
            barrier.wait()
            try:
                result = mapping_template_service.add_field_mapping_with_status(
                    session,
                    version_id,
                    cm03_payload(field_id, default_value=default_value),
                    organization_id,
                )
            except CanonicalMappingServiceError as exc:
                usable_count = session.scalar(
                    select(func.count())
                    .select_from(FieldMapping)
                    .where(FieldMapping.template_version_id == version_id)
                )
                assert usable_count is not None
                return "conflict", None, exc.code, usable_count
            return "created", result.field_mapping.id, None, 1

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(create, "first")
        second_future = executor.submit(create, "second")
        results = [first_future.result(), second_future.result()]

    assert sorted(status for status, _, _, _ in results) == ["conflict", "created"]
    loser = next(result for result in results if result[0] == "conflict")
    assert loser[2] == "FIELD_MAPPING_CONFLICT"
    assert loser[3] == 1
    with Session(postgres_engine) as session:
        rows = list(
            session.scalars(
                select(FieldMapping).where(FieldMapping.template_version_id == version_id)
            )
        )
        assert len(rows) == 1
        assert rows[0].default_value in {"first", "second"}


@pytest.mark.postgres
def test_concurrent_objective_replace_serializes_and_leaves_one_consistent_set(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        organization = OrganizationService().create(
            session,
            OrganizationCreate(
                name="Race Objectives",
                slug=f"race-objectives-{uuid4().hex[:10]}",
                country_code="US",
                default_currency="USD",
                timezone="UTC",
            ),
        )
        organization_id = organization.id
    actor = uuid4()

    barrier = Barrier(2)

    def replace(codes: list[str]) -> None:
        with Session(postgres_engine) as session:
            barrier.wait()
            replace_objectives(session, organization_id, codes, actor)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(replace, ["increase_revenue"])
        second_future = executor.submit(replace, ["reduce_downtime"])
        first_future.result()
        second_future.result()

    with Session(postgres_engine) as session:
        final = list_objectives(session, organization_id)
        # The row lock in _lock_organization serializes the two
        # read-existing/diff/write sequences: whichever call commits last
        # sees the other's committed row as "existing" and replaces it.
        # Without that lock both requests could read an empty "existing"
        # set concurrently and leave both codes selected instead of one.
        assert len(final) == 1
        assert final[0].objective_code in ("increase_revenue", "reduce_downtime")

        row_count = session.scalar(
            select(func.count())
            .select_from(OrganizationObjective)
            .where(OrganizationObjective.organization_id == organization_id)
        )
        assert row_count == 1


@pytest.mark.postgres
def test_ai_profile_concurrent_idempotent_creation_on_postgres(
    postgres_engine: Engine,
) -> None:
    config = alembic_config(require_disposable_postgres_url())
    command.upgrade(config, "head")
    with Session(postgres_engine) as session:
        organization = Organization(
            name="AI profile concurrency",
            slug=f"ai-profile-concurrency-{uuid4().hex[:12]}",
            country_code="US",
            default_currency="USD",
            timezone="UTC",
        )
        session.add(organization)
        session.commit()
        organization_id = organization.id

    provider = FakeProvider(
        [
            ai_profile_item(
                "INDUSTRY",
                "manufacturing",
                f"organization:{organization_id}",
            )
        ]
    )
    service = AIOperationalProfileService(
        Settings(ai_enabled=True, ai_api_key="obviously-fake-test-key")
    )
    service.set_provider_for_testing(provider)
    actor_id = uuid4()
    barrier = Barrier(2)

    def create_profile() -> UUID:
        with Session(postgres_engine) as session:
            barrier.wait()
            return service.create(
                session,
                organization_id,
                actor_id,
                "postgres:ai-profile:concurrent",
            ).id

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(create_profile)
        second = executor.submit(create_profile)
        assert first.result(timeout=20) == second.result(timeout=20)
    assert len(provider.calls) == 1


@pytest.mark.postgres
def test_operational_memory_serializes_concurrent_candidate_creation(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        organization_id, actor_id, source_schema, field_id = memory_foundation(
            session, f"memory-race-{uuid4().hex[:10]}"
        )
        candidates: list[tuple[MemoryCandidateCreate, str | None]] = [
            (
                memory_field_candidate(
                    source_schema,
                    field_id,
                    f"postgres:memory:candidate-same-{attempt}",
                    subject=f"Same Key Equipment {attempt}",
                ),
                None,
            )
            for attempt in range(10)
        ]
        candidates.extend(
            (
                memory_field_candidate(
                    source_schema,
                    field_id,
                    f"postgres:memory:candidate-a-{attempt}",
                    subject=f"Duplicate Identity Equipment {attempt}",
                ),
                f"postgres:memory:candidate-b-{attempt}",
            )
            for attempt in range(10)
        )

    for candidate, second_key in candidates:
        barrier = Barrier(2)

        def record(key: str) -> tuple[UUID, UUID]:
            request = candidate.model_copy(update={"idempotency_key": key})
            with Session(postgres_engine) as session:
                barrier.wait()
                item, version = operational_memory_service.record_candidate(
                    session,
                    organization_id,
                    request,
                    actor_id,
                    "organization_admin",
                )
                return item.id, version.id

        keys = [candidate.idempotency_key, second_key or candidate.idempotency_key]
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(record, keys))
        assert results[0][0] == results[1][0]
        if second_key is None:
            assert results[0] == results[1]
        with Session(postgres_engine) as session:
            item_id = results[0][0]
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(OperationalMemoryItem)
                    .where(
                        OperationalMemoryItem.organization_id == organization_id,
                        OperationalMemoryItem.id == item_id,
                    )
                )
                == 1
            )
            assert session.scalar(
                select(func.count())
                .select_from(OperationalMemoryVersion)
                .where(
                    OperationalMemoryVersion.organization_id == organization_id,
                    OperationalMemoryVersion.memory_id == item_id,
                )
            ) == (1 if second_key is None else 2)


@pytest.mark.postgres
def test_operational_memory_serializes_competing_decisions(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        organization_id, actor_id, source_schema, field_id = memory_foundation(
            session, f"memory-decisions-{uuid4().hex[:10]}"
        )
        confirm_candidates = [
            memory_field_candidate(
                source_schema,
                field_id,
                f"postgres:memory:confirm-seed-{attempt}",
                subject=f"Concurrent Confirm {attempt}",
            )
            for attempt in range(3)
        ]
        mixed_candidates = [
            memory_field_candidate(
                source_schema,
                field_id,
                f"postgres:memory:mixed-seed-{attempt}",
                subject=f"Confirm Reject {attempt}",
            )
            for attempt in range(3)
        ]
        correction_candidates = [
            memory_field_candidate(
                source_schema,
                field_id,
                f"postgres:memory:correct-seed-{attempt}",
                subject=f"Concurrent Correction {attempt}",
            )
            for attempt in range(3)
        ]

    def seed(
        candidate: MemoryCandidateCreate, *, confirm: bool = False
    ) -> tuple[UUID, int, dict[str, object]]:
        with Session(postgres_engine) as session:
            item, _ = operational_memory_service.record_candidate(
                session,
                organization_id,
                candidate,
                actor_id,
                "organization_admin",
            )
            if confirm:
                item, _ = operational_memory_service.decide(
                    session,
                    organization_id,
                    item.id,
                    MemoryDecisionRequest(
                        idempotency_key=f"{candidate.idempotency_key}:confirm",
                        expected_current_version=1,
                        action="CONFIRM",
                        decision_reason_code="HUMAN_REVIEWED",
                    ),
                    actor_id,
                    "organization_admin",
                )
            return item.id, item.current_version_number, dict(candidate.value_payload)

    def race(
        item_id: UUID,
        expected_version: int,
        requests: list[MemoryDecisionRequest],
    ) -> list[str]:
        barrier = Barrier(2)

        def decide(request: MemoryDecisionRequest) -> str:
            with Session(postgres_engine) as session:
                barrier.wait()
                try:
                    operational_memory_service.decide(
                        session,
                        organization_id,
                        item_id,
                        request,
                        actor_id,
                        "organization_admin",
                    )
                except OperationalMemoryServiceError as exc:
                    assert exc.code == "MEMORY_VERSION_CONFLICT"
                    return "conflict"
                return request.action

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(decide, requests))
        assert outcomes.count("conflict") == 1
        with Session(postgres_engine) as session:
            item = session.scalar(
                select(OperationalMemoryItem).where(
                    OperationalMemoryItem.organization_id == organization_id,
                    OperationalMemoryItem.id == item_id,
                )
            )
            assert item is not None and item.current_version_number == expected_version + 1
            current = session.scalar(
                select(OperationalMemoryVersion).where(
                    OperationalMemoryVersion.organization_id == organization_id,
                    OperationalMemoryVersion.memory_id == item_id,
                    OperationalMemoryVersion.version_number == item.current_version_number,
                )
            )
            assert current is not None and current.status == item.current_status
        return outcomes

    for attempt in range(3):
        item_id, version, _ = seed(confirm_candidates[attempt])
        requests = [
            MemoryDecisionRequest(
                idempotency_key=f"postgres:memory:confirm-{attempt}-{side}",
                expected_current_version=version,
                action="CONFIRM",
                decision_reason_code="HUMAN_REVIEWED",
            )
            for side in ("a", "b")
        ]
        assert sorted(race(item_id, version, requests)) == ["CONFIRM", "conflict"]

        mixed_item, mixed_version, _ = seed(mixed_candidates[attempt])
        mixed = [
            MemoryDecisionRequest(
                idempotency_key=f"postgres:memory:mixed-{attempt}-confirm",
                expected_current_version=mixed_version,
                action="CONFIRM",
                decision_reason_code="HUMAN_REVIEWED",
            ),
            MemoryDecisionRequest(
                idempotency_key=f"postgres:memory:mixed-{attempt}-reject",
                expected_current_version=mixed_version,
                action="REJECT",
                decision_reason_code="HUMAN_REVIEWED",
            ),
        ]
        assert sorted(race(mixed_item, mixed_version, mixed)) in (
            ["CONFIRM", "conflict"],
            ["REJECT", "conflict"],
        )

    for attempt in range(3):
        item_id, version, value = seed(correction_candidates[attempt], confirm=True)
        corrections = []
        for side in ("a", "b"):
            corrected = dict(value)
            corrected["canonical_field_code"] = f"equipment_identifier_{side}"
            corrections.append(
                MemoryDecisionRequest(
                    idempotency_key=f"postgres:memory:correct-{attempt}-{side}",
                    expected_current_version=version,
                    action="CORRECT",
                    corrected_payload=corrected,
                    decision_reason_code="HUMAN_REVIEWED",
                )
            )
        assert sorted(race(item_id, version, corrections)) == ["CORRECT", "conflict"]


@pytest.mark.postgres
def test_operational_memory_retrieval_is_atomic_during_correction_and_idempotent(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        organization_id, actor_id, source_schema, field_id = memory_foundation(
            session, f"memory-retrieval-race-{uuid4().hex[:10]}"
        )
        candidate = memory_field_candidate(
            source_schema,
            field_id,
            "postgres:memory:retrieval-race-seed",
            subject="Retrieval Race Equipment",
        )
        item, _ = operational_memory_service.record_candidate(
            session,
            organization_id,
            candidate,
            actor_id,
            "organization_admin",
        )
        item, confirmed = operational_memory_service.decide(
            session,
            organization_id,
            item.id,
            MemoryDecisionRequest(
                idempotency_key="postgres:memory:retrieval-race-confirm",
                expected_current_version=1,
                action="CONFIRM",
                decision_reason_code="HUMAN_REVIEWED",
            ),
            actor_id,
            "organization_admin",
        )
        item_id = item.id
        confirmed_version_id = confirmed.id
        schema_fingerprint = source_schema.schema_fingerprint
        other_organization_id, other_actor_id, other_schema, other_field_id = memory_foundation(
            session, f"memory-retrieval-other-{uuid4().hex[:10]}"
        )
        other_candidate = memory_field_candidate(
            other_schema,
            other_field_id,
            "postgres:memory:retrieval-other-seed",
            subject="Retrieval Race Equipment",
        )
        other_item, _ = operational_memory_service.record_candidate(
            session,
            other_organization_id,
            other_candidate,
            other_actor_id,
            "organization_admin",
        )
        _, other_confirmed = operational_memory_service.decide(
            session,
            other_organization_id,
            other_item.id,
            MemoryDecisionRequest(
                idempotency_key="postgres:memory:retrieval-other-confirm",
                expected_current_version=1,
                action="CONFIRM",
                decision_reason_code="HUMAN_REVIEWED",
            ),
            other_actor_id,
            "organization_admin",
        )
        other_version_id = other_confirmed.id
        other_schema_fingerprint = other_schema.schema_fingerprint

    request = MemoryRetrieveRequest(
        idempotency_key="postgres:memory:retrieval-during-correction",
        category="FIELD_MAPPING",
        subject_kind="SOURCE_FIELD",
        subject="Retrieval Race Equipment",
        source_system_family="ERP",
        canonical_domain="maintenance",
        context=MemoryContext(
            schema_fingerprint=schema_fingerprint,
            source_table_or_entity_context="equipment_master",
            neighboring_field_signatures=["description:string", "status:string"],
        ),
    )
    current_version_id = confirmed_version_id
    current_version_number = 2
    current_status = "CONFIRMED"
    for attempt in range(5):
        corrected_payload = dict(candidate.value_payload)
        corrected_payload["canonical_field_code"] = f"corrected_equipment_id_{attempt}"
        commit_entered = Event()
        allow_commit = Event()
        reader_started = Event()

        def correct() -> UUID:
            with Session(postgres_engine) as session:
                original_commit = session.commit

                def delayed_commit() -> None:
                    commit_entered.set()
                    assert allow_commit.wait(timeout=20)
                    original_commit()

                with patch.object(session, "commit", side_effect=delayed_commit):
                    _, version = operational_memory_service.decide(
                        session,
                        organization_id,
                        item_id,
                        MemoryDecisionRequest(
                            idempotency_key=f"postgres:memory:retrieval-race-correct-{attempt}",
                            expected_current_version=current_version_number,
                            action="CORRECT",
                            corrected_payload=corrected_payload,
                            decision_reason_code="HUMAN_REVIEWED",
                        ),
                        actor_id,
                        "organization_admin",
                    )
                return version.id

        def retrieve_during_correction() -> Any:
            reader_started.set()
            with Session(postgres_engine) as session:
                return operational_memory_service.retrieve(
                    session,
                    organization_id,
                    request.model_copy(
                        update={
                            "idempotency_key": (
                                f"postgres:memory:retrieval-during-correction-{attempt}"
                            )
                        }
                    ),
                )

        prior_version_id = current_version_id
        prior_status = current_status
        with ThreadPoolExecutor(max_workers=2) as executor:
            correction = executor.submit(correct)
            assert commit_entered.wait(timeout=20)
            reader = executor.submit(retrieve_during_correction)
            assert reader_started.wait(timeout=20)
            allow_commit.set()
            corrected_version_id = correction.result(timeout=30)
            during = reader.result(timeout=30)

        assert len(during.suggestions) == 1
        suggestion = during.suggestions[0]
        assert (suggestion.version_id, suggestion.status) in {
            (prior_version_id, prior_status),
            (corrected_version_id, "CORRECTED"),
        }
        current_version_id = corrected_version_id
        current_version_number += 1
        current_status = "CORRECTED"
        with Session(postgres_engine) as session:
            current_item = session.get(OperationalMemoryItem, item_id)
            assert current_item is not None
            assert (
                current_item.current_version_number,
                current_item.current_status,
            ) == (current_version_number, current_status)
            current_version = session.scalar(
                select(OperationalMemoryVersion).where(
                    OperationalMemoryVersion.organization_id == organization_id,
                    OperationalMemoryVersion.memory_id == item_id,
                    OperationalMemoryVersion.version_number == current_version_number,
                )
            )
            assert current_version is not None and current_version.id == current_version_id

    for attempt in range(10):
        concurrent_request = request.model_copy(
            update={"idempotency_key": f"postgres:memory:retrieval-idempotency-race-{attempt}"}
        )
        barrier = Barrier(2)

        def retrieve() -> UUID:
            with Session(postgres_engine) as session:
                barrier.wait()
                result = operational_memory_service.retrieve(
                    session, organization_id, concurrent_request
                )
                assert len(result.suggestions) == 1
                return result.suggestions[0].version_id

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: retrieve(), range(2)))
        assert results == [current_version_id, current_version_id]
        with Session(postgres_engine) as session:
            events = list(
                session.scalars(
                    select(OperationalMemoryReuseEvent).where(
                        OperationalMemoryReuseEvent.organization_id == organization_id,
                        OperationalMemoryReuseEvent.consumer_code == "operational_memory_api",
                        OperationalMemoryReuseEvent.idempotency_key
                        == concurrent_request.idempotency_key,
                    )
                )
            )
            assert len(events) == 1 and events[0].event_sequence == 1

    history_key = "postgres:memory:retrieval-idempotency-race-0"
    with Session(postgres_engine) as session:
        historical_event = session.scalar(
            select(OperationalMemoryReuseEvent).where(
                OperationalMemoryReuseEvent.organization_id == organization_id,
                OperationalMemoryReuseEvent.consumer_code == "operational_memory_api",
                OperationalMemoryReuseEvent.idempotency_key == history_key,
            )
        )
        assert historical_event is not None
        historical_snapshot = (
            historical_event.id,
            historical_event.memory_version_id,
            historical_event.request_fingerprint,
            historical_event.event_sequence,
            historical_event.occurred_at,
        )
    with Session(postgres_engine) as session:
        replayed = operational_memory_service.retrieve(
            session,
            organization_id,
            request.model_copy(update={"idempotency_key": history_key}),
        )
        assert replayed.suggestions[0].version_id == current_version_id
    with Session(postgres_engine) as session:
        historical_event = session.scalar(
            select(OperationalMemoryReuseEvent).where(
                OperationalMemoryReuseEvent.organization_id == organization_id,
                OperationalMemoryReuseEvent.consumer_code == "operational_memory_api",
                OperationalMemoryReuseEvent.idempotency_key == history_key,
            )
        )
        assert historical_event is not None
        assert (
            historical_event.id,
            historical_event.memory_version_id,
            historical_event.request_fingerprint,
            historical_event.event_sequence,
            historical_event.occurred_at,
        ) == historical_snapshot

    for attempt in range(5):
        idempotency_key = f"postgres:memory:retrieval-mismatch-race-{attempt}"
        requests = [
            request.model_copy(
                update={"idempotency_key": idempotency_key, "correlation_id": correlation}
            )
            for correlation in ("correlation-a", "correlation-b")
        ]
        barrier = Barrier(2)

        def retrieve_mismatch(payload: MemoryRetrieveRequest) -> str:
            with Session(postgres_engine) as session:
                barrier.wait()
                try:
                    operational_memory_service.retrieve(session, organization_id, payload)
                except OperationalMemoryServiceError as exc:
                    assert exc.code == "IDEMPOTENCY_CONFLICT"
                    return "conflict"
                return "retrieved"

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(retrieve_mismatch, requests))
        assert sorted(outcomes) == ["conflict", "retrieved"]
        with Session(postgres_engine) as session:
            events = list(
                session.scalars(
                    select(OperationalMemoryReuseEvent).where(
                        OperationalMemoryReuseEvent.organization_id == organization_id,
                        OperationalMemoryReuseEvent.consumer_code == "operational_memory_api",
                        OperationalMemoryReuseEvent.idempotency_key == idempotency_key,
                    )
                )
            )
            assert len(events) == 1 and events[0].event_sequence == 1

    cross_tenant_key = f"postgres:memory:retrieval-cross-tenant-{uuid4().hex}"
    other_request = request.model_copy(
        update={
            "idempotency_key": cross_tenant_key,
            "context": MemoryContext(
                schema_fingerprint=other_schema_fingerprint,
                source_table_or_entity_context="equipment_master",
                neighboring_field_signatures=["description:string", "status:string"],
            ),
        }
    )
    cross_tenant_barrier = Barrier(2)

    def retrieve_for_tenant(tenant_id: UUID, payload: MemoryRetrieveRequest) -> UUID:
        with Session(postgres_engine) as session:
            cross_tenant_barrier.wait()
            result = operational_memory_service.retrieve(session, tenant_id, payload)
            assert len(result.suggestions) == 1
            return result.suggestions[0].version_id

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(
            retrieve_for_tenant,
            organization_id,
            request.model_copy(update={"idempotency_key": cross_tenant_key}),
        )
        second = executor.submit(retrieve_for_tenant, other_organization_id, other_request)
        assert first.result(timeout=30) == current_version_id
        assert second.result(timeout=30) == other_version_id
    with Session(postgres_engine) as session:
        tenant_events = list(
            session.scalars(
                select(OperationalMemoryReuseEvent).where(
                    OperationalMemoryReuseEvent.organization_id.in_(
                        (organization_id, other_organization_id)
                    ),
                    OperationalMemoryReuseEvent.idempotency_key == cross_tenant_key,
                )
            )
        )
        assert {event.organization_id for event in tenant_events} == {
            organization_id,
            other_organization_id,
        }

    class UnrelatedDiag:
        constraint_name = "ck_unrelated_integrity_failure"

    class UnrelatedDatabaseError(Exception):
        diag = UnrelatedDiag()

    with Session(postgres_engine) as session:
        with patch.object(
            session,
            "commit",
            side_effect=IntegrityError("unrelated", {}, UnrelatedDatabaseError()),
        ):
            with pytest.raises(IntegrityError):
                operational_memory_service.retrieve(
                    session,
                    organization_id,
                    request.model_copy(
                        update={"idempotency_key": "postgres:memory:unrelated-integrity"}
                    ),
                )


@pytest.mark.postgres
def test_operational_memory_retrieval_uses_bounded_index_at_ten_thousand_rows(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        organization = Organization(
            name="Operational memory plan",
            slug=f"operational-memory-plan-{uuid4().hex[:12]}",
            country_code="US",
            default_currency="USD",
            timezone="UTC",
        )
        session.add(organization)
        session.commit()
        organization_id = organization.id

        now = datetime.now(UTC)
        session.execute(
            insert(OperationalMemoryItem),
            [
                {
                    "id": uuid4(),
                    "organization_id": organization_id,
                    "category": "TERMINOLOGY",
                    "subject_kind": "TERM",
                    "normalized_subject": f"plan subject {index}",
                    "source_system_family": "__plan_test__",
                    "canonical_domain": "certification",
                    "context_signature": f"{index + 10_000:064x}",
                    "memory_fingerprint": f"{index + 20_000:064x}",
                    "normalization_policy_code": "memory_normalization_v1",
                    "identity_policy_code": "memory_identity_v1",
                    "current_version_number": 1,
                    "current_status": "CONFIRMED",
                    "support_count": 1,
                    "contradiction_count": 0,
                    "confirmation_count": 1,
                    "rejection_count": 0,
                    "is_stale": False,
                    "valid_from": now,
                    "security_classification": "TENANT_INTERNAL",
                    "created_at": now,
                    "updated_at": now,
                }
                for index in range(10_000)
            ],
        )
        session.commit()
        session.execute(text("ANALYZE operational_memory_items"))
        plan = "\n".join(
            str(row[0])
            for row in session.execute(
                text(
                    "EXPLAIN SELECT id FROM operational_memory_items "
                    "WHERE organization_id = :organization_id "
                    "AND category = 'TERMINOLOGY' "
                    "AND normalized_subject = 'plan subject 9999' "
                    "AND current_status IN ('CONFIRMED', 'CORRECTED') LIMIT 20"
                ),
                {"organization_id": organization_id},
            )
        )
        assert "ix_operational_memory_items_org_category_subject" in plan
        session.execute(
            delete(OperationalMemoryItem).where(
                OperationalMemoryItem.organization_id == organization_id,
                OperationalMemoryItem.source_system_family == "__plan_test__",
            )
        )
        session.commit()


@pytest.mark.postgres
def test_cm01_migration_round_trip_enforces_expected_schema(postgres_engine: Engine) -> None:
    config = alembic_config(require_disposable_postgres_url())
    command.upgrade(config, "head")

    inspector = inspect(postgres_engine)
    columns = {column["name"]: column for column in inspector.get_columns("mapping_runs")}
    assert "source_schema_id" in columns
    assert columns["source_schema_id"]["nullable"] is True
    assert "schema_fingerprint_snapshot" in columns
    assert columns["schema_fingerprint_snapshot"]["nullable"] is True

    foreign_keys = {fk["name"]: fk for fk in inspector.get_foreign_keys("mapping_runs")}
    fk = foreign_keys["fk_mapping_runs_org_source_schema"]
    assert set(fk["constrained_columns"]) == {"organization_id", "source_schema_id"}
    assert fk["referred_table"] == "source_schemas"
    assert set(fk["referred_columns"]) == {"organization_id", "id"}

    indexes = {index["name"] for index in inspector.get_indexes("mapping_runs")}
    assert "ix_mapping_runs_org_source_schema" in indexes

    command.downgrade(config, "20260813_0039")
    downgraded_columns = {
        column["name"] for column in inspect(postgres_engine).get_columns("mapping_runs")
    }
    assert "source_schema_id" not in downgraded_columns
    assert "schema_fingerprint_snapshot" not in downgraded_columns

    command.upgrade(config, "head")
    reupgraded_columns = {
        column["name"] for column in inspect(postgres_engine).get_columns("mapping_runs")
    }
    assert "source_schema_id" in reupgraded_columns
    assert "schema_fingerprint_snapshot" in reupgraded_columns

    heads = ScriptDirectory.from_config(config).get_heads()
    assert heads == ["20260817_0043"]


@pytest.mark.postgres
def test_cm01_direct_sql_rejects_cross_tenant_source_schema_insert_on_postgres(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        organization_id, actor, _, version_id, _, _ = canonical_mapping_foundation(
            session, f"cm01-pg-fk-a-{uuid4().hex[:8]}"
        )
        other_id, _, other_dataset_id, other_version_id, _, _ = canonical_mapping_foundation(
            session, f"cm01-pg-fk-b-{uuid4().hex[:8]}"
        )
        _, template_version = cm01_published_entity_mapping(session, organization_id, actor)
        other_schema = cm01_discovered_schema(
            session, other_id, other_dataset_id, other_version_id, "cm01-pg-fk-b"
        )
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    """
                    INSERT INTO mapping_runs (
                        id, organization_id, dataset_version_id, template_version_id,
                        source_schema_id, status, idempotency_key, request_fingerprint,
                        input_count, mapped_count, exception_count, rejected_count,
                        created_by_user_id, created_at, updated_at
                    ) VALUES (
                        :id, :organization_id, :dataset_version_id, :template_version_id,
                        :source_schema_id, 'created', 'cm01-pg-fk-violation', :fingerprint,
                        0, 0, 0, 0, :actor, now(), now()
                    )
                    """
                ),
                {
                    "id": str(uuid4()),
                    "organization_id": str(organization_id),
                    "dataset_version_id": str(version_id),
                    "template_version_id": str(template_version.id),
                    "source_schema_id": str(other_schema.id),
                    "fingerprint": "2" * 64,
                    "actor": str(actor),
                },
            )
            session.commit()
        session.rollback()


@pytest.mark.postgres
def test_cm01_valid_execution_persists_snapshot_and_shares_schema_across_runs(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        organization_id, actor, dataset_id, version_id, _, raw_reference_id = (
            canonical_mapping_foundation(session, f"cm01-pg-valid-{uuid4().hex[:8]}")
        )
        _, template_version = cm01_published_entity_mapping(session, organization_id, actor)
        schema = cm01_discovered_schema(
            session, organization_id, dataset_id, version_id, "cm01-pg-valid"
        )
        request_one = MappingRunCreate(
            dataset_version_id=version_id,
            template_version_id=template_version.id,
            source_schema_id=schema.id,
            idempotency_key="cm01-pg-valid-run-1",
            records=[
                MappingInputRecord(
                    raw_record_reference_id=raw_reference_id,
                    values={"customer_id": "C-001", "customer_name": "Acme"},
                )
            ],
        )
        request_two = request_one.model_copy(update={"idempotency_key": "cm01-pg-valid-run-2"})
        run_one = mapping_execution_service.execute(session, organization_id, request_one, actor)
        run_two = mapping_execution_service.execute(session, organization_id, request_two, actor)
        assert run_one.id != run_two.id
        assert run_one.source_schema_id == schema.id
        assert run_two.source_schema_id == schema.id
        assert run_one.schema_fingerprint_snapshot == schema.schema_fingerprint
        assert run_two.schema_fingerprint_snapshot == schema.schema_fingerprint

        historical = MappingRun(
            organization_id=organization_id,
            dataset_version_id=version_id,
            template_version_id=template_version.id,
            source_schema_id=None,
            schema_fingerprint_snapshot=None,
            status="completed",
            idempotency_key="cm01-pg-historical",
            request_fingerprint="3" * 64,
            input_count=0,
            mapped_count=0,
            exception_count=0,
            rejected_count=0,
            created_by_user_id=actor,
        )
        session.add(historical)
        session.commit()
        session.refresh(historical)
        assert historical.source_schema_id is None
        assert historical.schema_fingerprint_snapshot is None


@pytest.mark.postgres
def test_cm01_wrong_dataset_pairing_rejected_by_service_on_postgres(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        organization_id, actor, dataset_id, version_id, _, raw_reference_id = (
            canonical_mapping_foundation(session, f"cm01-pg-wrong-version-{uuid4().hex[:8]}")
        )
        _, template_version = cm01_published_entity_mapping(session, organization_id, actor)
        schema = cm01_discovered_schema(
            session, organization_id, dataset_id, version_id, "cm01-pg-wrong-version"
        )
        dataset = session.get(Dataset, dataset_id)
        assert dataset is not None
        other_batch = IngestionBatchService().create(
            session,
            organization_id,
            IngestionBatchCreate(
                source_system_id=dataset.source_system_id,
                batch_number="cm01-pg-wrong-version-batch-2",
                ingestion_method="file_upload",
                trigger_type="manual",
            ),
            actor,
        )
        other_version = DatasetVersionService().create(
            session,
            organization_id,
            dataset_id,
            DatasetVersionCreate(
                ingestion_batch_id=other_batch.id,
                source_file_name="cm01-pg-wrong-version-2.csv",
                source_file_extension="csv",
            ),
        )
        with pytest.raises(CanonicalMappingServiceError) as exc:
            mapping_execution_service.execute(
                session,
                organization_id,
                MappingRunCreate(
                    dataset_version_id=other_version.id,
                    template_version_id=template_version.id,
                    source_schema_id=schema.id,
                    idempotency_key="cm01-pg-wrong-version-run",
                    records=[
                        MappingInputRecord(
                            raw_record_reference_id=raw_reference_id,
                            values={"customer_id": "C-001", "customer_name": "Acme"},
                        )
                    ],
                ),
                actor,
            )
        assert (exc.value.code, exc.value.status) == (
            "SOURCE_SCHEMA_DATASET_VERSION_MISMATCH",
            409,
        )


@pytest.mark.postgres
def test_cm02_concurrent_identical_execution_stress_probe(postgres_engine: Engine) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        organization_id, actor, dataset_id, version_id, _, raw_reference_id = (
            canonical_mapping_foundation(session, f"cm02-pg-stress-{uuid4().hex[:8]}")
        )
        _, template_version = cm01_published_entity_mapping(session, organization_id, actor)
        schema = cm01_discovered_schema(
            session, organization_id, dataset_id, version_id, "cm02-pg-stress"
        )
        template_version_id = template_version.id
        schema_id = schema.id
        schema_fingerprint = schema.schema_fingerprint

    rounds = 10
    concurrency = 5
    for round_index in range(rounds):
        idempotency_key = f"cm02-pg-stress-round-{round_index}"
        request = MappingRunCreate(
            dataset_version_id=version_id,
            template_version_id=template_version_id,
            source_schema_id=schema_id,
            idempotency_key=idempotency_key,
            records=[
                MappingInputRecord(
                    raw_record_reference_id=raw_reference_id,
                    values={"customer_id": f"C-{round_index}", "customer_name": "Acme"},
                )
            ],
        )
        barrier = Barrier(concurrency)

        def execute_run() -> UUID:
            with Session(postgres_engine) as worker_session:
                barrier.wait()
                return mapping_execution_service.execute(
                    worker_session, organization_id, request, actor
                ).id

        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(execute_run) for _ in range(concurrency)]
            results = [future.result(timeout=30) for future in futures]

        assert len(set(results)) == 1

        with Session(postgres_engine) as verify_session:
            runs = list(
                verify_session.scalars(
                    select(MappingRun).where(
                        MappingRun.organization_id == organization_id,
                        MappingRun.idempotency_key == idempotency_key,
                    )
                )
            )
            assert len(runs) == 1
            run = runs[0]
            assert run.source_schema_id == schema_id
            assert run.schema_fingerprint_snapshot == schema_fingerprint
            record_results = verify_session.scalar(
                select(func.count())
                .select_from(MappingRecordResult)
                .where(MappingRecordResult.mapping_run_id == run.id)
            )
            assert record_results == run.input_count


@pytest.mark.postgres
def test_cm02_concurrent_correlation_metadata_is_exact_replay(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        organization_id, actor, dataset_id, version_id, _, raw_reference_id = (
            canonical_mapping_foundation(session, f"cm02-pg-conflict-{uuid4().hex[:8]}")
        )
        _, template_version = cm01_published_entity_mapping(session, organization_id, actor)
        schema = cm01_discovered_schema(
            session, organization_id, dataset_id, version_id, "cm02-pg-conflict"
        )
        template_version_id = template_version.id
        schema_id = schema.id

    idempotency_key = "cm02-pg-conflict-key"
    request_a = MappingRunCreate(
        dataset_version_id=version_id,
        template_version_id=template_version_id,
        source_schema_id=schema_id,
        idempotency_key=idempotency_key,
        correlation_id="variant-a",
        records=[
            MappingInputRecord(
                raw_record_reference_id=raw_reference_id,
                values={"customer_id": "C-A", "customer_name": "Acme"},
            )
        ],
    )
    request_b = request_a.model_copy(update={"correlation_id": "variant-b"})
    barrier = Barrier(2)
    outcomes: list[tuple[str, object]] = []

    def execute_run(request: MappingRunCreate) -> None:
        with Session(postgres_engine) as worker_session:
            barrier.wait()
            try:
                run = mapping_execution_service.execute(
                    worker_session, organization_id, request, actor
                )
                outcomes.append(("ok", run.id))
            except CanonicalMappingServiceError as exc:
                outcomes.append((exc.code, exc.status))

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(execute_run, request_a)
        second = executor.submit(execute_run, request_b)
        first.result(timeout=20)
        second.result(timeout=20)

    winners = [outcome for outcome in outcomes if outcome[0] == "ok"]
    assert len(winners) == 2
    assert len({outcome[1] for outcome in winners}) == 1

    with Session(postgres_engine) as verify_session:
        run_count = verify_session.scalar(
            select(func.count())
            .select_from(MappingRun)
            .where(
                MappingRun.organization_id == organization_id,
                MappingRun.idempotency_key == idempotency_key,
            )
        )
        assert run_count == 1


@pytest.mark.postgres
def test_cm02_concurrent_semantic_difference_yields_controlled_conflict(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        organization_id, actor, dataset_id, version_id, _, raw_reference_id = (
            canonical_mapping_foundation(session, f"cm02-pg-semantic-{uuid4().hex[:8]}")
        )
        _, template_version = cm01_published_entity_mapping(session, organization_id, actor)
        schema = cm01_discovered_schema(
            session, organization_id, dataset_id, version_id, "cm02-pg-semantic"
        )
        template_version_id = template_version.id
        schema_id = schema.id

    idempotency_key = "cm02-pg-semantic-conflict-key"
    request_a = MappingRunCreate(
        dataset_version_id=version_id,
        template_version_id=template_version_id,
        source_schema_id=schema_id,
        idempotency_key=idempotency_key,
        records=[
            MappingInputRecord(
                raw_record_reference_id=raw_reference_id,
                values={"customer_id": "C-A", "customer_name": "Acme"},
            )
        ],
    )
    request_b = request_a.model_copy(
        update={
            "records": [
                MappingInputRecord(
                    raw_record_reference_id=raw_reference_id,
                    values={"customer_id": "C-B", "customer_name": "Beta"},
                )
            ]
        }
    )
    barrier = Barrier(2)

    def submit_run(request: MappingRunCreate) -> tuple[str, object]:
        with Session(postgres_engine) as worker_session:
            barrier.wait()
            try:
                run, _ = mapping_execution_service.submit(
                    worker_session, organization_id, request, actor
                )
                return "ok", run.id
            except CanonicalMappingServiceError as exc:
                return exc.code, exc.status

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(submit_run, (request_a, request_b)))

    assert sum(outcome[0] == "ok" for outcome in outcomes) == 1
    assert [outcome for outcome in outcomes if outcome[0] != "ok"] == [
        ("IDEMPOTENCY_CONFLICT", 409)
    ]
    with Session(postgres_engine) as verify_session:
        assert (
            verify_session.scalar(
                select(func.count())
                .select_from(MappingRun)
                .where(
                    MappingRun.organization_id == organization_id,
                    MappingRun.idempotency_key == idempotency_key,
                )
            )
            == 1
        )


@pytest.mark.postgres
def test_cm02_concurrent_cross_tenant_same_key_remains_isolated(postgres_engine: Engine) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        org_a, actor_a, dataset_a, version_a, _, raw_a = canonical_mapping_foundation(
            session, f"cm02-pg-tenant-a-{uuid4().hex[:8]}"
        )
        org_b, actor_b, dataset_b, version_b, _, raw_b = canonical_mapping_foundation(
            session, f"cm02-pg-tenant-b-{uuid4().hex[:8]}"
        )
        _, template_a = cm01_published_entity_mapping(session, org_a, actor_a)
        _, template_b = cm01_published_entity_mapping(session, org_b, actor_b)
        schema_a = cm01_discovered_schema(session, org_a, dataset_a, version_a, "cm02-pg-tenant-a")
        schema_b = cm01_discovered_schema(session, org_b, dataset_b, version_b, "cm02-pg-tenant-b")
        template_a_id = template_a.id
        template_b_id = template_b.id
        schema_a_id = schema_a.id
        schema_b_id = schema_b.id

    shared_key = "cm02-pg-shared-cross-tenant-key"
    request_a = MappingRunCreate(
        dataset_version_id=version_a,
        template_version_id=template_a_id,
        source_schema_id=schema_a_id,
        idempotency_key=shared_key,
        records=[
            MappingInputRecord(
                raw_record_reference_id=raw_a,
                values={"customer_id": "C-A", "customer_name": "Acme"},
            )
        ],
    )
    request_b = MappingRunCreate(
        dataset_version_id=version_b,
        template_version_id=template_b_id,
        source_schema_id=schema_b_id,
        idempotency_key=shared_key,
        records=[
            MappingInputRecord(
                raw_record_reference_id=raw_b,
                values={"customer_id": "C-B", "customer_name": "Acme"},
            )
        ],
    )
    barrier = Barrier(2)
    results: dict[str, UUID] = {}

    def execute_run(
        label: str, organization_id: UUID, request: MappingRunCreate, actor: UUID
    ) -> None:
        with Session(postgres_engine) as worker_session:
            barrier.wait()
            run = mapping_execution_service.execute(worker_session, organization_id, request, actor)
            results[label] = run.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(execute_run, "a", org_a, request_a, actor_a)
        second = executor.submit(execute_run, "b", org_b, request_b, actor_b)
        first.result(timeout=20)
        second.result(timeout=20)

    assert results["a"] != results["b"]
    with Session(postgres_engine) as verify_session:
        run_a = verify_session.get(MappingRun, results["a"])
        run_b = verify_session.get(MappingRun, results["b"])
        assert run_a is not None and run_b is not None
        assert run_a.organization_id == org_a
        assert run_b.organization_id == org_b


@pytest.mark.postgres
def test_dbfeedback_concurrent_identical_execution_registers_evidence_exactly_once(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        organization_id, actor, dataset_id, version_id, _, raw_reference_id = (
            canonical_mapping_foundation(session, f"dbfeedback-pg-stress-{uuid4().hex[:8]}")
        )
        _, template_version = cm01_published_entity_mapping(session, organization_id, actor)
        schema = schema_discovery_service.discover(
            session,
            organization_id,
            SourceSchemaDiscover(
                dataset_id=dataset_id,
                dataset_version_id=version_id,
                schema_fingerprint="dbfeedback-pg-stress-fingerprint".ljust(32, "0"),
                fields=[
                    SourceFieldCreate(field_path="customer_name", inferred_data_type="string"),
                    SourceFieldCreate(field_path="customer_id", inferred_data_type="string"),
                ],
            ),
        )
        template_version_id = template_version.id
        schema_id = schema.id

    rounds = 5
    concurrency = 5
    for round_index in range(rounds):
        idempotency_key = f"dbfeedback-pg-stress-round-{round_index}"
        request = MappingRunCreate(
            dataset_version_id=version_id,
            template_version_id=template_version_id,
            source_schema_id=schema_id,
            idempotency_key=idempotency_key,
            records=[
                MappingInputRecord(
                    raw_record_reference_id=raw_reference_id,
                    values={"customer_id": f"C-{round_index}", "customer_name": "Acme"},
                )
            ],
        )
        barrier = Barrier(concurrency)

        def execute_run() -> UUID:
            with Session(postgres_engine) as worker_session:
                barrier.wait()
                return mapping_execution_service.execute(
                    worker_session, organization_id, request, actor
                ).id

        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(execute_run) for _ in range(concurrency)]
            results = [future.result(timeout=30) for future in futures]

        assert len(set(results)) == 1

        with Session(postgres_engine) as verify_session:
            items = list(
                verify_session.scalars(
                    select(OperationalMemoryItem).where(
                        OperationalMemoryItem.organization_id == organization_id,
                        OperationalMemoryItem.category == "FIELD_MAPPING",
                    )
                )
            )
            assert {item.normalized_subject for item in items} == {
                "customer name",
                "customer id",
            }
            for item in items:
                # exactly one of the five concurrent callers per round may reach
                # the registration path (CM-02's replay/recovery paths return
                # before it); support_count must advance by exactly one per round.
                assert item.support_count == round_index + 1
                assert item.current_version_number == round_index + 1
                version_count = verify_session.scalar(
                    select(func.count())
                    .select_from(OperationalMemoryVersion)
                    .where(OperationalMemoryVersion.memory_id == item.id)
                )
                assert version_count == round_index + 1


@pytest.mark.postgres
def test_field_mapping_origin_lineage_migration_round_trip_enforces_expected_schema(
    postgres_engine: Engine,
) -> None:
    config = alembic_config(require_disposable_postgres_url())
    command.upgrade(config, "head")

    inspector = inspect(postgres_engine)
    columns = {column["name"]: column for column in inspector.get_columns("field_mappings")}
    assert "origin_memory_version_id" in columns
    assert columns["origin_memory_version_id"]["nullable"] is True
    foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys("field_mappings")}
    assert "fk_field_mappings_origin_memory_version" not in foreign_keys

    command.downgrade(config, "20260814_0040")
    downgraded_columns = {
        column["name"] for column in inspect(postgres_engine).get_columns("field_mappings")
    }
    assert "origin_memory_version_id" not in downgraded_columns

    command.upgrade(config, "head")
    reupgraded_columns = {
        column["name"] for column in inspect(postgres_engine).get_columns("field_mappings")
    }
    assert "origin_memory_version_id" in reupgraded_columns

    heads = ScriptDirectory.from_config(config).get_heads()
    assert heads == ["20260817_0043"]


@pytest.mark.postgres
def test_dbfeedback_c_lineage_column_persists_on_postgres(postgres_engine: Engine) -> None:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        organization_id, actor, dataset_id, version_id, _, _ = canonical_mapping_foundation(
            session, f"dbfeedback-c-pg-{uuid4().hex[:8]}"
        )
        _, template_version = cm01_published_entity_mapping(session, organization_id, actor)
        schema = cm01_discovered_schema(
            session, organization_id, dataset_id, version_id, "dbfeedback-c-pg"
        )
        existing = session.scalar(
            select(FieldMapping).where(FieldMapping.template_version_id == template_version.id)
        )
        assert existing is not None
        candidate = MemoryCandidateCreate(
            idempotency_key="dbfeedback-c-pg-candidate",
            category="FIELD_MAPPING",
            subject_kind="SOURCE_FIELD",
            subject="asset_no",
            context=MemoryContext(schema_fingerprint=schema.schema_fingerprint),
            value_payload={
                "source_field_path": "asset_no",
                "source_field_type": "string",
                "canonical_type_kind": "entity",
                "canonical_type_id": str(existing.canonical_field_definition_id),
                "canonical_field_definition_id": str(existing.canonical_field_definition_id),
                "canonical_field_code": "name",
                "schema_fingerprint": schema.schema_fingerprint,
            },
            provenance=MemoryProvenance(
                source_schema_id=schema.id,
                canonical_field_definition_ids=[existing.canonical_field_definition_id],
            ),
            source_fingerprint="a" * 64,
        )
        item, _ = operational_memory_service.record_candidate(
            session, organization_id, candidate, None, "system"
        )
        _, confirmed = operational_memory_service.decide(
            session,
            organization_id,
            item.id,
            MemoryDecisionRequest(
                idempotency_key="dbfeedback-c-pg-confirm",
                expected_current_version=item.current_version_number,
                action="CONFIRM",
            ),
            actor,
            "organization_admin",
        )
        lineage_field = FieldMapping(
            template_version_id=template_version.id,
            source_field_path="asset_no",
            canonical_field_definition_id=existing.canonical_field_definition_id,
            sequence=existing.sequence + 100,
            is_required_for_publication=False,
            default_value=None,
            origin_memory_version_id=confirmed.id,
        )
        session.add(lineage_field)
        session.commit()
        session.refresh(lineage_field)
        field_mapping_id = lineage_field.id
        confirmed_id = confirmed.id

    with Session(postgres_engine) as verify_session:
        reread = verify_session.get(FieldMapping, field_mapping_id)
        assert reread is not None
        assert reread.origin_memory_version_id == confirmed_id


@pytest.mark.postgres
def test_p3_03e1_governance_tier_historical_backfill_is_deterministic(
    postgres_engine: Engine,
) -> None:
    """P3.03E.1 hard tests L, M, N, O, P, Q, R, S, T.

    Seeds Finding rows shaped like each historical producer at the current
    head schema, strips the governance_tier column back to 20260815_0041,
    then re-applies 20260816_0042 and asserts the deterministic backfill rule:
    GOVERNED only when source_execution_id, trust_assessment_id,
    analytical_readiness_id, and dataset_id are ALL non-null; LIGHTWEIGHT
    otherwise. No third tier, no inference from any other column.
    """
    config = alembic_config(require_disposable_postgres_url())
    command.upgrade(config, "head")
    organization_service = OrganizationService()
    source_service = SourceSystemService()
    dataset_service = DatasetService()
    trust_service = TrustAssessmentService()
    intelligence_service = IntelligenceExecutionService()
    suffix = uuid4().hex[:10]
    finding_ids: dict[str, UUID] = {}

    with Session(postgres_engine) as session:
        actor = uuid4()
        organization = organization_service.create(
            session,
            OrganizationCreate(
                name=f"Governance Backfill {suffix}",
                slug=f"gov-backfill-{suffix}",
                country_code="US",
                default_currency="USD",
                timezone="UTC",
            ),
        )
        source = source_service.create(
            session,
            organization.id,
            SourceSystemCreate(
                name="Backfill ERP",
                code="backfill-erp",
                system_type="erp",
                integration_method="api",
            ),
            actor,
        )
        source.status = "active"
        session.commit()
        dataset = dataset_service.create(
            session,
            organization.id,
            DatasetCreate(
                source_system_id=source.id,
                name="Backfill dataset",
                code=f"backfill-dataset-{suffix}",
                domain="finance",
                dataset_type="transactional",
                default_currency="USD",
            ),
            actor,
        )
        assessment = trust_service.create_and_execute(
            session,
            organization.id,
            dataset.id,
            TrustAssessmentCreate(
                records=[{"id": "1", "amount": "10.00"}],
                rule_configurations={
                    "required_field_completeness": {"required_fields": ["id", "amount"]},
                    "numeric_range_validity": {"numeric_ranges": {"amount": {"minimum": 0}}},
                },
            ),
        )
        execution = intelligence_service.execute(
            session,
            organization.id,
            IntelligenceExecutionCreate(
                dataset_id=dataset.id,
                trust_assessment_id=assessment.id,
                execution_type="calculation",
                definition_code="sum",
                records=[{"amount": "10.00"}],
                parameters={"field": "amount"},
                currency="USD",
            ),
            actor,
        )

        # L: full governed lineage shape.
        governed = FindingPublicationService().publish_candidate_finding(
            session,
            organization.id,
            CandidateFindingCreate(
                execution_id=execution.id,
                result_id=execution.id,
                finding_type="kpi",
                title="Governed backfill shape",
                summary="Full governed lineage.",
                domain_code="finance",
                measured_value=execution.result_value,
                measured_value_type="currency",
                measured_currency="USD",
                severity="info",
                severity_reason={"policy": "backfill-validation"},
                dataset_reference=f"{dataset.code}@backfill-validation",
                evidence_policy_code="P3.03E.1-BACKFILL",
                evidence_policy_version="1.0",
                calculation_traces=[
                    {
                        "operation_code": "sum",
                        "input_reference_summary": {"dataset_id": str(dataset.id)},
                        "parameter_summary": {"field": "amount"},
                    }
                ],
            ),
            actor,
        )
        finding_ids["governed"] = governed.id
        assert governed.source_execution_id is not None
        assert governed.trust_assessment_id is not None
        assert governed.analytical_readiness_id is not None
        assert governed.dataset_id is not None

        # M: legacy FindingService shape (no lineage FKs, no finding_code).
        legacy = FindingService().create(
            session,
            organization.id,
            FindingCreate(
                rule_id="BACKFILL.LEGACY",
                title="Legacy backfill shape",
                summary="No governed lineage.",
                domain="job_to_cash",
                severity="high",
                confidence_score=1,
            ),
        )
        finding_ids["legacy"] = legacy.id

        # N: Industry-Pack-like shape (finding_code set, no lineage FKs).
        industry_pack_like = Finding(
            organization_id=organization.id,
            governance_tier=FindingGovernanceTier.LIGHTWEIGHT.value,
            rule_id="PACK-BACKFILL.RULE",
            finding_code="PACK-BACKFILL.RULE",
            finding_type="deterministic_rule",
            title="Industry-pack-like backfill shape",
            summary="Direct industry-pack style creation.",
            domain="operations",
            severity="medium",
            confidence_score=1,
            status="open",
            industry_pack_code="PACK-BACKFILL",
            measured_value=Decimal("12"),
            measured_value_type="observed",
            exposure_value=Decimal("2"),
            exposure_value_type="estimated",
            affected_record_count=1,
            detected_at=datetime.now(UTC),
            definition_code="PACK-BACKFILL.RULE",
            definition_version="1.0.0",
            confidence_level="high",
            deduplication_key=uuid4().hex,
            created_by_user_id=actor,
        )
        session.add(industry_pack_like)
        session.flush()
        finding_ids["industry_pack_like"] = industry_pack_like.id

        # O: Signature-like shape (finding_code set, no lineage FKs).
        signature_like = Finding(
            organization_id=organization.id,
            governance_tier=FindingGovernanceTier.LIGHTWEIGHT.value,
            rule_id="SIGNATURE.BACKFILL",
            finding_code="SIGNATURE.BACKFILL",
            finding_type="operational_signature",
            title="Signature-like backfill shape",
            summary="Direct signature style creation.",
            domain="oilfield",
            domain_code="oilfield",
            severity="medium",
            confidence_score=Decimal("0.9"),
            status="open",
            confidence_level="high",
            affected_record_count=1,
            detected_at=datetime.now(UTC),
            definition_code="SIGNATURE.BACKFILL",
            definition_version="1.0.0",
            deduplication_key=uuid4().hex,
            created_by_user_id=actor,
        )
        session.add(signature_like)
        session.flush()
        finding_ids["signature_like"] = signature_like.id
        session.commit()

    # Strip governance_tier back to its pre-P3.03E.1 (nonexistent) state, then
    # re-apply the migration to exercise the deterministic backfill rule.
    command.downgrade(config, "20260815_0041")
    command.upgrade(config, "head")

    inspector = inspect(postgres_engine)
    columns = {column["name"]: column for column in inspector.get_columns("findings")}
    assert "governance_tier" in columns
    assert columns["governance_tier"]["nullable"] is False  # S (NOT NULL half of Q/S)

    check_constraints = {c["name"] for c in inspector.get_check_constraints("findings")}
    assert "ck_findings_governance_tier" in check_constraints  # S

    indexes = {ix["name"] for ix in inspector.get_indexes("findings")}
    assert "ix_findings_organization_governance_tier" in indexes  # R

    with Session(postgres_engine) as session:
        raw_rows = {
            key: session.get(Finding, finding_id) for key, finding_id in finding_ids.items()
        }
        assert all(row is not None for row in raw_rows.values())
        rows = cast(dict[str, Finding], raw_rows)
        assert rows["governed"].governance_tier == FindingGovernanceTier.GOVERNED.value  # L
        assert rows["legacy"].governance_tier == FindingGovernanceTier.LIGHTWEIGHT.value  # M
        assert (
            rows["industry_pack_like"].governance_tier == FindingGovernanceTier.LIGHTWEIGHT.value
        )  # N
        assert (
            rows["signature_like"].governance_tier == FindingGovernanceTier.LIGHTWEIGHT.value
        )  # O

        remaining_null = session.scalar(
            select(func.count()).select_from(Finding).where(Finding.governance_tier.is_(None))
        )
        assert remaining_null == 0  # P

        with pytest.raises(IntegrityError):
            session.execute(
                text("UPDATE findings SET governance_tier = 'UNKNOWN' WHERE id = :id"),
                {"id": str(finding_ids["legacy"])},
            )
            session.commit()
        session.rollback()  # Q


@pytest.mark.postgres
def test_p3_03e1_migration_upgrade_downgrade_reupgrade_lifecycle_on_postgres(
    postgres_engine: Engine,
) -> None:
    """P3.03E.1 hard test T."""
    config = alembic_config(require_disposable_postgres_url())
    command.upgrade(config, "20260815_0041")
    command.upgrade(config, "head")
    inspector = inspect(postgres_engine)
    assert "governance_tier" in {column["name"] for column in inspector.get_columns("findings")}
    command.downgrade(config, "20260815_0041")
    inspector = inspect(postgres_engine)
    assert "governance_tier" not in {column["name"] for column in inspector.get_columns("findings")}
    command.upgrade(config, "head")
    inspector = inspect(postgres_engine)
    columns = {column["name"]: column for column in inspector.get_columns("findings")}
    assert "governance_tier" in columns
    assert columns["governance_tier"]["nullable"] is False
    check_constraints = {c["name"] for c in inspector.get_check_constraints("findings")}
    assert "ck_findings_governance_tier" in check_constraints
    indexes = {ix["name"] for ix in inspector.get_indexes("findings")}
    assert "ix_findings_organization_governance_tier" in indexes


@pytest.mark.postgres
def test_p3_05b_mapping_execution_contract_migration_on_postgres(
    postgres_engine: Engine,
) -> None:
    config = alembic_config(require_disposable_postgres_url())
    command.upgrade(config, "head")
    inspector = inspect(postgres_engine)

    assert "mapping_run_inputs" in inspector.get_table_names()
    run_columns = {column["name"] for column in inspector.get_columns("mapping_runs")}
    assert {
        "failure_code",
        "failure_message",
        "failure_retryable",
        "failed_at",
        "retry_of_run_id",
        "root_run_id",
        "attempt_number",
        "execution_claimed_at",
        "heartbeat_at",
    } <= run_columns
    uniques = {item["name"] for item in inspector.get_unique_constraints("mapping_runs")}
    assert "uq_mapping_run_retry_child" in uniques
    input_uniques = {
        item["name"] for item in inspector.get_unique_constraints("mapping_run_inputs")
    }
    assert "uq_mapping_run_input_sequence" in input_uniques

    command.downgrade(config, "20260816_0042")
    inspector = inspect(postgres_engine)
    assert "mapping_run_inputs" not in inspector.get_table_names()
    assert "failure_code" not in {
        column["name"] for column in inspector.get_columns("mapping_runs")
    }
    command.upgrade(config, "head")


def _p3_05b_postgres_context(
    postgres_engine: Engine, label: str
) -> tuple[UUID, UUID, UUID, UUID, UUID, UUID]:
    command.upgrade(alembic_config(require_disposable_postgres_url()), "head")
    with Session(postgres_engine) as session:
        organization_id, actor, dataset_id, version_id, _, raw_reference_id = (
            canonical_mapping_foundation(session, f"p305b-pg-{label}-{uuid4().hex[:8]}")
        )
        _, template_version = cm01_published_entity_mapping(session, organization_id, actor)
        schema = cm01_discovered_schema(
            session, organization_id, dataset_id, version_id, f"p305b-pg-{label}"
        )
        return organization_id, actor, version_id, template_version.id, schema.id, raw_reference_id


def _p3_05b_request(
    version_id: UUID,
    template_version_id: UUID,
    schema_id: UUID,
    raw_reference_id: UUID,
    idempotency_key: str,
    customer_id: str = "C-001",
) -> MappingRunCreate:
    return MappingRunCreate(
        dataset_version_id=version_id,
        template_version_id=template_version_id,
        source_schema_id=schema_id,
        idempotency_key=idempotency_key,
        records=[
            MappingInputRecord(
                raw_record_reference_id=raw_reference_id,
                values={"customer_id": customer_id, "customer_name": "Acme"},
            )
        ],
    )


@pytest.mark.postgres
def test_p3_05b_concurrent_exact_submission_on_postgres(postgres_engine: Engine) -> None:
    organization_id, actor, version_id, template_id, schema_id, raw_id = _p3_05b_postgres_context(
        postgres_engine, "exact-submit"
    )
    request = _p3_05b_request(version_id, template_id, schema_id, raw_id, "p305b-pg-exact-submit")
    barrier = Barrier(2)
    insert_barrier = Barrier(2)
    validate_submission = mapping_execution_service._validate_submission

    def synchronized_validation(
        session: Session, tenant_id: UUID, payload: MappingRunCreate
    ) -> None:
        validate_submission(session, tenant_id, payload)
        insert_barrier.wait()

    def submit() -> UUID:
        with Session(postgres_engine) as session:
            barrier.wait()
            run, _ = mapping_execution_service.submit(session, organization_id, request, actor)
            return run.id

    with patch.object(
        mapping_execution_service, "_validate_submission", side_effect=synchronized_validation
    ):
        with ThreadPoolExecutor(max_workers=2) as executor:
            run_ids = list(executor.map(lambda _: submit(), range(2)))

    assert len(set(run_ids)) == 1
    with Session(postgres_engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(MappingRun)
                .where(
                    MappingRun.organization_id == organization_id,
                    MappingRun.idempotency_key == request.idempotency_key,
                )
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(MappingRunInput)
                .where(MappingRunInput.mapping_run_id == run_ids[0])
            )
            == 1
        )


@pytest.mark.postgres
def test_p3_05b_concurrent_conflicting_submission_on_postgres(
    postgres_engine: Engine,
) -> None:
    organization_id, actor, version_id, template_id, schema_id, raw_id = _p3_05b_postgres_context(
        postgres_engine, "conflict-submit"
    )
    requests = (
        _p3_05b_request(
            version_id, template_id, schema_id, raw_id, "p305b-pg-conflict-submit", "C-A"
        ),
        _p3_05b_request(
            version_id, template_id, schema_id, raw_id, "p305b-pg-conflict-submit", "C-B"
        ),
    )
    barrier = Barrier(2)
    insert_barrier = Barrier(2)
    validate_submission = mapping_execution_service._validate_submission

    def synchronized_validation(
        session: Session, tenant_id: UUID, payload: MappingRunCreate
    ) -> None:
        validate_submission(session, tenant_id, payload)
        insert_barrier.wait()

    def submit(request: MappingRunCreate) -> tuple[str, object]:
        with Session(postgres_engine) as session:
            barrier.wait()
            try:
                run, _ = mapping_execution_service.submit(session, organization_id, request, actor)
                return "ok", run.id
            except CanonicalMappingServiceError as exc:
                return exc.code, exc.status

    with patch.object(
        mapping_execution_service, "_validate_submission", side_effect=synchronized_validation
    ):
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(submit, requests))

    assert sum(outcome[0] == "ok" for outcome in outcomes) == 1
    assert [outcome for outcome in outcomes if outcome[0] != "ok"] == [
        ("IDEMPOTENCY_CONFLICT", 409)
    ]
    with Session(postgres_engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(MappingRun)
                .where(
                    MappingRun.organization_id == organization_id,
                    MappingRun.idempotency_key == "p305b-pg-conflict-submit",
                )
            )
            == 1
        )


@pytest.mark.postgres
def test_p3_05b_atomic_claim_on_postgres(postgres_engine: Engine) -> None:
    organization_id, actor, version_id, template_id, schema_id, raw_id = _p3_05b_postgres_context(
        postgres_engine, "claim"
    )
    with Session(postgres_engine) as session:
        run, _ = mapping_execution_service.submit(
            session,
            organization_id,
            _p3_05b_request(version_id, template_id, schema_id, raw_id, "p305b-pg-claim"),
            actor,
        )
        run_id = run.id
    barrier = Barrier(2)

    def claim() -> tuple[str, object]:
        with Session(postgres_engine) as session:
            barrier.wait()
            try:
                result = mapping_execution_service.claim_and_execute(
                    session, organization_id, run_id
                )
                return "ok", result.id
            except CanonicalMappingServiceError as exc:
                return exc.code, exc.status

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: claim(), range(2)))

    assert sum(outcome[0] == "ok" for outcome in outcomes) == 1
    assert [outcome for outcome in outcomes if outcome[0] != "ok"] == [
        ("MAPPING_RUN_INVALID_TRANSITION", 409)
    ]
    with Session(postgres_engine) as session:
        persisted = session.get(MappingRun, run_id)
        assert persisted is not None
        assert persisted.execution_claimed_at is not None
        assert persisted.status in {
            MappingRunStatus.COMPLETED.value,
            MappingRunStatus.PARTIALLY_COMPLETED.value,
            MappingRunStatus.FAILED.value,
        }


def _p3_05b_retryable_predecessor(postgres_engine: Engine, label: str) -> tuple[UUID, UUID, UUID]:
    organization_id, actor, version_id, template_id, schema_id, raw_id = _p3_05b_postgres_context(
        postgres_engine, label
    )
    with Session(postgres_engine) as session:
        run, _ = mapping_execution_service.submit(
            session,
            organization_id,
            _p3_05b_request(version_id, template_id, schema_id, raw_id, f"p305b-pg-{label}-root"),
            actor,
        )
        failed = mapping_execution_service.fail(
            session, organization_id, run.id, "RETRYABLE_TEST_FAILURE", "Retryable failure", True
        )
        return organization_id, actor, failed.id


@pytest.mark.postgres
def test_p3_05b_concurrent_same_key_retry_on_postgres(postgres_engine: Engine) -> None:
    organization_id, actor, predecessor_id = _p3_05b_retryable_predecessor(
        postgres_engine, "same-retry"
    )
    payload = MappingRunRetryCreate(idempotency_key="p305b-pg-same-retry-child")
    barrier = Barrier(2)

    def retry() -> UUID:
        with Session(postgres_engine) as session:
            barrier.wait()
            child, _ = mapping_execution_service.retry(
                session, organization_id, predecessor_id, payload, actor
            )
            return child.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        child_ids = list(executor.map(lambda _: retry(), range(2)))

    assert len(set(child_ids)) == 1
    with Session(postgres_engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(MappingRun)
                .where(MappingRun.retry_of_run_id == predecessor_id)
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(MappingRunInput)
                .where(MappingRunInput.mapping_run_id == child_ids[0])
            )
            == 1
        )


@pytest.mark.postgres
def test_p3_05b_concurrent_different_key_retry_on_postgres(
    postgres_engine: Engine,
) -> None:
    organization_id, actor, predecessor_id = _p3_05b_retryable_predecessor(
        postgres_engine, "different-retry"
    )
    payloads = (
        MappingRunRetryCreate(idempotency_key="p305b-pg-different-retry-a"),
        MappingRunRetryCreate(idempotency_key="p305b-pg-different-retry-b"),
    )
    barrier = Barrier(2)

    def retry(payload: MappingRunRetryCreate) -> tuple[str, object]:
        with Session(postgres_engine) as session:
            barrier.wait()
            try:
                child, _ = mapping_execution_service.retry(
                    session, organization_id, predecessor_id, payload, actor
                )
                return "ok", child.id
            except CanonicalMappingServiceError as exc:
                return exc.code, exc.status

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(retry, payloads))

    assert sum(outcome[0] == "ok" for outcome in outcomes) == 1
    assert [outcome for outcome in outcomes if outcome[0] != "ok"] == [
        ("MAPPING_RUN_RETRY_ALREADY_CREATED", 409)
    ]
    with Session(postgres_engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(MappingRun)
                .where(MappingRun.retry_of_run_id == predecessor_id)
            )
            == 1
        )


@pytest.mark.postgres
def test_p3_05b_database_prevents_two_direct_retry_children(
    postgres_engine: Engine,
) -> None:
    organization_id, actor, predecessor_id = _p3_05b_retryable_predecessor(
        postgres_engine, "direct-child"
    )
    with Session(postgres_engine) as session:
        first, _ = mapping_execution_service.retry(
            session,
            organization_id,
            predecessor_id,
            MappingRunRetryCreate(idempotency_key="p305b-pg-direct-child-a"),
            actor,
        )
        predecessor = session.get(MappingRun, predecessor_id)
        assert predecessor is not None
        session.add(
            MappingRun(
                organization_id=organization_id,
                dataset_version_id=predecessor.dataset_version_id,
                template_version_id=predecessor.template_version_id,
                source_schema_id=predecessor.source_schema_id,
                schema_fingerprint_snapshot=predecessor.schema_fingerprint_snapshot,
                status=MappingRunStatus.QUEUED.value,
                idempotency_key="p305b-pg-direct-child-b",
                request_fingerprint=predecessor.request_fingerprint,
                input_count=predecessor.input_count,
                created_by_user_id=actor,
                retry_of_run_id=predecessor_id,
                root_run_id=predecessor.root_run_id,
                attempt_number=predecessor.attempt_number + 1,
            )
        )
        with pytest.raises(IntegrityError) as exc:
            session.commit()
        assert (
            getattr(getattr(exc.value.orig, "diag", None), "constraint_name", None)
            == "uq_mapping_run_retry_child"
        )
        session.rollback()
        assert session.get(MappingRun, first.id) is not None
