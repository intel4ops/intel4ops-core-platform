from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.ingestion import Dataset, DatasetVersion, IngestionBatch
from app.models.raw_lineage import (
    ActorType,
    ExecutorType,
    IntegrityStatus,
    LineageEdge,
    LineageEvent,
    LineageEventType,
    LineageNode,
    LineageNodeType,
    LineageRelationshipType,
    ProcessingRun,
    ProcessingRunStatus,
    ProcessingRunType,
    RawObjectStatus,
    RawObjectType,
    RawRecordReference,
    RawRecordStatus,
    RawStorageObject,
    RetentionClass,
)
from app.models.source_system import SourceSystem
from app.schemas.raw_lineage import (
    MAX_LINEAGE_DEPTH,
    MAX_LINEAGE_NODES,
    MAX_RECORD_BATCH_SIZE,
    IntegrityVerification,
    LineageEdgeCreate,
    LineageGraphRead,
    LineageNodeCreate,
    ProcessingRunCreate,
    ProcessingRunFailure,
    ProcessingRunResult,
    RawRecordReferenceCreate,
    RawStorageObjectCreate,
)


class RawLineageNotFoundError(ValueError):
    pass


class RawLineageConflictError(ValueError):
    pass


class RawLineageTenantMismatchError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


class LineageEventService:
    def record(
        self,
        db: Session,
        organization_id: UUID,
        event_type: LineageEventType,
        entity_type: str,
        entity_id: UUID,
        actor_user_id: UUID | None,
        *,
        processing_run_id: UUID | None = None,
        summary: str | None = None,
        metadata_json: dict[str, object] | None = None,
    ) -> LineageEvent:
        event = LineageEvent(
            organization_id=organization_id,
            event_type=event_type.value,
            entity_type=entity_type,
            entity_id=entity_id,
            processing_run_id=processing_run_id,
            actor_type=ActorType.USER.value if actor_user_id else ActorType.SYSTEM.value,
            actor_user_id=actor_user_id,
            summary=summary,
            metadata_json=metadata_json,
        )
        db.add(event)
        return event

    def list(
        self,
        db: Session,
        organization_id: UUID,
        *,
        event_type: LineageEventType | None = None,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        processing_run_id: UUID | None = None,
        occurred_from: datetime | None = None,
        occurred_to: datetime | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[LineageEvent]:
        statement = select(LineageEvent).where(LineageEvent.organization_id == organization_id)
        for column, value in (
            (LineageEvent.event_type, event_type.value if event_type else None),
            (LineageEvent.entity_type, entity_type),
            (LineageEvent.entity_id, entity_id),
            (LineageEvent.processing_run_id, processing_run_id),
        ):
            if value is not None:
                statement = statement.where(column == value)
        if occurred_from is not None:
            statement = statement.where(LineageEvent.occurred_at >= occurred_from)
        if occurred_to is not None:
            statement = statement.where(LineageEvent.occurred_at <= occurred_to)
        return list(
            db.scalars(
                statement.order_by(LineageEvent.occurred_at.desc(), LineageEvent.id)
                .offset(offset)
                .limit(limit)
            ).all()
        )


class LineageService:
    entity_models = {
        LineageNodeType.SOURCE_SYSTEM: SourceSystem,
        LineageNodeType.INGESTION_BATCH: IngestionBatch,
        LineageNodeType.DATASET: Dataset,
        LineageNodeType.DATASET_VERSION: DatasetVersion,
        LineageNodeType.RAW_STORAGE_OBJECT: RawStorageObject,
        LineageNodeType.RAW_RECORD_REFERENCE: RawRecordReference,
        LineageNodeType.PROCESSING_RUN: ProcessingRun,
    }
    acyclic_relationships = {
        LineageRelationshipType.DERIVED_FROM.value,
        LineageRelationshipType.TRANSFORMED_FROM.value,
        LineageRelationshipType.EXTRACTED_FROM.value,
        LineageRelationshipType.PARSED_FROM.value,
        LineageRelationshipType.PRODUCED_BY.value,
        LineageRelationshipType.CONSUMED_BY.value,
    }

    def __init__(self, events: LineageEventService | None = None) -> None:
        self.events = events or LineageEventService()

    def register_node(
        self,
        db: Session,
        organization_id: UUID,
        payload: LineageNodeCreate,
    ) -> LineageNode:
        existing = db.scalar(
            select(LineageNode).where(
                LineageNode.organization_id == organization_id,
                LineageNode.node_type == payload.node_type.value,
                LineageNode.entity_id == payload.entity_id,
            )
        )
        if existing is not None:
            return existing
        model: Any = self.entity_models.get(payload.node_type)
        if model is None:
            raise RawLineageConflictError("Custom lineage entities are not registered in WP-2.05")
        entity = db.scalar(
            select(model).where(
                model.id == payload.entity_id,
                model.organization_id == organization_id,
            )
        )
        if entity is None:
            raise RawLineageTenantMismatchError("Lineage entity not found in organization")
        node = LineageNode(organization_id=organization_id, **payload.model_dump())
        db.add(node)
        db.flush()
        return node

    def node_for_entity(
        self, db: Session, organization_id: UUID, node_type: LineageNodeType, entity_id: UUID
    ) -> LineageNode:
        node = db.scalar(
            select(LineageNode).where(
                LineageNode.organization_id == organization_id,
                LineageNode.node_type == node_type.value,
                LineageNode.entity_id == entity_id,
            )
        )
        if node is None:
            raise RawLineageNotFoundError("Lineage node not found")
        return node

    def get_node(self, db: Session, organization_id: UUID, node_id: UUID) -> LineageNode:
        node = db.scalar(
            select(LineageNode).where(
                LineageNode.id == node_id, LineageNode.organization_id == organization_id
            )
        )
        if node is None:
            raise RawLineageNotFoundError("Lineage node not found")
        return node

    def create_edge(
        self,
        db: Session,
        organization_id: UUID,
        payload: LineageEdgeCreate,
        actor_user_id: UUID,
        *,
        commit: bool = True,
    ) -> LineageEdge:
        source = self.get_node(db, organization_id, payload.from_node_id)
        target = self.get_node(db, organization_id, payload.to_node_id)
        if source.id == target.id:
            raise RawLineageConflictError("A lineage node cannot link to itself")
        if payload.processing_run_id is not None:
            run = db.scalar(
                select(ProcessingRun).where(
                    ProcessingRun.id == payload.processing_run_id,
                    ProcessingRun.organization_id == organization_id,
                )
            )
            if run is None:
                raise RawLineageTenantMismatchError("Processing run not found in organization")
        run_key = str(payload.processing_run_id) if payload.processing_run_id else ""
        existing = db.scalar(
            select(LineageEdge).where(
                LineageEdge.organization_id == organization_id,
                LineageEdge.from_node_id == source.id,
                LineageEdge.to_node_id == target.id,
                LineageEdge.relationship_type == payload.relationship_type.value,
                LineageEdge.processing_run_key == run_key,
            )
        )
        if existing is not None:
            return existing
        if payload.relationship_type.value in self.acyclic_relationships and self._reachable(
            db, organization_id, target.id, source.id
        ):
            raise RawLineageConflictError("Lineage edge would create a derivation cycle")
        values = payload.model_dump()
        values["processing_run_key"] = run_key
        edge = LineageEdge(
            organization_id=organization_id,
            created_by_user_id=actor_user_id,
            **values,
        )
        db.add(edge)
        db.flush()
        self.events.record(
            db,
            organization_id,
            LineageEventType.LINEAGE_LINK_CREATED,
            "lineage_edge",
            edge.id,
            actor_user_id,
            processing_run_id=payload.processing_run_id,
        )
        if commit:
            db.commit()
            db.refresh(edge)
        return edge

    def _reachable(self, db: Session, organization_id: UUID, start: UUID, target: UUID) -> bool:
        seen = {start}
        frontier = {start}
        for _ in range(MAX_LINEAGE_DEPTH):
            if not frontier:
                return False
            next_ids = set(
                db.scalars(
                    select(LineageEdge.to_node_id).where(
                        LineageEdge.organization_id == organization_id,
                        LineageEdge.from_node_id.in_(frontier),
                        LineageEdge.relationship_type.in_(self.acyclic_relationships),
                    )
                ).all()
            )
            if target in next_ids:
                return True
            frontier = next_ids - seen
            seen.update(frontier)
            if len(seen) >= MAX_LINEAGE_NODES:
                break
        return False

    def graph(
        self,
        db: Session,
        organization_id: UUID,
        root_node_id: UUID,
        *,
        direction: str = "both",
        max_depth: int = 3,
        max_nodes: int = 100,
        relationship_type: LineageRelationshipType | None = None,
        node_type: LineageNodeType | None = None,
    ) -> LineageGraphRead:
        if not 1 <= max_depth <= MAX_LINEAGE_DEPTH or not 1 <= max_nodes <= MAX_LINEAGE_NODES:
            raise RawLineageConflictError("Lineage traversal limit is invalid")
        root = self.get_node(db, organization_id, root_node_id)
        found: dict[UUID, LineageNode] = {root.id: root}
        edges: dict[UUID, LineageEdge] = {}
        queue: deque[tuple[UUID, int]] = deque([(root.id, 0)])
        depth_reached = 0
        truncated = False
        while queue:
            current, depth = queue.popleft()
            depth_reached = max(depth_reached, depth)
            if depth >= max_depth:
                continue
            edge_filter = [LineageEdge.organization_id == organization_id]
            if direction == "upstream":
                edge_filter.append(LineageEdge.to_node_id == current)
            elif direction == "downstream":
                edge_filter.append(LineageEdge.from_node_id == current)
            else:
                edge_filter.append(
                    or_(
                        LineageEdge.from_node_id == current,
                        LineageEdge.to_node_id == current,
                    )
                )
            if relationship_type is not None:
                edge_filter.append(LineageEdge.relationship_type == relationship_type.value)
            adjacent = list(db.scalars(select(LineageEdge).where(*edge_filter)).all())
            for edge in adjacent:
                neighbor_id = edge.from_node_id if edge.to_node_id == current else edge.to_node_id
                if neighbor_id not in found:
                    neighbor = self.get_node(db, organization_id, neighbor_id)
                    if node_type is not None and neighbor.node_type != node_type.value:
                        continue
                    if len(found) >= max_nodes:
                        truncated = True
                        continue
                    found[neighbor.id] = neighbor
                    queue.append((neighbor.id, depth + 1))
                edges[edge.id] = edge
        return LineageGraphRead(
            root_node_id=root.id,
            nodes=list(found.values()),
            edges=list(edges.values()),
            truncated=truncated,
            depth_reached=depth_reached,
        )


class RawStorageObjectService:
    transitions = {
        RawObjectStatus.REGISTERED: {RawObjectStatus.RECEIVING, RawObjectStatus.RECEIVED},
        RawObjectStatus.RECEIVING: {RawObjectStatus.RECEIVED, RawObjectStatus.QUARANTINED},
        RawObjectStatus.RECEIVED: {RawObjectStatus.VERIFYING, RawObjectStatus.QUARANTINED},
        RawObjectStatus.VERIFYING: {
            RawObjectStatus.SEALED,
            RawObjectStatus.QUARANTINED,
            RawObjectStatus.RECEIVED,
        },
        RawObjectStatus.SEALED: {
            RawObjectStatus.SUPERSEDED,
            RawObjectStatus.ARCHIVED,
            RawObjectStatus.DELETION_REQUESTED,
        },
        RawObjectStatus.QUARANTINED: {
            RawObjectStatus.VERIFYING,
            RawObjectStatus.ARCHIVED,
        },
        RawObjectStatus.SUPERSEDED: {RawObjectStatus.ARCHIVED},
        RawObjectStatus.ARCHIVED: {RawObjectStatus.DELETION_REQUESTED},
        RawObjectStatus.DELETION_REQUESTED: {
            RawObjectStatus.DELETED_REFERENCE,
            RawObjectStatus.ARCHIVED,
        },
        RawObjectStatus.DELETED_REFERENCE: set(),
    }

    def __init__(
        self,
        lineage: LineageService | None = None,
        events: LineageEventService | None = None,
    ) -> None:
        self.events = events or LineageEventService()
        self.lineage = lineage or LineageService(self.events)

    def register(
        self,
        db: Session,
        organization_id: UUID,
        payload: RawStorageObjectCreate,
        actor_user_id: UUID,
    ) -> RawStorageObject:
        source, batch, version, dataset = self._context(db, organization_id, payload)
        if payload.idempotency_key:
            existing = db.scalar(
                select(RawStorageObject).where(
                    RawStorageObject.organization_id == organization_id,
                    RawStorageObject.idempotency_key == payload.idempotency_key,
                )
            )
            if existing is not None:
                identity = (
                    "ingestion_batch_id",
                    "dataset_version_id",
                    "storage_reference",
                    "content_checksum",
                    "size_bytes",
                )
                if all(getattr(existing, key) == getattr(payload, key) for key in identity):
                    return existing
                raise RawLineageConflictError("Idempotency key conflicts with an existing object")
        if db.scalar(
            select(RawStorageObject.id).where(
                RawStorageObject.organization_id == organization_id,
                RawStorageObject.object_number == payload.object_number,
            )
        ):
            raise RawLineageConflictError("Object number already exists")
        if payload.supersedes_raw_object_id is not None:
            prior = self.get(db, organization_id, payload.supersedes_raw_object_id)
            if prior.id == payload.supersedes_raw_object_id and prior.id == getattr(
                payload, "id", None
            ):
                raise RawLineageConflictError("An object cannot supersede itself")
        raw_object = RawStorageObject(
            organization_id=organization_id,
            created_by_user_id=actor_user_id,
            **payload.model_dump(),
        )
        db.add(raw_object)
        try:
            db.flush()
            nodes = {
                "source": self.lineage.register_node(
                    db,
                    organization_id,
                    LineageNodeCreate(node_type=LineageNodeType.SOURCE_SYSTEM, entity_id=source.id),
                ),
                "batch": self.lineage.register_node(
                    db,
                    organization_id,
                    LineageNodeCreate(
                        node_type=LineageNodeType.INGESTION_BATCH, entity_id=batch.id
                    ),
                ),
                "dataset": self.lineage.register_node(
                    db,
                    organization_id,
                    LineageNodeCreate(node_type=LineageNodeType.DATASET, entity_id=dataset.id),
                ),
                "version": self.lineage.register_node(
                    db,
                    organization_id,
                    LineageNodeCreate(
                        node_type=LineageNodeType.DATASET_VERSION, entity_id=version.id
                    ),
                ),
                "raw": self.lineage.register_node(
                    db,
                    organization_id,
                    LineageNodeCreate(
                        node_type=LineageNodeType.RAW_STORAGE_OBJECT,
                        entity_id=raw_object.id,
                    ),
                ),
            }
            for start, end, relation in (
                ("source", "batch", LineageRelationshipType.ORIGINATES_FROM),
                ("batch", "version", LineageRelationshipType.DELIVERED_IN),
                ("dataset", "version", LineageRelationshipType.DESCRIBES),
                ("version", "raw", LineageRelationshipType.STORED_AS),
            ):
                self.lineage.create_edge(
                    db,
                    organization_id,
                    LineageEdgeCreate(
                        from_node_id=nodes[start].id,
                        to_node_id=nodes[end].id,
                        relationship_type=relation,
                    ),
                    actor_user_id,
                    commit=False,
                )
            self.events.record(
                db,
                organization_id,
                LineageEventType.REGISTERED,
                LineageNodeType.RAW_STORAGE_OBJECT.value,
                raw_object.id,
                actor_user_id,
            )
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise RawLineageConflictError("Raw object identity already exists") from exc
        db.refresh(raw_object)
        return raw_object

    def _context(
        self, db: Session, organization_id: UUID, payload: RawStorageObjectCreate
    ) -> tuple[SourceSystem, IngestionBatch, DatasetVersion, Dataset]:
        source = db.scalar(
            select(SourceSystem).where(
                SourceSystem.id == payload.source_system_id,
                SourceSystem.organization_id == organization_id,
            )
        )
        batch = db.scalar(
            select(IngestionBatch).where(
                IngestionBatch.id == payload.ingestion_batch_id,
                IngestionBatch.organization_id == organization_id,
            )
        )
        version = db.scalar(
            select(DatasetVersion).where(
                DatasetVersion.id == payload.dataset_version_id,
                DatasetVersion.organization_id == organization_id,
            )
        )
        if source is None or batch is None or version is None:
            raise RawLineageTenantMismatchError("Raw object context not found in organization")
        dataset = db.scalar(
            select(Dataset).where(
                Dataset.id == version.dataset_id, Dataset.organization_id == organization_id
            )
        )
        if (
            dataset is None
            or batch.id != version.ingestion_batch_id
            or source.id != batch.source_system_id
            or source.id != dataset.source_system_id
        ):
            raise RawLineageTenantMismatchError("Raw object context is inconsistent")
        return source, batch, version, dataset

    def get(self, db: Session, organization_id: UUID, raw_object_id: UUID) -> RawStorageObject:
        item = db.scalar(
            select(RawStorageObject).where(
                RawStorageObject.id == raw_object_id,
                RawStorageObject.organization_id == organization_id,
            )
        )
        if item is None:
            raise RawLineageNotFoundError("Raw storage object not found")
        return item

    def list(
        self,
        db: Session,
        organization_id: UUID,
        *,
        source_system_id: UUID | None = None,
        ingestion_batch_id: UUID | None = None,
        dataset_version_id: UUID | None = None,
        object_type: RawObjectType | None = None,
        status: RawObjectStatus | None = None,
        integrity_status: IntegrityStatus | None = None,
        retention_class: RetentionClass | None = None,
        legal_hold: bool | None = None,
        checksum: str | None = None,
        received_from: datetime | None = None,
        received_to: datetime | None = None,
        filename_search: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[RawStorageObject]:
        statement = select(RawStorageObject).where(
            RawStorageObject.organization_id == organization_id
        )
        for column, value in (
            (RawStorageObject.source_system_id, source_system_id),
            (RawStorageObject.ingestion_batch_id, ingestion_batch_id),
            (RawStorageObject.dataset_version_id, dataset_version_id),
            (RawStorageObject.object_type, object_type.value if object_type else None),
            (RawStorageObject.status, status.value if status else None),
            (
                RawStorageObject.integrity_status,
                integrity_status.value if integrity_status else None,
            ),
            (
                RawStorageObject.retention_class,
                retention_class.value if retention_class else None,
            ),
            (RawStorageObject.legal_hold, legal_hold),
            (RawStorageObject.content_checksum, checksum),
        ):
            if value is not None:
                statement = statement.where(column == value)
        if received_from is not None:
            statement = statement.where(RawStorageObject.received_at >= received_from)
        if received_to is not None:
            statement = statement.where(RawStorageObject.received_at <= received_to)
        if filename_search is not None:
            statement = statement.where(
                RawStorageObject.original_filename.ilike(f"%{filename_search}%")
            )
        return list(
            db.scalars(
                statement.order_by(RawStorageObject.received_at.desc(), RawStorageObject.id)
                .offset(offset)
                .limit(limit)
            ).all()
        )

    def transition(
        self,
        db: Session,
        organization_id: UUID,
        raw_object_id: UUID,
        target: RawObjectStatus,
        actor_user_id: UUID,
        *,
        summary: str | None = None,
    ) -> RawStorageObject:
        item = self.get(db, organization_id, raw_object_id)
        current = RawObjectStatus(item.status)
        if target not in self.transitions[current]:
            raise RawLineageConflictError(
                f"Cannot transition from {current.value} to {target.value}"
            )
        if target == RawObjectStatus.SEALED and item.integrity_status != IntegrityStatus.VERIFIED:
            raise RawLineageConflictError("Sealing requires verified integrity")
        if target == RawObjectStatus.DELETION_REQUESTED and item.legal_hold:
            raise RawLineageConflictError("Legal hold blocks deletion")
        item.status = target.value
        event_type = {
            RawObjectStatus.SEALED: LineageEventType.SEALED,
            RawObjectStatus.QUARANTINED: LineageEventType.QUARANTINED,
            RawObjectStatus.SUPERSEDED: LineageEventType.SUPERSEDED,
            RawObjectStatus.ARCHIVED: LineageEventType.ARCHIVED,
            RawObjectStatus.DELETION_REQUESTED: LineageEventType.DELETION_REQUESTED,
            RawObjectStatus.DELETED_REFERENCE: LineageEventType.REFERENCE_DELETED,
            RawObjectStatus.RECEIVED: LineageEventType.RECEIVED,
        }.get(target, LineageEventType.CUSTOM)
        now = _now()
        if target == RawObjectStatus.SEALED:
            item.sealed_at = now
        self.events.record(
            db,
            organization_id,
            event_type,
            LineageNodeType.RAW_STORAGE_OBJECT.value,
            item.id,
            actor_user_id,
            summary=summary,
        )
        db.commit()
        db.refresh(item)
        return item

    def verify(
        self,
        db: Session,
        organization_id: UUID,
        raw_object_id: UUID,
        payload: IntegrityVerification,
        actor_user_id: UUID,
    ) -> RawStorageObject:
        item = self.get(db, organization_id, raw_object_id)
        if item.status not in {
            RawObjectStatus.RECEIVED.value,
            RawObjectStatus.VERIFYING.value,
            RawObjectStatus.QUARANTINED.value,
        }:
            raise RawLineageConflictError("Object is not eligible for integrity verification")
        matched = (
            payload.matched
            and item.content_checksum_algorithm == payload.checksum_algorithm.value
            and item.content_checksum == payload.checksum
        )
        item.integrity_status = (
            IntegrityStatus.VERIFIED.value if matched else IntegrityStatus.MISMATCH.value
        )
        item.verified_at = _now() if matched else None
        self.events.record(
            db,
            organization_id,
            (
                LineageEventType.CHECKSUM_VERIFIED
                if matched
                else LineageEventType.INTEGRITY_MISMATCH
            ),
            LineageNodeType.RAW_STORAGE_OBJECT.value,
            item.id,
            actor_user_id,
        )
        db.commit()
        db.refresh(item)
        return item

    def apply_legal_hold(
        self, db: Session, organization_id: UUID, raw_object_id: UUID, reason: str, actor: UUID
    ) -> RawStorageObject:
        item = self.get(db, organization_id, raw_object_id)
        item.legal_hold = True
        item.legal_hold_reason = reason
        self.events.record(
            db,
            organization_id,
            LineageEventType.LEGAL_HOLD_APPLIED,
            LineageNodeType.RAW_STORAGE_OBJECT.value,
            item.id,
            actor,
            summary=reason,
        )
        db.commit()
        db.refresh(item)
        return item

    def release_legal_hold(
        self, db: Session, organization_id: UUID, raw_object_id: UUID, actor: UUID
    ) -> RawStorageObject:
        item = self.get(db, organization_id, raw_object_id)
        item.legal_hold = False
        item.legal_hold_reason = None
        self.events.record(
            db,
            organization_id,
            LineageEventType.LEGAL_HOLD_RELEASED,
            LineageNodeType.RAW_STORAGE_OBJECT.value,
            item.id,
            actor,
        )
        db.commit()
        db.refresh(item)
        return item


class RawRecordReferenceService:
    def __init__(
        self,
        raw_objects: RawStorageObjectService | None = None,
        lineage: LineageService | None = None,
        events: LineageEventService | None = None,
    ) -> None:
        self.events = events or LineageEventService()
        self.lineage = lineage or LineageService(self.events)
        self.raw_objects = raw_objects or RawStorageObjectService(self.lineage, self.events)

    def register(
        self,
        db: Session,
        organization_id: UUID,
        raw_object_id: UUID,
        payload: RawRecordReferenceCreate,
        actor: UUID,
        *,
        commit: bool = True,
    ) -> RawRecordReference:
        raw_object = self.raw_objects.get(db, organization_id, raw_object_id)
        if raw_object.dataset_version_id != payload.dataset_version_id:
            raise RawLineageTenantMismatchError("Record dataset version does not match raw object")
        reference = RawRecordReference(
            organization_id=organization_id,
            raw_storage_object_id=raw_object_id,
            **payload.model_dump(),
        )
        db.add(reference)
        try:
            db.flush()
            raw_node = self.lineage.node_for_entity(
                db, organization_id, LineageNodeType.RAW_STORAGE_OBJECT, raw_object_id
            )
            record_node = self.lineage.register_node(
                db,
                organization_id,
                LineageNodeCreate(
                    node_type=LineageNodeType.RAW_RECORD_REFERENCE,
                    entity_id=reference.id,
                ),
            )
            self.lineage.create_edge(
                db,
                organization_id,
                LineageEdgeCreate(
                    from_node_id=raw_node.id,
                    to_node_id=record_node.id,
                    relationship_type=LineageRelationshipType.CONTAINS,
                ),
                actor,
                commit=False,
            )
            self.events.record(
                db,
                organization_id,
                LineageEventType.REGISTERED,
                LineageNodeType.RAW_RECORD_REFERENCE.value,
                reference.id,
                actor,
            )
            if commit:
                db.commit()
                db.refresh(reference)
        except IntegrityError as exc:
            db.rollback()
            raise RawLineageConflictError("Record sequence already exists") from exc
        return reference

    def register_batch(
        self,
        db: Session,
        organization_id: UUID,
        raw_object_id: UUID,
        payloads: list[RawRecordReferenceCreate],
        actor: UUID,
    ) -> list[RawRecordReference]:
        if not payloads or len(payloads) > MAX_RECORD_BATCH_SIZE:
            raise RawLineageConflictError("Record batch size is invalid")
        created = [
            self.register(db, organization_id, raw_object_id, payload, actor, commit=False)
            for payload in payloads
        ]
        db.commit()
        for item in created:
            db.refresh(item)
        return created

    def get(self, db: Session, organization_id: UUID, reference_id: UUID) -> RawRecordReference:
        item = db.scalar(
            select(RawRecordReference).where(
                RawRecordReference.id == reference_id,
                RawRecordReference.organization_id == organization_id,
            )
        )
        if item is None:
            raise RawLineageNotFoundError("Raw record reference not found")
        return item

    def list(
        self,
        db: Session,
        organization_id: UUID,
        *,
        raw_object_id: UUID | None = None,
        dataset_version_id: UUID | None = None,
        status: RawRecordStatus | None = None,
        record_key: str | None = None,
        source_row_number: int | None = None,
        source_event_id: str | None = None,
        source_timestamp_from: datetime | None = None,
        source_timestamp_to: datetime | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[RawRecordReference]:
        statement = select(RawRecordReference).where(
            RawRecordReference.organization_id == organization_id
        )
        for column, value in (
            (RawRecordReference.raw_storage_object_id, raw_object_id),
            (RawRecordReference.dataset_version_id, dataset_version_id),
            (RawRecordReference.status, status.value if status else None),
            (RawRecordReference.record_key, record_key),
            (RawRecordReference.source_row_number, source_row_number),
            (RawRecordReference.source_event_id, source_event_id),
        ):
            if value is not None:
                statement = statement.where(column == value)
        if source_timestamp_from is not None:
            statement = statement.where(
                RawRecordReference.source_timestamp >= source_timestamp_from
            )
        if source_timestamp_to is not None:
            statement = statement.where(RawRecordReference.source_timestamp <= source_timestamp_to)
        return list(
            db.scalars(
                statement.order_by(RawRecordReference.record_sequence).offset(offset).limit(limit)
            ).all()
        )

    def set_status(
        self,
        db: Session,
        organization_id: UUID,
        reference_id: UUID,
        status: RawRecordStatus,
    ) -> RawRecordReference:
        if status not in {
            RawRecordStatus.EXCLUDED,
            RawRecordStatus.QUARANTINED,
            RawRecordStatus.SUPERSEDED,
        }:
            raise RawLineageConflictError("Record status operation is not permitted")
        item = self.get(db, organization_id, reference_id)
        item.status = status.value
        db.commit()
        db.refresh(item)
        return item


class ProcessingRunService:
    transitions = {
        ProcessingRunStatus.CREATED: {
            ProcessingRunStatus.QUEUED,
            ProcessingRunStatus.RUNNING,
            ProcessingRunStatus.CANCELLED,
        },
        ProcessingRunStatus.QUEUED: {
            ProcessingRunStatus.RUNNING,
            ProcessingRunStatus.CANCELLED,
            ProcessingRunStatus.QUARANTINED,
        },
        ProcessingRunStatus.RUNNING: {
            ProcessingRunStatus.COMPLETED,
            ProcessingRunStatus.PARTIALLY_COMPLETED,
            ProcessingRunStatus.FAILED,
            ProcessingRunStatus.CANCELLED,
            ProcessingRunStatus.QUARANTINED,
        },
        ProcessingRunStatus.FAILED: {ProcessingRunStatus.QUEUED},
        ProcessingRunStatus.QUARANTINED: {ProcessingRunStatus.QUEUED},
        ProcessingRunStatus.COMPLETED: set(),
        ProcessingRunStatus.PARTIALLY_COMPLETED: set(),
        ProcessingRunStatus.CANCELLED: set(),
    }

    def __init__(self, events: LineageEventService | None = None) -> None:
        self.events = events or LineageEventService()

    def create(
        self,
        db: Session,
        organization_id: UUID,
        payload: ProcessingRunCreate,
        actor: UUID,
    ) -> ProcessingRun:
        for model, entity_id, label in (
            (IngestionBatch, payload.ingestion_batch_id, "Ingestion batch"),
            (DatasetVersion, payload.dataset_version_id, "Dataset version"),
            (ProcessingRun, payload.parent_run_id, "Parent run"),
        ):
            if (
                entity_id is not None
                and db.scalar(
                    select(model.id).where(
                        model.id == entity_id, model.organization_id == organization_id
                    )
                )
                is None
            ):
                raise RawLineageTenantMismatchError(f"{label} not found in organization")
        run = ProcessingRun(
            organization_id=organization_id,
            created_by_user_id=actor,
            **payload.model_dump(),
        )
        db.add(run)
        db.flush()
        LineageService(self.events).register_node(
            db,
            organization_id,
            LineageNodeCreate(node_type=LineageNodeType.PROCESSING_RUN, entity_id=run.id),
        )
        self.events.record(
            db,
            organization_id,
            LineageEventType.REGISTERED,
            LineageNodeType.PROCESSING_RUN.value,
            run.id,
            actor,
            processing_run_id=run.id,
        )
        db.commit()
        db.refresh(run)
        return run

    def get(self, db: Session, organization_id: UUID, run_id: UUID) -> ProcessingRun:
        run = db.scalar(
            select(ProcessingRun).where(
                ProcessingRun.id == run_id,
                ProcessingRun.organization_id == organization_id,
            )
        )
        if run is None:
            raise RawLineageNotFoundError("Processing run not found")
        return run

    def list(
        self,
        db: Session,
        organization_id: UUID,
        *,
        status: ProcessingRunStatus | None = None,
        ingestion_batch_id: UUID | None = None,
        dataset_version_id: UUID | None = None,
        run_type: ProcessingRunType | None = None,
        executor_type: ExecutorType | None = None,
        correlation_id: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[ProcessingRun]:
        statement = select(ProcessingRun).where(ProcessingRun.organization_id == organization_id)
        if status is not None:
            statement = statement.where(ProcessingRun.status == status.value)
        for column, value in (
            (ProcessingRun.ingestion_batch_id, ingestion_batch_id),
            (ProcessingRun.dataset_version_id, dataset_version_id),
            (ProcessingRun.run_type, run_type.value if run_type else None),
            (ProcessingRun.executor_type, executor_type.value if executor_type else None),
            (ProcessingRun.correlation_id, correlation_id),
        ):
            if value is not None:
                statement = statement.where(column == value)
        if created_from is not None:
            statement = statement.where(ProcessingRun.created_at >= created_from)
        if created_to is not None:
            statement = statement.where(ProcessingRun.created_at <= created_to)
        return list(
            db.scalars(
                statement.order_by(ProcessingRun.created_at.desc(), ProcessingRun.id)
                .offset(offset)
                .limit(limit)
            ).all()
        )

    def transition(
        self,
        db: Session,
        organization_id: UUID,
        run_id: UUID,
        target: ProcessingRunStatus,
        actor: UUID,
        result: ProcessingRunResult | None = None,
    ) -> ProcessingRun:
        run = self.get(db, organization_id, run_id)
        current = ProcessingRunStatus(run.status)
        if target not in self.transitions[current]:
            raise RawLineageConflictError(
                f"Cannot transition processing run from {current.value} to {target.value}"
            )
        run.status = target.value
        now = _now()
        if target == ProcessingRunStatus.RUNNING:
            run.started_at = now
            event_type = LineageEventType.PROCESSING_STARTED
        elif target in {
            ProcessingRunStatus.COMPLETED,
            ProcessingRunStatus.PARTIALLY_COMPLETED,
        }:
            run.completed_at = now
            event_type = LineageEventType.PROCESSING_COMPLETED
        elif target == ProcessingRunStatus.FAILED:
            run.failed_at = now
            event_type = LineageEventType.PROCESSING_FAILED
        else:
            event_type = LineageEventType.CUSTOM
        if result is not None:
            for field, value in result.model_dump().items():
                setattr(run, field, value)
        self.events.record(
            db,
            organization_id,
            event_type,
            LineageNodeType.PROCESSING_RUN.value,
            run.id,
            actor,
            processing_run_id=run.id,
        )
        db.commit()
        db.refresh(run)
        return run

    def fail(
        self,
        db: Session,
        organization_id: UUID,
        run_id: UUID,
        payload: ProcessingRunFailure,
        actor: UUID,
    ) -> ProcessingRun:
        return self.transition(
            db, organization_id, run_id, ProcessingRunStatus.FAILED, actor, payload
        )
