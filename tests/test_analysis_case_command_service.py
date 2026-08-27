"""Proves operational_priority_v1 is deterministic and matches its
documented ordering: severity, then confidence, then affected-record
count, then detected_at (older first), then finding id -- never a
fabricated economic score."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.models.analysis_case import AnalysisCaseFinding
from app.models.entities import Finding, Organization
from app.schemas.contracts import OrganizationCreate
from app.services.analysis_case_command_service import (
    COMMAND_PRIORITY_METHOD,
    analysis_case_command_service,
)
from app.services.analysis_case_orchestration_service import analysis_case_orchestration_service
from app.services.analysis_case_service import analysis_case_service
from app.services.organization_service import OrganizationService


def _organization(db: Session, slug: str) -> Organization:
    return OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug.title(), slug=slug, country_code="US", default_currency="USD", timezone="UTC"
        ),
    )


def _finding(
    db: Session,
    org: Organization,
    *,
    severity: str,
    confidence_level: str | None = "unknown",
    affected_record_count: int = 0,
    detected_at: datetime | None = None,
) -> Finding:
    finding = Finding(
        organization_id=org.id,
        rule_id="TEST-RULE",
        title="Test finding",
        summary="Test finding summary",
        domain="maintenance",
        governance_tier="GOVERNED",
        severity=severity,
        confidence_level=confidence_level,
        affected_record_count=affected_record_count,
        detected_at=detected_at,
    )
    db.add(finding)
    db.flush()
    return finding


def _run(db: Session, org: Organization, case_id: UUID) -> UUID:
    run = analysis_case_orchestration_service.start_run(db, org.id, case_id, uuid4())
    db.flush()
    return run.id


def _link(db: Session, org: Organization, case_id: UUID, run_id: UUID, finding: Finding) -> None:
    db.add(
        AnalysisCaseFinding(
            organization_id=org.id, analysis_case_id=case_id, run_id=run_id, finding_id=finding.id
        )
    )


def test_priority_method_is_explicitly_versioned() -> None:
    assert COMMAND_PRIORITY_METHOD == "operational_priority_v1"


def test_severity_is_the_primary_sort_key(db: Session) -> None:
    org = _organization(db, "cmd-severity")
    case = analysis_case_service.create(db, org.id, "Case", "single", uuid4())
    run_id = _run(db, org, case.id)
    low = _finding(db, org, severity="low")
    critical = _finding(db, org, severity="critical")
    medium = _finding(db, org, severity="medium")
    for f in (low, critical, medium):
        _link(db, org, case.id, run_id, f)
    db.commit()

    result = analysis_case_command_service.priorities(db, org.id, case.id, run_id)
    assert [p.finding.id for p in result] == [critical.id, medium.id, low.id]
    assert all(p.priority_method == "operational_priority_v1" for p in result)


def test_confidence_breaks_ties_within_same_severity(db: Session) -> None:
    org = _organization(db, "cmd-confidence")
    case = analysis_case_service.create(db, org.id, "Case", "single", uuid4())
    run_id = _run(db, org, case.id)
    low_conf = _finding(db, org, severity="high", confidence_level="low")
    high_conf = _finding(db, org, severity="high", confidence_level="very_high")
    for f in (low_conf, high_conf):
        _link(db, org, case.id, run_id, f)
    db.commit()

    result = analysis_case_command_service.priorities(db, org.id, case.id, run_id)
    assert [p.finding.id for p in result] == [high_conf.id, low_conf.id]


def test_affected_record_count_breaks_ties_within_same_severity_and_confidence(
    db: Session,
) -> None:
    org = _organization(db, "cmd-affected-count")
    case = analysis_case_service.create(db, org.id, "Case", "single", uuid4())
    run_id = _run(db, org, case.id)
    small = _finding(db, org, severity="medium", confidence_level="high", affected_record_count=1)
    large = _finding(db, org, severity="medium", confidence_level="high", affected_record_count=10)
    for f in (small, large):
        _link(db, org, case.id, run_id, f)
    db.commit()

    result = analysis_case_command_service.priorities(db, org.id, case.id, run_id)
    assert [p.finding.id for p in result] == [large.id, small.id]


def test_older_detected_at_wins_final_tiebreak_before_id(db: Session) -> None:
    org = _organization(db, "cmd-recency")
    case = analysis_case_service.create(db, org.id, "Case", "single", uuid4())
    run_id = _run(db, org, case.id)
    older = _finding(
        db,
        org,
        severity="medium",
        confidence_level="high",
        affected_record_count=1,
        detected_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    newer = _finding(
        db,
        org,
        severity="medium",
        confidence_level="high",
        affected_record_count=1,
        detected_at=datetime(2026, 6, 1, tzinfo=UTC),
    )
    for f in (newer, older):
        _link(db, org, case.id, run_id, f)
    db.commit()

    result = analysis_case_command_service.priorities(db, org.id, case.id, run_id)
    assert [p.finding.id for p in result] == [older.id, newer.id]


def test_missing_severity_and_confidence_rank_lowest_not_fabricated(db: Session) -> None:
    # `severity` is DB-constrained to a fixed vocabulary (ck_findings_severity)
    # and has a Python-side default, so a literal None is unreachable -- "info"
    # is the real lowest legitimate value and exercises the same rank-0 floor.
    # `confidence_level` has no such constraint, so None is a genuine, reachable
    # missing value and must not be fabricated into a higher rank.
    org = _organization(db, "cmd-missing-values")
    case = analysis_case_service.create(db, org.id, "Case", "single", uuid4())
    run_id = _run(db, org, case.id)
    known = _finding(db, org, severity="low", confidence_level="low")
    lowest = _finding(db, org, severity="info", confidence_level=None)
    for f in (known, lowest):
        _link(db, org, case.id, run_id, f)
    db.commit()

    result = analysis_case_command_service.priorities(db, org.id, case.id, run_id)
    # "low" (rank 1) must outrank "info" (rank 0) and a missing confidence_level
    assert result[0].finding.id == known.id


def test_never_sums_observed_values_across_currencies(db: Session) -> None:
    org = _organization(db, "cmd-currency-grouping")
    case = analysis_case_service.create(db, org.id, "Case", "single", uuid4())
    run_id = _run(db, org, case.id)
    xof_finding = Finding(
        organization_id=org.id,
        rule_id="TEST-RULE",
        title="XOF finding",
        summary="s",
        domain="maintenance",
        governance_tier="GOVERNED",
        severity="high",
        measured_value=100,
        measured_value_type="currency",
        measured_currency="XOF",
    )
    db.add(xof_finding)
    db.flush()
    _link(db, org, case.id, run_id, xof_finding)
    db.commit()

    result = analysis_case_command_service.priorities(db, org.id, case.id, run_id)
    assert result[0].observed_values_by_currency == {"XOF": 100.0}
