from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess, require_organization_roles
from app.auth.commercial import require_commercial_entitlement
from app.auth.permissions import INTELLIGENCE_EXECUTION_ROLES, INTELLIGENCE_READ_ROLES
from app.db.session import get_db
from app.registries.calculation_registry import DefinitionNotFoundError
from app.schemas.intelligence import (
    DefinitionRead,
    IntelligenceExecutionCreate,
    IntelligenceExecutionRead,
)
from app.services.intelligence_service import (
    IntelligenceNotFoundError,
    intelligence_execution_service,
)

router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}",
    dependencies=[
        Depends(require_commercial_entitlement("intelligence.arithmetic", *INTELLIGENCE_READ_ROLES))
    ],
)


@router.post(
    "/intelligence-executions",
    response_model=IntelligenceExecutionRead,
    status_code=status.HTTP_201_CREATED,
)
def execute_intelligence(
    organization_id: UUID,
    payload: IntelligenceExecutionCreate,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*INTELLIGENCE_EXECUTION_ROLES)),
) -> object:
    try:
        return intelligence_execution_service.execute(
            db, organization_id, payload, access.user.user_id
        )
    except DefinitionNotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntelligenceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/intelligence-executions/{execution_id}",
    response_model=IntelligenceExecutionRead,
)
def get_intelligence_execution(
    organization_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*INTELLIGENCE_READ_ROLES)),
) -> object:
    try:
        return intelligence_execution_service.get(db, organization_id, execution_id)
    except IntelligenceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/intelligence-executions",
    response_model=list[IntelligenceExecutionRead],
)
def list_intelligence_executions(
    organization_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    _: OrganizationAccess = Depends(require_organization_roles(*INTELLIGENCE_READ_ROLES)),
) -> object:
    return intelligence_execution_service.list(db, organization_id, offset=offset, limit=limit)


def _definition_read(definition: object, operation: str) -> DefinitionRead:
    return DefinitionRead(
        code=definition.code,  # type: ignore[attr-defined]
        version=definition.version,  # type: ignore[attr-defined]
        name=definition.name,  # type: ignore[attr-defined]
        description=definition.description,  # type: ignore[attr-defined]
        operation=operation,
        required_parameters=list(definition.required_parameters),  # type: ignore[attr-defined]
        analytical_level=definition.analytical_level,  # type: ignore[attr-defined]
        status=definition.status,  # type: ignore[attr-defined]
        canonical_fields=list(getattr(definition, "canonical_fields", ())),
        evidence_contract=getattr(definition, "evidence_contract", None),
        unit_policy=getattr(definition, "unit_policy", None),
        currency_policy=getattr(definition, "currency_policy", None),
        scope_correction=getattr(definition, "scope_correction", None),
        domain_owner=getattr(definition, "domain_owner", None),
    )


@router.get("/calculation-definitions", response_model=list[DefinitionRead])
def list_calculation_definitions(
    organization_id: UUID,
    _: OrganizationAccess = Depends(require_organization_roles(*INTELLIGENCE_READ_ROLES)),
) -> list[DefinitionRead]:
    del organization_id
    return [
        _definition_read(definition, definition.operation.value)
        for definition in intelligence_execution_service.calculations.list()
    ]


@router.get("/rule-definitions", response_model=list[DefinitionRead])
def list_rule_definitions(
    organization_id: UUID,
    _: OrganizationAccess = Depends(require_organization_roles(*INTELLIGENCE_READ_ROLES)),
) -> list[DefinitionRead]:
    del organization_id
    return [
        _definition_read(definition, definition.operator.value)
        for definition in intelligence_execution_service.rules.list()
    ]
