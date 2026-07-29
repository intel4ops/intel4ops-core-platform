from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from conftest import IdentityState
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.definitions.resolution import (
    CodeBackedOIKBDefinitionResolver,
    DefinitionKnowledgeClass,
)
from app.models.entities import Finding
from app.models.intelligence import IntelligenceExecution
from app.models.orchestration import (
    IntelligenceEngineRegistration,
    IntelligenceOrchestrationStep,
)
from app.models.trust import AnalyticalReadinessDecision, ReadinessStatus
from app.registries.engine_registry import EngineRegistry
from app.schemas.contracts import OrganizationCreate
from app.schemas.findings import CandidateFindingCreate
from app.schemas.ingestion import DatasetCreate
from app.schemas.intelligence import ExecutionType
from app.schemas.oikb import (
    DefinitionCreate,
    DefinitionVersionCreate,
    GovernanceAction,
    InputRequirementCreate,
    LifecycleStatus,
    ValidationCaseCreate,
)
from app.schemas.orchestration import OrchestrationAnalyticalLevel, OrchestrationCreate
from app.schemas.source_systems import SourceSystemCreate
from app.schemas.trust import TrustAssessmentCreate
from app.services.ingestion_service import DatasetService
from app.services.oikb_service import (
    definition_registry_service,
    governance_service,
    knowledge_validation_service,
)
from app.services.orchestration_service import (
    ArithmeticEngineAdapter,
    EngineRegistrationConsistencyService,
    OrchestrationError,
    OrchestrationService,
)
from app.services.organization_service import OrganizationService
from app.services.source_system_service import SourceSystemService
from app.services.trust_service import TrustAssessmentService


def foundation(db: Session, slug: str) -> tuple[UUID, UUID, UUID, UUID]:
    actor = uuid4()
    organization = OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug,
            slug=slug,
            country_code="US",
            default_currency="USD",
            timezone="UTC",
        ),
    )
    source = SourceSystemService().create(
        db,
        organization.id,
        SourceSystemCreate(
            name="ERP",
            code="erp",
            system_type="erp",
            integration_method="api",
        ),
        actor,
    )
    source.status = "active"
    db.commit()
    dataset = DatasetService().create(
        db,
        organization.id,
        DatasetCreate(
            source_system_id=source.id,
            name="Canonical operations",
            code="canonical-operations",
            domain="operations",
            dataset_type="transactional",
            default_currency="USD",
        ),
        actor,
    )
    assessment = TrustAssessmentService().create_and_execute(
        db,
        organization.id,
        dataset.id,
        TrustAssessmentCreate(
            records=[{"id": "1", "amount": "10.25"}],
            rule_configurations={
                "required_field_completeness": {"required_fields": ["id", "amount"]},
                "numeric_range_validity": {"numeric_ranges": {"amount": {"minimum": 0}}},
            },
        ),
    )
    readiness = db.scalar(
        select(AnalyticalReadinessDecision).where(
            AnalyticalReadinessDecision.trust_assessment_id == assessment.id,
            AnalyticalReadinessDecision.analytical_level == "arithmetic",
        )
    )
    assert readiness is not None
    return organization.id, dataset.id, assessment.id, readiness.id


def request(
    dataset_id: UUID,
    assessment_id: UUID,
    readiness_id: UUID,
    *,
    key: str,
    execution_type: str = "calculation",
    definition_code: str = "sum",
    parameters: dict[str, object] | None = None,
    records: list[dict[str, object]] | None = None,
) -> OrchestrationCreate:
    return OrchestrationCreate(
        definition_code=definition_code,
        definition_version="1.0",
        dataset_id=dataset_id,
        dataset_reference=f"dataset:{dataset_id}",
        trust_assessment_id=assessment_id,
        analytical_readiness_id=readiness_id,
        execution_type=execution_type,
        records=records or [{"id": "1", "amount": "10.25"}],
        parameters=parameters or {"field": "amount"},
        currency="USD" if execution_type == "calculation" else None,
        correlation_id=f"correlation-{key}",
        idempotency_key=key,
    )


def candidate(measured_value: str) -> CandidateFindingCreate:
    placeholder = uuid4()
    return CandidateFindingCreate(
        execution_id=placeholder,
        result_id=placeholder,
        finding_type="exception",
        title="Governed arithmetic exception",
        summary="Synthetic orchestration publication.",
        domain_code="operations",
        measured_value=Decimal(measured_value),
        measured_value_type="currency",
        measured_currency="USD",
        severity="medium",
        severity_reason={"policy": "synthetic"},
        confidence_level="high",
        affected_record_count=1,
        occurrence_start=datetime(2026, 7, 1, tzinfo=UTC),
        occurrence_end=datetime(2026, 7, 31, tzinfo=UTC),
        dataset_reference="synthetic-dataset",
        evidence_policy_code="WP209",
        evidence_policy_version="1.0",
        evidence=[
            {
                "evidence_type": "affected_record",
                "reference_type": "canonical_record",
                "reference_id": "SYNTHETIC-1",
                "label": "Synthetic affected record",
            }
        ],
        calculation_traces=[
            {
                "operation_code": "sum",
                "input_reference_summary": {"dataset": "synthetic-dataset"},
                "parameter_summary": {"field": "amount"},
            }
        ],
        limitations=["Synthetic acceptance-test evidence."],
    )


def test_governed_oikb_definition_executes_through_wp207_adapter(db: Session) -> None:
    organization_id, dataset_id, assessment_id, readiness_id = foundation(
        db, "orchestration-governed-oikb"
    )
    actor = uuid4()
    definition = definition_registry_service.create(
        db,
        DefinitionCreate(
            stable_code="SHARED.OPERATIONS.GOVERNED_SUM",
            name="Governed sum",
            description="Governed orchestration integration test.",
            knowledge_class="kpi",
            analytical_level="arithmetic",
            domain="operations",
            scope_type="shared_core",
            is_system_definition=True,
        ),
        actor,
    )
    version = definition_registry_service.create_version(
        db,
        definition.id,
        None,
        DefinitionVersionCreate(
            semantic_version="1.0.0",
            quality_level="provisional",
            expression_schema={"operation": "sum", "inputs": ["amount"]},
            output_type="currency",
            output_unit="USD",
            currency_code="USD",
            readiness_requirement={"analytical_level": "arithmetic"},
            input_requirements=[
                InputRequirementCreate(
                    input_code="amount",
                    canonical_entity="transaction",
                    canonical_field="amount",
                    expected_type="currency",
                    expected_unit="USD",
                    currency_code="USD",
                )
            ],
        ),
        actor,
    )
    knowledge_validation_service.create_case(
        db,
        version,
        ValidationCaseCreate(
            case_code="NORMAL_CASE",
            description="Normal sum.",
            input_payload={"values": [1, 2]},
            expected_output="3",
            tolerance="0",
        ),
    )
    knowledge_validation_service.run(db, version, actor)
    for lifecycle in (
        LifecycleStatus.IN_REVIEW,
        LifecycleStatus.VALIDATED,
        LifecycleStatus.APPROVED,
        LifecycleStatus.ACTIVE,
    ):
        if lifecycle == LifecycleStatus.VALIDATED:
            governance_service.mark_validated(db, version.id, None, actor)
        else:
            governance_service.transition(
                db,
                version.id,
                None,
                lifecycle,
                GovernanceAction(reason=f"test {lifecycle.value}"),
                actor,
            )
    payload = request(
        dataset_id,
        assessment_id,
        readiness_id,
        key="governed-oikb",
        definition_code=definition.stable_code,
    ).model_copy(update={"definition_version": "1.0.0"})
    service = OrchestrationService()
    outcome = service.orchestrate(db, organization_id, payload, actor)
    execution_id = next(
        step.source_execution_id
        for step in service.steps(db, organization_id, outcome.id)
        if step.source_execution_id is not None
    )
    execution = db.get(IntelligenceExecution, execution_id)
    assert execution is not None
    assert execution.status == "completed"
    assert execution.definition_code == definition.stable_code
    assert execution.definition_version == "1.0.0"
    assert execution.definition_fingerprint == version.fingerprint
    assert any("governed OIKB-to-WP-2.07" in item for item in execution.limitations)


def test_arithmetic_orchestration_is_explainable_and_reuses_wp207(db: Session) -> None:
    organization_id, dataset_id, assessment_id, readiness_id = foundation(
        db, "orchestration-arithmetic"
    )
    service = OrchestrationService()
    outcome = service.orchestrate(
        db,
        organization_id,
        request(dataset_id, assessment_id, readiness_id, key="arithmetic-1"),
        uuid4(),
    )

    steps = service.steps(db, organization_id, outcome.id)
    decisions = service.decisions(db, organization_id, outcome.id)
    history = service.history(db, organization_id, outcome.id)
    execution_step = next(step for step in steps if step.step_type == "execution")

    assert outcome.status == "completed"
    assert execution_step.source_execution_id == execution_step.source_result_id
    assert execution_step.result_locator == "embedded_result"
    assert execution_step.output_index == 0
    assert execution_step.engine_code == "ARITHMETIC_ENGINE"
    assert decisions[-1].sufficiency_status == "sufficient"
    assert decisions[-1].escalation_status == "not_required"
    assert [item.new_status for item in history] == [
        "received",
        "validating",
        "deciding",
        "executing",
        "completed",
    ]
    assert "records" not in outcome.parameters_summary
    assert len(outcome.context_fingerprint) == 64


def test_rule_orchestration_uses_only_registered_rule_engine(db: Session) -> None:
    organization_id, dataset_id, assessment_id, readiness_id = foundation(db, "orchestration-rule")
    payload = request(
        dataset_id,
        assessment_id,
        readiness_id,
        key="rule-1",
        execution_type="rule",
        definition_code="threshold_exceeded",
        parameters={"value": 12, "threshold": 10},
        records=[],
    )
    outcome = OrchestrationService().orchestrate(db, organization_id, payload, uuid4())
    step = db.scalar(
        select(IntelligenceOrchestrationStep).where(
            IntelligenceOrchestrationStep.orchestration_request_id == outcome.id,
            IntelligenceOrchestrationStep.step_type == "execution",
        )
    )

    assert outcome.status == "completed"
    assert step is not None
    assert step.engine_code == "DETERMINISTIC_RULE_ENGINE"
    assert step.analytical_level == "rule_based"
    decisions = OrchestrationService().decisions(db, organization_id, outcome.id)
    assert decisions[0].requested_level == "rule_based"
    assert decisions[0].evaluated_readiness_level == "arithmetic"
    assert decisions[0].readiness_mapping_policy_code == "LEGACY_RULE_TO_ARITHMETIC_V1"
    assert decisions[0].readiness_mapping_policy_version == "1.0"
    assert "Dedicated rule-based readiness is unavailable" in decisions[0].warnings[0]
    assert any("LEGACY_RULE_TO_ARITHMETIC_V1" in item for item in outcome.warnings)


def test_idempotency_conflicts_and_tenant_keys_are_isolated(db: Session) -> None:
    first = foundation(db, "orchestration-idempotency-first")
    second = foundation(db, "orchestration-idempotency-second")
    service = OrchestrationService()
    payload = request(first[1], first[2], first[3], key="shared-key")
    created = service.orchestrate(db, first[0], payload, uuid4())
    retried = service.orchestrate(db, first[0], payload, uuid4())
    assert retried.id == created.id

    with pytest.raises(OrchestrationError, match="different request") as conflict:
        service.orchestrate(
            db,
            first[0],
            payload.model_copy(update={"parameters": {"field": "other"}}),
            uuid4(),
        )
    assert conflict.value.code == "INVALID_IDEMPOTENCY_KEY"

    other = service.orchestrate(
        db,
        second[0],
        request(second[1], second[2], second[3], key="shared-key"),
        uuid4(),
    )
    assert other.organization_id == second[0]


def test_readiness_block_is_policy_block_not_failure(db: Session) -> None:
    organization_id, dataset_id, assessment_id, readiness_id = foundation(
        db, "orchestration-blocked"
    )
    readiness = db.get(AnalyticalReadinessDecision, readiness_id)
    assert readiness is not None
    readiness.readiness_status = ReadinessStatus.BLOCKED.value
    readiness.explanation = "Critical completeness policy blocked execution"
    db.commit()

    service = OrchestrationService()
    outcome = service.orchestrate(
        db,
        organization_id,
        request(dataset_id, assessment_id, readiness_id, key="blocked-1"),
        uuid4(),
    )
    steps = service.steps(db, organization_id, outcome.id)

    assert outcome.status == "blocked"
    assert all(step.status != "failed" for step in steps)
    assert steps[-1].block_reason_code == "TRUST_REQUIREMENT_NOT_MET"


def test_arithmetic_fallback_preserves_result_when_advanced_engine_is_absent(
    db: Session,
) -> None:
    organization_id, dataset_id, assessment_id, _ = foundation(db, "orchestration-fallback")
    statistical = db.scalar(
        select(AnalyticalReadinessDecision).where(
            AnalyticalReadinessDecision.trust_assessment_id == assessment_id,
            AnalyticalReadinessDecision.analytical_level == "statistical",
        )
    )
    assert statistical is not None
    statistical.readiness_status = ReadinessStatus.READY.value
    statistical.explanation = "Synthetic readiness for fallback policy test"
    db.commit()
    payload = request(dataset_id, assessment_id, statistical.id, key="fallback-1").model_copy(
        update={"requested_analytical_level": OrchestrationAnalyticalLevel.STATISTICAL}
    )

    service = OrchestrationService()
    outcome = service.orchestrate(db, organization_id, payload, uuid4())
    decisions = service.decisions(db, organization_id, outcome.id)

    assert outcome.status == "completed_with_limitations"
    assert "arithmetic fallback" in outcome.limitations[0]
    assert decisions[-1].escalation_status == "not_required"
    assert all(decision.selected_engine_code != "STATISTICAL_ENGINE" for decision in decisions)


def test_wp208_handoff_and_partial_completion_are_governed(db: Session) -> None:
    organization_id, dataset_id, assessment_id, readiness_id = foundation(
        db, "orchestration-finding"
    )
    service = OrchestrationService()
    base = request(dataset_id, assessment_id, readiness_id, key="finding-1")
    published = service.orchestrate(
        db,
        organization_id,
        base.model_copy(update={"publish_finding": True, "finding_candidate": candidate("10.25")}),
        uuid4(),
    )
    finding_step = next(
        step
        for step in service.steps(db, organization_id, published.id)
        if step.step_type == "finding_publication"
    )
    assert published.status == "completed"
    assert finding_step.finding_id is not None
    finding = db.get(Finding, finding_step.finding_id)
    assert finding is not None
    assert finding.source_execution_id == finding_step.source_execution_id
    assert finding.source_result_id == finding_step.source_result_id
    assert finding_step.result_locator == "embedded_result"
    assert finding_step.output_index == 0

    partial = service.orchestrate(
        db,
        organization_id,
        base.model_copy(
            update={
                "idempotency_key": "finding-2",
                "correlation_id": "correlation-finding-2",
                "publish_finding": True,
                "finding_candidate": candidate("999.00"),
            }
        ),
        uuid4(),
    )
    assert partial.status == "partially_completed"
    assert any("RESULT_NOT_ELIGIBLE" in item for item in partial.limitations)


def test_engine_registry_has_only_real_engines_and_persists_capabilities(
    db: Session,
) -> None:
    service = OrchestrationService()
    engines = service.engines_list(db)
    assert [engine.engine_code for engine in engines] == [
        "ARITHMETIC_ENGINE",
        "DETERMINISTIC_RULE_ENGINE",
        "FORECASTING_INTELLIGENCE_ENGINE",
        "STATISTICAL_INTELLIGENCE_ENGINE",
    ]
    assert all(engine.is_available and engine.supports_sync for engine in engines)
    assert (
        db.scalar(
            select(IntelligenceEngineRegistration).where(
                IntelligenceEngineRegistration.engine_code == "STATISTICAL_ENGINE"
            )
        )
        is None
    )


def test_code_backed_oikb_adapter_returns_normalized_definition_contract() -> None:
    resolver = CodeBackedOIKBDefinitionResolver()
    calculation = resolver.resolve("sum", "1.0", ExecutionType.CALCULATION)
    rule = resolver.resolve("threshold_exceeded", "1.0", ExecutionType.RULE)

    assert calculation.knowledge_class == DefinitionKnowledgeClass.CALCULATION
    assert calculation.analytical_level == "arithmetic"
    assert calculation.required_readiness_level == "arithmetic"
    assert calculation.required_engine_capability == "bounded_arithmetic"
    assert calculation.is_active and calculation.publication_eligible
    assert calculation.sufficiency_policy.code
    assert calculation.escalation_policy.code
    assert calculation.evidence_policy.code
    assert isinstance(calculation.scope_metadata, dict)
    assert len(calculation.definition_fingerprint) == 64
    assert rule.knowledge_class == DefinitionKnowledgeClass.DETERMINISTIC_RULE
    assert rule.analytical_level == "rule_based"
    assert rule.required_readiness_level == "arithmetic"


def test_rule_bridge_blocks_without_arithmetic_readiness_and_fabricates_nothing(
    db: Session,
) -> None:
    organization_id, dataset_id, assessment_id, readiness_id = foundation(
        db, "orchestration-rule-readiness-block"
    )
    readiness = db.get(AnalyticalReadinessDecision, readiness_id)
    assert readiness is not None
    readiness.readiness_status = ReadinessStatus.BLOCKED.value
    readiness.explanation = "Arithmetic readiness is blocked"
    db.commit()
    payload = request(
        dataset_id,
        assessment_id,
        readiness_id,
        key="rule-readiness-block",
        execution_type="rule",
        definition_code="threshold_exceeded",
        parameters={"value": 12, "threshold": 10},
        records=[],
    )
    service = OrchestrationService()
    outcome = service.orchestrate(db, organization_id, payload, uuid4())
    decision = service.decisions(db, organization_id, outcome.id)[0]

    assert outcome.status == "blocked"
    assert decision.evaluated_readiness_level == "arithmetic"
    assert decision.readiness_mapping_policy_code == "LEGACY_RULE_TO_ARITHMETIC_V1"
    assert (
        db.scalar(
            select(AnalyticalReadinessDecision).where(
                AnalyticalReadinessDecision.trust_assessment_id == assessment_id,
                AnalyticalReadinessDecision.analytical_level == "rule_based",
            )
        )
        is None
    )
    assert not any(
        step.step_type == "execution" for step in service.steps(db, organization_id, outcome.id)
    )


@pytest.mark.parametrize("level", ["forecasting", "reliability", "simulation"])
def test_missing_readiness_levels_are_governed_unsupported_outcomes(
    db: Session, level: str
) -> None:
    organization_id, dataset_id, assessment_id, readiness_id = foundation(
        db, f"orchestration-unsupported-{level}"
    )
    if level == "forecasting":
        forecasting_readiness = db.scalar(
            select(AnalyticalReadinessDecision).where(
                AnalyticalReadinessDecision.trust_assessment_id == assessment_id,
                AnalyticalReadinessDecision.analytical_level == "forecasting",
            )
        )
        assert forecasting_readiness is not None
        readiness_id = forecasting_readiness.id
    payload = request(
        dataset_id,
        assessment_id,
        readiness_id,
        key=f"unsupported-{level}",
    ).model_copy(
        update={
            "requested_analytical_level": OrchestrationAnalyticalLevel(level),
            "allow_arithmetic_fallback": False,
        }
    )
    payload = OrchestrationCreate.model_validate(payload.model_dump())
    service = OrchestrationService()
    outcome = service.orchestrate(db, organization_id, payload, uuid4())
    decision = service.decisions(db, organization_id, outcome.id)[0]

    assert outcome.status == ("blocked" if level == "forecasting" else "unsupported")
    assert decision.decision_reason_code == (
        "READINESS_REQUIREMENT_NOT_MET" if level == "forecasting" else "READINESS_LEVEL_UNSUPPORTED"
    )
    assert decision.evaluated_readiness_level == ("forecasting" if level == "forecasting" else None)
    assert decision.selected_engine_code is None
    assert not any(
        step.step_type == "execution" for step in service.steps(db, organization_id, outcome.id)
    )


def test_engine_registration_and_adapter_must_match_exactly(db: Session) -> None:
    consistency = EngineRegistrationConsistencyService()
    adapter = ArithmeticEngineAdapter()
    registry = EngineRegistry()
    registry.register(adapter)

    with pytest.raises(OrchestrationError) as missing:
        consistency.eligible_adapter(db, registry, adapter.capability.analytical_level)
    assert missing.value.code == "ENGINE_NOT_REGISTERED"

    consistency.seed_missing(db, registry)
    registration = db.scalar(
        select(IntelligenceEngineRegistration).where(
            IntelligenceEngineRegistration.engine_code == "ARITHMETIC_ENGINE"
        )
    )
    assert registration is not None
    consistency.validate_registration(registration, adapter)

    with pytest.raises(OrchestrationError) as no_adapter:
        consistency.validate_registration(registration, None)
    assert no_adapter.value.code == "ENGINE_NOT_REGISTERED"

    mismatch_cases = (
        ("engine_version", "9.9"),
        ("input_contract_version", "9.9"),
        ("output_contract_version", "9.9"),
        ("analytical_level", "statistical"),
    )
    for field, invalid in mismatch_cases:
        original = getattr(registration, field)
        setattr(registration, field, invalid)
        with pytest.raises(OrchestrationError) as mismatch:
            consistency.validate_registration(registration, adapter)
        assert mismatch.value.code == "ENGINE_CONTRACT_MISMATCH"
        setattr(registration, field, original)

    registration.status = "inactive"
    with pytest.raises(OrchestrationError) as inactive:
        consistency.validate_registration(registration, adapter)
    assert inactive.value.code == "ENGINE_UNAVAILABLE"
    registration.status = "active"

    database_only = IntelligenceEngineRegistration(
        engine_code="DATABASE_ONLY_ENGINE",
        engine_name="Database-only engine",
        engine_version="1.0",
        analytical_level="statistical",
        capability_code="not_executable",
        status="active",
        is_available=True,
        supports_sync=True,
        supports_async=False,
        input_contract_version="1.0",
        output_contract_version="1.0",
        implementation_reference="none",
    )
    db.add(database_only)
    db.flush()
    with pytest.raises(OrchestrationError) as database_without_adapter:
        consistency.validate_registration(database_only, None)
    assert database_without_adapter.value.code == "ENGINE_NOT_REGISTERED"


def test_api_queries_are_tenant_scoped_paginated_and_authorized(
    client: TestClient,
    db: Session,
    identity: IdentityState,
) -> None:
    organization_id, dataset_id, assessment_id, readiness_id = foundation(db, "orchestration-api")
    payload = request(dataset_id, assessment_id, readiness_id, key="api-1").model_dump(mode="json")
    created = client.post(
        f"/api/v1/organizations/{organization_id}/intelligence/orchestrations",
        json=payload,
    )
    assert created.status_code == 201
    orchestration_id = created.json()["id"]

    page = client.get(
        f"/api/v1/organizations/{organization_id}/intelligence/orchestrations",
        params={"status": "completed", "page_size": 1},
    )
    detail = client.get(
        f"/api/v1/organizations/{organization_id}/intelligence/orchestrations/{orchestration_id}"
    )
    assert page.status_code == 200
    assert page.json()["total"] == 1
    assert detail.status_code == 200
    assert detail.json()["steps"]
    assert detail.json()["decisions"]

    other = foundation(db, "orchestration-api-other")[0]
    hidden = client.get(
        f"/api/v1/organizations/{other}/intelligence/orchestrations/{orchestration_id}"
    )
    assert hidden.status_code == 404

    identity.is_platform_admin = False
    engines = client.get("/api/v1/intelligence/engines")
    assert engines.status_code == 403


def test_actions_reject_cross_tenant_orchestration_sources(
    client: TestClient,
    db: Session,
) -> None:
    first, dataset_id, assessment_id, readiness_id = foundation(db, "action-orchestration-source")
    orchestration = client.post(
        f"/api/v1/organizations/{first}/intelligence/orchestrations",
        json=request(
            dataset_id,
            assessment_id,
            readiness_id,
            key="action-source",
        ).model_dump(mode="json"),
    )
    assert orchestration.status_code == 201
    orchestration_id = orchestration.json()["id"]
    second = foundation(db, "action-orchestration-source-other")[0]
    payload = {
        "source_type": "manual",
        "source_reference": f"orchestration:{orchestration_id}",
        "orchestration_request_id": orchestration_id,
        "recommendation_type": "inspection",
        "recommendation_rule_version": "1.0",
        "title": "Inspect governed orchestration result",
        "description": "Validate the governed result before operational execution.",
        "rationale": "The orchestration result requires an organization-owned action.",
    }

    cross_tenant = client.post(
        f"/api/v1/organizations/{second}/actions",
        json=payload,
    )
    assert cross_tenant.status_code == 404
    assert cross_tenant.json()["detail"]["code"] == "SOURCE_NOT_FOUND"

    same_tenant = client.post(
        f"/api/v1/organizations/{first}/actions",
        json=payload,
    )
    assert same_tenant.status_code == 201
    assert same_tenant.json()["organization_id"] == str(first)
