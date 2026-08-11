from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from test_canonical_mapping_foundation import foundation

from app.models.canonical_mapping import (
    CanonicalFieldDefinition,
    FieldMapping,
    MappingTemplateVersion,
    SourceSchema,
)
from app.models.entities import utc_now
from app.models.ingestion import Dataset
from app.models.operational_memory import (
    OperationalMemoryItem,
    OperationalMemoryReuseEvent,
    OperationalMemoryVersion,
)
from app.models.source_system import SourceSystem
from app.models.trust import TrustAssessment
from app.schemas.canonical_mapping import (
    CanonicalFieldCreate,
    CanonicalTypeCreate,
    FieldMappingCreate,
    MappingTemplateCreate,
    MappingTemplateVersionCreate,
    SourceFieldCreate,
    SourceSchemaDiscover,
)
from app.schemas.memory_effectiveness import MemoryEffectivenessRead
from app.schemas.operational_memory import (
    MemoryCandidateCreate,
    MemoryContext,
    MemoryDecisionRequest,
    MemoryProvenance,
    MemoryRetrieveRequest,
)
from app.services.canonical_mapping_service import (
    canonical_registry_service,
    mapping_template_service,
    schema_discovery_service,
)
from app.services.memory_effectiveness_service import memory_effectiveness_service
from app.services.operational_memory_service import operational_memory_service

FIELD_PATH = "equipment_no"


@pytest.fixture(autouse=True)
def cleanup_memory_rows(db: Session) -> Iterator[None]:
    # Mirrors the other operational-memory test files: SQLite's
    # Base.metadata.drop_all() cannot resolve OperationalMemoryVersion's
    # self-referential supersedes FK together with OperationalMemoryReuseEvent's
    # reference to it, so rows referencing a supersession chain must be cleared
    # before teardown.
    yield
    db.rollback()
    db.execute(delete(OperationalMemoryReuseEvent))
    version_ids = list(
        db.scalars(
            select(OperationalMemoryVersion.id).order_by(
                OperationalMemoryVersion.version_number.desc()
            )
        )
    )
    for version_id in version_ids:
        db.execute(
            delete(OperationalMemoryVersion).where(OperationalMemoryVersion.id == version_id)
        )
    db.execute(delete(OperationalMemoryItem))
    db.commit()


def _organization_template(
    db: Session, organization_id: UUID, actor: UUID, slug: str
) -> tuple[CanonicalFieldDefinition, CanonicalFieldDefinition, MappingTemplateVersion]:
    code = slug.replace("-", "_")
    entity_type = canonical_registry_service.create_type(
        db,
        "entity",
        CanonicalTypeCreate(
            type_code=f"equip_{code}",
            display_name="Equipment",
            scope_type="organization",
            scope_key=f"organization:{organization_id}",
            owner_organization_id=organization_id,
            identity_strategy_code="exact_identifier",
        ),
    )
    field = canonical_registry_service.create_field(
        db,
        CanonicalFieldCreate(
            canonical_type_kind="entity",
            canonical_type_id=entity_type.id,
            field_code="equipment_id",
            display_name="Equipment ID",
            data_type="string",
            is_required=True,
        ),
        organization_id,
    )
    other_field = canonical_registry_service.create_field(
        db,
        CanonicalFieldCreate(
            canonical_type_kind="entity",
            canonical_type_id=entity_type.id,
            field_code="asset_number",
            display_name="Asset Number",
            data_type="string",
            is_required=False,
        ),
        organization_id,
    )
    template = mapping_template_service.create(
        db,
        MappingTemplateCreate(
            template_code=f"equip_{code}",
            name="Equipment",
            scope_type="organization",
            scope_key=f"organization:{organization_id}",
            owner_organization_id=organization_id,
            source_system_type="file_upload",
            target_canonical_type_kind="entity",
            target_canonical_type_id=entity_type.id,
        ),
        actor,
        authorized_organization_id=organization_id,
    )
    version = mapping_template_service.create_version(
        db,
        template.id,
        MappingTemplateVersionCreate(semantic_version="1.0.0", definition_json={}),
        actor,
        organization_id,
    )
    return field, other_field, version


def _shared_template_version(
    db: Session, actor: UUID, slug: str
) -> tuple[CanonicalFieldDefinition, MappingTemplateVersion]:
    code = slug.replace("-", "_")
    entity_type = canonical_registry_service.create_type(
        db,
        "entity",
        CanonicalTypeCreate(
            type_code=f"shared_{code}",
            display_name="Shared Equipment",
            scope_type="shared_core",
            scope_key=f"shared:{slug}",
            identity_strategy_code="exact_identifier",
        ),
    )
    field = canonical_registry_service.create_field(
        db,
        CanonicalFieldCreate(
            canonical_type_kind="entity",
            canonical_type_id=entity_type.id,
            field_code="equipment_id",
            display_name="Equipment ID",
            data_type="string",
            is_required=True,
        ),
        None,
    )
    template = mapping_template_service.create(
        db,
        MappingTemplateCreate(
            template_code=f"shared_{code}",
            name="Shared Equipment",
            scope_type="shared_core",
            scope_key=f"shared:{slug}",
            source_system_type="file_upload",
            target_canonical_type_kind="entity",
            target_canonical_type_id=entity_type.id,
        ),
        actor,
    )
    version = mapping_template_service.create_version(
        db,
        template.id,
        MappingTemplateVersionCreate(semantic_version="1.0.0", definition_json={}),
        actor,
        None,
    )
    return field, version


def _schema_with_fields(
    db: Session,
    organization_id: UUID,
    dataset_id: UUID,
    dataset_version_id: UUID,
    slug: str,
    field_paths: tuple[str, ...] = (FIELD_PATH,),
) -> SourceSchema:
    return schema_discovery_service.discover(
        db,
        organization_id,
        SourceSchemaDiscover(
            dataset_id=dataset_id,
            dataset_version_id=dataset_version_id,
            schema_fingerprint=f"{slug}-fingerprint".ljust(32, "0"),
            fields=[
                SourceFieldCreate(field_path=path, inferred_data_type="string")
                for path in field_paths
            ],
        ),
    )


def _foundation_context(db: Session, dataset_id: UUID) -> tuple[str | None, str | None]:
    dataset = db.get(Dataset, dataset_id)
    assert dataset is not None
    source_system = db.get(SourceSystem, dataset.source_system_id)
    family = source_system.system_type if source_system is not None else None
    return family, dataset.domain


def _memory_payload(
    schema: SourceSchema, field: CanonicalFieldDefinition, field_path: str = FIELD_PATH
) -> dict[str, object]:
    return {
        "source_field_path": field_path,
        "source_field_type": "string",
        "canonical_type_kind": "entity",
        "canonical_type_id": str(field.canonical_type_id),
        "canonical_field_definition_id": str(field.id),
        "canonical_field_code": field.field_code,
        "schema_fingerprint": schema.schema_fingerprint,
    }


def _record(
    db: Session,
    organization_id: UUID,
    schema: SourceSchema,
    field: CanonicalFieldDefinition,
    key: str,
    *,
    field_path: str = FIELD_PATH,
    source_system_family: str | None = None,
    canonical_domain: str | None = None,
) -> OperationalMemoryItem:
    candidate = MemoryCandidateCreate(
        idempotency_key=f"{key}-candidate",
        category="FIELD_MAPPING",
        subject_kind="SOURCE_FIELD",
        subject=field_path,
        source_system_family=source_system_family,
        canonical_domain=canonical_domain,
        context=MemoryContext(schema_fingerprint=schema.schema_fingerprint),
        value_payload=_memory_payload(schema, field, field_path),
        provenance=MemoryProvenance(
            source_schema_id=schema.id, canonical_field_definition_ids=[field.id]
        ),
        source_fingerprint="a" * 64,
    )
    item, _ = operational_memory_service.record_candidate(
        db, organization_id, candidate, None, "system"
    )
    return item


def _confirm(
    db: Session, organization_id: UUID, actor: UUID, item: OperationalMemoryItem, key: str
) -> OperationalMemoryVersion:
    _, version = operational_memory_service.decide(
        db,
        organization_id,
        item.id,
        MemoryDecisionRequest(
            idempotency_key=f"{key}-confirm",
            expected_current_version=item.current_version_number,
            action="CONFIRM",
        ),
        actor,
        "organization_admin",
    )
    return version


def _confirmed_memory(
    db: Session,
    organization_id: UUID,
    actor: UUID,
    schema: SourceSchema,
    field: CanonicalFieldDefinition,
    key: str,
    *,
    source_system_family: str | None = None,
    canonical_domain: str | None = None,
) -> tuple[OperationalMemoryItem, OperationalMemoryVersion]:
    item = _record(
        db,
        organization_id,
        schema,
        field,
        key,
        source_system_family=source_system_family,
        canonical_domain=canonical_domain,
    )
    version = _confirm(db, organization_id, actor, item, key)
    db.refresh(item)
    return item, version


def _publish(
    db: Session,
    template_version: MappingTemplateVersion,
    field: CanonicalFieldDefinition,
    actor: UUID,
    organization_id: UUID | None,
    *,
    origin_memory_version_id: UUID | None = None,
) -> FieldMapping:
    field_mapping = mapping_template_service.add_field_mapping(
        db,
        template_version.id,
        FieldMappingCreate(
            source_field_path=FIELD_PATH,
            canonical_field_definition_id=field.id,
            origin_memory_version_id=origin_memory_version_id,
        ),
        organization_id,
    )
    for target in ("candidate", "validated", "approved", "published"):
        mapping_template_service.transition(db, template_version.id, target, actor, organization_id)
    return field_mapping


def _report(
    db: Session,
    organization_id: UUID,
    *,
    source_schema_id: UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> MemoryEffectivenessRead:
    return memory_effectiveness_service.report(
        db,
        organization_id,
        source_schema_id=source_schema_id,
        date_from=date_from,
        date_to=date_to,
    )


# --- A/B: zero-state semantics --------------------------------------------------


def test_zero_memory_nonzero_fields_reports_zero_coverage(db: Session) -> None:
    org, actor, dataset_id, dataset_version_id, _, _ = foundation(db, "eff-a")
    _schema_with_fields(db, org, dataset_id, dataset_version_id, "eff-a")
    result = _report(db, org)
    assert result.coverage.source_field_count == 1
    assert result.coverage.covered_field_count == 0
    assert result.coverage.exact_context_coverage_pct == 0.0
    assert result.coverage.no_match_rate_pct == 100.0


def test_zero_source_fields_reports_null_coverage(db: Session) -> None:
    org, actor, dataset_id, dataset_version_id, _, _ = foundation(db, "eff-b")
    result = _report(db, org)
    assert result.coverage.source_field_count == 0
    assert result.coverage.exact_context_coverage_pct is None
    assert result.coverage.no_match_rate_pct is None


# --- C/D/E/F/G/H/I/J: coverage eligibility by memory status/context ------------


def test_confirmed_exact_context_memory_is_covered(db: Session) -> None:
    org, actor, dataset_id, dataset_version_id, _, _ = foundation(db, "eff-c")
    field, _, _ = _organization_template(db, org, actor, "eff-c")
    schema = _schema_with_fields(db, org, dataset_id, dataset_version_id, "eff-c")
    family, domain = _foundation_context(db, dataset_id)
    _confirmed_memory(
        db, org, actor, schema, field, "eff-c", source_system_family=family, canonical_domain=domain
    )
    result = _report(db, org)
    assert result.coverage.source_field_count == 1
    assert result.coverage.covered_field_count == 1
    assert result.coverage.exact_context_coverage_pct == 100.0


def test_corrected_memory_is_covered(db: Session) -> None:
    org, actor, dataset_id, dataset_version_id, _, _ = foundation(db, "eff-d")
    field, other_field, _ = _organization_template(db, org, actor, "eff-d")
    schema = _schema_with_fields(db, org, dataset_id, dataset_version_id, "eff-d")
    family, domain = _foundation_context(db, dataset_id)
    item, _ = _confirmed_memory(
        db, org, actor, schema, field, "eff-d", source_system_family=family, canonical_domain=domain
    )
    operational_memory_service.decide(
        db,
        org,
        item.id,
        MemoryDecisionRequest(
            idempotency_key="eff-d-correct",
            expected_current_version=item.current_version_number,
            action="CORRECT",
            corrected_payload=_memory_payload(schema, other_field),
        ),
        actor,
        "organization_admin",
    )
    result = _report(db, org)
    assert result.coverage.covered_field_count == 1


def test_observed_memory_is_not_covered(db: Session) -> None:
    org, actor, dataset_id, dataset_version_id, _, _ = foundation(db, "eff-e")
    field, _, _ = _organization_template(db, org, actor, "eff-e")
    schema = _schema_with_fields(db, org, dataset_id, dataset_version_id, "eff-e")
    family, domain = _foundation_context(db, dataset_id)
    _record(db, org, schema, field, "eff-e", source_system_family=family, canonical_domain=domain)
    result = _report(db, org)
    assert result.coverage.covered_field_count == 0
    assert result.coverage.no_match_rate_pct == 100.0


def test_rejected_memory_is_not_covered(db: Session) -> None:
    org, actor, dataset_id, dataset_version_id, _, _ = foundation(db, "eff-f")
    field, _, _ = _organization_template(db, org, actor, "eff-f")
    schema = _schema_with_fields(db, org, dataset_id, dataset_version_id, "eff-f")
    family, domain = _foundation_context(db, dataset_id)
    item = _record(
        db, org, schema, field, "eff-f", source_system_family=family, canonical_domain=domain
    )
    operational_memory_service.decide(
        db,
        org,
        item.id,
        MemoryDecisionRequest(
            idempotency_key="eff-f-reject",
            expected_current_version=item.current_version_number,
            action="REJECT",
        ),
        actor,
        "organization_admin",
    )
    result = _report(db, org)
    assert result.coverage.covered_field_count == 0


def test_ambiguous_memory_is_not_covered(db: Session) -> None:
    org, actor, dataset_id, dataset_version_id, _, _ = foundation(db, "eff-g")
    field, other_field, _ = _organization_template(db, org, actor, "eff-g")
    schema = _schema_with_fields(db, org, dataset_id, dataset_version_id, "eff-g")
    family, domain = _foundation_context(db, dataset_id)
    item = _record(
        db, org, schema, field, "eff-g", source_system_family=family, canonical_domain=domain
    )
    # A second, conflicting observation under the same identity triggers D-A's
    # existing AMBIGUOUS contradiction logic.
    candidate = MemoryCandidateCreate(
        idempotency_key="eff-g-candidate-2",
        category="FIELD_MAPPING",
        subject_kind="SOURCE_FIELD",
        subject=FIELD_PATH,
        source_system_family=family,
        canonical_domain=domain,
        context=MemoryContext(schema_fingerprint=schema.schema_fingerprint),
        value_payload=_memory_payload(schema, other_field),
        provenance=MemoryProvenance(
            source_schema_id=schema.id, canonical_field_definition_ids=[other_field.id]
        ),
        source_fingerprint="b" * 64,
    )
    operational_memory_service.record_candidate(db, org, candidate, None, "system")
    db.refresh(item)
    assert item.current_status == "AMBIGUOUS"
    result = _report(db, org)
    assert result.coverage.covered_field_count == 0


def test_stale_memory_is_not_covered_but_counted_in_stale_rate(db: Session) -> None:
    org, actor, dataset_id, dataset_version_id, _, _ = foundation(db, "eff-h")
    field, _, _ = _organization_template(db, org, actor, "eff-h")
    schema = _schema_with_fields(db, org, dataset_id, dataset_version_id, "eff-h")
    family, domain = _foundation_context(db, dataset_id)
    item, _ = _confirmed_memory(
        db, org, actor, schema, field, "eff-h", source_system_family=family, canonical_domain=domain
    )
    item.is_stale = True
    item.stale_reason_code = "SCHEMA_CHANGED"
    item.stale_detected_at = utc_now()
    db.commit()
    result = _report(db, org)
    assert result.coverage.covered_field_count == 0
    assert result.quality.stale_memory_count == 1
    assert result.quality.stale_memory_rate_pct == 100.0
    assert result.quality.stale_reason_breakdown == {"SCHEMA_CHANGED": 1}


def test_wrong_context_memory_is_not_covered(db: Session) -> None:
    org, actor, dataset_id, dataset_version_id, _, _ = foundation(db, "eff-i")
    field, _, _ = _organization_template(db, org, actor, "eff-i")
    schema_a = _schema_with_fields(db, org, dataset_id, dataset_version_id, "eff-i-a")
    schema_b = _schema_with_fields(db, org, dataset_id, dataset_version_id, "eff-i-b")
    family, domain = _foundation_context(db, dataset_id)
    _confirmed_memory(
        db,
        org,
        actor,
        schema_a,
        field,
        "eff-i",
        source_system_family=family,
        canonical_domain=domain,
    )
    result = _report(db, org, source_schema_id=schema_b.id)
    assert result.coverage.covered_field_count == 0


def test_exact_context_memory_is_covered_for_matching_schema_only(db: Session) -> None:
    org, actor, dataset_id, dataset_version_id, _, _ = foundation(db, "eff-j")
    field, _, _ = _organization_template(db, org, actor, "eff-j")
    schema_a = _schema_with_fields(db, org, dataset_id, dataset_version_id, "eff-j-a")
    _schema_with_fields(db, org, dataset_id, dataset_version_id, "eff-j-b")
    family, domain = _foundation_context(db, dataset_id)
    _confirmed_memory(
        db,
        org,
        actor,
        schema_a,
        field,
        "eff-j",
        source_system_family=family,
        canonical_domain=domain,
    )
    result = _report(db, org, source_schema_id=schema_a.id)
    assert result.coverage.covered_field_count == 1


# --- K/L/M/N/O: reuse-rate classification ---------------------------------------


def test_reuse_rate_counts_field_mappings_with_origin(db: Session) -> None:
    org, actor, dataset_id, dataset_version_id, _, _ = foundation(db, "eff-k")
    field, _, template_version = _organization_template(db, org, actor, "eff-k")
    schema = _schema_with_fields(db, org, dataset_id, dataset_version_id, "eff-k")
    _, origin_version = _confirmed_memory(db, org, actor, schema, field, "eff-k")
    _publish(db, template_version, field, actor, org, origin_memory_version_id=origin_version.id)
    result = _report(db, org)
    assert result.reuse.field_mapping_count == 1
    assert result.reuse.memory_derived_mapping_count == 1
    assert result.reuse.memory_reuse_rate_pct == 100.0


def test_shared_template_field_mappings_excluded_from_reuse(db: Session) -> None:
    org, actor, dataset_id, dataset_version_id, _, _ = foundation(db, "eff-l")
    field, _, _ = _organization_template(db, org, actor, "eff-l")
    schema = _schema_with_fields(db, org, dataset_id, dataset_version_id, "eff-l")
    _, origin_version = _confirmed_memory(db, org, actor, schema, field, "eff-l")
    shared_field, shared_version = _shared_template_version(db, actor, "eff-l")
    mapping_template_service.add_field_mapping(
        db,
        shared_version.id,
        FieldMappingCreate(
            source_field_path=FIELD_PATH,
            canonical_field_definition_id=shared_field.id,
        ),
        None,
    )
    result = _report(db, org)
    assert result.reuse.field_mapping_count == 0
    assert result.reuse.memory_derived_mapping_count == 0


def test_unchanged_reuse_classification_matches_dc1_semantics(db: Session) -> None:
    org, actor, dataset_id, dataset_version_id, _, _ = foundation(db, "eff-m")
    field, _, template_version = _organization_template(db, org, actor, "eff-m")
    schema = _schema_with_fields(db, org, dataset_id, dataset_version_id, "eff-m")
    _, origin_version = _confirmed_memory(db, org, actor, schema, field, "eff-m")
    _publish(db, template_version, field, actor, org, origin_memory_version_id=origin_version.id)
    result = _report(db, org)
    assert result.reuse.unchanged_reuse_count == 1
    assert result.reuse.modified_reuse_count == 0
    assert result.reuse.unresolved_origin_count == 0
    assert result.reuse.unchanged_reuse_pct == 100.0
    assert result.reuse.modified_reuse_pct == 0.0


def test_modified_reuse_classification(db: Session) -> None:
    org, actor, dataset_id, dataset_version_id, _, _ = foundation(db, "eff-n")
    field, other_field, template_version = _organization_template(db, org, actor, "eff-n")
    schema = _schema_with_fields(db, org, dataset_id, dataset_version_id, "eff-n")
    _, origin_version = _confirmed_memory(db, org, actor, schema, field, "eff-n")
    _publish(
        db, template_version, other_field, actor, org, origin_memory_version_id=origin_version.id
    )
    result = _report(db, org)
    assert result.reuse.modified_reuse_count == 1
    assert result.reuse.unchanged_reuse_count == 0
    assert result.reuse.modified_reuse_pct == 100.0


def test_unresolved_origin_is_explicitly_accounted_for(db: Session) -> None:
    org, actor, dataset_id, dataset_version_id, _, _ = foundation(db, "eff-o")
    field, _, template_version = _organization_template(db, org, actor, "eff-o")
    field_mapping = _publish(db, template_version, field, actor, org)
    reloaded_field_mapping = db.get(FieldMapping, field_mapping.id)
    assert reloaded_field_mapping is not None
    reloaded_field_mapping.origin_memory_version_id = uuid4()
    db.commit()
    result = _report(db, org)
    assert result.reuse.memory_derived_mapping_count == 1
    assert result.reuse.unresolved_origin_count == 1
    assert result.reuse.unchanged_reuse_count == 0
    assert result.reuse.modified_reuse_count == 0
    # Resolved-reuse denominator is zero, so the percentages must not fabricate
    # a value from an all-unresolved population.
    assert result.reuse.unchanged_reuse_pct is None
    assert result.reuse.modified_reuse_pct is None


# --- P/Q: quality rates ----------------------------------------------------------


def test_contradiction_rate_numerator_and_denominator(db: Session) -> None:
    org, actor, dataset_id, dataset_version_id, _, _ = foundation(db, "eff-p")
    field, other_field, _ = _organization_template(db, org, actor, "eff-p")
    schema = _schema_with_fields(db, org, dataset_id, dataset_version_id, "eff-p")
    item = _record(db, org, schema, field, "eff-p")
    conflicting = MemoryCandidateCreate(
        idempotency_key="eff-p-candidate-2",
        category="FIELD_MAPPING",
        subject_kind="SOURCE_FIELD",
        subject=FIELD_PATH,
        context=MemoryContext(schema_fingerprint=schema.schema_fingerprint),
        value_payload=_memory_payload(schema, other_field),
        provenance=MemoryProvenance(
            source_schema_id=schema.id, canonical_field_definition_ids=[other_field.id]
        ),
        source_fingerprint="c" * 64,
    )
    operational_memory_service.record_candidate(db, org, conflicting, None, "system")
    db.refresh(item)
    assert item.contradiction_count == 1
    result = _report(db, org)
    assert result.quality.memory_item_count == 1
    assert result.quality.contradiction_item_count == 1
    assert result.quality.contradiction_rate_pct == 100.0


def test_stale_rate_numerator_and_denominator(db: Session) -> None:
    org, actor, dataset_id, dataset_version_id, _, _ = foundation(db, "eff-q")
    field, _, _ = _organization_template(db, org, actor, "eff-q")
    schema = _schema_with_fields(db, org, dataset_id, dataset_version_id, "eff-q")
    item, _ = _confirmed_memory(db, org, actor, schema, field, "eff-q")
    item.is_stale = True
    item.stale_reason_code = "VALIDITY_EXPIRED"
    item.stale_detected_at = utc_now()
    db.commit()
    result = _report(db, org)
    assert result.quality.memory_item_count == 1
    assert result.quality.stale_memory_count == 1
    assert result.quality.stale_memory_rate_pct == 100.0


# --- R: deterministic multi-schema sequence -------------------------------------


def test_multiple_source_schemas_produce_deterministic_sequence(db: Session) -> None:
    org, actor, dataset_id, dataset_version_id, _, _ = foundation(db, "eff-r")
    schema_1 = _schema_with_fields(db, org, dataset_id, dataset_version_id, "eff-r-1")
    schema_2 = _schema_with_fields(db, org, dataset_id, dataset_version_id, "eff-r-2")
    schema_3 = _schema_with_fields(db, org, dataset_id, dataset_version_id, "eff-r-3")
    base = utc_now()
    schema_1.discovered_at = base
    schema_2.discovered_at = base + timedelta(minutes=1)
    schema_3.discovered_at = base + timedelta(minutes=2)
    db.commit()

    result = _report(db, org)
    assert [point.source_schema_id for point in result.trend] == [
        schema_1.id,
        schema_2.id,
        schema_3.id,
    ]
    assert [point.case_sequence for point in result.trend] == [1, 2, 3]

    result_again = _report(db, org)
    assert [point.source_schema_id for point in result_again.trend] == [
        schema_1.id,
        schema_2.id,
        schema_3.id,
    ]


def test_trend_reflects_current_state_not_historical_discovery_time(db: Session) -> None:
    # Honesty check for the current-vs-historical coverage gate: a schema
    # discovered BEFORE any memory existed still reports as covered NOW, once
    # memory is confirmed later. The trend is explicitly current-state, not a
    # point-in-time reconstruction of eligibility as of discovered_at.
    org, actor, dataset_id, dataset_version_id, _, _ = foundation(db, "eff-r2")
    field, _, _ = _organization_template(db, org, actor, "eff-r2")
    schema = _schema_with_fields(db, org, dataset_id, dataset_version_id, "eff-r2")
    family, domain = _foundation_context(db, dataset_id)
    result_before = _report(db, org)
    assert result_before.trend[0].exact_context_coverage_pct == 0.0

    _confirmed_memory(
        db,
        org,
        actor,
        schema,
        field,
        "eff-r2",
        source_system_family=family,
        canonical_domain=domain,
    )

    result_after = _report(db, org)
    assert result_after.trend[0].exact_context_coverage_pct == 100.0


# --- S/T: tenant isolation --------------------------------------------------------


def test_tenant_isolation_across_all_sections(db: Session) -> None:
    org_a, actor_a, dataset_a, dataset_version_a, _, _ = foundation(db, "eff-s-a")
    org_b, actor_b, dataset_b, dataset_version_b, _, _ = foundation(db, "eff-s-b")
    field_a, _, template_version_a = _organization_template(db, org_a, actor_a, "eff-s-a")
    field_b, _, template_version_b = _organization_template(db, org_b, actor_b, "eff-s-b")
    schema_a = _schema_with_fields(db, org_a, dataset_a, dataset_version_a, "eff-s-a")
    schema_b = _schema_with_fields(db, org_b, dataset_b, dataset_version_b, "eff-s-b")
    _, origin_a = _confirmed_memory(db, org_a, actor_a, schema_a, field_a, "eff-s-a")
    _, origin_b = _confirmed_memory(db, org_b, actor_b, schema_b, field_b, "eff-s-b")
    _publish(db, template_version_a, field_a, actor_a, org_a, origin_memory_version_id=origin_a.id)
    _publish(db, template_version_b, field_b, actor_b, org_b, origin_memory_version_id=origin_b.id)

    result_a = _report(db, org_a)
    result_b = _report(db, org_b)
    assert result_a.reuse.field_mapping_count == 1
    assert result_b.reuse.field_mapping_count == 1
    assert {point.source_schema_id for point in result_a.trend}.isdisjoint(
        {point.source_schema_id for point in result_b.trend}
    )


def test_same_field_name_across_tenants_does_not_leak(db: Session) -> None:
    org_a, actor_a, dataset_a, dataset_version_a, _, _ = foundation(db, "eff-t-a")
    org_b, actor_b, dataset_b, dataset_version_b, _, _ = foundation(db, "eff-t-b")
    field_a, _, _ = _organization_template(db, org_a, actor_a, "eff-t-a")
    _organization_template(db, org_b, actor_b, "eff-t-b")
    schema_a = _schema_with_fields(db, org_a, dataset_a, dataset_version_a, "eff-t-a")
    _schema_with_fields(db, org_b, dataset_b, dataset_version_b, "eff-t-b")
    _confirmed_memory(db, org_a, actor_a, schema_a, field_a, "eff-t-a")

    result_b = _report(db, org_b)
    assert result_b.coverage.covered_field_count == 0


# --- U: reuse-event audit counts (retrieval != acceptance) ----------------------


def test_audit_retrieved_event_count_is_not_acceptance(db: Session) -> None:
    org, actor, dataset_id, dataset_version_id, _, _ = foundation(db, "eff-u")
    field, _, _ = _organization_template(db, org, actor, "eff-u")
    schema = _schema_with_fields(db, org, dataset_id, dataset_version_id, "eff-u")
    _confirmed_memory(db, org, actor, schema, field, "eff-u")
    operational_memory_service.retrieve(
        db,
        org,
        MemoryRetrieveRequest(
            idempotency_key="eff-u-retrieve",
            category="FIELD_MAPPING",
            subject_kind="SOURCE_FIELD",
            subject=FIELD_PATH,
            context=MemoryContext(schema_fingerprint=schema.schema_fingerprint),
        ),
    )
    result = _report(db, org)
    assert result.audit.retrieved_event_count == 1
    # No FieldMapping was ever authored: retrieval happened, but nothing was used.
    assert result.reuse.memory_derived_mapping_count == 0


def test_audit_no_match_event_count(db: Session) -> None:
    org, actor, dataset_id, dataset_version_id, _, _ = foundation(db, "eff-u2")
    schema = _schema_with_fields(db, org, dataset_id, dataset_version_id, "eff-u2")
    operational_memory_service.retrieve(
        db,
        org,
        MemoryRetrieveRequest(
            idempotency_key="eff-u2-retrieve",
            category="FIELD_MAPPING",
            subject_kind="SOURCE_FIELD",
            subject=FIELD_PATH,
            context=MemoryContext(schema_fingerprint=schema.schema_fingerprint),
        ),
    )
    result = _report(db, org)
    assert result.audit.no_match_event_count == 1
    assert result.audit.retrieved_event_count == 0


# --- V: zero-denominator semantics across all sections --------------------------


def test_zero_denominators_are_null_not_fabricated(db: Session) -> None:
    org, actor, dataset_id, dataset_version_id, _, _ = foundation(db, "eff-v")
    result = _report(db, org)
    assert result.coverage.exact_context_coverage_pct is None
    assert result.coverage.no_match_rate_pct is None
    assert result.reuse.memory_reuse_rate_pct is None
    assert result.reuse.unchanged_reuse_pct is None
    assert result.reuse.modified_reuse_pct is None
    assert result.quality.contradiction_rate_pct is None
    assert result.quality.stale_memory_rate_pct is None


# --- W: determinism ---------------------------------------------------------------


def test_determinism_same_state_same_payload_except_generated_at(db: Session) -> None:
    org, actor, dataset_id, dataset_version_id, _, _ = foundation(db, "eff-w")
    field, _, template_version = _organization_template(db, org, actor, "eff-w")
    schema = _schema_with_fields(db, org, dataset_id, dataset_version_id, "eff-w")
    _, origin_version = _confirmed_memory(db, org, actor, schema, field, "eff-w")
    _publish(db, template_version, field, actor, org, origin_memory_version_id=origin_version.id)

    first = _report(db, org)
    second = _report(db, org)
    assert first.model_dump(exclude={"generated_at"}) == second.model_dump(exclude={"generated_at"})


# --- X: read-only (zero mutations) ------------------------------------------------


def test_report_creates_zero_mutations(db: Session) -> None:
    org, actor, dataset_id, dataset_version_id, _, _ = foundation(db, "eff-x")
    field, _, template_version = _organization_template(db, org, actor, "eff-x")
    schema = _schema_with_fields(db, org, dataset_id, dataset_version_id, "eff-x")
    _, origin_version = _confirmed_memory(db, org, actor, schema, field, "eff-x")
    _publish(db, template_version, field, actor, org, origin_memory_version_id=origin_version.id)

    def _counts() -> tuple[int, int, int, int, int]:
        return (
            db.scalar(select(func.count()).select_from(OperationalMemoryItem)) or 0,
            db.scalar(select(func.count()).select_from(OperationalMemoryVersion)) or 0,
            db.scalar(select(func.count()).select_from(OperationalMemoryReuseEvent)) or 0,
            db.scalar(select(func.count()).select_from(FieldMapping)) or 0,
            db.scalar(select(func.count()).select_from(TrustAssessment)) or 0,
        )

    before = _counts()
    _report(db, org)
    after = _counts()
    assert before == after
    assert not db.dirty
    assert not db.new
