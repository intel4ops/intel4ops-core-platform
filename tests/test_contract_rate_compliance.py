"""P3.xxI.5A CONTRACT-RATE-COMPLIANCE mechanical and safety contract."""

from pathlib import Path
from uuid import UUID, uuid4

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Finding, Organization
from app.models.findings import FindingEvidenceBundle, FindingEvidenceItem
from app.models.intelligence_activation import IntelligenceActivationDecision
from app.models.semantic import SemanticInterpretationDecision
from app.models.trust import (
    AnalyticalLevel,
    AnalyticalReadinessDecision,
    ReadinessStatus,
    TrustAssessment,
)
from app.schemas.contracts import OrganizationCreate
from app.schemas.findings import FindingType, FindingValueType
from app.services.analysis_case_orchestration_service import analysis_case_orchestration_service
from app.services.analysis_case_service import AnalysisCaseService, UploadedFile
from app.services.contract_rate_compliance_service import (
    AppliedRateDatasetFields,
    derive_actual_applied_rates,
    run_contract_rate_compliance,
)
from app.services.governed_cross_dataset_rate import RateDatasetFields
from app.services.organization_service import OrganizationService
from app.storage.local_storage import LocalFileStorage


def _bootstrap_context(db: Session, tmp_path: Path, slug: str) -> tuple[UUID, UUID, UUID, UUID]:
    org: Organization = OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug.title(), slug=slug, country_code="US", default_currency="USD", timezone="UTC"
        ),
    )
    rows = "asset_id,work_order_id,failure_code,downtime_hours,repair_cost,event_date\n"
    for index in range(5):
        rows += f"A-{index + 1},WO-{index + 1},brake,48,10000,2026-08-{index + 1:02d}T08:00:00\n"
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    actor = uuid4()
    case = service.create(db, org.id, "Rate compliance bootstrap", "single", actor)
    service.register_artifacts(
        db, org.id, case.id, [UploadedFile("maintenance_events.csv", rows.encode())], actor
    )
    run = analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org.id, case.id, run.id, actor)
    readiness = db.scalar(
        select(AnalyticalReadinessDecision).where(
            AnalyticalReadinessDecision.organization_id == org.id,
            AnalyticalReadinessDecision.analytical_level == AnalyticalLevel.ARITHMETIC.value,
            AnalyticalReadinessDecision.readiness_status.in_(
                [ReadinessStatus.READY.value, ReadinessStatus.READY_WITH_WARNINGS.value]
            ),
        )
    )
    assert readiness is not None
    assessment = db.get(TrustAssessment, readiness.trust_assessment_id)
    assert assessment is not None
    return org.id, actor, readiness.trust_assessment_id, assessment.dataset_id


def _actual(
    dataset_id: UUID,
    trust_id: UUID,
    rows: list[dict[str, object]],
    *,
    actual_rate_field: str | None = "billed_rate",
    unit_field: str | None = "rate_unit",
    currency_field: str | None = "currency",
) -> AppliedRateDatasetFields:
    return AppliedRateDatasetFields(
        dataset_id=dataset_id,
        dataset_label="service_charges.csv",
        dataframe=pd.DataFrame(rows),
        trust_assessment_id=trust_id,
        subject_id_field="service_id",
        actual_rate_field=actual_rate_field,
        contract_id_field="agreement_id" if any("agreement_id" in row for row in rows) else None,
        unit_field=unit_field,
        currency_field=currency_field,
        event_timestamp_field="service_at" if any("service_at" in row for row in rows) else None,
        quantity_field="quantity" if any("quantity" in row for row in rows) else None,
    )


def _rates(dataset_id: UUID, rows: list[dict[str, object]]) -> RateDatasetFields:
    return RateDatasetFields(
        dataset_id=dataset_id,
        dataset_label="rate_schedule.csv",
        dataframe=pd.DataFrame(rows),
        contract_id_field="agreement_id",
        rate_field="contract_rate",
        effective_from_field=(
            "effective_from" if any("effective_from" in row for row in rows) else None
        ),
        effective_to_field="effective_to" if any("effective_to" in row for row in rows) else None,
        unit_field="rate_unit" if any("rate_unit" in row for row in rows) else None,
        currency_field="currency" if any("currency" in row for row in rows) else None,
    )


def _row(
    subject: str = "SVC-1",
    contract: str | None = "AGR-1",
    actual: float = 120,
    unit: str = "hour",
    currency: str = "USD",
    quantity: float | None = 10,
    at: str | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "service_id": subject,
        "billed_rate": actual,
        "rate_unit": unit,
        "currency": currency,
    }
    if contract is not None:
        row["agreement_id"] = contract
    if quantity is not None:
        row["quantity"] = quantity
    if at is not None:
        row["service_at"] = at
    return row


def _rate(
    contract: str = "AGR-1",
    amount: float = 100,
    unit: str = "hour",
    currency: str = "USD",
    start: str | None = None,
    end: str | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "agreement_id": contract,
        "contract_rate": amount,
        "rate_unit": unit,
        "currency": currency,
    }
    if start is not None:
        row["effective_from"] = start
    if end is not None:
        row["effective_to"] = end
    return row


def _run(
    db: Session,
    tmp_path: Path,
    slug: str,
    actual_rows: list[dict[str, object]],
    rate_rows: list[dict[str, object]],
    *,
    actual_rate_field: str | None = "billed_rate",
    unit_field: str | None = "rate_unit",
    currency_field: str | None = "currency",
    eligible: set[str] | None = None,
    subject_type: str = "work_order",
) -> list[Finding]:
    org_id, actor, trust_id, dataset_id = _bootstrap_context(db, tmp_path, slug)
    return run_contract_rate_compliance(
        db,
        org_id,
        [
            _actual(
                dataset_id,
                trust_id,
                actual_rows,
                actual_rate_field=actual_rate_field,
                unit_field=unit_field,
                currency_field=currency_field,
            )
        ],
        eligible or {str(row["service_id"]) for row in actual_rows},
        actor,
        [_rates(dataset_id, rate_rows)],
        subject_entity_type=subject_type,
    )


def test_a_actual_120_per_hour_vs_contract_100_per_hour_finds_mismatch(
    db: Session, tmp_path: Path
) -> None:
    findings = _run(db, tmp_path, "rate-comp-a", [_row()], [_rate()])
    assert len(findings) == 1
    finding = findings[0]
    assert finding.finding_type == FindingType.RECONCILIATION.value
    assert finding.exposure_value == 200
    assert finding.exposure_value_type == FindingValueType.CURRENCY.value
    assert finding.exposure_currency == "USD"
    assert finding.definition_code == "CONTRACT-RATE-COMPLIANCE"

    evidence = list(
        db.scalars(
            select(FindingEvidenceItem)
            .join(
                FindingEvidenceBundle,
                FindingEvidenceBundle.id == FindingEvidenceItem.evidence_bundle_id,
            )
            .where(FindingEvidenceBundle.finding_id == finding.id)
        ).all()
    )
    reference_types = {item.reference_type for item in evidence}
    assert "actual_applied_rate_line" in reference_types
    assert "applicable_contract_rate_line" in reference_types
    assert "rate_comparison" in reference_types


def test_b_equal_actual_and_contract_rate_produces_no_finding(db: Session, tmp_path: Path) -> None:
    assert _run(db, tmp_path, "rate-comp-b", [_row(actual=100)], [_rate()]) == []


def test_c_temporally_applicable_contract_rate_is_selected(db: Session, tmp_path: Path) -> None:
    findings = _run(
        db,
        tmp_path,
        "rate-comp-c",
        [_row(actual=120, at="2026-06-01")],
        [
            _rate(amount=80, start="2025-01-01", end="2025-12-31"),
            _rate(amount=100, start="2026-01-01", end="2026-12-31"),
        ],
    )
    assert len(findings) == 1
    assert "applicable contract rate 100" in findings[0].summary.lower()


def test_d_generic_equipment_service_fixture_is_not_domain_specific(
    db: Session, tmp_path: Path
) -> None:
    findings = _run(
        db,
        tmp_path,
        "rate-comp-d-equipment",
        [_row(subject="EQUIP-SVC-9", actual=75, quantity=4)],
        [_rate(amount=70)],
    )
    assert len(findings) == 1
    entities = findings[0].entities_json
    assert entities is not None
    assert entities[0]["canonical_key"] == "EQUIP-SVC-9"


def test_e_multiple_subjects_have_distinct_finding_identity(db: Session, tmp_path: Path) -> None:
    findings = _run(
        db,
        tmp_path,
        "rate-comp-e",
        [_row(subject="SVC-1"), _row(subject="SVC-2")],
        [_rate()],
    )
    assert len(findings) == 2
    assert len({finding.finding_code for finding in findings}) == 2


def test_f_bare_rate_without_uom_abstains(db: Session, tmp_path: Path) -> None:
    assert (
        _run(
            db,
            tmp_path,
            "rate-comp-f",
            [_row()],
            [_rate()],
            unit_field=None,
        )
        == []
    )


def test_g_different_currencies_abstain(db: Session, tmp_path: Path) -> None:
    assert _run(db, tmp_path, "rate-comp-g", [_row(currency="EUR")], [_rate()]) == []


def test_h_different_rate_bases_abstain(db: Session, tmp_path: Path) -> None:
    assert _run(db, tmp_path, "rate-comp-h", [_row(unit="day")], [_rate(unit="hour")]) == []


def test_i_multiple_applicable_contract_rates_abstain(db: Session, tmp_path: Path) -> None:
    assert _run(db, tmp_path, "rate-comp-i", [_row()], [_rate(), _rate(amount=90)]) == []


def test_j_ambiguous_or_unresolved_actual_rate_abstains(db: Session, tmp_path: Path) -> None:
    assert (
        _run(
            db,
            tmp_path,
            "rate-comp-j",
            [_row()],
            [_rate()],
            actual_rate_field=None,
        )
        == []
    )


def test_k_missing_contract_linkage_abstains(db: Session, tmp_path: Path) -> None:
    assert _run(db, tmp_path, "rate-comp-k", [_row(contract=None)], [_rate()]) == []


def test_l_rate_card_value_is_never_actual_billed_rate(db: Session, tmp_path: Path) -> None:
    assert (
        _run(
            db,
            tmp_path,
            "rate-comp-l",
            [_row()],
            [_rate()],
            actual_rate_field=None,
        )
        == []
    )


def test_missing_quantity_preserves_rate_finding_without_fabricated_exposure(
    db: Session, tmp_path: Path
) -> None:
    findings = _run(
        db,
        tmp_path,
        "rate-comp-no-quantity",
        [_row(quantity=None)],
        [_rate()],
    )
    assert len(findings) == 1
    assert findings[0].exposure_value is None
    assert findings[0].exposure_currency is None


def test_explicit_zero_actual_rate_is_not_treated_as_missing(db: Session, tmp_path: Path) -> None:
    findings = _run(db, tmp_path, "rate-comp-zero", [_row(actual=0)], [_rate()])
    assert len(findings) == 1
    assert findings[0].exposure_value == 1000


def test_contract_can_be_the_governed_subject(db: Session, tmp_path: Path) -> None:
    findings = _run(
        db,
        tmp_path,
        "rate-comp-contract-subject",
        [_row(subject="AGR-1", contract=None)],
        [_rate()],
        subject_type="contract",
    )
    assert len(findings) == 1
    entities = findings[0].entities_json
    assert entities is not None
    assert entities[0]["entity_type"] == "contract"


def test_orchestration_generic_service_rate_comparison_end_to_end(
    db: Session, tmp_path: Path
) -> None:
    """A generic service engagement reaches governed readiness and publishes
    without any customer, filename, or industry branch."""
    org: Organization = OrganizationService().create(
        db,
        OrganizationCreate(
            name="Generic Service Rate",
            slug="rate-comp-orchestration",
            country_code="US",
            default_currency="USD",
            timezone="UTC",
        ),
    )
    subjects = "work_order_id,contract_id,status,event_date\n"
    charges = (
        "invoice_id,work_order_id,contract_id,billed_rate,rate_unit,currency,event_date,status\n"
    )
    rates = "contract_id,start_date,end_date,hourly_rate,currency\n"
    for index in range(6):
        number = index + 1
        subjects += f"SVC-{number},AGR-{number},CLOSED,2026-06-01\n"
        charges += f"INV-{number},SVC-{number},AGR-{number},120,hour,USD,2026-06-01,ISSUED\n"
        rates += f"AGR-{number},2026-01-01,2026-12-31,100,USD\n"

    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    actor = uuid4()
    case = service.create(db, org.id, "Generic service engagement", "single", actor)
    service.register_artifacts(
        db,
        org.id,
        case.id,
        [
            UploadedFile("service_subjects.csv", subjects.encode()),
            UploadedFile("service_charges.csv", charges.encode()),
            UploadedFile("governed_rates.csv", rates.encode()),
        ],
        actor,
    )
    run = analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org.id, case.id, run.id, actor)

    decision = db.scalar(
        select(IntelligenceActivationDecision).where(
            IntelligenceActivationDecision.run_id == run.id,
            IntelligenceActivationDecision.rule_code == "CONTRACT-RATE-COMPLIANCE",
        )
    )
    semantic_debug = list(
        db.execute(
            select(
                SemanticInterpretationDecision.source_field,
                SemanticInterpretationDecision.selected_concept,
                SemanticInterpretationDecision.confidence,
                SemanticInterpretationDecision.status,
            ).where(SemanticInterpretationDecision.run_id == run.id)
        ).all()
    )
    assert decision is not None
    assert decision.mode == "governed"
    assert decision.governed_status == "READY", semantic_debug
    findings = list(
        db.scalars(
            select(Finding).where(
                Finding.organization_id == org.id,
                Finding.definition_code == "CONTRACT-RATE-COMPLIANCE",
            )
        ).all()
    )
    assert len(findings) == 6, semantic_debug
    assert all(finding.exposure_value is None for finding in findings)


# ---------------------------------------------------------------------------
# P3.xxI.5A-R: derived_actual_applied_rate -- an independent alternative
# evidence path for subjects with no explicit actual_applied_rate column.
# `derived actual rate = (invoice amount - governed non-target component(s))
# / governed target quantity`. Every helper below builds AppliedRateDatasetFields
# directly (mirrors this file's own established style for the explicit-rate
# path) so each test proves one governed safety gate in isolation.
# ---------------------------------------------------------------------------


def _billing(
    dataset_id: UUID,
    trust_id: UUID | None,
    rows: list[dict[str, object]],
    *,
    label: str = "invoices.csv",
    invoice_amount_field: str | None = "invoice_amount",
    currency_field: str | None = "currency",
    contract_id_field: str | None = "agreement_id",
    is_rate_card_shaped: bool = False,
) -> AppliedRateDatasetFields:
    return AppliedRateDatasetFields(
        dataset_id=dataset_id,
        dataset_label=label,
        dataframe=pd.DataFrame(rows),
        trust_assessment_id=trust_id,
        subject_id_field="work_order_id",
        actual_rate_field=None,
        contract_id_field=contract_id_field,
        unit_field=None,
        currency_field=currency_field,
        quantity_field=None,
        invoice_amount_field=invoice_amount_field,
        is_rate_card_shaped=is_rate_card_shaped,
    )


def _quantity(
    dataset_id: UUID,
    rows: list[dict[str, object]],
    *,
    label: str = "labor_entries.csv",
    quantity_field: str | None = "hours",
    unit_field: str | None = None,
    implicit_quantity_unit: str | None = "hour",
) -> AppliedRateDatasetFields:
    return AppliedRateDatasetFields(
        dataset_id=dataset_id,
        dataset_label=label,
        dataframe=pd.DataFrame(rows),
        trust_assessment_id=None,
        subject_id_field="work_order_id",
        actual_rate_field=None,
        contract_id_field=None,
        unit_field=unit_field,
        currency_field=None,
        quantity_field=quantity_field,
        implicit_quantity_unit=implicit_quantity_unit,
    )


def _component(
    dataset_id: UUID,
    rows: list[dict[str, object]],
    *,
    label: str = "parts_usage.csv",
    quantity_field: str | None = "part_quantity",
    component_unit_price_field: str | None = "unit_price",
    currency_field: str | None = "currency",
) -> AppliedRateDatasetFields:
    return AppliedRateDatasetFields(
        dataset_id=dataset_id,
        dataset_label=label,
        dataframe=pd.DataFrame(rows),
        trust_assessment_id=None,
        subject_id_field="work_order_id",
        actual_rate_field=None,
        contract_id_field=None,
        unit_field=None,
        currency_field=currency_field,
        quantity_field=quantity_field,
        component_unit_price_field=component_unit_price_field,
    )


def _billing_row(
    subject: str = "WO-1",
    contract: str | None = "AGR-1",
    amount: float = 1200,
    currency: str | None = "USD",
) -> dict[str, object]:
    row: dict[str, object] = {"work_order_id": subject, "invoice_amount": amount}
    if contract is not None:
        row["agreement_id"] = contract
    if currency is not None:
        row["currency"] = currency
    return row


def _quantity_row(
    subject: str = "WO-1", hours: float | None = 10, unit: str | None = None
) -> dict[str, object]:
    row: dict[str, object] = {"work_order_id": subject}
    if hours is not None:
        row["hours"] = hours
    if unit is not None:
        row["rate_unit"] = unit
    return row


def _component_row(
    subject: str = "WO-1",
    quantity: float | None = 2,
    price: float | None = 100,
    currency: str | None = "USD",
) -> dict[str, object]:
    row: dict[str, object] = {"work_order_id": subject}
    if quantity is not None:
        row["part_quantity"] = quantity
    if price is not None:
        row["unit_price"] = price
    if currency is not None:
        row["currency"] = currency
    return row


def test_derived_a_worked_example_produces_finding(db: Session, tmp_path: Path) -> None:
    """Mission worked example: invoice 1200 - non-target component 200 (2 *
    100) = target amount 1000; 1000 / 10 hours = derived actual rate 100/hr;
    contract rate 90/hr -> variance 10/hr * 10 hours = exposure 100."""
    org_id, actor, trust_id, dataset_id = _bootstrap_context(db, tmp_path, "rate-comp-derived-a")
    findings = run_contract_rate_compliance(
        db,
        org_id,
        [
            _billing(dataset_id, trust_id, [_billing_row(amount=1200)]),
            _quantity(dataset_id, [_quantity_row(hours=10)]),
            _component(dataset_id, [_component_row(quantity=2, price=100)]),
        ],
        {"WO-1"},
        actor,
        [_rates(dataset_id, [_rate(amount=90)])],
    )
    assert len(findings) == 1
    finding = findings[0]
    assert finding.definition_code == "CONTRACT-RATE-COMPLIANCE"
    assert finding.exposure_value == 100
    assert finding.exposure_currency == "USD"


def test_derived_b_actual_equals_contract_no_finding(db: Session, tmp_path: Path) -> None:
    org_id, actor, trust_id, dataset_id = _bootstrap_context(db, tmp_path, "rate-comp-derived-b")
    findings = run_contract_rate_compliance(
        db,
        org_id,
        [
            _billing(dataset_id, trust_id, [_billing_row(amount=1200)]),
            _quantity(uuid4(), [_quantity_row(hours=10)]),
            _component(uuid4(), [_component_row(quantity=2, price=100)]),
        ],
        {"WO-1"},
        actor,
        [_rates(dataset_id, [_rate(amount=100)])],
    )
    assert findings == []


def test_derived_c_multiple_subjects_have_distinct_findings(db: Session, tmp_path: Path) -> None:
    org_id, actor, trust_id, dataset_id = _bootstrap_context(db, tmp_path, "rate-comp-derived-c")
    findings = run_contract_rate_compliance(
        db,
        org_id,
        [
            _billing(
                dataset_id,
                trust_id,
                [
                    _billing_row(subject="WO-1", amount=1200),
                    _billing_row(subject="WO-2", amount=600),
                ],
            ),
            _quantity(
                dataset_id,
                [_quantity_row(subject="WO-1", hours=10), _quantity_row(subject="WO-2", hours=5)],
            ),
            _component(
                dataset_id,
                [
                    _component_row(subject="WO-1", quantity=2, price=100),
                    _component_row(subject="WO-2", quantity=1, price=100),
                ],
            ),
        ],
        {"WO-1", "WO-2"},
        actor,
        [_rates(dataset_id, [_rate(contract="AGR-1", amount=90)])],
    )
    assert len(findings) == 2
    assert len({finding.finding_code for finding in findings}) == 2


def test_derived_d_generic_non_fieldmaintenance_orchestration_end_to_end(
    db: Session, tmp_path: Path
) -> None:
    """Full, unmodified execute() run on a generic field-service fixture --
    no FieldMaintenance column names (no labor_entries.csv, parts_usage.csv,
    or work_orders.csv), proving the derived path is not domain-specific."""
    org: Organization = OrganizationService().create(
        db,
        OrganizationCreate(
            name="Generic Field Service",
            slug="rate-comp-derived-orchestration",
            country_code="US",
            default_currency="USD",
            timezone="UTC",
        ),
    )
    subjects = "job_id,contract_id,status,event_date\n"
    invoices = "invoice_id,job_id,contract_id,invoice_amount,currency,status,event_date\n"
    hours = "job_id,hours\n"
    kits = "job_id,count,price,currency\n"
    rates = "contract_id,start_date,end_date,hourly_rate,currency\n"
    for index in range(3):
        n = index + 1
        subjects += f"JOB-{n},AGR-{n},CLOSED,2026-06-01\n"
        invoices += f"INV-{n},JOB-{n},AGR-{n},1200,USD,ISSUED,2026-06-01\n"
        hours += f"JOB-{n},10\n"
        kits += f"JOB-{n},2,100,USD\n"
        rates += f"AGR-{n},2026-01-01,2026-12-31,90,USD\n"

    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    actor = uuid4()
    case = service.create(db, org.id, "Generic field service engagement", "single", actor)
    service.register_artifacts(
        db,
        org.id,
        case.id,
        [
            UploadedFile("job_subjects.csv", subjects.encode()),
            UploadedFile("job_invoices.csv", invoices.encode()),
            UploadedFile("job_hours.csv", hours.encode()),
            UploadedFile("job_kits.csv", kits.encode()),
            UploadedFile("job_rates.csv", rates.encode()),
        ],
        actor,
    )
    run = analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org.id, case.id, run.id, actor)

    findings = list(
        db.scalars(
            select(Finding).where(
                Finding.organization_id == org.id,
                Finding.definition_code == "CONTRACT-RATE-COMPLIANCE",
            )
        ).all()
    )
    assert len(findings) == 3
    assert all(finding.exposure_value == 100 for finding in findings)


def test_derived_negative_a_missing_quantity_abstains(db: Session, tmp_path: Path) -> None:
    org_id, actor, trust_id, dataset_id = _bootstrap_context(
        db, tmp_path, "rate-comp-derived-neg-a"
    )
    findings = run_contract_rate_compliance(
        db,
        org_id,
        [_billing(dataset_id, trust_id, [_billing_row()])],
        {"WO-1"},
        actor,
        [_rates(dataset_id, [_rate(amount=90)])],
    )
    assert findings == []


def test_derived_negative_b_zero_quantity_abstains(db: Session, tmp_path: Path) -> None:
    org_id, actor, trust_id, dataset_id = _bootstrap_context(
        db, tmp_path, "rate-comp-derived-neg-b"
    )
    findings = run_contract_rate_compliance(
        db,
        org_id,
        [
            _billing(dataset_id, trust_id, [_billing_row()]),
            _quantity(uuid4(), [_quantity_row(hours=0)]),
        ],
        {"WO-1"},
        actor,
        [_rates(dataset_id, [_rate(amount=90)])],
    )
    assert findings == []


def test_derived_negative_c_conflicting_quantity_abstains(db: Session, tmp_path: Path) -> None:
    """Two independent quantity-bearing datasets disagree on the same
    subject's total -- abstain rather than silently preferring either."""
    org_id, actor, trust_id, dataset_id = _bootstrap_context(
        db, tmp_path, "rate-comp-derived-neg-c"
    )
    findings = run_contract_rate_compliance(
        db,
        org_id,
        [
            _billing(dataset_id, trust_id, [_billing_row()]),
            _quantity(uuid4(), [_quantity_row(hours=10)], label="labor_entries.csv"),
            _quantity(uuid4(), [_quantity_row(hours=7)], label="timesheets.csv"),
        ],
        {"WO-1"},
        actor,
        [_rates(dataset_id, [_rate(amount=90)])],
    )
    assert findings == []


def test_derived_negative_d_incomplete_component_row_abstains(db: Session, tmp_path: Path) -> None:
    """A non-target component dataset resolves for this subject but is
    missing its unit price on the row -- abstain rather than guess the
    component is zero."""
    org_id, actor, trust_id, dataset_id = _bootstrap_context(
        db, tmp_path, "rate-comp-derived-neg-d"
    )
    findings = run_contract_rate_compliance(
        db,
        org_id,
        [
            _billing(dataset_id, trust_id, [_billing_row()]),
            _quantity(uuid4(), [_quantity_row(hours=10)]),
            _component(uuid4(), [_component_row(quantity=2, price=None)]),
        ],
        {"WO-1"},
        actor,
        [_rates(dataset_id, [_rate(amount=90)])],
    )
    assert findings == []


def test_derived_negative_e_missing_currency_no_publication(db: Session, tmp_path: Path) -> None:
    org_id, actor, trust_id, dataset_id = _bootstrap_context(
        db, tmp_path, "rate-comp-derived-neg-e"
    )
    findings = run_contract_rate_compliance(
        db,
        org_id,
        [
            _billing(dataset_id, trust_id, [_billing_row(currency=None)]),
            _quantity(uuid4(), [_quantity_row(hours=10)]),
            _component(uuid4(), [_component_row(quantity=2, price=100)]),
        ],
        {"WO-1"},
        actor,
        [_rates(dataset_id, [_rate(amount=90)])],
    )
    assert findings == []


def test_derived_negative_f_incompatible_uom_abstains(db: Session, tmp_path: Path) -> None:
    """Governed target quantity is explicitly denominated in days; the
    contract rate is hourly -- incompatible bases must never be compared."""
    org_id, actor, trust_id, dataset_id = _bootstrap_context(
        db, tmp_path, "rate-comp-derived-neg-f"
    )
    findings = run_contract_rate_compliance(
        db,
        org_id,
        [
            _billing(dataset_id, trust_id, [_billing_row()]),
            _quantity(
                uuid4(),
                [_quantity_row(hours=10, unit="day")],
                unit_field="rate_unit",
                implicit_quantity_unit=None,
            ),
            _component(uuid4(), [_component_row(quantity=2, price=100)]),
        ],
        {"WO-1"},
        actor,
        [_rates(dataset_id, [_rate(amount=90, unit="hour")])],
    )
    assert findings == []


def test_derived_negative_g_ambiguous_invoice_attribution_abstains(
    db: Session, tmp_path: Path
) -> None:
    """Two billing lines for the same subject -- no single amount is
    uniquely attributable, so the subject abstains entirely."""
    org_id, actor, trust_id, dataset_id = _bootstrap_context(
        db, tmp_path, "rate-comp-derived-neg-g"
    )
    findings = run_contract_rate_compliance(
        db,
        org_id,
        [
            _billing(dataset_id, trust_id, [_billing_row(amount=1200), _billing_row(amount=600)]),
            _quantity(uuid4(), [_quantity_row(hours=10)]),
            _component(uuid4(), [_component_row(quantity=2, price=100)]),
        ],
        {"WO-1"},
        actor,
        [_rates(dataset_id, [_rate(amount=90)])],
    )
    assert findings == []


def test_derived_negative_h_rate_card_dataset_never_becomes_actual_rate_input(
    db: Session, tmp_path: Path
) -> None:
    """A dataset the orchestration layer already flagged as rate-card-shaped
    is excluded from derivation entirely, even though it structurally has an
    invoice_amount-like field -- it must never be misread as a billing,
    quantity, or component source."""
    org_id, actor, trust_id, dataset_id = _bootstrap_context(
        db, tmp_path, "rate-comp-derived-neg-h"
    )
    findings = run_contract_rate_compliance(
        db,
        org_id,
        [
            _billing(
                dataset_id,
                trust_id,
                [_billing_row(amount=90)],
                is_rate_card_shaped=True,
            ),
            _quantity(uuid4(), [_quantity_row(hours=10)]),
            _component(uuid4(), [_component_row(quantity=2, price=100)]),
        ],
        {"WO-1"},
        actor,
        [_rates(dataset_id, [_rate(amount=90)])],
    )
    assert findings == []


def test_derived_negative_i_bare_rental_rate_without_uom_abstains(
    db: Session, tmp_path: Path
) -> None:
    """The real, frozen Rental corpus's own contracts.csv shape (a bare
    numeric ``rate`` with no unit/UOM column anywhere) must never acquire an
    implicit denominator for the derived path either."""
    org_id, actor, trust_id, dataset_id = _bootstrap_context(
        db, tmp_path, "rate-comp-derived-neg-i"
    )
    rate_dataset = RateDatasetFields(
        dataset_id=dataset_id,
        dataset_label="contracts.csv",
        dataframe=pd.DataFrame([{"agreement_id": "AGR-1", "contract_rate": 1850}]),
        contract_id_field="agreement_id",
        rate_field="contract_rate",
        unit_field=None,
        currency_field=None,
    )
    findings = run_contract_rate_compliance(
        db,
        org_id,
        [
            _billing(dataset_id, trust_id, [_billing_row()]),
            _quantity(uuid4(), [_quantity_row(hours=10)]),
            _component(uuid4(), [_component_row(quantity=2, price=100)]),
        ],
        {"WO-1"},
        actor,
        [rate_dataset],
    )
    assert findings == []


def test_derived_negative_j_generic_quantity_ambiguity_abstains_without_identifiers(
    db: Session, tmp_path: Path
) -> None:
    """Same underlying safety gate as the conflicting-quantity case, proven
    again on a fixture with no FieldMaintenance-shaped column names and no
    reference to any specific truth item -- the abstention is a generic
    property of disagreeing governed quantity, never a per-case exclusion."""
    org_id, actor, trust_id, dataset_id = _bootstrap_context(
        db, tmp_path, "rate-comp-derived-neg-j"
    )
    findings = run_contract_rate_compliance(
        db,
        org_id,
        [
            _billing(dataset_id, trust_id, [_billing_row(subject="JOB-9", amount=1200)]),
            _quantity(
                uuid4(),
                [_quantity_row(subject="JOB-9", hours=8)],
                label="crew_hours.csv",
            ),
            _quantity(
                uuid4(),
                [_quantity_row(subject="JOB-9", hours=5)],
                label="billed_hours.csv",
            ),
            _component(uuid4(), [_component_row(subject="JOB-9", quantity=2, price=100)]),
        ],
        {"JOB-9"},
        actor,
        [_rates(dataset_id, [_rate(amount=90)])],
    )
    assert findings == []


def test_derived_path_never_double_publishes_when_explicit_rate_also_present(
    db: Session, tmp_path: Path
) -> None:
    """A subject with a valid explicit actual_applied_rate is authoritative;
    the derived path must not also publish a second, competing finding for
    the same subject from unrelated amount/quantity evidence."""
    org_id, actor, trust_id, dataset_id = _bootstrap_context(
        db, tmp_path, "rate-comp-derived-no-double-publish"
    )
    findings = run_contract_rate_compliance(
        db,
        org_id,
        [
            _actual(dataset_id, trust_id, [_row(actual=120)]),
            _quantity(uuid4(), [_quantity_row(subject="SVC-1", hours=10)]),
            _component(uuid4(), [_component_row(subject="SVC-1", quantity=2, price=100)]),
            _billing(uuid4(), None, [_billing_row(subject="SVC-1", amount=1200)]),
        ],
        {"SVC-1"},
        actor,
        [_rates(dataset_id, [_rate()])],
    )
    assert len(findings) == 1
    assert findings[0].exposure_value == 200


def test_derive_actual_applied_rates_returns_empty_for_no_datasets() -> None:
    assert derive_actual_applied_rates([], {"WO-1"}) == []
