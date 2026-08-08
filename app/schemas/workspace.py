from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Governed range codes for the two profile-enrichment fields that P3.02
# deliberately avoids collecting as exact figures.
EMPLOYEE_COUNT_RANGES: tuple[str, ...] = (
    "1_10",
    "11_50",
    "51_200",
    "201_500",
    "501_1000",
    "1001_5000",
    "5001_PLUS",
)

ANNUAL_REVENUE_RANGES: tuple[str, ...] = (
    "under_1m",
    "1m_10m",
    "10m_50m",
    "50m_250m",
    "250m_1b",
    "over_1b",
)


class IndustryRead(BaseModel):
    code: str
    display_name: str
    description: str
    operational_archetype: str | None = None
    typical_system_categories: tuple[str, ...] = ()
    recommended_objective_codes: tuple[str, ...] = ()
    recommended_challenge_codes: tuple[str, ...] = ()


class ObjectiveRead(BaseModel):
    code: str
    display_name: str
    description: str
    recommended_kpi_codes: tuple[str, ...] = ()
    recommended_data_categories: tuple[str, ...] = ()
    recommended_analysis_categories: tuple[str, ...] = ()


class ChallengeRead(BaseModel):
    code: str
    display_name: str
    description: str
    recommended_objective_codes: tuple[str, ...] = ()
    recommended_data_categories: tuple[str, ...] = ()


class SystemRead(BaseModel):
    code: str
    display_name: str
    category: str
    description: str
    allows_custom_label: bool = False


class OrganizationObjectiveRead(BaseModel):
    id: UUID
    organization_id: UUID
    objective_code: str
    selected_by_user_id: UUID
    selected_at: datetime
    model_config = ConfigDict(from_attributes=True)


class OrganizationObjectivesReplace(BaseModel):
    objective_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def reject_duplicates(self) -> "OrganizationObjectivesReplace":
        if len(set(self.objective_codes)) != len(self.objective_codes):
            raise ValueError("objective_codes must not contain duplicates")
        return self


class OrganizationChallengeRead(BaseModel):
    id: UUID
    organization_id: UUID
    challenge_code: str
    selected_by_user_id: UUID
    selected_at: datetime
    model_config = ConfigDict(from_attributes=True)


class OrganizationChallengesReplace(BaseModel):
    challenge_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def reject_duplicates(self) -> "OrganizationChallengesReplace":
        if len(set(self.challenge_codes)) != len(self.challenge_codes):
            raise ValueError("challenge_codes must not contain duplicates")
        return self


class OrganizationSystemRead(BaseModel):
    id: UUID
    organization_id: UUID
    system_code: str
    custom_label: str | None
    selected_by_user_id: UUID
    selected_at: datetime
    model_config = ConfigDict(from_attributes=True)


class OrganizationSystemSelection(BaseModel):
    system_code: str
    custom_label: str | None = Field(default=None, max_length=150)


class OrganizationSystemsReplace(BaseModel):
    systems: list[OrganizationSystemSelection] = Field(default_factory=list)

    @model_validator(mode="after")
    def reject_duplicates(self) -> "OrganizationSystemsReplace":
        seen = {(item.system_code, item.custom_label) for item in self.systems}
        if len(seen) != len(self.systems):
            raise ValueError("systems must not contain duplicate selections")
        return self


class TeamSummaryRead(BaseModel):
    active_member_count: int
    pending_invitation_count: int
    counts_by_role: dict[str, int]
    counts_by_persona: dict[str, int]


class SetupProgressRead(BaseModel):
    percent: int
    components: dict[str, bool]
    missing_required: list[str]
    recommended_next_steps: list[str]


class WorkspaceSummaryRead(BaseModel):
    organization_id: UUID
    organization_name: str
    organization_status: str
    industry: str | None
    sub_industry: str | None
    current_user_role: str
    current_user_persona: str
    profile_complete: bool
    objectives: list[str]
    challenges: list[str]
    systems: list[OrganizationSystemRead]
    team_summary: TeamSummaryRead
    setup_progress: SetupProgressRead
    data_readiness: str
    ai_readiness: str
    handoff_state: str
    next_step: str
