"""P3.xxE.2 sections 21/37.7 (spec H/I): a provider timeout, malformed
output, or any other failure must never fail dataset interpretation or the
AnalysisCase run -- deterministic interpretation always completes."""

from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest
from sqlalchemy.orm import Session

from app.models.analysis_case import AnalysisCaseRunStatus
from app.schemas.contracts import OrganizationCreate
from app.semantic.interpreter import interpret_dataset
from app.semantic.provider import SemanticInterpretationRequest, SemanticInterpretationResponse
from app.services.analysis_case_orchestration_service import analysis_case_orchestration_service
from app.services.analysis_case_service import AnalysisCaseService, UploadedFile
from app.services.organization_service import OrganizationService
from app.storage.local_storage import LocalFileStorage

WORK_ORDER_CSV = b"work_order_id,technician_id,status\nWO-1,T-1,open\nWO-2,T-2,closed\n"


class _TimeoutProvider:
    provider_name = "flaky"
    provider_version = "1.0"

    def propose(self, request: SemanticInterpretationRequest) -> SemanticInterpretationResponse:
        raise TimeoutError("provider timed out")


class _MalformedProvider:
    provider_name = "flaky"
    provider_version = "1.0"

    def propose(self, request: SemanticInterpretationRequest) -> SemanticInterpretationResponse:
        raise ValueError("malformed response could not be parsed")


class _CrashingProvider:
    provider_name = "flaky"
    provider_version = "1.0"

    def propose(self, request: SemanticInterpretationRequest) -> SemanticInterpretationResponse:
        raise RuntimeError("unexpected provider crash")


def _work_order_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "work_order_id": ["WO-1", "WO-2"],
            "technician_id": ["T-1", "T-2"],
            "status": ["open", "closed"],
        }
    )


# H. Provider timeout does not fail interpretation.
@pytest.mark.parametrize("provider_cls", [_TimeoutProvider, _MalformedProvider, _CrashingProvider])
def test_interpret_dataset_degrades_to_deterministic_only_on_provider_failure(
    provider_cls: type,
) -> None:
    result = interpret_dataset("ds-1", "work_orders.csv", _work_order_df(), provider=provider_cls())
    assert len(result.field_decisions) == 3
    work_order_decision = next(
        d for d in result.field_decisions if d.source_field == "work_order_id"
    )
    assert work_order_decision.selected_concept == "work_order_id"
    assert work_order_decision.ai_provenance is None


# H/I, end-to-end: a provider failure mid-run still lets the AnalysisCase
# complete normally, matching the P3.xxE.1 precedent
# (test_a_semantic_interpretation_failure_never_fails_the_run) but at the
# provider layer specifically rather than the whole semantic stage.
def test_provider_failure_never_fails_the_analysis_case_run(
    db: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.services.analysis_case_orchestration_service as orchestration_module

    monkeypatch.setattr(
        orchestration_module,
        "select_semantic_reasoning_provider",
        lambda settings: _CrashingProvider(),
    )

    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    org = OrganizationService().create(
        db,
        OrganizationCreate(
            name="Provider Failure Case",
            slug="provider-failure-case",
            country_code="US",
            default_currency="USD",
            timezone="UTC",
        ),
    )
    actor = uuid4()
    case = service.create(db, org.id, "Case", "single", actor)
    service.register_artifacts(
        db, org.id, case.id, [UploadedFile("work_orders.csv", WORK_ORDER_CSV)], actor
    )
    run = analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org.id, case.id, run.id, actor)
    db.refresh(run)

    assert run.status in {
        AnalysisCaseRunStatus.COMPLETED.value,
        AnalysisCaseRunStatus.PARTIAL.value,
        AnalysisCaseRunStatus.REVIEW_REQUIRED.value,
    }
    assert run.status != AnalysisCaseRunStatus.FAILED.value
