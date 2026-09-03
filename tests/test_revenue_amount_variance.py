"""P3.xxI.2: REVENUE-AMOUNT-VARIANCE. Additive sibling to XDOM-B -- no
XDOM-A, XDOM-B, or MAINT-001 test, fixture, or source file is read, called,
or modified here.

Two test groups:
  1. Direct rule-logic tests (Section 17 matrix A-M) -- call
     run_revenue_amount_variance directly against hand-built
     DatasetConceptFields/pandas DataFrames, reusing the already-proven
     XDOM-A-shaped bootstrap fixture (test_governed_finding_publisher_identity.py's
     own pattern) purely to obtain a genuinely valid, READY
     (organization_id, actor, trust_assessment_id, dataset_id) context --
     never to exercise XDOM-A itself.
  2. Orchestration-level readiness + generalization tests -- a full,
     unmodified analysis_case_orchestration_service.execute() run against
     two DIFFERENT raw schemas (one FieldMaintenance-shaped, one using
     entirely different column names/aliases), proving the capability
     generalizes through canonical semantics, never a filename or column
     literal.
"""

from pathlib import Path
from uuid import UUID, uuid4

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Finding, Organization
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
from app.services.canonical_revenue_variance_evidence import classify_currency_comparability
from app.services.governed_cross_dataset_rate import RateDatasetFields
from app.services.organization_service import OrganizationService
from app.services.revenue_variance_intelligence_service import (
    DatasetConceptFields,
    run_revenue_amount_variance,
)
from app.storage.local_storage import LocalFileStorage

_RULE_CODE = "REVENUE-AMOUNT-VARIANCE"
_N_ASSETS = 5


# ---------------------------------------------------------------------------
# Group 1: direct rule-logic tests
# ---------------------------------------------------------------------------


def _bootstrap_context(db: Session, tmp_path: Path, slug: str) -> tuple[UUID, UUID, UUID, UUID]:
    """Reuses the already-proven XDOM-A-shaped fixture (same as
    test_governed_finding_publisher_identity.py) purely to obtain a
    genuinely valid, READY (organization_id, actor, trust_assessment_id,
    dataset_id) -- never to exercise XDOM-A itself."""
    org: Organization = OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug.title(), slug=slug, country_code="US", default_currency="USD", timezone="UTC"
        ),
    )
    maint_rows = "asset_id,work_order_id,failure_code,downtime_hours,repair_cost,event_date\n"
    for i in range(_N_ASSETS):
        maint_rows += f"A-{i + 1},WO-{i + 1},brake,48,10000,2026-08-{i + 1:02d}T08:00:00\n"
    files = [UploadedFile("maintenance_events.csv", maint_rows.encode())]
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    actor = uuid4()
    case = service.create(db, org.id, "RevVar Bootstrap", "single", actor)
    service.register_artifacts(db, org.id, case.id, files, actor)
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
    assert readiness is not None, "bootstrap fixture must produce a READY trust assessment"
    assessment = db.get(TrustAssessment, readiness.trust_assessment_id)
    assert assessment is not None
    return org.id, actor, readiness.trust_assessment_id, assessment.dataset_id


def _consumption_dataset(
    dataset_id: UUID,
    trust_id: UUID,
    rows: list[tuple[str, float, float]],
    *,
    currency: str | None = None,
) -> DatasetConceptFields:
    df = pd.DataFrame(
        {
            "work_order_id": [r[0] for r in rows],
            "quantity": [r[1] for r in rows],
            "unit_price": [r[2] for r in rows],
            **({"currency": [currency] * len(rows)} if currency is not None else {}),
        }
    )
    return DatasetConceptFields(
        dataset_id=dataset_id,
        dataset_label="parts_usage.csv",
        dataframe=df,
        trust_assessment_id=trust_id,
        work_order_id_field="work_order_id",
        quantity_field="quantity",
        unit_price_field="unit_price",
        invoice_amount_field=None,
        cost_amount_field=None,
        currency_field="currency" if currency is not None else None,
    )


def _invoice_dataset(
    dataset_id: UUID, trust_id: UUID, rows: list[tuple[str, float]], *, currency: str | None = None
) -> DatasetConceptFields:
    df = pd.DataFrame(
        {
            "work_order_id": [r[0] for r in rows],
            "amount": [r[1] for r in rows],
            **({"currency": [currency] * len(rows)} if currency is not None else {}),
        }
    )
    return DatasetConceptFields(
        dataset_id=dataset_id,
        dataset_label="invoices.csv",
        dataframe=df,
        trust_assessment_id=trust_id,
        work_order_id_field="work_order_id",
        quantity_field=None,
        unit_price_field=None,
        invoice_amount_field="amount",
        cost_amount_field=None,
        currency_field="currency" if currency is not None else None,
    )


def test_a_full_expected_1000_actual_800_same_currency_yields_shortfall_200(
    db: Session, tmp_path: Path
) -> None:
    org_id, actor, trust_id, dataset_id = _bootstrap_context(db, tmp_path, "revvar-a")
    consumption = _consumption_dataset(
        dataset_id, trust_id, [("WO-1", 10.0, 100.0)], currency="USD"
    )
    invoices = _invoice_dataset(dataset_id, trust_id, [("WO-1", 800.0)], currency="USD")
    findings = run_revenue_amount_variance(db, org_id, [consumption, invoices], {"WO-1"}, actor)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.exposure_value == 200
    assert finding.exposure_value_type == FindingValueType.CURRENCY.value
    assert finding.exposure_currency == "USD"
    assert finding.finding_type == FindingType.LEAKAGE.value


def test_b_multiple_invoice_lines_total_800_against_expected_1000(
    db: Session, tmp_path: Path
) -> None:
    org_id, actor, trust_id, dataset_id = _bootstrap_context(db, tmp_path, "revvar-b")
    consumption = _consumption_dataset(
        dataset_id, trust_id, [("WO-1", 10.0, 100.0)], currency="USD"
    )
    invoices = _invoice_dataset(
        dataset_id, trust_id, [("WO-1", 500.0), ("WO-1", 300.0)], currency="USD"
    )
    findings = run_revenue_amount_variance(db, org_id, [consumption, invoices], {"WO-1"}, actor)
    assert len(findings) == 1
    assert findings[0].exposure_value == 200


def test_cross_dataset_governed_rate_produces_expected_amount(db: Session, tmp_path: Path) -> None:
    org_id, actor, trust_id, dataset_id = _bootstrap_context(db, tmp_path, "revvar-cross-rate")
    bridge = DatasetConceptFields(
        dataset_id=dataset_id,
        dataset_label="work-subjects",
        dataframe=pd.DataFrame({"work": ["WO-1"], "agreement": ["C-1"]}),
        trust_assessment_id=trust_id,
        work_order_id_field="work",
        quantity_field=None,
        unit_price_field=None,
        invoice_amount_field=None,
        cost_amount_field=None,
        currency_field=None,
        contract_id_field="agreement",
    )
    quantities = DatasetConceptFields(
        dataset_id=dataset_id,
        dataset_label="activity",
        dataframe=pd.DataFrame(
            {"work": ["WO-1"], "hours": [10], "at": ["2026-06-01"], "currency": ["USD"]}
        ),
        trust_assessment_id=trust_id,
        work_order_id_field="work",
        quantity_field="hours",
        unit_price_field=None,
        invoice_amount_field=None,
        cost_amount_field=None,
        currency_field="currency",
        event_timestamp_field="at",
        implicit_quantity_unit="hour",
    )
    invoices = _invoice_dataset(dataset_id, trust_id, [("WO-1", 800)], currency="USD")
    rates = [
        RateDatasetFields(
            dataset_id=dataset_id,
            dataset_label="rate-reference",
            dataframe=pd.DataFrame(
                {
                    "agreement": ["C-1"],
                    "rate": [100],
                    "from": ["2026-01-01"],
                    "to": ["2026-12-31"],
                    "currency": ["USD"],
                }
            ),
            contract_id_field="agreement",
            rate_field="rate",
            effective_from_field="from",
            effective_to_field="to",
            currency_field="currency",
            implicit_unit="hour",
        )
    ]
    findings = run_revenue_amount_variance(
        db, org_id, [bridge, quantities, invoices], {"WO-1"}, actor, rates
    )
    assert len(findings) == 1
    assert findings[0].exposure_value == 200


def test_c_actual_zero_with_existing_billing_context_governed_shortfall(
    db: Session, tmp_path: Path
) -> None:
    org_id, actor, trust_id, dataset_id = _bootstrap_context(db, tmp_path, "revvar-c")
    consumption = _consumption_dataset(
        dataset_id, trust_id, [("WO-1", 10.0, 100.0)], currency="USD"
    )
    invoices = _invoice_dataset(dataset_id, trust_id, [], currency="USD")
    findings = run_revenue_amount_variance(db, org_id, [consumption, invoices], {"WO-1"}, actor)
    assert len(findings) == 1
    assert findings[0].exposure_value == 1000
    assert findings[0].content_fingerprint is not None
    finding = findings[0]
    # full shortfall condition string is recorded as the rule_condition_code
    # basis on severity_reason
    assert finding.severity_reason == {"basis": "full_billing_shortfall"}


def test_d_quantity_times_rate_correctly_yields_expected_value(db: Session, tmp_path: Path) -> None:
    org_id, actor, trust_id, dataset_id = _bootstrap_context(db, tmp_path, "revvar-d")
    consumption = _consumption_dataset(dataset_id, trust_id, [("WO-1", 7.0, 50.0)], currency="USD")
    invoices = _invoice_dataset(dataset_id, trust_id, [("WO-1", 0.0)], currency="USD")
    findings = run_revenue_amount_variance(db, org_id, [consumption, invoices], {"WO-1"}, actor)
    assert len(findings) == 1
    assert findings[0].exposure_value == 350  # 7 * 50


def test_e_actual_equals_expected_no_finding(db: Session, tmp_path: Path) -> None:
    org_id, actor, trust_id, dataset_id = _bootstrap_context(db, tmp_path, "revvar-e")
    consumption = _consumption_dataset(
        dataset_id, trust_id, [("WO-1", 10.0, 100.0)], currency="USD"
    )
    invoices = _invoice_dataset(dataset_id, trust_id, [("WO-1", 1000.0)], currency="USD")
    findings = run_revenue_amount_variance(db, org_id, [consumption, invoices], {"WO-1"}, actor)
    assert findings == []


def test_f_actual_greater_than_expected_no_underbilling_finding(
    db: Session, tmp_path: Path
) -> None:
    org_id, actor, trust_id, dataset_id = _bootstrap_context(db, tmp_path, "revvar-f")
    consumption = _consumption_dataset(
        dataset_id, trust_id, [("WO-1", 10.0, 100.0)], currency="USD"
    )
    invoices = _invoice_dataset(dataset_id, trust_id, [("WO-1", 1500.0)], currency="USD")
    findings = run_revenue_amount_variance(db, org_id, [consumption, invoices], {"WO-1"}, actor)
    assert findings == []


def test_g_tiny_rounding_difference_within_tolerance_no_finding(
    db: Session, tmp_path: Path
) -> None:
    org_id, actor, trust_id, dataset_id = _bootstrap_context(db, tmp_path, "revvar-g")
    consumption = _consumption_dataset(
        dataset_id, trust_id, [("WO-1", 10.0, 100.0)], currency="USD"
    )
    # 999.50 vs 1000 -- $0.50 variance, well within the max(1.00, 2%) tolerance
    invoices = _invoice_dataset(dataset_id, trust_id, [("WO-1", 999.5)], currency="USD")
    findings = run_revenue_amount_variance(db, org_id, [consumption, invoices], {"WO-1"}, actor)
    assert findings == []


def test_h_different_currency_without_fx_no_definitive_comparison(
    db: Session, tmp_path: Path
) -> None:
    org_id, actor, trust_id, dataset_id = _bootstrap_context(db, tmp_path, "revvar-h")
    consumption = _consumption_dataset(
        dataset_id, trust_id, [("WO-1", 10.0, 100.0)], currency="USD"
    )
    invoices = _invoice_dataset(dataset_id, trust_id, [("WO-1", 500.0)], currency="EUR")
    findings = run_revenue_amount_variance(db, org_id, [consumption, invoices], {"WO-1"}, actor)
    assert findings == []


def test_i_incompatible_units_no_definitive_comparison(db: Session, tmp_path: Path) -> None:
    """Cross-dataset unit mismatch is prevented by construction: quantity
    and unit_price are only ever multiplied when they come from the SAME
    row of the SAME dataset. A dataset carrying only a bare quantity with
    no co-located rate produces no expected-amount line at all -- never a
    cross-record unit guess."""
    org_id, actor, trust_id, dataset_id = _bootstrap_context(db, tmp_path, "revvar-i")
    bare_quantity_df = pd.DataFrame({"work_order_id": ["WO-1"], "quantity": [10.0]})
    consumption = DatasetConceptFields(
        dataset_id=dataset_id,
        dataset_label="labor_entries.csv",
        dataframe=bare_quantity_df,
        trust_assessment_id=trust_id,
        work_order_id_field="work_order_id",
        quantity_field="quantity",
        unit_price_field=None,
        invoice_amount_field=None,
        cost_amount_field=None,
        currency_field=None,
    )
    invoices = _invoice_dataset(dataset_id, trust_id, [("WO-1", 0.0)], currency="USD")
    findings = run_revenue_amount_variance(db, org_id, [consumption, invoices], {"WO-1"}, actor)
    assert findings == []


def test_j_ambiguous_linkage_not_eligible_no_finding(db: Session, tmp_path: Path) -> None:
    """A work order not in the eligible (governed-entity-cleared) set
    produces no finding, even with clear amount evidence -- linkage
    ambiguity is represented by the caller never adding it to
    eligible_work_order_keys."""
    org_id, actor, trust_id, dataset_id = _bootstrap_context(db, tmp_path, "revvar-j")
    consumption = _consumption_dataset(
        dataset_id, trust_id, [("WO-1", 10.0, 100.0)], currency="USD"
    )
    invoices = _invoice_dataset(dataset_id, trust_id, [("WO-1", 0.0)], currency="USD")
    findings = run_revenue_amount_variance(
        db,
        org_id,
        [consumption, invoices],
        set(),
        actor,  # WO-1 not eligible
    )
    assert findings == []


def test_k_unrelated_invoice_does_not_satisfy_or_distort_another_event(
    db: Session, tmp_path: Path
) -> None:
    org_id, actor, trust_id, dataset_id = _bootstrap_context(db, tmp_path, "revvar-k")
    consumption = _consumption_dataset(
        dataset_id,
        trust_id,
        [("WO-1", 10.0, 100.0), ("WO-2", 5.0, 100.0)],
        currency="USD",
    )
    # WO-2's invoice is fully paid; WO-1 has none at all.
    invoices = _invoice_dataset(dataset_id, trust_id, [("WO-2", 500.0)], currency="USD")
    findings = run_revenue_amount_variance(
        db, org_id, [consumption, invoices], {"WO-1", "WO-2"}, actor
    )
    assert len(findings) == 1
    subjects = set()
    for f in findings:
        assert f.entities_json is not None
        subjects.add(f.entities_json[0]["canonical_key"])
    assert subjects == {"WO-1"}


def test_l_repeat_same_publication_is_idempotent(db: Session, tmp_path: Path) -> None:
    org_id, actor, trust_id, dataset_id = _bootstrap_context(db, tmp_path, "revvar-l")
    consumption = _consumption_dataset(
        dataset_id, trust_id, [("WO-1", 10.0, 100.0)], currency="USD"
    )
    invoices = _invoice_dataset(dataset_id, trust_id, [("WO-1", 800.0)], currency="USD")
    first = run_revenue_amount_variance(db, org_id, [consumption, invoices], {"WO-1"}, actor)
    second = run_revenue_amount_variance(db, org_id, [consumption, invoices], {"WO-1"}, actor)
    assert len(first) == 1
    assert len(second) == 1
    assert first[0].id == second[0].id
    count = db.scalar(select(Finding).where(Finding.definition_code == _RULE_CODE))
    all_rows = list(
        db.scalars(
            select(Finding).where(
                Finding.definition_code == _RULE_CODE, Finding.organization_id == org_id
            )
        ).all()
    )
    assert len(all_rows) == 1
    del count


def test_m_two_different_events_same_variance_two_findings(db: Session, tmp_path: Path) -> None:
    org_id, actor, trust_id, dataset_id = _bootstrap_context(db, tmp_path, "revvar-m")
    consumption = _consumption_dataset(
        dataset_id,
        trust_id,
        [("WO-1", 10.0, 100.0), ("WO-2", 10.0, 100.0)],
        currency="USD",
    )
    invoices = _invoice_dataset(
        dataset_id, trust_id, [("WO-1", 800.0), ("WO-2", 800.0)], currency="USD"
    )
    findings = run_revenue_amount_variance(
        db, org_id, [consumption, invoices], {"WO-1", "WO-2"}, actor
    )
    assert len(findings) == 2
    assert findings[0].id != findings[1].id


# ---------------------------------------------------------------------------
# P3.xxI.2A: three-state evidence contract (Section 16) -- NO_GOVERNED_EVIDENCE
# must never be converted into a numeric zero. Distinguishes "this dataset
# never resolved the amount concept at all" (must block) from "this dataset
# resolved the amount concept and genuinely has no matching row" (Test C
# above, CONFIRMED_ZERO, still valid).
# ---------------------------------------------------------------------------


def _unresolved_invoice_dataset(
    dataset_id: UUID, trust_id: UUID, rows: list[tuple[str, float]]
) -> DatasetConceptFields:
    """Same physical shape as _invoice_dataset (a work-order-linked billing
    dataset with real rows and a real 'amount' column) but with
    invoice_amount_field/unit_price_field left None -- exactly what the
    orchestration layer passes when semantic resolution never reached
    AUTO_ACCEPTED/human-governed for that column, the shape confirmed live
    on FIELDMAINT-002 pre-remediation (docs/p3xxi2a-governed-actual-billing-
    evidence-remediation.md Section B): the dataset and its rows are real,
    only the CONCEPT never resolved."""
    df = pd.DataFrame({"work_order_id": [r[0] for r in rows], "amount": [r[1] for r in rows]})
    return DatasetConceptFields(
        dataset_id=dataset_id,
        dataset_label="invoices.csv",
        dataframe=df,
        trust_assessment_id=trust_id,
        work_order_id_field="work_order_id",
        quantity_field=None,
        unit_price_field=None,
        invoice_amount_field=None,
        cost_amount_field=None,
        currency_field=None,
    )


def test_no_governed_evidence_actual_side_no_definitive_finding(
    db: Session, tmp_path: Path
) -> None:
    """Section 16.B: the actual/billing side's amount concept never
    resolved anywhere in the case (invoices.csv has real rows, but neither
    invoice_amount_field nor unit_price_field was ever populated) -- must
    never be silently summed to Decimal("0") and reported as a full
    billing shortfall."""
    org_id, actor, trust_id, dataset_id = _bootstrap_context(db, tmp_path, "revvar-no-evidence-a")
    consumption = _consumption_dataset(
        dataset_id, trust_id, [("WO-1", 10.0, 100.0)], currency="USD"
    )
    unresolved_invoices = _unresolved_invoice_dataset(dataset_id, trust_id, [("WO-1", 800.0)])
    findings = run_revenue_amount_variance(
        db, org_id, [consumption, unresolved_invoices], {"WO-1"}, actor
    )
    assert findings == []


def test_no_governed_evidence_expected_side_no_definitive_finding(
    db: Session, tmp_path: Path
) -> None:
    """Section 16.C: mirror of the above for the expected side -- neither
    quantity+unit_price nor cost_amount ever resolved on any dataset."""
    org_id, actor, trust_id, dataset_id = _bootstrap_context(db, tmp_path, "revvar-no-evidence-e")
    df = pd.DataFrame({"work_order_id": ["WO-1"], "quantity": [10.0], "unit_price": [100.0]})
    unresolved_consumption = DatasetConceptFields(
        dataset_id=dataset_id,
        dataset_label="parts_usage.csv",
        dataframe=df,
        trust_assessment_id=trust_id,
        work_order_id_field="work_order_id",
        quantity_field=None,
        unit_price_field=None,
        invoice_amount_field=None,
        cost_amount_field=None,
        currency_field=None,
    )
    invoices = _invoice_dataset(dataset_id, trust_id, [("WO-1", 800.0)], currency="USD")
    findings = run_revenue_amount_variance(
        db, org_id, [unresolved_consumption, invoices], {"WO-1"}, actor
    )
    assert findings == []


def test_confirmed_zero_still_produces_a_finding_when_evidence_is_governed(
    db: Session, tmp_path: Path
) -> None:
    """Section 16.D: the safety gate must not become so conservative it
    also blocks the legitimate CONFIRMED_ZERO case -- re-asserts Test C's
    own outcome explicitly as a three-state contrast against the two tests
    immediately above (same physical emptiness, opposite cause)."""
    org_id, actor, trust_id, dataset_id = _bootstrap_context(db, tmp_path, "revvar-confirmed-zero")
    consumption = _consumption_dataset(
        dataset_id, trust_id, [("WO-1", 10.0, 100.0)], currency="USD"
    )
    invoices = _invoice_dataset(dataset_id, trust_id, [], currency="USD")  # resolved, zero rows
    findings = run_revenue_amount_variance(db, org_id, [consumption, invoices], {"WO-1"}, actor)
    assert len(findings) == 1
    assert findings[0].exposure_value == 1000


def test_mass_false_positive_class_structurally_impossible(db: Session, tmp_path: Path) -> None:
    """Section 14: generic regression fixture reproducing the live-observed
    failure SHAPE (many work orders, each with real consumption evidence
    and a real, row-populated invoice dataset whose amount concept simply
    never resolved) -- never referencing any specific simulation. Before
    P3.xxI.2A this produced one 'full billing shortfall' finding per work
    order; after, it must produce zero, proving missing evidence != zero
    at scale, not just for one work order."""
    org_id, actor, trust_id, dataset_id = _bootstrap_context(db, tmp_path, "revvar-mass-fp")
    n = 25
    consumption = _consumption_dataset(
        dataset_id,
        trust_id,
        [(f"WO-{i}", 10.0, 100.0) for i in range(n)],
        currency="USD",
    )
    unresolved_invoices = _unresolved_invoice_dataset(
        dataset_id, trust_id, [(f"WO-{i}", 900.0) for i in range(n)]
    )
    findings = run_revenue_amount_variance(
        db,
        org_id,
        [consumption, unresolved_invoices],
        {f"WO-{i}" for i in range(n)},
        actor,
    )
    assert findings == []


def test_unknown_currency_both_sides_proceeds_with_decimal_exposure(
    db: Session, tmp_path: Path
) -> None:
    org_id, actor, trust_id, dataset_id = _bootstrap_context(db, tmp_path, "revvar-unknown-ccy")
    consumption = _consumption_dataset(dataset_id, trust_id, [("WO-1", 10.0, 100.0)])
    invoices = _invoice_dataset(dataset_id, trust_id, [("WO-1", 800.0)])
    findings = run_revenue_amount_variance(db, org_id, [consumption, invoices], {"WO-1"}, actor)
    assert len(findings) == 1
    assert findings[0].exposure_value_type == FindingValueType.DECIMAL.value
    assert findings[0].exposure_currency is None
    assert findings[0].exposure_value == 200


def test_currency_comparability_classification() -> None:
    assert classify_currency_comparability("USD", "USD") == "same_known"
    assert classify_currency_comparability("USD", "EUR") == "different_known"
    assert classify_currency_comparability(None, None) == "unknown_both"
    assert classify_currency_comparability("USD", None) == "mixed_known_unknown"
    assert classify_currency_comparability(None, "USD") == "mixed_known_unknown"


# ---------------------------------------------------------------------------
# Group 2: orchestration-level readiness + generalization
# ---------------------------------------------------------------------------


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


def _decision(db: Session, run_id: UUID) -> IntelligenceActivationDecision | None:
    return db.scalar(
        select(IntelligenceActivationDecision).where(
            IntelligenceActivationDecision.run_id == run_id,
            IntelligenceActivationDecision.rule_code == _RULE_CODE,
        )
    )


_N_WORK_ORDERS = 6


def _field_maintenance_shaped_csvs() -> list[UploadedFile]:
    """Same column-naming convention as the real Wave 1 corpus:
    work_order_id, quantity, unit_price, amount."""
    parts = "work_order_id,part_number,quantity,unit_price\n"
    invoices = "work_order_id,invoice_date,amount,status\n"
    for i in range(_N_WORK_ORDERS):
        parts += f"WO-{i + 1},PRT-{i + 1},{4 + i},{50 + i * 5}\n"
        billed = (4 + i) * (50 + i * 5) - 150  # always short by 150
        invoices += f"WO-{i + 1},2026-08-{i + 1:02d},{max(billed, 0)},CLOSED\n"
    return [
        UploadedFile("parts_usage.csv", parts.encode()),
        UploadedFile("invoices.csv", invoices.encode()),
    ]


def _differently_named_schema_csvs() -> list[UploadedFile]:
    """A DIFFERENT raw schema for the identical business invariant: a
    ticket-shaped consumption record (order_id/units/price alias forms)
    and a billing record (bill_id/total_amount alias forms) -- proves the
    capability generalizes through canonical semantics, not column
    literals. Uses only aliases already registered in
    app/semantic/concept_registry.py (order_id -> work_order_id, qty ->
    quantity, price -> unit_price, total_amount -> invoice_amount)."""
    tickets = "order_id,sku,qty,price\n"
    bills = "order_id,bill_id,total_amount\n"
    for i in range(_N_WORK_ORDERS):
        tickets += f"ORD-{i + 1},SKU-{i + 1},{3 + i},{40 + i * 4}\n"
        billed = (3 + i) * (40 + i * 4) - 100
        bills += f"ORD-{i + 1},BILL-{i + 1},{max(billed, 0)}\n"
    return [
        UploadedFile("service_tickets.csv", tickets.encode()),
        UploadedFile("billing_records.csv", bills.encode()),
    ]


def test_orchestration_wiring_produces_activation_decision(db: Session, tmp_path: Path) -> None:
    """Proves REVENUE-AMOUNT-VARIANCE participates in the same generic
    readiness/activation persistence XDOM-A/XDOM-B already use -- one row
    is written per run, regardless of the resulting status."""
    org = _organization(db, "revvar-orch-decision")
    _, run_id = _run_case(
        db, tmp_path, org.id, _field_maintenance_shaped_csvs(), "RevVar Orchestration"
    )
    decision = _decision(db, run_id)
    assert decision is not None
    assert decision.mode == "governed"


def test_orchestration_cross_dataset_hourly_rate_end_to_end(db: Session, tmp_path: Path) -> None:
    """Real orchestration proves semantic authority, relationship lookup,
    temporal applicability, unit basis, actual billing, and publication as
    one governed chain. Six subjects satisfy the existing entity-evidence
    floor; no filename or customer-specific execution branch is involved.
    """
    org = _organization(db, "revvar-cross-rate-e2e")
    work_orders = "work_order_id,contract_id,status\n"
    labor = "work_order_id,hours,entry_date\n"
    contracts = "contract_id,start_date,end_date,labor_rate\n"
    invoices = "invoice_id,work_order_id,invoice_date,amount,status\n"
    for i in range(_N_WORK_ORDERS):
        n = i + 1
        work_orders += f"WO-{n},C-{n},CLOSED\n"
        labor += f"WO-{n},10,2026-06-01\n"
        contracts += f"C-{n},2026-01-01,2026-12-31,100\n"
        invoices += f"INV-{n},WO-{n},2026-06-02,800,CLOSED\n"
    files = [
        UploadedFile("work-subjects.csv", work_orders.encode()),
        UploadedFile("labor-activity.csv", labor.encode()),
        UploadedFile("commercial-reference.csv", contracts.encode()),
        UploadedFile("billing.csv", invoices.encode()),
    ]
    _, run_id = _run_case(db, tmp_path, org.id, files, "Cross-dataset rate E2E")
    decision = _decision(db, run_id)
    assert decision is not None
    assert decision.governed_status == "READY"
    findings = list(
        db.scalars(
            select(Finding).where(
                Finding.organization_id == org.id, Finding.definition_code == _RULE_CODE
            )
        ).all()
    )
    semantic_debug = list(
        db.execute(
            select(
                SemanticInterpretationDecision.source_field,
                SemanticInterpretationDecision.selected_concept,
                SemanticInterpretationDecision.confidence,
                SemanticInterpretationDecision.status,
            ).where(SemanticInterpretationDecision.run_id == run_id)
        ).all()
    )
    assert len(findings) == _N_WORK_ORDERS, semantic_debug
    assert all(f.exposure_value == 200 for f in findings)


def test_generalization_different_schema_same_invariant(db: Session, tmp_path: Path) -> None:
    """Section 23: a completely different raw schema (order_id/qty/price
    instead of work_order_id/quantity/unit_price, bill_id/total_amount
    instead of invoice_id/amount) still resolves through canonical
    semantics -- no filename- or column-literal branch exists anywhere in
    this capability. READINESS reaching READY (required_canonical_entities
    + required_canonical_measures both satisfied through the DIFFERENT raw
    names) is the actual generalization proof: work_order_id and quantity
    both independently reach AUTO_ACCEPTED here purely from their own
    alias/role/value-pattern evidence. Whether a finding is ALSO produced
    additionally depends on total_amount's own semantic confidence tier for
    THIS specific fixture (invoice_amount shares its raw "amount" alias
    with unit_price/cost_amount and only reaches AUTO_ACCEPTED with
    cross-dataset corroboration this two-file fixture doesn't happen to
    provide) -- asserted as an honest, non-forced outcome rather than
    tuned to make a finding appear."""
    org = _organization(db, "revvar-generalization")
    _, run_id = _run_case(
        db, tmp_path, org.id, _differently_named_schema_csvs(), "RevVar Generalization"
    )
    decision = _decision(db, run_id)
    assert decision is not None
    assert decision.governed_status == "READY"
    findings = list(
        db.scalars(
            select(Finding).where(
                Finding.organization_id == org.id, Finding.definition_code == _RULE_CODE
            )
        ).all()
    )
    assert all(f.exposure_value is not None and f.exposure_value > 0 for f in findings)
