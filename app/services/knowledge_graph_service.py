from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from time import monotonic
from typing import cast
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.knowledge_graph.catalog import (
    RELATIONSHIP_TYPE_CODES,
    graph_id,
)
from app.models.commercial import Entitlement, UsageEvent
from app.models.entities import Finding
from app.models.knowledge_graph import (
    KnowledgeGraphChange,
    KnowledgeGraphEdge,
    KnowledgeGraphEdgeEvidence,
    KnowledgeGraphEntityType,
    KnowledgeGraphEntityTypeVersion,
    KnowledgeGraphGovernanceEvent,
    KnowledgeGraphNode,
    KnowledgeGraphProjectionCheckpoint,
    KnowledgeGraphQueryRun,
    KnowledgeGraphQueryStep,
    KnowledgeGraphRelationshipType,
    KnowledgeGraphRelationshipTypeVersion,
    KnowledgeGraphVersion,
)
from app.models.signatures import OperationalSignatureExecution
from app.schemas.knowledge_graph import (
    FindingProjectionCreate,
    GraphExplanationRead,
    GraphHealthRead,
    GraphTraversalCreate,
    GraphTraversalRead,
    GraphTypeTransition,
)

FEATURE_KEY = "intelligence.enterprise_knowledge_graph"


class KnowledgeGraphServiceError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def _fingerprint(value: object) -> str:
    return sha256(
        json.dumps(value, default=str, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _require_entitlement(db: Session, organization_id: UUID) -> None:
    now = datetime.now(UTC)
    entitlement = db.scalar(
        select(Entitlement)
        .where(
            Entitlement.organization_id == organization_id,
            Entitlement.entitlement_key == FEATURE_KEY,
            Entitlement.enabled.is_(True),
            Entitlement.effective_at <= now,
            or_(Entitlement.expires_at.is_(None), Entitlement.expires_at > now),
        )
        .order_by(Entitlement.effective_at.desc())
    )
    if entitlement is None:
        raise KnowledgeGraphServiceError(
            "KNOWLEDGE_GRAPH_NOT_ENTITLED",
            "Enterprise Knowledge Graph entitlement is required",
            403,
        )


class GraphTypeCatalogService:
    def entity_types(self, db: Session) -> list[KnowledgeGraphEntityType]:
        return list(
            db.scalars(select(KnowledgeGraphEntityType).order_by(KnowledgeGraphEntityType.code))
        )

    def relationship_types(self, db: Session) -> list[KnowledgeGraphRelationshipType]:
        return list(
            db.scalars(
                select(KnowledgeGraphRelationshipType).order_by(KnowledgeGraphRelationshipType.code)
            )
        )

    def entity_type_versions(
        self, db: Session, entity_type_id: UUID
    ) -> list[KnowledgeGraphEntityTypeVersion]:
        return list(
            db.scalars(
                select(KnowledgeGraphEntityTypeVersion)
                .where(KnowledgeGraphEntityTypeVersion.entity_type_id == entity_type_id)
                .order_by(KnowledgeGraphEntityTypeVersion.semantic_version)
            )
        )

    def relationship_type_versions(
        self, db: Session, relationship_type_id: UUID
    ) -> list[KnowledgeGraphRelationshipTypeVersion]:
        return list(
            db.scalars(
                select(KnowledgeGraphRelationshipTypeVersion)
                .where(
                    KnowledgeGraphRelationshipTypeVersion.relationship_type_id
                    == relationship_type_id
                )
                .order_by(KnowledgeGraphRelationshipTypeVersion.semantic_version)
            )
        )

    def transition(
        self,
        db: Session,
        asset_id: UUID,
        payload: GraphTypeTransition,
        actor_user_id: UUID,
    ) -> KnowledgeGraphEntityType | KnowledgeGraphRelationshipType:
        model = (
            KnowledgeGraphEntityType
            if payload.asset_type == "entity_type"
            else KnowledgeGraphRelationshipType
        )
        asset = cast(
            KnowledgeGraphEntityType | KnowledgeGraphRelationshipType,
            db.get(model, asset_id),
        )
        if asset is None:
            raise KnowledgeGraphServiceError(
                "GRAPH_TYPE_NOT_FOUND", "Knowledge Graph type not found", 404
            )
        prior = db.scalar(
            select(KnowledgeGraphGovernanceEvent).where(
                KnowledgeGraphGovernanceEvent.asset_type == payload.asset_type,
                KnowledgeGraphGovernanceEvent.asset_id == asset_id,
                KnowledgeGraphGovernanceEvent.idempotency_key == payload.idempotency_key,
            )
        )
        if prior is not None:
            if prior.new_status != payload.target_status:
                raise KnowledgeGraphServiceError(
                    "IDEMPOTENCY_CONFLICT",
                    "Idempotency key was already used for another transition",
                    409,
                )
            return asset
        transitions = {
            "draft": {"under_review"},
            "under_review": {"draft", "approved"},
            "approved": {"active"},
            "active": {"suspended", "deprecated"},
            "suspended": {"active", "retired"},
            "deprecated": {"retired"},
            "retired": set(),
        }
        if payload.target_status not in transitions[asset.lifecycle_status]:
            raise KnowledgeGraphServiceError(
                "INVALID_GRAPH_TYPE_TRANSITION",
                f"Cannot transition from {asset.lifecycle_status} to {payload.target_status}",
                409,
            )
        prior_status = asset.lifecycle_status
        asset.lifecycle_status = payload.target_status
        asset.updated_at = datetime.now(UTC)
        db.add(
            KnowledgeGraphGovernanceEvent(
                asset_type=payload.asset_type,
                asset_id=asset.id,
                prior_status=prior_status,
                new_status=payload.target_status,
                actor_user_id=actor_user_id,
                actor_role="platform_admin",
                reason=payload.reason,
                idempotency_key=payload.idempotency_key,
            )
        )
        db.commit()
        db.refresh(asset)
        return asset


class GraphProjectionService:
    adapter_code = "finding_evidence"
    adapter_version = "1.0.0"

    @staticmethod
    def _clone_active_snapshot(
        db: Session,
        previous: KnowledgeGraphVersion | None,
        target: KnowledgeGraphVersion,
    ) -> tuple[int, int]:
        if previous is None:
            return 0, 0
        source_nodes = list(
            db.scalars(
                select(KnowledgeGraphNode).where(
                    KnowledgeGraphNode.organization_id == previous.organization_id,
                    KnowledgeGraphNode.graph_version_id == previous.id,
                )
            )
        )
        node_mapping: dict[UUID, UUID] = {}
        for source_node in source_nodes:
            node_clone = KnowledgeGraphNode(
                organization_id=target.organization_id,
                graph_version_id=target.id,
                entity_type_version_id=source_node.entity_type_version_id,
                source_registry=source_node.source_registry,
                source_object_id=source_node.source_object_id,
                source_version_id=source_node.source_version_id,
                source_version_key=source_node.source_version_key,
                stable_code=source_node.stable_code,
                display_label=source_node.display_label,
                reference_fingerprint=source_node.reference_fingerprint,
                valid_from=source_node.valid_from,
                valid_to=source_node.valid_to,
                status=source_node.status,
                metadata_json=source_node.metadata_json,
            )
            db.add(node_clone)
            db.flush()
            node_mapping[source_node.id] = node_clone.id
        source_edges = list(
            db.scalars(
                select(KnowledgeGraphEdge).where(
                    KnowledgeGraphEdge.organization_id == previous.organization_id,
                    KnowledgeGraphEdge.graph_version_id == previous.id,
                )
            )
        )
        edge_mapping: dict[UUID, UUID] = {}
        for source_edge in source_edges:
            edge_clone = KnowledgeGraphEdge(
                organization_id=target.organization_id,
                graph_version_id=target.id,
                relationship_type_version_id=source_edge.relationship_type_version_id,
                from_node_id=node_mapping[source_edge.from_node_id],
                to_node_id=node_mapping[source_edge.to_node_id],
                assertion_kind=source_edge.assertion_kind,
                derivation_method=source_edge.derivation_method,
                derivation_version=source_edge.derivation_version,
                derivation_fingerprint=source_edge.derivation_fingerprint,
                confidence_score=source_edge.confidence_score,
                confidence_method=source_edge.confidence_method,
                valid_from=source_edge.valid_from,
                valid_to=source_edge.valid_to,
                validity_key=source_edge.validity_key,
                observed_at=source_edge.observed_at,
                status=source_edge.status,
                definition_fingerprint=source_edge.definition_fingerprint,
                content_fingerprint=source_edge.content_fingerprint,
                properties_json=source_edge.properties_json,
                created_by_user_id=source_edge.created_by_user_id,
            )
            db.add(edge_clone)
            db.flush()
            edge_mapping[source_edge.id] = edge_clone.id
        evidence_rows = list(
            db.scalars(
                select(KnowledgeGraphEdgeEvidence).where(
                    KnowledgeGraphEdgeEvidence.organization_id == previous.organization_id,
                    KnowledgeGraphEdgeEvidence.graph_version_id == previous.id,
                )
            )
        )
        for source_evidence in evidence_rows:
            db.add(
                KnowledgeGraphEdgeEvidence(
                    organization_id=target.organization_id,
                    graph_version_id=target.id,
                    edge_id=edge_mapping[source_evidence.edge_id],
                    source_type=source_evidence.source_type,
                    source_identifier=source_evidence.source_identifier,
                    source_object_id=source_evidence.source_object_id,
                    lineage_node_id=source_evidence.lineage_node_id,
                    integrity_fingerprint=source_evidence.integrity_fingerprint,
                    relevance=source_evidence.relevance,
                    observed_at=source_evidence.observed_at,
                    retention_until=source_evidence.retention_until,
                    metadata_json=source_evidence.metadata_json,
                )
            )
        return len(source_nodes), len(source_edges)

    def project_finding(
        self,
        db: Session,
        organization_id: UUID,
        payload: FindingProjectionCreate,
        actor_user_id: UUID,
    ) -> KnowledgeGraphChange:
        _require_entitlement(db, organization_id)
        finding = db.scalar(
            select(Finding).where(
                Finding.id == payload.finding_id,
                Finding.organization_id == organization_id,
            )
        )
        if finding is None:
            raise KnowledgeGraphServiceError("FINDING_NOT_FOUND", "Finding not found", 404)
        source_fingerprint = _fingerprint(
            {
                "finding_id": finding.id,
                "status": finding.status,
                "signature_execution_id": finding.signature_execution_id,
                "last_detected_at": finding.last_detected_at,
            }
        )
        prior = db.scalar(
            select(KnowledgeGraphChange).where(
                KnowledgeGraphChange.organization_id == organization_id,
                KnowledgeGraphChange.idempotency_key == payload.idempotency_key,
            )
        )
        if prior is not None:
            if (
                prior.source_event_id != payload.source_event_id
                or prior.source_fingerprint != source_fingerprint
            ):
                raise KnowledgeGraphServiceError(
                    "IDEMPOTENCY_CONFLICT",
                    "Idempotency key was already used for a different projection",
                    409,
                )
            return cast(KnowledgeGraphChange, prior)
        source_prior = db.scalar(
            select(KnowledgeGraphChange).where(
                KnowledgeGraphChange.organization_id == organization_id,
                KnowledgeGraphChange.adapter_code == self.adapter_code,
                KnowledgeGraphChange.source_event_id == payload.source_event_id,
            )
        )
        if source_prior is not None:
            if source_prior.source_fingerprint != source_fingerprint:
                raise KnowledgeGraphServiceError(
                    "SOURCE_EVENT_CONFLICT",
                    "Source event was already projected with different content",
                    409,
                )
            return cast(KnowledgeGraphChange, source_prior)

        previous_active = db.scalar(
            select(KnowledgeGraphVersion).where(
                KnowledgeGraphVersion.organization_id == organization_id,
                KnowledgeGraphVersion.status == "active",
            )
        )
        version_number = (
            db.scalar(
                select(func.max(KnowledgeGraphVersion.version)).where(
                    KnowledgeGraphVersion.organization_id == organization_id
                )
            )
            or 0
        ) + 1
        graph_version = KnowledgeGraphVersion(
            organization_id=organization_id,
            version=version_number,
            status="building",
            definition_fingerprint=_fingerprint({"entity": "1.0.0", "relationship": "1.0.0"}),
            created_by_user_id=actor_user_id,
        )
        db.add(graph_version)
        db.flush()
        node_count, edge_count = self._clone_active_snapshot(db, previous_active, graph_version)
        finding_node = db.scalar(
            select(KnowledgeGraphNode).where(
                KnowledgeGraphNode.organization_id == organization_id,
                KnowledgeGraphNode.graph_version_id == graph_version.id,
                KnowledgeGraphNode.source_registry == "findings",
                KnowledgeGraphNode.source_object_id == finding.id,
            )
        )
        if finding_node is None:
            finding_node = KnowledgeGraphNode(
                organization_id=organization_id,
                graph_version_id=graph_version.id,
                entity_type_version_id=graph_id("entity_type_version", "finding"),
                source_registry="findings",
                source_object_id=finding.id,
                source_version_id=None,
                source_version_key="",
                stable_code=finding.finding_code,
                display_label=finding.title,
                reference_fingerprint=source_fingerprint,
                status="active",
                metadata_json={"domain": finding.domain, "severity": finding.severity},
            )
            db.add(finding_node)
            db.flush()
            node_count += 1
        else:
            finding_node.stable_code = finding.finding_code
            finding_node.display_label = finding.title
            finding_node.reference_fingerprint = source_fingerprint
            finding_node.metadata_json = {
                "domain": finding.domain,
                "severity": finding.severity,
            }

        if finding.signature_execution_id is not None:
            execution = db.scalar(
                select(OperationalSignatureExecution).where(
                    OperationalSignatureExecution.id == finding.signature_execution_id,
                    OperationalSignatureExecution.organization_id == organization_id,
                )
            )
            if execution is None:
                raise KnowledgeGraphServiceError(
                    "INVALID_SOURCE_REFERENCE",
                    "Finding signature execution does not belong to the organization",
                    409,
                )
            execution_node = db.scalar(
                select(KnowledgeGraphNode).where(
                    KnowledgeGraphNode.organization_id == organization_id,
                    KnowledgeGraphNode.graph_version_id == graph_version.id,
                    KnowledgeGraphNode.source_registry == "operational_signature_executions",
                    KnowledgeGraphNode.source_object_id == execution.id,
                )
            )
            if execution_node is None:
                execution_node = KnowledgeGraphNode(
                    organization_id=organization_id,
                    graph_version_id=graph_version.id,
                    entity_type_version_id=graph_id("entity_type_version", "signature_execution"),
                    source_registry="operational_signature_executions",
                    source_object_id=execution.id,
                    source_version_id=execution.signature_version_id,
                    source_version_key=str(execution.signature_version_id),
                    stable_code=None,
                    display_label="Operational signature execution",
                    reference_fingerprint=_fingerprint(
                        {"execution_id": execution.id, "status": execution.status}
                    ),
                    status="active",
                    metadata_json={},
                )
                db.add(execution_node)
                db.flush()
                node_count += 1
            edge = db.scalar(
                select(KnowledgeGraphEdge).where(
                    KnowledgeGraphEdge.organization_id == organization_id,
                    KnowledgeGraphEdge.graph_version_id == graph_version.id,
                    KnowledgeGraphEdge.relationship_type_version_id
                    == graph_id("relationship_type_version", "produced_finding"),
                    KnowledgeGraphEdge.from_node_id == execution_node.id,
                    KnowledgeGraphEdge.to_node_id == finding_node.id,
                )
            )
            if edge is None:
                edge = KnowledgeGraphEdge(
                    organization_id=organization_id,
                    graph_version_id=graph_version.id,
                    relationship_type_version_id=graph_id(
                        "relationship_type_version", "produced_finding"
                    ),
                    from_node_id=execution_node.id,
                    to_node_id=finding_node.id,
                    assertion_kind="observed",
                    derivation_method=self.adapter_code,
                    derivation_version=self.adapter_version,
                    derivation_fingerprint=source_fingerprint,
                    confidence_score=Decimal(finding.confidence_score),
                    confidence_method=finding.confidence_method_code or "source_finding",
                    validity_key="",
                    observed_at=finding.last_detected_at,
                    status="active",
                    definition_fingerprint=source_fingerprint,
                    content_fingerprint=_fingerprint(
                        {"from": execution_node.id, "to": finding_node.id}
                    ),
                    properties_json={},
                    created_by_user_id=actor_user_id,
                )
                db.add(edge)
                db.flush()
                db.add(
                    KnowledgeGraphEdgeEvidence(
                        organization_id=organization_id,
                        graph_version_id=graph_version.id,
                        edge_id=edge.id,
                        source_type="signature_execution",
                        source_identifier=str(execution.id),
                        source_object_id=execution.id,
                        integrity_fingerprint=execution.input_fingerprint,
                        observed_at=execution.completed_at or execution.started_at,
                        retention_until=datetime.now(UTC) + timedelta(days=2555),
                        metadata_json={"finding_id": str(finding.id)},
                    )
                )
                edge_count += 1

        graph_version.node_count = node_count
        graph_version.edge_count = edge_count
        graph_version.validation_summary = {
            "tenant_references": "passed",
            "evidence_complete": (edge_count == 0 or finding.signature_execution_id is not None),
        }
        graph_version.status = "active"
        graph_version.published_at = datetime.now(UTC)
        if previous_active is not None:
            previous_active.status = "superseded"
        change = KnowledgeGraphChange(
            organization_id=organization_id,
            graph_version_id=graph_version.id,
            adapter_code=self.adapter_code,
            adapter_version=self.adapter_version,
            source_event_id=payload.source_event_id,
            source_fingerprint=source_fingerprint,
            idempotency_key=payload.idempotency_key,
            status="completed",
            node_count=node_count,
            edge_count=edge_count,
            result_json={"finding_node_id": str(finding_node.id)},
        )
        db.add(change)
        checkpoint = db.scalar(
            select(KnowledgeGraphProjectionCheckpoint).where(
                KnowledgeGraphProjectionCheckpoint.organization_id == organization_id,
                KnowledgeGraphProjectionCheckpoint.adapter_code == self.adapter_code,
            )
        )
        if checkpoint is None:
            checkpoint = KnowledgeGraphProjectionCheckpoint(
                organization_id=organization_id,
                adapter_code=self.adapter_code,
                adapter_version=self.adapter_version,
                source_cursor=payload.source_event_id,
                source_fingerprint=source_fingerprint,
                graph_version_id=graph_version.id,
                status="current",
            )
            db.add(checkpoint)
        else:
            checkpoint.source_cursor = payload.source_event_id
            checkpoint.source_fingerprint = source_fingerprint
            checkpoint.graph_version_id = graph_version.id
            checkpoint.updated_at = datetime.now(UTC)
        self._meter(db, organization_id, "graph_nodes_materialized", node_count, change.id)
        self._meter(db, organization_id, "graph_edges_materialized", edge_count, change.id)
        db.commit()
        db.refresh(change)
        return change

    @staticmethod
    def _meter(
        db: Session, organization_id: UUID, code: str, quantity: int, source_id: UUID
    ) -> None:
        if quantity == 0:
            return
        db.add(
            UsageEvent(
                organization_id=organization_id,
                meter_code=code,
                idempotency_key=f"knowledge-graph:{source_id}:{code}",
                quantity=Decimal(quantity),
                source_type="knowledge_graph_projection",
                source_id=str(source_id),
                occurred_at=datetime.now(UTC),
                metadata_json={},
            )
        )


class GraphQueryService:
    def versions(self, db: Session, organization_id: UUID) -> list[KnowledgeGraphVersion]:
        _require_entitlement(db, organization_id)
        return list(
            db.scalars(
                select(KnowledgeGraphVersion)
                .where(KnowledgeGraphVersion.organization_id == organization_id)
                .order_by(KnowledgeGraphVersion.version.desc())
            )
        )

    def nodes(self, db: Session, organization_id: UUID) -> list[KnowledgeGraphNode]:
        _require_entitlement(db, organization_id)
        return list(
            db.scalars(
                select(KnowledgeGraphNode)
                .join(
                    KnowledgeGraphVersion,
                    KnowledgeGraphVersion.id == KnowledgeGraphNode.graph_version_id,
                )
                .where(KnowledgeGraphNode.organization_id == organization_id)
                .where(KnowledgeGraphVersion.status == "active")
                .order_by(KnowledgeGraphNode.created_at.desc())
            )
        )

    def node(self, db: Session, organization_id: UUID, node_id: UUID) -> KnowledgeGraphNode:
        _require_entitlement(db, organization_id)
        node = db.scalar(
            select(KnowledgeGraphNode).where(
                KnowledgeGraphNode.organization_id == organization_id,
                KnowledgeGraphNode.id == node_id,
            )
        )
        if node is None:
            raise KnowledgeGraphServiceError("GRAPH_NODE_NOT_FOUND", "Graph node not found", 404)
        return cast(KnowledgeGraphNode, node)

    def traverse(
        self,
        db: Session,
        organization_id: UUID,
        payload: GraphTraversalCreate,
        actor_user_id: UUID,
    ) -> GraphTraversalRead:
        _require_entitlement(db, organization_id)
        fingerprint = _fingerprint(payload.model_dump(mode="json"))
        prior = db.scalar(
            select(KnowledgeGraphQueryRun).where(
                KnowledgeGraphQueryRun.organization_id == organization_id,
                KnowledgeGraphQueryRun.idempotency_key == payload.idempotency_key,
            )
        )
        if prior is not None:
            if prior.request_fingerprint != fingerprint:
                raise KnowledgeGraphServiceError(
                    "IDEMPOTENCY_CONFLICT",
                    "Idempotency key was already used for a different traversal",
                    409,
                )
            return self._response(db, prior)
        start = self.node(db, organization_id, payload.start_node_id)
        if (
            payload.graph_version_id is not None
            and payload.graph_version_id != start.graph_version_id
        ):
            raise KnowledgeGraphServiceError(
                "GRAPH_VERSION_MISMATCH", "Start node is not in the requested graph version", 409
            )
        target: KnowledgeGraphNode | None = None
        if payload.target_node_id is not None:
            target = self.node(db, organization_id, payload.target_node_id)
            if target.graph_version_id != start.graph_version_id:
                raise KnowledgeGraphServiceError(
                    "GRAPH_VERSION_MISMATCH",
                    "Target node is not in the requested graph version",
                    409,
                )
        unknown = set(payload.relationship_codes) - set(RELATIONSHIP_TYPE_CODES)
        if unknown:
            raise KnowledgeGraphServiceError(
                "INVALID_RELATIONSHIP_TYPE", "Relationship allowlist contains an unknown type"
            )
        run = KnowledgeGraphQueryRun(
            organization_id=organization_id,
            graph_version_id=start.graph_version_id,
            idempotency_key=payload.idempotency_key,
            request_fingerprint=fingerprint,
            operation=payload.operation,
            request_json=payload.model_dump(mode="json"),
            status="running",
            max_depth=payload.max_depth,
            max_nodes=payload.max_nodes,
            max_edges=payload.max_edges,
            max_paths=payload.max_paths,
            timeout_ms=payload.timeout_ms,
            requested_by_user_id=actor_user_id,
            retain_until=datetime.now(UTC) + timedelta(days=90),
        )
        db.add(run)
        db.flush()
        started = monotonic()
        visited = {start.id}
        frontier = {start.id}
        predecessor: dict[UUID, tuple[UUID, UUID]] = {}
        edges: list[KnowledgeGraphEdge] = []
        sequence = 0
        truncated = False
        effective_direction = {
            "upstream_evidence": "inbound",
            "downstream_impact": "outbound",
            "intervention_to_outcome": "outbound",
            "value_trace": "outbound",
        }.get(payload.operation, payload.direction)
        point_in_time = payload.point_in_time or datetime.now(UTC)
        for depth in range(1, payload.max_depth + 1):
            if not frontier or (monotonic() - started) * 1000 >= payload.timeout_ms:
                truncated = bool(frontier)
                break
            conditions = []
            if effective_direction in {"outbound", "both"}:
                conditions.append(KnowledgeGraphEdge.from_node_id.in_(frontier))
            if effective_direction in {"inbound", "both"}:
                conditions.append(KnowledgeGraphEdge.to_node_id.in_(frontier))
            evidence_exists = (
                select(KnowledgeGraphEdgeEvidence.id)
                .where(
                    KnowledgeGraphEdgeEvidence.organization_id == organization_id,
                    KnowledgeGraphEdgeEvidence.graph_version_id == start.graph_version_id,
                    KnowledgeGraphEdgeEvidence.edge_id == KnowledgeGraphEdge.id,
                )
                .exists()
            )
            statement = select(KnowledgeGraphEdge).where(
                KnowledgeGraphEdge.organization_id == organization_id,
                KnowledgeGraphEdge.graph_version_id == start.graph_version_id,
                KnowledgeGraphEdge.status == "active",
                KnowledgeGraphEdge.confidence_score >= Decimal(str(payload.minimum_confidence)),
                or_(
                    KnowledgeGraphEdge.valid_from.is_(None),
                    KnowledgeGraphEdge.valid_from <= point_in_time,
                ),
                or_(
                    KnowledgeGraphEdge.valid_to.is_(None),
                    KnowledgeGraphEdge.valid_to > point_in_time,
                ),
                evidence_exists,
                or_(*conditions),
            )
            if payload.relationship_codes:
                statement = statement.where(
                    KnowledgeGraphEdge.relationship_type_version_id.in_(
                        [
                            graph_id("relationship_type_version", code)
                            for code in payload.relationship_codes
                        ]
                    )
                )
            remaining_edge_budget = payload.max_edges - len(edges)
            level_edges = list(
                db.scalars(
                    statement.order_by(KnowledgeGraphEdge.id).limit(remaining_edge_budget + 1)
                )
            )
            if len(level_edges) > remaining_edge_budget:
                level_edges = level_edges[:remaining_edge_budget]
                truncated = True
            next_frontier: set[UUID] = set()
            for edge in level_edges:
                if len(edges) >= payload.max_edges or len(visited) >= payload.max_nodes:
                    truncated = True
                    break
                other = edge.to_node_id if edge.from_node_id in frontier else edge.from_node_id
                edges.append(edge)
                if other not in visited:
                    visited.add(other)
                    next_frontier.add(other)
                    predecessor[other] = (
                        edge.from_node_id if other == edge.to_node_id else edge.to_node_id,
                        edge.id,
                    )
                sequence += 1
                evidence = list(
                    db.scalars(
                        select(KnowledgeGraphEdgeEvidence).where(
                            KnowledgeGraphEdgeEvidence.organization_id == organization_id,
                            KnowledgeGraphEdgeEvidence.edge_id == edge.id,
                        )
                    )
                )
                db.add(
                    KnowledgeGraphQueryStep(
                        organization_id=organization_id,
                        query_run_id=run.id,
                        sequence=sequence,
                        depth=depth,
                        from_node_id=edge.from_node_id,
                        edge_id=edge.id,
                        to_node_id=edge.to_node_id,
                        explanation_json={
                            "derivation_method": edge.derivation_method,
                            "confidence": str(edge.confidence_score),
                        },
                        evidence_references=[
                            {"type": item.source_type, "id": item.source_identifier}
                            for item in evidence
                        ],
                    )
                )
            frontier = next_frontier
            if target is not None and target.id in visited:
                break
            if truncated:
                break
        paths: list[list[UUID]] = []
        if target is not None and target.id in visited:
            path = [target.id]
            cursor = target.id
            while cursor != start.id:
                cursor = predecessor[cursor][0]
                path.append(cursor)
            paths.append(list(reversed(path)))
        run.returned_nodes = len(visited)
        run.returned_edges = len(edges)
        run.returned_paths = len(paths)
        run.truncated = truncated
        run.status = "completed"
        run.completed_at = datetime.now(UTC)
        run.result_summary = {
            "node_ids": [str(item) for item in sorted(visited, key=str)],
            "edge_ids": [str(item.id) for item in edges],
            "paths": [[str(node_id) for node_id in path] for path in paths],
            "warnings": ["Result was truncated by the approved budget"] if truncated else [],
        }
        GraphProjectionService._meter(db, organization_id, "graph_traversals", 1, run.id)
        db.commit()
        return self._response(db, run)

    def _response(self, db: Session, run: KnowledgeGraphQueryRun) -> GraphTraversalRead:
        raw_node_ids = cast(list[str], run.result_summary.get("node_ids", []))
        raw_edge_ids = cast(list[str], run.result_summary.get("edge_ids", []))
        raw_paths = cast(list[list[str]], run.result_summary.get("paths", []))
        node_ids = [UUID(item) for item in raw_node_ids]
        edge_ids = [UUID(item) for item in raw_edge_ids]
        nodes = list(
            db.scalars(
                select(KnowledgeGraphNode).where(
                    KnowledgeGraphNode.organization_id == run.organization_id,
                    KnowledgeGraphNode.id.in_(node_ids),
                )
            )
        )
        edges = list(
            db.scalars(
                select(KnowledgeGraphEdge).where(
                    KnowledgeGraphEdge.organization_id == run.organization_id,
                    KnowledgeGraphEdge.id.in_(edge_ids),
                )
            )
        )
        return GraphTraversalRead(
            run_id=run.id,
            graph_version_id=run.graph_version_id,
            nodes=nodes,
            edges=edges,
            paths=[[UUID(node_id) for node_id in path] for path in raw_paths],
            truncated=run.truncated,
            warnings=cast(list[str], run.result_summary.get("warnings", [])),
        )

    def run(self, db: Session, organization_id: UUID, run_id: UUID) -> GraphTraversalRead:
        _require_entitlement(db, organization_id)
        run = db.scalar(
            select(KnowledgeGraphQueryRun).where(
                KnowledgeGraphQueryRun.organization_id == organization_id,
                KnowledgeGraphQueryRun.id == run_id,
            )
        )
        if run is None:
            raise KnowledgeGraphServiceError("GRAPH_QUERY_NOT_FOUND", "Traversal not found", 404)
        return self._response(db, run)

    def explanation(self, db: Session, organization_id: UUID, run_id: UUID) -> GraphExplanationRead:
        _require_entitlement(db, organization_id)
        run = db.scalar(
            select(KnowledgeGraphQueryRun).where(
                KnowledgeGraphQueryRun.organization_id == organization_id,
                KnowledgeGraphQueryRun.id == run_id,
            )
        )
        if run is None:
            raise KnowledgeGraphServiceError("GRAPH_QUERY_NOT_FOUND", "Traversal not found", 404)
        steps = list(
            db.scalars(
                select(KnowledgeGraphQueryStep)
                .where(
                    KnowledgeGraphQueryStep.organization_id == organization_id,
                    KnowledgeGraphQueryStep.query_run_id == run_id,
                )
                .order_by(KnowledgeGraphQueryStep.sequence)
            )
        )
        return GraphExplanationRead(
            run_id=run.id,
            graph_version_id=run.graph_version_id,
            steps=[
                {
                    "sequence": step.sequence,
                    "depth": step.depth,
                    "edge_id": str(step.edge_id),
                    "explanation": step.explanation_json,
                    "evidence": step.evidence_references,
                }
                for step in steps
            ],
            limitations=["Causal inference is excluded; caused_by is not supported."],
        )

    def health(self, db: Session, organization_id: UUID) -> GraphHealthRead:
        _require_entitlement(db, organization_id)
        graph = db.scalar(
            select(KnowledgeGraphVersion)
            .where(
                KnowledgeGraphVersion.organization_id == organization_id,
                KnowledgeGraphVersion.status == "active",
            )
            .order_by(KnowledgeGraphVersion.version.desc())
        )
        if graph is None:
            return GraphHealthRead(
                graph_version_id=None,
                status="not_materialized",
                node_count=0,
                edge_count=0,
                orphan_count=0,
            )
        connected = (
            select(KnowledgeGraphEdge.from_node_id)
            .where(
                KnowledgeGraphEdge.organization_id == organization_id,
                KnowledgeGraphEdge.graph_version_id == graph.id,
            )
            .union(
                select(KnowledgeGraphEdge.to_node_id).where(
                    KnowledgeGraphEdge.organization_id == organization_id,
                    KnowledgeGraphEdge.graph_version_id == graph.id,
                )
            )
        )
        orphan_count = (
            db.scalar(
                select(func.count())
                .select_from(KnowledgeGraphNode)
                .where(
                    KnowledgeGraphNode.organization_id == organization_id,
                    KnowledgeGraphNode.graph_version_id == graph.id,
                    KnowledgeGraphNode.id.not_in(connected),
                )
            )
            or 0
        )
        return GraphHealthRead(
            graph_version_id=graph.id,
            status=graph.status,
            node_count=graph.node_count,
            edge_count=graph.edge_count,
            orphan_count=orphan_count,
        )


graph_type_catalog_service = GraphTypeCatalogService()
graph_projection_service = GraphProjectionService()
graph_query_service = GraphQueryService()
