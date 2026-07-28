from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.knowledge_graph.catalog import definition_hash, graph_id
from app.models.commercial import Entitlement, UsageEvent, UsageMeterDefinition
from app.models.entities import Finding, Organization
from app.models.gateway import ApplicationClient
from app.models.knowledge_graph import (
    KnowledgeGraphChange,
    KnowledgeGraphEdge,
    KnowledgeGraphEdgeEvidence,
    KnowledgeGraphEntityType,
    KnowledgeGraphEntityTypeVersion,
    KnowledgeGraphGovernanceEvent,
    KnowledgeGraphNode,
    KnowledgeGraphRelationshipType,
    KnowledgeGraphRelationshipTypeVersion,
    KnowledgeGraphVersion,
)
from app.schemas.knowledge_graph import (
    FindingProjectionCreate,
    GraphTraversalCreate,
    GraphTypeTransition,
)
from app.services.knowledge_graph_service import (
    KnowledgeGraphServiceError,
    graph_projection_service,
    graph_query_service,
    graph_type_catalog_service,
)


def _foundation(db: Session, *, entitled: bool = True) -> tuple[Organization, Finding]:
    actor = uuid4()
    organization = Organization(
        name=f"Graph Tenant {uuid4()}",
        slug=f"graph-{uuid4()}",
        country_code="US",
        default_currency="USD",
        timezone="UTC",
        status="active",
        is_demo=True,
    )
    db.add(organization)
    db.flush()
    now = datetime.now(UTC)
    if entitled:
        db.add(
            Entitlement(
                organization_id=organization.id,
                entitlement_type="feature",
                entitlement_key="intelligence.enterprise_knowledge_graph",
                enabled=True,
                source="contract",
                effective_at=now - timedelta(minutes=1),
                idempotency_key=f"graph:{organization.id}",
                granted_by_user_id=actor,
            )
        )
    for code in (
        "graph_nodes_materialized",
        "graph_edges_materialized",
        "graph_traversals",
    ):
        if db.scalar(select(UsageMeterDefinition).where(UsageMeterDefinition.code == code)) is None:
            db.add(
                UsageMeterDefinition(
                    code=code,
                    product="enterprise_intelligence",
                    meter_kind="counter",
                    unit="count",
                    aggregation="sum",
                    currency_behavior="not_applicable",
                )
            )
    entity_type = db.get(KnowledgeGraphEntityType, graph_id("entity_type", "finding"))
    if entity_type is None:
        entity_type = KnowledgeGraphEntityType(
            id=graph_id("entity_type", "finding"),
            code="finding",
            name="Finding",
            description="Governed finding reference.",
            lifecycle_status="active",
            owner="Enterprise Intelligence Architecture",
            security_classification="internal",
            tags=[],
            documentation_reference=("docs/phase3/wp-3.01-knowledge-graph-specification.md"),
        )
        db.add(entity_type)
        db.add(
            KnowledgeGraphEntityTypeVersion(
                id=graph_id("entity_type_version", "finding"),
                entity_type_id=entity_type.id,
                semantic_version="1.0.0",
                source_registries=["findings"],
                reference_contract={},
                property_contract={},
                validation_contract={},
                retention_policy={},
                known_limitations=[],
                definition_hash=definition_hash("entity_type", "finding"),
                approved_at=now,
            )
        )
    finding = Finding(
        organization_id=organization.id,
        rule_id="GRAPH.TEST",
        title="Governed graph test finding",
        summary="A test finding projected from the authoritative store.",
        domain="quality",
        confidence_score=0.9,
        status="published",
    )
    db.add(finding)
    db.commit()
    return organization, finding


def test_projection_is_tenant_scoped_idempotent_and_metered(db: Session) -> None:
    organization, finding = _foundation(db)
    actor = uuid4()
    payload = FindingProjectionCreate(
        idempotency_key="projection-1",
        finding_id=finding.id,
        source_event_id="finding-published-1",
    )
    first = graph_projection_service.project_finding(db, organization.id, payload, actor)
    replay = graph_projection_service.project_finding(db, organization.id, payload, actor)
    assert replay.id == first.id
    assert first.node_count == 1
    assert (
        db.scalar(
            select(func.count())
            .select_from(KnowledgeGraphChange)
            .where(KnowledgeGraphChange.organization_id == organization.id)
        )
        == 1
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(UsageEvent)
            .where(UsageEvent.organization_id == organization.id)
        )
        == 1
    )

    with pytest.raises(KnowledgeGraphServiceError, match="different projection") as conflict:
        graph_projection_service.project_finding(
            db,
            organization.id,
            FindingProjectionCreate(
                idempotency_key="projection-1",
                finding_id=finding.id,
                source_event_id="different-event",
            ),
            actor,
        )
    assert conflict.value.status == 409

    other, _ = _foundation(db)
    with pytest.raises(KnowledgeGraphServiceError, match="Finding not found"):
        graph_projection_service.project_finding(db, other.id, payload, actor)


def test_traversal_is_bounded_explainable_and_idempotent(db: Session) -> None:
    organization, finding = _foundation(db)
    actor = uuid4()
    change = graph_projection_service.project_finding(
        db,
        organization.id,
        FindingProjectionCreate(
            idempotency_key="projection-2",
            finding_id=finding.id,
            source_event_id="finding-published-2",
        ),
        actor,
    )
    node = graph_query_service.nodes(db, organization.id)[0]
    payload = GraphTraversalCreate(
        idempotency_key="traversal-1",
        start_node_id=node.id,
        graph_version_id=change.graph_version_id,
        max_depth=6,
    )
    result = graph_query_service.traverse(db, organization.id, payload, actor)
    replay = graph_query_service.traverse(db, organization.id, payload, actor)
    assert replay.run_id == result.run_id
    assert [item.id for item in result.nodes] == [node.id]
    assert result.edges == []
    explanation = graph_query_service.explanation(db, organization.id, result.run_id)
    assert explanation.steps == []
    assert "caused_by is not supported" in explanation.limitations[0]

    with pytest.raises(KnowledgeGraphServiceError) as conflict:
        graph_query_service.traverse(
            db,
            organization.id,
            payload.model_copy(update={"max_depth": 2}),
            actor,
        )
    assert conflict.value.status == 409

    with pytest.raises(ValidationError):
        GraphTraversalCreate(
            idempotency_key="too-deep",
            start_node_id=node.id,
            max_depth=7,
        )


def test_entitlement_is_required_before_projection(db: Session) -> None:
    organization, finding = _foundation(db, entitled=False)
    with pytest.raises(KnowledgeGraphServiceError) as exc:
        graph_projection_service.project_finding(
            db,
            organization.id,
            FindingProjectionCreate(
                idempotency_key="not-entitled",
                finding_id=finding.id,
                source_event_id="finding-published-3",
            ),
            uuid4(),
        )
    assert exc.value.status == 403


def test_catalog_api_exposes_governed_types(client: TestClient, db: Session) -> None:
    _foundation(db)
    db.add(
        ApplicationClient(
            client_code="intel4ops-web",
            name="Intel4Ops Web",
            client_type="first_party",
            status="active",
        )
    )
    db.commit()
    response = client.get("/api/v1/enterprise-intelligence/knowledge-graph/entity-types")
    assert response.status_code == 200, response.text
    assert [item["code"] for item in response.json()] == ["finding"]


def test_type_governance_transition_is_append_only_and_idempotent(
    db: Session,
) -> None:
    _foundation(db)
    asset_id = graph_id("entity_type", "finding")
    actor = uuid4()
    payload = GraphTypeTransition(
        asset_type="entity_type",
        target_status="suspended",
        reason="Temporarily suspend the governed type.",
        idempotency_key="type-transition-1",
    )
    transitioned = graph_type_catalog_service.transition(db, asset_id, payload, actor)
    replay = graph_type_catalog_service.transition(db, asset_id, payload, actor)
    assert transitioned.lifecycle_status == "suspended"
    assert replay.lifecycle_status == "suspended"
    assert (
        db.scalar(
            select(func.count())
            .select_from(KnowledgeGraphGovernanceEvent)
            .where(KnowledgeGraphGovernanceEvent.asset_id == asset_id)
        )
        == 1
    )


def test_projection_carries_forward_the_active_snapshot(db: Session) -> None:
    organization, first_finding = _foundation(db)
    actor = uuid4()
    first = graph_projection_service.project_finding(
        db,
        organization.id,
        FindingProjectionCreate(
            idempotency_key="snapshot-first",
            finding_id=first_finding.id,
            source_event_id="snapshot-event-first",
        ),
        actor,
    )
    second_finding = Finding(
        organization_id=organization.id,
        rule_id="GRAPH.SECOND",
        title="Second governed finding",
        summary="A second authoritative finding.",
        domain="quality",
        confidence_score=0.8,
        status="published",
    )
    db.add(second_finding)
    db.commit()
    second = graph_projection_service.project_finding(
        db,
        organization.id,
        FindingProjectionCreate(
            idempotency_key="snapshot-second",
            finding_id=second_finding.id,
            source_event_id="snapshot-event-second",
        ),
        actor,
    )
    first_version = db.get(KnowledgeGraphVersion, first.graph_version_id)
    second_version = db.get(KnowledgeGraphVersion, second.graph_version_id)
    assert first_version is not None and first_version.status == "superseded"
    assert second_version is not None and second_version.status == "active"
    assert second_version.node_count == 2
    assert (
        db.scalar(
            select(func.count())
            .select_from(KnowledgeGraphNode)
            .where(KnowledgeGraphNode.graph_version_id == second.graph_version_id)
        )
        == 2
    )


def test_tenant_reads_require_an_active_entitlement(db: Session) -> None:
    organization, _finding = _foundation(db, entitled=False)
    with pytest.raises(KnowledgeGraphServiceError) as exc:
        graph_query_service.versions(db, organization.id)
    assert exc.value.status == 403


def test_source_registry_allowlist_is_database_enforced(db: Session) -> None:
    organization, finding = _foundation(db)
    change = graph_projection_service.project_finding(
        db,
        organization.id,
        FindingProjectionCreate(
            idempotency_key="registry-foundation",
            finding_id=finding.id,
            source_event_id="registry-foundation-event",
        ),
        uuid4(),
    )
    db.add(
        KnowledgeGraphNode(
            organization_id=organization.id,
            graph_version_id=change.graph_version_id,
            entity_type_version_id=graph_id("entity_type_version", "finding"),
            source_registry="arbitrary_customer_table",
            source_object_id=uuid4(),
            source_version_key="",
            reference_fingerprint="a" * 64,
            status="active",
            metadata_json={},
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_shortest_path_requires_accessible_current_evidence(db: Session) -> None:
    organization, finding = _foundation(db)
    actor = uuid4()
    change = graph_projection_service.project_finding(
        db,
        organization.id,
        FindingProjectionCreate(
            idempotency_key="path-foundation",
            finding_id=finding.id,
            source_event_id="path-foundation-event",
        ),
        actor,
    )
    start = db.scalar(
        select(KnowledgeGraphNode).where(
            KnowledgeGraphNode.graph_version_id == change.graph_version_id
        )
    )
    assert start is not None
    relationship = KnowledgeGraphRelationshipType(
        id=graph_id("relationship_type", "correlated_with"),
        code="correlated_with",
        name="Correlated With",
        description="Explicitly non-causal correlation.",
        lifecycle_status="active",
        directed=False,
        symmetric=True,
        owner="Enterprise Intelligence Architecture",
        security_classification="internal",
        documentation_reference="docs/phase3/wp-3.01-knowledge-graph-specification.md",
    )
    db.add(relationship)
    db.add(
        KnowledgeGraphRelationshipTypeVersion(
            id=graph_id("relationship_type_version", "correlated_with"),
            relationship_type_id=relationship.id,
            semantic_version="1.0.0",
            allowed_from_entity_codes=["finding"],
            allowed_to_entity_codes=["finding"],
            evidence_contract={"minimum_references": 1},
            confidence_policy={"minimum": 0, "maximum": 1},
            temporal_policy={"point_in_time": True},
            revalidation_policy={"on_source_change": True},
            known_limitations=["Non-causal."],
            definition_hash=definition_hash("relationship_type", "correlated_with"),
            approved_at=datetime.now(UTC),
        )
    )
    target = KnowledgeGraphNode(
        organization_id=organization.id,
        graph_version_id=change.graph_version_id,
        entity_type_version_id=graph_id("entity_type_version", "finding"),
        source_registry="findings",
        source_object_id=uuid4(),
        source_version_key="",
        display_label="Target finding",
        reference_fingerprint="b" * 64,
        status="active",
        metadata_json={},
    )
    unsupported = KnowledgeGraphNode(
        organization_id=organization.id,
        graph_version_id=change.graph_version_id,
        entity_type_version_id=graph_id("entity_type_version", "finding"),
        source_registry="findings",
        source_object_id=uuid4(),
        source_version_key="",
        display_label="Unsupported finding",
        reference_fingerprint="c" * 64,
        status="active",
        metadata_json={},
    )
    db.add_all([target, unsupported])
    db.flush()
    supported_edge = KnowledgeGraphEdge(
        organization_id=organization.id,
        graph_version_id=change.graph_version_id,
        relationship_type_version_id=graph_id("relationship_type_version", "correlated_with"),
        from_node_id=start.id,
        to_node_id=target.id,
        assertion_kind="calculated",
        derivation_method="test_adapter",
        derivation_version="1.0.0",
        derivation_fingerprint="d" * 64,
        confidence_score=Decimal("0.9"),
        confidence_method="test",
        validity_key="current",
        valid_from=datetime.now(UTC) - timedelta(days=1),
        valid_to=datetime.now(UTC) + timedelta(days=1),
        status="active",
        definition_fingerprint="e" * 64,
        content_fingerprint="f" * 64,
        properties_json={},
        created_by_user_id=actor,
    )
    unsupported_edge = KnowledgeGraphEdge(
        organization_id=organization.id,
        graph_version_id=change.graph_version_id,
        relationship_type_version_id=graph_id("relationship_type_version", "correlated_with"),
        from_node_id=start.id,
        to_node_id=unsupported.id,
        assertion_kind="calculated",
        derivation_method="test_adapter",
        derivation_version="1.0.0",
        derivation_fingerprint="1" * 64,
        confidence_score=Decimal("0.9"),
        confidence_method="test",
        validity_key="unsupported",
        status="active",
        definition_fingerprint="2" * 64,
        content_fingerprint="3" * 64,
        properties_json={},
        created_by_user_id=actor,
    )
    db.add_all([supported_edge, unsupported_edge])
    db.flush()
    db.add(
        KnowledgeGraphEdgeEvidence(
            organization_id=organization.id,
            graph_version_id=change.graph_version_id,
            edge_id=supported_edge.id,
            source_type="finding_evidence_bundle",
            source_identifier="bundle:test",
            integrity_fingerprint="4" * 64,
            relevance="supporting",
            observed_at=datetime.now(UTC),
            metadata_json={},
        )
    )
    db.commit()
    result = graph_query_service.traverse(
        db,
        organization.id,
        GraphTraversalCreate(
            idempotency_key="shortest-path",
            start_node_id=start.id,
            target_node_id=target.id,
            graph_version_id=change.graph_version_id,
            operation="shortest_governed_path",
        ),
        actor,
    )
    assert result.paths == [[start.id, target.id]]
    assert [edge.id for edge in result.edges] == [supported_edge.id]
    assert unsupported.id not in {node.id for node in result.nodes}
