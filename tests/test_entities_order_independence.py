"""P3.xxE.3 section 23 (required): entity/relationship resolution must be
invariant to dataset-processing order. Same pattern as
tests/test_semantic_cross_dataset_context.py's Part B -- the real
AnalysisCase orchestration is run twice with reversed dataset registration
order, and the resulting CanonicalCaseEntity/CanonicalCaseRelationship sets
(keyed by content, not id/created_at) must be identical.

Fixture shape note: asset_id/work_order_id need enough distinct values
(high uniqueness) and genuine cross-dataset corroboration to naturally
clear the deterministic confidence engine's auto_accept threshold (0.90)
-- small hand-typed fixtures otherwise cap out around accepted_with_flag
(~0.85) and produce zero typed entities, which was confirmed directly
against app.semantic.interpreter.interpret_dataset before settling on
this shape."""

from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Organization
from app.models.entities_canonical import CanonicalCaseEntity, CanonicalCaseRelationship
from app.schemas.contracts import OrganizationCreate
from app.services.analysis_case_orchestration_service import analysis_case_orchestration_service
from app.services.analysis_case_service import AnalysisCaseService, UploadedFile
from app.services.organization_service import OrganizationService
from app.storage.local_storage import LocalFileStorage


def _events_csv() -> bytes:
    rows = [f"A-{i % 10},WO-{i},2026-0{(i % 9) + 1}-0{(i % 9) + 1}" for i in range(1, 31)]
    return ("asset_id,work_order_id,event_date\n" + "\n".join(rows) + "\n").encode()


def _work_orders_csv() -> bytes:
    rows = [f"WO-{i},A-{i % 10},T-{i % 3}" for i in range(1, 16)]
    return ("work_order_id,asset_id,technician_id\n" + "\n".join(rows) + "\n").encode()


EVENTS_CSV = _events_csv()
WORK_ORDERS_CSV = _work_orders_csv()


def _organization(db: Session, slug: str) -> Organization:
    return OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug.title(), slug=slug, country_code="US", default_currency="USD", timezone="UTC"
        ),
    )


def _run_case_with_order(
    db: Session, tmp_path: Path, slug: str, filenames_in_order: list[str]
) -> tuple[set[tuple[str, str]], set[tuple[str, str, str, str, str]]]:
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    org = _organization(db, slug)
    actor = uuid4()
    case = service.create(db, org.id, "Case", "single", actor)
    files_by_name = {
        "events.csv": UploadedFile("events.csv", EVENTS_CSV),
        "work_orders.csv": UploadedFile("work_orders.csv", WORK_ORDERS_CSV),
    }
    service.register_artifacts(
        db, org.id, case.id, [files_by_name[name] for name in filenames_in_order], actor
    )
    run = analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org.id, case.id, run.id, actor)

    entities = list(
        db.scalars(select(CanonicalCaseEntity).where(CanonicalCaseEntity.run_id == run.id)).all()
    )
    entity_keys = {(e.entity_type, e.canonical_key) for e in entities}
    by_id = {e.id: (e.entity_type, e.canonical_key) for e in entities}

    relationships = list(
        db.scalars(
            select(CanonicalCaseRelationship).where(CanonicalCaseRelationship.run_id == run.id)
        ).all()
    )
    relationship_keys = {
        (*by_id[r.left_entity_id], *by_id[r.right_entity_id], r.relationship_type)
        for r in relationships
    }
    return entity_keys, relationship_keys


def test_entity_and_relationship_resolution_is_order_independent(
    db: Session, tmp_path: Path
) -> None:
    forward_entities, forward_relationships = _run_case_with_order(
        db, tmp_path, "entities-order-a", ["events.csv", "work_orders.csv"]
    )
    reversed_entities, reversed_relationships = _run_case_with_order(
        db, tmp_path, "entities-order-b", ["work_orders.csv", "events.csv"]
    )

    assert forward_entities, "expected at least one resolved entity in the forward-order run"
    assert forward_entities == reversed_entities, (
        f"entity set differed by dataset-processing order: "
        f"{forward_entities} vs {reversed_entities}"
    )
    assert forward_relationships, "expected at least one discovered relationship"
    assert forward_relationships == reversed_relationships, (
        f"relationship set differed by dataset-processing order: "
        f"{forward_relationships} vs {reversed_relationships}"
    )
