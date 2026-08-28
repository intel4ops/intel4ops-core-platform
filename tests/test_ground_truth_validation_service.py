"""P3.xxD.1B core Validation Plane service tests: simulation creation,
ground-truth upload/versioning, the semantic (not literal-text) matcher,
and end-to-end validate_run scoring."""

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.ground_truth_validation.normalizer import GroundTruthFormatError, normalize_ground_truth
from app.ground_truth_validation.service import ValidationServiceError, validation_service
from app.models.entities import Organization
from app.schemas.contracts import OrganizationCreate
from app.services.analysis_case_orchestration_service import analysis_case_orchestration_service
from app.services.analysis_case_service import AnalysisCaseService, UploadedFile
from app.services.organization_service import OrganizationService
from app.storage.local_storage import LocalFileStorage

MAINT_CSV = (
    b"asset_id,failure_code,downtime_hours,repair_cost,event_date\n"
    b"V1,brake,4,10000,2026-08-01T08:00:00\n"
    b"V1,brake,5,11000,2026-08-05T08:00:00\n"
    b"V1,brake,6,12000,2026-08-10T08:00:00\n"
)


def _organization(db: Session, slug: str) -> Organization:
    return OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug.title(), slug=slug, country_code="US", default_currency="USD", timezone="UTC"
        ),
    )


def _completed_run(db: Session, tmp_path: Path, org_slug: str) -> tuple:
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    org = _organization(db, org_slug)
    actor = uuid4()
    case = service.create(db, org.id, "Case", "single", actor)
    service.register_artifacts(
        db, org.id, case.id, [UploadedFile("maintenance_events.csv", MAINT_CSV)], actor
    )
    run = analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org.id, case.id, run.id, actor)
    db.refresh(run)
    return org, actor, case, run


# ---------------------------------------------------------------------------
# Normalizer
# ---------------------------------------------------------------------------


def test_normalizer_accepts_a_well_formed_payload() -> None:
    result = normalize_ground_truth(
        {
            "expected_findings": [
                {
                    "expected_finding_code": "EXP-001",
                    "domain": "maintenance",
                    "severity": "high",
                    "entities": [{"entity_type": "asset", "canonical_key": "V1"}],
                    "evidence_refs": ["maintenance_events.csv"],
                    "expected_economic_impact": 33000,
                    "currency": "USD",
                }
            ],
            "expected_clean_areas": ["revenue"],
            "tolerance": {"economic_variance_pct": 15},
        }
    )
    assert len(result.expected_findings) == 1
    assert result.expected_findings[0].domain == "maintenance"
    assert result.expected_clean_areas == ["revenue"]


def test_normalizer_rejects_duplicate_expected_finding_codes() -> None:
    with pytest.raises(GroundTruthFormatError):
        normalize_ground_truth(
            {
                "expected_findings": [
                    {
                        "expected_finding_code": "EXP-001",
                        "domain": "maintenance",
                        "severity": "high",
                    },
                    {"expected_finding_code": "EXP-001", "domain": "revenue", "severity": "low"},
                ]
            }
        )


def test_normalizer_rejects_missing_required_field() -> None:
    with pytest.raises(GroundTruthFormatError):
        normalize_ground_truth(
            {"expected_findings": [{"domain": "maintenance", "severity": "high"}]}
        )


# ---------------------------------------------------------------------------
# Simulation + ground truth lifecycle
# ---------------------------------------------------------------------------


def test_create_simulation_requires_a_real_analysis_case(db: Session) -> None:
    org = _organization(db, "gtv-no-case")
    with pytest.raises(ValidationServiceError) as excinfo:
        validation_service.create_simulation(db, org.id, "SIM-X", "X", uuid4(), uuid4())
    assert excinfo.value.code == "case_not_found"


def test_simulation_code_is_unique_per_organization(db: Session, tmp_path: Path) -> None:
    org, actor, case, _run = _completed_run(db, tmp_path, "gtv-dup-code")
    validation_service.create_simulation(db, org.id, "SIM-DUP-001", "First", case.id, actor)
    with pytest.raises(ValidationServiceError) as excinfo:
        validation_service.create_simulation(db, org.id, "SIM-DUP-001", "Second", case.id, actor)
    assert excinfo.value.code == "simulation_code_conflict"


def test_ground_truth_uploads_are_versioned_and_immutable(db: Session, tmp_path: Path) -> None:
    org, actor, case, _run = _completed_run(db, tmp_path, "gtv-versioning")
    simulation = validation_service.create_simulation(
        db, org.id, "SIM-VERSION-001", "Versioning", case.id, actor
    )
    payload: dict[str, object] = {
        "expected_findings": [
            {"expected_finding_code": "EXP-001", "domain": "maintenance", "severity": "high"}
        ]
    }
    v1 = validation_service.upload_ground_truth(db, org.id, simulation.id, payload, actor)
    assert v1.version == 1
    v2 = validation_service.upload_ground_truth(db, org.id, simulation.id, payload, actor)
    assert v2.version == 2

    v1.checksum = "tampered"
    with pytest.raises(ValueError, match="immutable"):
        db.commit()
    db.rollback()


def test_upload_ground_truth_rejects_malformed_payload(db: Session, tmp_path: Path) -> None:
    org, actor, case, _run = _completed_run(db, tmp_path, "gtv-malformed")
    simulation = validation_service.create_simulation(
        db, org.id, "SIM-MALFORMED-001", "Malformed", case.id, actor
    )
    with pytest.raises(ValidationServiceError) as excinfo:
        validation_service.upload_ground_truth(db, org.id, simulation.id, {"nope": True}, actor)
    assert excinfo.value.code == "ground_truth_format_error"


def test_validate_run_requires_ground_truth_to_exist(db: Session, tmp_path: Path) -> None:
    org, actor, case, run = _completed_run(db, tmp_path, "gtv-no-ground-truth")
    simulation = validation_service.create_simulation(
        db, org.id, "SIM-NO-GT-001", "No GT", case.id, actor
    )
    with pytest.raises(ValidationServiceError) as excinfo:
        validation_service.validate_run(db, org.id, simulation.id, run.id, actor)
    assert excinfo.value.code == "ground_truth_missing"


# ---------------------------------------------------------------------------
# Matcher/scoring semantics -- TP/FP/FN, precision/recall/F1, and extras
# ---------------------------------------------------------------------------


def test_validate_run_scores_a_true_positive_with_matching_ground_truth(
    db: Session, tmp_path: Path
) -> None:
    org, actor, case, run = _completed_run(db, tmp_path, "gtv-true-positive")
    simulation = validation_service.create_simulation(
        db, org.id, "SIM-TP-001", "True Positive", case.id, actor
    )
    validation_service.upload_ground_truth(
        db,
        org.id,
        simulation.id,
        {
            "expected_findings": [
                {
                    "expected_finding_code": "EXP-001",
                    "domain": "maintenance",
                    "severity": "medium",
                    "entities": [{"entity_type": "asset", "canonical_key": "V1"}],
                    "evidence_refs": ["maintenance_events.csv"],
                }
            ]
        },
        actor,
    )
    _validation_run, score, matches = validation_service.validate_run(
        db, org.id, simulation.id, run.id, actor
    )
    assert score.true_positive_count == 1
    assert score.false_positive_count == 0
    assert score.false_negative_count == 0
    assert score.precision == 1.0
    assert score.recall == 1.0
    assert score.f1 == 1.0
    assert score.severity_accuracy == 1.0
    tp_matches = [m for m in matches if m.match_type == "true_positive"]
    assert len(tp_matches) == 1
    assert tp_matches[0].evidence_match is True


def test_validate_run_scores_a_false_negative_when_expected_finding_missing(
    db: Session, tmp_path: Path
) -> None:
    org, actor, case, run = _completed_run(db, tmp_path, "gtv-false-negative")
    simulation = validation_service.create_simulation(
        db, org.id, "SIM-FN-001", "False Negative", case.id, actor
    )
    validation_service.upload_ground_truth(
        db,
        org.id,
        simulation.id,
        {
            "expected_findings": [
                {
                    "expected_finding_code": "EXP-001",
                    "domain": "maintenance",
                    "severity": "medium",
                    "entities": [{"entity_type": "asset", "canonical_key": "V1"}],
                },
                {
                    # No asset V2 finding ever gets produced by this fixture
                    # -- must be scored as a genuine miss, not silently
                    # dropped.
                    "expected_finding_code": "EXP-002",
                    "domain": "maintenance",
                    "severity": "critical",
                    "entities": [{"entity_type": "asset", "canonical_key": "V2"}],
                },
            ]
        },
        actor,
    )
    _validation_run, score, _matches = validation_service.validate_run(
        db, org.id, simulation.id, run.id, actor
    )
    assert score.true_positive_count == 1
    assert score.false_negative_count == 1
    assert score.recall == 0.5
    # The missed finding was severity=critical -- critical_leakage_recall
    # must reflect that miss, not be silently 1.0.
    assert score.critical_leakage_recall == 0.0


def test_validate_run_scores_a_false_positive_for_unexpected_finding(
    db: Session, tmp_path: Path
) -> None:
    org, actor, case, run = _completed_run(db, tmp_path, "gtv-false-positive")
    simulation = validation_service.create_simulation(
        db, org.id, "SIM-FP-001", "False Positive", case.id, actor
    )
    # Ground truth expects nothing at all -- the real finding the pipeline
    # produced must be scored as a false positive.
    validation_service.upload_ground_truth(
        db,
        org.id,
        simulation.id,
        {
            "expected_findings": [
                {"expected_finding_code": "EXP-UNRELATED", "domain": "revenue", "severity": "low"}
            ]
        },
        actor,
    )
    _validation_run, score, matches = validation_service.validate_run(
        db, org.id, simulation.id, run.id, actor
    )
    assert score.false_positive_count == 1
    assert score.false_negative_count == 1
    fp_matches = [m for m in matches if m.match_type == "false_positive"]
    assert len(fp_matches) == 1
    assert fp_matches[0].expected_finding_id is None
    assert fp_matches[0].actual_finding_id is not None


def test_matcher_uses_semantic_matching_not_literal_text_equality(
    db: Session, tmp_path: Path
) -> None:
    """Ground truth description text is completely different from the
    real finding's title/summary -- domain+entity overlap alone must still
    produce a true positive."""
    org, actor, case, run = _completed_run(db, tmp_path, "gtv-semantic-match")
    simulation = validation_service.create_simulation(
        db, org.id, "SIM-SEMANTIC-001", "Semantic Match", case.id, actor
    )
    validation_service.upload_ground_truth(
        db,
        org.id,
        simulation.id,
        {
            "expected_findings": [
                {
                    "expected_finding_code": "EXP-001",
                    "domain": "maintenance",
                    "severity": "high",
                    "entities": [{"entity_type": "asset", "canonical_key": "V1"}],
                    "description": "Completely different wording than the real finding's title",
                }
            ]
        },
        actor,
    )
    _validation_run, score, _matches = validation_service.validate_run(
        db, org.id, simulation.id, run.id, actor
    )
    assert score.true_positive_count == 1
    # Severity differs (ground truth says high, real finding is medium) --
    # proves the matcher still matched on domain+entity even though
    # severity/text disagree, and correctly flags the severity mismatch
    # rather than silently ignoring it.
    assert score.severity_accuracy == 0.0


def test_get_results_returns_full_history_across_multiple_validation_runs(
    db: Session, tmp_path: Path
) -> None:
    org, actor, case, run = _completed_run(db, tmp_path, "gtv-history")
    simulation = validation_service.create_simulation(
        db, org.id, "SIM-HISTORY-001", "History", case.id, actor
    )
    validation_service.upload_ground_truth(
        db,
        org.id,
        simulation.id,
        {
            "expected_findings": [
                {"expected_finding_code": "EXP-001", "domain": "maintenance", "severity": "medium"}
            ]
        },
        actor,
    )
    validation_service.validate_run(db, org.id, simulation.id, run.id, actor)
    validation_service.validate_run(db, org.id, simulation.id, run.id, actor)

    results = validation_service.get_results(db, org.id, simulation.id)
    assert len(results) == 2
    for _run_row, score_row, matches in results:
        assert score_row is not None
        assert score_row.true_positive_count == 1
        assert matches
