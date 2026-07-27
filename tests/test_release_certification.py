from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.validation.certification import (
    CertificationDecision,
    CertificationReport,
    GateDefinition,
    GateResult,
    GateStatus,
    ReleaseGateEvaluator,
    Waiver,
    evidence_hash,
    require_production_eligible_artifact,
    validate_artifact_transition,
    write_certification_reports,
)


def result(code: str, status: GateStatus) -> GateResult:
    return GateResult(
        code=code,
        status=status,
        summary=f"{code} {status}",
        evidence_hash=evidence_hash({"code": code, "status": status}),
    )


def test_all_gates_pass_and_unrun_or_nonwaivable_failure_blocks() -> None:
    definitions = (
        GateDefinition(code="SECURITY", waivable=False),
        GateDefinition(code="OBSERVABILITY", waivable=True),
    )
    evaluator = ReleaseGateEvaluator()
    assert (
        evaluator.evaluate(
            definitions,
            (result("SECURITY", GateStatus.PASSED), result("OBSERVABILITY", GateStatus.PASSED)),
        )[0]
        is CertificationDecision.CERTIFIED
    )
    assert evaluator.evaluate(definitions, (result("SECURITY", GateStatus.PASSED),))[0] is (
        CertificationDecision.BLOCKED
    )
    assert (
        evaluator.evaluate(
            definitions,
            (result("SECURITY", GateStatus.FAILED), result("OBSERVABILITY", GateStatus.PASSED)),
        )[0]
        is CertificationDecision.REJECTED
    )


def test_only_eligible_approved_unexpired_waiver_is_conditional() -> None:
    now = datetime(2026, 7, 27, tzinfo=UTC)
    definition = (GateDefinition(code="OBSERVABILITY", waivable=True),)
    failed = (result("OBSERVABILITY", GateStatus.FAILED),)
    waiver = Waiver(
        gate_code="OBSERVABILITY",
        approved=True,
        expires_at=now + timedelta(days=1),
        justification="Temporary collector outage",
        compensating_control="Manual evidence review enabled",
    )
    decision, waived = ReleaseGateEvaluator().evaluate(definition, failed, (waiver,), now=now)
    assert decision is CertificationDecision.CONDITIONALLY_CERTIFIED
    assert waived == ("OBSERVABILITY",)
    expired = waiver.model_copy(update={"expires_at": now - timedelta(seconds=1)})
    assert ReleaseGateEvaluator().evaluate(definition, failed, (expired,), now=now)[0] is (
        CertificationDecision.REJECTED
    )


def test_artifact_governance_requires_active_immutable_version() -> None:
    validate_artifact_transition("draft", "under_review")
    validate_artifact_transition("approved", "active")
    require_production_eligible_artifact("active")
    with pytest.raises(ValueError, match="Invalid analytical artifact transition"):
        validate_artifact_transition("draft", "active")
    for status in ("draft", "suspended", "retired"):
        with pytest.raises(PermissionError, match="cannot execute"):
            require_production_eligible_artifact(status)


def test_reports_reference_exact_commit_and_have_integrity_hash(tmp_path: Path) -> None:
    gate = result("SECURITY", GateStatus.PASSED)
    report = CertificationReport(
        commit_sha="abcdef1234567890",
        branch="feature/wp-2-20-release-certification",
        migration_head="20260727_0020",
        environment="test",
        decision=CertificationDecision.CERTIFIED,
        gate_results=(gate,),
        waived_gates=(),
        generated_at=datetime(2026, 7, 27, tzinfo=UTC),
    )
    json_path, markdown_path = write_certification_reports(report, tmp_path)
    assert '"commit_sha": "abcdef1234567890"' in json_path.read_text(encoding="utf-8")
    assert '"report_hash": ""' not in json_path.read_text(encoding="utf-8")
    assert "`abcdef1234567890`" in markdown_path.read_text(encoding="utf-8")
