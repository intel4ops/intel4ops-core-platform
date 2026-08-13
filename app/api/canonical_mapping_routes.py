from datetime import datetime
from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.auth.authorization import (
    OrganizationAccess,
    require_platform_admin,
)
from app.auth.commercial import require_commercial_entitlement
from app.auth.identity import AuthenticatedUser
from app.auth.permissions import (
    INGESTION_ADMIN_ROLES,
    INGESTION_OPERATION_ROLES,
    INGESTION_READ_ROLES,
    OIKB_AUTHOR_ROLES,
)
from app.db.session import get_db
from app.models.canonical_mapping import MappingLifecycleStatus, MappingRunStatus
from app.schemas.canonical_mapping import (
    CanonicalEntityRead,
    CanonicalEventRead,
    CanonicalFieldCreate,
    CanonicalFieldRead,
    CanonicalMetricRead,
    CanonicalTypeCreate,
    CanonicalTypeRead,
    EntityMatchDecision,
    FieldMappingCreate,
    FieldMappingRead,
    FieldMappingSuggestionListRead,
    LineagePathRead,
    MappingExceptionRead,
    MappingReviewCreate,
    MappingRunCreate,
    MappingRunPage,
    MappingRunRead,
    MappingRunRetryCreate,
    MappingTemplateCreate,
    MappingTemplateRead,
    MappingTemplateVersionConfigurationRead,
    MappingTemplateVersionCreate,
    MappingTemplateVersionRead,
    SourceSchemaDiscover,
    SourceSchemaRead,
    TransformationCreate,
    ValueCrosswalkCreate,
    ValueCrosswalkEntryCreate,
)
from app.services.canonical_mapping_service import (
    CanonicalMappingServiceError,
    canonical_record_service,
    canonical_registry_service,
    entity_resolution_service,
    field_mapping_suggestion_service,
    mapping_execution_service,
    mapping_review_service,
    mapping_template_service,
    mapping_trust_signal_service,
    schema_discovery_service,
    value_crosswalk_service,
)

catalog_router = APIRouter(
    prefix="/api/v1/canonical-mapping",
    tags=["canonical-mapping-governance"],
)
tenant_router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/canonical-mapping",
    tags=["canonical-mapping"],
)


def _raise(exc: CanonicalMappingServiceError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status,
        detail={"code": exc.code, "message": str(exc)},
    ) from exc


@catalog_router.get("/canonical-types", response_model=list[CanonicalTypeRead])
def catalog_types(
    kind: str = Query(pattern="^(entity|event|metric)$"),
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_platform_admin),
) -> object:
    try:
        return canonical_registry_service.list_types(db, kind, None)
    except CanonicalMappingServiceError as exc:
        _raise(exc)


@catalog_router.post("/canonical-types", response_model=CanonicalTypeRead, status_code=201)
def create_catalog_type(
    payload: CanonicalTypeCreate,
    kind: str = Query(pattern="^(entity|event|metric)$"),
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_platform_admin),
) -> object:
    try:
        return canonical_registry_service.create_type(db, kind, payload)
    except CanonicalMappingServiceError as exc:
        _raise(exc)


@catalog_router.post(
    "/canonical-fields",
    response_model=CanonicalFieldRead,
    status_code=201,
)
def create_catalog_field(
    payload: CanonicalFieldCreate,
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_platform_admin),
) -> object:
    try:
        return canonical_registry_service.create_field(db, payload)
    except CanonicalMappingServiceError as exc:
        _raise(exc)


@catalog_router.post(
    "/mapping-templates",
    response_model=MappingTemplateRead,
    status_code=201,
)
def create_catalog_template(
    payload: MappingTemplateCreate,
    db: Session = Depends(get_db),
    actor: AuthenticatedUser = Depends(require_platform_admin),
) -> object:
    try:
        return mapping_template_service.create(db, payload, actor.user_id)
    except CanonicalMappingServiceError as exc:
        _raise(exc)


@tenant_router.get("/canonical-types", response_model=list[CanonicalTypeRead])
def tenant_types(
    organization_id: UUID,
    kind: str = Query(pattern="^(entity|event|metric)$"),
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_commercial_entitlement("connect.canonical_mapping", *INGESTION_READ_ROLES)
    ),
) -> object:
    try:
        return canonical_registry_service.list_types(db, kind, organization_id)
    except CanonicalMappingServiceError as exc:
        _raise(exc)


@tenant_router.post(
    "/source-schemas/discover",
    response_model=SourceSchemaRead,
    status_code=201,
)
def discover_schema(
    organization_id: UUID,
    payload: SourceSchemaDiscover,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_commercial_entitlement("connect.canonical_mapping", *INGESTION_OPERATION_ROLES)
    ),
) -> object:
    try:
        return schema_discovery_service.discover(db, organization_id, payload)
    except CanonicalMappingServiceError as exc:
        _raise(exc)


@tenant_router.get(
    "/source-schemas/{dataset_version_id}",
    response_model=list[SourceSchemaRead],
)
def schemas_for_version(
    organization_id: UUID,
    dataset_version_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_commercial_entitlement("connect.canonical_mapping", *INGESTION_READ_ROLES)
    ),
) -> object:
    return schema_discovery_service.for_dataset_version(db, organization_id, dataset_version_id)


@tenant_router.get(
    "/source-schemas/{source_schema_id}/field-mapping-suggestions",
    response_model=FieldMappingSuggestionListRead,
)
def field_mapping_suggestions(
    organization_id: UUID,
    source_schema_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_commercial_entitlement("connect.canonical_mapping", *INGESTION_READ_ROLES)
    ),
) -> object:
    try:
        return field_mapping_suggestion_service.suggest(db, organization_id, source_schema_id)
    except CanonicalMappingServiceError as exc:
        _raise(exc)


@tenant_router.post(
    "/mapping-templates",
    response_model=MappingTemplateRead,
    status_code=201,
)
def create_tenant_template(
    organization_id: UUID,
    payload: MappingTemplateCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_commercial_entitlement("connect.canonical_mapping", *INGESTION_ADMIN_ROLES)
    ),
) -> object:
    try:
        return mapping_template_service.create(
            db,
            payload,
            access.user.user_id,
            authorized_organization_id=organization_id,
        )
    except CanonicalMappingServiceError as exc:
        _raise(exc)


@tenant_router.get("/mapping-templates", response_model=list[MappingTemplateRead])
def list_mapping_templates(
    organization_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_commercial_entitlement("connect.canonical_mapping", *INGESTION_READ_ROLES)
    ),
) -> object:
    return mapping_template_service.list_templates(db, organization_id)


@tenant_router.get("/mapping-templates/{template_id}", response_model=MappingTemplateRead)
def get_mapping_template(
    organization_id: UUID,
    template_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_commercial_entitlement("connect.canonical_mapping", *INGESTION_READ_ROLES)
    ),
) -> object:
    try:
        return mapping_template_service.get_template(db, organization_id, template_id)
    except CanonicalMappingServiceError as exc:
        _raise(exc)


@tenant_router.get(
    "/mapping-templates/{template_id}/versions",
    response_model=list[MappingTemplateVersionRead],
)
def list_mapping_template_versions(
    organization_id: UUID,
    template_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_commercial_entitlement("connect.canonical_mapping", *INGESTION_READ_ROLES)
    ),
) -> object:
    try:
        return mapping_template_service.list_versions(db, organization_id, template_id)
    except CanonicalMappingServiceError as exc:
        _raise(exc)


@tenant_router.get(
    "/mapping-template-versions/{version_id}",
    response_model=MappingTemplateVersionConfigurationRead,
)
def get_mapping_template_version(
    organization_id: UUID,
    version_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_commercial_entitlement("connect.canonical_mapping", *INGESTION_READ_ROLES)
    ),
) -> object:
    try:
        return mapping_template_service.get_version_configuration(db, organization_id, version_id)
    except CanonicalMappingServiceError as exc:
        _raise(exc)


@tenant_router.post(
    "/mapping-templates/{template_id}/versions",
    response_model=MappingTemplateVersionRead,
    status_code=201,
)
def create_template_version(
    organization_id: UUID,
    template_id: UUID,
    payload: MappingTemplateVersionCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_commercial_entitlement("connect.canonical_mapping", *OIKB_AUTHOR_ROLES)
    ),
) -> object:
    try:
        return mapping_template_service.create_version(
            db,
            template_id,
            payload,
            access.user.user_id,
            organization_id,
        )
    except CanonicalMappingServiceError as exc:
        _raise(exc)


@tenant_router.post(
    "/mapping-template-versions/{version_id}/field-mappings",
    response_model=FieldMappingRead,
    status_code=201,
)
def add_field_mapping(
    organization_id: UUID,
    version_id: UUID,
    payload: FieldMappingCreate,
    response: Response,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_commercial_entitlement("connect.canonical_mapping", *OIKB_AUTHOR_ROLES)
    ),
) -> object:
    try:
        result = mapping_template_service.add_field_mapping_with_status(
            db,
            version_id,
            payload,
            organization_id,
        )
        if not result.created:
            response.status_code = 200
        return result.field_mapping
    except CanonicalMappingServiceError as exc:
        _raise(exc)


@tenant_router.post(
    "/field-mappings/{field_mapping_id}/transformations",
    status_code=201,
)
def add_transformation(
    organization_id: UUID,
    field_mapping_id: UUID,
    payload: TransformationCreate,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_commercial_entitlement("connect.canonical_mapping", *OIKB_AUTHOR_ROLES)
    ),
) -> object:
    try:
        return mapping_template_service.add_transformation(
            db,
            field_mapping_id,
            payload,
            organization_id,
        )
    except CanonicalMappingServiceError as exc:
        _raise(exc)


@tenant_router.post(
    "/mapping-template-versions/{version_id}/transition/{target}",
    response_model=MappingTemplateVersionRead,
)
def transition_template_version(
    organization_id: UUID,
    version_id: UUID,
    target: MappingLifecycleStatus,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_commercial_entitlement("connect.canonical_mapping", *INGESTION_ADMIN_ROLES)
    ),
) -> object:
    try:
        return mapping_template_service.transition(
            db,
            version_id,
            target.value,
            access.user.user_id,
            organization_id,
        )
    except CanonicalMappingServiceError as exc:
        _raise(exc)


@tenant_router.post("/value-crosswalks", status_code=201)
def create_crosswalk(
    organization_id: UUID,
    payload: ValueCrosswalkCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_commercial_entitlement("connect.canonical_mapping", *INGESTION_ADMIN_ROLES)
    ),
) -> object:
    try:
        return value_crosswalk_service.create(
            db,
            payload,
            access.user.user_id,
            organization_id,
        )
    except CanonicalMappingServiceError as exc:
        _raise(exc)


@tenant_router.post("/value-crosswalks/{crosswalk_id}/entries", status_code=201)
def add_crosswalk_entry(
    organization_id: UUID,
    crosswalk_id: UUID,
    payload: ValueCrosswalkEntryCreate,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_commercial_entitlement("connect.canonical_mapping", *OIKB_AUTHOR_ROLES)
    ),
) -> object:
    try:
        return value_crosswalk_service.add_entry(db, crosswalk_id, payload, organization_id)
    except CanonicalMappingServiceError as exc:
        _raise(exc)


@tenant_router.post("/value-crosswalk-entries/{entry_id}/approve")
def approve_crosswalk_entry(
    organization_id: UUID,
    entry_id: UUID,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_commercial_entitlement("connect.canonical_mapping", *INGESTION_ADMIN_ROLES)
    ),
) -> object:
    try:
        return value_crosswalk_service.approve(
            db,
            entry_id,
            access.user.user_id,
            organization_id,
        )
    except CanonicalMappingServiceError as exc:
        _raise(exc)


@tenant_router.post("/mapping-runs", response_model=MappingRunRead, status_code=202)
def execute_mapping(
    organization_id: UUID,
    payload: MappingRunCreate,
    response: Response,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_commercial_entitlement("connect.canonical_mapping", *INGESTION_OPERATION_ROLES)
    ),
) -> object:
    try:
        run, created = mapping_execution_service.submit(
            db,
            organization_id,
            payload,
            access.user.user_id,
        )
        if not created:
            response.status_code = 200
        return run
    except CanonicalMappingServiceError as exc:
        _raise(exc)


@tenant_router.get("/mapping-runs", response_model=MappingRunPage)
def list_mapping_runs(
    organization_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    status: MappingRunStatus | None = None,
    template_version_id: UUID | None = None,
    dataset_version_id: UUID | None = None,
    source_schema_id: UUID | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    retry_of_run_id: UUID | None = None,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_commercial_entitlement("connect.canonical_mapping", *INGESTION_READ_ROLES)
    ),
) -> object:
    return mapping_execution_service.list_runs(
        db,
        organization_id,
        page,
        page_size,
        status=status.value if status else None,
        template_version_id=template_version_id,
        dataset_version_id=dataset_version_id,
        source_schema_id=source_schema_id,
        created_from=created_from,
        created_to=created_to,
        retry_of_run_id=retry_of_run_id,
    )


@tenant_router.post(
    "/mapping-runs/{mapping_run_id}/retry", response_model=MappingRunRead, status_code=202
)
def retry_mapping_run(
    organization_id: UUID,
    mapping_run_id: UUID,
    payload: MappingRunRetryCreate,
    response: Response,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_commercial_entitlement("connect.canonical_mapping", *INGESTION_OPERATION_ROLES)
    ),
) -> object:
    try:
        run, created = mapping_execution_service.retry(
            db, organization_id, mapping_run_id, payload, access.user.user_id
        )
        if not created:
            response.status_code = 200
        return run
    except CanonicalMappingServiceError as exc:
        _raise(exc)


@tenant_router.get("/mapping-runs/{mapping_run_id}", response_model=MappingRunRead)
def mapping_run(
    organization_id: UUID,
    mapping_run_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_commercial_entitlement("connect.canonical_mapping", *INGESTION_READ_ROLES)
    ),
) -> object:
    try:
        return mapping_execution_service.get(db, organization_id, mapping_run_id)
    except CanonicalMappingServiceError as exc:
        _raise(exc)


@tenant_router.get(
    "/mapping-runs/{mapping_run_id}/exceptions",
    response_model=list[MappingExceptionRead],
)
def mapping_exceptions(
    organization_id: UUID,
    mapping_run_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_commercial_entitlement("connect.canonical_mapping", *INGESTION_READ_ROLES)
    ),
) -> object:
    try:
        return mapping_execution_service.exceptions(db, organization_id, mapping_run_id)
    except CanonicalMappingServiceError as exc:
        _raise(exc)


@tenant_router.post("/mapping-exceptions/{exception_id}/review", status_code=201)
def review_exception(
    organization_id: UUID,
    exception_id: UUID,
    payload: MappingReviewCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_commercial_entitlement("connect.canonical_mapping", *INGESTION_OPERATION_ROLES)
    ),
) -> object:
    try:
        return mapping_review_service.review_exception(
            db,
            organization_id,
            exception_id,
            payload,
            access.user.user_id,
        )
    except CanonicalMappingServiceError as exc:
        _raise(exc)


@tenant_router.get("/entity-match-candidates")
def entity_match_candidates(
    organization_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_commercial_entitlement("connect.canonical_mapping", *INGESTION_READ_ROLES)
    ),
) -> object:
    return entity_resolution_service.candidates(db, organization_id)


@tenant_router.post("/entity-match-candidates/{candidate_id}/decide")
def decide_match_candidate(
    organization_id: UUID,
    candidate_id: UUID,
    payload: EntityMatchDecision,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(
        require_commercial_entitlement("connect.canonical_mapping", *INGESTION_OPERATION_ROLES)
    ),
) -> object:
    try:
        return mapping_review_service.decide_candidate(
            db,
            organization_id,
            candidate_id,
            payload,
            access.user.user_id,
        )
    except CanonicalMappingServiceError as exc:
        _raise(exc)


@tenant_router.get("/canonical-entities/{entity_id}", response_model=CanonicalEntityRead)
def canonical_entity(
    organization_id: UUID,
    entity_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_commercial_entitlement("connect.canonical_mapping", *INGESTION_READ_ROLES)
    ),
) -> object:
    try:
        return canonical_record_service.entity(db, organization_id, entity_id)
    except CanonicalMappingServiceError as exc:
        _raise(exc)


@tenant_router.get("/canonical-events", response_model=list[CanonicalEventRead])
def canonical_events(
    organization_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_commercial_entitlement("connect.canonical_mapping", *INGESTION_READ_ROLES)
    ),
) -> object:
    return canonical_record_service.events(db, organization_id)


@tenant_router.get("/canonical-metrics", response_model=list[CanonicalMetricRead])
def canonical_metrics(
    organization_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_commercial_entitlement("connect.canonical_mapping", *INGESTION_READ_ROLES)
    ),
) -> object:
    return canonical_record_service.metrics(db, organization_id)


@tenant_router.get(
    "/canonical-entities/{entity_id}/lineage",
    response_model=LineagePathRead,
)
def canonical_lineage(
    organization_id: UUID,
    entity_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_commercial_entitlement("connect.canonical_mapping", *INGESTION_READ_ROLES)
    ),
) -> object:
    try:
        node_ids, relationships = canonical_record_service.lineage(
            db,
            organization_id,
            entity_id,
        )
        return LineagePathRead(
            canonical_target_id=entity_id,
            node_ids=node_ids,
            relationship_types=relationships,
        )
    except CanonicalMappingServiceError as exc:
        _raise(exc)


@tenant_router.get("/mapping-runs/{mapping_run_id}/trust-signals")
def mapping_trust_signals(
    organization_id: UUID,
    mapping_run_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(
        require_commercial_entitlement("connect.canonical_mapping", *INGESTION_READ_ROLES)
    ),
) -> object:
    try:
        return mapping_trust_signal_service.signals(db, organization_id, mapping_run_id)
    except CanonicalMappingServiceError as exc:
        _raise(exc)
