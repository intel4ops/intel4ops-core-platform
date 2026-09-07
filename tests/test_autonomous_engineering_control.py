from pathlib import Path
from uuid import uuid4

from app.schemas.autonomous_engineering_control import AutonomousEngineeringPolicyRequest
from app.storage.local_storage import LocalFileStorage
from app.validation_program.autonomous_engineering_control import AutonomousEngineeringControlService


def _service(tmp_path: Path) -> AutonomousEngineeringControlService:
    return AutonomousEngineeringControlService(LocalFileStorage(str(tmp_path / "storage")))


def test_routine_implementation_auto_executes(tmp_path: Path) -> None:
    decision = _service(tmp_path).evaluate(
        uuid4(),
        AutonomousEngineeringPolicyRequest(
            risk_class="R1",
            lifecycle_stage="implementation",
        ),
    )
    assert decision.decision == "AUTO_EXECUTE"
    assert decision.owner_required is False
    assert decision.auto_execute_allowed is True


def test_verified_green_candidate_auto_merges(tmp_path: Path) -> None:
    decision = _service(tmp_path).evaluate(
        uuid4(),
        AutonomousEngineeringPolicyRequest(
            risk_class="R2",
            lifecycle_stage="verified_candidate",
            verification_decision="VERIFIED_IMPROVEMENT",
            quality_gate_green=True,
            exact_candidate_bound=True,
        ),
    )
    assert decision.decision == "AUTO_MERGE"
    assert decision.owner_required is False
    assert decision.auto_merge_allowed is True


def test_staging_exact_merge_commit_auto_deploys(tmp_path: Path) -> None:
    decision = _service(tmp_path).evaluate(
        uuid4(),
        AutonomousEngineeringPolicyRequest(
            risk_class="R1",
            lifecycle_stage="merged_release_candidate",
            quality_gate_green=True,
            target_environment="staging",
            exact_merge_commit_bound=True,
        ),
    )
    assert decision.decision == "AUTO_DEPLOY_STAGING"
    assert decision.auto_deploy_staging_allowed is True
    assert decision.production_deploy_allowed is False


def test_production_remains_owner_gated(tmp_path: Path) -> None:
    decision = _service(tmp_path).evaluate(
        uuid4(),
        AutonomousEngineeringPolicyRequest(
            risk_class="R1",
            lifecycle_stage="deployment",
            quality_gate_green=True,
            target_environment="production",
            exact_merge_commit_bound=True,
        ),
    )
    assert decision.decision == "OWNER_APPROVAL_PRODUCTION"
    assert decision.owner_required is True
    assert decision.production_deploy_allowed is False


def test_r3_or_protected_boundary_requires_owner(tmp_path: Path) -> None:
    r3 = _service(tmp_path).evaluate(
        uuid4(),
        AutonomousEngineeringPolicyRequest(
            risk_class="R3",
            lifecycle_stage="implementation",
        ),
    )
    boundary = _service(tmp_path).evaluate(
        uuid4(),
        AutonomousEngineeringPolicyRequest(
            risk_class="R1",
            lifecycle_stage="verified_candidate",
            verification_decision="VERIFIED_IMPROVEMENT",
            quality_gate_green=True,
            exact_candidate_bound=True,
            truth_isolation_change=True,
        ),
    )
    assert r3.decision == "OWNER_APPROVAL_R3"
    assert boundary.decision == "OWNER_APPROVAL_R3"
    assert boundary.auto_merge_allowed is False


def test_regression_blocks_autonomy(tmp_path: Path) -> None:
    decision = _service(tmp_path).evaluate(
        uuid4(),
        AutonomousEngineeringPolicyRequest(
            risk_class="R1",
            lifecycle_stage="verified_candidate",
            verification_decision="REGRESSION",
            quality_gate_green=True,
            exact_candidate_bound=True,
        ),
    )
    assert decision.decision == "ESCALATE_ON_REGRESSION"
    assert decision.owner_required is True
    assert decision.auto_merge_allowed is False
