"""P3.xxI.2C: billable subject generalization -- unit coverage for the
concept-registry reverse lookup, the readiness alternative-entity-set
evaluator, the subject-generic revenue-variance service, and the new
orchestration-layer governed identifier bridge. Full live certification
(the real semantic pipeline, real Rental fixtures, real orchestration
execute() run) is reported separately in
docs/p3xxi2c-billable-subject-generalization.md -- these tests instead
prove each layer's OWN new mechanism directly and cheaply, using hand-built
semantic decisions rather than the full confidence engine, matching this
suite's own established style (tests/test_revenue_amount_variance.py does
the same for the service layer)."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.entities.entity_type import EntityType
from app.intelligence_packs.registry import (
    IntelligencePackDefinition,
    default_intelligence_pack_registry,
)
from app.models.analysis_case import AnalysisCaseDataset
from app.models.entities import Finding, Organization
from app.models.intelligence_activation import IntelligenceActivationDecision
from app.schemas.contracts import OrganizationCreate
from app.semantic.candidate import InterpretationDecision
from app.semantic.concept_registry import default_canonical_concept_registry
from app.services.analysis_case_orchestration_service import (
    SemanticInterpretationOutcome,
    analysis_case_orchestration_service,
)
from app.services.analysis_case_service import AnalysisCaseService, UploadedFile
from app.services.governed_cross_dataset_rate import RateDatasetFields
from app.services.intelligence_readiness_service import evaluate_readiness
from app.services.organization_service import OrganizationService
from app.services.revenue_variance_intelligence_service import (
    DatasetConceptFields,
    run_revenue_amount_variance,
)
from app.storage.local_storage import LocalFileStorage

_RULE_CODE = "REVENUE-AMOUNT-VARIANCE"

# ---------------------------------------------------------------------------
# Section 1: concept registry reverse lookup
# ---------------------------------------------------------------------------


def test_identifier_concept_codes_for_entity_type_contract_closes_the_documented_gap() -> None:
    codes = default_canonical_concept_registry.identifier_concept_codes_for_entity_type("CONTRACT")
    assert codes == frozenset({"contract_id"})


def test_identifier_concept_codes_for_entity_type_event_new_dispatch_concept() -> None:
    codes = default_canonical_concept_registry.identifier_concept_codes_for_entity_type("EVENT")
    assert codes == frozenset({"dispatch_id"})


def test_identifier_concept_codes_for_entity_type_work_order_unchanged() -> None:
    codes = default_canonical_concept_registry.identifier_concept_codes_for_entity_type(
        "WORK_ORDER"
    )
    assert codes == frozenset({"work_order_id"})


def test_identifier_concept_codes_for_entity_type_unregistered_returns_empty() -> None:
    # LOCATION/PRODUCT/TRANSACTION are still forward-declared with no
    # backing concept -- this milestone closed CONTRACT/EVENT specifically,
    # never speculatively closed every gap.
    assert (
        default_canonical_concept_registry.identifier_concept_codes_for_entity_type("LOCATION")
        == frozenset()
    )
    assert (
        default_canonical_concept_registry.identifier_concept_codes_for_entity_type("PRODUCT")
        == frozenset()
    )


# ---------------------------------------------------------------------------
# Section 2: readiness alternative_canonical_entity_sets
# ---------------------------------------------------------------------------


class _FakeIndex:
    """Minimal stand-in for CaseCapabilityIndex -- only the attributes
    evaluate_readiness actually reads for entity-set evaluation."""

    def __init__(
        self,
        canonical_entity_types_present: frozenset[str],
        confidence_by_type: dict[str, _FakeDistribution],
    ) -> None:
        self.available_domains: frozenset[str] = frozenset()
        self.available_canonical_fields: frozenset[str] = frozenset()
        self.resolved_entity_types: frozenset[str] = frozenset()
        self.canonical_entity_types_present = canonical_entity_types_present
        self.canonical_relationship_types_present: frozenset[str] = frozenset()
        self.activity_types_present: frozenset[str] = frozenset()
        self.precedes_pairs_present: frozenset[tuple[str, str]] = frozenset()
        self.named_states_present: frozenset[str] = frozenset()
        # Only the entity side is under test here; the measure side is
        # pre-satisfied with dummy entries so it never masks the entity
        # assertions below (evaluate_readiness only checks measure KEYS
        # against alternative_canonical_measure_sets, never their values).
        self.canonical_measures: dict = {"quantity": object(), "unit_price": object()}
        self.currency_unresolved = False
        self.distinct_currencies_observed: frozenset[str] = frozenset()
        self.distinct_units_observed_by_measure: dict = {}
        self.domains_with_resolved_trust: frozenset[str] = frozenset()
        self.canonical_entity_identity_confidence_by_type = confidence_by_type
        self.canonical_relationship_confidence_by_type: dict = {}
        self.activity_type_confidence_by_type: dict = {}
        self.precedes_pair_confidence: dict = {}
        self.state_meaning_confidence_by_state: dict = {}


class _FakeDistribution:
    def __init__(self, value: float) -> None:
        self.min = value
        self.median = value
        self.max = value

    def coverage_above(self, minimum: float) -> float:
        return 1.0 if self.min >= minimum else 0.0


def _rev_var_pack() -> IntelligencePackDefinition:
    pack = default_intelligence_pack_registry().get("REVENUE-AMOUNT-VARIANCE")
    assert pack is not None
    return pack


def test_readiness_satisfied_by_work_order_when_present_unchanged_behavior() -> None:
    pack = _rev_var_pack()
    index = _FakeIndex(
        canonical_entity_types_present=frozenset({EntityType.WORK_ORDER.value}),
        confidence_by_type={EntityType.WORK_ORDER.value: _FakeDistribution(0.95)},
    )
    result = evaluate_readiness(pack, index)  # type: ignore[arg-type]
    assert result.missing_canonical_entities == frozenset()
    assert result.status == "READY"


def test_readiness_satisfied_by_contract_alternative_when_work_order_absent() -> None:
    pack = _rev_var_pack()
    index = _FakeIndex(
        canonical_entity_types_present=frozenset({EntityType.CONTRACT.value}),
        confidence_by_type={EntityType.CONTRACT.value: _FakeDistribution(0.95)},
    )
    result = evaluate_readiness(pack, index)  # type: ignore[arg-type]
    assert result.missing_canonical_entities == frozenset()
    assert result.status == "READY"


def test_readiness_confidence_check_applies_to_the_satisfying_type_not_the_primary() -> None:
    """The regression this test guards against: a naive port of
    alternative_canonical_measure_sets would still check confidence against
    required_canonical_entities (WORK_ORDER) even when CONTRACT is what
    actually satisfied readiness -- silently reporting PARTIAL/READY based
    on a type that isn't even present, or crashing on a missing key."""
    pack = _rev_var_pack()
    index = _FakeIndex(
        canonical_entity_types_present=frozenset({EntityType.CONTRACT.value}),
        confidence_by_type={EntityType.CONTRACT.value: _FakeDistribution(0.50)},  # below 0.70 bar
    )
    result = evaluate_readiness(pack, index)  # type: ignore[arg-type]
    assert result.missing_canonical_entities == frozenset()
    assert result.status == "PARTIAL"
    assert f"entity_identity.{EntityType.CONTRACT.value}" in result.below_confidence_threshold


def test_readiness_blocked_when_neither_alternative_present() -> None:
    pack = _rev_var_pack()
    index = _FakeIndex(
        canonical_entity_types_present=frozenset({EntityType.ASSET.value}),
        confidence_by_type={},
    )
    result = evaluate_readiness(pack, index)  # type: ignore[arg-type]
    assert result.status == "BLOCKED"
    assert EntityType.WORK_ORDER.value in result.missing_canonical_entities


# ---------------------------------------------------------------------------
# Section 3: revenue-variance service, generic subject type via ALTERNATE
# aliases (never the literal "contract_id"/"dispatch_id" strings) -- proves
# the mechanism is concept-driven, not name-driven (mission success
# criterion 10, service layer).
# ---------------------------------------------------------------------------


def _bootstrap_context(db: Session, tmp_path: Path, slug: str) -> tuple[UUID, UUID, UUID, UUID]:
    """Reuses the exact same real-orchestration bootstrap pattern
    tests/test_revenue_amount_variance.py's own Group 1 uses -- a genuine
    READY (organization_id, actor, trust_assessment_id, dataset_id), never
    used to exercise MAINT-001 itself."""
    from sqlalchemy import select

    from app.models.trust import (
        AnalyticalLevel,
        AnalyticalReadinessDecision,
        ReadinessStatus,
        TrustAssessment,
    )
    from app.services.analysis_case_orchestration_service import analysis_case_orchestration_service
    from app.services.analysis_case_service import AnalysisCaseService, UploadedFile
    from app.storage.local_storage import LocalFileStorage

    org: Organization = OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug.title(), slug=slug, country_code="US", default_currency="USD", timezone="UTC"
        ),
    )
    maint_rows = "asset_id,work_order_id,failure_code,downtime_hours,repair_cost,event_date\n"
    for i in range(5):
        maint_rows += f"A-{i + 1},WO-{i + 1},brake,48,10000,2026-08-{i + 1:02d}T08:00:00\n"
    files = [UploadedFile("maintenance_events.csv", maint_rows.encode())]
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    actor = uuid4()
    case = service.create(db, org.id, "P3xxI2C Bootstrap", "single", actor)
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


def test_run_revenue_amount_variance_contract_subject_via_agreement_id_alias(
    db: Session, tmp_path: Path
) -> None:
    """Subject entity type CONTRACT, but the raw column is literally named
    "agreement_id" (a registered alias of contract_id, never the literal
    string "contract_id") and "rate_card_id" bridging is not used here --
    this proves run_revenue_amount_variance/DatasetConceptFields work off
    the RESOLVED CONCEPT, never a hardcoded field name."""
    org_id, actor, trust_id, dataset_id = _bootstrap_context(
        db, tmp_path, "revvar-2c-contract-subject"
    )

    quantity_df = pd.DataFrame(
        {
            "agreement_id": ["CNT-1"],
            "duration": [10.0],
        }
    )
    quantity = DatasetConceptFields(
        dataset_id=dataset_id,
        dataset_label="usage.csv",
        dataframe=quantity_df,
        trust_assessment_id=trust_id,
        subject_id_field="agreement_id",
        quantity_field="duration",
        unit_price_field=None,
        invoice_amount_field=None,
        cost_amount_field=None,
        currency_field=None,
        implicit_quantity_unit="hour",
    )
    rate_df = pd.DataFrame({"agreement_id": ["CNT-1"], "day_rate": [100.0]})
    rate = RateDatasetFields(
        dataset_id=dataset_id,
        dataset_label="contracts.csv",
        dataframe=rate_df,
        contract_id_field="agreement_id",
        rate_field="day_rate",
        effective_from_field=None,
        effective_to_field=None,
        unit_field=None,
        currency_field=None,
        implicit_unit="hour",
        temporal_authority_unresolved=False,
    )
    actual_df = pd.DataFrame({"agreement_id": ["CNT-1"], "amount": [800.0]})
    actual = DatasetConceptFields(
        dataset_id=dataset_id,
        dataset_label="invoices.csv",
        dataframe=actual_df,
        trust_assessment_id=trust_id,
        subject_id_field="agreement_id",
        quantity_field=None,
        unit_price_field=None,
        invoice_amount_field="amount",
        cost_amount_field=None,
        currency_field=None,
    )

    findings = run_revenue_amount_variance(
        db,
        org_id,
        [quantity, actual],
        {"CNT-1"},
        actor,
        [rate],
        subject_entity_type="contract",
    )
    assert len(findings) == 1
    finding = findings[0]
    assert finding.exposure_value == 200
    assert finding.entities_json == [{"entity_type": "contract", "canonical_key": "CNT-1"}]


# ---------------------------------------------------------------------------
# Section 4: orchestration-layer governed identifier bridge -- direct unit
# coverage of the new _resolve_identifier_bridge_map /
# _resolve_subject_field_for_dataset methods, using a THIRD, synthetic
# subject/bridge shape (neither FieldMaintenance's work_order_id nor
# Rental's literal dispatch_id/contract_id spellings) via the
# service_event_id / rate_card_id aliases already registered -- mission
# success criterion 10, orchestration layer.
# ---------------------------------------------------------------------------


def _decision(source_field: str, concept: str, dataset_id: str = "ds") -> InterpretationDecision:
    return InterpretationDecision(
        source_dataset_id=dataset_id,
        source_field=source_field,
        selected_concept=concept,
        confidence=0.95,
        status="auto_accepted",
        evidence_summary=[],
        alternative_candidates=[],
        decision_source="test",
        decision_version="1.0",
    )


def _case_dataset(dataset_id: UUID | None = None, label: str = "ds") -> AnalysisCaseDataset:
    return AnalysisCaseDataset(id=uuid4(), dataset_id=dataset_id or uuid4(), source_label=label)


def test_resolve_identifier_bridge_map_builds_one_hop_bridge_via_alternate_aliases() -> None:
    events = _case_dataset(label="events.csv")
    events_df = pd.DataFrame(
        {
            "svc_event": ["EVT-1", "EVT-2", "EVT-3"],
            "rate_card": ["RC-1", "RC-1", "RC-2"],
            "asset": ["A-1", "A-1", "A-2"],
        }
    )
    semantic_outcome = SemanticInterpretationOutcome(
        case_context=None,  # type: ignore[arg-type]
        decisions_by_case_dataset={
            events.id: [
                _decision("svc_event", "dispatch_id"),
                _decision("rate_card", "contract_id"),
            ]
        },
    )
    bridge_map = analysis_case_orchestration_service._resolve_identifier_bridge_map(
        [events], {events.id: events_df}, semantic_outcome, "dispatch_id", "contract_id"
    )
    assert bridge_map == {"EVT-1": "RC-1", "EVT-2": "RC-1", "EVT-3": "RC-2"}


def test_resolve_identifier_bridge_map_drops_ambiguous_bridge_values() -> None:
    events = _case_dataset(label="events.csv")
    # EVT-1 maps to two DIFFERENT rate cards across rows -- ambiguous,
    # must be dropped, never guessed.
    events_df = pd.DataFrame({"svc_event": ["EVT-1", "EVT-1"], "rate_card": ["RC-1", "RC-2"]})
    semantic_outcome = SemanticInterpretationOutcome(
        case_context=None,  # type: ignore[arg-type]
        decisions_by_case_dataset={
            events.id: [
                _decision("svc_event", "dispatch_id"),
                _decision("rate_card", "contract_id"),
            ]
        },
    )
    bridge_map = analysis_case_orchestration_service._resolve_identifier_bridge_map(
        [events], {events.id: events_df}, semantic_outcome, "dispatch_id", "contract_id"
    )
    assert bridge_map == {}


def test_resolve_subject_field_for_dataset_prefers_direct_resolution() -> None:
    ds = _case_dataset(label="invoices.csv")
    df = pd.DataFrame({"rate_card": ["RC-1"], "amount": [100.0]})
    semantic_outcome = SemanticInterpretationOutcome(
        case_context=None,  # type: ignore[arg-type]
        decisions_by_case_dataset={ds.id: [_decision("rate_card", "contract_id")]},
    )
    result_df, field, evidence_concept = (
        analysis_case_orchestration_service._resolve_subject_field_for_dataset(
            ds, df, [ds], {ds.id: df}, semantic_outcome, frozenset({"contract_id"})
        )
    )
    assert field == "rate_card"
    assert evidence_concept == "contract_id"
    assert result_df is df  # never copied when resolution is direct


def test_resolve_subject_field_for_dataset_bridges_when_direct_absent() -> None:
    events = _case_dataset(label="events.csv")
    events_df = pd.DataFrame(
        {"svc_event": ["EVT-1", "EVT-2", "EVT-3"], "rate_card": ["RC-1", "RC-1", "RC-2"]}
    )
    usage = _case_dataset(label="usage.csv")
    usage_df = pd.DataFrame({"svc_event": ["EVT-1"], "duration": [5.0]})
    semantic_outcome = SemanticInterpretationOutcome(
        case_context=None,  # type: ignore[arg-type]
        decisions_by_case_dataset={
            events.id: [
                _decision("svc_event", "dispatch_id"),
                _decision("rate_card", "contract_id"),
            ],
            usage.id: [
                _decision("svc_event", "dispatch_id"),
                _decision("duration", "duration_hours"),
            ],
        },
    )
    result_df, field, evidence_concept = (
        analysis_case_orchestration_service._resolve_subject_field_for_dataset(
            usage,
            usage_df,
            [events, usage],
            {events.id: events_df, usage.id: usage_df},
            semantic_outcome,
            frozenset({"contract_id"}),
        )
    )
    assert field is not None
    assert evidence_concept == "dispatch_id"
    assert result_df is not usage_df  # bridged: a copy with the new column
    assert result_df.loc[0, field] == "RC-1"


def test_resolve_subject_field_for_dataset_bridge_disabled_for_rate_card_shaped() -> None:
    events = _case_dataset(label="events.csv")
    events_df = pd.DataFrame({"svc_event": ["EVT-1"], "rate_card": ["RC-1"]})
    rate_card_ds = _case_dataset(label="rate_cards.csv")
    rate_card_df = pd.DataFrame({"svc_event": ["EVT-1"], "day_rate": [100.0]})
    semantic_outcome = SemanticInterpretationOutcome(
        case_context=None,  # type: ignore[arg-type]
        decisions_by_case_dataset={
            events.id: [
                _decision("svc_event", "dispatch_id"),
                _decision("rate_card", "contract_id"),
            ],
            rate_card_ds.id: [
                _decision("svc_event", "dispatch_id"),
                _decision("day_rate", "unit_price"),
            ],
        },
    )
    result_df, field, evidence_concept = (
        analysis_case_orchestration_service._resolve_subject_field_for_dataset(
            rate_card_ds,
            rate_card_df,
            [events, rate_card_ds],
            {events.id: events_df, rate_card_ds.id: rate_card_df},
            semantic_outcome,
            frozenset({"contract_id"}),
            allow_bridge=False,
        )
    )
    assert field is None
    assert evidence_concept is None
    assert result_df is rate_card_df


def test_resolve_subject_field_for_dataset_returns_none_when_no_path_exists() -> None:
    ds = _case_dataset(label="unrelated.csv")
    df = pd.DataFrame({"note": ["hello"]})
    semantic_outcome = SemanticInterpretationOutcome(
        case_context=None,  # type: ignore[arg-type]
        decisions_by_case_dataset={ds.id: []},
    )
    result_df, field, evidence_concept = (
        analysis_case_orchestration_service._resolve_subject_field_for_dataset(
            ds, df, [ds], {ds.id: df}, semantic_outcome, frozenset({"contract_id"})
        )
    )
    assert field is None
    assert evidence_concept is None


# ---------------------------------------------------------------------------
# Section 5: full, unmodified orchestration.execute() run -- the real
# semantic pipeline, real entity resolution, real readiness evaluator, real
# claim-exclusive subject-type iteration. A CONTRACT-only-shaped schema
# (no work_order_id concept anywhere in the case) using a THIRD set of
# raw column names -- neither FieldMaintenance's nor Rental's own literal
# spellings -- through the dispatch_id/contract_id ALIASES already
# registered (assignment_id/agreement_id/rate_card_id), mirroring
# test_generalization_different_schema_same_invariant's own established
# pattern one level up (mission success criterion 10, full pipeline).
# ---------------------------------------------------------------------------

_N_CONTRACTS = 6


def _organization(db: Session, slug: str) -> Organization:
    return OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug.title(), slug=slug, country_code="US", default_currency="USD", timezone="UTC"
        ),
    )


def _run_case(
    db: Session, tmp_path: Path, org_id: UUID, files: list[UploadedFile], name: str
) -> tuple[UUID, UUID]:
    service = AnalysisCaseService(storage=LocalFileStorage(str(tmp_path)))
    actor = uuid4()
    case = service.create(db, org_id, name, "single", actor)
    service.register_artifacts(db, org_id, case.id, files, actor)
    run = analysis_case_orchestration_service.start_run(db, org_id, case.id, actor)
    analysis_case_orchestration_service.execute(db, service.storage, org_id, case.id, run.id, actor)
    return case.id, run.id


def test_contract_subject_end_to_end_via_alias_only_schema_no_work_order_anywhere(
    db: Session, tmp_path: Path
) -> None:
    """No column anywhere in this fixture aliases to work_order_id -- the
    WORK_ORDER subject-type pass must find zero eligible entities and
    contribute nothing; every finding must come from the CONTRACT
    alternative, resolved entirely through governed concept aliases
    (dispatch_id -> the new EVENT-typed concept, agreement_id/rate_card_id
    -> contract_id, hours_used -> duration_hours, labor_rate ->
    hourly_rate). usage.csv's own dispatch_id carries no contract_id
    sibling (only assignments.csv does), so its own per-dataset resolution
    sits at ACCEPTED_WITH_FLAG -- the governed one-hop bridge is what
    actually attributes its quantity evidence to a contract, not a direct
    per-row resolution, proving the bridge mechanism itself, not just
    direct-resolution CONTRACT mode (which Section 3's service-level test
    already covers)."""
    org = _organization(db, "revvar-2c-contract-e2e")
    assignments = "dispatch_id,agreement_id,asset_id\n"
    usage = "dispatch_id,hours_used,dispatch_date\n"
    rate_cards = "rate_card_id,labor_rate\n"
    billing = "bill_id,agreement_id,amount,status\n"
    for i in range(_N_CONTRACTS):
        n = i + 1
        assignments += f"DSP-{n},AGR-{n},AST-{n}\n"
        usage += f"DSP-{n},10,2026-06-0{n}\n"
        rate_cards += f"AGR-{n},100\n"
        billing += f"BILL-{n},AGR-{n},800,ISSUED\n"
    files = [
        UploadedFile("assignments.csv", assignments.encode()),
        UploadedFile("usage.csv", usage.encode()),
        UploadedFile("rate_cards.csv", rate_cards.encode()),
        UploadedFile("billing.csv", billing.encode()),
    ]
    _, run_id = _run_case(db, tmp_path, org.id, files, "Contract subject E2E")

    decision = db.scalar(
        select(IntelligenceActivationDecision).where(
            IntelligenceActivationDecision.run_id == run_id,
            IntelligenceActivationDecision.rule_code == _RULE_CODE,
        )
    )
    assert decision is not None
    assert decision.governed_status == "READY"

    findings = list(
        db.scalars(
            select(Finding).where(
                Finding.organization_id == org.id, Finding.definition_code == _RULE_CODE
            )
        ).all()
    )
    assert len(findings) == _N_CONTRACTS
    assert all(f.exposure_value == 200 for f in findings)
    for f in findings:
        assert f.entities_json is not None
        assert f.entities_json[0]["entity_type"] == "contract"
    contract_keys = {f.entities_json[0]["canonical_key"] for f in findings if f.entities_json}
    assert contract_keys == {f"AGR-{i + 1}" for i in range(_N_CONTRACTS)}
