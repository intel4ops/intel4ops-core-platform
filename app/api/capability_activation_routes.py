from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.authorization import OrganizationAccess, require_organization_roles
from app.auth.permissions import ANALYSIS_CASE_READ_ROLES
from app.db.session import get_db
from app.schemas.intelligence_activation import (
    ActivationDecisionListRead,
    ActivationDecisionRead,
    CapabilityListRead,
    CapabilityRead,
    ShadowComparisonSummaryRead,
)
from app.services.analysis_case_capability_service import analysis_case_capability_service

router = APIRouter(prefix="/api/v1/organizations/{organization_id}")


@router.get("/intelligence-capabilities", response_model=CapabilityListRead)
def list_intelligence_capabilities(
    organization_id: UUID,
    access: OrganizationAccess = Depends(require_organization_roles(*ANALYSIS_CASE_READ_ROLES)),
) -> object:
    capabilities = analysis_case_capability_service.list_capabilities()
    return CapabilityListRead(
        capabilities=[
            CapabilityRead(
                pack_code=c.pack_code,
                rule_code=c.rule_code,
                version=c.version,
                required_domains=sorted(c.required_domains),
                required_canonical_fields=sorted(c.required_canonical_fields),
                required_canonical_entities=sorted(c.required_canonical_entities),
                required_relationships=sorted(c.required_relationships),
                required_activities=sorted(c.required_activities),
                required_states=sorted(c.required_states),
                required_canonical_measures=sorted(c.required_canonical_measures),
                currency_behavior=c.currency_behavior,
                unit_behavior=c.unit_behavior,
                activation_policy_version=c.activation_policy_version,
                is_disabled=c.is_disabled,
            )
            for c in capabilities
        ]
    )


@router.get(
    "/analysis-cases/{case_id}/activation-decisions", response_model=ActivationDecisionListRead
)
def list_case_activation_decisions(
    organization_id: UUID,
    case_id: UUID,
    run_id: UUID | None = None,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ANALYSIS_CASE_READ_ROLES)),
) -> object:
    resolved_run_id, decisions = analysis_case_capability_service.list_activation_decisions(
        db, organization_id, case_id, run_id
    )
    return ActivationDecisionListRead(
        analysis_case_id=case_id,
        run_id=resolved_run_id,
        decisions=[ActivationDecisionRead.model_validate(d) for d in decisions],
    )


@router.get(
    "/analysis-cases/{case_id}/shadow-comparison", response_model=ShadowComparisonSummaryRead
)
def get_case_shadow_comparison(
    organization_id: UUID,
    case_id: UUID,
    run_id: UUID | None = None,
    db: Session = Depends(get_db),
    access: OrganizationAccess = Depends(require_organization_roles(*ANALYSIS_CASE_READ_ROLES)),
) -> object:
    resolved_run_id, shadow_decisions = analysis_case_capability_service.shadow_comparison_summary(
        db, organization_id, case_id, run_id
    )
    agree_count = sum(1 for d in shadow_decisions if d.agree)
    return ShadowComparisonSummaryRead(
        analysis_case_id=case_id,
        run_id=resolved_run_id,
        packs_evaluated=len(shadow_decisions),
        agree_count=agree_count,
        disagree_count=len(shadow_decisions) - agree_count,
        decisions=[ActivationDecisionRead.model_validate(d) for d in shadow_decisions],
    )
