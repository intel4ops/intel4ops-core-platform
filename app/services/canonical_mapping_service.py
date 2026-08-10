from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from typing import Any, NoReturn
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.canonical_mapping import (
    CanonicalEntity,
    CanonicalEntityType,
    CanonicalEvent,
    CanonicalEventType,
    CanonicalFieldDefinition,
    CanonicalMetric,
    CanonicalMetricType,
    CanonicalTypeKind,
    CrosswalkEntryStatus,
    EntityMatchCandidate,
    EntityMatchRule,
    FieldMapping,
    MappingAuditEvent,
    MappingException,
    MappingExceptionStatus,
    MappingExceptionType,
    MappingLifecycleStatus,
    MappingRecordResult,
    MappingRecordStatus,
    MappingReview,
    MappingRun,
    MappingRunStatus,
    MappingTemplate,
    MappingTemplateVersion,
    MappingTransformation,
    MatchCandidateStatus,
    OccurrencePrecision,
    SourceCanonicalLink,
    SourceField,
    SourceSchema,
    TransformationType,
    ValueCrosswalk,
    ValueCrosswalkEntry,
)
from app.models.entities import utc_now
from app.models.ingestion import Dataset, DatasetVersion, SchemaStatus
from app.models.raw_lineage import (
    LineageEdge,
    LineageNode,
    LineageNodeStatus,
    LineageNodeType,
    LineageRelationshipType,
    RawRecordReference,
)
from app.schemas.canonical_mapping import (
    CanonicalFieldCreate,
    CanonicalTypeCreate,
    EntityMatchDecision,
    FieldMappingCreate,
    MappingInputRecord,
    MappingReviewCreate,
    MappingRunCreate,
    MappingTemplateCreate,
    MappingTemplateVersionCreate,
    SourceSchemaDiscover,
    TransformationCreate,
    ValueCrosswalkCreate,
    ValueCrosswalkEntryCreate,
)
from app.schemas.operational_memory import (
    FieldMappingPayload,
    MemoryCandidateCreate,
    MemoryContext,
    MemoryProvenance,
)
from app.services.operational_memory_service import operational_memory_service

_MAPPING_RUN_IDEMPOTENCY_CONSTRAINT = "uq_mapping_run_idempotency_key"


class CanonicalMappingServiceError(RuntimeError):
    def __init__(self, code: str, message: str, status: int) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class CanonicalFieldValidationError(ValueError):
    pass


def _fail(code: str, message: str, status: int = 400) -> NoReturn:
    raise CanonicalMappingServiceError(code, message, status)


def _stable_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: object) -> str:
    return hashlib.sha256(_stable_json(value).encode()).hexdigest()


def _scope_visible(
    owner_organization_id: UUID | None,
    scope_type: str,
    organization_id: UUID | None,
) -> bool:
    if scope_type != "organization":
        return True
    return organization_id is not None and owner_organization_id == organization_id


def _audit(
    db: Session,
    organization_id: UUID,
    event_type: str,
    entity_type: str,
    entity_id: UUID,
    actor_user_id: UUID,
    summary: str,
    metadata: dict[str, object] | None = None,
) -> None:
    db.add(
        MappingAuditEvent(
            organization_id=organization_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_type="user",
            actor_user_id=actor_user_id,
            summary=summary,
            metadata_json=metadata or {},
        )
    )


class CanonicalRegistryService:
    def create_type(
        self,
        db: Session,
        kind: str,
        payload: CanonicalTypeCreate,
    ) -> CanonicalEntityType | CanonicalEventType | CanonicalMetricType:
        if kind not in {item.value for item in CanonicalTypeKind}:
            _fail("CANONICAL_KIND_INVALID", "Unsupported canonical type kind")
        if payload.scope_type == "organization" and payload.owner_organization_id is None:
            _fail("SCOPE_OWNER_REQUIRED", "Organization scope requires an owner")
        common: dict[str, object] = {
            "type_code": payload.type_code,
            "display_name": payload.display_name,
            "description": payload.description,
            "scope_type": payload.scope_type,
            "scope_key": payload.scope_key,
            "owner_organization_id": payload.owner_organization_id,
            "industry_pack_code": payload.industry_pack_code,
        }
        record: CanonicalEntityType | CanonicalEventType | CanonicalMetricType
        if kind == CanonicalTypeKind.ENTITY.value:
            record = CanonicalEntityType(
                **common,
                identity_strategy_code=payload.identity_strategy_code,
            )
        elif kind == CanonicalTypeKind.EVENT.value:
            record = CanonicalEventType(
                **common,
                applicable_entity_type_id=payload.applicable_entity_type_id,
            )
        else:
            if payload.aggregation_hint is None:
                _fail("AGGREGATION_REQUIRED", "Metric types require an aggregation hint")
            record = CanonicalMetricType(
                **common,
                unit_dimension=payload.unit_dimension,
                default_unit=payload.default_unit,
                aggregation_hint=payload.aggregation_hint,
            )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def list_types(
        self,
        db: Session,
        kind: str,
        organization_id: UUID | None,
    ) -> list[CanonicalEntityType | CanonicalEventType | CanonicalMetricType]:
        records: list[CanonicalEntityType | CanonicalEventType | CanonicalMetricType]
        if kind == CanonicalTypeKind.ENTITY.value:
            records = list(
                db.scalars(select(CanonicalEntityType).order_by(CanonicalEntityType.type_code))
            )
        elif kind == CanonicalTypeKind.EVENT.value:
            records = list(
                db.scalars(select(CanonicalEventType).order_by(CanonicalEventType.type_code))
            )
        elif kind == CanonicalTypeKind.METRIC.value:
            records = list(
                db.scalars(select(CanonicalMetricType).order_by(CanonicalMetricType.type_code))
            )
        else:
            _fail("CANONICAL_KIND_INVALID", "Unsupported canonical type kind")
        return [
            item
            for item in records
            if _scope_visible(
                item.owner_organization_id,
                item.scope_type,
                organization_id,
            )
        ]

    def create_field(
        self,
        db: Session,
        payload: CanonicalFieldCreate,
        organization_id: UUID | None = None,
    ) -> CanonicalFieldDefinition:
        self.require_type(
            db,
            payload.canonical_type_kind,
            payload.canonical_type_id,
            organization_id,
        )
        field = CanonicalFieldDefinition(**payload.model_dump())
        db.add(field)
        db.commit()
        db.refresh(field)
        return field

    def require_field(
        self,
        db: Session,
        field_id: UUID,
        organization_id: UUID | None,
    ) -> CanonicalFieldDefinition:
        field = db.get(CanonicalFieldDefinition, field_id)
        if field is None:
            _fail("CANONICAL_FIELD_NOT_FOUND", "Canonical field was not found", 404)
        self.require_type(
            db,
            field.canonical_type_kind,
            field.canonical_type_id,
            organization_id,
        )
        return field

    def require_type(
        self,
        db: Session,
        kind: str,
        type_id: UUID,
        organization_id: UUID | None,
    ) -> CanonicalEntityType | CanonicalEventType | CanonicalMetricType:
        record: CanonicalEntityType | CanonicalEventType | CanonicalMetricType | None
        if kind == CanonicalTypeKind.ENTITY.value:
            record = db.get(CanonicalEntityType, type_id)
        elif kind == CanonicalTypeKind.EVENT.value:
            record = db.get(CanonicalEventType, type_id)
        elif kind == CanonicalTypeKind.METRIC.value:
            record = db.get(CanonicalMetricType, type_id)
        else:
            _fail("CANONICAL_KIND_INVALID", "Unsupported canonical type kind")
        if record is None or not _scope_visible(
            record.owner_organization_id,
            record.scope_type,
            organization_id,
        ):
            _fail("CANONICAL_TYPE_NOT_FOUND", "Canonical type is outside the visible scope", 404)
        return record


class SchemaDiscoveryService:
    def discover(
        self,
        db: Session,
        organization_id: UUID,
        payload: SourceSchemaDiscover,
    ) -> SourceSchema:
        dataset = db.scalar(
            select(Dataset).where(
                Dataset.id == payload.dataset_id,
                Dataset.organization_id == organization_id,
            )
        )
        if dataset is None:
            _fail("DATASET_NOT_FOUND", "Dataset is outside tenant scope", 404)
        if payload.dataset_version_id is not None:
            version = db.scalar(
                select(DatasetVersion).where(
                    DatasetVersion.id == payload.dataset_version_id,
                    DatasetVersion.organization_id == organization_id,
                    DatasetVersion.dataset_id == payload.dataset_id,
                )
            )
            if version is None:
                _fail("DATASET_VERSION_NOT_FOUND", "Dataset version is outside tenant scope", 404)
        existing = db.scalar(
            select(SourceSchema).where(
                SourceSchema.organization_id == organization_id,
                SourceSchema.dataset_id == payload.dataset_id,
                SourceSchema.schema_fingerprint == payload.schema_fingerprint,
            )
        )
        if existing is not None:
            return existing
        record = SourceSchema(
            organization_id=organization_id,
            dataset_id=payload.dataset_id,
            dataset_version_id=payload.dataset_version_id,
            status=SchemaStatus.DISCOVERED.value,
            schema_fingerprint=payload.schema_fingerprint,
            discovery_method="automated",
        )
        db.add(record)
        db.flush()
        db.add_all(
            [
                SourceField(
                    organization_id=organization_id,
                    source_schema_id=record.id,
                    **field.model_dump(),
                )
                for field in payload.fields
            ]
        )
        db.commit()
        db.refresh(record)
        return record

    def for_dataset_version(
        self,
        db: Session,
        organization_id: UUID,
        dataset_version_id: UUID,
    ) -> list[SourceSchema]:
        return list(
            db.scalars(
                select(SourceSchema)
                .where(
                    SourceSchema.organization_id == organization_id,
                    SourceSchema.dataset_version_id == dataset_version_id,
                )
                .order_by(SourceSchema.discovered_at.desc())
            )
        )


class MappingTemplateService:
    transitions = {
        MappingLifecycleStatus.DRAFT.value: {MappingLifecycleStatus.CANDIDATE.value},
        MappingLifecycleStatus.CANDIDATE.value: {MappingLifecycleStatus.VALIDATED.value},
        MappingLifecycleStatus.VALIDATED.value: {MappingLifecycleStatus.APPROVED.value},
        MappingLifecycleStatus.APPROVED.value: {MappingLifecycleStatus.PUBLISHED.value},
        MappingLifecycleStatus.PUBLISHED.value: {MappingLifecycleStatus.DEPRECATED.value},
        MappingLifecycleStatus.DEPRECATED.value: {MappingLifecycleStatus.RETIRED.value},
        MappingLifecycleStatus.RETIRED.value: set(),
    }

    def create(
        self,
        db: Session,
        payload: MappingTemplateCreate,
        actor_user_id: UUID,
        authorized_organization_id: UUID | None = None,
    ) -> MappingTemplate:
        canonical_registry_service.require_type(
            db,
            payload.target_canonical_type_kind,
            payload.target_canonical_type_id,
            payload.owner_organization_id,
        )
        if payload.scope_type == "organization" and payload.owner_organization_id is None:
            _fail("SCOPE_OWNER_REQUIRED", "Organization scope requires an owner")
        if authorized_organization_id is not None and (
            payload.scope_type != "organization"
            or payload.owner_organization_id != authorized_organization_id
        ):
            _fail(
                "TEMPLATE_SCOPE_MISMATCH",
                "Tenant template owner must match the authorized organization",
                403,
            )
        template = MappingTemplate(**payload.model_dump())
        db.add(template)
        db.flush()
        audit_org = payload.owner_organization_id
        if audit_org is not None:
            _audit(
                db,
                audit_org,
                "template_created",
                "mapping_template",
                template.id,
                actor_user_id,
                "Mapping template created",
            )
        db.commit()
        db.refresh(template)
        return template

    def create_version(
        self,
        db: Session,
        template_id: UUID,
        payload: MappingTemplateVersionCreate,
        actor_user_id: UUID,
        organization_id: UUID | None,
    ) -> MappingTemplateVersion:
        template = self.require_template(db, template_id, organization_id)
        content_hash = _fingerprint(payload.definition_json)
        version = MappingTemplateVersion(
            template_id=template.id,
            semantic_version=payload.semantic_version,
            lifecycle_status=MappingLifecycleStatus.DRAFT.value,
            content_hash=content_hash,
            definition_json=payload.definition_json,
            created_by_user_id=actor_user_id,
        )
        db.add(version)
        db.commit()
        db.refresh(version)
        return version

    def add_field_mapping(
        self,
        db: Session,
        version_id: UUID,
        payload: FieldMappingCreate,
        organization_id: UUID | None,
    ) -> FieldMapping:
        version = self.require_version(db, version_id, organization_id)
        if version.lifecycle_status not in {
            MappingLifecycleStatus.DRAFT.value,
            MappingLifecycleStatus.CANDIDATE.value,
        }:
            _fail("VERSION_IMMUTABLE", "Field mappings cannot change after validation", 409)
        field_definition = canonical_registry_service.require_field(
            db,
            payload.canonical_field_definition_id,
            organization_id,
        )
        template = db.get(MappingTemplate, version.template_id)
        assert template is not None
        if (
            field_definition.canonical_type_kind != template.target_canonical_type_kind
            or field_definition.canonical_type_id != template.target_canonical_type_id
        ):
            _fail(
                "CANONICAL_FIELD_TARGET_MISMATCH",
                "Canonical field does not belong to the mapping template target type",
                422,
            )
        field = FieldMapping(template_version_id=version.id, **payload.model_dump())
        db.add(field)
        db.commit()
        db.refresh(field)
        return field

    def add_transformation(
        self,
        db: Session,
        field_mapping_id: UUID,
        payload: TransformationCreate,
        organization_id: UUID | None,
    ) -> MappingTransformation:
        field = db.get(FieldMapping, field_mapping_id)
        if field is None:
            _fail("FIELD_MAPPING_NOT_FOUND", "Field mapping was not found", 404)
        version = self.require_version(db, field.template_version_id, organization_id)
        if version.lifecycle_status not in {
            MappingLifecycleStatus.DRAFT.value,
            MappingLifecycleStatus.CANDIDATE.value,
        }:
            _fail("VERSION_IMMUTABLE", "Transformations cannot change after validation", 409)
        transformation = MappingTransformation(
            field_mapping_id=field.id,
            **payload.model_dump(),
        )
        db.add(transformation)
        db.commit()
        db.refresh(transformation)
        return transformation

    def transition(
        self,
        db: Session,
        version_id: UUID,
        target: str,
        actor_user_id: UUID,
        organization_id: UUID | None,
    ) -> MappingTemplateVersion:
        version = self.require_version(db, version_id, organization_id)
        allowed = self.transitions.get(version.lifecycle_status, set())
        if target not in allowed:
            _fail(
                "INVALID_LIFECYCLE_TRANSITION",
                f"{version.lifecycle_status} cannot transition to {target}",
                409,
            )
        if target == MappingLifecycleStatus.VALIDATED.value:
            mappings = list(
                db.scalars(
                    select(FieldMapping).where(FieldMapping.template_version_id == version.id)
                )
            )
            if not mappings:
                _fail("MAPPING_REQUIRED", "A template version requires at least one field mapping")
            version.validated_at = utc_now()
        elif target == MappingLifecycleStatus.APPROVED.value:
            version.approved_at = utc_now()
            version.approved_by_user_id = actor_user_id
        elif target == MappingLifecycleStatus.PUBLISHED.value:
            version.published_at = utc_now()
        version.lifecycle_status = target
        db.commit()
        db.refresh(version)
        return version

    def require_template(
        self,
        db: Session,
        template_id: UUID,
        organization_id: UUID | None,
    ) -> MappingTemplate:
        template = db.get(MappingTemplate, template_id)
        if template is None or not _scope_visible(
            template.owner_organization_id,
            template.scope_type,
            organization_id,
        ):
            _fail("MAPPING_TEMPLATE_NOT_FOUND", "Mapping template is outside scope", 404)
        return template

    def require_version(
        self,
        db: Session,
        version_id: UUID,
        organization_id: UUID | None,
    ) -> MappingTemplateVersion:
        version = db.get(MappingTemplateVersion, version_id)
        if version is None:
            _fail("MAPPING_VERSION_NOT_FOUND", "Mapping version was not found", 404)
        self.require_template(db, version.template_id, organization_id)
        return version


class ValueCrosswalkService:
    def create(
        self,
        db: Session,
        payload: ValueCrosswalkCreate,
        actor_user_id: UUID,
        authorized_organization_id: UUID | None = None,
    ) -> ValueCrosswalk:
        if authorized_organization_id is not None and (
            payload.scope_type != "organization"
            or payload.owner_organization_id != authorized_organization_id
        ):
            _fail(
                "CROSSWALK_TENANT_MISMATCH",
                "Tenant crosswalk owner must match the authorized organization",
                422,
            )
        visible_organization_id = (
            authorized_organization_id
            if authorized_organization_id is not None
            else payload.owner_organization_id
        )
        canonical_registry_service.require_field(
            db,
            payload.canonical_field_definition_id,
            visible_organization_id,
        )
        crosswalk = ValueCrosswalk(
            **payload.model_dump(),
            created_by_user_id=actor_user_id,
        )
        db.add(crosswalk)
        db.commit()
        db.refresh(crosswalk)
        return crosswalk

    def add_entry(
        self,
        db: Session,
        crosswalk_id: UUID,
        payload: ValueCrosswalkEntryCreate,
        organization_id: UUID | None,
    ) -> ValueCrosswalkEntry:
        crosswalk = db.get(ValueCrosswalk, crosswalk_id)
        if crosswalk is None or not _scope_visible(
            crosswalk.owner_organization_id,
            crosswalk.scope_type,
            organization_id,
        ):
            _fail("CROSSWALK_NOT_FOUND", "Crosswalk is outside scope", 404)
        entry = ValueCrosswalkEntry(
            owner_organization_id=crosswalk.owner_organization_id,
            crosswalk_id=crosswalk.id,
            source_value=payload.source_value,
            normalized_source_value=self.normalize(payload.source_value),
            canonical_target_value=payload.canonical_target_value,
            mapping_confidence_score=payload.mapping_confidence_score,
            confidence_method_code=payload.confidence_method_code,
            confidence_method_version=payload.confidence_method_version,
            confidence_components=None,
            confidence_interpretation=None,
            confidence_limitations=None,
            status=CrosswalkEntryStatus.DRAFT.value,
            effective_from=payload.effective_from,
            effective_to=payload.effective_to,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry

    def approve(
        self,
        db: Session,
        entry_id: UUID,
        actor_user_id: UUID,
        organization_id: UUID | None,
    ) -> ValueCrosswalkEntry:
        entry = db.get(ValueCrosswalkEntry, entry_id)
        if entry is None:
            _fail("CROSSWALK_ENTRY_NOT_FOUND", "Crosswalk entry was not found", 404)
        crosswalk = db.get(ValueCrosswalk, entry.crosswalk_id)
        assert crosswalk is not None
        if not _scope_visible(
            crosswalk.owner_organization_id,
            crosswalk.scope_type,
            organization_id,
        ):
            _fail("CROSSWALK_ENTRY_NOT_FOUND", "Crosswalk entry is outside scope", 404)
        entry.status = CrosswalkEntryStatus.APPROVED.value
        entry.approved_by_user_id = actor_user_id
        entry.approved_at = utc_now()
        db.commit()
        db.refresh(entry)
        return entry

    def resolve(
        self,
        db: Session,
        crosswalk_id: UUID,
        source_value: object,
        organization_id: UUID,
    ) -> ValueCrosswalkEntry | None:
        normalized = self.normalize(str(source_value))
        now = utc_now()
        return db.scalar(
            select(ValueCrosswalkEntry).where(
                ValueCrosswalkEntry.crosswalk_id == crosswalk_id,
                ValueCrosswalkEntry.normalized_source_value == normalized,
                ValueCrosswalkEntry.status == CrosswalkEntryStatus.APPROVED.value,
                (
                    (ValueCrosswalkEntry.owner_organization_id.is_(None))
                    | (ValueCrosswalkEntry.owner_organization_id == organization_id)
                ),
                (
                    (ValueCrosswalkEntry.effective_from.is_(None))
                    | (ValueCrosswalkEntry.effective_from <= now)
                ),
                (
                    (ValueCrosswalkEntry.effective_to.is_(None))
                    | (ValueCrosswalkEntry.effective_to > now)
                ),
            )
        )

    @staticmethod
    def normalize(value: str) -> str:
        return " ".join(value.strip().casefold().split())


class MappingExecutionService:
    def execute(
        self,
        db: Session,
        organization_id: UUID,
        payload: MappingRunCreate,
        actor_user_id: UUID,
    ) -> MappingRun:
        request_fingerprint = _fingerprint(payload.model_dump(mode="json"))
        existing = db.scalar(
            select(MappingRun).where(
                MappingRun.organization_id == organization_id,
                MappingRun.idempotency_key == payload.idempotency_key,
            )
        )
        if existing is not None:
            if existing.request_fingerprint != request_fingerprint:
                _fail(
                    "IDEMPOTENCY_CONFLICT",
                    "Idempotency key was reused with a different mapping request",
                    409,
                )
            return existing
        dataset_version = db.scalar(
            select(DatasetVersion).where(
                DatasetVersion.id == payload.dataset_version_id,
                DatasetVersion.organization_id == organization_id,
            )
        )
        if dataset_version is None:
            _fail("DATASET_VERSION_NOT_FOUND", "Dataset version is outside tenant scope", 404)
        source_schema = db.scalar(
            select(SourceSchema).where(
                SourceSchema.id == payload.source_schema_id,
                SourceSchema.organization_id == organization_id,
            )
        )
        if source_schema is None:
            _fail("SOURCE_SCHEMA_NOT_FOUND", "Source schema is outside tenant scope", 404)
        if source_schema.dataset_version_id != payload.dataset_version_id:
            _fail(
                "SOURCE_SCHEMA_DATASET_VERSION_MISMATCH",
                "Source schema does not belong to the selected dataset version",
                409,
            )
        if source_schema.status in {SchemaStatus.CHANGED.value, SchemaStatus.INCOMPATIBLE.value}:
            _fail(
                "SOURCE_SCHEMA_NOT_USABLE",
                "Source schema is changed or incompatible and cannot govern execution",
                409,
            )
        version = mapping_template_service.require_version(
            db,
            payload.template_version_id,
            organization_id,
        )
        if version.lifecycle_status != MappingLifecycleStatus.PUBLISHED.value:
            _fail("MAPPING_VERSION_NOT_PUBLISHED", "Only published mappings may execute", 409)
        run = MappingRun(
            organization_id=organization_id,
            dataset_version_id=payload.dataset_version_id,
            template_version_id=payload.template_version_id,
            source_schema_id=source_schema.id,
            schema_fingerprint_snapshot=source_schema.schema_fingerprint,
            status=MappingRunStatus.RUNNING.value,
            idempotency_key=payload.idempotency_key,
            request_fingerprint=request_fingerprint,
            correlation_id=payload.correlation_id,
            started_at=utc_now(),
            input_count=len(payload.records),
            mapped_count=0,
            exception_count=0,
            rejected_count=0,
            created_by_user_id=actor_user_id,
        )
        db.add(run)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            if constraint != _MAPPING_RUN_IDEMPOTENCY_CONSTRAINT:
                raise
            concurrent = db.scalar(
                select(MappingRun).where(
                    MappingRun.organization_id == organization_id,
                    MappingRun.idempotency_key == payload.idempotency_key,
                )
            )
            if concurrent is None:
                raise
            if concurrent.request_fingerprint != request_fingerprint:
                _fail(
                    "IDEMPOTENCY_CONFLICT",
                    "Idempotency key was reused with a different mapping request",
                    409,
                )
            return concurrent
        template = db.get(MappingTemplate, version.template_id)
        assert template is not None
        for record in payload.records:
            self._map_record(db, organization_id, run, template, version, record, actor_user_id)
        run.status = (
            MappingRunStatus.COMPLETED.value
            if run.exception_count == 0
            else MappingRunStatus.PARTIALLY_COMPLETED.value
        )
        run.completed_at = utc_now()
        _audit(
            db,
            organization_id,
            "mapping_run_completed",
            "mapping_run",
            run.id,
            actor_user_id,
            "Mapping run completed",
            {
                "mapped_count": run.mapped_count,
                "exception_count": run.exception_count,
            },
        )
        db.commit()
        db.refresh(run)
        if run.status == MappingRunStatus.COMPLETED.value and run.source_schema_id is not None:
            self._register_field_mapping_evidence(
                db,
                organization_id,
                run.id,
                run.source_schema_id,
                run.template_version_id,
                run.schema_fingerprint_snapshot,
            )
        return run

    def _register_field_mapping_evidence(
        self,
        db: Session,
        organization_id: UUID,
        run_id: UUID,
        source_schema_id: UUID,
        template_version_id: UUID,
        schema_fingerprint_snapshot: str | None,
    ) -> None:
        # Runs after the authoritative MappingRun commit above. A failure here must
        # never roll back or otherwise affect the already-persisted MappingRun.
        if schema_fingerprint_snapshot is None:
            return
        field_mappings = list(
            db.scalars(
                select(FieldMapping)
                .where(FieldMapping.template_version_id == template_version_id)
                .order_by(FieldMapping.sequence)
            )
        )
        for field_mapping in field_mappings:
            try:
                self._register_single_field_mapping_evidence(
                    db,
                    organization_id,
                    run_id,
                    source_schema_id,
                    template_version_id,
                    schema_fingerprint_snapshot,
                    field_mapping,
                )
            except Exception:  # noqa: BLE001
                # Evidence registration is best-effort and runs strictly after the
                # authoritative MappingRun commit; no failure here may propagate
                # and no failure here may affect the already-persisted MappingRun.
                db.rollback()
                continue

    def _register_single_field_mapping_evidence(
        self,
        db: Session,
        organization_id: UUID,
        run_id: UUID,
        source_schema_id: UUID,
        template_version_id: UUID,
        schema_fingerprint_snapshot: str,
        field_mapping: FieldMapping,
    ) -> None:
        source_field = db.scalar(
            select(SourceField).where(
                SourceField.organization_id == organization_id,
                SourceField.source_schema_id == source_schema_id,
                SourceField.field_path == field_mapping.source_field_path,
            )
        )
        if source_field is None:
            return
        canonical_field = db.get(
            CanonicalFieldDefinition, field_mapping.canonical_field_definition_id
        )
        if canonical_field is None:
            return
        transformation = db.scalar(
            select(MappingTransformation)
            .where(MappingTransformation.field_mapping_id == field_mapping.id)
            .order_by(MappingTransformation.sequence)
            .limit(1)
        )
        evidence_payload = FieldMappingPayload(
            source_field_path=field_mapping.source_field_path,
            source_field_type=source_field.inferred_data_type,
            canonical_type_kind=canonical_field.canonical_type_kind,
            canonical_type_id=canonical_field.canonical_type_id,
            canonical_field_definition_id=canonical_field.id,
            canonical_field_code=canonical_field.field_code,
            schema_fingerprint=schema_fingerprint_snapshot,
            mapping_transform_code=(
                transformation.transformation_type if transformation is not None else None
            ),
            unit_context=None,
        )
        source_fingerprint = _fingerprint(
            {
                "run_id": str(run_id),
                "field_mapping_id": str(field_mapping.id),
                "source_field_path": field_mapping.source_field_path,
                "source_field_type": source_field.inferred_data_type,
                "canonical_field_definition_id": str(canonical_field.id),
                "schema_fingerprint": schema_fingerprint_snapshot,
            }
        )
        candidate = MemoryCandidateCreate(
            idempotency_key=f"mapping-run:{run_id}:field-mapping:{field_mapping.id}",
            category="FIELD_MAPPING",
            subject_kind="SOURCE_FIELD",
            subject=field_mapping.source_field_path,
            context=MemoryContext(schema_fingerprint=schema_fingerprint_snapshot),
            value_payload=evidence_payload.model_dump(mode="json"),
            provenance=MemoryProvenance(
                source_schema_id=source_schema_id,
                mapping_template_version_id=template_version_id,
                canonical_field_definition_ids=[canonical_field.id],
            ),
            source_fingerprint=source_fingerprint,
        )
        operational_memory_service.record_candidate(
            db,
            organization_id,
            candidate,
            actor_user_id=None,
            actor_role="system",
        )

    def _map_record(
        self,
        db: Session,
        organization_id: UUID,
        run: MappingRun,
        template: MappingTemplate,
        version: MappingTemplateVersion,
        input_record: MappingInputRecord,
        actor_user_id: UUID,
    ) -> None:
        raw = db.scalar(
            select(RawRecordReference).where(
                RawRecordReference.id == input_record.raw_record_reference_id,
                RawRecordReference.organization_id == organization_id,
                RawRecordReference.dataset_version_id == run.dataset_version_id,
            )
        )
        if raw is None:
            _fail("RAW_RECORD_NOT_FOUND", "Raw record is outside tenant or dataset scope", 404)
        mappings = list(
            db.scalars(
                select(FieldMapping)
                .where(FieldMapping.template_version_id == version.id)
                .order_by(FieldMapping.sequence)
            )
        )
        output: dict[str, object] = {}
        confidence_scores: list[Decimal] = []
        missing: list[str] = []
        for field_mapping in mappings:
            field = db.get(CanonicalFieldDefinition, field_mapping.canonical_field_definition_id)
            assert field is not None
            value = input_record.values.get(field_mapping.source_field_path)
            if value is None:
                value = field_mapping.default_value
            if value is None and field_mapping.is_required_for_publication:
                missing.append(field.field_code)
                continue
            transformations = list(
                db.scalars(
                    select(MappingTransformation)
                    .where(MappingTransformation.field_mapping_id == field_mapping.id)
                    .order_by(MappingTransformation.sequence)
                )
            )
            try:
                for transformation in transformations:
                    value, confidence = self._transform(
                        db,
                        organization_id,
                        value,
                        transformation,
                        input_record.values,
                    )
                    if confidence is not None:
                        confidence_scores.append(confidence)
                self._validate_field(field, value)
            except CanonicalFieldValidationError as exc:
                self._exception_result(
                    db,
                    organization_id,
                    run,
                    raw,
                    template,
                    input_record,
                    MappingExceptionType.VALIDATION_FAILURE.value,
                    {"field": field.field_code, "error": str(exc)},
                )
                return
            except (ValueError, TypeError, KeyError) as exc:
                exception_type = (
                    MappingExceptionType.CROSSWALK_MISS.value
                    if transformation.transformation_type
                    == TransformationType.CROSSWALK_LOOKUP.value
                    else MappingExceptionType.TRANSFORMATION_FAILURE.value
                )
                self._exception_result(
                    db,
                    organization_id,
                    run,
                    raw,
                    template,
                    input_record,
                    exception_type,
                    {
                        "field": field.field_code,
                        "transformation_type": transformation.transformation_type,
                        "error": str(exc),
                    },
                )
                return
            output[field.field_code] = value
        if missing:
            self._exception_result(
                db,
                organization_id,
                run,
                raw,
                template,
                input_record,
                MappingExceptionType.MISSING_REQUIRED_FIELD.value,
                {"fields": missing},
            )
            return
        confidence = min(confidence_scores, default=Decimal("1"))
        target, record_status, match_candidates = self._materialize_target(
            db,
            organization_id,
            template,
            output,
            confidence,
            input_record.source_reported_timestamp,
        )
        result = MappingRecordResult(
            organization_id=organization_id,
            mapping_run_id=run.id,
            raw_record_reference_id=raw.id,
            status=record_status,
            canonical_target_kind=template.target_canonical_type_kind,
            canonical_target_id=target.id,
            mapping_confidence_score=confidence,
            confidence_method_code="minimum_supporting_input",
            confidence_method_version="1.0",
            confidence_components={
                "supporting_scores": [str(score) for score in confidence_scores]
            },
            confidence_interpretation="Minimum confidence across supporting mapping decisions.",
            confidence_limitations="Rule-based confidence; no learned calibration.",
            source_reported_timestamp=input_record.source_reported_timestamp,
            content_hash=_fingerprint(output),
            result_json=output,
        )
        db.add(result)
        db.flush()
        link = SourceCanonicalLink(
            organization_id=organization_id,
            raw_record_reference_id=raw.id,
            canonical_target_kind=template.target_canonical_type_kind,
            canonical_target_id=target.id,
            mapping_run_id=run.id,
            template_version_id=version.id,
            is_primary=True,
            mapping_confidence_score=confidence,
            confidence_method_code="minimum_supporting_input",
            confidence_method_version="1.0",
            confidence_components={"mapping_record_result_id": str(result.id)},
            confidence_interpretation="Primary deterministic source-to-canonical link.",
            confidence_limitations="Limited to the configured mapping template.",
        )
        link.is_primary = record_status == MappingRecordStatus.MAPPED.value
        db.add(link)
        db.flush()
        for rule, candidate_entity, match_score in match_candidates:
            db.add(
                EntityMatchCandidate(
                    organization_id=organization_id,
                    source_canonical_link_id=link.id,
                    candidate_entity_id=candidate_entity.id,
                    match_rule_id=rule.id,
                    match_score=match_score,
                    status=MatchCandidateStatus.CANDIDATE.value,
                )
            )
        if (
            record_status == MappingRecordStatus.MAPPED.value
            and isinstance(target, CanonicalEntity)
            and target.survivorship_source_link_id is None
        ):
            target.survivorship_source_link_id = link.id
        self._register_lineage(db, organization_id, raw, run, result, target, confidence)
        if record_status == MappingRecordStatus.AMBIGUOUS.value:
            self._add_exception(
                db,
                organization_id,
                result,
                MappingExceptionType.AMBIGUOUS_ENTITY.value,
                {"candidate_count": len(match_candidates)},
            )
            run.exception_count += 1
            run.rejected_count += 1
        elif record_status == MappingRecordStatus.CONFLICTING.value:
            self._add_exception(
                db,
                organization_id,
                result,
                MappingExceptionType.CONFLICTING_MAPPING.value,
                {"canonical_target_id": str(target.id)},
            )
            run.exception_count += 1
            run.rejected_count += 1
        else:
            run.mapped_count += 1
        _audit(
            db,
            organization_id,
            "record_mapped",
            template.target_canonical_type_kind,
            target.id,
            actor_user_id,
            "Raw record mapped to canonical target",
            {"raw_record_reference_id": str(raw.id), "mapping_run_id": str(run.id)},
        )

    def _exception_result(
        self,
        db: Session,
        organization_id: UUID,
        run: MappingRun,
        raw: RawRecordReference,
        template: MappingTemplate,
        input_record: MappingInputRecord,
        exception_type: str,
        detail: dict[str, object],
    ) -> None:
        status = (
            MappingRecordStatus.MISSING_REQUIRED_FIELD.value
            if exception_type == MappingExceptionType.MISSING_REQUIRED_FIELD.value
            else MappingRecordStatus.UNRESOLVED.value
        )
        result = MappingRecordResult(
            organization_id=organization_id,
            mapping_run_id=run.id,
            raw_record_reference_id=raw.id,
            status=status,
            canonical_target_kind=template.target_canonical_type_kind,
            canonical_target_id=None,
            mapping_confidence_score=None,
            confidence_method_code=None,
            confidence_method_version=None,
            confidence_components=None,
            confidence_interpretation=None,
            confidence_limitations="Mapping did not produce a canonical target.",
            source_reported_timestamp=input_record.source_reported_timestamp,
            content_hash=_fingerprint({"input": input_record.values, "detail": detail}),
            result_json={},
        )
        db.add(result)
        db.flush()
        db.add(
            MappingException(
                organization_id=organization_id,
                mapping_record_result_id=result.id,
                exception_type=exception_type,
                status=MappingExceptionStatus.OPEN.value,
                detail_json=detail,
            )
        )
        run.exception_count += 1
        run.rejected_count += 1

    @staticmethod
    def _add_exception(
        db: Session,
        organization_id: UUID,
        result: MappingRecordResult,
        exception_type: str,
        detail: dict[str, object],
    ) -> None:
        db.add(
            MappingException(
                organization_id=organization_id,
                mapping_record_result_id=result.id,
                exception_type=exception_type,
                status=MappingExceptionStatus.OPEN.value,
                detail_json=detail,
            )
        )

    def _transform(
        self,
        db: Session,
        organization_id: UUID,
        value: object,
        transformation: MappingTransformation,
        record_values: dict[str, object] | None = None,
    ) -> tuple[object, Decimal | None]:
        kind = transformation.transformation_type
        params = transformation.parameters_json
        if kind == TransformationType.TRIM_NORMALIZE.value:
            return " ".join(str(value).strip().split()), Decimal("1")
        if kind == TransformationType.TYPE_CAST.value:
            target = str(params.get("target_type"))
            casts: dict[str, Any] = {
                "string": str,
                "integer": int,
                "decimal": Decimal,
                "boolean": self._as_bool,
            }
            if target not in casts:
                raise ValueError(f"Unsupported target type: {target}")
            return casts[target](value), Decimal("1")
        if kind == TransformationType.DATE_PARSE.value:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")), Decimal("1")
        if kind == TransformationType.TIMEZONE_NORMALIZE.value:
            parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
            source_zone = ZoneInfo(str(params["source_timezone"]))
            localized = parsed.replace(tzinfo=source_zone) if parsed.tzinfo is None else parsed
            return localized.astimezone(UTC), Decimal("1")
        if kind == TransformationType.UNIT_CONVERT.value:
            factor = Decimal(str(params["factor"]))
            return Decimal(str(value)) * factor, Decimal("1")
        if kind == TransformationType.CURRENCY_NORMALIZE.value:
            code = str(value).strip().upper()
            if len(code) != 3 or not code.isalpha():
                raise ValueError("Currency must be an ISO-style three-letter code")
            return code, Decimal("1")
        if kind == TransformationType.CROSSWALK_LOOKUP.value:
            entry = value_crosswalk_service.resolve(
                db,
                UUID(str(params["crosswalk_id"])),
                value,
                organization_id,
            )
            if entry is None:
                raise ValueError("No approved crosswalk entry")
            return (
                entry.canonical_target_value,
                entry.mapping_confidence_score or Decimal("1"),
            )
        if kind == TransformationType.DERIVE.value:
            template = str(params["format"])
            context = dict(record_values or {})
            context["value"] = value
            return template.format(**context), Decimal("1")
        if kind == TransformationType.CONSTANT.value:
            return params.get("value"), Decimal("1")
        if kind == TransformationType.CUSTOM_FUNCTION.value:
            raise ValueError("Custom functions require a separately governed implementation")
        return value, Decimal("1")

    @staticmethod
    def _validate_field(field: CanonicalFieldDefinition, value: object) -> None:
        if value is None:
            return
        if field.allowed_values is not None and value not in field.allowed_values:
            raise CanonicalFieldValidationError("Value is outside the governed allowed set")
        rule = field.validation_rule or {}
        try:
            if "minimum" in rule and Decimal(str(value)) < Decimal(str(rule["minimum"])):
                raise CanonicalFieldValidationError("Value is below the governed minimum")
            if "maximum" in rule and Decimal(str(value)) > Decimal(str(rule["maximum"])):
                raise CanonicalFieldValidationError("Value exceeds the governed maximum")
        except CanonicalFieldValidationError:
            raise
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise CanonicalFieldValidationError(
                "Value cannot be evaluated against the governed numeric range"
            ) from exc
        if "min_length" in rule and len(str(value)) < int(str(rule["min_length"])):
            raise CanonicalFieldValidationError("Value is shorter than the governed minimum")
        if "max_length" in rule and len(str(value)) > int(str(rule["max_length"])):
            raise CanonicalFieldValidationError("Value exceeds the governed maximum length")
        if "pattern" in rule and re.fullmatch(str(rule["pattern"]), str(value)) is None:
            raise CanonicalFieldValidationError("Value does not match the governed pattern")

    @staticmethod
    def _as_bool(value: object) -> bool:
        if isinstance(value, bool):
            return value
        normalized = str(value).strip().casefold()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
        raise ValueError("Value cannot be converted to boolean")

    def _materialize_target(
        self,
        db: Session,
        organization_id: UUID,
        template: MappingTemplate,
        output: dict[str, object],
        confidence: Decimal,
        source_timestamp: datetime | None,
    ) -> tuple[
        CanonicalEntity | CanonicalEvent | CanonicalMetric,
        str,
        list[tuple[EntityMatchRule, CanonicalEntity, Decimal]],
    ]:
        fingerprint = _fingerprint(
            {
                "kind": template.target_canonical_type_kind,
                "type_id": str(template.target_canonical_type_id),
                "output": output,
            }
        )
        common = {
            "organization_id": organization_id,
            "mapping_confidence_score": confidence,
            "confidence_method_code": "minimum_supporting_input",
            "confidence_method_version": "1.0",
            "confidence_components": {"record_fingerprint": fingerprint},
            "confidence_interpretation": "Deterministic mapping confidence.",
            "confidence_limitations": "Dependent on configured field mappings.",
        }
        if template.target_canonical_type_kind == CanonicalTypeKind.ENTITY.value:
            existing = db.scalar(
                select(CanonicalEntity).where(
                    CanonicalEntity.organization_id == organization_id,
                    CanonicalEntity.content_fingerprint == fingerprint,
                )
            )
            if existing is not None:
                return existing, MappingRecordStatus.MAPPED.value, []
            deterministic, conflict, candidates = entity_resolution_service.resolve(
                db,
                organization_id,
                template.target_canonical_type_id,
                output,
            )
            if deterministic is not None:
                return (
                    deterministic,
                    (
                        MappingRecordStatus.CONFLICTING.value
                        if conflict
                        else MappingRecordStatus.MAPPED.value
                    ),
                    [],
                )
            target: CanonicalEntity | CanonicalEvent | CanonicalMetric = CanonicalEntity(
                **common,
                entity_type_id=template.target_canonical_type_id,
                canonical_entity_key=(
                    str(output["canonical_entity_key"])
                    if output.get("canonical_entity_key") is not None
                    else None
                ),
                attributes_json=output,
                survivorship_source_link_id=None,
                content_fingerprint=fingerprint,
            )
        elif template.target_canonical_type_kind == CanonicalTypeKind.EVENT.value:
            entity_id = UUID(str(output["canonical_entity_id"]))
            occurrence = self._as_datetime(output["occurrence_start"])
            target = CanonicalEvent(
                **common,
                canonical_entity_id=entity_id,
                event_type_id=template.target_canonical_type_id,
                occurrence_start=occurrence,
                occurrence_end=self._optional_datetime(output.get("occurrence_end")),
                occurrence_precision=str(
                    output.get("occurrence_precision", OccurrencePrecision.INSTANT.value)
                ),
                source_reported_timestamp=source_timestamp,
                first_detected_at=utc_now(),
                last_detected_at=utc_now(),
                actor_reference=(
                    str(output["actor_reference"])
                    if output.get("actor_reference") is not None
                    else None
                ),
                mapping_status=MappingRecordStatus.MAPPED.value,
                attributes_json=output,
                content_fingerprint=fingerprint,
            )
        else:
            entity_id = UUID(str(output["canonical_entity_id"]))
            occurrence = self._as_datetime(output["occurrence_start"])
            target = CanonicalMetric(
                **common,
                canonical_entity_id=entity_id,
                metric_type_id=template.target_canonical_type_id,
                measured_value=Decimal(str(output["measured_value"])),
                unit=str(output["unit"]),
                currency=(
                    str(output["currency"]).upper() if output.get("currency") is not None else None
                ),
                occurrence_start=occurrence,
                occurrence_end=self._optional_datetime(output.get("occurrence_end")),
                occurrence_precision=str(
                    output.get("occurrence_precision", OccurrencePrecision.INSTANT.value)
                ),
                source_reported_timestamp=source_timestamp,
                first_detected_at=utc_now(),
                last_detected_at=utc_now(),
                mapping_status=MappingRecordStatus.MAPPED.value,
                attributes_json=output,
                content_fingerprint=fingerprint,
            )
        db.add(target)
        db.flush()
        if isinstance(target, CanonicalEntity) and candidates:
            return target, MappingRecordStatus.AMBIGUOUS.value, candidates
        return target, MappingRecordStatus.MAPPED.value, []

    @staticmethod
    def _as_datetime(value: object) -> datetime:
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    def _optional_datetime(self, value: object | None) -> datetime | None:
        return None if value is None else self._as_datetime(value)

    def _register_lineage(
        self,
        db: Session,
        organization_id: UUID,
        raw: RawRecordReference,
        run: MappingRun,
        result: MappingRecordResult,
        target: CanonicalEntity | CanonicalEvent | CanonicalMetric,
        confidence: Decimal,
    ) -> None:
        raw_node = self._node(
            db,
            organization_id,
            LineageNodeType.RAW_RECORD_REFERENCE.value,
            raw.id,
            "Raw record",
        )
        run_node = self._node(
            db,
            organization_id,
            LineageNodeType.MAPPING_RUN.value,
            run.id,
            "Mapping run",
        )
        result_node = self._node(
            db,
            organization_id,
            LineageNodeType.MAPPING_RECORD_RESULT.value,
            result.id,
            "Mapping record result",
        )
        target_kind = {
            CanonicalEntity: LineageNodeType.CANONICAL_ENTITY.value,
            CanonicalEvent: LineageNodeType.CANONICAL_EVENT.value,
            CanonicalMetric: LineageNodeType.CANONICAL_METRIC.value,
        }[type(target)]
        target_node = self._node(
            db,
            organization_id,
            target_kind,
            target.id,
            "Canonical target",
        )
        for from_node, to_node, relationship in (
            (raw_node, run_node, LineageRelationshipType.CONSUMED_BY.value),
            (raw_node, result_node, LineageRelationshipType.MAPPED_BY.value),
            (result_node, target_node, LineageRelationshipType.CANONICALIZED_AS.value),
        ):
            db.add(
                LineageEdge(
                    organization_id=organization_id,
                    from_node_id=from_node.id,
                    to_node_id=to_node.id,
                    relationship_type=relationship,
                    processing_run_id=None,
                    processing_run_key=str(run.id),
                    sequence=0,
                    confidence=float(confidence),
                    is_primary=True,
                    effective_at=utc_now(),
                    metadata_json={"mapping_run_id": str(run.id)},
                    created_by_user_id=run.created_by_user_id,
                )
            )

    @staticmethod
    def _node(
        db: Session,
        organization_id: UUID,
        node_type: str,
        entity_id: UUID,
        display_name: str,
    ) -> LineageNode:
        existing = db.scalar(
            select(LineageNode).where(
                LineageNode.organization_id == organization_id,
                LineageNode.node_type == node_type,
                LineageNode.entity_id == entity_id,
            )
        )
        if existing is not None:
            return existing
        node = LineageNode(
            organization_id=organization_id,
            node_type=node_type,
            entity_id=entity_id,
            entity_reference=str(entity_id),
            display_name=display_name,
            status=LineageNodeStatus.ACTIVE.value,
            metadata_json={},
        )
        db.add(node)
        db.flush()
        return node

    def get(
        self,
        db: Session,
        organization_id: UUID,
        mapping_run_id: UUID,
    ) -> MappingRun:
        run = db.scalar(
            select(MappingRun).where(
                MappingRun.id == mapping_run_id,
                MappingRun.organization_id == organization_id,
            )
        )
        if run is None:
            _fail("MAPPING_RUN_NOT_FOUND", "Mapping run is outside tenant scope", 404)
        return run

    def exceptions(
        self,
        db: Session,
        organization_id: UUID,
        mapping_run_id: UUID,
    ) -> list[MappingException]:
        self.get(db, organization_id, mapping_run_id)
        return list(
            db.scalars(
                select(MappingException)
                .join(
                    MappingRecordResult,
                    MappingRecordResult.id == MappingException.mapping_record_result_id,
                )
                .where(
                    MappingException.organization_id == organization_id,
                    MappingRecordResult.mapping_run_id == mapping_run_id,
                )
            )
        )


class MappingReviewService:
    def review_exception(
        self,
        db: Session,
        organization_id: UUID,
        exception_id: UUID,
        payload: MappingReviewCreate,
        actor_user_id: UUID,
    ) -> MappingReview:
        exception = db.scalar(
            select(MappingException).where(
                MappingException.id == exception_id,
                MappingException.organization_id == organization_id,
            )
        )
        if exception is None:
            _fail("MAPPING_EXCEPTION_NOT_FOUND", "Exception is outside tenant scope", 404)
        if exception.status not in {
            MappingExceptionStatus.OPEN.value,
            MappingExceptionStatus.UNDER_REVIEW.value,
        }:
            _fail("MAPPING_EXCEPTION_FINAL", "Exception already has a final decision", 409)
        review = MappingReview(
            organization_id=organization_id,
            mapping_exception_id=exception.id,
            decision=payload.decision,
            reviewer_user_id=actor_user_id,
            reviewed_at=utc_now(),
            notes=payload.notes,
            override_value=payload.override_value,
        )
        if payload.decision in {"confirm", "override"}:
            exception.status = MappingExceptionStatus.RESOLVED.value
        elif payload.decision == "reject":
            exception.status = MappingExceptionStatus.WONT_FIX.value
        else:
            exception.status = MappingExceptionStatus.UNDER_REVIEW.value
        db.add(review)
        db.commit()
        db.refresh(review)
        return review

    def decide_candidate(
        self,
        db: Session,
        organization_id: UUID,
        candidate_id: UUID,
        payload: EntityMatchDecision,
        actor_user_id: UUID,
    ) -> EntityMatchCandidate:
        candidate = db.scalar(
            select(EntityMatchCandidate).where(
                EntityMatchCandidate.id == candidate_id,
                EntityMatchCandidate.organization_id == organization_id,
            )
        )
        if candidate is None:
            _fail("MATCH_CANDIDATE_NOT_FOUND", "Candidate is outside tenant scope", 404)
        if candidate.status != MatchCandidateStatus.CANDIDATE.value:
            _fail("MATCH_CANDIDATE_FINAL", "Candidate already has a final decision", 409)
        candidate.status = payload.decision
        candidate.decided_by_user_id = actor_user_id
        candidate.decided_at = utc_now()
        if payload.decision == MatchCandidateStatus.ACCEPTED.value:
            source_link = db.scalar(
                select(SourceCanonicalLink).where(
                    SourceCanonicalLink.id == candidate.source_canonical_link_id,
                    SourceCanonicalLink.organization_id == organization_id,
                )
            )
            assert source_link is not None
            source_link.canonical_target_id = candidate.candidate_entity_id
            source_link.is_primary = True
            source_link.mapping_confidence_score = candidate.match_score
            source_link.confidence_method_code = "human_entity_match_review"
            source_link.confidence_method_version = "1.0"
            source_link.confidence_interpretation = (
                "Entity match accepted by an authorized reviewer."
            )
            result = db.scalar(
                select(MappingRecordResult).where(
                    MappingRecordResult.organization_id == organization_id,
                    MappingRecordResult.mapping_run_id == source_link.mapping_run_id,
                    MappingRecordResult.raw_record_reference_id
                    == source_link.raw_record_reference_id,
                    MappingRecordResult.canonical_target_kind == CanonicalTypeKind.ENTITY.value,
                )
            )
            assert result is not None
            result.canonical_target_id = candidate.candidate_entity_id
            result.status = MappingRecordStatus.HUMAN_CONFIRMED.value
            result.mapping_confidence_score = candidate.match_score
            result.confidence_method_code = "human_entity_match_review"
            result.confidence_method_version = "1.0"
            result.confidence_interpretation = "Entity match accepted by an authorized reviewer."
            entity = db.get(CanonicalEntity, candidate.candidate_entity_id)
            assert entity is not None
            if entity.survivorship_source_link_id is None:
                entity.survivorship_source_link_id = source_link.id
            for sibling in db.scalars(
                select(EntityMatchCandidate).where(
                    EntityMatchCandidate.organization_id == organization_id,
                    EntityMatchCandidate.source_canonical_link_id == source_link.id,
                    EntityMatchCandidate.id != candidate.id,
                    EntityMatchCandidate.status == MatchCandidateStatus.CANDIDATE.value,
                )
            ):
                sibling.status = MatchCandidateStatus.SUPERSEDED.value
                sibling.decided_by_user_id = actor_user_id
                sibling.decided_at = candidate.decided_at
            exception = db.scalar(
                select(MappingException).where(
                    MappingException.organization_id == organization_id,
                    MappingException.mapping_record_result_id == result.id,
                    MappingException.exception_type == MappingExceptionType.AMBIGUOUS_ENTITY.value,
                )
            )
            if exception is not None:
                exception.status = MappingExceptionStatus.RESOLVED.value
                exception.resolution_summary = "Accepted governed entity-match candidate."
            _audit(
                db,
                organization_id,
                "entity_match_accepted",
                "canonical_entity",
                candidate.candidate_entity_id,
                actor_user_id,
                "Entity match candidate accepted",
                {
                    "candidate_id": str(candidate.id),
                    "source_canonical_link_id": str(source_link.id),
                },
            )
        db.commit()
        db.refresh(candidate)
        return candidate


class EntityResolutionService:
    max_candidates = 20

    def resolve(
        self,
        db: Session,
        organization_id: UUID,
        entity_type_id: UUID,
        attributes: dict[str, object],
    ) -> tuple[
        CanonicalEntity | None,
        bool,
        list[tuple[EntityMatchRule, CanonicalEntity, Decimal]],
    ]:
        rules = list(
            db.scalars(
                select(EntityMatchRule)
                .where(EntityMatchRule.entity_type_id == entity_type_id)
                .order_by(EntityMatchRule.rule_code)
            )
        )
        entities = list(
            db.scalars(
                select(CanonicalEntity).where(
                    CanonicalEntity.organization_id == organization_id,
                    CanonicalEntity.entity_type_id == entity_type_id,
                )
            )
        )
        fuzzy_candidates: list[tuple[EntityMatchRule, CanonicalEntity, Decimal]] = []
        for rule in rules:
            if rule.match_method == "fuzzy_candidate":
                threshold = Decimal(str(rule.normalization_json.get("candidate_threshold", "0.75")))
                for entity in entities:
                    score = self._fuzzy_score(rule.match_fields, attributes, entity)
                    if score >= threshold:
                        fuzzy_candidates.append((rule, entity, score))
                continue
            matches = [
                entity
                for entity in entities
                if self._deterministic_match(
                    rule.match_method,
                    rule.match_fields,
                    attributes,
                    entity,
                )
            ]
            if matches:
                entity = matches[0]
                conflicts = len(matches) > 1 or _stable_json(
                    entity.attributes_json
                ) != _stable_json(attributes)
                return entity, conflicts, []
        fuzzy_candidates.sort(key=lambda item: item[2], reverse=True)
        return None, False, fuzzy_candidates[: self.max_candidates]

    @staticmethod
    def _entity_value(entity: CanonicalEntity, field: str) -> object | None:
        if field == "canonical_entity_key":
            return entity.canonical_entity_key
        return entity.attributes_json.get(field)

    @staticmethod
    def _normalized(value: object) -> str:
        return " ".join(str(value).strip().casefold().split())

    def _deterministic_match(
        self,
        method: str,
        fields: list[str],
        attributes: dict[str, object],
        entity: CanonicalEntity,
    ) -> bool:
        if not fields:
            return False
        pairs = [(attributes.get(field), self._entity_value(entity, field)) for field in fields]
        if any(left is None or right is None for left, right in pairs):
            return False
        if method == "exact_identifier":
            return all(str(left) == str(right) for left, right in pairs)
        if method in {"normalized_identifier", "deterministic_composite"}:
            return all(self._normalized(left) == self._normalized(right) for left, right in pairs)
        return False

    def _fuzzy_score(
        self,
        fields: list[str],
        attributes: dict[str, object],
        entity: CanonicalEntity,
    ) -> Decimal:
        left = "|".join(
            self._normalized(attributes[field]) for field in fields if field in attributes
        )
        right = "|".join(
            self._normalized(value)
            for field in fields
            if (value := self._entity_value(entity, field)) is not None
        )
        if not left or not right:
            return Decimal(0)
        return Decimal(str(SequenceMatcher(None, left, right).ratio())).quantize(Decimal("0.0001"))

    def candidates(
        self,
        db: Session,
        organization_id: UUID,
    ) -> list[EntityMatchCandidate]:
        return list(
            db.scalars(
                select(EntityMatchCandidate).where(
                    EntityMatchCandidate.organization_id == organization_id
                )
            )
        )


class CanonicalRecordService:
    def entity(
        self,
        db: Session,
        organization_id: UUID,
        entity_id: UUID,
    ) -> CanonicalEntity:
        record = db.scalar(
            select(CanonicalEntity).where(
                CanonicalEntity.id == entity_id,
                CanonicalEntity.organization_id == organization_id,
            )
        )
        if record is None:
            _fail("CANONICAL_ENTITY_NOT_FOUND", "Canonical entity is outside tenant scope", 404)
        return record

    def events(self, db: Session, organization_id: UUID) -> list[CanonicalEvent]:
        return list(
            db.scalars(
                select(CanonicalEvent)
                .where(CanonicalEvent.organization_id == organization_id)
                .order_by(CanonicalEvent.occurrence_start)
            )
        )

    def metrics(self, db: Session, organization_id: UUID) -> list[CanonicalMetric]:
        return list(
            db.scalars(
                select(CanonicalMetric)
                .where(CanonicalMetric.organization_id == organization_id)
                .order_by(CanonicalMetric.occurrence_start)
            )
        )

    def lineage(
        self,
        db: Session,
        organization_id: UUID,
        target_id: UUID,
    ) -> tuple[list[UUID], list[str]]:
        target = db.scalar(
            select(LineageNode).where(
                LineageNode.organization_id == organization_id,
                LineageNode.entity_id == target_id,
                LineageNode.node_type.in_(
                    (
                        LineageNodeType.CANONICAL_ENTITY.value,
                        LineageNodeType.CANONICAL_EVENT.value,
                        LineageNodeType.CANONICAL_METRIC.value,
                    )
                ),
            )
        )
        if target is None:
            _fail("LINEAGE_NOT_FOUND", "Canonical lineage is outside tenant scope", 404)
        edges = list(
            db.scalars(
                select(LineageEdge).where(
                    LineageEdge.organization_id == organization_id,
                    LineageEdge.to_node_id == target.id,
                )
            )
        )
        return [edge.from_node_id for edge in edges] + [target.id], [
            edge.relationship_type for edge in edges
        ]


class MappingSuggestionService:
    def suggest(
        self,
        db: Session,
        organization_id: UUID,
        source_schema_id: UUID,
    ) -> list[dict[str, object]]:
        fields = list(
            db.scalars(
                select(SourceField).where(
                    SourceField.organization_id == organization_id,
                    SourceField.source_schema_id == source_schema_id,
                )
            )
        )
        visible_type_ids = {
            record.id
            for kind in CanonicalTypeKind
            for record in canonical_registry_service.list_types(
                db,
                kind.value,
                organization_id,
            )
        }
        canonical_fields = list(
            db.scalars(
                select(CanonicalFieldDefinition).where(
                    CanonicalFieldDefinition.canonical_type_id.in_(visible_type_ids)
                )
            )
        )
        by_code = {field.field_code.casefold(): field for field in canonical_fields}
        return [
            {
                "source_field_id": field.id,
                "source_field_path": field.field_path,
                "canonical_field_definition_id": by_code[field.field_path.casefold()].id,
                "confidence": Decimal("0.95"),
            }
            for field in fields
            if field.field_path.casefold() in by_code
        ]


class MappingTrustSignalService:
    blocking_statuses = {
        MappingRecordStatus.UNRESOLVED.value,
        MappingRecordStatus.AMBIGUOUS.value,
        MappingRecordStatus.CONFLICTING.value,
        MappingRecordStatus.MISSING_REQUIRED_FIELD.value,
    }

    def signals(
        self,
        db: Session,
        organization_id: UUID,
        mapping_run_id: UUID,
    ) -> dict[str, object]:
        run = mapping_execution_service.get(db, organization_id, mapping_run_id)
        results = list(
            db.scalars(
                select(MappingRecordResult).where(
                    MappingRecordResult.organization_id == organization_id,
                    MappingRecordResult.mapping_run_id == run.id,
                )
            )
        )
        blocking = sum(item.status in self.blocking_statuses for item in results)
        effective_mapped = sum(
            item.status
            in {
                MappingRecordStatus.MAPPED.value,
                MappingRecordStatus.HUMAN_CONFIRMED.value,
            }
            for item in results
        )
        completeness = (
            Decimal(effective_mapped) / Decimal(run.input_count) if run.input_count else Decimal(0)
        )
        confidence = sorted(
            item.mapping_confidence_score
            for item in results
            if item.mapping_confidence_score is not None
        )
        exceptions = list(
            db.scalars(
                select(MappingException)
                .join(
                    MappingRecordResult,
                    MappingRecordResult.id == MappingException.mapping_record_result_id,
                )
                .where(
                    MappingException.organization_id == organization_id,
                    MappingRecordResult.mapping_run_id == run.id,
                )
            )
        )
        source_links = list(
            db.scalars(
                select(SourceCanonicalLink).where(
                    SourceCanonicalLink.organization_id == organization_id,
                    SourceCanonicalLink.mapping_run_id == run.id,
                )
            )
        )
        result_count = len(results)
        linked_targets = {
            (
                item.raw_record_reference_id,
                item.canonical_target_kind,
                item.canonical_target_id,
            )
            for item in source_links
        }
        linked_result_count = sum(
            (
                item.raw_record_reference_id,
                item.canonical_target_kind,
                item.canonical_target_id,
            )
            in linked_targets
            for item in results
            if item.canonical_target_id is not None
        )
        status_counts = {
            status: sum(item.status == status for item in results)
            for status in self.blocking_statuses
        }
        normalization_types = {
            TransformationType.UNIT_CONVERT.value,
            TransformationType.CURRENCY_NORMALIZE.value,
            TransformationType.TIMEZONE_NORMALIZE.value,
        }
        return {
            "mapping_completeness": completeness,
            "blocking_record_count": blocking,
            "trust_ready": blocking == 0
            and run.status
            in {
                MappingRunStatus.COMPLETED.value,
                MappingRunStatus.PARTIALLY_COMPLETED.value,
            },
            "minimum_mapping_confidence": confidence[0] if confidence else None,
            "mapping_confidence_p10": self._percentile(confidence, Decimal("0.10")),
            "mapping_confidence_p50": self._percentile(confidence, Decimal("0.50")),
            "mapping_confidence_p90": self._percentile(confidence, Decimal("0.90")),
            "unresolved_ratio": (
                Decimal(status_counts[MappingRecordStatus.UNRESOLVED.value]) / Decimal(result_count)
                if result_count
                else Decimal(0)
            ),
            "ambiguous_ratio": (
                Decimal(status_counts[MappingRecordStatus.AMBIGUOUS.value]) / Decimal(result_count)
                if result_count
                else Decimal(0)
            ),
            "missing_required_field_count": status_counts[
                MappingRecordStatus.MISSING_REQUIRED_FIELD.value
            ],
            "conflicting_mapping_count": status_counts[MappingRecordStatus.CONFLICTING.value],
            "transformation_failure_count": sum(
                item.exception_type == MappingExceptionType.TRANSFORMATION_FAILURE.value
                for item in exceptions
            ),
            "normalization_failure_count": sum(
                item.exception_type == MappingExceptionType.TRANSFORMATION_FAILURE.value
                and item.detail_json.get("transformation_type") in normalization_types
                for item in exceptions
            ),
            "lineage_completeness_ratio": (
                Decimal(linked_result_count) / Decimal(result_count) if result_count else Decimal(0)
            ),
        }

    @staticmethod
    def _percentile(values: list[Decimal], percentile: Decimal) -> Decimal | None:
        if not values:
            return None
        position = Decimal(len(values) - 1) * percentile
        lower = int(position)
        upper = min(lower + 1, len(values) - 1)
        fraction = position - Decimal(lower)
        return values[lower] + (values[upper] - values[lower]) * fraction


canonical_registry_service = CanonicalRegistryService()
schema_discovery_service = SchemaDiscoveryService()
mapping_template_service = MappingTemplateService()
value_crosswalk_service = ValueCrosswalkService()
mapping_execution_service = MappingExecutionService()
mapping_review_service = MappingReviewService()
entity_resolution_service = EntityResolutionService()
canonical_record_service = CanonicalRecordService()
mapping_suggestion_service = MappingSuggestionService()
mapping_trust_signal_service = MappingTrustSignalService()
