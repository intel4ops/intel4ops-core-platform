"""P3.xxV.2K (Fix #8, DC-3): Trust's request schema caps assessed records at
MAX_ASSESSMENT_RECORDS (app/schemas/trust.py). Before this fix, any dataset
exceeding the cap raised a pydantic ValidationError (a ValueError subclass)
during TrustAssessmentCreate construction, caught by orchestration's generic
`except ValueError`, and silently converted into an unresolved trust status
for that dataset -- indistinguishable, from the outside, from a genuine
data-quality failure. No rule threshold changes; the same rule logic runs
against a deterministic, full-dataset-spanning sample instead of being
skipped outright."""

from pathlib import Path
from uuid import UUID, uuid4

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis_case import AnalysisCaseDataset
from app.models.entities import Organization
from app.schemas.contracts import OrganizationCreate
from app.schemas.trust import MAX_ASSESSMENT_RECORDS
from app.services.analysis_case_orchestration_service import (
    _representative_sample,
    analysis_case_orchestration_service,
)
from app.services.analysis_case_service import AnalysisCaseService, UploadedFile
from app.services.organization_service import OrganizationService
from app.storage.local_storage import LocalFileStorage

# ---------------------------------------------------------------------------
# Unit tests: _representative_sample is a pure function, no DB/case needed.
# ---------------------------------------------------------------------------


def test_sample_is_a_noop_when_already_under_the_cap() -> None:
    df = pd.DataFrame({"x": range(10)})
    result = _representative_sample(df, max_rows=1000)
    assert result is df


def test_sample_is_a_noop_when_exactly_at_the_cap() -> None:
    df = pd.DataFrame({"x": range(1000)})
    result = _representative_sample(df, max_rows=1000)
    assert result is df


def test_sample_downsizes_to_at_most_the_cap() -> None:
    df = pd.DataFrame({"x": range(2500)})
    result = _representative_sample(df, max_rows=1000)
    assert len(result) <= 1000
    assert len(result) > 900  # evenly spaced, not aggressively truncated


def test_sample_spans_the_full_dataframe_not_just_the_head() -> None:
    """The whole point: a sample biased toward early rows would silently
    miss data-quality problems concentrated later in a large export."""
    df = pd.DataFrame({"x": range(5000)})
    result = _representative_sample(df, max_rows=1000)
    values = result["x"].tolist()
    assert min(values) < 100
    assert max(values) > 4900


def test_sample_is_deterministic_across_repeated_calls() -> None:
    df = pd.DataFrame({"x": range(3333)})
    first = _representative_sample(df, max_rows=1000)
    second = _representative_sample(df, max_rows=1000)
    assert first["x"].tolist() == second["x"].tolist()


def test_sample_preserves_row_order() -> None:
    df = pd.DataFrame({"x": range(1500)})
    result = _representative_sample(df, max_rows=1000)
    values = result["x"].tolist()
    assert values == sorted(values)


# ---------------------------------------------------------------------------
# Integration: an over-the-cap maintenance-shaped dataset must still reach a
# resolved trust status end-to-end, through the real orchestration pipeline.
# ---------------------------------------------------------------------------

_OVER_CAP_ROW_COUNT = MAX_ASSESSMENT_RECORDS + 405  # mirrors FIELDMAINT-005's real overage


def _large_maintenance_csv() -> UploadedFile:
    header = "event_id,asset_id,work_order_id,event_type,scheduled_date,completed_date\n"
    rows = [header]
    for i in range(_OVER_CAP_ROW_COUNT):
        rows.append(
            f"EVT-{i},A-{i % 25},WO-{i},repair,"
            f"2026-01-{(i % 28) + 1:02d}T08:00:00,2026-01-{(i % 28) + 1:02d}T12:00:00\n"
        )
    return UploadedFile("maintenance_events.csv", "".join(rows).encode())


def _organization(db: Session, slug: str) -> Organization:
    return OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug.title(), slug=slug, country_code="US", default_currency="USD", timezone="UTC"
        ),
    )


def _run_case(db: Session, tmp_path: Path, org_id: UUID) -> tuple[UUID, UUID]:
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    actor = uuid4()
    case = service.create(db, org_id, "Trust Sampling Over-Cap Case", "single", actor)
    service.register_artifacts(db, org_id, case.id, [_large_maintenance_csv()], actor)
    run = analysis_case_orchestration_service.start_run(db, org_id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org_id, case.id, run.id, actor)
    return case.id, run.id


def test_over_cap_dataset_still_resolves_domain_as_maintenance(db: Session, tmp_path: Path) -> None:
    org = _organization(db, "trust-sampling-domain")
    case_id, _ = _run_case(db, tmp_path, org.id)
    dataset = db.scalar(
        select(AnalysisCaseDataset).where(AnalysisCaseDataset.analysis_case_id == case_id)
    )
    assert dataset is not None
    assert dataset.row_count == _OVER_CAP_ROW_COUNT
    assert dataset.detected_domain == "maintenance"


def test_over_cap_dataset_still_resolves_trust(db: Session, tmp_path: Path) -> None:
    """The actual DC-3 proof: before this fix, a dataset this large never
    obtained a resolved trust_assessment_id at all -- it silently hit the
    generic ValueError branch. After the fix, a representative sample is
    assessed instead and the dataset ends up with a real, queryable
    assessment, regardless of that assessment's own pass/warn/fail score."""
    org = _organization(db, "trust-sampling-resolves")
    case_id, _ = _run_case(db, tmp_path, org.id)
    dataset = db.scalar(
        select(AnalysisCaseDataset).where(AnalysisCaseDataset.analysis_case_id == case_id)
    )
    assert dataset is not None
    assert dataset.trust_assessment_id is not None
    assert dataset.trust_status != "not_assessed"
