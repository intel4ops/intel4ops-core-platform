"""P3.xxI.3: governed canonical duration / interval evidence -- unit
coverage for app/services/governed_duration_evidence.py (the reusable,
capability-agnostic derivation primitive itself) and one real, unmodified
orchestration.execute() run proving the full chain (derived duration ->
governed rate -> REVENUE-AMOUNT-VARIANCE finding) end to end, matching
tests/test_revenue_amount_variance.py's own established style (direct
unit tests for the framework-light module, one real orchestration run for
the full pipeline)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis_case import AnalysisCaseDataset
from app.models.entities import Finding, Organization
from app.models.intelligence_activation import IntelligenceActivationDecision
from app.schemas.contracts import OrganizationCreate
from app.semantic.candidate import InterpretationDecision
from app.services.analysis_case_orchestration_service import (
    SemanticInterpretationOutcome,
    analysis_case_orchestration_service,
)
from app.services.analysis_case_service import AnalysisCaseService, UploadedFile
from app.services.governed_duration_evidence import (
    resolve_cross_dataset_duration,
    resolve_row_duration,
)
from app.services.organization_service import OrganizationService
from app.storage.local_storage import LocalFileStorage

_RULE_CODE = "REVENUE-AMOUNT-VARIANCE"

# ---------------------------------------------------------------------------
# Section A: resolve_row_duration -- positive cases
# ---------------------------------------------------------------------------


def test_same_row_start_end_produces_governed_elapsed_duration() -> None:
    row = pd.Series({"start": "2026-01-01T00:00:00", "end": "2026-01-06T00:00:00"})
    evidence = resolve_row_duration(
        row, "start", "end", "event_timestamp", "completed_timestamp", "0"
    )
    assert evidence is not None
    assert evidence.elapsed_hours == Decimal("120")
    assert evidence.elapsed_days == Decimal("5")
    assert evidence.start_concept == "event_timestamp"
    assert evidence.end_concept == "completed_timestamp"


def test_alternate_column_names_same_result() -> None:
    """Same elapsed interval, different raw column names -- the
    function is field-name-agnostic, only the resolved values matter."""
    row = pd.Series({"dispatch_date": "2026-03-01", "return_date": "2026-03-06"})
    evidence = resolve_row_duration(
        row, "dispatch_date", "return_date", "event_timestamp", "completed_timestamp", "0"
    )
    assert evidence is not None
    assert evidence.elapsed_days == Decimal("5")


def test_date_only_interval_deterministic_midnight_semantics() -> None:
    """A bare date parses to that date's midnight -- pandas' own
    pre-existing, deterministic date-only semantics, not a new rule."""
    row = pd.Series({"start": "2026-06-01", "end": "2026-06-02"})
    evidence = resolve_row_duration(
        row, "start", "end", "event_timestamp", "completed_timestamp", "0"
    )
    assert evidence is not None
    assert evidence.elapsed_hours == Decimal("24")
    assert evidence.elapsed_days == Decimal("1")


def test_timezone_aware_timestamps_correct_elapsed_time() -> None:
    row = pd.Series(
        {
            "start": "2026-01-01T00:00:00+00:00",
            "end": "2026-01-01T05:00:00+02:00",  # = 03:00 UTC -> 3 hours elapsed
        }
    )
    evidence = resolve_row_duration(
        row, "start", "end", "event_timestamp", "completed_timestamp", "0"
    )
    assert evidence is not None
    assert evidence.elapsed_hours == Decimal("3")


def test_no_rounding_23_hours_stays_23_hours_not_1_day() -> None:
    row = pd.Series({"start": "2026-01-01T00:00:00", "end": "2026-01-01T23:00:00"})
    evidence = resolve_row_duration(
        row, "start", "end", "event_timestamp", "completed_timestamp", "0"
    )
    assert evidence is not None
    assert evidence.elapsed_hours == Decimal("23")
    assert evidence.elapsed_days == Decimal("23") / Decimal("24")


def test_no_rounding_25_hours_stays_25_hours_not_1_day() -> None:
    row = pd.Series({"start": "2026-01-01T00:00:00", "end": "2026-01-02T01:00:00"})
    evidence = resolve_row_duration(
        row, "start", "end", "event_timestamp", "completed_timestamp", "0"
    )
    assert evidence is not None
    assert evidence.elapsed_hours == Decimal("25")
    assert evidence.elapsed_days == Decimal("25") / Decimal("24")


def test_cross_dataset_subject_linked_interval_full_lineage() -> None:
    """Start on one dataset, end on another, already joined via a
    governed subject key (mirrors the shape P3.xxI.2C's own subject
    bridge produces) -- Section 13E."""
    start_by_subject = {"WO-1": "2026-01-01T08:00:00", "WO-2": "2026-01-02T08:00:00"}
    end_by_subject = {"WO-1": "2026-01-01T12:00:00"}  # WO-2 has no end -- must be silently absent
    results = resolve_cross_dataset_duration(
        start_by_subject, end_by_subject, "event_timestamp", "completed_timestamp"
    )
    assert set(results) == {"WO-1"}
    assert results["WO-1"].elapsed_hours == Decimal("4")
    assert results["WO-1"].start_field == "<cross-dataset>"
    assert results["WO-1"].row_reference == "WO-1"


# ---------------------------------------------------------------------------
# Section B: resolve_row_duration -- negative cases (Section 14)
# ---------------------------------------------------------------------------


def test_missing_start_no_duration() -> None:
    row = pd.Series({"end": "2026-01-06T00:00:00"})
    assert resolve_row_duration(row, "start", "end", "a", "b", "0") is None


def test_missing_end_no_duration() -> None:
    row = pd.Series({"start": "2026-01-01T00:00:00"})
    assert resolve_row_duration(row, "start", "end", "a", "b", "0") is None


def test_end_before_start_abstains() -> None:
    row = pd.Series({"start": "2026-01-06T00:00:00", "end": "2026-01-01T00:00:00"})
    assert resolve_row_duration(row, "start", "end", "a", "b", "0") is None


def test_unparseable_timestamp_abstains() -> None:
    row = pd.Series({"start": "not-a-date", "end": "2026-01-06T00:00:00"})
    assert resolve_row_duration(row, "start", "end", "a", "b", "0") is None


def test_null_start_value_abstains() -> None:
    row = pd.Series({"start": None, "end": "2026-01-06T00:00:00"})
    assert resolve_row_duration(row, "start", "end", "a", "b", "0") is None


def test_mismatched_tz_awareness_abstains_not_crashes() -> None:
    """One offset-aware, one naive -- pandas itself refuses to compare
    these; that TypeError is the correct abstain signal, never a crash
    or an invented conversion."""
    row = pd.Series({"start": "2026-01-01T00:00:00+00:00", "end": "2026-01-02T00:00:00"})
    assert resolve_row_duration(row, "start", "end", "a", "b", "0") is None


def test_missing_subject_linkage_no_cross_subject_attribution() -> None:
    """Section 14I: a subject present in only one side never gets a
    fabricated duration."""
    start_by_subject = {"WO-1": "2026-01-01T00:00:00"}
    end_by_subject = {"WO-2": "2026-01-02T00:00:00"}
    results = resolve_cross_dataset_duration(start_by_subject, end_by_subject, "a", "b")
    assert results == {}


# ---------------------------------------------------------------------------
# Section C: full orchestration -- derived duration -> rate -> finding
# (Sections 11, 13F/G). A synthetic, non-Rental, non-FieldMaintenance
# shape (Section 15's own generalization requirement) modeling a generic
# "service response interval" process: request received -> resolved,
# billed per hour AND, in a second fixture, per day.
# ---------------------------------------------------------------------------

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


def test_derived_duration_hourly_rate_end_to_end_generic_shape(db: Session, tmp_path: Path) -> None:
    """Generic service-response-interval process (not Rental, not
    FieldMaintenance): dispatch_id/contract_id resolve the CONTRACT
    subject (P3.xxI.2C), assignment start/end resolve as
    event_timestamp/completed_timestamp (no stored quantity column
    anywhere), billed hourly -- proves REVENUE-AMOUNT-VARIANCE consumes a
    PURELY derived duration with zero Rental-specific column names."""
    org = _organization(db, "revvar-2i3-response-hourly")
    # start/end live on the SAME row as the governed contract reference --
    # sibling-concept corroboration (both event_timestamp AND, as of this
    # milestone, completed_timestamp) needs that co-location to reach
    # AUTO_ACCEPTED, exactly like Rental's own real dispatch.csv shape.
    events = "dispatch_id,agreement_id,asset_id,occurred_at,completed_at\n"
    rate_cards = "rate_card_id,labor_rate\n"
    billing = "bill_id,agreement_id,amount,status\n"
    for i in range(_N_SUBJECTS):
        n = i + 1
        events += (
            f"DSP-{n},AGR-{n},AST-{n},2026-02-0{n}T08:00:00,2026-02-0{n}T18:00:00\n"  # 10h elapsed
        )
        rate_cards += f"AGR-{n},50\n"  # $50/hr * 10h = $500 expected
        billing += f"BILL-{n},AGR-{n},400,ISSUED\n"  # actual 400 -> shortfall 100
    files = [
        UploadedFile("events.csv", events.encode()),
        UploadedFile("rate_cards.csv", rate_cards.encode()),
        UploadedFile("billing.csv", billing.encode()),
    ]
    _, run_id = _run_case(db, tmp_path, org.id, files, "Derived duration hourly E2E")

    decision = db.scalar(
        select(IntelligenceActivationDecision).where(
            IntelligenceActivationDecision.run_id == run_id,
            IntelligenceActivationDecision.rule_code == _RULE_CODE,
        )
    )
    assert decision is not None
    assert decision.governed_status == "READY"

    findings = list(
        db.scalars(
            select(Finding).where(
                Finding.organization_id == org.id, Finding.definition_code == _RULE_CODE
            )
        ).all()
    )
    assert len(findings) == _N_SUBJECTS
    assert all(f.exposure_value == 100 for f in findings)


def test_derived_duration_day_rate_end_to_end_explicit_unit_conversion(
    db: Session, tmp_path: Path
) -> None:
    """Section 13G: derived duration + a compatible PER-DAY rate,
    selected only because this dataset carries its own explicit,
    governed unit_of_measure evidence saying "day" -- never guessed from
    the rate concept's name or any implicit business rounding. A 5-day
    exact elapsed interval (2026-03-01T00:00 -> 2026-03-06T00:00) times
    $100/day = $500 expected; actual $400 -> shortfall $100."""
    org = _organization(db, "revvar-2i3-response-daily")
    events = "dispatch_id,agreement_id,asset_id,occurred_at,completed_at,unit\n"
    # "rate" (not "labor_rate") resolves as unit_price, not hourly_rate --
    # hourly_rate forces an implicit "hour" unit unconditionally
    # (app/services/analysis_case_orchestration_service.py), which would
    # never match a day-denominated quantity. unit_price carries no such
    # forced default, so its OWN explicit "day" unit column is what
    # actually governs the match here -- explicit unit conversion, never
    # an implicit business-rounding guess.
    rate_cards = "rate_card_id,rate,unit\n"
    billing = "bill_id,agreement_id,amount,status\n"
    for i in range(_N_SUBJECTS):
        n = i + 1
        events += (
            f"DSP-{n},AGR-{n},AST-{n},2026-03-0{n}T00:00:00,2026-03-{n + 5:02d}T00:00:00,day\n"
        )
        rate_cards += f"AGR-{n},100,day\n"  # $100/day * 5 days = $500 expected
        billing += f"BILL-{n},AGR-{n},400,ISSUED\n"  # actual 400 -> shortfall 100
    files = [
        UploadedFile("events.csv", events.encode()),
        UploadedFile("rate_cards.csv", rate_cards.encode()),
        UploadedFile("billing.csv", billing.encode()),
    ]
    _, run_id = _run_case(db, tmp_path, org.id, files, "Derived duration daily E2E")

    findings = list(
        db.scalars(
            select(Finding).where(
                Finding.organization_id == org.id, Finding.definition_code == _RULE_CODE
            )
        ).all()
    )
    assert len(findings) == _N_SUBJECTS
    assert all(f.exposure_value == 100 for f in findings)


# ---------------------------------------------------------------------------
# Section D: _resolve_derived_duration_field -- direct method-call
# coverage for the orchestration-layer helper, using hand-built semantic
# decisions rather than the full confidence engine (mirrors
# tests/test_p3xxi2c_billable_subject_generalization.py's own established
# style for its analogous helper). Covers Section 14D/E (ambiguous
# endpoint -> abstain, enforced by construction: only a STRICT,
# AUTO_ACCEPTED-tier decision is ever passed through) and Section 14H
# (competing interval pairs that disagree -> abstain).
# ---------------------------------------------------------------------------


def _decision(
    source_field: str, concept: str, status: str = "auto_accepted"
) -> InterpretationDecision:
    return InterpretationDecision(
        source_dataset_id="ds",
        source_field=source_field,
        selected_concept=concept,
        confidence=0.98 if status == "auto_accepted" else 0.8,
        status=status,
        evidence_summary=[],
        alternative_candidates=[],
        decision_source="test",
        decision_version="1.0",
    )


def _case_dataset(label: str = "ds") -> AnalysisCaseDataset:
    return AnalysisCaseDataset(id=uuid4(), dataset_id=uuid4(), source_label=label)


def test_ambiguous_endpoint_never_reaches_derivation_no_duration() -> None:
    """Section 14D/E: an endpoint decision that only reached
    ACCEPTED_WITH_FLAG never becomes a governed field at all (the strict
    resolver returns None for it), so the derivation finds no resolved
    pair and abstains -- ambiguity is excluded by construction, not a
    special case inside the helper itself."""
    ds = _case_dataset("events.csv")
    df = pd.DataFrame({"start": ["2026-01-01"], "end": ["2026-01-06"]})
    semantic_outcome = SemanticInterpretationOutcome(
        case_context=None,  # type: ignore[arg-type]
        decisions_by_case_dataset={
            ds.id: [
                _decision("start", "event_timestamp", status="accepted_with_flag"),
                _decision("end", "completed_timestamp", status="accepted_with_flag"),
            ]
        },
    )
    result_df, hours_field, days_field, basis = (
        analysis_case_orchestration_service._resolve_derived_duration_field(
            ds, df, semantic_outcome
        )
    )
    assert hours_field is None
    assert days_field is None
    assert basis is None
    assert result_df is df


def test_one_governed_one_ambiguous_endpoint_no_duration() -> None:
    """Only the START reaching AUTO_ACCEPTED is not enough -- BOTH
    endpoints must independently clear the bar."""
    ds = _case_dataset("events.csv")
    df = pd.DataFrame({"start": ["2026-01-01"], "end": ["2026-01-06"]})
    semantic_outcome = SemanticInterpretationOutcome(
        case_context=None,  # type: ignore[arg-type]
        decisions_by_case_dataset={
            ds.id: [
                _decision("start", "event_timestamp", status="auto_accepted"),
                _decision("end", "completed_timestamp", status="accepted_with_flag"),
            ]
        },
    )
    _, hours_field, days_field, basis = (
        analysis_case_orchestration_service._resolve_derived_duration_field(
            ds, df, semantic_outcome
        )
    )
    assert hours_field is None and days_field is None and basis is None


def test_governed_pair_produces_derived_duration_columns() -> None:
    ds = _case_dataset("events.csv")
    df = pd.DataFrame({"start": ["2026-01-01T00:00:00"], "end": ["2026-01-06T00:00:00"]})
    semantic_outcome = SemanticInterpretationOutcome(
        case_context=None,  # type: ignore[arg-type]
        decisions_by_case_dataset={
            ds.id: [
                _decision("start", "event_timestamp"),
                _decision("end", "completed_timestamp"),
            ]
        },
    )
    result_df, hours_field, days_field, basis = (
        analysis_case_orchestration_service._resolve_derived_duration_field(
            ds, df, semantic_outcome
        )
    )
    assert hours_field is not None and days_field is not None
    assert basis == "event_timestamp->completed_timestamp"
    assert result_df.loc[0, hours_field] == 120.0
    assert result_df.loc[0, days_field] == 5.0
    assert result_df is not df  # never mutates the shared canonical_frames dataframe


def test_competing_interval_pairs_that_disagree_abstain() -> None:
    """Section 14H: event_timestamp->completed_timestamp AND
    scheduled_timestamp->completed_timestamp both independently resolve
    on this dataset, but disagree materially on the same row -- abstain
    entirely rather than silently preferring one."""
    ds = _case_dataset("events.csv")
    df = pd.DataFrame(
        {
            "occurred": ["2026-01-01T00:00:00"],
            "scheduled": ["2026-01-03T00:00:00"],  # a very different start
            "completed": ["2026-01-06T00:00:00"],
        }
    )
    semantic_outcome = SemanticInterpretationOutcome(
        case_context=None,  # type: ignore[arg-type]
        decisions_by_case_dataset={
            ds.id: [
                _decision("occurred", "event_timestamp"),
                _decision("scheduled", "scheduled_timestamp"),
                _decision("completed", "completed_timestamp"),
            ]
        },
    )
    _, hours_field, days_field, basis = (
        analysis_case_orchestration_service._resolve_derived_duration_field(
            ds, df, semantic_outcome
        )
    )
    assert hours_field is None and days_field is None and basis is None


def test_competing_interval_pairs_that_agree_use_first_declared() -> None:
    """When the two declared pairs happen to agree (or simply don't
    overlap), declaration order is itself the governed resolution --
    event_timestamp->completed_timestamp (declared first) wins over
    scheduled_timestamp->completed_timestamp."""
    ds = _case_dataset("events.csv")
    df = pd.DataFrame(
        {
            "occurred": ["2026-01-01T00:00:00"],
            "scheduled": ["2026-01-01T00:00:00"],  # identical to occurred
            "completed": ["2026-01-06T00:00:00"],
        }
    )
    semantic_outcome = SemanticInterpretationOutcome(
        case_context=None,  # type: ignore[arg-type]
        decisions_by_case_dataset={
            ds.id: [
                _decision("occurred", "event_timestamp"),
                _decision("scheduled", "scheduled_timestamp"),
                _decision("completed", "completed_timestamp"),
            ]
        },
    )
    _, hours_field, days_field, basis = (
        analysis_case_orchestration_service._resolve_derived_duration_field(
            ds, df, semantic_outcome
        )
    )
    assert basis == "event_timestamp->completed_timestamp"
    assert hours_field is not None


def test_derived_duration_unit_incompatible_with_rate_basis_no_finding(
    db: Session, tmp_path: Path
) -> None:
    """Section 14G: the derived duration defaults to hours (no LOCAL day
    signal on the quantity dataset, and the rate's own governed unit is
    "week" -- not "day"/"days", so the hours<->days swap never triggers).
    An hours-denominated quantity against a week-denominated rate is a
    genuine, governed unit mismatch -- resolve_applicable_rate's own
    strict equality check abstains, producing no expected-amount line and
    therefore no finding, never an invented conversion."""
    org = _organization(db, "revvar-2i3-unit-mismatch")
    events = "dispatch_id,agreement_id,asset_id,occurred_at,completed_at\n"
    rate_cards = "rate_card_id,rate,unit\n"
    billing = "bill_id,agreement_id,amount,status\n"
    for i in range(_N_SUBJECTS):
        n = i + 1
        events += f"DSP-{n},AGR-{n},AST-{n},2026-02-0{n}T08:00:00,2026-02-0{n}T18:00:00\n"
        rate_cards += f"AGR-{n},700,week\n"
        billing += f"BILL-{n},AGR-{n},400,ISSUED\n"
    files = [
        UploadedFile("events.csv", events.encode()),
        UploadedFile("rate_cards.csv", rate_cards.encode()),
        UploadedFile("billing.csv", billing.encode()),
    ]
    _, run_id = _run_case(db, tmp_path, org.id, files, "Derived duration unit mismatch")

    findings = list(
        db.scalars(
            select(Finding).where(
                Finding.organization_id == org.id, Finding.definition_code == _RULE_CODE
            )
        ).all()
    )
    assert findings == []
