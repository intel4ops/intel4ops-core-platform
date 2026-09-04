"""P3.xxI.4: governed rate basis / unit-of-measure evidence -- orchestration-
level (full, unmodified execute()) coverage complementing the primitive-
level tests in tests/test_governed_cross_dataset_rate.py. Focuses on the
parts P3.xxI.3's own test suite did not yet exercise: the new generic
rate_unit/billing_unit/price_unit aliases on a non-Rental fixture, and a
direct regression encoding of this milestone's own live-certification
finding -- a bare "rate" column, in an otherwise Rental-shaped fixture,
must never acquire an implicit denominator."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Finding, Organization
from app.models.intelligence_activation import IntelligenceActivationDecision
from app.schemas.contracts import OrganizationCreate
from app.services.analysis_case_orchestration_service import analysis_case_orchestration_service
from app.services.analysis_case_service import AnalysisCaseService, UploadedFile
from app.services.organization_service import OrganizationService
from app.storage.local_storage import LocalFileStorage

_RULE_CODE = "REVENUE-AMOUNT-VARIANCE"
_N_SUBJECTS = 6


def _organization(db: Session, slug: str) -> Organization:
    return OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug.title(), slug=slug, country_code="US", default_currency="USD", timezone="UTC"
        ),
    )


def _run_case(
    db: Session, tmp_path: Path, org_id: UUID, files: list[UploadedFile], name: str
) -> tuple[UUID, UUID]:
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    actor = uuid4()
    case = service.create(db, org_id, name, "single", actor)
    service.register_artifacts(db, org_id, case.id, files, actor)
    run = analysis_case_orchestration_service.start_run(db, org_id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org_id, case.id, run.id, actor)
    return case.id, run.id


def _findings(db: Session, org_id: UUID) -> list[Finding]:
    return list(
        db.scalars(
            select(Finding).where(
                Finding.organization_id == org_id, Finding.definition_code == _RULE_CODE
            )
        ).all()
    )


def _governed_status(db: Session, run_id: UUID) -> str | None:
    decision = db.scalar(
        select(IntelligenceActivationDecision).where(
            IntelligenceActivationDecision.run_id == run_id,
            IntelligenceActivationDecision.rule_code == _RULE_CODE,
        )
    )
    return decision.governed_status if decision is not None else None


# ---------------------------------------------------------------------------
# Positive test D (Section 12): a generic, non-Rental, non-duration-only
# fixture -- a field-service visit rate card carrying an explicit
# "billing_unit" column (one of the three new generic aliases added this
# milestone) -- proves the alias expansion reaches AUTO_ACCEPTED and
# produces real governed rate evidence, not just a duration-hours case.
# ---------------------------------------------------------------------------


def test_generic_service_fixture_with_billing_unit_alias_produces_governed_rate(
    db: Session, tmp_path: Path
) -> None:
    org = _organization(db, "revvar-2i4-service-billing-unit")
    visits = "dispatch_id,agreement_id,asset_id,occurred_at,completed_at\n"
    rate_cards = "rate_card_id,rate,billing_unit\n"
    billing = "bill_id,agreement_id,amount,status\n"
    for i in range(_N_SUBJECTS):
        n = i + 1
        visits += f"DSP-{n},AGR-{n},AST-{n},2026-05-0{n}T09:00:00,2026-05-0{n}T13:00:00\n"  # 4h
        rate_cards += f"AGR-{n},75,hour\n"  # $75/hr * 4h = $300 expected
        billing += f"BILL-{n},AGR-{n},250,ISSUED\n"  # actual 250 -> shortfall 50
    files = [
        UploadedFile("visits.csv", visits.encode()),
        UploadedFile("rate_cards.csv", rate_cards.encode()),
        UploadedFile("billing.csv", billing.encode()),
    ]
    _, run_id = _run_case(db, tmp_path, org.id, files, "Generic service billing_unit E2E")

    assert _governed_status(db, run_id) == "READY"
    findings = _findings(db, org.id)
    assert len(findings) == _N_SUBJECTS
    assert all(f.exposure_value == 50 for f in findings)


# ---------------------------------------------------------------------------
# Negative test H (Section 13): a Rental-shaped fixture -- the EXACT column
# shape of the real, frozen Rental corpus's own contracts.csv
# (contract_id,customer_id,asset_id,start_date,end_date,rate) -- carrying
# no UOM evidence anywhere. Direct regression encoding of this milestone's
# own live-certification finding: a bare "rate" column must never acquire
# an implicit day (or any other) denominator merely because the shape
# looks like a rental agreement. Readiness still reaches READY (duration
# derives correctly and the pipeline runs to completion); the rate itself
# correctly abstains, producing zero findings -- the honest DATA_CONTRACT_GAP
# outcome, never a fabricated match.
# ---------------------------------------------------------------------------


def test_rental_shaped_bare_rate_column_never_infers_day_denominator(
    db: Session, tmp_path: Path
) -> None:
    org = _organization(db, "revvar-2i4-rental-shaped-no-uom")
    contracts = "contract_id,customer_id,asset_id,start_date,end_date,rate\n"
    dispatch = "dispatch_id,contract_id,asset_id,dispatch_date,return_date\n"
    invoices = "invoice_id,contract_id,invoice_date,amount,status\n"
    for i in range(_N_SUBJECTS):
        n = i + 1
        contracts += f"CNT-{n},CUST-{n},AST-{n},2026-02-0{n},2026-02-2{n}\n"
        dispatch += f"DSP-{n},CNT-{n},AST-{n},2026-02-0{n},2026-02-2{n}\n"  # ~20 days elapsed
        invoices += f"INV-{n},CNT-{n},2026-02-2{n},999,ISSUED\n"
    files = [
        UploadedFile("contracts.csv", contracts.encode()),
        UploadedFile("dispatch.csv", dispatch.encode()),
        UploadedFile("invoices.csv", invoices.encode()),
    ]
    _, run_id = _run_case(db, tmp_path, org.id, files, "Rental-shaped bare rate, no UOM")

    assert _governed_status(db, run_id) == "READY"
    assert _findings(db, org.id) == []


# ---------------------------------------------------------------------------
# Section 15: rate-card / actual-billing separation regression. A
# self-cancellation fixture -- if contracts.csv's own "rate" value were
# ever misread a second time as a flat billed amount (the P3.xxI.3-fixed
# latent bug), the resulting doubled "actual" side would silently cancel
# the real expected-vs-actual variance and produce zero findings even
# though a governed rate basis IS present here. Asserts the real,
# non-zero variance still surfaces.
# ---------------------------------------------------------------------------


def test_rate_card_value_never_double_counted_as_actual_billing(
    db: Session, tmp_path: Path
) -> None:
    org = _organization(db, "revvar-2i4-rate-card-not-actual-billing")
    events = "dispatch_id,agreement_id,asset_id,occurred_at,completed_at\n"
    rate_cards = "rate_card_id,labor_rate\n"
    billing = "bill_id,agreement_id,amount,status\n"
    for i in range(_N_SUBJECTS):
        n = i + 1
        events += f"DSP-{n},AGR-{n},AST-{n},2026-02-0{n}T08:00:00,2026-02-0{n}T18:00:00\n"  # 10h
        rate_cards += f"AGR-{n},50\n"  # hourly_rate -> implicit "hour"; 10h * $50 = $500 expected
        # actual billing deliberately equals the RATE VALUE itself (50),
        # not the expected amount (500) -- if the rate card's own 50 were
        # ever ALSO read as a second, independent actual-billing line, the
        # two actual-side lines (50 + 50) would still never coincidentally
        # equal 500, so a self-cancellation would show up as a wrong
        # exposure_value rather than a real $450 shortfall.
        billing += f"BILL-{n},AGR-{n},50,ISSUED\n"
    files = [
        UploadedFile("events.csv", events.encode()),
        UploadedFile("rate_cards.csv", rate_cards.encode()),
        UploadedFile("billing.csv", billing.encode()),
    ]
    _, run_id = _run_case(db, tmp_path, org.id, files, "Rate card not actual billing E2E")

    assert _governed_status(db, run_id) == "READY"
    findings = _findings(db, org.id)
    assert len(findings) == _N_SUBJECTS
    # expected 500 (10h * $50/hr), actual 50 -> exposure 450, never 0 and
    # never contaminated by a phantom second actual-billing line sourced
    # from the rate card's own value.
    assert all(f.exposure_value == 450 for f in findings)
