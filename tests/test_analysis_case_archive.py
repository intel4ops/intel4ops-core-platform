"""Proves archiving an AnalysisCase is a soft, idempotent, non-destructive
operation: it hides the case from the default list view but never deletes
it or anything it produced, mirroring the existing Finding.archived_at
pattern."""

from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.entities import Organization
from app.schemas.contracts import OrganizationCreate
from app.services.analysis_case_service import analysis_case_service
from app.services.organization_service import OrganizationService


def _organization(db: Session, slug: str) -> Organization:
    return OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug.title(), slug=slug, country_code="US", default_currency="USD", timezone="UTC"
        ),
    )


def test_archive_sets_timestamp_and_actor(db: Session) -> None:
    org = _organization(db, "archive-basic")
    actor = uuid4()
    archiver = uuid4()
    case = analysis_case_service.create(db, org.id, "Case", "single", actor)
    assert case.archived_at is None
    assert case.archived_by_user_id is None

    archived = analysis_case_service.archive(db, org.id, case.id, archiver)
    assert archived.archived_at is not None
    assert archived.archived_by_user_id == archiver


def test_archive_is_idempotent(db: Session) -> None:
    org = _organization(db, "archive-idempotent")
    actor = uuid4()
    case = analysis_case_service.create(db, org.id, "Case", "single", actor)

    first = analysis_case_service.archive(db, org.id, case.id, uuid4())
    first_timestamp = first.archived_at
    first_actor = first.archived_by_user_id

    second = analysis_case_service.archive(db, org.id, case.id, uuid4())
    assert second.archived_at == first_timestamp
    assert second.archived_by_user_id == first_actor


def test_archived_case_excluded_from_default_list_but_included_when_requested(
    db: Session,
) -> None:
    org = _organization(db, "archive-listing")
    actor = uuid4()
    live = analysis_case_service.create(db, org.id, "Live Case", "single", actor)
    to_archive = analysis_case_service.create(db, org.id, "Archived Case", "single", actor)
    analysis_case_service.archive(db, org.id, to_archive.id, uuid4())

    default_listing = analysis_case_service.list_cases(db, org.id)
    assert [c.id for c in default_listing] == [live.id]

    full_listing = analysis_case_service.list_cases(db, org.id, include_archived=True)
    assert {c.id for c in full_listing} == {live.id, to_archive.id}


def test_archived_case_remains_directly_retrievable(db: Session) -> None:
    org = _organization(db, "archive-get")
    actor = uuid4()
    case = analysis_case_service.create(db, org.id, "Case", "single", actor)
    analysis_case_service.archive(db, org.id, case.id, uuid4())

    fetched = analysis_case_service.get(db, org.id, case.id)
    assert fetched.id == case.id
    assert fetched.archived_at is not None
