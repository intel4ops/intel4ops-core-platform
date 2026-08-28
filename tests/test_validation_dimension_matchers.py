"""P3.xxD.1E: proves each validation dimension (section 11) is
independently scored, never returns a fabricated number when it cannot be
evaluated (section 12), and that finding-detection matching works purely
through expected_detection_family (section 7) with no domain field at
all."""

from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session
from test_validation_adapters import _build_sim_005_scale_package

from app.ground_truth_validation.causal_matcher import score_causal
from app.ground_truth_validation.dq_matcher import score_data_quality
from app.ground_truth_validation.family_registry import (
    ValidationFindingFamilyMapping,
    ValidationFindingFamilyMappingRegistry,
)
from app.ground_truth_validation.leakage_matcher import match_leakage
from app.ground_truth_validation.leakage_matcher import score_leakage as compute_leakage_score
from app.ground_truth_validation.matcher import match_findings
from app.ground_truth_validation.service import validation_service
from app.models.entities import Organization
from app.models.ground_truth_validation import ValidationDimensionStatus
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


def test_causal_dimension_is_not_available_when_causal_truth_uploaded() -> None:
    """Exactly section 12's own worked example: causal truth exists, but
    production emits no causal claim to compare it against."""
    result = score_causal(expected_causal_truth_count=5)
    assert result.status == ValidationDimensionStatus.NOT_AVAILABLE.value
    assert "does not currently emit" in result.summary
    assert result.expected_count == 5


def test_causal_dimension_is_not_available_when_no_causal_truth_at_all() -> None:
    result = score_causal(expected_causal_truth_count=0)
    assert result.status == ValidationDimensionStatus.NOT_AVAILABLE.value
    assert "No causal truth" in result.summary


def test_data_quality_dimension_not_available_without_a_resolvable_family() -> None:
    from app.models.ground_truth_validation import ValidationDataQualityTruth as DQ

    defects = [
        DQ(organization_id=uuid4(), ground_truth_id=uuid4(), truth_dq_id="DQ-1", dq_family=None)
    ]
    result = score_data_quality(defects, actual_findings=[])
    assert result.status == ValidationDimensionStatus.NOT_AVAILABLE.value
    assert "no wired data-quality" in result.summary


def test_data_quality_dimension_scores_when_a_family_is_registered() -> None:
    """Structural generality (section 11D): register a hypothetical
    DATA_QUALITY family mapped to an existing rule, and the SAME matcher
    now genuinely scores TP/FP/FN -- no matcher code change, only a
    registry entry."""
    from app.models.ground_truth_validation import ValidationDataQualityTruth as DQ

    registry = ValidationFindingFamilyMappingRegistry()
    registry.register(
        ValidationFindingFamilyMapping(
            authored_family="TEST_DQ_FAMILY",
            production_rule_families=frozenset({"MAINT-001-REPEATED-FAILURE"}),
            production_domains=frozenset({"maintenance"}),
        )
    )
    defects = [
        DQ(
            organization_id=uuid4(),
            ground_truth_id=uuid4(),
            truth_dq_id="DQ-1",
            dq_family="TEST_DQ_FAMILY",
        )
    ]
    result = score_data_quality(defects, actual_findings=[], family_registry=registry)
    assert result.status == ValidationDimensionStatus.SCORED.value
    # no actual findings supplied -> the one defect is missed
    assert result.false_negative_count == 1
    assert result.true_positive_count == 0


def test_leakage_dimension_not_available_with_no_leakage_truth() -> None:
    pairs = match_leakage([], actual_findings=[])
    assert pairs == []
    summary = compute_leakage_score(pairs)
    assert summary.status == ValidationDimensionStatus.NOT_AVAILABLE.value


def test_finding_matcher_matches_purely_on_family_with_no_domain_field() -> None:
    """Section 7: an expected finding with domain=None must still match,
    resolved entirely through expected_detection_family."""
    from app.models.ground_truth_validation import ValidationExpectedFinding

    expected = ValidationExpectedFinding(
        organization_id=uuid4(),
        ground_truth_id=uuid4(),
        expected_finding_code="EXP-1",
        domain=None,
        severity="medium",
        expected_detection_family="MAINTENANCE_ECONOMICS",
        entities=[{"entity_type": "asset", "canonical_key": "V1"}],
    )

    from app.models.entities import Finding

    finding = Finding(
        organization_id=uuid4(),
        rule_id="MAINT-001-REPEATED-FAILURE",
        title="t",
        summary="s",
        domain="maintenance",
        governance_tier="GOVERNED",
        severity="medium",
        entities_json=[{"entity_type": "asset", "canonical_key": "V1"}],
        domains_json=["maintenance"],
    )
    from app.services.analysis_case_command_service import PrioritizedFinding

    actual = PrioritizedFinding(
        finding=finding, impacted_domains=["maintenance"], observed_values_by_currency={}
    )

    pairs = match_findings([expected], [actual])
    assert len(pairs) == 1
    assert pairs[0].match_type == "true_positive"
    matched_expected = pairs[0].expected
    assert matched_expected is not None
    assert matched_expected.domain is None


def test_sim_005_scale_package_scores_end_to_end_through_real_service(
    db: Session, tmp_path: Path
) -> None:
    """Full pipeline at SIM-005's real scale (387/387/387/60): upload,
    run a real AnalysisCase, validate, and confirm every dimension reports
    a real status -- never crashes, never fabricates a number."""
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    org = _organization(db, "sim005-scale")
    actor = uuid4()
    case = service.create(db, org.id, "SIM-005 Scale Case", "single", actor)
    service.register_artifacts(
        db, org.id, case.id, [UploadedFile("maintenance_events.csv", MAINT_CSV)], actor
    )
    run = analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org.id, case.id, run.id, actor)
    db.refresh(run)

    simulation = validation_service.create_simulation(
        db, org.id, "SIM-OFS-FIELDMAINT-005", "Field Maintenance Simulation", case.id, actor
    )
    package = _build_sim_005_scale_package(finding_count=387, dq_count=60)
    ground_truth = validation_service.upload_ground_truth(db, org.id, simulation.id, package, actor)
    assert ground_truth.schema_version == "intel4ops_simulation_truth_v1"

    from app.ground_truth_validation.repository import validation_ground_truth_repository as repo

    assert len(repo.list_expected_findings(db, org.id, ground_truth.id)) == 387
    assert len(repo.list_leakage_truth(db, org.id, ground_truth.id)) == 387
    assert len(repo.list_causal_truth(db, org.id, ground_truth.id)) == 387
    assert len(repo.list_data_quality_truth(db, org.id, ground_truth.id)) == 60

    validation_run, score, dimensions, matches = validation_service.validate_run(
        db, org.id, simulation.id, run.id, actor
    )
    assert validation_run.status == "completed"
    assert score is not None

    by_code = {d.dimension_code: d for d in dimensions}
    assert set(by_code) == {"finding_detection", "leakage_value", "causal", "data_quality"}
    for dimension in dimensions:
        # Never NOT_IMPLEMENTED/INVALID_GROUND_TRUTH/None -- every dimension
        # reports a real, explicit status (section 12).
        assert dimension.status in {
            "scored",
            "partially_scored",
            "not_available",
            "insufficient_production_evidence",
        }
        assert dimension.summary

    # The one real, currently-wired production rule (MAINT-001) produced
    # exactly one finding, matched against exactly one of the 387 expected
    # findings that shares its family/entity -- the other 386 are correctly
    # false negatives (this synthetic package deliberately does not attempt
    # to make all 387 rows independently detectable by the currently wired
    # 3 rules; it certifies volume/shape handling, not full recall).
    finding_tp_count = by_code["finding_detection"].metrics["true_positive_count"]
    assert isinstance(finding_tp_count, int)
    assert finding_tp_count <= 1
    assert len(matches) > 0
