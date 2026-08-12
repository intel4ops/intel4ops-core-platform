from uuid import uuid4

import pytest
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import Finding, Organization, RecoveryAction
from app.models.raw_lineage import ProcessingRun
from app.schemas.contracts import OrganizationCreate
from app.services.organization_service import OrganizationService


def organization(db: Session, slug: str) -> Organization:
    return OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug,
            slug=slug,
            country_code="US",
            default_currency="USD",
            timezone="UTC",
        ),
    )


def finding(db: Session, org: Organization) -> Finding:
    row = Finding(
        organization_id=org.id,
        governance_tier="LIGHTWEIGHT",
        rule_id="constraint-test",
        title="Constraint test",
        summary="Database enforcement",
        domain="quality",
        severity="medium",
        status="open",
    )
    db.add(row)
    db.commit()
    return row


@pytest.mark.parametrize(
    ("model", "field", "invalid"),
    [
        (Organization, "status", "unknown"),
        (Finding, "severity", "urgent"),
        (Finding, "status", "unknown"),
        (Finding, "governance_tier", "UNKNOWN"),
        (RecoveryAction, "status", "unknown"),
    ],
)
def test_foundation_state_checks_reject_invalid_values(
    db: Session, model: type[object], field: str, invalid: str
) -> None:
    org = organization(db, f"check-{model.__name__.lower()}-{field}".replace("_", "-"))
    if model is Organization:
        row_id = org.id
    else:
        finding_row = finding(db, org)
        if model is Finding:
            row_id = finding_row.id
        else:
            action = RecoveryAction(
                organization_id=org.id,
                finding_id=finding_row.id,
                title="Recover",
                owner="owner",
            )
            db.add(action)
            db.commit()
            row_id = action.id
    with pytest.raises(IntegrityError):
        db.execute(update(model).where(model.id == row_id).values({field: invalid}))  # type: ignore[attr-defined]
        db.commit()
    db.rollback()


def test_processing_run_data_anchor_is_database_enforced(db: Session) -> None:
    org = organization(db, "check-processing-anchor")
    db.add(
        ProcessingRun(
            organization_id=org.id,
            run_type="parsing",
            executor_type="worker",
            created_by_user_id=uuid4(),
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
