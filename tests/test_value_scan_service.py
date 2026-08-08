from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest
from conftest import IdentityState
from fastapi.testclient import TestClient
from governed_provenance_helpers import add_eligible_dataset_version
from sqlalchemy import select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_finding_platform import create_execution, publish

from app.models.economics import (
    EconomicCalculation,
    EconomicScenario,
    OpportunityFinding,
    OpportunityOverlapGroup,
    OpportunityOverlapMember,
    PrioritizationAssessment,
    RecoveryOpportunity,
)
from app.models.entities import Finding
from app.models.findings import FindingEvidenceBundle, FindingEvidenceItem
from app.models.ingestion import Dataset
from app.models.intelligence import IntelligenceExecution
from app.models.trust import AnalyticalReadinessDecision, TrustAssessment
from app.models.value_scan import DirectionalValueScan
from app.models.workspace import OrganizationObjective
from app.services.value_scan_service import ValueScanServiceError, directional_value_scan_service


def governed_finding(
    client: TestClient,
    db_engine: Engine,
    identity: IdentityState,
    slug: str,
    *,
    start_offset: int = 0,
) -> tuple[UUID, Finding]:
    organization_id, execution_id = create_execution(client, slug)
    actor = identity.user_id
    assert actor is not None
    with Session(db_engine) as db:
        execution = db.get(IntelligenceExecution, execution_id)
        assert execution is not None
        dataset = db.get(Dataset, execution.dataset_id)
        assert dataset is not None
        version = add_eligible_dataset_version(
            db,
            organization_id,
            dataset.source_system_id,
            dataset.id,
            actor,
            checksum=(slug.encode().hex() + "0" * 64)[:64],
        )
        execution = db.get(IntelligenceExecution, execution_id)
        assert execution is not None
        execution.dataset_version_id = version.id
        db.commit()
    finding = publish(
        db_engine,
        organization_id,
        execution_id,
        actor,
        start_offset=start_offset,
    )
    return organization_id, finding


def add_economics(
    db: Session,
    organization_id: UUID,
    finding_id: UUID,
    *,
    score: Decimal = Decimal("82.00"),
    currency: str = "USD",
    included: bool = True,
) -> tuple[RecoveryOpportunity, EconomicCalculation, PrioritizationAssessment]:
    actor = uuid4()
    opportunity = RecoveryOpportunity(
        organization_id=organization_id,
        opportunity_code=f"OPP-{uuid4().hex[:12].upper()}",
        idempotency_key=f"opp:{uuid4()}",
        economic_source_key=f"finding:{finding_id}:{uuid4()}",
        title="Governed recovery opportunity",
        description="Existing deterministic Recovery Economics output.",
        status="economically_qualified",
        priority_category="critical",
        currency_code=currency,
        limitations=[],
        created_by_user_id=actor,
    )
    db.add(opportunity)
    db.flush()
    db.add(
        OpportunityFinding(
            organization_id=organization_id,
            opportunity_id=opportunity.id,
            finding_id=finding_id,
            allocation_percentage=Decimal("1"),
            created_by_user_id=actor,
        )
    )
    scenario = EconomicScenario(
        organization_id=organization_id,
        opportunity_id=opportunity.id,
        scenario_code="BASE",
        version=1,
        name="Base",
        currency_code=currency,
        lower_exposure=Decimal("80"),
        gross_exposure=Decimal("100"),
        upper_exposure=Decimal("120"),
        addressability_rate=Decimal("0.8"),
        recoverability_rate=Decimal("0.5"),
        success_probability=Decimal("0.75"),
        recovery_cost=Decimal("10"),
        scenario_probability=Decimal("1"),
        assumptions_summary=[],
        created_by_user_id=actor,
    )
    db.add(scenario)
    db.flush()
    calculation = EconomicCalculation(
        organization_id=organization_id,
        opportunity_id=opportunity.id,
        scenario_id=scenario.id,
        idempotency_key=f"calc:{uuid4()}",
        calculation_version="1.0",
        currency_code=currency,
        gross_exposure=Decimal("100"),
        addressable_exposure=Decimal("80"),
        expected_recoverable_value=Decimal("40"),
        probability_adjusted_value=Decimal("30"),
        recovery_cost=Decimal("10"),
        expected_net_benefit=Decimal("20"),
        expected_roi=Decimal("2"),
        payback_period_days=Decimal("30"),
        zero_cost_policy="standard",
        input_snapshot={"source": "governed-test"},
        limitations=[],
        calculated_by_user_id=actor,
    )
    db.add(calculation)
    db.flush()
    priority = PrioritizationAssessment(
        organization_id=organization_id,
        opportunity_id=opportunity.id,
        calculation_id=calculation.id,
        idempotency_key=f"priority:{uuid4()}",
        profile_code="default_enterprise",
        model_name="transparent_weighted_recovery_priority",
        model_version="1.0",
        factor_weights={"existing": "1"},
        normalized_factors={"existing": "1"},
        factor_contributions={"existing": "1"},
        priority_score=score,
        priority_category="critical" if score >= 80 else "high",
        calculation_reason="Existing persisted prioritization.",
        limitations=[],
        source_references=[],
        calculated_by_user_id=actor,
    )
    db.add(priority)
    if not included:
        group = OpportunityOverlapGroup(
            organization_id=organization_id,
            overlap_key=f"overlap:{uuid4()}",
            overlap_type="duplicate",
            created_by_user_id=actor,
        )
        db.add(group)
        db.flush()
        db.add(
            OpportunityOverlapMember(
                organization_id=organization_id,
                overlap_group_id=group.id,
                opportunity_id=opportunity.id,
                allocation_percentage=Decimal("0"),
                inclusion_status="excluded",
            )
        )
    db.commit()
    return opportunity, calculation, priority


def test_supported_scan_truth_labels_next_step_and_safe_replay(
    client: TestClient,
    db_engine: Engine,
    identity: IdentityState,
) -> None:
    organization_id, finding = governed_finding(client, db_engine, identity, "value-scan-supported")
    actor = identity.user_id
    assert actor is not None
    with Session(db_engine) as db:
        scan, current = directional_value_scan_service.create(
            db, organization_id, actor, "scan-supported"
        )
        assert current is True
        assert scan.status == "partial"
        assert scan.opportunity_count == 1
        opportunity = scan.opportunity_snapshot[0]
        assert opportunity["finding_id"] == str(finding.id)
        assert opportunity["truth_label"] == "SUPPORTED_FINDING"
        assert opportunity["potential_exposure"]["truth_label"] == "POTENTIAL_EXPOSURE"  # type: ignore[index]
        assert opportunity["expected_recovery"] is None
        assert "VERIFIED_VALUE" not in str(opportunity)
        assert scan.next_investigation_snapshot == {
            "truth_label": "RECOMMENDATION",
            "code": "REVIEW_AFFECTED_RECORDS",
            "text": "Review the governed affected records for Direct quality cost exposure.",
        }
        retry, retry_current = directional_value_scan_service.create(
            db, organization_id, actor, "scan-supported"
        )
        other_key, _ = directional_value_scan_service.create(
            db, organization_id, actor, "scan-supported-other-key"
        )
        assert retry.id == scan.id == other_key.id
        assert retry_current is True


def test_only_published_and_confirmed_findings_are_customer_visible(
    client: TestClient,
    db_engine: Engine,
    identity: IdentityState,
) -> None:
    organization_id, first = governed_finding(client, db_engine, identity, "value-scan-statuses")
    actor = identity.user_id
    assert actor is not None
    with Session(db_engine) as db:
        base = db.get(Finding, first.id)
        assert base is not None
        statuses = [
            "confirmed",
            "under_review",
            "draft",
            "dismissed",
            "superseded",
            "resolved",
            "archived",
        ]
        for index, status in enumerate(statuses, start=1):
            clone = clone_finding(base, index, status)
            db.add(clone)
            db.flush()
            db.add(complete_bundle(clone, actor))
        db.commit()
        scan, _ = directional_value_scan_service.create(db, organization_id, actor, "statuses")
        visible_statuses = {item["finding_status"] for item in scan.opportunity_snapshot}
        assert visible_statuses == {"published", "confirmed"}
        assert scan.opportunity_count == 2


@pytest.mark.parametrize(
    ("trust_status", "readiness_status", "bundle_status", "expected_state"),
    [
        ("completed", "ready_with_warnings", "complete", "PARTIAL"),
        ("completed", "blocked", "complete", None),
        ("completed", "insufficient_data", "complete", None),
        ("failed", "ready", "complete", None),
        ("completed", "ready", "invalid", None),
    ],
)
def test_trust_and_evidence_hard_gates(
    client: TestClient,
    db_engine: Engine,
    identity: IdentityState,
    trust_status: str,
    readiness_status: str,
    bundle_status: str,
    expected_state: str | None,
) -> None:
    organization_id, finding = governed_finding(
        client,
        db_engine,
        identity,
        f"value-scan-gate-{trust_status}-{readiness_status.replace('_', '-')}-{bundle_status}",
    )
    actor = identity.user_id
    assert actor is not None
    with Session(db_engine) as db:
        readiness = db.get(AnalyticalReadinessDecision, finding.analytical_readiness_id)
        trust = db.get(TrustAssessment, finding.trust_assessment_id)
        bundle = db.scalar(
            select(FindingEvidenceBundle).where(FindingEvidenceBundle.finding_id == finding.id)
        )
        assert readiness is not None and trust is not None and bundle is not None
        trust.status = trust_status
        readiness.readiness_status = readiness_status
        if readiness_status != "ready":
            readiness.warning_rule_codes = ["governed-warning"]
        if bundle_status != "complete":
            db.execute(
                update(FindingEvidenceBundle)
                .where(FindingEvidenceBundle.id == bundle.id)
                .values(status=bundle_status, completeness_status="invalid")
            )
        db.commit()
        scan, _ = directional_value_scan_service.create(
            db, organization_id, actor, f"gate-{readiness_status}-{bundle_status}"
        )
        if expected_state:
            assert scan.opportunity_snapshot[0]["support_state"] == expected_state
            assert scan.status == "partial"
        else:
            assert scan.status == "refused"
            assert scan.opportunity_count == 0
            assert scan.data_gap_count >= 1
            assert scan.next_investigation_snapshot["code"] == "RESOLVE_BLOCKING_DATA_GAP"  # type: ignore[index]


def test_existing_economics_ranks_first_and_currencies_are_not_reconciled(
    client: TestClient,
    db_engine: Engine,
    identity: IdentityState,
) -> None:
    organization_id, first = governed_finding(client, db_engine, identity, "value-scan-economics")
    actor = identity.user_id
    assert actor is not None
    with Session(db_engine) as db:
        base = db.get(Finding, first.id)
        assert base is not None
        second = clone_finding(base, 20, "confirmed")
        db.add(second)
        db.flush()
        db.add(complete_bundle(second, actor))
        db.commit()
        add_economics(
            db,
            organization_id,
            second.id,
            score=Decimal("91"),
            currency="EUR",
        )
        scan, _ = directional_value_scan_service.create(db, organization_id, actor, "economics")
        ranked = scan.opportunity_snapshot
        assert ranked[0]["finding_id"] == str(second.id)
        assert ranked[0]["priority_source"] == "ECONOMICS_PRIORITIZATION"
        expected_recovery = cast(dict[str, object], ranked[0]["expected_recovery"])
        potential_exposure = cast(dict[str, object], ranked[0]["potential_exposure"])
        assert expected_recovery["truth_label"] == "EXPECTED_RECOVERY"
        assert expected_recovery["currency"] == "EUR"
        assert potential_exposure["currency"] == "USD"
        limitations = cast(list[str], ranked[0]["limitations"])
        assert any("different currencies" in item for item in limitations)
        assert scan.data_coverage_snapshot["currencies_present"] == ["EUR", "USD"]


def test_overlap_excluded_economics_is_not_used(
    client: TestClient,
    db_engine: Engine,
    identity: IdentityState,
) -> None:
    organization_id, finding = governed_finding(client, db_engine, identity, "value-scan-overlap")
    actor = identity.user_id
    assert actor is not None
    with Session(db_engine) as db:
        add_economics(db, organization_id, finding.id, included=False)
        scan, _ = directional_value_scan_service.create(db, organization_id, actor, "overlap")
        assert scan.opportunity_snapshot[0]["expected_recovery"] is None
        assert scan.opportunity_snapshot[0]["priority_source"] == "FINDING_PRIORITY"


def test_no_eligible_findings_is_not_a_clean_bill_of_health(
    client: TestClient,
    db_engine: Engine,
    identity: IdentityState,
) -> None:
    organization_id, finding = governed_finding(
        client, db_engine, identity, "value-scan-no-findings"
    )
    actor = identity.user_id
    assert actor is not None
    with Session(db_engine) as db:
        row = db.get(Finding, finding.id)
        assert row is not None
        row.status = "under_review"
        db.commit()
        scan, _ = directional_value_scan_service.create(db, organization_id, actor, "none")
        assert scan.status == "completed"
        assert scan.opportunity_count == 0
        assert "not a clean bill of health" in str(
            scan.data_coverage_snapshot["zero_opportunity_interpretation"]
        )


def test_cross_tenant_governed_reference_rejects_entire_scan(
    client: TestClient,
    db_engine: Engine,
    identity: IdentityState,
) -> None:
    organization_id, finding = governed_finding(client, db_engine, identity, "value-scan-tenant-a")
    other_id, other_finding = governed_finding(client, db_engine, identity, "value-scan-tenant-b")
    assert organization_id != other_id
    actor = identity.user_id
    assert actor is not None
    with Session(db_engine) as db:
        row = db.get(Finding, finding.id)
        assert row is not None
        row.trust_assessment_id = other_finding.trust_assessment_id
        db.commit()
        with pytest.raises(ValueScanServiceError, match="outside the organization boundary") as exc:
            directional_value_scan_service.create(db, organization_id, actor, "cross-tenant")
        assert exc.value.code == "CROSS_TENANT_REFERENCE"
        assert not db.scalars(
            select(DirectionalValueScan).where(
                DirectionalValueScan.organization_id == organization_id
            )
        ).all()


def test_cross_tenant_evidence_reference_rejects_entire_scan(
    client: TestClient,
    db_engine: Engine,
    identity: IdentityState,
) -> None:
    organization_id, finding = governed_finding(
        client, db_engine, identity, "value-scan-evidence-a"
    )
    other_id, _ = governed_finding(client, db_engine, identity, "value-scan-evidence-b")
    actor = identity.user_id
    assert actor is not None
    with Session(db_engine) as db:
        item = db.scalar(
            select(FindingEvidenceItem).where(
                FindingEvidenceItem.organization_id == organization_id,
                FindingEvidenceItem.evidence_bundle_id.in_(
                    select(FindingEvidenceBundle.id).where(
                        FindingEvidenceBundle.finding_id == finding.id
                    )
                ),
            )
        )
        assert item is not None
        db.execute(
            update(FindingEvidenceItem)
            .where(FindingEvidenceItem.id == item.id)
            .values(organization_id=other_id)
        )
        db.commit()
        with pytest.raises(ValueScanServiceError) as exc:
            directional_value_scan_service.create(db, organization_id, actor, "cross-evidence")
        assert exc.value.code == "CROSS_TENANT_REFERENCE"


def test_cross_tenant_economics_rejects_entire_scan(
    client: TestClient,
    db_engine: Engine,
    identity: IdentityState,
) -> None:
    organization_id, finding = governed_finding(
        client, db_engine, identity, "value-scan-economics-a"
    )
    other_id, _ = governed_finding(client, db_engine, identity, "value-scan-economics-b")
    actor = identity.user_id
    assert actor is not None
    with Session(db_engine) as db:
        _, calculation, _ = add_economics(db, organization_id, finding.id)
        db.execute(
            update(EconomicCalculation)
            .where(EconomicCalculation.id == calculation.id)
            .values(organization_id=other_id)
        )
        db.commit()
        with pytest.raises(ValueScanServiceError) as exc:
            directional_value_scan_service.create(db, organization_id, actor, "cross-economics")
        assert exc.value.code == "CROSS_TENANT_REFERENCE"
        assert not db.scalars(
            select(DirectionalValueScan).where(
                DirectionalValueScan.organization_id == organization_id
            )
        ).all()


def test_immutability_historical_snapshot_and_idempotency_conflict(
    client: TestClient,
    db_engine: Engine,
    identity: IdentityState,
) -> None:
    organization_id, finding = governed_finding(client, db_engine, identity, "value-scan-immutable")
    actor = identity.user_id
    assert actor is not None
    with Session(db_engine) as db:
        scan, _ = directional_value_scan_service.create(db, organization_id, actor, "immutable")
        original_title = scan.opportunity_snapshot[0]["title"]
        row = db.get(Finding, finding.id)
        assert row is not None
        row.title = "Changed governed source title"
        row.content_fingerprint = "f" * 64
        db.commit()
        historical, current = directional_value_scan_service.get(db, organization_id, scan.id)
        assert current is False
        assert historical.opportunity_snapshot[0]["title"] == original_title
        with pytest.raises(ValueScanServiceError) as exc:
            directional_value_scan_service.create(db, organization_id, actor, "immutable")
        assert exc.value.code == "IDEMPOTENCY_CONFLICT"
        historical.status = "refused"
        with pytest.raises(ValueError, match="immutable"):
            db.commit()
        db.rollback()
        db.delete(historical)
        with pytest.raises(ValueError, match="immutable"):
            db.commit()


def test_context_changes_fingerprint_but_not_ranking(
    client: TestClient,
    db_engine: Engine,
    identity: IdentityState,
) -> None:
    organization_id, _ = governed_finding(client, db_engine, identity, "value-scan-context")
    actor = identity.user_id
    assert actor is not None
    with Session(db_engine) as db:
        first, _ = directional_value_scan_service.create(db, organization_id, actor, "context-a")
        first_order = [item["finding_id"] for item in first.opportunity_snapshot]
        db.add(
            OrganizationObjective(
                organization_id=organization_id,
                objective_code="increase_revenue",
                selected_by_user_id=actor,
            )
        )
        db.commit()
        second, _ = directional_value_scan_service.create(db, organization_id, actor, "context-b")
        assert second.id != first.id
        assert second.input_fingerprint != first.input_fingerprint
        assert [item["finding_id"] for item in second.opportunity_snapshot] == first_order
        assert second.customer_context_snapshot["ranking_influence"] == "none_v1"


def test_candidate_limit_is_partial_and_output_is_bounded(
    client: TestClient,
    db_engine: Engine,
    identity: IdentityState,
) -> None:
    organization_id, finding = governed_finding(client, db_engine, identity, "value-scan-limit")
    actor = identity.user_id
    assert actor is not None
    with Session(db_engine) as db:
        base = db.get(Finding, finding.id)
        assert base is not None
        clones = [clone_finding(base, index, "published") for index in range(1, 1001)]
        db.add_all(clones)
        db.flush()
        db.add_all(complete_bundle(clone, actor) for clone in clones)
        db.commit()
        scan, _ = directional_value_scan_service.create(db, organization_id, actor, "limit")
        assert scan.status == "partial"
        assert scan.candidate_finding_count == 1000
        assert scan.opportunity_count == 10
        assert scan.data_coverage_snapshot["candidate_universe_truncated"] is True
        assert any("truncated" in limitation for limitation in scan.limitations)


def clone_finding(base: Finding, index: int, status: str) -> Finding:
    detected_at = datetime(2026, 8, 1, tzinfo=UTC)
    return Finding(
        organization_id=base.organization_id,
        rule_id=f"scan-clone-{index}-{uuid4()}",
        title=f"Directional opportunity {index}",
        summary="Governed cloned Finding for bounded scan certification.",
        domain=base.domain,
        severity=base.severity,
        priority=(index % 5) + 1,
        exposure_low=base.exposure_low,
        exposure_high=base.exposure_high,
        currency=base.currency,
        confidence_score=base.confidence_score,
        status=status,
        ontology_concept_ids=[],
        first_detected_at=detected_at,
        last_detected_at=detected_at,
        finding_code=f"FND-SCAN-{index}-{uuid4().hex[:8]}",
        finding_type=base.finding_type,
        domain_code=base.domain_code,
        process_code=base.process_code,
        severity_reason=base.severity_reason,
        confidence_level=base.confidence_level,
        measured_value=base.measured_value,
        measured_value_type=base.measured_value_type,
        measured_unit=base.measured_unit,
        measured_currency=base.measured_currency,
        exposure_value=base.exposure_value,
        exposure_value_type=base.exposure_value_type,
        exposure_currency=base.exposure_currency,
        affected_record_count=base.affected_record_count,
        detected_at=detected_at,
        published_at=detected_at if status == "published" else base.published_at,
        confirmed_at=detected_at if status == "confirmed" else None,
        source_execution_id=base.source_execution_id,
        source_result_id=base.source_result_id,
        definition_code=base.definition_code,
        definition_version=base.definition_version,
        definition_fingerprint=base.definition_fingerprint,
        trust_assessment_id=base.trust_assessment_id,
        analytical_readiness_id=base.analytical_readiness_id,
        dataset_id=base.dataset_id,
        dataset_reference=base.dataset_reference,
        warnings=list(base.warnings or []),
        limitations=list(base.limitations or []),
        content_fingerprint=uuid4().hex + uuid4().hex,
        deduplication_key=uuid4().hex + uuid4().hex,
        created_by_user_id=base.created_by_user_id,
    )


def complete_bundle(finding: Finding, actor: UUID) -> FindingEvidenceBundle:
    return FindingEvidenceBundle(
        organization_id=finding.organization_id,
        finding_id=finding.id,
        bundle_version=1,
        evidence_policy_code="P3.03A-TEST",
        evidence_policy_version="1.0",
        status="complete",
        completeness_status="complete",
        content_hash=uuid4().hex + uuid4().hex,
        created_by_user_id=actor,
        finalized_at=datetime.now(UTC),
    )
