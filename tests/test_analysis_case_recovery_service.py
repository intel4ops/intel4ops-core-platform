from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.models.analysis_case import AnalysisCaseAction
from app.models.entities import Finding, Organization
from app.schemas.contracts import OrganizationCreate
from app.services.analysis_case_recovery_service import (
    AnalysisCaseRecoveryServiceError,
    analysis_case_recovery_service,
)
from app.services.analysis_case_service import analysis_case_service
from app.services.organization_service import OrganizationService


def _organization(db: Session, slug: str) -> Organization:
    return OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug.title(), slug=slug, country_code="US", default_currency="USD", timezone="UTC"
        ),
    )


def test_verified_value_rejected_without_evidence(db: Session) -> None:
    org = _organization(db, "recovery-no-evidence")
    with pytest.raises(AnalysisCaseRecoveryServiceError) as excinfo:
        analysis_case_recovery_service.upsert(
            db,
            org.id,
            uuid4(),
            uuid4(),
            uuid4(),
            baseline_condition="baseline",
            intervention_summary="fixed the seal",
            recovery_status="verified",
            observed_post_condition=None,
            observed_value=None,
            estimated_value=None,
            verified_value=100.0,
            currency_detail=None,
            evidence_json=None,
        )
    assert excinfo.value.code == "verification_evidence_required"


def test_verified_value_rejected_when_status_is_not_verified(db: Session) -> None:
    org = _organization(db, "recovery-wrong-status")
    with pytest.raises(AnalysisCaseRecoveryServiceError) as excinfo:
        analysis_case_recovery_service.upsert(
            db,
            org.id,
            uuid4(),
            uuid4(),
            uuid4(),
            baseline_condition="baseline",
            intervention_summary="fixed the seal",
            recovery_status="in_progress",
            observed_post_condition=None,
            observed_value=None,
            estimated_value=None,
            verified_value=100.0,
            currency_detail=None,
            evidence_json={"proof": "before/after photos"},
        )
    assert excinfo.value.code == "verification_not_eligible"


def test_verified_value_accepted_with_status_and_evidence(db: Session) -> None:
    org = _organization(db, "recovery-happy-path")
    finding = Finding(
        organization_id=org.id,
        rule_id="XDOM-A-ASSET-FAILURE-LOST-ACTIVITY",
        title="Test finding",
        summary="Test finding summary",
        domain="maintenance",
        governance_tier="GOVERNED",
    )
    db.add(finding)
    db.flush()
    case = analysis_case_service.create(db, org.id, "Recovery Test Case", "single", uuid4())
    action = AnalysisCaseAction(
        organization_id=org.id,
        analysis_case_id=case.id,
        title="Fix the seal",
        status="in_progress",
        created_by_user_id=uuid4(),
    )
    db.add(action)
    db.flush()
    record = analysis_case_recovery_service.upsert(
        db,
        org.id,
        case.id,
        action.id,
        finding.id,
        baseline_condition="baseline",
        intervention_summary="fixed the seal",
        recovery_status="verified",
        observed_post_condition={"status": "resolved"},
        observed_value=None,
        estimated_value=None,
        verified_value=100.0,
        currency_detail={"verified": {"currency": "XOF", "currency_status": "confirmed"}},
        evidence_json={"proof": "before/after photos"},
    )
    assert record.verified_value == 100.0
    assert record.recovery_status == "verified"

    # completing an action does NOT retroactively mark value verified --
    # a caller must explicitly go through the guarded path again.
    fetched = analysis_case_recovery_service.get(db, org.id, action.id, finding.id)
    assert fetched is not None
    assert fetched.verified_value == 100.0
