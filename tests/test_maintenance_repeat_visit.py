"""P3.xxI.5B maintenance repeat-visit pairing and publication contract."""

from pathlib import Path
from uuid import UUID, uuid4

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Finding, Organization
from app.models.entities_canonical import CanonicalCaseEntity
from app.models.findings import FindingEvidenceBundle, FindingEvidenceItem
from app.models.intelligence_activation import IntelligenceActivationDecision
from app.models.trust import (
    AnalyticalLevel,
    AnalyticalReadinessDecision,
    ReadinessStatus,
    TrustAssessment,
)
from app.schemas.contracts import OrganizationCreate
from app.services.analysis_case_orchestration_service import analysis_case_orchestration_service
from app.services.analysis_case_service import AnalysisCaseService, UploadedFile
from app.services.maintenance_repeat_visit_service import (
    InterventionDatasetFields,
    build_repeat_visit_pairs,
    run_maintenance_repeat_visit,
)
from app.services.organization_service import OrganizationService
from app.storage.local_storage import LocalFileStorage


def _dataset(
    rows: list[dict[str, object]],
    *,
    dataset_id: UUID | None = None,
    trust_id: UUID | None = None,
    label: str = "service_interventions.csv",
) -> InterventionDatasetFields:
    return InterventionDatasetFields(
        dataset_id=dataset_id or uuid4(),
        dataset_label=label,
        dataframe=pd.DataFrame(rows),
        trust_assessment_id=trust_id or uuid4(),
        subject_id_field="equipment",
        intervention_id_field="service_order",
        timestamp_field="completed_at",
        activity_category_field="service_category",
    )


def _row(
    subject: str,
    intervention: str,
    occurred_at: str | None,
    category: str = "calibration",
) -> dict[str, object]:
    return {
        "equipment": subject,
        "service_order": intervention,
        "completed_at": occurred_at,
        "service_category": category,
    }


def _bootstrap_context(db: Session, tmp_path: Path, slug: str) -> tuple[UUID, UUID, UUID, UUID]:
    org: Organization = OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug.title(),
            slug=slug,
            country_code="US",
            default_currency="USD",
            timezone="UTC",
        ),
    )
    rows = "asset_id,work_order_id,failure_code,downtime_hours,repair_cost,event_date\n"
    for index in range(3):
        rows += f"A-{index + 1},WO-{index + 1},seal,8,1000,2026-08-{index + 1:02d}T08:00:00\n"
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    actor = uuid4()
    case = service.create(db, org.id, "Repeat visit bootstrap", "single", actor)
    service.register_artifacts(
        db,
        org.id,
        case.id,
        [UploadedFile("maintenance_events.csv", rows.encode())],
        actor,
    )
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
    assert readiness is not None
    assessment = db.get(TrustAssessment, readiness.trust_assessment_id)
    assert assessment is not None
    return org.id, actor, readiness.trust_assessment_id, assessment.dataset_id


def test_a_same_asset_related_subsequent_intervention_produces_pair() -> None:
    pairs = build_repeat_visit_pairs(
        [
            _dataset(
                [
                    _row("EQ-1", "SO-1", "2026-01-01T08:00:00Z"),
                    _row("EQ-1", "SO-2", "2026-01-03T08:00:00Z"),
                ]
            )
        ],
        {"EQ-1"},
    )
    assert len(pairs) == 1
    assert pairs[0].prior.intervention_key == "SO-1"
    assert pairs[0].subsequent.intervention_key == "SO-2"
    assert pairs[0].elapsed_hours == 48


def test_b_multiple_assets_produce_separate_pairs() -> None:
    pairs = build_repeat_visit_pairs(
        [
            _dataset(
                [
                    _row("EQ-1", "SO-1", "2026-01-01"),
                    _row("EQ-1", "SO-2", "2026-01-02"),
                    _row("EQ-2", "SO-3", "2026-01-01"),
                    _row("EQ-2", "SO-4", "2026-01-04"),
                ]
            )
        ],
        {"EQ-1", "EQ-2"},
    )
    assert len(pairs) == 2
    assert {pair.prior.subject_key for pair in pairs} == {"EQ-1", "EQ-2"}


def test_c_three_event_chain_pairs_only_adjacent_interventions() -> None:
    pairs = build_repeat_visit_pairs(
        [
            _dataset(
                [
                    _row("EQ-1", "SO-C", "2026-01-03"),
                    _row("EQ-1", "SO-A", "2026-01-01"),
                    _row("EQ-1", "SO-B", "2026-01-02"),
                ]
            )
        ],
        {"EQ-1"},
    )
    assert [(pair.prior.intervention_key, pair.subsequent.intervention_key) for pair in pairs] == [
        ("SO-A", "SO-B"),
        ("SO-B", "SO-C"),
    ]


def test_d_generic_service_fixture_runs_end_to_end(db: Session, tmp_path: Path) -> None:
    org: Organization = OrganizationService().create(
        db,
        OrganizationCreate(
            name="Industrial Callback Service",
            slug="repeat-visit-generic-orchestration",
            country_code="US",
            default_currency="USD",
            timezone="UTC",
        ),
    )
    history = (
        "asset_id,work_order_id,service_type,completed_at\n"
        "EQ-1,SO-0,commissioning,2025-12-20T08:00:00Z\n"
        "EQ-2,SO-20,inspection,2025-12-21T08:00:00Z\n"
        "EQ-3,SO-30,inspection,2025-12-22T08:00:00Z\n"
        "EQ-4,SO-40,inspection,2025-12-23T08:00:00Z\n"
        "EQ-5,SO-50,inspection,2025-12-24T08:00:00Z\n"
    )
    visits = (
        "asset_id,work_order_id,service_type,completed_at\n"
        "EQ-1,SO-1,calibration,2026-01-01T08:00:00Z\n"
        "EQ-1,SO-2,calibration,2026-01-03T08:00:00Z\n"
        "EQ-1,SO-3,inspection,2026-01-04T08:00:00Z\n"
        "EQ-2,SO-21,calibration,2026-01-05T08:00:00Z\n"
        "EQ-3,SO-31,calibration,2026-01-06T08:00:00Z\n"
        "EQ-4,SO-41,calibration,2026-01-07T08:00:00Z\n"
        "EQ-5,SO-51,calibration,2026-01-08T08:00:00Z\n"
    )
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    actor = uuid4()
    case = service.create(db, org.id, "Generic service callbacks", "single", actor)
    service.register_artifacts(
        db,
        org.id,
        case.id,
        [
            UploadedFile("service_history.csv", history.encode()),
            UploadedFile("service_callbacks.csv", visits.encode()),
        ],
        actor,
    )
    run = analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org.id, case.id, run.id, actor)

    activation = db.scalar(
        select(IntelligenceActivationDecision).where(
            IntelligenceActivationDecision.organization_id == org.id,
            IntelligenceActivationDecision.run_id == run.id,
            IntelligenceActivationDecision.rule_code == "MAINTENANCE-REPEAT-VISIT",
        )
    )
    assert activation is not None
    asset_entities = list(
        db.scalars(
            select(CanonicalCaseEntity).where(
                CanonicalCaseEntity.organization_id == org.id,
                CanonicalCaseEntity.run_id == run.id,
                CanonicalCaseEntity.entity_type == "ASSET",
            )
        ).all()
    )
    assert activation.governed_status == "READY", (
        activation.governed_missing_summary,
        activation.governed_confidence_summary,
        activation.evidence_summary,
        [entity.entity_identity_confidence for entity in asset_entities],
    )
    findings = list(
        db.scalars(
            select(Finding).where(
                Finding.organization_id == org.id,
                Finding.definition_code == "MAINTENANCE-REPEAT-VISIT",
            )
        ).all()
    )
    assert len(findings) == 1
    assert "SO-1" in findings[0].summary
    assert "SO-2" in findings[0].summary


def test_e_published_finding_preserves_full_lineage_and_no_policy_claim(
    db: Session, tmp_path: Path
) -> None:
    org_id, actor, trust_id, dataset_id = _bootstrap_context(db, tmp_path, "repeat-visit-lineage")
    findings = run_maintenance_repeat_visit(
        db,
        org_id,
        [
            _dataset(
                [
                    _row("EQ-1", "SO-1", "2026-01-01T08:00:00Z"),
                    _row("EQ-1", "SO-2", "2026-01-03T08:00:00Z"),
                ],
                dataset_id=dataset_id,
                trust_id=trust_id,
            )
        ],
        {"EQ-1"},
        actor,
    )
    assert len(findings) == 1
    finding = findings[0]
    assert finding.exposure_value is None
    assert finding.limitations is not None
    assert any("does not assert a policy violation" in item for item in finding.limitations)
    evidence = list(
        db.scalars(
            select(FindingEvidenceItem)
            .join(
                FindingEvidenceBundle,
                FindingEvidenceBundle.id == FindingEvidenceItem.evidence_bundle_id,
            )
            .where(FindingEvidenceBundle.finding_id == finding.id)
        ).all()
    )
    reference_types = {item.reference_type for item in evidence}
    assert {
        "asset",
        "prior_intervention",
        "subsequent_intervention",
        "activity_category",
        "repeat_interval",
    } <= reference_types
    interval = next(item for item in evidence if item.reference_type == "repeat_interval")
    assert interval.comparison_value == 48
    assert interval.comparison_unit == "hours"
    assert interval.metadata_json["policy_violation_asserted"] is False


def test_negative_a_different_assets_do_not_pair() -> None:
    pairs = build_repeat_visit_pairs(
        [
            _dataset(
                [
                    _row("EQ-1", "SO-1", "2026-01-01"),
                    _row("EQ-2", "SO-2", "2026-01-02"),
                ]
            )
        ],
        {"EQ-1", "EQ-2"},
    )
    assert pairs == []


def test_negative_b_unrelated_categories_do_not_pair() -> None:
    pairs = build_repeat_visit_pairs(
        [
            _dataset(
                [
                    _row("EQ-1", "SO-1", "2026-01-01", "calibration"),
                    _row("EQ-1", "SO-2", "2026-01-02", "inspection"),
                ]
            )
        ],
        {"EQ-1"},
    )
    assert pairs == []


def test_negative_c_missing_timestamp_abstains() -> None:
    pairs = build_repeat_visit_pairs(
        [
            _dataset(
                [
                    _row("EQ-1", "SO-1", None),
                    _row("EQ-1", "SO-2", "2026-01-02"),
                ]
            )
        ],
        {"EQ-1"},
    )
    assert pairs == []


def test_negative_d_conflicting_event_representation_abstains() -> None:
    pairs = build_repeat_visit_pairs(
        [
            _dataset(
                [
                    _row("EQ-1", "SO-1", "2026-01-01", "calibration"),
                    _row("EQ-1", "SO-1", "2026-01-01", "inspection"),
                    _row("EQ-1", "SO-2", "2026-01-02", "calibration"),
                ]
            )
        ],
        {"EQ-1"},
    )
    assert pairs == []


def test_negative_e_duplicate_rows_do_not_duplicate_finding() -> None:
    pairs = build_repeat_visit_pairs(
        [
            _dataset(
                [
                    _row("EQ-1", "SO-1", "2026-01-01"),
                    _row("EQ-1", "SO-1", "2026-01-01"),
                    _row("EQ-1", "SO-2", "2026-01-02"),
                ]
            )
        ],
        {"EQ-1"},
    )
    assert len(pairs) == 1


def test_negative_f_out_of_order_rows_are_deterministic() -> None:
    ordered = [
        _row("EQ-1", "SO-1", "2026-01-01"),
        _row("EQ-1", "SO-2", "2026-01-02"),
        _row("EQ-1", "SO-3", "2026-01-03"),
    ]
    forward = build_repeat_visit_pairs([_dataset(ordered)], {"EQ-1"})
    reverse = build_repeat_visit_pairs([_dataset(list(reversed(ordered)))], {"EQ-1"})
    forward_keys = [
        (pair.prior.intervention_key, pair.subsequent.intervention_key) for pair in forward
    ]
    reverse_keys = [
        (pair.prior.intervention_key, pair.subsequent.intervention_key) for pair in reverse
    ]
    assert forward_keys == reverse_keys


def test_negative_g_same_event_in_two_sources_is_deduplicated() -> None:
    first = _dataset(
        [
            _row("EQ-1", "SO-1", "2026-01-01"),
            _row("EQ-1", "SO-2", "2026-01-02"),
        ],
        label="service_log.csv",
    )
    second = _dataset(
        [_row("EQ-1", "SO-1", "2026-01-01")],
        label="callback_log.csv",
    )
    pairs = build_repeat_visit_pairs([first, second], {"EQ-1"})
    assert len(pairs) == 1


def test_negative_h_tied_distinct_events_abstain_from_ordering() -> None:
    pairs = build_repeat_visit_pairs(
        [
            _dataset(
                [
                    _row("EQ-1", "SO-1", "2026-01-01"),
                    _row("EQ-1", "SO-2", "2026-01-01"),
                    _row("EQ-1", "SO-3", "2026-01-02"),
                ]
            )
        ],
        {"EQ-1"},
    )
    assert pairs == []
