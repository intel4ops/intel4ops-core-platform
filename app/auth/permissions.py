from app.models.entities import MembershipRole

ORGANIZATION_READ_ROLES = (
    MembershipRole.ORGANIZATION_ADMIN,
    MembershipRole.ANALYST,
    MembershipRole.OPERATOR,
    MembershipRole.RECOVERY_MANAGER,
    MembershipRole.VIEWER,
)
ORGANIZATION_ADMIN_ROLES = (MembershipRole.ORGANIZATION_ADMIN,)
MAINTENANCE_ANALYSIS_ROLES = (
    MembershipRole.ORGANIZATION_ADMIN,
    MembershipRole.ANALYST,
    MembershipRole.OPERATOR,
)
RECOVERY_WRITE_ROLES = (
    MembershipRole.ORGANIZATION_ADMIN,
    MembershipRole.OPERATOR,
    MembershipRole.RECOVERY_MANAGER,
)
