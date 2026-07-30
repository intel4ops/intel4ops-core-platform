from uuid import uuid4

import pytest
from sqlalchemy.orm import Session
from test_statistical_service import _GOVERNED_DATASETS, statistical_foundation

from app.schemas.intelligence import ExecutionType
from app.schemas.orchestration import OrchestrationAnalyticalLevel, OrchestrationCreate
from app.services.orchestration_service import OrchestrationError, OrchestrationService


def test_statistical_engine_registration_and_governed_orchestration(db: Session) -> None:
    organization_id, dataset_id, trust_id, readiness_id, actor = statistical_foundation(
        db, "statistical-orchestrator"
    )
    service = OrchestrationService()
    outcome = service.orchestrate(
        db,
        organization_id,
        OrchestrationCreate(
            definition_code="SHARED.STATISTICS.ROBUST_OUTLIER",
            definition_version="1.0.0",
            dataset_id=dataset_id,
            dataset_version_id=_GOVERNED_DATASETS[trust_id][1],
            trust_assessment_id=trust_id,
            analytical_readiness_id=readiness_id,
            requested_analytical_level=OrchestrationAnalyticalLevel.STATISTICAL,
            records=[
                {"value": value, "entity_reference": f"entity-{index}"}
                for index, value in enumerate([10, 11, 9, 10, 10, 100])
            ],
            parameters={
                "deviation_threshold": 3.5,
                "minimum_confidence": 0.1,
                "persistence_count": 2,
            },
            execution_type=ExecutionType.CALCULATION,
            unit="USD",
            currency="USD",
            correlation_id=f"statistical-{uuid4()}",
            idempotency_key=f"statistical-{uuid4()}",
            request_context={
                "dataset_fingerprint": "c" * 64,
                "source_lineage_reference": f"lineage:{dataset_id}",
            },
        ),
        actor,
    )
    assert outcome.status == "completed"
    steps = service.steps(db, organization_id, outcome.id)
    execution_step = next(step for step in steps if step.step_type == "execution")
    assert execution_step.engine_code == "STATISTICAL_INTELLIGENCE_ENGINE"
    assert execution_step.result_locator is not None
    assert execution_step.result_locator.startswith("statistical_execution:")
    engines = service.engines_list(db)
    statistical = next(
        engine for engine in engines if engine.engine_code == "STATISTICAL_INTELLIGENCE_ENGINE"
    )
    assert statistical.capability_code == "bounded_statistical_intelligence"
    assert statistical.analytical_level == "statistical"


def test_statistical_adapter_validation_uses_governed_error_contract(db: Session) -> None:
    organization_id, dataset_id, trust_id, readiness_id, actor = statistical_foundation(
        db, "statistical-validation-envelope"
    )
    with pytest.raises(OrchestrationError) as captured:
        OrchestrationService().orchestrate(
            db,
            organization_id,
            OrchestrationCreate(
                definition_code="SHARED.STATISTICS.ROBUST_OUTLIER",
                definition_version="1.0.0",
                dataset_id=dataset_id,
                dataset_version_id=_GOVERNED_DATASETS[trust_id][1],
                trust_assessment_id=trust_id,
                analytical_readiness_id=readiness_id,
                requested_analytical_level=OrchestrationAnalyticalLevel.STATISTICAL,
                records=[{"value": {"invalid": "numeric-input"}}],
                parameters={"deviation_threshold": 3.5},
                execution_type=ExecutionType.CALCULATION,
                correlation_id=f"statistical-invalid-{uuid4()}",
                idempotency_key=f"statistical-invalid-{uuid4()}",
            ),
            actor,
        )
    assert captured.value.code == "INVALID_ENGINE_INPUT"
