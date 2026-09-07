"""AGENTIC-CONTROL-001 Phase G/P: structured worker-output validation.
Malformed output must never be silently accepted."""

import pytest
from pydantic import ValidationError

from app.schemas.agent_jobs import WorkerStructuredResult

VALID = {
    "primary_gap_class": "DATA_CONTRACT_GAP",
    "secondary_gap_classes": [],
    "confidence": 94,
    "summary": "Missing rate basis on contracts.csv",
    "evidence_refs": ["ref-1"],
    "fp_risk": "low",
    "architecture_impact": False,
    "policy_dependency": False,
    "data_contract_dependency": True,
    "recommended_action": "No action -- data-contract dead end",
    "escalate": False,
    "escalation_reason": None,
}


def test_valid_structured_result_parses() -> None:
    result = WorkerStructuredResult.model_validate(VALID)
    assert result.confidence == 94
    assert result.primary_gap_class == "DATA_CONTRACT_GAP"


def test_missing_confidence_is_rejected() -> None:
    payload = dict(VALID)
    del payload["confidence"]
    with pytest.raises(ValidationError):
        WorkerStructuredResult.model_validate(payload)


def test_confidence_out_of_range_is_rejected() -> None:
    payload = dict(VALID, confidence=101)
    with pytest.raises(ValidationError):
        WorkerStructuredResult.model_validate(payload)
    payload = dict(VALID, confidence=-1)
    with pytest.raises(ValidationError):
        WorkerStructuredResult.model_validate(payload)


def test_unknown_gap_class_is_rejected() -> None:
    payload = dict(VALID, primary_gap_class="NOT_A_REAL_GAP_CLASS")
    with pytest.raises(ValidationError):
        WorkerStructuredResult.model_validate(payload)


def test_invalid_fp_risk_value_is_rejected() -> None:
    payload = dict(VALID, fp_risk="catastrophic")
    with pytest.raises(ValidationError):
        WorkerStructuredResult.model_validate(payload)


def test_escalate_true_requires_a_reason() -> None:
    payload = dict(VALID, escalate=True, escalation_reason=None)
    with pytest.raises(ValidationError):
        WorkerStructuredResult.model_validate(payload)

    payload = dict(VALID, escalate=True, escalation_reason="confidence too low")
    result = WorkerStructuredResult.model_validate(payload)
    assert result.escalate is True


def test_empty_summary_is_rejected() -> None:
    payload = dict(VALID, summary="")
    with pytest.raises(ValidationError):
        WorkerStructuredResult.model_validate(payload)
