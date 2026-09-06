"""P3.xxI.6 (GAP-007) maintenance schedule completion pairing and
publication contract."""

from pathlib import Path
from uuid import UUID, uuid4

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Finding, Organization
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
from app.services.maintenance_schedule_completion_service import (
    ScheduledMaintenanceDatasetFields,
    find_incomplete_scheduled_maintenance,
    run_maintenance_schedule_completion,
)
from app.services.organization_service import OrganizationService
from app.storage.local_storage import LocalFileStorage


def _dataset(
    rows: list[dict[str, object]],
    *,
    dataset_id: UUID | None = None,
    trust_id: UUID | None = None,
    label: str = "maintenance_events.csv",
) -> ScheduledMaintenanceDatasetFields:
    return ScheduledMaintenanceDatasetFields(
        dataset_id=dataset_id or uuid4(),
        dataset_label=label,
        dataframe=pd.DataFrame(rows),
        trust_assessment_id=trust_id or uuid4(),
        subject_id_field="asset",
        event_id_field="work_order",
        scheduled_timestamp_field="scheduled_at",
        completed_timestamp_field="completed_at",
    )


def _row(
    subject: str,
    event: str,
    scheduled_at: str | None,
    completed_at: str | None = None,
) -> dict[str, object]:
    return {
        "asset": subject,
        "work_order": event,
        "scheduled_at": scheduled_at,
        "completed_at": completed_at,
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
    case = service.create(db, org.id, "Schedule completion bootstrap", "single", actor)
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


def test_a_scheduled_with_no_completed_produces_a_gap() -> None:
    gaps = find_incomplete_scheduled_maintenance(
        [_dataset([_row("A-1", "WO-1", "2026-01-01")])],
        {"A-1"},
    )
    assert len(gaps) == 1
    assert gaps[0].subject_key == "A-1"
    assert gaps[0].event_key == "WO-1"


def test_b_scheduled_with_completed_does_not_produce_a_gap() -> None:
    gaps = find_incomplete_scheduled_maintenance(
        [_dataset([_row("A-1", "WO-1", "2026-01-01", "2026-01-05")])],
        {"A-1"},
    )
    assert gaps == []


def test_c_multiple_assets_produce_separate_gaps() -> None:
    gaps = find_incomplete_scheduled_maintenance(
        [
            _dataset(
                [
                    _row("A-1", "WO-1", "2026-01-01"),
                    _row("A-2", "WO-2", "2026-01-02", "2026-01-06"),
                    _row("A-3", "WO-3", "2026-01-03"),
                ]
            )
        ],
        {"A-1", "A-2", "A-3"},
    )
    assert {g.subject_key for g in gaps} == {"A-1", "A-3"}


def test_d_generic_orchestration_end_to_end(db: Session, tmp_path: Path) -> None:
    org: Organization = OrganizationService().create(
        db,
        OrganizationCreate(
            name="Industrial Schedule Adherence",
            slug="schedule-completion-generic-orchestration",
            country_code="US",
            default_currency="USD",
            timezone="UTC",
        ),
    )
    history = (
        "asset_id,work_order_id,event_type,scheduled_date,completed_date\n"
        "EQ-1,SO-0,CM,,2025-12-20\n"
        "EQ-2,SO-20,CM,,2025-12-21\n"
        "EQ-3,SO-30,CM,,2025-12-22\n"
        "EQ-4,SO-40,CM,,2025-12-23\n"
        "EQ-5,SO-50,CM,,2025-12-24\n"
    )
    rows = (
        "asset_id,work_order_id,event_type,scheduled_date,completed_date\n"
        "EQ-1,SO-1,PM,2026-01-01,2026-01-03\n"
        "EQ-2,SO-2,PM,2026-01-02,\n"
        "EQ-3,SO-3,CM,,2026-01-04\n"
        "EQ-4,SO-4,PM,2026-01-05,2026-01-07\n"
        "EQ-5,SO-5,PM,2026-01-06,\n"
    )
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    actor = uuid4()
    case = service.create(db, org.id, "Generic schedule completion", "single", actor)
    service.register_artifacts(
        db,
        org.id,
        case.id,
        [
            UploadedFile("maintenance_history.csv", history.encode()),
            UploadedFile("maintenance_log.csv", rows.encode()),
        ],
        actor,
    )
    run = analysis_case_orchestration_service.start_run(db, org.id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org.id, case.id, run.id, actor)

    activation = db.scalar(
        select(IntelligenceActivationDecision).where(
            IntelligenceActivationDecision.organization_id == org.id,
            IntelligenceActivationDecision.run_id == run.id,
            IntelligenceActivationDecision.rule_code == "MAINTENANCE-SCHEDULE-COMPLETION-GAP",
        )
    )
    assert activation is not None
    assert activation.governed_status == "READY", (
        activation.governed_missing_summary,
        activation.governed_confidence_summary,
        activation.evidence_summary,
    )
    findings = list(
        db.scalars(
            select(Finding).where(
                Finding.organization_id == org.id,
                Finding.definition_code == "MAINTENANCE-SCHEDULE-COMPLETION-GAP",
            )
        ).all()
    )
    assert len(findings) == 2
    summaries = {f.summary for f in findings}
    assert any("SO-2" in s for s in summaries)
    assert any("SO-5" in s for s in summaries)
    assert not any("SO-1" in s or "SO-3" in s or "SO-4" in s for s in summaries)


def test_e_published_finding_preserves_full_lineage_and_no_policy_claim(
    db: Session, tmp_path: Path
) -> None:
    org_id, actor, trust_id, dataset_id = _bootstrap_context(
        db, tmp_path, "schedule-completion-lineage"
    )
    findings = run_maintenance_schedule_completion(
        db,
        org_id,
        [
            _dataset(
                [_row("A-1", "WO-1", "2026-01-01")],
                dataset_id=dataset_id,
                trust_id=trust_id,
            )
        ],
        {"A-1"},
        actor,
    )
    assert len(findings) == 1
    finding = findings[0]
    assert finding.exposure_value is None
    assert finding.limitations is not None
    assert any("no corrective-cost exposure is estimated" in item for item in finding.limitations)
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
    assert {"asset", "scheduled_event"} <= reference_types
    scheduled = next(item for item in evidence if item.reference_type == "scheduled_event")
    assert scheduled.metadata_json["policy_violation_asserted"] is False


def test_negative_a_no_scheduled_date_never_produces_a_gap() -> None:
    gaps = find_incomplete_scheduled_maintenance(
        [_dataset([_row("A-1", "WO-1", None)])],
        {"A-1"},
    )
    assert gaps == []


def test_negative_b_subject_not_eligible_is_excluded() -> None:
    gaps = find_incomplete_scheduled_maintenance(
        [_dataset([_row("A-1", "WO-1", "2026-01-01")])],
        {"A-2"},
    )
    assert gaps == []


def test_negative_c_conflicting_representation_abstains() -> None:
    gaps = find_incomplete_scheduled_maintenance(
        [
            _dataset(
                [
                    _row("A-1", "WO-1", "2026-01-01", None),
                    _row("A-1", "WO-1", "2026-01-02", None),
                ]
            )
        ],
        {"A-1"},
    )
    assert gaps == []


def test_negative_d_same_event_in_two_sources_is_deduplicated() -> None:
    first = _dataset([_row("A-1", "WO-1", "2026-01-01")], label="log_a.csv")
    second = _dataset([_row("A-1", "WO-1", "2026-01-01")], label="log_b.csv")
    gaps = find_incomplete_scheduled_maintenance([first, second], {"A-1"})
    assert len(gaps) == 1


def test_negative_e_missing_required_field_on_dataset_is_skipped() -> None:
    dataset = ScheduledMaintenanceDatasetFields(
        dataset_id=uuid4(),
        dataset_label="incomplete.csv",
        dataframe=pd.DataFrame(
            [{"asset": "A-1", "work_order": "WO-1", "scheduled_at": "2026-01-01"}]
        ),
        trust_assessment_id=uuid4(),
        subject_id_field="asset",
        event_id_field="work_order",
        scheduled_timestamp_field="scheduled_at",
        completed_timestamp_field="completed_at",  # column does not exist on this dataframe
    )
    gaps = find_incomplete_scheduled_maintenance([dataset], {"A-1"})
    assert gaps == []


def test_negative_f_row_order_is_deterministic() -> None:
    rows = [
        _row("A-1", "WO-1", "2026-01-01"),
        _row("A-2", "WO-2", "2026-01-02"),
        _row("A-3", "WO-3", "2026-01-03"),
    ]
    forward = find_incomplete_scheduled_maintenance([_dataset(rows)], {"A-1", "A-2", "A-3"})
    reverse = find_incomplete_scheduled_maintenance(
        [_dataset(list(reversed(rows)))], {"A-1", "A-2", "A-3"}
    )
    assert [g.subject_key for g in forward] == [g.subject_key for g in reverse]
