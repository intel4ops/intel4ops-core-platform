from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.canonical_mapping import (
    FieldMapping,
    MappingTemplate,
    MappingTemplateVersion,
    SourceField,
    SourceSchema,
)
from app.models.entities import Organization, utc_now
from app.models.ingestion import Dataset
from app.models.operational_memory import (
    OperationalMemoryItem,
    OperationalMemoryReuseEvent,
    OperationalMemoryVersion,
)
from app.models.source_system import SourceSystem
from app.schemas.memory_effectiveness import (
    MemoryEffectivenessAudit,
    MemoryEffectivenessCoverage,
    MemoryEffectivenessQuality,
    MemoryEffectivenessRead,
    MemoryEffectivenessReuse,
    MemoryEffectivenessScope,
    MemoryEffectivenessTrendPoint,
)
from app.schemas.operational_memory import MemoryContext
from app.services.operational_memory_service import (
    OperationalMemoryServiceError,
    context_signature,
    normalize_subject,
)

# Mirrors OperationalMemoryService._REUSABLE: the two governed statuses D-A
# treats as eligible for suggestion/reuse. Duplicated as a public tuple here
# rather than importing the private constant, since this is a stable,
# documented governance contract (see MEMORY_STATUSES / D-A docs), not an
# implementation detail.
_REUSABLE_STATUSES = ("CONFIRMED", "CORRECTED")


class MemoryEffectivenessService:
    """Deterministic, read-only Operational Memory / Canonical Mapping metrics.

    Every method here only SELECTs. Nothing is inserted, updated, or deleted;
    no memory status, support_count, confirmation_count, or mapping data is
    ever touched. Metrics are computed on demand against current governed
    state, never materialized or cached.
    """

    def report(
        self,
        db: Session,
        organization_id: UUID,
        *,
        source_schema_id: UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> MemoryEffectivenessRead:
        organization = db.get(Organization, organization_id)
        industry = organization.industry if organization is not None else None
        now = utc_now()

        eligible = self._eligible_signatures(db, organization_id, now)

        trend, in_scope_schemas = self._trend(
            db,
            organization_id,
            eligible,
            industry,
            source_schema_id=source_schema_id,
            date_from=date_from,
            date_to=date_to,
        )
        source_field_count = sum(point.field_count for point in trend)
        covered_field_count = sum(point.covered_field_count for point in trend)
        coverage_pct = (
            None
            if not in_scope_schemas or source_field_count == 0
            else covered_field_count / source_field_count * 100
        )
        no_match_pct = None if coverage_pct is None else 100 - coverage_pct

        (
            field_mapping_count,
            memory_derived_mapping_count,
            unchanged_count,
            modified_count,
            unresolved_count,
        ) = self._reuse_counts(db, organization_id, date_from=date_from, date_to=date_to)
        reuse_rate_pct = (
            None
            if field_mapping_count == 0
            else memory_derived_mapping_count / field_mapping_count * 100
        )
        resolved_reused_count = memory_derived_mapping_count - unresolved_count
        unchanged_pct = (
            None if resolved_reused_count == 0 else unchanged_count / resolved_reused_count * 100
        )
        modified_pct = (
            None if resolved_reused_count == 0 else modified_count / resolved_reused_count * 100
        )

        (
            memory_item_count,
            contradiction_item_count,
            stale_memory_count,
            stale_reason_breakdown,
        ) = self._quality_counts(db, organization_id, date_from=date_from, date_to=date_to)
        contradiction_rate_pct = (
            None if memory_item_count == 0 else contradiction_item_count / memory_item_count * 100
        )
        stale_rate_pct = (
            None if memory_item_count == 0 else stale_memory_count / memory_item_count * 100
        )

        retrieved_event_count, no_match_event_count = self._audit_counts(
            db, organization_id, date_from=date_from, date_to=date_to
        )

        return MemoryEffectivenessRead(
            organization_id=organization_id,
            generated_at=now,
            scope=MemoryEffectivenessScope(
                source_schema_id=source_schema_id,
                date_from=date_from,
                date_to=date_to,
            ),
            coverage=MemoryEffectivenessCoverage(
                source_field_count=source_field_count,
                covered_field_count=covered_field_count,
                exact_context_coverage_pct=coverage_pct,
                no_match_rate_pct=no_match_pct,
            ),
            reuse=MemoryEffectivenessReuse(
                field_mapping_count=field_mapping_count,
                memory_derived_mapping_count=memory_derived_mapping_count,
                memory_reuse_rate_pct=reuse_rate_pct,
                unchanged_reuse_count=unchanged_count,
                unchanged_reuse_pct=unchanged_pct,
                modified_reuse_count=modified_count,
                modified_reuse_pct=modified_pct,
                unresolved_origin_count=unresolved_count,
            ),
            quality=MemoryEffectivenessQuality(
                memory_item_count=memory_item_count,
                contradiction_item_count=contradiction_item_count,
                contradiction_rate_pct=contradiction_rate_pct,
                stale_memory_count=stale_memory_count,
                stale_memory_rate_pct=stale_rate_pct,
                stale_reason_breakdown=stale_reason_breakdown,
            ),
            trend=trend,
            audit=MemoryEffectivenessAudit(
                retrieved_event_count=retrieved_event_count,
                no_match_event_count=no_match_event_count,
            ),
        )

    @staticmethod
    def _eligible_signatures(
        db: Session, organization_id: UUID, now: datetime
    ) -> set[tuple[str, str]]:
        # Mirrors OperationalMemoryService.retrieve()'s eligibility gate exactly
        # (status in the reusable set, not stale, not expired) but reads the
        # is_stale flag as currently stored rather than recomputing it, since
        # recomputation (_refresh_staleness) mutates the item and D-D must never
        # mutate memory state. This can make coverage marginally optimistic for
        # items that have not been retrieved (and therefore not re-evaluated)
        # recently; see docs for the full explanation.
        rows = db.execute(
            select(
                OperationalMemoryItem.normalized_subject,
                OperationalMemoryItem.context_signature,
            ).where(
                OperationalMemoryItem.organization_id == organization_id,
                OperationalMemoryItem.category == "FIELD_MAPPING",
                OperationalMemoryItem.current_status.in_(_REUSABLE_STATUSES),
                OperationalMemoryItem.is_stale.is_(False),
                or_(
                    OperationalMemoryItem.valid_to.is_(None),
                    OperationalMemoryItem.valid_to > now,
                ),
            )
        ).all()
        return {(subject, signature) for subject, signature in rows}

    @staticmethod
    def _resolve_context(
        db: Session, organization_id: UUID, schema: SourceSchema
    ) -> tuple[str | None, str | None]:
        dataset = db.scalar(
            select(Dataset).where(
                Dataset.id == schema.dataset_id,
                Dataset.organization_id == organization_id,
            )
        )
        if dataset is None:
            return None, None
        source_system = db.scalar(
            select(SourceSystem).where(
                SourceSystem.id == dataset.source_system_id,
                SourceSystem.organization_id == organization_id,
            )
        )
        source_system_family = source_system.system_type if source_system is not None else None
        return source_system_family, dataset.domain

    def _schema_coverage(
        self,
        db: Session,
        organization_id: UUID,
        schema: SourceSchema,
        eligible: set[tuple[str, str]],
        industry: str | None,
    ) -> tuple[int, int]:
        fields = list(
            db.scalars(
                select(SourceField).where(
                    SourceField.organization_id == organization_id,
                    SourceField.source_schema_id == schema.id,
                )
            )
        )
        if not fields:
            return 0, 0
        source_system_family, canonical_domain = self._resolve_context(db, organization_id, schema)
        signature = context_signature(
            source_system_family,
            canonical_domain,
            MemoryContext(schema_fingerprint=schema.schema_fingerprint),
            industry,
        )
        covered = 0
        for field in fields:
            try:
                subject = normalize_subject(field.field_path)
            except OperationalMemoryServiceError:
                continue
            if (subject, signature) in eligible:
                covered += 1
        return len(fields), covered

    def _trend(
        self,
        db: Session,
        organization_id: UUID,
        eligible: set[tuple[str, str]],
        industry: str | None,
        *,
        source_schema_id: UUID | None,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> tuple[list[MemoryEffectivenessTrendPoint], list[SourceSchema]]:
        query = select(SourceSchema).where(SourceSchema.organization_id == organization_id)
        if source_schema_id is not None:
            query = query.where(SourceSchema.id == source_schema_id)
        if date_from is not None:
            query = query.where(SourceSchema.discovered_at >= date_from)
        if date_to is not None:
            query = query.where(SourceSchema.discovered_at <= date_to)
        schemas = list(
            db.scalars(query.order_by(SourceSchema.discovered_at.asc(), SourceSchema.id.asc()))
        )
        points: list[MemoryEffectivenessTrendPoint] = []
        for sequence, schema in enumerate(schemas, start=1):
            field_count, covered_field_count = self._schema_coverage(
                db, organization_id, schema, eligible, industry
            )
            coverage_pct = None if field_count == 0 else covered_field_count / field_count * 100
            no_match_pct = None if coverage_pct is None else 100 - coverage_pct
            points.append(
                MemoryEffectivenessTrendPoint(
                    source_schema_id=schema.id,
                    case_sequence=sequence,
                    discovered_at=schema.discovered_at,
                    field_count=field_count,
                    covered_field_count=covered_field_count,
                    exact_context_coverage_pct=coverage_pct,
                    no_match_rate_pct=no_match_pct,
                )
            )
        return points, schemas

    @staticmethod
    def _reuse_counts(
        db: Session,
        organization_id: UUID,
        *,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> tuple[int, int, int, int, int]:
        query = (
            select(FieldMapping)
            .join(
                MappingTemplateVersion,
                MappingTemplateVersion.id == FieldMapping.template_version_id,
            )
            .join(MappingTemplate, MappingTemplate.id == MappingTemplateVersion.template_id)
            .where(
                MappingTemplate.owner_organization_id == organization_id,
                MappingTemplate.scope_type == "organization",
            )
        )
        if date_from is not None:
            query = query.where(FieldMapping.created_at >= date_from)
        if date_to is not None:
            query = query.where(FieldMapping.created_at <= date_to)
        field_mappings = list(db.scalars(query))
        field_mapping_count = len(field_mappings)

        reused = [fm for fm in field_mappings if fm.origin_memory_version_id is not None]
        memory_derived_mapping_count = len(reused)

        origin_ids = {fm.origin_memory_version_id for fm in reused if fm.origin_memory_version_id}
        versions_by_id: dict[UUID, OperationalMemoryVersion] = {}
        if origin_ids:
            versions_by_id = {
                version.id: version
                for version in db.scalars(
                    select(OperationalMemoryVersion).where(
                        OperationalMemoryVersion.organization_id == organization_id,
                        OperationalMemoryVersion.id.in_(origin_ids),
                    )
                )
            }

        unchanged_count = 0
        modified_count = 0
        unresolved_count = 0
        for field_mapping in reused:
            classification = _classify_reused_mapping(field_mapping, versions_by_id)
            if classification is None:
                unresolved_count += 1
            elif classification:
                unchanged_count += 1
            else:
                modified_count += 1

        return (
            field_mapping_count,
            memory_derived_mapping_count,
            unchanged_count,
            modified_count,
            unresolved_count,
        )

    @staticmethod
    def _quality_counts(
        db: Session,
        organization_id: UUID,
        *,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> tuple[int, int, int, dict[str, int]]:
        query = select(OperationalMemoryItem).where(
            OperationalMemoryItem.organization_id == organization_id,
            OperationalMemoryItem.category == "FIELD_MAPPING",
        )
        if date_from is not None:
            query = query.where(OperationalMemoryItem.created_at >= date_from)
        if date_to is not None:
            query = query.where(OperationalMemoryItem.created_at <= date_to)
        items = list(db.scalars(query))
        memory_item_count = len(items)
        contradiction_item_count = sum(1 for item in items if item.contradiction_count > 0)
        stale_items = [item for item in items if item.is_stale]
        breakdown: dict[str, int] = {}
        for item in stale_items:
            if item.stale_reason_code:
                breakdown[item.stale_reason_code] = breakdown.get(item.stale_reason_code, 0) + 1
        return memory_item_count, contradiction_item_count, len(stale_items), breakdown

    @staticmethod
    def _audit_counts(
        db: Session,
        organization_id: UUID,
        *,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> tuple[int, int]:
        query = (
            select(OperationalMemoryReuseEvent.event_type, func.count())
            .where(OperationalMemoryReuseEvent.organization_id == organization_id)
            .group_by(OperationalMemoryReuseEvent.event_type)
        )
        if date_from is not None:
            query = query.where(OperationalMemoryReuseEvent.occurred_at >= date_from)
        if date_to is not None:
            query = query.where(OperationalMemoryReuseEvent.occurred_at <= date_to)
        counts: dict[str, int] = {event_type: count for event_type, count in db.execute(query)}
        return counts.get("RETRIEVED", 0), counts.get("NO_MATCH", 0)


def _classify_reused_mapping(
    field_mapping: FieldMapping,
    versions_by_id: dict[UUID, OperationalMemoryVersion],
) -> bool | None:
    """Mirrors D-C.1's _is_memory_derived_unchanged comparison, read-only.

    Returns True (unchanged), False (modified), or None (origin unresolved:
    missing, cross-tenant, or malformed payload) — never raises, since one
    corrupted row must never abort the whole tenant report.
    """
    version = versions_by_id.get(field_mapping.origin_memory_version_id)  # type: ignore[arg-type]
    if version is None:
        return None
    try:
        origin_field_id = version.value_payload.get("canonical_field_definition_id")
        if not origin_field_id:
            return None
        origin_uuid = UUID(str(origin_field_id))
    except (AttributeError, ValueError):
        return None
    return origin_uuid == field_mapping.canonical_field_definition_id


memory_effectiveness_service = MemoryEffectivenessService()
