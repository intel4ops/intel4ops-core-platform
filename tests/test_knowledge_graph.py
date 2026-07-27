from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.knowledge_graph.catalog import definition_hash, graph_id
from app.models.commercial import Entitlement, UsageEvent, UsageMeterDefinition
from app.models.entities import Finding, Organization
from app.models.gateway import ApplicationClient
from app.models.knowledge_graph import (
    KnowledgeGraphChange,
    KnowledgeGraphEntityType,
    KnowledgeGraphEntityTypeVersion,
    KnowledgeGraphGovernanceEvent,
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
