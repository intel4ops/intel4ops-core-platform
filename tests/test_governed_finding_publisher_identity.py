"""P3.xxV.2J (Fix #7): governed finding identity + deduplication contract.

Platform-level tests against governed_finding_publisher.publish() directly
-- no XDOM-A/XDOM-B rule logic is exercised or modified here. A real,
minimal AnalysisCase run bootstraps a genuinely valid (organization_id,
trust_assessment_id, dataset_id, READY AnalyticalReadinessDecision) context
once; every test below then calls publish() directly with hand-built
GovernedFindingRequests to exercise the identity contract precisely --
exactly the kind of surgical control Sections 9-12 of the mission ask for,
without a second, invented DB-fixture path.

See tests/test_capability_governed_activation_xdom_a.py's
test_mixed_c_execution_includes_eligible_assets_and_excludes_the_tail and
test_xdom_a_ready_governed_execution_occurs_with_real_finding for the
real-orchestrator, multi-asset certification (Section 8/17)."""

from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Finding, Organization
from app.models.findings import FindingEvidenceBundle, FindingEvidenceItem
from app.models.trust import (
    AnalyticalLevel,
    AnalyticalReadinessDecision,
    ReadinessStatus,
    TrustAssessment,
)
from app.schemas.contracts import OrganizationCreate
from app.schemas.findings import FindingSeverity, FindingType
from app.services.analysis_case_orchestration_service import analysis_case_orchestration_service
from app.services.analysis_case_service import AnalysisCaseService, UploadedFile
from app.services.governed_finding_publisher import (
    ContributingDataset,
    GovernedFindingRequest,
    StableFindingIdentityReference,
    governed_finding_publisher,
)
from app.services.organization_service import OrganizationService
from app.storage.local_storage import LocalFileStorage

_N_ASSETS = 5


def _bootstrap_context(db: Session, tmp_path: Path, slug: str) -> tuple[UUID, UUID, UUID, UUID]:
    """Real orchestrator run against a tiny, already-established-working
    fixture shape (mirrors test_capability_governed_activation_xdom_a.py's
    own _positive_fixture_csvs), purely to obtain a genuinely valid
    (organization_id, actor_user_id, dataset_id, trust_assessment_id) with
    an already-READY AnalyticalReadinessDecision -- never to exercise
    XDOM-A/XDOM-B themselves."""
    org: Organization = OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug.title(), slug=slug, country_code="US", default_currency="USD", timezone="UTC"
        ),
    )
    maint_rows = "asset_id,work_order_id,failure_code,downtime_hours,repair_cost,event_date\n"
    for i in range(_N_ASSETS):
        maint_rows += f"A-{i + 1},WO-{i + 1},brake,48,10000,2026-08-{i + 1:02d}T08:00:00\n"
    files = [UploadedFile("maintenance_events.csv", maint_rows.encode())]
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    actor = uuid4()
    case = service.create(db, org.id, "Fix7 Bootstrap", "single", actor)
    service.register_artifacts(db, org.id, case.id, files, actor)
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
    assert readiness is not None, "bootstrap fixture must produce a READY trust assessment"
    assessment = db.get(TrustAssessment, readiness.trust_assessment_id)
    assert assessment is not None
    return org.id, actor, readiness.trust_assessment_id, assessment.dataset_id


def _identity(
    reference_type: str,
    canonical_reference: str,
    *,
    role: Literal["subject", "material_condition"] = "subject",
) -> StableFindingIdentityReference:
    return StableFindingIdentityReference(
        identity_role=role,
        reference_type=reference_type,
        canonical_reference=canonical_reference,
        canonical_entity=reference_type if role == "subject" else None,
    )


def _request(
    org_id: UUID,
    dataset_id: UUID,
    trust_assessment_id: UUID,
    actor: UUID,
    *,
    definition_code: str = "MAINT-001-REPEATED-FAILURE",
    entities: list[dict[str, object]] | None = None,
    identity_references: list[StableFindingIdentityReference] | None = None,
    affected_record_count: int = 1,
) -> GovernedFindingRequest:
    return GovernedFindingRequest(
        organization_id=org_id,
        primary_dataset_id=dataset_id,
        trust_assessment_id=trust_assessment_id,
        definition_code=definition_code,
        definition_version="1.0",
        rule_condition_code="test_condition",
        affected_record_count=affected_record_count,
        title="Test finding",
        summary="Test finding summary.",
        domain_code="test_domain",
        severity=FindingSeverity.HIGH,
        finding_type=FindingType.EXCEPTION,
        actor_user_id=actor,
        contributing_datasets=[ContributingDataset(dataset_id=dataset_id)],
        entities=entities or [],
        identity_references=identity_references or [],
        domains=["test_domain"],
    )


# ---------------------------------------------------------------------------
# Section 9: duplicate same-subject test
# ---------------------------------------------------------------------------


def test_duplicate_same_subject_deduplicates_to_one_finding(db: Session, tmp_path: Path) -> None:
    org_id, actor, trust_id, dataset_id = _bootstrap_context(db, tmp_path, "fix7-dup-subject")
    entities: list[dict[str, object]] = [{"entity_type": "asset", "canonical_key": "A-1"}]
    first = governed_finding_publisher.publish(
        db,
        _request(
            org_id,
            dataset_id,
            trust_id,
            actor,
            entities=entities,
            identity_references=[_identity("asset", "A-1")],
        ),
    )
    second = governed_finding_publisher.publish(
        db,
        _request(
            org_id,
            dataset_id,
            trust_id,
            actor,
            entities=entities,
            identity_references=[_identity("asset", "A-1")],
        ),
    )
    assert first is not None
    assert second is not None
    assert first.id == second.id
    total = db.scalars(
        select(Finding).where(
            Finding.organization_id == org_id,
            Finding.definition_code == "MAINT-001-REPEATED-FAILURE",
        )
    ).all()
    assert len(list(total)) == 1


# ---------------------------------------------------------------------------
# Section 10: different-subject test
# ---------------------------------------------------------------------------


def test_different_subject_produces_two_findings(db: Session, tmp_path: Path) -> None:
    org_id, actor, trust_id, dataset_id = _bootstrap_context(db, tmp_path, "fix7-diff-subject")
    finding_a = governed_finding_publisher.publish(
        db,
        _request(
            org_id,
            dataset_id,
            trust_id,
            actor,
            entities=[{"entity_type": "asset", "canonical_key": "ASSET-A"}],
            identity_references=[_identity("asset", "ASSET-A")],
        ),
    )
    finding_b = governed_finding_publisher.publish(
        db,
        _request(
            org_id,
            dataset_id,
            trust_id,
            actor,
            entities=[{"entity_type": "asset", "canonical_key": "ASSET-B"}],
            identity_references=[_identity("asset", "ASSET-B")],
        ),
    )
    assert finding_a is not None
    assert finding_b is not None
    assert finding_a.id != finding_b.id
    assert finding_a.entities_json == [{"entity_type": "asset", "canonical_key": "ASSET-A"}]
    assert finding_b.entities_json == [{"entity_type": "asset", "canonical_key": "ASSET-B"}]


# ---------------------------------------------------------------------------
# Section 11: same subject, different event (evidence fingerprint) test
# ---------------------------------------------------------------------------


def test_same_subject_different_evidence_produces_two_findings(db: Session, tmp_path: Path) -> None:
    """Where the model contract supplies a second, evidence-scoped entity
    (a durable business identifier for the specific condition, e.g. an
    operational event id -- never a run timestamp or DB row id), two
    findings for the SAME subject are preserved as distinct, because the
    dedup key's affected_references set differs."""
    org_id, actor, trust_id, dataset_id = _bootstrap_context(db, tmp_path, "fix7-diff-event")
    subject: dict[str, object] = {
        "entity_type": "asset",
        "canonical_key": "ASSET-A",
    }
    event_1 = governed_finding_publisher.publish(
        db,
        _request(
            org_id,
            dataset_id,
            trust_id,
            actor,
            entities=[subject, {"entity_type": "operational_event", "canonical_key": "OE-1"}],
            identity_references=[
                _identity("asset", "ASSET-A"),
                _identity("operational_event", "OE-1", role="material_condition"),
            ],
        ),
    )
    event_2 = governed_finding_publisher.publish(
        db,
        _request(
            org_id,
            dataset_id,
            trust_id,
            actor,
            entities=[subject, {"entity_type": "operational_event", "canonical_key": "OE-2"}],
            identity_references=[
                _identity("asset", "ASSET-A"),
                _identity("operational_event", "OE-2", role="material_condition"),
            ],
        ),
    )
    assert event_1 is not None
    assert event_2 is not None
    assert event_1.id != event_2.id


# ---------------------------------------------------------------------------
# Section 12: cross-rule test
# ---------------------------------------------------------------------------


def test_same_subject_different_rule_code_never_deduplicates(db: Session, tmp_path: Path) -> None:
    org_id, actor, trust_id, dataset_id = _bootstrap_context(db, tmp_path, "fix7-cross-rule")
    entities: list[dict[str, object]] = [{"entity_type": "asset", "canonical_key": "A-1"}]
    xdom_a = governed_finding_publisher.publish(
        db,
        _request(
            org_id,
            dataset_id,
            trust_id,
            actor,
            definition_code="MAINT-001-REPEATED-FAILURE",
            entities=entities,
            identity_references=[_identity("asset", "A-1")],
        ),
    )
    xdom_b = governed_finding_publisher.publish(
        db,
        _request(
            org_id,
            dataset_id,
            trust_id,
            actor,
            definition_code="XDOM-B-LOST-ACTIVITY-REVENUE-GAP",
            entities=entities,
            identity_references=[_identity("asset", "A-1")],
        ),
    )
    assert xdom_a is not None
    assert xdom_b is not None
    assert xdom_a.id != xdom_b.id
    assert xdom_a.definition_code != xdom_b.definition_code


# ---------------------------------------------------------------------------
# Non-entity findings (Section 6) and evidence lineage (Section 13)
# ---------------------------------------------------------------------------


def test_no_entities_falls_back_to_dataset_level_dedup_unchanged(
    db: Session, tmp_path: Path
) -> None:
    """A dataset/process-level finding with no single subject (empty
    entities) must not be forced into a fake subject -- dedup behavior for
    this case is exactly what it was before this fix (dataset+value+type),
    and two calls with identical inputs still deduplicate to one row."""
    org_id, actor, trust_id, dataset_id = _bootstrap_context(db, tmp_path, "fix7-no-entities")
    first = governed_finding_publisher.publish(
        db, _request(org_id, dataset_id, trust_id, actor, entities=[])
    )
    second = governed_finding_publisher.publish(
        db, _request(org_id, dataset_id, trust_id, actor, entities=[])
    )
    assert first is not None
    assert second is not None
    assert first.id == second.id
    assert first.entities_json is None


def test_subject_evidence_is_persisted_and_traceable(db: Session, tmp_path: Path) -> None:
    """Section 13: evidence lineage is never sacrificed for deduplication
    -- the subject's evidence item is a real, queryable, persisted
    FindingEvidenceItem row, not merely folded into an opaque hash."""
    org_id, actor, trust_id, dataset_id = _bootstrap_context(db, tmp_path, "fix7-lineage")
    finding = governed_finding_publisher.publish(
        db,
        _request(
            org_id,
            dataset_id,
            trust_id,
            actor,
            entities=[{"entity_type": "asset", "canonical_key": "A-1"}],
            identity_references=[_identity("asset", "A-1")],
        ),
    )
    assert finding is not None
    items = list(
        db.scalars(
            select(FindingEvidenceItem)
            .join(
                FindingEvidenceBundle,
                FindingEvidenceBundle.id == FindingEvidenceItem.evidence_bundle_id,
            )
            .where(FindingEvidenceBundle.finding_id == finding.id)
        ).all()
    )
    subject_items = [i for i in items if i.evidence_type == "affected_record"]
    assert any(
        i.canonical_entity == "asset" and i.canonical_record_reference == "A-1"
        for i in subject_items
    )


def test_identity_reference_order_does_not_change_deduplication(
    db: Session, tmp_path: Path
) -> None:
    org_id, actor, trust_id, dataset_id = _bootstrap_context(db, tmp_path, "fix7-order")
    subject = _identity("asset", "A-1")
    condition = _identity("operational_event", "OE-1", role="material_condition")
    first = governed_finding_publisher.publish(
        db,
        _request(
            org_id,
            dataset_id,
            trust_id,
            actor,
            identity_references=[subject, condition],
        ),
    )
    second = governed_finding_publisher.publish(
        db,
        _request(
            org_id,
            dataset_id,
            trust_id,
            actor,
            identity_references=[condition, subject],
        ),
    )
    assert first is not None
    assert second is not None
    assert first.id == second.id


def test_duplicate_identity_reference_does_not_change_deduplication(
    db: Session, tmp_path: Path
) -> None:
    org_id, actor, trust_id, dataset_id = _bootstrap_context(db, tmp_path, "fix7-duplicate-input")
    subject = _identity("asset", "A-1")
    first = governed_finding_publisher.publish(
        db,
        _request(
            org_id,
            dataset_id,
            trust_id,
            actor,
            identity_references=[subject],
        ),
    )
    second = governed_finding_publisher.publish(
        db,
        _request(
            org_id,
            dataset_id,
            trust_id,
            actor,
            identity_references=[subject, subject],
        ),
    )
    assert first is not None
    assert second is not None
    assert first.id == second.id


def test_ephemeral_entity_database_id_does_not_participate_in_identity(
    db: Session, tmp_path: Path
) -> None:
    org_id, actor, trust_id, dataset_id = _bootstrap_context(db, tmp_path, "fix7-ephemeral-id")
    stable_identity = [_identity("asset", "A-1")]
    first = governed_finding_publisher.publish(
        db,
        _request(
            org_id,
            dataset_id,
            trust_id,
            actor,
            entities=[
                {
                    "entity_type": "asset",
                    "canonical_key": "A-1",
                    "canonical_entity_id": str(uuid4()),
                }
            ],
            identity_references=stable_identity,
        ),
    )
    second = governed_finding_publisher.publish(
        db,
        _request(
            org_id,
            dataset_id,
            trust_id,
            actor,
            entities=[
                {
                    "entity_type": "asset",
                    "canonical_key": "A-1",
                    "canonical_entity_id": str(uuid4()),
                }
            ],
            identity_references=stable_identity,
        ),
    )
    assert first is not None
    assert second is not None
    assert first.id == second.id
