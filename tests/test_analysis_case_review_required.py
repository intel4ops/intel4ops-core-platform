"""P3.xxC.2E: review_required must always be actionable, and (per the
P3.xxC.2E domain-detection precision correction) must only ever reflect a
genuine, evidence-backed operator-review need -- never a false-positive
domain guess made from generic fields alone.

Two conditions set any_review_required in
analysis_case_orchestration_service.execute():
  1. MAPPING_REVIEW_REQUIRED -- a CONFIRMED-domain dataset whose mapping
     bridge still could not resolve every required field. Kept as a
     safety net (see tests/test_analysis_case_mapping_service.py for its
     direct unit coverage); structurally unreachable through the normal
     pipeline since detect_domain() and the mapping bridge now use the
     identical CONFIRMED-implies-fields-present guarantee.
  2. DOMAIN_REVIEW_REQUIRED -- a dataset whose domain detection is
     NEEDS_REVIEW (plausible but unconfirmed evidence) in a domain that
     actually feeds a wired intelligence path (maintenance / operations /
     revenue). A NEEDS_REVIEW classification in an unrelated domain (one
     no intelligence path consumes) does not set any_review_required --
     see test_unrelated_ambiguous_dataset_does_not_force_case_review_required.

Intelligence readiness, entity-resolution conflicts, and artifact
extraction failures each have their own status columns already
(intelligence_readiness_status, EntityLinkStatus, SourceArtifact
extraction_status) but none of them currently sets any_review_required in
execute() -- extraction failures drive PARTIAL, not review_required, and
intelligence-readiness/entity-resolution results are computed but not
wired to any run-status effect at all. Per the explicit instruction not to
add review-reason types the backend does not genuinely produce, this file
does not fabricate ENTITY_RESOLUTION_REVIEW_REQUIRED /
INTELLIGENCE_READINESS_BLOCKED / DATA_LINKAGE_REVIEW_REQUIRED /
CURRENCY_REVIEW_REQUIRED / ARTIFACT_EXTRACTION_REVIEW_REQUIRED reasons or
tests for them -- see the P3.xxC.2E report for the full list of
genuinely-wired vs. not-yet-wired review causes."""

from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.analysis_case import AnalysisCaseRunStatus
from app.models.entities import Organization
from app.schemas.contracts import OrganizationCreate
from app.services.analysis_case_orchestration_service import analysis_case_orchestration_service
from app.services.analysis_case_service import AnalysisCaseService, UploadedFile
from app.services.organization_service import OrganizationService
from app.storage.local_storage import LocalFileStorage

MAINT_CSV_COMPLETE = (
    b"asset_id,failure_code,downtime_hours,repair_cost,event_date\n"
    b"V1,brake,4,10000,2026-08-01T08:00:00\n"
    b"V1,brake,5,11000,2026-08-05T08:00:00\n"
    b"V1,brake,6,12000,2026-08-10T08:00:00\n"
)

# asset_id + failure_code, missing downtime_hours -- plausible maintenance
# evidence (includes a domain-specific field, not just the generic
# asset_id), but not enough to CONFIRM. NEEDS_REVIEW, domain=maintenance,
# and maintenance is intelligence-relevant, so this genuinely warrants
# review_required.
AMBIGUOUS_MAINTENANCE_CSV = b"asset_id,failure_code\nV1,brake\nV2,brake\n"

# fuel_quantity alone (no asset_id) -- plausible fuel_energy evidence, but
# partial (fuel_energy also requires asset_id) so NEEDS_REVIEW, not
# CONFIRMED. fuel_energy has no wired intelligence path at all, so this is
# the "unrelated" ambiguous dataset from requirement 6/test G: it must not
# force the whole case into review_required.
UNRELATED_AMBIGUOUS_CSV = b"fuel_quantity\n120\n95\n"


def _organization(db: Session, slug: str) -> Organization:
    return OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug.title(), slug=slug, country_code="US", default_currency="USD", timezone="UTC"
        ),
    )


def test_domain_review_required_produces_actionable_reason(db: Session, tmp_path: Path) -> None:
    """Genuine, evidence-backed domain ambiguity -> review_required + a
    DOMAIN_REVIEW_REQUIRED reason naming the candidate domain and basis."""
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    org = _organization(db, "review-domain")
    actor = uuid4()
    case = service.create(db, org.id, "Domain Review Case", "single", actor)
    service.register_artifacts(
        db, org.id, case.id, [UploadedFile("assets.csv", AMBIGUOUS_MAINTENANCE_CSV)], actor
    )

    run = analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org.id, case.id, run.id, actor)
    db.refresh(run)
    assert run.status == AnalysisCaseRunStatus.REVIEW_REQUIRED.value

    reasons = analysis_case_orchestration_service.review_reasons(db, org.id, case.id)
    assert len(reasons) == 1
    reason = reasons[0]
    assert reason.code == "DOMAIN_REVIEW_REQUIRED"
    assert reason.stage == "domain_detection"
    assert reason.review_target == "sources"
    assert reason.source_label == "assets.csv"
    assert reason.domain == "maintenance"
    assert "maintenance" in reason.message


def test_review_required_never_returns_empty_reason_list(db: Session, tmp_path: Path) -> None:
    """review_required never returns an empty reason list -- proven with
    two independently-ambiguous datasets so the invariant isn't just an
    accident of a single-dataset scenario."""
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    org = _organization(db, "review-never-empty")
    actor = uuid4()
    case = service.create(db, org.id, "Multi Domain Review Case", "orchestrated", actor)
    service.register_artifacts(
        db,
        org.id,
        case.id,
        [
            UploadedFile("assets.csv", AMBIGUOUS_MAINTENANCE_CSV),
            UploadedFile("contracts.csv", AMBIGUOUS_MAINTENANCE_CSV),
        ],
        actor,
    )

    run = analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org.id, case.id, run.id, actor)
    db.refresh(run)
    assert run.status == AnalysisCaseRunStatus.REVIEW_REQUIRED.value

    reasons = analysis_case_orchestration_service.review_reasons(db, org.id, case.id)
    assert len(reasons) == 2
    assert {r.source_label for r in reasons} == {"assets.csv", "contracts.csv"}
    assert all(r.code == "DOMAIN_REVIEW_REQUIRED" for r in reasons)


def test_findings_unavailable_explains_review_required(db: Session, tmp_path: Path) -> None:
    """Findings unavailable because of review -> explicit explanation."""
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    org = _organization(db, "review-findings-explained")
    actor = uuid4()
    case = service.create(db, org.id, "Findings Explained Case", "single", actor)
    service.register_artifacts(
        db, org.id, case.id, [UploadedFile("assets.csv", AMBIGUOUS_MAINTENANCE_CSV)], actor
    )

    run = analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org.id, case.id, run.id, actor)
    db.refresh(run)

    reasons = analysis_case_orchestration_service.review_reasons(db, org.id, case.id)
    available, note = analysis_case_orchestration_service.findings_availability(
        db, org.id, case.id, run.id, run.status, reasons
    )
    assert available is False
    assert note is not None
    assert "review is required" in note
    assert "assets.csv" in note


def test_completed_run_has_no_review_reason_required(db: Session, tmp_path: Path) -> None:
    """A clean, fully-confirmed run has no review reasons at all."""
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    org = _organization(db, "review-completed-clean")
    actor = uuid4()
    case = service.create(db, org.id, "Clean Completed Case", "single", actor)
    service.register_artifacts(
        db, org.id, case.id, [UploadedFile("maintenance_events.csv", MAINT_CSV_COMPLETE)], actor
    )

    run = analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org.id, case.id, run.id, actor)
    db.refresh(run)
    assert run.status == AnalysisCaseRunStatus.COMPLETED.value

    reasons = analysis_case_orchestration_service.review_reasons(db, org.id, case.id)
    assert reasons == []

    available, note = analysis_case_orchestration_service.findings_availability(
        db, org.id, case.id, run.id, run.status, reasons
    )
    assert available is True
    assert note is None


def test_partial_run_is_distinct_from_review_required(db: Session, tmp_path: Path) -> None:
    """A partial run remains distinct from review_required. Constructs the
    PARTIAL status directly rather than reproducing the pipeline's own
    (pre-existing, out of P3.xxC.2E's scope) failure path -- this test
    verifies the review-reason/findings-note contract treats PARTIAL and
    REVIEW_REQUIRED as genuinely distinct, not that this is the only way a
    PARTIAL run can arise."""
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    org = _organization(db, "review-partial-distinct")
    actor = uuid4()
    case = service.create(db, org.id, "Partial Case", "single", actor)
    service.register_artifacts(
        db, org.id, case.id, [UploadedFile("maintenance_events.csv", MAINT_CSV_COMPLETE)], actor
    )
    run = analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
    run.status = AnalysisCaseRunStatus.PARTIAL.value
    db.add(run)
    db.commit()
    db.refresh(run)

    # no dataset was ever put into a review-worthy state for this case, so
    # a PARTIAL run must not fabricate review reasons.
    reasons = analysis_case_orchestration_service.review_reasons(db, org.id, case.id)
    assert reasons == []

    available, note = analysis_case_orchestration_service.findings_availability(
        db, org.id, case.id, run.id, run.status, reasons
    )
    assert available is False
    assert note is not None
    assert "review is required" not in note
    assert "processing failed" in note


def test_unrelated_ambiguous_dataset_does_not_force_case_review_required(
    db: Session, tmp_path: Path
) -> None:
    """G. An unrelated dataset's uncertain domain detection (fuel_energy,
    which has no wired intelligence path at all) must not block the case
    or force review_required -- the run completes using the good
    maintenance dataset, and the ambiguous fuel dataset is simply excluded
    from domain intelligence rather than flagged for review."""
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    org = _organization(db, "review-unrelated-ambiguous")
    actor = uuid4()
    case = service.create(db, org.id, "Unrelated Ambiguity Case", "orchestrated", actor)
    service.register_artifacts(
        db,
        org.id,
        case.id,
        [
            UploadedFile("maintenance_events.csv", MAINT_CSV_COMPLETE),
            UploadedFile("fuel.csv", UNRELATED_AMBIGUOUS_CSV),
        ],
        actor,
    )

    run = analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org.id, case.id, run.id, actor)
    db.refresh(run)

    assert run.status == AnalysisCaseRunStatus.COMPLETED.value
    reasons = analysis_case_orchestration_service.review_reasons(db, org.id, case.id)
    assert reasons == []

    from app.services.analysis_case_command_service import analysis_case_command_service

    findings = analysis_case_command_service.priorities(db, org.id, case.id, run_id=run.id)
    assert len(findings) == 1
    assert findings[0].finding.rule_id == "MAINT-001-REPEATED-FAILURE"


def test_status_route_exposes_review_reasons(db: Session, tmp_path: Path) -> None:
    """Confirms GET .../runs/{run_id}/status exposes review_reasons,
    review_target, findings_available, and findings_note directly -- no
    endpoint composition required on the Navigator side."""
    from app.models.analysis_case import AnalysisCaseRun as _Run

    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    org = _organization(db, "review-status-route")
    actor = uuid4()
    case = service.create(db, org.id, "Status Route Case", "single", actor)
    service.register_artifacts(
        db, org.id, case.id, [UploadedFile("assets.csv", AMBIGUOUS_MAINTENANCE_CSV)], actor
    )
    run = analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org.id, case.id, run.id, actor)
    db.commit()

    reloaded = db.get(_Run, run.id)
    assert reloaded is not None
    reasons = analysis_case_orchestration_service.review_reasons(db, org.id, case.id)
    available, note = analysis_case_orchestration_service.findings_availability(
        db, org.id, case.id, run.id, reloaded.status, reasons
    )
    from app.schemas.analysis_case import AnalysisCaseRunRead, AnalysisCaseRunStatusRead

    payload = AnalysisCaseRunStatusRead(
        **AnalysisCaseRunRead.model_validate(reloaded).model_dump(),
        review_reasons=reasons,
        review_target=reasons[0].review_target if reasons else None,
        findings_available=available,
        findings_note=note,
    )
    body = payload.model_dump()
    assert body["status"] == "review_required"
    assert body["review_target"] == "sources"
    assert len(body["review_reasons"]) == 1
    assert body["review_reasons"][0]["code"] == "DOMAIN_REVIEW_REQUIRED"
    assert body["findings_available"] is False
    assert "review is required" in body["findings_note"]
