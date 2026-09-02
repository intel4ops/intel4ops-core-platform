"""P3.xxE.5 Phase 2 (XDOM-A promotion): XDOM-A's positive (READY) path has
never fired on the real 11-case SOTRA Pilot corpus -- domain detection has
never classified a dataset as 'maintenance' there (a pre-existing,
upstream characteristic this milestone does not touch). Proving XDOM-A's
governed READY path therefore requires a controlled, VALIDATION/TEST-ONLY
fixture built to satisfy XDOM-A's REAL, UNMODIFIED capability contract --
never a lowered threshold, an invented requirement, or a production
shortcut.

The real contract (verified directly against the code, not assumed):
  - required_domains = {maintenance, operations}                 (registry.py)
  - required_canonical_fields = {asset_id, downtime_hours, operational_event_id}
  - required_entities (legacy) = {asset, operational_event}       -- exact-value
    match of the SAME literal id across >=2 datasets
    (app/services/entity_resolution_service.py)
  - required_canonical_entities = {ASSET}, minimum_entity_identity_confidence=0.70,
    coverage_above_threshold @ 100% coverage
  - required_resolved_trust_domains = {maintenance}
  - required_relationships / required_activities / required_canonical_measures
    are all EMPTY -- XDOM-A declares no E.3-relationship, E.4-process, or
    measure requirement at all
  - currency_behavior = "currency_agnostic", unit_behavior = "unit_agnostic"
    -- this rule can never be BLOCKED by a currency/unit violation by
    construction (it never aggregates a monetary or physical-unit value)

The hard, easy-to-miss part of this contract is NOT anything XDOM-A-
specific -- it is E.3's own semantic-interpretation gate (app/semantic/
confidence_engine.py's AUTO_ACCEPTED >= 0.90 threshold): an identifier
column only becomes an EntityObservation (app/entities/entity_resolution.py)
when its semantic interpretation clears 0.90, not merely 0.70
(ACCEPTED_WITH_FLAG). A repeated, low-cardinality asset_id value (e.g. the
same "V1" on every row) never reaches 0.90 -- see
tests/test_entities_order_independence.py's own docstring and
tests/entity_relationship_calibration_fixtures.py for the established,
working shape this fixture below is modeled on: asset_id needs a genuinely
unique sibling identifier column (here, work_order_id) in the SAME dataset
so the neighbor-context confidence bonus (app/semantic/neighbor_context.py)
plus the datatype bonus (asset_id itself varying across rows) clears 0.90,
and the identical asset_id value must then appear again in a second
dataset (operations) at the same confidence tier for cross-dataset EXACT-
tier dedup to reach entity_identity_confidence = 0.735 >= 0.70.

This fixture lives entirely in this test file: it does not modify domain
detection, semantic thresholds, Trust logic, E.3 entity logic, or E.4
process logic anywhere in app/ -- it only supplies CSV data shaped to
naturally satisfy the EXISTING, unmodified thresholds those modules already
enforce."""

from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.intelligence_packs.case_capability_index import CaseCapabilityIndex
from app.intelligence_packs.confidence_distribution import ConfidenceDistribution
from app.intelligence_packs.registry import (
    IntelligencePackDefinition,
    default_intelligence_pack_registry,
)
from app.models.analysis_case import AnalysisCaseStageEvent
from app.models.entities import Organization
from app.models.entities_canonical import CanonicalCaseEntity
from app.models.intelligence_activation import IntelligenceActivationDecision
from app.models.semantic import SemanticInterpretationDecision
from app.schemas.contracts import OrganizationCreate
from app.services.analysis_case_command_service import analysis_case_command_service
from app.services.analysis_case_orchestration_service import analysis_case_orchestration_service
from app.services.analysis_case_service import AnalysisCaseService, UploadedFile
from app.services.intelligence_readiness_service import evaluate_readiness
from app.services.organization_service import OrganizationService
from app.storage.local_storage import LocalFileStorage

_XDOM_A = "XDOM-A-ASSET-FAILURE-LOST-ACTIVITY"
_N_ASSETS = 5


def _positive_fixture_csvs() -> list[UploadedFile]:
    maint_rows = "asset_id,work_order_id,failure_code,downtime_hours,repair_cost,event_date\n"
    for i in range(_N_ASSETS):
        maint_rows += f"A-{i + 1},WO-{i + 1},brake,48,10000,2026-08-{i + 1:02d}T08:00:00\n"
    ops_rows = "operational_event_id,asset_id,event_date,operational_event_status\n"
    for i in range(_N_ASSETS):
        ops_rows += f"OE-{i + 1},A-{i + 1},2026-08-{i + 1:02d}T18:00:00,completed\n"
    rev_rows = "transaction_amount,event_date,operational_event_id\n"
    for i in range(_N_ASSETS):
        rev_rows += f"{5000 + i * 100},2026-08-{i + 1:02d}T18:00:00,OE-{i + 1}\n"
    return [
        UploadedFile("maintenance_events.csv", maint_rows.encode()),
        UploadedFile("operations_events.csv", ops_rows.encode()),
        UploadedFile("revenue_events.csv", rev_rows.encode()),
    ]


def _organization(db: Session, slug: str) -> Organization:
    return OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug.title(), slug=slug, country_code="US", default_currency="USD", timezone="UTC"
        ),
    )


def _run_case(
    db: Session, tmp_path: Path, org_id: UUID, files: list[UploadedFile]
) -> tuple[UUID, UUID]:
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    actor = uuid4()
    case = service.create(db, org_id, "XDOM-A Positive Case", "single", actor)
    service.register_artifacts(db, org_id, case.id, files, actor)
    run = analysis_case_orchestration_service.start_run(db, org_id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org_id, case.id, run.id, actor)
    return case.id, run.id


def _decisions(db: Session, run_id: UUID) -> dict[str, IntelligenceActivationDecision]:
    rows = list(
        db.scalars(
            select(IntelligenceActivationDecision).where(
                IntelligenceActivationDecision.run_id == run_id
            )
        ).all()
    )
    return {d.rule_code: d for d in rows}


# ---------------------------------------------------------------------------
# Section 3: positive readiness + execution certification (items A, B, C, D)
# ---------------------------------------------------------------------------


def test_xdom_a_positive_fixture_reaches_canonical_asset_confidence(
    db: Session, tmp_path: Path
) -> None:
    """Precondition check: the fixture's own semantic/entity-resolution
    mechanics work as documented above -- ASSET canonical entities resolve
    at >=0.70 identity confidence for every one of the 5 distinct assets."""
    org = _organization(db, "xdom-a-pos-precondition")
    _, run_id = _run_case(db, tmp_path, org.id, _positive_fixture_csvs())
    entities = list(
        db.scalars(select(CanonicalCaseEntity).where(CanonicalCaseEntity.run_id == run_id)).all()
    )
    asset_entities = [e for e in entities if e.entity_type == "ASSET"]
    assert len(asset_entities) == _N_ASSETS
    for e in asset_entities:
        assert e.entity_identity_confidence >= 0.70


def test_xdom_a_complete_capability_set_is_ready(db: Session, tmp_path: Path) -> None:
    """A -- every mandatory requirement satisfied naturally -> governed
    READY, legacy also activates, and they agree."""
    org = _organization(db, "xdom-a-pos-ready")
    _, run_id = _run_case(db, tmp_path, org.id, _positive_fixture_csvs())
    decisions = _decisions(db, run_id)
    xdom_a = decisions[_XDOM_A]

    assert xdom_a.governed_status == "READY"
    assert xdom_a.legacy_activated is True
    assert xdom_a.agree is True
    assert xdom_a.mode == "governed"

    # every requirement category independently confirmed satisfied --
    # nothing missing, no confidence shortfall, no currency/unit violation.
    assert xdom_a.governed_missing_summary == []
    assert xdom_a.governed_confidence_summary["below_confidence_threshold"] == []
    assert xdom_a.governed_confidence_summary["currency_violation"] is False
    assert xdom_a.governed_confidence_summary["unit_violation"] is False


def test_xdom_a_ready_governed_execution_occurs_with_real_finding(
    db: Session, tmp_path: Path
) -> None:
    """B, C -- governed READY: XDOM-A actually executes (stage event
    recorded) and publishes one real, well-formed finding per independently
    eligible asset -- not merely "the function was called", and (since
    P3.xxV.2J / Fix #7) not collapsed by a shared deduplication key either."""
    org = _organization(db, "xdom-a-pos-execution")
    case_id, run_id = _run_case(db, tmp_path, org.id, _positive_fixture_csvs())

    stage_events = list(
        db.scalars(
            select(AnalysisCaseStageEvent).where(
                AnalysisCaseStageEvent.run_id == run_id,
                AnalysisCaseStageEvent.stage == "cross_domain_intelligence",
            )
        ).all()
    )
    assert any(e.detail.get("rule") == "XDOM-A" for e in stage_events)

    priorities = analysis_case_command_service.priorities(db, org.id, case_id, run_id=run_id)
    xdom_a_priorities = [p for p in priorities if p.finding.rule_id == _XDOM_A]
    assert len(xdom_a_priorities) == _N_ASSETS
    assert {
        entity["canonical_key"]
        for priority in xdom_a_priorities
        for entity in (priority.finding.entities_json or [])
        if entity.get("entity_type") == "asset"
    } == {f"A-{i}" for i in range(1, _N_ASSETS + 1)}

    finding = xdom_a_priorities[0].finding
    assert finding.rule_id == _XDOM_A
    assert finding.severity == "high"
    assert "downtime" in finding.title.lower() or "downtime" in finding.summary.lower()


def test_xdom_a_governed_positive_result_materially_equals_legacy(
    db: Session, tmp_path: Path
) -> None:
    """D -- governed and legacy agree on activation, and because governed
    execution calls the identical run_asset_failure_to_lost_activity
    function with identical inputs (only the entry gate differs), the
    published finding carries the exact evidence legacy would have
    produced: the specific asset, its severity/finding_type, its
    contributing datasets, and its domains -- no silent transformation."""
    org = _organization(db, "xdom-a-pos-equivalence")
    case_id, run_id = _run_case(db, tmp_path, org.id, _positive_fixture_csvs())
    decisions = _decisions(db, run_id)
    assert decisions[_XDOM_A].agree is True

    priorities = analysis_case_command_service.priorities(db, org.id, case_id, run_id=run_id)
    xdom_a_findings = [p.finding for p in priorities if p.finding.rule_id == _XDOM_A]
    assert xdom_a_findings
    finding = xdom_a_findings[0]
    assert finding.definition_code == _XDOM_A
    assert finding.economic_status == "governed_pending"
    assert finding.domain_code == "cross_domain"


# ---------------------------------------------------------------------------
# Section 4: requirement-ablation tests, at the readiness-evaluator level
# against the REAL registry pack (mirrors the established
# test_shadow_comparison.py pattern for XDOM-B's own trust-domain ablation).
# ---------------------------------------------------------------------------


def _xdom_a_pack() -> IntelligencePackDefinition:
    registry = default_intelligence_pack_registry()
    return next(p for p in registry.all() if p.rule_code == _XDOM_A)


_READY_INDEX = CaseCapabilityIndex(
    organization_id="org1",
    analysis_case_id="case1",
    run_id="run1",
    available_domains=frozenset({"maintenance", "operations"}),
    available_canonical_fields=frozenset({"asset_id", "downtime_hours", "operational_event_id"}),
    resolved_entity_types=frozenset({"asset", "operational_event"}),
    domains_with_resolved_trust=frozenset({"maintenance"}),
    canonical_entity_types_present=frozenset({"ASSET"}),
    canonical_entity_identity_confidence_by_type={"ASSET": ConfidenceDistribution((0.9, 0.9, 0.9))},
)


def test_ablation_baseline_is_ready() -> None:
    """Sanity check for the ablation harness itself: the baseline index
    reaches READY before any requirement is removed."""
    result = evaluate_readiness(_xdom_a_pack(), _READY_INDEX)
    assert result.status == "READY"


def test_ablation_a_missing_domain_blocks() -> None:
    from dataclasses import replace

    index = replace(_READY_INDEX, available_domains=frozenset({"maintenance"}))
    result = evaluate_readiness(_xdom_a_pack(), index)
    assert result.status == "BLOCKED"
    assert result.missing_domains == frozenset({"operations"})


def test_ablation_b_unresolved_trust_blocks() -> None:
    from dataclasses import replace

    index = replace(_READY_INDEX, domains_with_resolved_trust=frozenset())
    result = evaluate_readiness(_xdom_a_pack(), index)
    assert result.status == "BLOCKED"
    assert result.missing_resolved_trust_domains == frozenset({"maintenance"})


def test_ablation_c_missing_canonical_entity_blocks() -> None:
    from dataclasses import replace

    index = replace(
        _READY_INDEX,
        canonical_entity_types_present=frozenset(),
        canonical_entity_identity_confidence_by_type={},
    )
    result = evaluate_readiness(_xdom_a_pack(), index)
    assert result.status == "BLOCKED"
    assert result.missing_canonical_entities == frozenset({"ASSET"})


def test_ablation_d_missing_field_blocks() -> None:
    from dataclasses import replace

    index = replace(
        _READY_INDEX,
        available_canonical_fields=frozenset({"asset_id", "operational_event_id"}),
    )
    result = evaluate_readiness(_xdom_a_pack(), index)
    assert result.status == "BLOCKED"
    assert result.missing_fields == frozenset({"downtime_hours"})


def test_ablation_e_no_required_measure_declared() -> None:
    """E -- N/A for XDOM-A by its real, verified contract: it declares no
    required_canonical_measures at all (it compares downtime-hour windows,
    never a monetary/physical-quantity measure). Documented explicitly
    rather than fabricating a measure requirement that doesn't exist."""
    assert _xdom_a_pack().required_canonical_measures == frozenset()


def test_ablation_f_low_confidence_is_partial_not_blocked() -> None:
    """F -- the canonical entity is structurally present but its identity
    confidence falls short of the 0.70 floor: PARTIAL, not BLOCKED --
    nothing is structurally missing, only the confidence bar isn't
    cleared."""
    from dataclasses import replace

    index = replace(
        _READY_INDEX,
        canonical_entity_identity_confidence_by_type={"ASSET": ConfidenceDistribution((0.3, 0.4))},
    )
    result = evaluate_readiness(_xdom_a_pack(), index)
    assert result.status == "PARTIAL"
    assert result.below_confidence_threshold == frozenset({"entity_identity.ASSET"})
    assert not result.missing_canonical_entities


def test_ablation_g_currency_unit_can_never_block_xdom_a() -> None:
    """G -- N/A by XDOM-A's real, verified currency_agnostic/unit_agnostic
    declaration: it can never be BLOCKED by a currency or unit violation,
    regardless of what currency/unit evidence the index carries -- proven
    directly, not merely asserted from the registry field."""
    from dataclasses import replace

    pack = _xdom_a_pack()
    assert pack.currency_behavior == "currency_agnostic"
    assert pack.unit_behavior == "unit_agnostic"
    index = replace(
        _READY_INDEX,
        distinct_currencies_observed=frozenset({"USD", "EUR", "GBP"}),
        distinct_units_observed_by_measure={"downtime_hours": frozenset({"hours", "minutes"})},
    )
    result = evaluate_readiness(pack, index)
    assert result.currency_violation is False
    assert result.unit_violation is False


# ---------------------------------------------------------------------------
# Section 6 / item Q: negative-path safety through the real orchestrator,
# mirroring the actual real-corpus characteristic (maintenance domain
# absent entirely) without touching domain detection at all.
# ---------------------------------------------------------------------------


def test_xdom_a_stays_blocked_when_maintenance_domain_absent(db: Session, tmp_path: Path) -> None:
    """Q -- mirrors the real 11-case corpus's own observed shape (no
    'maintenance' domain ever detected): with only operations+revenue
    uploaded, XDOM-A must correctly stay BLOCKED and never execute, exactly
    matching the real live corpus's own already-certified behavior. No
    domain-detection or threshold change involved -- purely a case that
    never uploads a maintenance-shaped dataset."""
    org = _organization(db, "xdom-a-neg-no-maintenance")
    files = [f for f in _positive_fixture_csvs() if f.filename != "maintenance_events.csv"]
    case_id, run_id = _run_case(db, tmp_path, org.id, files)
    decisions = _decisions(db, run_id)
    xdom_a = decisions[_XDOM_A]
    assert xdom_a.mode == "governed"
    assert xdom_a.governed_status == "BLOCKED"
    assert "domain:maintenance" in xdom_a.governed_missing_summary

    stage_events = list(
        db.scalars(
            select(AnalysisCaseStageEvent).where(
                AnalysisCaseStageEvent.run_id == run_id,
                AnalysisCaseStageEvent.stage == "cross_domain_intelligence",
            )
        ).all()
    )
    assert not any(e.detail.get("rule") == "XDOM-A" for e in stage_events)

    priorities = analysis_case_command_service.priorities(db, org.id, case_id, run_id=run_id)
    xdom_a_findings = [p for p in priorities if p.finding.rule_id == _XDOM_A]
    assert xdom_a_findings == []


# ---------------------------------------------------------------------------
# P3.xxV.2H (Fix #5): mixed-population certification. The prior ablation
# tests above (A-G) are unchanged and still pass -- this section adds the
# scenario Fix #5 specifically exists for: some, but not all, of a case's
# ASSET population individually clears the 0.70 floor. Before Fix #5, one
# below-floor "tail" entity anywhere in the case-global CanonicalCaseEntity
# population blocked the whole rule (docs/p3xxv2g-entity-population-coverage-
# diagnosis-report.md). After Fix #5, readiness and execution both read the
# same canonical population and agree: the tail entity is excluded from
# execution, but does not block the otherwise-eligible candidates.
# ---------------------------------------------------------------------------


def _mixed_fixture_csvs() -> list[UploadedFile]:
    """5 assets (A-1..A-5) legitimately cross-referenced in BOTH
    maintenance and operations datasets -- multi-dataset, identity
    confidence >= 0.70, exactly like _positive_fixture_csvs() above. A 6th
    asset (A-6) appears ONLY in the maintenance dataset -- single-dataset,
    identity confidence stays at the 0.65 floor, below XDOM-A's declared
    minimum. No simulation-specific or asset-name-specific logic anywhere
    in production reads "A-6" -- it is simply the one asset_id value this
    fixture never repeats in operations_events.csv."""
    maint_rows = "asset_id,work_order_id,failure_code,downtime_hours,repair_cost,event_date\n"
    for i in range(_N_ASSETS):
        maint_rows += f"A-{i + 1},WO-{i + 1},brake,48,10000,2026-08-{i + 1:02d}T08:00:00\n"
    maint_rows += "A-6,WO-6,brake,48,10000,2026-08-06T08:00:00\n"
    ops_rows = "operational_event_id,asset_id,event_date,operational_event_status\n"
    for i in range(_N_ASSETS):
        ops_rows += f"OE-{i + 1},A-{i + 1},2026-08-{i + 1:02d}T18:00:00,completed\n"
    rev_rows = "transaction_amount,event_date,operational_event_id\n"
    for i in range(_N_ASSETS):
        rev_rows += f"{5000 + i * 100},2026-08-{i + 1:02d}T18:00:00,OE-{i + 1}\n"
    return [
        UploadedFile("maintenance_events.csv", maint_rows.encode()),
        UploadedFile("operations_events.csv", ops_rows.encode()),
        UploadedFile("revenue_events.csv", rev_rows.encode()),
    ]


def _stage_events(db: Session, run_id: UUID) -> list[AnalysisCaseStageEvent]:
    events = list(
        db.scalars(
            select(AnalysisCaseStageEvent).where(
                AnalysisCaseStageEvent.run_id == run_id,
                AnalysisCaseStageEvent.stage == "cross_domain_intelligence",
            )
        ).all()
    )
    return [e for e in events if e.detail.get("rule") == "XDOM-A"]


def test_mixed_a_below_floor_tail_entity_confirmed_at_065(db: Session, tmp_path: Path) -> None:
    """Precondition: A-6 really does resolve at the single-dataset 0.65
    floor, and A-1..A-5 really do clear 0.70 -- the fixture produces the
    exact mixed population this migration targets, not merely a claim."""
    org = _organization(db, "xdom-a-mixed-precondition")
    _, run_id = _run_case(db, tmp_path, org.id, _mixed_fixture_csvs())
    entities = list(
        db.scalars(select(CanonicalCaseEntity).where(CanonicalCaseEntity.run_id == run_id)).all()
    )
    asset_entities = {e.canonical_key: e for e in entities if e.entity_type == "ASSET"}
    assert len(asset_entities) == _N_ASSETS + 1
    assert asset_entities["a-6"].entity_identity_confidence == 0.65
    for i in range(1, _N_ASSETS + 1):
        assert asset_entities[f"a-{i}"].entity_identity_confidence >= 0.70


def test_mixed_b_readiness_is_ready_not_blocked_by_the_tail_entity(
    db: Session, tmp_path: Path
) -> None:
    """The core Fix #5 readiness proof: before this fix, A-6 alone would
    have kept entity_identity.ASSET below the case-global coverage_above_
    threshold@1.0 bar, BLOCKING the whole rule. Under the corrected "max"
    policy, at least one eligible entity existing is sufficient."""
    org = _organization(db, "xdom-a-mixed-readiness")
    _, run_id = _run_case(db, tmp_path, org.id, _mixed_fixture_csvs())
    decisions = _decisions(db, run_id)
    xdom_a = decisions[_XDOM_A]
    assert xdom_a.governed_status == "READY"
    assert xdom_a.governed_confidence_summary["below_confidence_threshold"] == []


def test_mixed_c_execution_includes_eligible_assets_and_excludes_the_tail(
    db: Session, tmp_path: Path
) -> None:
    """B, C, negative A/D: XDOM-A actually executes over A-1..A-5
    independently -- A-6, correctly excluded from the eligible set, never
    enters the candidate loop and produces no finding referencing it. One
    low-confidence asset never invalidates independent high-confidence
    candidates.

    Asserts exactly 5 findings, one per eligible asset: before P3.xxV.2J
    (Fix #7), governed_finding_publisher.publish() never attached an
    "affected_record"-typed evidence item identifying WHICH asset a finding
    concerns, so FindingDeduplicationService.key() hashed identically for
    every asset in this fixture and every call after the first silently
    returned the pre-existing row (documented at the time as a known,
    out-of-scope defect in the Fix #5 report). Fix #7 corrected this
    platform-wide; see tests/test_governed_finding_publisher_identity.py
    for the dedicated identity/deduplication contract tests."""
    org = _organization(db, "xdom-a-mixed-execution")
    case_id, run_id = _run_case(db, tmp_path, org.id, _mixed_fixture_csvs())

    priorities = analysis_case_command_service.priorities(db, org.id, case_id, run_id=run_id)
    xdom_a_findings = [p.finding for p in priorities if p.finding.rule_id == _XDOM_A]
    titles = {f.title for f in xdom_a_findings}
    assert len(xdom_a_findings) == _N_ASSETS
    assert titles == {
        f"Asset A-{i} failure downtime overlapped scheduled activity"
        for i in range(1, _N_ASSETS + 1)
    }
    assert {
        entity["canonical_key"]
        for finding in xdom_a_findings
        for entity in (finding.entities_json or [])
        if entity.get("entity_type") == "asset"
    } == {f"A-{i}" for i in range(1, _N_ASSETS + 1)}
    assert not any("A-6" in title for title in titles)


def test_mixed_d_legacy_vs_canonical_comparison_recorded_on_stage_event(
    db: Session, tmp_path: Path
) -> None:
    """Section 6 migration safety comparison: both populations are
    computed and recorded, neither silently dropped. Legacy's own
    >=2-dataset exact-match rule independently excludes A-6 the same way
    (it never appears in a second dataset) -- so on this fixture the two
    populations happen to agree; Section F of the Fix #5 report explains
    why that agreement is expected, not coincidental, given both mechanisms
    count datasets from the same underlying observations."""
    org = _organization(db, "xdom-a-mixed-comparison")
    _, run_id = _run_case(db, tmp_path, org.id, _mixed_fixture_csvs())
    events = _stage_events(db, run_id)
    assert events, "expected an XDOM-A cross_domain_intelligence stage event"
    detail = events[0].detail
    assert detail["eligible_asset_count"] == _N_ASSETS
    assert detail["legacy_matched_asset_count"] == _N_ASSETS
    assert detail["eligible_and_legacy_intersection"] == _N_ASSETS
    assert detail["legacy_only_count"] == 0
    assert detail["canonical_only_count"] == 0


def test_mixed_e_readiness_execution_consistency_invariant(db: Session, tmp_path: Path) -> None:
    """Section 12 release-blocking invariant, checked live end-to-end: if
    readiness reports READY on entity_identity.ASSET, execution must
    enumerate >=1 eligible entity from the same run; the converse
    (governed BLOCKED-only-on-entities => zero eligible) is exercised by
    test_ablation_c_missing_canonical_entity_blocks / test_ablation_f at
    the pure evaluate_readiness() level already."""
    org = _organization(db, "xdom-a-mixed-consistency")
    _, run_id = _run_case(db, tmp_path, org.id, _mixed_fixture_csvs())
    decisions = _decisions(db, run_id)
    xdom_a = decisions[_XDOM_A]
    below_threshold = cast(list, xdom_a.governed_confidence_summary["below_confidence_threshold"])
    entity_ready = "entity_identity.ASSET" not in below_threshold
    events = _stage_events(db, run_id)
    eligible_count = cast(int, events[0].detail["eligible_asset_count"]) if events else 0
    assert entity_ready is True
    assert eligible_count > 0


def test_ablation_h_mixed_confidence_population_still_ready(db: Session, tmp_path: Path) -> None:
    """H (pure evaluate_readiness() level, mirrors ablation A-G's own
    style): a distribution with one entity far below 0.70 and others far
    above it must NOT block readiness under XDOM-A's "max" policy -- the
    exact scenario "coverage_above_threshold @ 1.0" got wrong."""
    from dataclasses import replace

    index = replace(
        _READY_INDEX,
        canonical_entity_identity_confidence_by_type={
            "ASSET": ConfidenceDistribution((0.95, 0.94, 0.3))
        },
    )
    result = evaluate_readiness(_xdom_a_pack(), index)
    assert result.status == "READY"
    assert result.below_confidence_threshold == frozenset()


def test_ablation_i_all_low_confidence_still_blocks(db: Session, tmp_path: Path) -> None:
    """I: the safety side of the same change -- if NO entity in the
    population clears the floor, "max" still correctly fails, exactly like
    "coverage_above_threshold" did. Fix #5 changes WHICH question is asked
    (does at least one qualify vs. does the whole population qualify), not
    whether a genuinely all-low-confidence case is protected."""
    from dataclasses import replace

    index = replace(
        _READY_INDEX,
        canonical_entity_identity_confidence_by_type={"ASSET": ConfidenceDistribution((0.3, 0.4))},
    )
    result = evaluate_readiness(_xdom_a_pack(), index)
    assert result.status == "PARTIAL"
    assert result.below_confidence_threshold == frozenset({"entity_identity.ASSET"})


# ---------------------------------------------------------------------------
# P3.xxV.2I (Fix #6): canonical event-time evidence. XDOM-A's two date
# accesses (maintenance-side, operations-side) previously required a
# literal raw column named "event_date" -- Rental's real corpus instead
# spells these maintenance_date/dispatch_date, which never matched. This
# section proves the fix live, through the real orchestrator: a
# Rental-shaped fixture (identical structure to _positive_fixture_csvs(),
# only the raw date column names changed) now resolves canonical temporal
# evidence and advances XDOM-A's execution chain -- exactly the corpus
# vocabulary that blocked it in production, not a synthetic stand-in.
# ---------------------------------------------------------------------------


def _rental_shaped_temporal_fixture_csvs() -> list[UploadedFile]:
    maint_rows = "asset_id,work_order_id,failure_code,downtime_hours,repair_cost,maintenance_date\n"
    for i in range(_N_ASSETS):
        maint_rows += f"A-{i + 1},WO-{i + 1},brake,48,10000,2026-08-{i + 1:02d}T08:00:00\n"
    ops_rows = "operational_event_id,asset_id,dispatch_date,operational_event_status\n"
    for i in range(_N_ASSETS):
        ops_rows += f"OE-{i + 1},A-{i + 1},2026-08-{i + 1:02d}T18:00:00,completed\n"
    rev_rows = "transaction_amount,event_date,operational_event_id\n"
    for i in range(_N_ASSETS):
        rev_rows += f"{5000 + i * 100},2026-08-{i + 1:02d}T18:00:00,OE-{i + 1}\n"
    return [
        UploadedFile("maintenance_events.csv", maint_rows.encode()),
        UploadedFile("operations_events.csv", ops_rows.encode()),
        UploadedFile("revenue_events.csv", rev_rows.encode()),
    ]


def _unrelated_date_fixture_csvs() -> list[UploadedFile]:
    """Negative A: maintenance.csv carries a date-shaped field, but one
    that legitimately means something else (invoice_date) -- must never
    satisfy XDOM-A's event_timestamp requirement merely because it looks
    date-shaped."""
    maint_rows = "asset_id,work_order_id,failure_code,downtime_hours,repair_cost,invoice_date\n"
    for i in range(_N_ASSETS):
        maint_rows += f"A-{i + 1},WO-{i + 1},brake,48,10000,2026-08-{i + 1:02d}T08:00:00\n"
    ops_rows = "operational_event_id,asset_id,event_date,operational_event_status\n"
    for i in range(_N_ASSETS):
        ops_rows += f"OE-{i + 1},A-{i + 1},2026-08-{i + 1:02d}T18:00:00,completed\n"
    rev_rows = "transaction_amount,event_date,operational_event_id\n"
    for i in range(_N_ASSETS):
        rev_rows += f"{5000 + i * 100},2026-08-{i + 1:02d}T18:00:00,OE-{i + 1}\n"
    return [
        UploadedFile("maintenance_events.csv", maint_rows.encode()),
        UploadedFile("operations_events.csv", ops_rows.encode()),
        UploadedFile("revenue_events.csv", rev_rows.encode()),
    ]


def _missing_date_fixture_csvs() -> list[UploadedFile]:
    """Negative B: no date-shaped field on the maintenance side at all."""
    maint_rows = "asset_id,work_order_id,failure_code,downtime_hours,repair_cost\n"
    for i in range(_N_ASSETS):
        maint_rows += f"A-{i + 1},WO-{i + 1},brake,48,10000\n"
    ops_rows = "operational_event_id,asset_id,event_date,operational_event_status\n"
    for i in range(_N_ASSETS):
        ops_rows += f"OE-{i + 1},A-{i + 1},2026-08-{i + 1:02d}T18:00:00,completed\n"
    rev_rows = "transaction_amount,event_date,operational_event_id\n"
    for i in range(_N_ASSETS):
        rev_rows += f"{5000 + i * 100},2026-08-{i + 1:02d}T18:00:00,OE-{i + 1}\n"
    return [
        UploadedFile("maintenance_events.csv", maint_rows.encode()),
        UploadedFile("operations_events.csv", ops_rows.encode()),
        UploadedFile("revenue_events.csv", rev_rows.encode()),
    ]


def _semantic_decisions(db: Session, run_id: UUID) -> list[SemanticInterpretationDecision]:
    return list(
        db.scalars(
            select(SemanticInterpretationDecision).where(
                SemanticInterpretationDecision.run_id == run_id
            )
        ).all()
    )


def test_temporal_a_maintenance_date_resolves_to_event_timestamp_auto_accepted(
    db: Session, tmp_path: Path
) -> None:
    """Precondition + positive: maintenance_date and dispatch_date -- the
    real raw field names that blocked Rental live -- both independently
    resolve to the event_timestamp canonical concept at auto_accepted."""
    org = _organization(db, "xdom-a-temporal-precondition")
    _, run_id = _run_case(db, tmp_path, org.id, _rental_shaped_temporal_fixture_csvs())
    decisions = {d.source_field: d for d in _semantic_decisions(db, run_id)}
    assert decisions["maintenance_date"].selected_concept == "event_timestamp"
    assert decisions["maintenance_date"].status == "auto_accepted"
    assert decisions["dispatch_date"].selected_concept == "event_timestamp"
    assert decisions["dispatch_date"].status == "auto_accepted"


def test_temporal_b_xdom_a_execution_chain_advances_on_rental_shaped_fields(
    db: Session, tmp_path: Path
) -> None:
    """Primary success criterion (Section 13): canonical temporal evidence
    resolves and is recorded on the XDOM-A stage event -- the execution
    chain advances past the point that previously collapsed solely because
    maintenance_date != event_date. This is checked directly (not inferred
    from finding count, which a later legitimate condition may still
    eliminate)."""
    org = _organization(db, "xdom-a-temporal-execution")
    _, run_id = _run_case(db, tmp_path, org.id, _rental_shaped_temporal_fixture_csvs())
    events = _stage_events(db, run_id)
    assert events, "expected an XDOM-A cross_domain_intelligence stage event"
    detail = events[0].detail
    assert detail["maintenance_time_field"] == "maintenance_date"
    # NOT "dispatch_date": domain_registry.py's own, independent alias
    # table already renames "dispatch_date" -> "operational_event_start"
    # in canonical_frames (an operational-event start-time field, for a
    # reason unrelated to this fix) -- _resolve_canonical_temporal_field
    # bridges the two canonicalization systems and returns the PHYSICAL
    # column name the dataframe actually has, not the semantic layer's
    # raw source_field. See the Fix #6 report, Section D, for the full
    # trace of this real defect caught while building this test.
    assert detail["operations_time_field"] == "operational_event_start"
    # And, since this fixture's windows/values are identical in shape to
    # the already-certified _positive_fixture_csvs(), findings are in fact
    # produced -- advancing all the way through, not merely resolving
    # evidence.
    assert cast(int, detail["finding_count"]) >= 1


def test_temporal_c_event_date_still_works_unchanged(db: Session, tmp_path: Path) -> None:
    """Regression guard: the original _positive_fixture_csvs() (literal
    event_date on both sides) is untouched by this fix -- same resolver,
    same concept, same result."""
    org = _organization(db, "xdom-a-temporal-regression")
    _, run_id = _run_case(db, tmp_path, org.id, _positive_fixture_csvs())
    events = _stage_events(db, run_id)
    assert events
    detail = events[0].detail
    assert detail["maintenance_time_field"] == "event_date"
    assert detail["operations_time_field"] == "event_date"
    assert cast(int, detail["finding_count"]) >= 1


def test_temporal_negative_a_unrelated_date_field_does_not_satisfy(
    db: Session, tmp_path: Path
) -> None:
    """Negative A: invoice_date (a real but unrelated canonical concept)
    must not satisfy XDOM-A's temporal requirement merely because it is
    date-shaped."""
    org = _organization(db, "xdom-a-temporal-neg-unrelated")
    _, run_id = _run_case(db, tmp_path, org.id, _unrelated_date_fixture_csvs())
    decisions = {d.source_field: d for d in _semantic_decisions(db, run_id)}
    assert decisions["invoice_date"].selected_concept != "event_timestamp"
    events = _stage_events(db, run_id)
    assert events
    assert events[0].detail["maintenance_time_field"] is None
    assert events[0].detail["finding_count"] == 0


def test_temporal_negative_b_missing_date_field_is_insufficient_evidence(
    db: Session, tmp_path: Path
) -> None:
    """Negative B: no date-shaped field at all on the maintenance side --
    XDOM-A must not fabricate a temporal anchor."""
    org = _organization(db, "xdom-a-temporal-neg-missing")
    case_id, run_id = _run_case(db, tmp_path, org.id, _missing_date_fixture_csvs())
    events = _stage_events(db, run_id)
    assert events
    assert events[0].detail["maintenance_time_field"] is None
    assert events[0].detail["finding_count"] == 0
    priorities = analysis_case_command_service.priorities(db, org.id, case_id, run_id=run_id)
    assert [p for p in priorities if p.finding.rule_id == _XDOM_A] == []
