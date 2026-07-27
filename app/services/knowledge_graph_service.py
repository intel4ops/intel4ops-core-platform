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
        node_count = 1
        edge_count = 0

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
                    source_type="finding",
                    source_identifier=str(finding.id),
                    source_object_id=finding.id,
                    integrity_fingerprint=source_fingerprint,
                    observed_at=finding.last_detected_at,
                    retention_until=datetime.now(UTC) + timedelta(days=2555),
                    metadata_json={},
                )
            )
            node_count = 2
            edge_count = 1

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
        return list(
            db.scalars(
                select(KnowledgeGraphVersion)
                .where(KnowledgeGraphVersion.organization_id == organization_id)
                .order_by(KnowledgeGraphVersion.version.desc())
            )
        )

    def nodes(self, db: Session, organization_id: UUID) -> list[KnowledgeGraphNode]:
        return list(
            db.scalars(
                select(KnowledgeGraphNode)
                .where(KnowledgeGraphNode.organization_id == organization_id)
                .order_by(KnowledgeGraphNode.created_at.desc())
            )
        )

    def node(self, db: Session, organization_id: UUID, node_id: UUID) -> KnowledgeGraphNode:
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
        edges: list[KnowledgeGraphEdge] = []
        sequence = 0
        truncated = False
        for depth in range(1, payload.max_depth + 1):
            if not frontier or (monotonic() - started) * 1000 >= payload.timeout_ms:
                truncated = bool(frontier)
                break
            conditions = []
            if payload.direction in {"outbound", "both"}:
                conditions.append(KnowledgeGraphEdge.from_node_id.in_(frontier))
            if payload.direction in {"inbound", "both"}:
                conditions.append(KnowledgeGraphEdge.to_node_id.in_(frontier))
            statement = select(KnowledgeGraphEdge).where(
                KnowledgeGraphEdge.organization_id == organization_id,
                KnowledgeGraphEdge.graph_version_id == start.graph_version_id,
                KnowledgeGraphEdge.status == "active",
                KnowledgeGraphEdge.confidence_score >= Decimal(str(payload.minimum_confidence)),
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
            level_edges = list(db.scalars(statement.order_by(KnowledgeGraphEdge.id)))
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
            if truncated:
                break
        run.returned_nodes = len(visited)
        run.returned_edges = len(edges)
        run.returned_paths = min(len(edges), payload.max_paths)
        run.truncated = truncated
        run.status = "completed"
        run.completed_at = datetime.now(UTC)
        run.result_summary = {
            "node_ids": [str(item) for item in sorted(visited, key=str)],
            "edge_ids": [str(item.id) for item in edges],
            "warnings": ["Result was truncated by the approved budget"] if truncated else [],
        }
        GraphProjectionService._meter(db, organization_id, "graph_traversals", 1, run.id)
        db.commit()
        return self._response(db, run)

    def _response(self, db: Session, run: KnowledgeGraphQueryRun) -> GraphTraversalRead:
        raw_node_ids = cast(list[str], run.result_summary.get("node_ids", []))
        raw_edge_ids = cast(list[str], run.result_summary.get("edge_ids", []))
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
            truncated=run.truncated,
            warnings=cast(list[str], run.result_summary.get("warnings", [])),
        )

    def run(self, db: Session, organization_id: UUID, run_id: UUID) -> GraphTraversalRead:
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
