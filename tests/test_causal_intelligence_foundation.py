from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, configure_mappers

from app.db.session import Base
from app.models.canonical_mapping import (
    CanonicalEntity,
    CanonicalEntityType,
    CanonicalEvent,
    CanonicalEventType,
)
from app.models.causal_intelligence import (
    CausalAuditEvent,
    CausalChain,
    CausalChainVersion,
    CausalEdge,
    CausalEvidenceLink,
    CausalHypothesis,
    CausalIntervention,
    CausalMethodDefinition,
    CausalNode,
    CausalOutcomeAssessment,
    CausalReview,
)
from app.schemas.actions import ActionCreate, ActionOutcomeCreate
from app.schemas.causal_intelligence import (
    CausalEvidenceLinkCreate,
    CausalHypothesisCreate,
    CausalInterventionCreate,
    CausalMethodDefinitionCreate,
    CausalNodeCreate,
    CausalOutcomeAssessmentCreate,
    CausalReviewCreate,
)
from app.schemas.contracts import OrganizationCreate
from app.services.action_service import ActionService
from app.services.causal_intelligence_service import (
    CausalIntelligenceServiceError,
    causal_chain_service,
    causal_evaluation_service,
    causal_evidence_service,
    causal_hypothesis_service,
    causal_intervention_service,
    causal_node_service,
    causal_ontology_service,
    causal_outcome_assessment_service,
    causal_review_service,
    root_cause_ranking_service,
)
from app.services.organization_service import OrganizationService

CAUSAL_TABLES = {
    "causal_method_definitions",
    "causal_nodes",
    "causal_hypotheses",
    "causal_evidence_links",
    "causal_reviews",
    "causal_edges",
    "causal_chains",
    "causal_chain_versions",
    "causal_interventions",
    "causal_outcome_assessments",
    "causal_audit_events",
}
CAUSAL_MODELS = [
    CausalMethodDefinition,
    CausalNode,
    CausalHypothesis,
    CausalEvidenceLink,
    CausalReview,
    CausalEdge,
    CausalChain,
    CausalChainVersion,
    CausalIntervention,
    CausalOutcomeAssessment,
    CausalAuditEvent,
]


def reason_codes(reasons: list[object]) -> set[str]:
    return {str(reason["code"]) for reason in reasons if isinstance(reason, dict)}


def make_org(db: Session, slug: str) -> tuple[UUID, UUID]:
    organization = OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug, slug=slug, country_code="US", default_currency="USD", timezone="UTC"
        ),
    )
    actor = uuid4()
    return organization.id, actor


def make_method(db: Session, code: str = "det_rule") -> CausalMethodDefinition:
    return causal_ontology_service.create_method(
        db,
        CausalMethodDefinitionCreate(
            method_code=code,
            method_name="Deterministic Rule",
            method_class="deterministic_temporal_rule",
            method_version="1.0.0",
            default_confidence_weight=Decimal("0.8"),
            scope_type="shared_core",
            scope_key=f"shared_core:{code}",
        ),
    )


def make_nodes(db: Session, organization_id: UUID) -> tuple[CausalNode, CausalNode]:
    node_a = causal_node_service.get_or_create(
        db,
        organization_id,
        CausalNodeCreate(node_type="external_factor", external_description="cause"),
    )
    node_b = causal_node_service.get_or_create(
        db,
        organization_id,
        CausalNodeCreate(node_type="external_factor", external_description="effect"),
    )
    return node_a, node_b


def confirm_hypothesis(
    db: Session, organization_id: UUID, actor: UUID, edge_type: str = "causes"
) -> tuple[CausalHypothesis, CausalNode, CausalNode, CausalMethodDefinition]:
    method = make_method(db, code=f"det_rule_{uuid4().hex[:8]}")
    node_a, node_b = make_nodes(db, organization_id)
    hyp = causal_hypothesis_service.create(
        db,
        organization_id,
        CausalHypothesisCreate(
            source_node_id=node_a.id,
            target_node_id=node_b.id,
            proposed_edge_type=edge_type,
            method_id=method.id,
        ),
        actor,
    )
    causal_hypothesis_service.propose(db, organization_id, hyp.id)
    causal_evidence_service.attach(
        db,
        organization_id,
        hyp.id,
        CausalEvidenceLinkCreate(evidence_kind="rule_trace", evidence_id=uuid4(), supports=True),
    )
    hyp = causal_evaluation_service.evaluate(db, organization_id, hyp.id)
    return hyp, node_a, node_b, method


def test_exact_table_contract_mapper_configuration_and_metadata() -> None:
    configure_mappers()
    assert len(CAUSAL_TABLES) == 11
    assert {model.__tablename__ for model in CAUSAL_MODELS} == CAUSAL_TABLES
    assert CAUSAL_TABLES <= set(Base.metadata.tables)

    node_constraints = {c.name for c in Base.metadata.tables["causal_nodes"].constraints if c.name}
    assert {"uq_causal_nodes_org_id", "uq_causal_node_target"} <= node_constraints

    hyp_fks = {fk.name for fk in Base.metadata.tables["causal_hypotheses"].foreign_key_constraints}
    assert {
        "fk_causal_hypotheses_org_source_node",
        "fk_causal_hypotheses_org_target_node",
        "fk_causal_hypotheses_org_superseded_by",
        "fk_causal_hypotheses_method",
    } <= hyp_fks

    outcome_fks = {
        fk.name for fk in Base.metadata.tables["causal_outcome_assessments"].foreign_key_constraints
    }
    assert "fk_causal_outcome_assessments_org_action_outcome" in outcome_fks
    action_outcome_uniques = {
        c.name for c in Base.metadata.tables["action_outcomes"].constraints if c.name
    }
    assert "uq_action_outcomes_org_id" in action_outcome_uniques


def test_migration_is_static_revision_scoped_and_creates_exact_tables() -> None:
    source = Path(
        "migrations/versions/20260806_0032_causal_links_root_cause_intelligence.py"
    ).read_text(encoding="utf-8")
    assert 'revision: str = "20260806_0032"' in source
    assert 'down_revision: str | None = "20260804_0031"' in source
    assert "Base.metadata" not in source
    assert "from app." not in source
    assert source.count("op.create_table(") == 11
    for table_name in CAUSAL_TABLES:
        assert f'        "{table_name}",' in source


def test_hypothesis_evaluation_confirmation_and_edge_materialization(db: Session) -> None:
    organization_id, actor = make_org(db, "causal-basic")
    hyp, node_a, node_b, _method = confirm_hypothesis(db, organization_id, actor)
    assert hyp.lifecycle_status == "under_review"
    assert hyp.hard_gate_outcome == "passed"
    assert hyp.confidence_score is not None

    review = causal_review_service.review(
        db, organization_id, hyp.id, CausalReviewCreate(decision="confirm"), actor
    )
    assert review.resulting_lifecycle_status == "confirmed"

    edge = db.scalar(select(CausalEdge).where(CausalEdge.hypothesis_id == hyp.id))
    assert edge is not None
    assert edge.source_node_id == node_a.id
    assert edge.target_node_id == node_b.id
    assert edge.edge_type == "causes"


def test_association_only_edge_type_can_never_reach_confirmed(db: Session) -> None:
    organization_id, actor = make_org(db, "causal-association")
    hyp, _a, _b, _method = confirm_hypothesis(
        db, organization_id, actor, edge_type="correlates_with"
    )
    assert hyp.lifecycle_status == "probable"
    with pytest.raises(CausalIntelligenceServiceError):
        causal_review_service.review(
            db, organization_id, hyp.id, CausalReviewCreate(decision="confirm"), actor
        )


def test_association_only_edge_blocked_at_database_level_directly(db: Session) -> None:
    organization_id, actor = make_org(db, "causal-db-gate")
    method = make_method(db, "det_rule_db_gate")
    node_a, node_b = make_nodes(db, organization_id)
    bad = CausalHypothesis(
        organization_id=organization_id,
        source_node_id=node_a.id,
        target_node_id=node_b.id,
        proposed_edge_type="associated_with",
        method_id=method.id,
        lifecycle_status="confirmed",
        content_hash="direct-bad-1",
        created_by_user_id=actor,
    )
    db.add(bad)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_terminal_hypothesis_is_immutable_with_narrow_status_escape_hatch(db: Session) -> None:
    organization_id, actor = make_org(db, "causal-immutable")
    hyp, _a, _b, _method = confirm_hypothesis(db, organization_id, actor)
    causal_review_service.review(
        db, organization_id, hyp.id, CausalReviewCreate(decision="confirm"), actor
    )
    db.refresh(hyp)
    assert hyp.lifecycle_status == "confirmed"

    hyp.content_hash = "mutated-after-confirmed"
    with pytest.raises(ValueError):
        db.commit()
    db.rollback()

    db.refresh(hyp)
    hyp.lifecycle_status = "revoked"
    db.commit()
    assert hyp.lifecycle_status == "revoked"

    with pytest.raises(ValueError):
        db.delete(hyp)
        db.commit()
    db.rollback()


def test_temporal_precedence_hard_gate_blocks_causes_when_reversed(db: Session) -> None:
    organization_id, actor = make_org(db, "causal-temporal")
    entity_type = CanonicalEntityType(
        type_code="asset",
        display_name="Asset",
        scope_type="shared_core",
        scope_key="shared_core:asset",
    )
    db.add(entity_type)
    db.commit()
    entity = CanonicalEntity(
        organization_id=organization_id,
        entity_type_id=entity_type.id,
        content_fingerprint="fp-entity-1",
    )
    db.add(entity)
    db.commit()
    event_type = CanonicalEventType(
        type_code="incident",
        display_name="Incident",
        scope_type="shared_core",
        scope_key="shared_core:incident",
    )
    db.add(event_type)
    db.commit()

    later = CanonicalEvent(
        organization_id=organization_id,
        canonical_entity_id=entity.id,
        event_type_id=event_type.id,
        occurrence_start=datetime(2026, 1, 2, tzinfo=UTC),
        occurrence_precision="day",
        mapping_status="mapped",
        content_fingerprint="fp-later",
    )
    earlier = CanonicalEvent(
        organization_id=organization_id,
        canonical_entity_id=entity.id,
        event_type_id=event_type.id,
        occurrence_start=datetime(2026, 1, 1, tzinfo=UTC),
        occurrence_precision="day",
        mapping_status="mapped",
        content_fingerprint="fp-earlier",
    )
    db.add_all([later, earlier])
    db.commit()

    method = make_method(db, "det_rule_temporal")
    node_source = causal_node_service.get_or_create(
        db, organization_id, CausalNodeCreate(node_type="canonical_event", target_id=later.id)
    )
    node_target = causal_node_service.get_or_create(
        db, organization_id, CausalNodeCreate(node_type="canonical_event", target_id=earlier.id)
    )
    hyp = causal_hypothesis_service.create(
        db,
        organization_id,
        CausalHypothesisCreate(
            source_node_id=node_source.id,
            target_node_id=node_target.id,
            proposed_edge_type="causes",
            method_id=method.id,
        ),
        actor,
    )
    causal_hypothesis_service.propose(db, organization_id, hyp.id)
    causal_evidence_service.attach(
        db,
        organization_id,
        hyp.id,
        CausalEvidenceLinkCreate(
            evidence_kind="canonical_record", evidence_id=later.id, supports=True
        ),
    )
    hyp = causal_evaluation_service.evaluate(db, organization_id, hyp.id)
    assert hyp.hard_gate_outcome == "blocked"
    assert "temporal_precedence_violation" in reason_codes(hyp.hard_gate_failure_reasons)
    assert hyp.lifecycle_status == "evidence_pending"


def test_blocking_mapping_status_hard_gate(db: Session) -> None:
    organization_id, actor = make_org(db, "causal-mapping-gate")
    entity_type = CanonicalEntityType(
        type_code="asset2",
        display_name="Asset",
        scope_type="shared_core",
        scope_key="shared_core:asset2",
    )
    db.add(entity_type)
    db.commit()
    entity = CanonicalEntity(
        organization_id=organization_id,
        entity_type_id=entity_type.id,
        content_fingerprint="fp-entity-2",
    )
    db.add(entity)
    db.commit()
    event_type = CanonicalEventType(
        type_code="incident2",
        display_name="Incident",
        scope_type="shared_core",
        scope_key="shared_core:incident2",
    )
    db.add(event_type)
    db.commit()
    unresolved_event = CanonicalEvent(
        organization_id=organization_id,
        canonical_entity_id=entity.id,
        event_type_id=event_type.id,
        occurrence_start=datetime(2026, 1, 1, tzinfo=UTC),
        occurrence_precision="day",
        mapping_status="unresolved",
        content_fingerprint="fp-unresolved",
    )
    db.add(unresolved_event)
    db.commit()

    method = make_method(db, "det_rule_mapgate")
    node_a, node_b = make_nodes(db, organization_id)
    hyp = causal_hypothesis_service.create(
        db,
        organization_id,
        CausalHypothesisCreate(
            source_node_id=node_a.id,
            target_node_id=node_b.id,
            proposed_edge_type="causes",
            method_id=method.id,
        ),
        actor,
    )
    causal_hypothesis_service.propose(db, organization_id, hyp.id)
    causal_evidence_service.attach(
        db,
        organization_id,
        hyp.id,
        CausalEvidenceLinkCreate(
            evidence_kind="canonical_record", evidence_id=unresolved_event.id, supports=True
        ),
    )
    hyp = causal_evaluation_service.evaluate(db, organization_id, hyp.id)
    assert hyp.hard_gate_outcome == "blocked"
    assert "blocking_mapping_status" in reason_codes(hyp.hard_gate_failure_reasons)


def test_minimum_mapping_confidence_is_never_averaged(db: Session) -> None:
    organization_id, actor = make_org(db, "causal-min-confidence")
    entity_type = CanonicalEntityType(
        type_code="asset3",
        display_name="Asset",
        scope_type="shared_core",
        scope_key="shared_core:asset3",
    )
    db.add(entity_type)
    db.commit()
    entity = CanonicalEntity(
        organization_id=organization_id,
        entity_type_id=entity_type.id,
        content_fingerprint="fp-entity-3",
    )
    db.add(entity)
    db.commit()
    event_type = CanonicalEventType(
        type_code="incident3",
        display_name="Incident",
        scope_type="shared_core",
        scope_key="shared_core:incident3",
    )
    db.add(event_type)
    db.commit()
    high_confidence = CanonicalEvent(
        organization_id=organization_id,
        canonical_entity_id=entity.id,
        event_type_id=event_type.id,
        occurrence_start=datetime(2026, 1, 1, tzinfo=UTC),
        occurrence_precision="day",
        mapping_status="mapped",
        content_fingerprint="fp-high",
        mapping_confidence_score=Decimal("0.95"),
    )
    low_confidence = CanonicalEvent(
        organization_id=organization_id,
        canonical_entity_id=entity.id,
        event_type_id=event_type.id,
        occurrence_start=datetime(2026, 1, 1, tzinfo=UTC),
        occurrence_precision="day",
        mapping_status="mapped",
        content_fingerprint="fp-low",
        mapping_confidence_score=Decimal("0.10"),
    )
    db.add_all([high_confidence, low_confidence])
    db.commit()

    method = make_method(db, "det_rule_minconf")
    node_a, node_b = make_nodes(db, organization_id)
    hyp = causal_hypothesis_service.create(
        db,
        organization_id,
        CausalHypothesisCreate(
            source_node_id=node_a.id,
            target_node_id=node_b.id,
            proposed_edge_type="contributes_to",
            method_id=method.id,
        ),
        actor,
    )
    causal_hypothesis_service.propose(db, organization_id, hyp.id)
    causal_evidence_service.attach(
        db,
        organization_id,
        hyp.id,
        CausalEvidenceLinkCreate(
            evidence_kind="canonical_record", evidence_id=high_confidence.id, supports=True
        ),
    )
    causal_evidence_service.attach(
        db,
        organization_id,
        hyp.id,
        CausalEvidenceLinkCreate(
            evidence_kind="canonical_record", evidence_id=low_confidence.id, supports=True
        ),
    )
    hyp = causal_evaluation_service.evaluate(db, organization_id, hyp.id)
    assert hyp.minimum_supporting_mapping_confidence == Decimal("0.10")
    assert "insufficient_mapping_confidence" in reason_codes(hyp.hard_gate_failure_reasons)


def test_contradiction_count_discounts_confidence(db: Session) -> None:
    organization_id, actor = make_org(db, "causal-contradiction")
    method = make_method(db, "det_rule_contra")
    node_a, node_b = make_nodes(db, organization_id)
    hyp = causal_hypothesis_service.create(
        db,
        organization_id,
        CausalHypothesisCreate(
            source_node_id=node_a.id,
            target_node_id=node_b.id,
            proposed_edge_type="causes",
            method_id=method.id,
        ),
        actor,
    )
    causal_hypothesis_service.propose(db, organization_id, hyp.id)
    causal_evidence_service.attach(
        db,
        organization_id,
        hyp.id,
        CausalEvidenceLinkCreate(evidence_kind="rule_trace", evidence_id=uuid4(), supports=True),
    )
    causal_evidence_service.attach(
        db,
        organization_id,
        hyp.id,
        CausalEvidenceLinkCreate(evidence_kind="rule_trace", evidence_id=uuid4(), supports=False),
    )
    hyp = causal_evaluation_service.evaluate(db, organization_id, hyp.id)
    assert hyp.contradiction_count == 1
    assert hyp.confidence_score is not None
    assert hyp.confidence_score < Decimal("0.8")


def test_competing_hypotheses_on_same_node_pair(db: Session) -> None:
    organization_id, actor = make_org(db, "causal-competing")
    method = make_method(db, "det_rule_competing")
    node_a, node_b = make_nodes(db, organization_id)
    hyp1 = causal_hypothesis_service.create(
        db,
        organization_id,
        CausalHypothesisCreate(
            source_node_id=node_a.id,
            target_node_id=node_b.id,
            proposed_edge_type="causes",
            method_id=method.id,
        ),
        actor,
    )
    hyp2 = causal_hypothesis_service.create(
        db,
        organization_id,
        CausalHypothesisCreate(
            source_node_id=node_a.id,
            target_node_id=node_b.id,
            proposed_edge_type="contributes_to",
            method_id=method.id,
        ),
        actor,
    )
    assert hyp1.id != hyp2.id
    assert hyp1.proposed_edge_type != hyp2.proposed_edge_type


def test_hypothesis_create_is_idempotent_by_content_hash(db: Session) -> None:
    organization_id, actor = make_org(db, "causal-idempotent")
    method = make_method(db, "det_rule_idem")
    node_a, node_b = make_nodes(db, organization_id)
    payload = CausalHypothesisCreate(
        source_node_id=node_a.id,
        target_node_id=node_b.id,
        proposed_edge_type="causes",
        method_id=method.id,
    )
    first = causal_hypothesis_service.create(db, organization_id, payload, actor)
    second = causal_hypothesis_service.create(db, organization_id, payload, actor)
    assert first.id == second.id


def test_external_factor_nodes_are_individually_addressable(db: Session) -> None:
    organization_id, _actor = make_org(db, "causal-external-nodes")
    node1 = causal_node_service.get_or_create(
        db, organization_id, CausalNodeCreate(node_type="external_factor", external_description="a")
    )
    node2 = causal_node_service.get_or_create(
        db, organization_id, CausalNodeCreate(node_type="external_factor", external_description="b")
    )
    assert node1.id != node2.id
    assert node1.target_kind is None
    assert node1.target_id is None


def test_cross_tenant_hypothesis_reference_is_rejected(db: Session) -> None:
    org_a_id, actor = make_org(db, "causal-tenant-a")
    org_b_id, _ = make_org(db, "causal-tenant-b")
    method = make_method(db, "det_rule_tenant")
    node_a, node_b = make_nodes(db, org_a_id)
    bad = CausalHypothesis(
        organization_id=org_b_id,
        source_node_id=node_a.id,
        target_node_id=node_b.id,
        proposed_edge_type="causes",
        method_id=method.id,
        lifecycle_status="draft",
        content_hash="cross-tenant-1",
        created_by_user_id=actor,
    )
    db.add(bad)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_root_cause_ranking_scores_multiplicatively_and_tracks_weakest_link(db: Session) -> None:
    organization_id, actor = make_org(db, "causal-ranking")
    hyp, node_a, node_b, _method = confirm_hypothesis(db, organization_id, actor)
    causal_review_service.review(
        db, organization_id, hyp.id, CausalReviewCreate(decision="confirm"), actor
    )

    chain = causal_chain_service.create(db, organization_id, "chain-1", node_a.id, node_b.id)
    version = root_cause_ranking_service.compute_chain_version(db, organization_id, chain)
    assert version.version_number == 1
    assert version.path_score == hyp.confidence_score
    assert version.weakest_link_confidence == hyp.confidence_score
    assert version.occurrence_count == 1

    ranking = root_cause_ranking_service.rank_root_causes(db, organization_id)
    assert len(ranking) == 1
    assert ranking[0].chain_code == "chain-1"


def test_cycle_detection_raises_and_does_not_silently_resolve(db: Session) -> None:
    organization_id, actor = make_org(db, "causal-cycle")
    method = make_method(db, "det_rule_cycle")
    node_a, node_b = make_nodes(db, organization_id)

    def _confirmed_edge(source: CausalNode, target: CausalNode) -> None:
        hyp = causal_hypothesis_service.create(
            db,
            organization_id,
            CausalHypothesisCreate(
                source_node_id=source.id,
                target_node_id=target.id,
                proposed_edge_type="causes",
                method_id=method.id,
            ),
            actor,
        )
        causal_hypothesis_service.propose(db, organization_id, hyp.id)
        causal_evidence_service.attach(
            db,
            organization_id,
            hyp.id,
            CausalEvidenceLinkCreate(
                evidence_kind="rule_trace", evidence_id=uuid4(), supports=True
            ),
        )
        hyp = causal_evaluation_service.evaluate(db, organization_id, hyp.id)
        causal_review_service.review(
            db, organization_id, hyp.id, CausalReviewCreate(decision="confirm"), actor
        )

    _confirmed_edge(node_a, node_b)
    _confirmed_edge(node_b, node_a)

    with pytest.raises(CausalIntelligenceServiceError):
        root_cause_ranking_service.find_paths(db, organization_id, node_a.id, node_b.id)


def test_intervention_target_xor_is_enforced(db: Session) -> None:
    organization_id, actor = make_org(db, "causal-intervention-xor")
    action = ActionService().create(
        db,
        organization_id,
        ActionCreate(
            source_type="manual",
            source_reference="ref-1",
            recommendation_type="inspect",
            title="Inspect",
            description="Inspect asset",
            rationale="predicted failure",
        ),
        actor,
    )
    node_a, node_b = make_nodes(db, organization_id)
    with pytest.raises(CausalIntelligenceServiceError):
        causal_intervention_service.create(
            db,
            organization_id,
            CausalInterventionCreate(
                action_id=action.id,
                targeted_node_id=node_a.id,
                targeted_edge_id=None,
                expected_mechanism="both targets set is invalid",
            ).model_copy(update={"targeted_edge_id": node_b.id}),
            actor,
        )


def test_intervention_and_outcome_feedback_creates_hypothesis_revision(db: Session) -> None:
    organization_id, actor = make_org(db, "causal-outcome-feedback")
    hyp, node_a, node_b, _method = confirm_hypothesis(db, organization_id, actor)
    causal_review_service.review(
        db, organization_id, hyp.id, CausalReviewCreate(decision="confirm"), actor
    )
    edge = db.scalar(select(CausalEdge).where(CausalEdge.hypothesis_id == hyp.id))
    assert edge is not None

    action = ActionService().create(
        db,
        organization_id,
        ActionCreate(
            source_type="manual",
            source_reference="ref-2",
            recommendation_type="inspect",
            title="Inspect",
            description="Inspect asset",
            rationale="predicted failure",
        ),
        actor,
    )
    intervention = causal_intervention_service.create(
        db,
        organization_id,
        CausalInterventionCreate(
            action_id=action.id, targeted_edge_id=edge.id, expected_mechanism="mitigate root cause"
        ),
        actor,
    )
    outcome = ActionService().record_outcome(
        db,
        organization_id,
        action.id,
        ActionOutcomeCreate(outcome_type="expected", calculation_method="manual"),
        actor,
    )
    causal_outcome_assessment_service.create(
        db,
        organization_id,
        CausalOutcomeAssessmentCreate(
            intervention_id=intervention.id,
            action_outcome_id=outcome.id,
            hypothesis_effect="refuted",
        ),
        actor,
    )
    db.refresh(hyp)
    assert hyp.lifecycle_status == "superseded"
    assert hyp.superseded_by_hypothesis_id is not None
    revision = db.get(CausalHypothesis, hyp.superseded_by_hypothesis_id)
    assert revision is not None
    assert revision.lifecycle_status == "under_review"


def test_causal_audit_events_are_immutable(db: Session) -> None:
    organization_id, actor = make_org(db, "causal-audit")
    event = CausalAuditEvent(
        organization_id=organization_id,
        event_type="test_event",
        entity_type="causal_hypothesis",
        entity_id=uuid4(),
        actor_type="user",
        actor_user_id=actor,
        summary="test",
    )
    db.add(event)
    db.commit()
    event.summary = "mutated"
    with pytest.raises(ValueError):
        db.commit()
    db.rollback()


def test_causal_review_is_immutable_after_creation(db: Session) -> None:
    organization_id, actor = make_org(db, "causal-review-immutable")
    hyp, _a, _b, _method = confirm_hypothesis(db, organization_id, actor)
    review = causal_review_service.review(
        db, organization_id, hyp.id, CausalReviewCreate(decision="probable"), actor
    )
    review.notes = "mutated"
    with pytest.raises(ValueError):
        db.commit()
    db.rollback()
