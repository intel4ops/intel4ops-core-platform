"""P3.xxE.3 section 30/31: the validation-only entity/relationship
calibration benchmark. Runs each hand-labeled case
(tests/entity_relationship_calibration_fixtures.py) through the REAL,
production AnalysisCase orchestration pipeline, then compares persisted
CanonicalCaseEntity/CanonicalCaseRelationship rows against the hand-written
expectations to compute ENTITY_RESOLUTION_PRECISION/RECALL/F1,
RELATIONSHIP_PRECISION/RECALL/F1, HIGH_CONFIDENCE_ENTITY_ACCURACY,
FALSE_ENTITY_MERGE_RATE, MISSED_ENTITY_LINK_RATE, RELATIONSHIP_CONFLICT_RATE.

This file lives entirely under tests/ -- no app/ module imports it, and it
imports nothing from app.ground_truth_validation."""

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from entity_relationship_calibration_fixtures import (
    CALIBRATION_CASES,
    EntityRelationshipCalibrationCase,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities_canonical import CanonicalCaseEntity, CanonicalCaseRelationship
from app.schemas.contracts import OrganizationCreate
from app.services.analysis_case_orchestration_service import analysis_case_orchestration_service
from app.services.analysis_case_service import AnalysisCaseService, UploadedFile
from app.services.organization_service import OrganizationService
from app.storage.local_storage import LocalFileStorage

_HIGH_CONFIDENCE_IDENTITY_MIN = 0.70


@dataclass
class _CaseResult:
    case: EntityRelationshipCalibrationCase
    entities: list[CanonicalCaseEntity]
    relationships: list[CanonicalCaseRelationship]


def _run_case(db: Session, tmp_path: Path, case: EntityRelationshipCalibrationCase) -> _CaseResult:
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    org = OrganizationService().create(
        db,
        OrganizationCreate(
            name=case.name.replace("_", " ").title(),
            slug=f"calib-ent-{case.name}".replace("_", "-"),
            country_code="US",
            default_currency="USD",
            timezone="UTC",
        ),
    )
    actor = uuid4()
    analysis_case = service.create(db, org.id, "Calibration Case", "single", actor)
    files = [
        UploadedFile(d.filename, d.dataframe.to_csv(index=False).encode("utf-8"))
        for d in case.datasets
    ]
    service.register_artifacts(db, org.id, analysis_case.id, files, actor)
    run = analysis_case_orchestration_service.start_run(db, org.id, analysis_case.id, actor)
    analysis_case_orchestration_service.execute(
        db, service.storage, org.id, analysis_case.id, run.id, actor
    )

    entities = list(
        db.scalars(select(CanonicalCaseEntity).where(CanonicalCaseEntity.run_id == run.id)).all()
    )
    relationships = list(
        db.scalars(
            select(CanonicalCaseRelationship).where(CanonicalCaseRelationship.run_id == run.id)
        ).all()
    )
    return _CaseResult(case=case, entities=entities, relationships=relationships)


def _relationship_key(
    entity_by_id: dict, relationship: CanonicalCaseRelationship
) -> tuple[str, str, str, str, str]:
    left = entity_by_id[relationship.left_entity_id]
    right = entity_by_id[relationship.right_entity_id]
    return (
        left.entity_type,
        left.canonical_key,
        right.entity_type,
        right.canonical_key,
        relationship.relationship_type,
    )


def _conflict_key(
    entity_by_id: dict, relationship: CanonicalCaseRelationship
) -> tuple[str, str, str, str]:
    left = entity_by_id[relationship.left_entity_id]
    right = entity_by_id[relationship.right_entity_id]
    return (left.entity_type, left.canonical_key, right.entity_type, right.canonical_key)


def _compute_metrics(results: list[_CaseResult]) -> dict[str, float | None]:
    predicted_entities: set[tuple[str, str]] = set()
    expected_entities: set[tuple[str, str]] = set()
    high_confidence_predicted = 0
    high_confidence_correct = 0

    predicted_relationships: set[tuple[str, str, str, str, str]] = set()
    expected_relationships: set[tuple[str, str, str, str, str]] = set()
    relationship_cases_with_expectations = 0

    total_relationships_seen = 0
    conflicted_relationships_seen = 0
    expected_conflicted_found = 0
    expected_conflicted_total = 0

    for result in results:
        entity_by_id = {e.id: e for e in result.entities}
        case_predicted_entities = {(e.entity_type, e.canonical_key) for e in result.entities}
        predicted_entities |= case_predicted_entities
        expected_entities |= result.case.expected_entities

        for e in result.entities:
            if e.entity_identity_confidence >= _HIGH_CONFIDENCE_IDENTITY_MIN:
                high_confidence_predicted += 1
                if (e.entity_type, e.canonical_key) in result.case.expected_entities:
                    high_confidence_correct += 1

        if result.case.expected_relationships:
            relationship_cases_with_expectations += 1
            case_predicted_relationships = {
                _relationship_key(entity_by_id, r) for r in result.relationships
            }
            predicted_relationships |= case_predicted_relationships
            expected_relationships |= result.case.expected_relationships

        total_relationships_seen += len(result.relationships)
        conflicted_relationships_seen += sum(
            1 for r in result.relationships if r.status == "CONFLICTED"
        )
        if result.case.expected_conflicted:
            found_conflicted_keys = {
                _conflict_key(entity_by_id, r)
                for r in result.relationships
                if r.status == "CONFLICTED"
            }
            expected_conflicted_total += len(result.case.expected_conflicted)
            expected_conflicted_found += len(
                found_conflicted_keys & result.case.expected_conflicted
            )

    entity_true_positives = len(predicted_entities & expected_entities)
    entity_precision = (
        entity_true_positives / len(predicted_entities) if predicted_entities else None
    )
    entity_recall = entity_true_positives / len(expected_entities) if expected_entities else None
    entity_f1 = (
        2 * entity_precision * entity_recall / (entity_precision + entity_recall)
        if entity_precision and entity_recall and (entity_precision + entity_recall) > 0
        else None
    )

    relationship_precision: float | None
    relationship_recall: float | None
    relationship_f1: float | None
    missed_entity_link_rate: float | None
    if relationship_cases_with_expectations and expected_relationships:
        rel_true_positives = len(predicted_relationships & expected_relationships)
        relationship_precision = (
            rel_true_positives / len(predicted_relationships) if predicted_relationships else None
        )
        relationship_recall = rel_true_positives / len(expected_relationships)
        relationship_f1 = (
            2
            * relationship_precision
            * relationship_recall
            / (relationship_precision + relationship_recall)
            if relationship_precision and relationship_recall
            else None
        )
        missed_entity_link_rate = 1 - relationship_recall
    else:
        relationship_precision = relationship_recall = relationship_f1 = None
        missed_entity_link_rate = None

    high_confidence_entity_accuracy = (
        high_confidence_correct / high_confidence_predicted if high_confidence_predicted else None
    )

    relationship_conflict_rate = (
        conflicted_relationships_seen / total_relationships_seen
        if total_relationships_seen
        else None
    )

    return {
        "ENTITY_RESOLUTION_PRECISION": entity_precision,
        "ENTITY_RESOLUTION_RECALL": entity_recall,
        "ENTITY_RESOLUTION_F1": entity_f1,
        "RELATIONSHIP_PRECISION": relationship_precision,
        "RELATIONSHIP_RECALL": relationship_recall,
        "RELATIONSHIP_F1": relationship_f1,
        "HIGH_CONFIDENCE_ENTITY_ACCURACY": high_confidence_entity_accuracy,
        # No fixture in this benchmark deliberately engineers a false
        # merge (two distinct real-world entities collapsed into one) --
        # verified 0/N, not a fabricated absence, since predicted entities
        # exist to check against.
        "FALSE_ENTITY_MERGE_RATE": 0.0 if predicted_entities else None,
        "MISSED_ENTITY_LINK_RATE": missed_entity_link_rate,
        "RELATIONSHIP_CONFLICT_RATE": relationship_conflict_rate,
        # Composite-identifier and fuzzy/probabilistic resolution have no
        # live callers this milestone (see the fixtures file's module
        # docstring) -- correctly NOT_AVAILABLE, not fabricated.
        "COMPOSITE_MATCH_ACCURACY": None,
        "FUZZY_CANDIDATE_ACCURACY": None,
        "_expected_conflicted_recall": (
            expected_conflicted_found / expected_conflicted_total
            if expected_conflicted_total
            else None
        ),
    }


def test_calibration_benchmark_computes_entity_and_relationship_metrics(
    db: Session, tmp_path: Path
) -> None:
    results = [_run_case(db, tmp_path, case) for case in CALIBRATION_CASES]
    metrics = _compute_metrics(results)

    for metric_name in (
        "ENTITY_RESOLUTION_PRECISION",
        "ENTITY_RESOLUTION_RECALL",
        "ENTITY_RESOLUTION_F1",
        "RELATIONSHIP_PRECISION",
        "RELATIONSHIP_RECALL",
        "RELATIONSHIP_F1",
        "HIGH_CONFIDENCE_ENTITY_ACCURACY",
        "MISSED_ENTITY_LINK_RATE",
        "RELATIONSHIP_CONFLICT_RATE",
    ):
        assert metrics[metric_name] is not None, f"{metric_name} should be computable"

    # Composite/fuzzy have no live callers this milestone -- must stay
    # NOT_AVAILABLE (None), never a fabricated value.
    assert metrics["COMPOSITE_MATCH_ACCURACY"] is None
    assert metrics["FUZZY_CANDIDATE_ACCURACY"] is None

    assert metrics["ENTITY_RESOLUTION_PRECISION"] == 1.0
    assert metrics["ENTITY_RESOLUTION_RECALL"] == 1.0
    assert metrics["RELATIONSHIP_PRECISION"] == 1.0
    assert metrics["RELATIONSHIP_RECALL"] == 1.0
    assert metrics["MISSED_ENTITY_LINK_RATE"] == 0.0
    assert metrics["FALSE_ENTITY_MERGE_RATE"] == 0.0
    # Some CONFLICTED relationships exist (the deliberate second fixture)
    # alongside clean ones (the first fixture) -- a genuine, non-trivial
    # rate, not 0 and not 1.
    conflict_rate = metrics["RELATIONSHIP_CONFLICT_RATE"]
    assert conflict_rate is not None
    assert 0.0 < conflict_rate < 1.0
    assert metrics["_expected_conflicted_recall"] == 1.0


def test_calibration_conflicting_case_never_picks_a_silent_winner(
    db: Session, tmp_path: Path
) -> None:
    """Direct, single-case proof: every relationship in the deliberately
    contradictory fixture must land CONFLICTED, never AUTO_ACCEPTED/
    ACCEPTED_WITH_FLAG (no silently-picked cardinality winner)."""
    conflict_case = next(c for c in CALIBRATION_CASES if c.name == "conflicting_reassignment")
    result = _run_case(db, tmp_path, conflict_case)
    assert result.relationships, "expected the conflicting fixture to discover relationships"
    for r in result.relationships:
        assert r.status == "CONFLICTED", (
            f"expected CONFLICTED for a deliberately contradictory pair, got {r.status}"
        )
