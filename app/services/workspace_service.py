from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.access import InvitationStatus, OrganizationInvitation
from app.models.entities import (
    MembershipRole,
    MembershipStatus,
    Organization,
    OrganizationMembership,
)
from app.models.ingestion import Dataset, IngestionBatch
from app.models.trust import AnalyticalReadinessDecision, ReadinessStatus
from app.models.workspace import OrganizationChallenge, OrganizationObjective, OrganizationSystem
from app.registries.challenge_registry import is_valid_challenge_code
from app.registries.objective_registry import is_valid_objective_code
from app.registries.system_registry import get_system, is_valid_system_code
from app.schemas.workspace import (
    OrganizationSystemRead,
    OrganizationSystemSelection,
    SetupProgressRead,
    TeamSummaryRead,
    WorkspaceSummaryRead,
)
from app.services.organization_service import OrganizationNotFoundError, OrganizationService

# UI-only persona labels. Never persisted, never used for authorization --
# authorization always runs on the underlying MembershipRole. platform_admin
# is intentionally absent: it is not a customer-facing organization persona.
PERSONA_LABELS: dict[str, str] = {
    MembershipRole.ORGANIZATION_ADMIN.value: "Admin",
    MembershipRole.OPERATOR.value: "Operations",
    MembershipRole.RECOVERY_MANAGER.value: "Finance",
    MembershipRole.ANALYST.value: "Analyst",
    MembershipRole.VIEWER.value: "Viewer",
}

_NEXT_STEP_LABELS: dict[str, str] = {
    "profile": "Complete your company profile",
    "industry": "Select your industry",
    "objectives": "Choose your top priorities",
    "challenges": "Tell us about your operational challenges",
    "systems": "Tell us what systems you use",
    "team": "Invite your team",
}

organization_service = OrganizationService()


class WorkspaceServiceError(ValueError):
    def __init__(self, message: str, *, code: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def persona_for_role(role: str) -> str:
    return PERSONA_LABELS.get(role, role.replace("_", " ").title())


def _get_organization(db: Session, organization_id: UUID) -> Organization:
    try:
        return organization_service.get(db, organization_id)
    except OrganizationNotFoundError as exc:
        raise WorkspaceServiceError(
            "Organization not found", code="organization_not_found", status=404
        ) from exc


def _lock_organization(db: Session, organization_id: UUID) -> Organization:
    """Row-locks the organization before a replace-set read-modify-write so
    two concurrent PUTs for the same org serialize instead of racing (the
    second would otherwise read a stale "existing" set and silently
    resurrect a selection the first request just removed)."""
    organization = db.scalar(
        select(Organization).where(Organization.id == organization_id).with_for_update()
    )
    if organization is None:
        raise WorkspaceServiceError(
            "Organization not found", code="organization_not_found", status=404
        )
    return organization


# ---------------------------------------------------------------------------
# Objectives
# ---------------------------------------------------------------------------
def list_objectives(db: Session, organization_id: UUID) -> list[OrganizationObjective]:
    statement = (
        select(OrganizationObjective)
        .where(OrganizationObjective.organization_id == organization_id)
        .order_by(OrganizationObjective.selected_at)
    )
    return list(db.scalars(statement).all())


def replace_objectives(
    db: Session, organization_id: UUID, codes: list[str], actor_user_id: UUID
) -> list[OrganizationObjective]:
    for code in codes:
        if not is_valid_objective_code(code):
            raise WorkspaceServiceError(
                f"'{code}' is not a governed objective code",
                code="invalid_registry_code",
                status=400,
            )
    _lock_organization(db, organization_id)
    existing = {item.objective_code: item for item in list_objectives(db, organization_id)}
    desired = set(codes)
    for code, row in existing.items():
        if code not in desired:
            db.delete(row)
    for code in desired - existing.keys():
        db.add(
            OrganizationObjective(
                organization_id=organization_id,
                objective_code=code,
                selected_by_user_id=actor_user_id,
            )
        )
    db.commit()
    return list_objectives(db, organization_id)


# ---------------------------------------------------------------------------
# Challenges
# ---------------------------------------------------------------------------
def list_challenges(db: Session, organization_id: UUID) -> list[OrganizationChallenge]:
    statement = (
        select(OrganizationChallenge)
        .where(OrganizationChallenge.organization_id == organization_id)
        .order_by(OrganizationChallenge.selected_at)
    )
    return list(db.scalars(statement).all())


def replace_challenges(
    db: Session, organization_id: UUID, codes: list[str], actor_user_id: UUID
) -> list[OrganizationChallenge]:
    for code in codes:
        if not is_valid_challenge_code(code):
            raise WorkspaceServiceError(
                f"'{code}' is not a governed challenge code",
                code="invalid_registry_code",
                status=400,
            )
    _lock_organization(db, organization_id)
    existing = {item.challenge_code: item for item in list_challenges(db, organization_id)}
    desired = set(codes)
    for code, row in existing.items():
        if code not in desired:
            db.delete(row)
    for code in desired - existing.keys():
        db.add(
            OrganizationChallenge(
                organization_id=organization_id,
                challenge_code=code,
                selected_by_user_id=actor_user_id,
            )
        )
    db.commit()
    return list_challenges(db, organization_id)


# ---------------------------------------------------------------------------
# Systems
# ---------------------------------------------------------------------------
def list_systems(db: Session, organization_id: UUID) -> list[OrganizationSystem]:
    statement = (
        select(OrganizationSystem)
        .where(OrganizationSystem.organization_id == organization_id)
        .order_by(OrganizationSystem.selected_at)
    )
    return list(db.scalars(statement).all())


def replace_systems(
    db: Session,
    organization_id: UUID,
    selections: list[OrganizationSystemSelection],
    actor_user_id: UUID,
) -> list[OrganizationSystem]:
    normalized: list[tuple[str, str | None]] = []
    non_custom_codes: set[str] = set()
    for selection in selections:
        if not is_valid_system_code(selection.system_code):
            raise WorkspaceServiceError(
                f"'{selection.system_code}' is not a governed system code",
                code="invalid_registry_code",
                status=400,
            )
        definition = get_system(selection.system_code)
        assert definition is not None  # guaranteed by is_valid_system_code above
        label = (selection.custom_label or "").strip() or None
        if definition.allows_custom_label:
            if not label:
                raise WorkspaceServiceError(
                    f"custom_label is required for system_code '{selection.system_code}'",
                    code="invalid_system_selection",
                    status=400,
                )
        else:
            if label is not None:
                raise WorkspaceServiceError(
                    f"custom_label is not permitted for system_code '{selection.system_code}'",
                    code="invalid_system_selection",
                    status=400,
                )
            if selection.system_code in non_custom_codes:
                raise WorkspaceServiceError(
                    f"'{selection.system_code}' was selected more than once",
                    code="invalid_system_selection",
                    status=400,
                )
            non_custom_codes.add(selection.system_code)
        normalized.append((selection.system_code, label))

    _lock_organization(db, organization_id)
    existing_rows = list_systems(db, organization_id)
    existing = {(row.system_code, row.custom_label): row for row in existing_rows}
    desired = set(normalized)
    for key, row in existing.items():
        if key not in desired:
            db.delete(row)
    for system_code, label in desired - existing.keys():
        db.add(
            OrganizationSystem(
                organization_id=organization_id,
                system_code=system_code,
                custom_label=label,
                selected_by_user_id=actor_user_id,
            )
        )
    db.commit()
    return list_systems(db, organization_id)


# ---------------------------------------------------------------------------
# Team summary
# ---------------------------------------------------------------------------
def get_team_summary(db: Session, organization_id: UUID) -> TeamSummaryRead:
    role_counts = db.execute(
        select(OrganizationMembership.role, func.count())
        .where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.status == MembershipStatus.ACTIVE.value,
        )
        .group_by(OrganizationMembership.role)
    ).all()
    counts_by_role: dict[str, int] = {role: count for role, count in role_counts}
    counts_by_persona: dict[str, int] = {}
    for role, count in role_counts:
        persona = persona_for_role(role)
        counts_by_persona[persona] = counts_by_persona.get(persona, 0) + count
    active_member_count = sum(counts_by_role.values())
    pending_invitation_count = (
        db.scalar(
            select(func.count())
            .select_from(OrganizationInvitation)
            .where(
                OrganizationInvitation.organization_id == organization_id,
                OrganizationInvitation.status == InvitationStatus.PENDING.value,
            )
        )
        or 0
    )
    return TeamSummaryRead(
        active_member_count=active_member_count,
        pending_invitation_count=pending_invitation_count,
        counts_by_role=counts_by_role,
        counts_by_persona=counts_by_persona,
    )


# ---------------------------------------------------------------------------
# Readiness
# ---------------------------------------------------------------------------
def _setup_progress(
    organization: Organization,
    objective_count: int,
    challenge_count: int,
    system_count: int,
    active_member_count: int,
) -> SetupProgressRead:
    required = {
        "profile": bool(
            organization.name
            and organization.country_code
            and organization.default_currency
            and organization.timezone
        ),
        "industry": bool(organization.industry),
        "objectives": objective_count >= 1,
    }
    optional = {
        "challenges": challenge_count >= 1,
        "systems": system_count >= 1,
        "team": active_member_count >= 2,
    }
    components = {**required, **optional}
    missing_required = [key for key, satisfied in required.items() if not satisfied]
    missing_optional = [key for key, satisfied in optional.items() if not satisfied]
    satisfied_count = sum(1 for value in components.values() if value)
    percent = round((satisfied_count / len(components)) * 100) if components else 0
    recommended_next_steps = [
        _NEXT_STEP_LABELS[key] for key in (*missing_required, *missing_optional)
    ]
    return SetupProgressRead(
        percent=percent,
        components=components,
        missing_required=missing_required,
        recommended_next_steps=recommended_next_steps,
    )


def _data_readiness(db: Session, organization_id: UUID) -> str:
    has_batch = db.scalar(
        select(IngestionBatch.id).where(IngestionBatch.organization_id == organization_id).limit(1)
    )
    if has_batch is not None:
        return "HAS_DATA"
    has_dataset = db.scalar(
        select(Dataset.id).where(Dataset.organization_id == organization_id).limit(1)
    )
    return "HAS_DATA" if has_dataset is not None else "NOT_STARTED"


def _ai_readiness(
    db: Session, organization_id: UUID, workspace_ready: bool, data_readiness: str
) -> str:
    """Derived only, never a stored field. Never claims READY without
    authoritative Trust evidence -- if no AnalyticalReadinessDecision exists
    yet, the truthful answer is PENDING_TRUST, not READY."""
    if not workspace_ready:
        return "NOT_READY"
    if data_readiness == "NOT_STARTED":
        return "PENDING_DATA"
    latest_status = db.scalar(
        select(AnalyticalReadinessDecision.readiness_status)
        .where(AnalyticalReadinessDecision.organization_id == organization_id)
        .order_by(AnalyticalReadinessDecision.created_at.desc())
        .limit(1)
    )
    if latest_status in (ReadinessStatus.READY.value, ReadinessStatus.READY_WITH_WARNINGS.value):
        return "READY"
    return "PENDING_TRUST"


def _handoff_state(workspace_ready: bool, data_readiness: str, ai_readiness: str) -> str:
    """Four truthfully-distinguishable states given the v1 (NOT_STARTED /
    HAS_DATA) data-readiness model. A workspace that is ready but has no
    data yet is reported as DATA_PENDING; a separate "WORKSPACE_READY"
    handoff value is deliberately not exposed here since this v1's
    data-readiness model cannot truthfully distinguish it from DATA_PENDING
    -- setup_progress.percent == 100 already carries that signal."""
    if not workspace_ready:
        return "SETUP_IN_PROGRESS"
    if data_readiness == "NOT_STARTED":
        return "DATA_PENDING"
    if ai_readiness != "READY":
        return "TRUST_PENDING"
    return "READY_FOR_VALUE_SCAN"


def get_workspace_summary(
    db: Session, organization_id: UUID, current_user_id: UUID
) -> WorkspaceSummaryRead:
    organization = _get_organization(db, organization_id)
    objectives = list_objectives(db, organization_id)
    challenges = list_challenges(db, organization_id)
    systems = list_systems(db, organization_id)
    team_summary = get_team_summary(db, organization_id)

    current_membership = db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == current_user_id,
        )
    )
    current_role = current_membership.role if current_membership else MembershipRole.VIEWER.value

    setup_progress = _setup_progress(
        organization,
        len(objectives),
        len(challenges),
        len(systems),
        team_summary.active_member_count,
    )
    workspace_ready = not setup_progress.missing_required
    data_readiness = _data_readiness(db, organization_id)
    ai_readiness = _ai_readiness(db, organization_id, workspace_ready, data_readiness)
    handoff_state = _handoff_state(workspace_ready, data_readiness, ai_readiness)
    next_step = (
        setup_progress.recommended_next_steps[0]
        if setup_progress.recommended_next_steps
        else "You're ready for your first Value Scan"
    )

    return WorkspaceSummaryRead(
        organization_id=organization.id,
        organization_name=organization.name,
        organization_status=organization.status,
        industry=organization.industry,
        sub_industry=organization.sub_industry,
        current_user_role=current_role,
        current_user_persona=persona_for_role(current_role),
        profile_complete=setup_progress.components["profile"],
        objectives=[item.objective_code for item in objectives],
        challenges=[item.challenge_code for item in challenges],
        systems=[OrganizationSystemRead.model_validate(item) for item in systems],
        team_summary=team_summary,
        setup_progress=setup_progress,
        data_readiness=data_readiness,
        ai_readiness=ai_readiness,
        handoff_state=handoff_state,
        next_step=next_step,
    )
