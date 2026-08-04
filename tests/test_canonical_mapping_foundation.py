from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, configure_mappers

from app.db.session import Base
from app.models.canonical_mapping import (
    CanonicalEntity,
    CanonicalEntityType,
    CanonicalEvent,
    CanonicalEventType,
    CanonicalFieldDefinition,
    CanonicalMetric,
    CanonicalMetricType,
    EntityMatchCandidate,
    EntityMatchRule,
    FieldMapping,
    MappingAuditEvent,
    MappingException,
    MappingRecordResult,
    MappingReview,
    MappingRun,
    MappingTemplate,
    MappingTemplateVersion,
    MappingTransformation,
    SourceCanonicalLink,
    SourceField,
    SourceSchema,
    ValueCrosswalk,
    ValueCrosswalkEntry,
)
from app.models.raw_lineage import LineageEdge
from app.registries.canonical_mapping_registry import CANONICAL_MAPPING_PROFILES
from app.registries.rule_registry import default_rule_registry
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
    SourceFieldCreate,
    SourceSchemaDiscover,
    TransformationCreate,
    ValueCrosswalkCreate,
    ValueCrosswalkEntryCreate,
)
from app.schemas.contracts import OrganizationCreate
from app.schemas.ingestion import DatasetCreate, DatasetVersionCreate, IngestionBatchCreate
from app.schemas.raw_lineage import RawRecordReferenceCreate, RawStorageObjectCreate
from app.schemas.source_systems import SourceSystemCreate
from app.services.canonical_mapping_service import (
    CanonicalMappingServiceError,
    canonical_registry_service,
    mapping_execution_service,
    mapping_review_service,
    mapping_suggestion_service,
    mapping_template_service,
    mapping_trust_signal_service,
    schema_discovery_service,
    value_crosswalk_service,
)
from app.services.ingestion_service import (
    DatasetService,
    DatasetVersionService,
    IngestionBatchService,
)
from app.services.organization_service import OrganizationService
from app.services.raw_lineage_service import RawRecordReferenceService, RawStorageObjectService
from app.services.source_system_service import SourceSystemService

WP_301_TABLES = {
    "canonical_entity_types",
    "canonical_field_definitions",
    "canonical_event_types",
    "canonical_metric_types",
    "mapping_templates",
    "mapping_template_versions",
    "field_mappings",
    "mapping_transformations",
    "value_crosswalks",
    "value_crosswalk_entries",
    "entity_match_rules",
    "source_schemas",
    "source_fields",
    "mapping_runs",
    "mapping_record_results",
    "mapping_exceptions",
    "mapping_reviews",
    "canonical_entities",
    "canonical_events",
    "canonical_metrics",
    "source_canonical_links",
    "entity_match_candidates",
    "mapping_audit_events",
}

WP_301_MODELS = (
    CanonicalEntityType,
    CanonicalFieldDefinition,
    CanonicalEventType,
    CanonicalMetricType,
    MappingTemplate,
    MappingTemplateVersion,
    FieldMapping,
    MappingTransformation,
    ValueCrosswalk,
    ValueCrosswalkEntry,
    EntityMatchRule,
    SourceSchema,
    SourceField,
    MappingRun,
    MappingRecordResult,
    MappingException,
    MappingReview,
    CanonicalEntity,
    CanonicalEvent,
    CanonicalMetric,
    SourceCanonicalLink,
    EntityMatchCandidate,
    MappingAuditEvent,
)


def foundation(db: Session, slug: str) -> tuple[UUID, UUID, UUID, UUID, UUID, UUID]:
    actor = uuid4()
    organization = OrganizationService().create(
        db,
        OrganizationCreate(
            name=slug,
            slug=slug,
            country_code="US",
            default_currency="USD",
            timezone="UTC",
        ),
    )
    source = SourceSystemService().create(
        db,
        organization.id,
        SourceSystemCreate(
            name="ERP",
            code="erp",
            system_type="erp",
            integration_method="file_upload",
        ),
        actor,
    )
    source.status = "active"
    db.commit()
    batch = IngestionBatchService().create(
        db,
        organization.id,
        IngestionBatchCreate(
            source_system_id=source.id,
            batch_number="batch-001",
            ingestion_method="file_upload",
            trigger_type="manual",
        ),
        actor,
    )
    dataset = DatasetService().create(
        db,
        organization.id,
        DatasetCreate(
            source_system_id=source.id,
            name="Customers",
            code="customers",
            domain="customers",
            dataset_type="master_data",
        ),
        actor,
    )
    version = DatasetVersionService().create(
        db,
        organization.id,
        dataset.id,
        DatasetVersionCreate(
            ingestion_batch_id=batch.id,
            source_file_name="customers.csv",
            source_file_extension="csv",
        ),
    )
    raw_service = RawStorageObjectService()
    raw_object = raw_service.register(
        db,
        organization.id,
        RawStorageObjectCreate(
            source_system_id=source.id,
            ingestion_batch_id=batch.id,
            dataset_version_id=version.id,
            object_number="raw-001",
            idempotency_key=f"raw-{slug}",
            object_type="file",
            storage_provider="s3",
            storage_reference=f"s3://opaque/{slug}",
            original_filename="customers.csv",
            normalized_filename="customers.csv",
            file_extension="csv",
            media_type="text/csv",
            encoding="utf-8",
            content_checksum_algorithm="sha256",
            content_checksum="a" * 64,
            size_bytes=100,
            received_at=datetime.now(UTC),
        ),
        actor,
    )
    raw_reference = RawRecordReferenceService(
        raw_service,
        raw_service.lineage,
        raw_service.events,
    ).register(
        db,
        organization.id,
        raw_object.id,
        RawRecordReferenceCreate(
            dataset_version_id=version.id,
            record_sequence=1,
            source_row_number=2,
        ),
        actor,
    )
    return organization.id, actor, dataset.id, version.id, raw_object.id, raw_reference.id


def published_entity_mapping(
    db: Session,
    organization_id: UUID,
    actor: UUID,
    name_validation_rule: dict[str, object] | None = None,
) -> tuple[CanonicalEntityType, MappingTemplateVersion]:
    entity_type = canonical_registry_service.create_type(
        db,
        "entity",
        CanonicalTypeCreate(
            type_code="customer",
            display_name="Customer",
            scope_type="organization",
            scope_key=f"organization:{organization_id}",
            owner_organization_id=organization_id,
            identity_strategy_code="exact_identifier",
        ),
    )
    assert isinstance(entity_type, CanonicalEntityType)
    name_field = canonical_registry_service.create_field(
        db,
        CanonicalFieldCreate(
            canonical_type_kind="entity",
            canonical_type_id=entity_type.id,
            field_code="name",
            display_name="Name",
            data_type="string",
            is_required=True,
            validation_rule=name_validation_rule,
        ),
        organization_id,
    )
    key_field = canonical_registry_service.create_field(
        db,
        CanonicalFieldCreate(
            canonical_type_kind="entity",
            canonical_type_id=entity_type.id,
            field_code="canonical_entity_key",
            display_name="Customer key",
            data_type="string",
            is_required=True,
        ),
        organization_id,
    )
    template = mapping_template_service.create(
        db,
        MappingTemplateCreate(
            template_code="customer_csv",
            name="Customer CSV",
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
        MappingTemplateVersionCreate(
            semantic_version="1.0.0",
            definition_json={"format": "customer_csv"},
        ),
        actor,
        organization_id,
    )
    name_mapping = mapping_template_service.add_field_mapping(
        db,
        version.id,
        FieldMappingCreate(
            source_field_path="customer_name",
            canonical_field_definition_id=name_field.id,
            sequence=0,
            is_required_for_publication=True,
        ),
        organization_id,
    )
    mapping_template_service.add_transformation(
        db,
        name_mapping.id,
        TransformationCreate(
            sequence=0,
            transformation_type="trim_normalize",
            parameters_json={},
        ),
        organization_id,
    )
    mapping_template_service.add_field_mapping(
        db,
        version.id,
        FieldMappingCreate(
            source_field_path="customer_id",
            canonical_field_definition_id=key_field.id,
            sequence=1,
            is_required_for_publication=True,
        ),
        organization_id,
    )
    for target in ("candidate", "validated", "approved", "published"):
        mapping_template_service.transition(db, version.id, target, actor, organization_id)
    return entity_type, version


def test_exact_table_contract_mapper_configuration_and_metadata() -> None:
    configure_mappers()
    assert len(WP_301_TABLES) == 23
    assert {model.__tablename__ for model in WP_301_MODELS} == WP_301_TABLES
    assert WP_301_TABLES <= set(Base.metadata.tables)

    raw_uniques = {
        constraint.name
        for constraint in Base.metadata.tables["raw_record_references"].constraints
        if constraint.name
    }
    assert "uq_raw_record_references_org_id" in raw_uniques
    assert {
        "fk_mapping_record_results_org_raw_record",
        "fk_mapping_record_results_org_mapping_run",
    } <= {
        constraint.name
        for constraint in Base.metadata.tables["mapping_record_results"].constraints
        if constraint.name
    }
    record_fks = [
        constraint
        for constraint in Base.metadata.tables["mapping_record_results"].foreign_key_constraints
    ]
    assert {
        constraint.name
        for constraint in record_fks
        if constraint.referred_table.name in {"mapping_runs", "raw_record_references"}
    } == {
        "fk_mapping_record_results_org_mapping_run",
        "fk_mapping_record_results_org_raw_record",
    }
    assert all(
        len(constraint.column_keys) == 2
        for constraint in record_fks
        if constraint.referred_table.name in {"mapping_runs", "raw_record_references"}
    )
    entry_constraints = Base.metadata.tables["value_crosswalk_entries"].constraints
    assert {
        "fk_value_crosswalk_entry_owner_crosswalk",
        "fk_value_crosswalk_entry_owner_supersedes",
        "uq_value_crosswalk_entries_owner_id",
    } <= {constraint.name for constraint in entry_constraints if constraint.name}


def test_migration_is_static_revision_scoped_and_creates_exact_tables() -> None:
    source = Path("migrations/versions/20260804_0031_canonical_mapping_foundation.py").read_text(
        encoding="utf-8"
    )
    assert 'revision: str = "20260804_0031"' in source
    assert 'down_revision: str | None = "20260802_0030"' in source
    assert "Base.metadata" not in source
    assert "from app." not in source
    assert source.count("op.create_table(") == 23
    for table_name in WP_301_TABLES:
        assert f'        "{table_name}",' in source


def test_source_schema_is_idempotent_and_tenant_safe(db: Session) -> None:
    organization_id, actor, dataset_id, version_id, _, _ = foundation(db, "mapping-schema")
    other_id, other_actor, _, _, _, _ = foundation(db, "mapping-schema-other")
    payload = SourceSchemaDiscover(
        dataset_id=dataset_id,
        dataset_version_id=version_id,
        schema_fingerprint="f" * 64,
        fields=[
            SourceFieldCreate(
                field_path="customer_id",
                inferred_data_type="string",
                null_ratio=Decimal("0"),
                distinct_ratio=Decimal("1"),
            )
        ],
    )
    schema = schema_discovery_service.discover(db, organization_id, payload)
    assert schema_discovery_service.discover(db, organization_id, payload).id == schema.id
    assert (
        db.scalar(select(SourceField).where(SourceField.source_schema_id == schema.id)) is not None
    )
    with pytest.raises(CanonicalMappingServiceError, match="outside tenant scope"):
        schema_discovery_service.discover(db, other_id, payload)

    entity_type, _ = published_entity_mapping(db, organization_id, actor)
    other_entity_type, _ = published_entity_mapping(db, other_id, other_actor)
    visible_customer_field = canonical_registry_service.create_field(
        db,
        CanonicalFieldCreate(
            canonical_type_kind="entity",
            canonical_type_id=entity_type.id,
            field_code="customer_id",
            display_name="Customer ID",
            data_type="string",
        ),
        organization_id,
    )
    hidden_customer_field = canonical_registry_service.create_field(
        db,
        CanonicalFieldCreate(
            canonical_type_kind="entity",
            canonical_type_id=other_entity_type.id,
            field_code="customer_id",
            display_name="Customer ID",
            data_type="string",
        ),
        other_id,
    )
    suggestions = mapping_suggestion_service.suggest(db, organization_id, schema.id)
    visible_field_ids = {
        field.id
        for field in db.scalars(
            select(CanonicalFieldDefinition).where(
                CanonicalFieldDefinition.canonical_type_id == entity_type.id
            )
        )
    }
    hidden_field_ids = {
        field.id
        for field in db.scalars(
            select(CanonicalFieldDefinition).where(
                CanonicalFieldDefinition.canonical_type_id == other_entity_type.id
            )
        )
    }
    suggested_ids = {suggestion["canonical_field_definition_id"] for suggestion in suggestions}
    assert visible_customer_field.id in suggested_ids
    assert hidden_customer_field.id not in suggested_ids
    assert suggested_ids <= visible_field_ids
    assert suggested_ids.isdisjoint(hidden_field_ids)


def test_template_lifecycle_immutability_and_single_published_version(db: Session) -> None:
    organization_id, actor, _, _, _, _ = foundation(db, "mapping-template")
    _, version = published_entity_mapping(db, organization_id, actor)
    version.definition_json = {"changed": True}
    with pytest.raises(ValueError, match="immutable"):
        db.commit()
    db.rollback()
    stored = db.get(MappingTemplateVersion, version.id)
    assert stored is not None
    assert stored.definition_json == {"format": "customer_csv"}
    field_mapping = db.scalar(
        select(FieldMapping).where(FieldMapping.template_version_id == stored.id)
    )
    assert field_mapping is not None
    with pytest.raises(CanonicalMappingServiceError) as exc:
        mapping_template_service.add_transformation(
            db,
            field_mapping.id,
            TransformationCreate(
                sequence=99,
                transformation_type="trim_normalize",
                parameters_json={},
            ),
            organization_id,
        )
    assert exc.value.code == "VERSION_IMMUTABLE"
    mapping_template_service.transition(
        db,
        stored.id,
        "deprecated",
        actor,
        organization_id,
    )
    mapping_template_service.transition(
        db,
        stored.id,
        "retired",
        actor,
        organization_id,
    )


def test_crosswalk_entries_are_governed_versioned_and_tenant_visible(db: Session) -> None:
    organization_id, actor, _, _, _, _ = foundation(db, "mapping-crosswalk")
    other_id, other_actor, _, _, _, _ = foundation(db, "mapping-crosswalk-other")
    entity_type, _ = published_entity_mapping(db, organization_id, actor)
    field = canonical_registry_service.create_field(
        db,
        CanonicalFieldCreate(
            canonical_type_kind="entity",
            canonical_type_id=entity_type.id,
            field_code="status",
            display_name="Status",
            data_type="enum",
        ),
        organization_id,
    )
    crosswalk = value_crosswalk_service.create(
        db,
        ValueCrosswalkCreate(
            crosswalk_code="customer_status",
            name="Customer status",
            canonical_field_definition_id=field.id,
            scope_type="organization",
            scope_key=f"organization:{organization_id}",
            owner_organization_id=organization_id,
        ),
        actor,
    )
    entry = value_crosswalk_service.add_entry(
        db,
        crosswalk.id,
        ValueCrosswalkEntryCreate(
            source_value="  ACTIVE ",
            canonical_target_value="active",
            mapping_confidence_score=Decimal("0.95"),
            confidence_method_code="governed_crosswalk",
            confidence_method_version="1.0",
        ),
        organization_id,
    )
    value_crosswalk_service.approve(db, entry.id, actor, organization_id)
    resolved = value_crosswalk_service.resolve(db, crosswalk.id, "active", organization_id)
    assert resolved is not None
    assert resolved.canonical_target_value == "active"
    assert value_crosswalk_service.resolve(db, crosswalk.id, "active", other_id) is None
    stored_entry = db.get(ValueCrosswalkEntry, entry.id)
    assert stored_entry is not None
    state = inspect(stored_entry)
    assert state is not None and state.persistent

    other_entity_type, _ = published_entity_mapping(db, other_id, other_actor)
    other_field = db.scalar(
        select(CanonicalFieldDefinition).where(
            CanonicalFieldDefinition.canonical_type_id == other_entity_type.id
        )
    )
    assert other_field is not None
    with pytest.raises(CanonicalMappingServiceError) as exc:
        value_crosswalk_service.create(
            db,
            ValueCrosswalkCreate(
                crosswalk_code="cross_tenant_field",
                name="Invalid cross-tenant field",
                canonical_field_definition_id=other_field.id,
                scope_type="organization",
                scope_key=f"organization:{organization_id}",
                owner_organization_id=organization_id,
            ),
            actor,
            organization_id,
        )
    assert exc.value.code == "CANONICAL_TYPE_NOT_FOUND"

    other_crosswalk = value_crosswalk_service.create(
        db,
        ValueCrosswalkCreate(
            crosswalk_code="other_status",
            name="Other status",
            canonical_field_definition_id=other_field.id,
            scope_type="organization",
            scope_key=f"organization:{other_id}",
            owner_organization_id=other_id,
        ),
        other_actor,
        other_id,
    )
    other_entry = value_crosswalk_service.add_entry(
        db,
        other_crosswalk.id,
        ValueCrosswalkEntryCreate(
            source_value="legacy",
            canonical_target_value="legacy",
        ),
        other_id,
    )
    db.add(
        ValueCrosswalkEntry(
            owner_organization_id=organization_id,
            crosswalk_id=crosswalk.id,
            source_value="replacement",
            normalized_source_value="replacement",
            canonical_target_value="replacement",
            status="draft",
            supersedes_entry_id=other_entry.id,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_mapping_execution_replay_confidence_lineage_and_trust_signals(db: Session) -> None:
    organization_id, actor, _, version_id, _, raw_reference_id = foundation(
        db,
        "mapping-execution",
    )
    entity_type, template_version = published_entity_mapping(db, organization_id, actor)
    request = MappingRunCreate(
        dataset_version_id=version_id,
        template_version_id=template_version.id,
        idempotency_key="map-customers-001",
        records=[
            MappingInputRecord(
                raw_record_reference_id=raw_reference_id,
                values={"customer_id": "C-001", "customer_name": "  Acme   Energy "},
            )
        ],
    )
    run = mapping_execution_service.execute(db, organization_id, request, actor)
    replay = mapping_execution_service.execute(db, organization_id, request, actor)
    assert replay.id == run.id
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                """
                INSERT INTO mapping_runs (
                    id, organization_id, dataset_version_id, template_version_id,
                    status, idempotency_key, request_fingerprint, input_count,
                    mapped_count, exception_count, rejected_count, created_by_user_id,
                    created_at, updated_at
                ) VALUES (
                    :id, :organization_id, :dataset_version_id, :template_version_id,
                    'created', :idempotency_key, :fingerprint, 0, 0, 0, 0, :actor,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "id": str(uuid4()),
                "organization_id": str(organization_id),
                "dataset_version_id": str(version_id),
                "template_version_id": str(template_version.id),
                "idempotency_key": request.idempotency_key,
                "fingerprint": "0" * 64,
                "actor": str(actor),
            },
        )
        db.commit()
    db.rollback()
    assert run.status == "completed"
    assert run.mapped_count == 1
    entity = db.scalar(
        select(CanonicalEntity).where(
            CanonicalEntity.organization_id == organization_id,
            CanonicalEntity.entity_type_id == entity_type.id,
        )
    )
    assert entity is not None
    assert entity.attributes_json["name"] == "Acme Energy"
    assert entity.mapping_confidence_score == Decimal("1.0000")
    assert (
        db.scalar(
            select(SourceCanonicalLink).where(
                SourceCanonicalLink.organization_id == organization_id,
                SourceCanonicalLink.canonical_target_id == entity.id,
            )
        )
        is not None
    )
    assert (
        len(
            list(
                db.scalars(
                    select(LineageEdge).where(LineageEdge.organization_id == organization_id)
                )
            )
        )
        >= 3
    )
    signals = mapping_trust_signal_service.signals(db, organization_id, run.id)
    assert signals["trust_ready"] is True
    assert signals["mapping_completeness"] == Decimal("1")
    assert signals["mapping_confidence_p10"] == Decimal("1.0000")
    assert signals["mapping_confidence_p50"] == Decimal("1.0000")
    assert signals["mapping_confidence_p90"] == Decimal("1.0000")
    assert signals["lineage_completeness_ratio"] == Decimal("1")

    link = db.scalar(
        select(SourceCanonicalLink).where(
            SourceCanonicalLink.organization_id == organization_id,
            SourceCanonicalLink.canonical_target_id == entity.id,
        )
    )
    assert link is not None
    rule = EntityMatchRule(
        entity_type_id=entity_type.id,
        rule_code="customer_name_candidate",
        match_method="fuzzy_candidate",
        match_fields=["name"],
        confidence_weight=Decimal("0.8"),
        normalization_json={"casefold": True},
    )
    db.add(rule)
    db.flush()
    candidate = EntityMatchCandidate(
        organization_id=organization_id,
        source_canonical_link_id=link.id,
        candidate_entity_id=entity.id,
        match_rule_id=rule.id,
        match_score=Decimal("0.8"),
        status="candidate",
    )
    db.add(candidate)
    db.commit()
    decided = mapping_review_service.decide_candidate(
        db,
        organization_id,
        candidate.id,
        EntityMatchDecision(decision="accepted"),
        actor,
    )
    assert decided.status == "accepted"
    assert decided.decided_at is not None

    conflict = request.model_copy(
        update={
            "records": [
                MappingInputRecord(
                    raw_record_reference_id=raw_reference_id,
                    values={"customer_id": "C-002", "customer_name": "Different"},
                )
            ]
        }
    )
    with pytest.raises(CanonicalMappingServiceError) as exc:
        mapping_execution_service.execute(db, organization_id, conflict, actor)
    assert exc.value.code == "IDEMPOTENCY_CONFLICT"
    assert exc.value.status == 409


def test_entity_resolution_conflicts_and_fuzzy_matches_require_review(db: Session) -> None:
    organization_id, actor, _, version_id, _, raw_reference_id = foundation(
        db,
        "mapping-resolution",
    )
    entity_type, template_version = published_entity_mapping(db, organization_id, actor)
    first = mapping_execution_service.execute(
        db,
        organization_id,
        MappingRunCreate(
            dataset_version_id=version_id,
            template_version_id=template_version.id,
            idempotency_key="resolution-original",
            records=[
                MappingInputRecord(
                    raw_record_reference_id=raw_reference_id,
                    values={"customer_id": "C-001", "customer_name": "Acme Energy"},
                )
            ],
        ),
        actor,
    )
    assert first.status == "completed"
    exact_rule = EntityMatchRule(
        entity_type_id=entity_type.id,
        rule_code="customer_exact_id",
        match_method="exact_identifier",
        match_fields=["canonical_entity_key"],
        confidence_weight=Decimal("1"),
        normalization_json={},
    )
    fuzzy_rule = EntityMatchRule(
        entity_type_id=entity_type.id,
        rule_code="customer_name_fuzzy",
        match_method="fuzzy_candidate",
        match_fields=["name"],
        confidence_weight=Decimal("0.8"),
        normalization_json={"candidate_threshold": "0.80"},
    )
    db.add_all([exact_rule, fuzzy_rule])
    db.commit()

    conflicting_run = mapping_execution_service.execute(
        db,
        organization_id,
        MappingRunCreate(
            dataset_version_id=version_id,
            template_version_id=template_version.id,
            idempotency_key="resolution-conflict",
            records=[
                MappingInputRecord(
                    raw_record_reference_id=raw_reference_id,
                    values={
                        "customer_id": "C-001",
                        "customer_name": "Acme Energy Holdings",
                    },
                )
            ],
        ),
        actor,
    )
    conflicting_result = db.scalar(
        select(MappingRecordResult).where(MappingRecordResult.mapping_run_id == conflicting_run.id)
    )
    assert conflicting_result is not None
    assert conflicting_result.status == "conflicting"
    conflicting_exception = db.scalar(
        select(MappingException).where(
            MappingException.mapping_record_result_id == conflicting_result.id
        )
    )
    assert conflicting_exception is not None
    assert conflicting_exception.exception_type == "conflicting_mapping"

    ambiguous_run = mapping_execution_service.execute(
        db,
        organization_id,
        MappingRunCreate(
            dataset_version_id=version_id,
            template_version_id=template_version.id,
            idempotency_key="resolution-ambiguous",
            records=[
                MappingInputRecord(
                    raw_record_reference_id=raw_reference_id,
                    values={"customer_id": "C-002", "customer_name": "Acme Energi"},
                )
            ],
        ),
        actor,
    )
    ambiguous_result = db.scalar(
        select(MappingRecordResult).where(MappingRecordResult.mapping_run_id == ambiguous_run.id)
    )
    assert ambiguous_result is not None
    assert ambiguous_result.status == "ambiguous"
    candidate = db.scalar(
        select(EntityMatchCandidate).where(
            EntityMatchCandidate.organization_id == organization_id,
            EntityMatchCandidate.source_canonical_link_id
            == db.scalar(
                select(SourceCanonicalLink.id).where(
                    SourceCanonicalLink.mapping_run_id == ambiguous_run.id
                )
            ),
        )
    )
    assert candidate is not None
    assert candidate.status == "candidate"
    assert candidate.match_score >= Decimal("0.80")
    ambiguous_exception = db.scalar(
        select(MappingException).where(
            MappingException.mapping_record_result_id == ambiguous_result.id
        )
    )
    assert ambiguous_exception is not None
    assert ambiguous_exception.exception_type == "ambiguous_entity"
    assert (
        mapping_trust_signal_service.signals(db, organization_id, ambiguous_run.id)["trust_ready"]
        is False
    )
    accepted = mapping_review_service.decide_candidate(
        db,
        organization_id,
        candidate.id,
        EntityMatchDecision(decision="accepted"),
        actor,
    )
    assert accepted.status == "accepted"
    db.refresh(ambiguous_result)
    db.refresh(ambiguous_exception)
    accepted_link = db.scalar(
        select(SourceCanonicalLink).where(
            SourceCanonicalLink.id == candidate.source_canonical_link_id
        )
    )
    assert accepted_link is not None
    assert accepted_link.canonical_target_id == candidate.candidate_entity_id
    assert accepted_link.is_primary is True
    assert ambiguous_result.status == "human_confirmed"
    assert ambiguous_result.canonical_target_id == candidate.candidate_entity_id
    assert ambiguous_exception.status == "resolved"
    assert (
        mapping_trust_signal_service.signals(db, organization_id, ambiguous_run.id)["trust_ready"]
        is True
    )


def test_missing_required_fields_are_hard_readiness_blocks(db: Session) -> None:
    organization_id, actor, _, version_id, _, raw_reference_id = foundation(
        db,
        "mapping-blocked",
    )
    _, template_version = published_entity_mapping(db, organization_id, actor)
    run = mapping_execution_service.execute(
        db,
        organization_id,
        MappingRunCreate(
            dataset_version_id=version_id,
            template_version_id=template_version.id,
            idempotency_key="missing-required",
            records=[
                MappingInputRecord(
                    raw_record_reference_id=raw_reference_id,
                    values={"customer_id": "C-003"},
                )
            ],
        ),
        actor,
    )
    result = db.scalar(
        select(MappingRecordResult).where(MappingRecordResult.mapping_run_id == run.id)
    )
    assert result is not None
    assert result.status == "missing_required_field"
    exception = db.scalar(
        select(MappingException).where(MappingException.mapping_record_result_id == result.id)
    )
    assert exception is not None
    assert mapping_trust_signal_service.signals(db, organization_id, run.id)["trust_ready"] is False
    review = mapping_review_service.review_exception(
        db,
        organization_id,
        exception.id,
        MappingReviewCreate(decision="confirm", notes="Confirmed missing source field"),
        actor,
    )
    with pytest.raises(CanonicalMappingServiceError) as exc:
        mapping_review_service.review_exception(
            db,
            organization_id,
            exception.id,
            MappingReviewCreate(decision="confirm"),
            actor,
        )
    assert exc.value.code == "MAPPING_EXCEPTION_FINAL"
    review.notes = "attempted mutation"
    with pytest.raises(ValueError, match="immutable"):
        db.commit()
    db.rollback()


def test_governed_field_validation_failure_is_a_hard_exception(db: Session) -> None:
    organization_id, actor, _, version_id, _, raw_reference_id = foundation(
        db,
        "mapping-validation",
    )
    _, template_version = published_entity_mapping(
        db,
        organization_id,
        actor,
        name_validation_rule={"pattern": r"^[A-Z][A-Za-z ]+$", "max_length": 40},
    )
    run = mapping_execution_service.execute(
        db,
        organization_id,
        MappingRunCreate(
            dataset_version_id=version_id,
            template_version_id=template_version.id,
            idempotency_key="invalid-customer-name",
            records=[
                MappingInputRecord(
                    raw_record_reference_id=raw_reference_id,
                    values={"customer_id": "C-004", "customer_name": "123-invalid"},
                )
            ],
        ),
        actor,
    )
    result = db.scalar(
        select(MappingRecordResult).where(MappingRecordResult.mapping_run_id == run.id)
    )
    assert result is not None
    assert result.status == "unresolved"
    exception = db.scalar(
        select(MappingException).where(MappingException.mapping_record_result_id == result.id)
    )
    assert exception is not None
    assert exception.exception_type == "validation_failure"
    assert mapping_trust_signal_service.signals(db, organization_id, run.id)["trust_ready"] is False


def test_crosswalk_miss_is_recorded_as_a_specific_hard_exception(db: Session) -> None:
    organization_id, actor, _, version_id, _, raw_reference_id = foundation(
        db,
        "mapping-crosswalk-miss",
    )
    entity_type = canonical_registry_service.create_type(
        db,
        "entity",
        CanonicalTypeCreate(
            type_code="invoice",
            display_name="Invoice",
            scope_type="organization",
            scope_key=f"organization:{organization_id}",
            owner_organization_id=organization_id,
        ),
    )
    assert isinstance(entity_type, CanonicalEntityType)
    status_field = canonical_registry_service.create_field(
        db,
        CanonicalFieldCreate(
            canonical_type_kind="entity",
            canonical_type_id=entity_type.id,
            field_code="status",
            display_name="Status",
            data_type="enum",
            is_required=True,
        ),
        organization_id,
    )
    crosswalk = value_crosswalk_service.create(
        db,
        ValueCrosswalkCreate(
            crosswalk_code="invoice_status",
            name="Invoice status",
            canonical_field_definition_id=status_field.id,
            scope_type="organization",
            scope_key=f"organization:{organization_id}",
            owner_organization_id=organization_id,
        ),
        actor,
        organization_id,
    )
    template = mapping_template_service.create(
        db,
        MappingTemplateCreate(
            template_code="invoice_csv",
            name="Invoice CSV",
            scope_type="organization",
            scope_key=f"organization:{organization_id}",
            owner_organization_id=organization_id,
            target_canonical_type_kind="entity",
            target_canonical_type_id=entity_type.id,
        ),
        actor,
        authorized_organization_id=organization_id,
    )
    template_version = mapping_template_service.create_version(
        db,
        template.id,
        MappingTemplateVersionCreate(
            semantic_version="1.0.0",
            definition_json={"format": "invoice_csv"},
        ),
        actor,
        organization_id,
    )
    field_mapping = mapping_template_service.add_field_mapping(
        db,
        template_version.id,
        FieldMappingCreate(
            source_field_path="invoice_status",
            canonical_field_definition_id=status_field.id,
            sequence=0,
            is_required_for_publication=True,
        ),
        organization_id,
    )
    mapping_template_service.add_transformation(
        db,
        field_mapping.id,
        TransformationCreate(
            sequence=0,
            transformation_type="crosswalk_lookup",
            parameters_json={"crosswalk_id": str(crosswalk.id)},
        ),
        organization_id,
    )
    for target in ("candidate", "validated", "approved", "published"):
        mapping_template_service.transition(
            db,
            template_version.id,
            target,
            actor,
            organization_id,
        )
    run = mapping_execution_service.execute(
        db,
        organization_id,
        MappingRunCreate(
            dataset_version_id=version_id,
            template_version_id=template_version.id,
            idempotency_key="crosswalk-miss",
            records=[
                MappingInputRecord(
                    raw_record_reference_id=raw_reference_id,
                    values={"invoice_status": "UNKNOWN"},
                )
            ],
        ),
        actor,
    )
    result = db.scalar(
        select(MappingRecordResult).where(MappingRecordResult.mapping_run_id == run.id)
    )
    assert result is not None
    assert result.status == "unresolved"
    exception = db.scalar(
        select(MappingException).where(MappingException.mapping_record_result_id == result.id)
    )
    assert exception is not None
    assert exception.exception_type == "crosswalk_miss"
    assert mapping_trust_signal_service.signals(db, organization_id, run.id)["trust_ready"] is False


def test_direct_sql_rejects_cross_tenant_mapping_run_reference(db: Session) -> None:
    organization_id, actor, _, version_id, _, _ = foundation(db, "mapping-direct-sql")
    other_id, _, _, _, _, _ = foundation(db, "mapping-direct-sql-other")
    _, template_version = published_entity_mapping(db, organization_id, actor)
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                """
                INSERT INTO mapping_runs (
                    id, organization_id, dataset_version_id, template_version_id,
                    status, idempotency_key, request_fingerprint, input_count,
                    mapped_count, exception_count, rejected_count, created_by_user_id,
                    created_at, updated_at
                ) VALUES (
                    :id, :organization_id, :dataset_version_id, :template_version_id,
                    'created', 'cross-tenant', :fingerprint, 0, 0, 0, 0, :actor,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "id": str(uuid4()),
                "organization_id": str(other_id),
                "dataset_version_id": str(version_id),
                "template_version_id": str(template_version.id),
                "fingerprint": "0" * 64,
                "actor": str(actor),
            },
        )
        db.commit()
    db.rollback()


def test_governed_profiles_and_mapping_readiness_rules_are_registered() -> None:
    assert {profile.profile_code for profile in CANONICAL_MAPPING_PROFILES} == {
        "job_to_cash",
        "oilfield_services",
    }
    codes = {definition.code for definition in default_rule_registry().list()}
    assert {
        "mapping_completeness_below_threshold",
        "mapping_unresolved_ratio_exceeded",
        "mapping_ambiguous_ratio_exceeded",
        "mapping_conflict_count_exceeded",
        "mapping_required_field_failures",
        "mapping_lineage_completeness_below_threshold",
    } <= codes


def test_deterministic_transformation_contracts(db: Session) -> None:
    transform = mapping_execution_service._transform
    unit = MappingTransformation(
        field_mapping_id=uuid4(),
        sequence=0,
        transformation_type="unit_convert",
        parameters_json={"factor": "0.3048"},
    )
    assert transform(db, uuid4(), "10", unit) == (Decimal("3.0480"), Decimal("1"))

    currency = MappingTransformation(
        field_mapping_id=uuid4(),
        sequence=0,
        transformation_type="currency_normalize",
        parameters_json={},
    )
    assert transform(db, uuid4(), " usd ", currency) == ("USD", Decimal("1"))

    parsed = MappingTransformation(
        field_mapping_id=uuid4(),
        sequence=0,
        transformation_type="date_parse",
        parameters_json={},
    )
    timestamp, confidence = transform(db, uuid4(), "2026-08-04T12:30:00Z", parsed)
    assert timestamp == datetime(2026, 8, 4, 12, 30, tzinfo=UTC)
    assert confidence == Decimal("1")

    timezone = MappingTransformation(
        field_mapping_id=uuid4(),
        sequence=0,
        transformation_type="timezone_normalize",
        parameters_json={"source_timezone": "America/Chicago"},
    )
    normalized, _ = transform(db, uuid4(), "2026-08-04T07:30:00", timezone)
    assert normalized == datetime(2026, 8, 4, 12, 30, tzinfo=UTC)

    custom = MappingTransformation(
        field_mapping_id=uuid4(),
        sequence=0,
        transformation_type="custom_function",
        parameters_json={},
    )
    with pytest.raises(ValueError, match="separately governed"):
        transform(db, uuid4(), "value", custom)

    derived = MappingTransformation(
        field_mapping_id=uuid4(),
        sequence=0,
        transformation_type="derive",
        parameters_json={"format": "{first_name} {last_name}"},
    )
    assert transform(
        db,
        uuid4(),
        None,
        derived,
        {"first_name": "Acme", "last_name": "Energy"},
    ) == ("Acme Energy", Decimal("1"))


def test_canonical_event_metric_temporal_and_tenant_contracts(db: Session) -> None:
    organization_id, _, _, _, _, _ = foundation(db, "mapping-temporal")
    other_id, _, _, _, _, _ = foundation(db, "mapping-temporal-other")
    entity_type = canonical_registry_service.create_type(
        db,
        "entity",
        CanonicalTypeCreate(
            type_code="asset",
            display_name="Asset",
            scope_type="organization",
            scope_key=f"organization:{organization_id}",
            owner_organization_id=organization_id,
        ),
    )
    assert isinstance(entity_type, CanonicalEntityType)
    event_type = canonical_registry_service.create_type(
        db,
        "event",
        CanonicalTypeCreate(
            type_code="maintenance_completed",
            display_name="Maintenance completed",
            scope_type="organization",
            scope_key=f"organization:{organization_id}",
            owner_organization_id=organization_id,
            applicable_entity_type_id=entity_type.id,
        ),
    )
    metric_type = canonical_registry_service.create_type(
        db,
        "metric",
        CanonicalTypeCreate(
            type_code="operating_hours",
            display_name="Operating hours",
            scope_type="organization",
            scope_key=f"organization:{organization_id}",
            owner_organization_id=organization_id,
            unit_dimension="time",
            default_unit="hour",
            aggregation_hint="sum",
        ),
    )
    assert isinstance(event_type, CanonicalEventType)
    assert isinstance(metric_type, CanonicalMetricType)
    entity = CanonicalEntity(
        organization_id=organization_id,
        entity_type_id=entity_type.id,
        canonical_entity_key="ASSET-001",
        attributes_json={"name": "Pump 1"},
        survivorship_source_link_id=None,
        content_fingerprint="1" * 64,
        mapping_confidence_score=Decimal("1"),
        confidence_method_code="deterministic",
        confidence_method_version="1.0",
        confidence_components={},
        confidence_interpretation="Exact asset identifier.",
        confidence_limitations=None,
    )
    db.add(entity)
    db.flush()
    occurrence = datetime(2026, 8, 1, 12, tzinfo=UTC)
    detected = datetime(2026, 8, 4, 12, tzinfo=UTC)
    event = CanonicalEvent(
        organization_id=organization_id,
        canonical_entity_id=entity.id,
        event_type_id=event_type.id,
        occurrence_start=occurrence,
        occurrence_end=occurrence,
        occurrence_precision="hour",
        source_reported_timestamp=occurrence,
        first_detected_at=detected,
        last_detected_at=detected,
        actor_reference="TECH-001",
        mapping_status="mapped",
        attributes_json={"work_order": "WO-1"},
        content_fingerprint="2" * 64,
        mapping_confidence_score=Decimal("0.9"),
        confidence_method_code="governed_mapping",
        confidence_method_version="1.0",
        confidence_components={},
        confidence_interpretation="Mapped maintenance event.",
        confidence_limitations=None,
    )
    metric = CanonicalMetric(
        organization_id=organization_id,
        canonical_entity_id=entity.id,
        metric_type_id=metric_type.id,
        measured_value=Decimal("125.5"),
        unit="hour",
        currency=None,
        occurrence_start=occurrence,
        occurrence_end=None,
        occurrence_precision="hour",
        source_reported_timestamp=occurrence,
        first_detected_at=detected,
        last_detected_at=detected,
        mapping_status="mapped",
        attributes_json={},
        content_fingerprint="3" * 64,
        mapping_confidence_score=Decimal("0.95"),
        confidence_method_code="governed_mapping",
        confidence_method_version="1.0",
        confidence_components={},
        confidence_interpretation="Mapped operating-hours metric.",
        confidence_limitations=None,
    )
    db.add_all([event, metric])
    db.commit()
    assert event.occurrence_start < event.first_detected_at
    assert metric.source_reported_timestamp == occurrence

    db.add(
        CanonicalEvent(
            organization_id=other_id,
            canonical_entity_id=entity.id,
            event_type_id=event_type.id,
            occurrence_start=occurrence,
            occurrence_end=None,
            occurrence_precision="instant",
            source_reported_timestamp=occurrence,
            first_detected_at=detected,
            last_detected_at=detected,
            actor_reference=None,
            mapping_status="mapped",
            attributes_json={},
            content_fingerprint="4" * 64,
            mapping_confidence_score=Decimal("1"),
            confidence_method_code="deterministic",
            confidence_method_version="1.0",
            confidence_components={},
            confidence_interpretation=None,
            confidence_limitations=None,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
