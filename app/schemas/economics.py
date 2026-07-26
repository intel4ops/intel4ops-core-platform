from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.engines.economics_engine import OpportunityStatus, PriorityCategory


class OpportunityCreate(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=255)
    economic_source_key: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=250)
    description: str = Field(min_length=1, max_length=4000)
    currency_code: str = Field(pattern=r"^[A-Z]{3}$")
    business_domain: str | None = Field(default=None, max_length=100)
    site_reference: str | None = Field(default=None, max_length=150)
    industry_pack_code: str | None = Field(default=None, max_length=100)
    capability_code: str | None = Field(default=None, max_length=100)
    owner_user_id: UUID | None = None
    limitations: list[str] = Field(default_factory=list, max_length=50)


class OpportunityUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=250)
    description: str | None = Field(default=None, min_length=1, max_length=4000)
    business_domain: str | None = Field(default=None, max_length=100)
    site_reference: str | None = Field(default=None, max_length=150)
    owner_user_id: UUID | None = None
    limitations: list[str] | None = None


class OpportunityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    opportunity_code: str
    economic_source_key: str
    title: str
    description: str
    currency_code: str
    business_domain: str | None
    site_reference: str | None
    status: OpportunityStatus
    priority_category: PriorityCategory | None
    selected_scenario_id: UUID | None
    current_baseline_version: int | None
    limitations: list[str]
    created_at: datetime
    updated_at: datetime


class OpportunityPage(BaseModel):
    items: list[OpportunityRead]
    page: int
    page_size: int
    total: int


class FindingLinkCreate(BaseModel):
    finding_id: UUID
    allocation_percentage: Decimal = Field(default=Decimal("1"), ge=0, le=1)
    relationship_type: str = Field(default="contributes", max_length=40)


class ActionLinkCreate(BaseModel):
    action_id: UUID
    relationship_type: str = Field(default="proposed", max_length=40)


class ScenarioCreate(BaseModel):
    scenario_code: str = Field(pattern=r"^(low|base|high|conservative|optimistic|[a-z0-9_-]+)$")
    name: str = Field(min_length=1, max_length=150)
    currency_code: str = Field(pattern=r"^[A-Z]{3}$")
    lower_exposure: Decimal = Field(ge=0)
    gross_exposure: Decimal = Field(ge=0)
    upper_exposure: Decimal = Field(ge=0)
    addressability_rate: Decimal = Field(ge=0, le=1)
    recoverability_rate: Decimal = Field(ge=0, le=1)
    success_probability: Decimal = Field(ge=0, le=1)
    recovery_cost: Decimal = Field(ge=0)
    benefit_period_days: int | None = Field(default=None, gt=0)
    scenario_probability: Decimal = Field(default=Decimal("1"), ge=0, le=1)
    measurement_period: str | None = Field(default=None, max_length=50)
    mutually_exclusive_group: str | None = Field(default=None, max_length=100)
    assumptions_summary: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def bounds_and_currency(self) -> "ScenarioCreate":
        if not self.lower_exposure <= self.gross_exposure <= self.upper_exposure:
            raise ValueError("Exposure must satisfy lower <= gross <= upper")
        return self


class ScenarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    opportunity_id: UUID
    scenario_code: str
    version: int
    name: str
    currency_code: str
    lower_exposure: Decimal
    gross_exposure: Decimal
    upper_exposure: Decimal
    addressability_rate: Decimal
    recoverability_rate: Decimal
    success_probability: Decimal
    recovery_cost: Decimal
    benefit_period_days: int | None
    scenario_probability: Decimal
    active: bool
    created_at: datetime


class AssumptionCreate(BaseModel):
    scenario_id: UUID | None = None
    assumption_code: str = Field(min_length=1, max_length=100)
    value: Decimal
    unit: str = Field(min_length=1, max_length=50)
    currency_code: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    source: str = Field(min_length=1, max_length=100)
    source_reference: str | None = Field(default=None, max_length=500)
    evidence_reference: str | None = Field(default=None, max_length=500)
    confidence_score: Decimal = Field(ge=0, le=1)
    effective_at: datetime | None = None
    expires_at: datetime | None = None
    model_version: str = Field(default="1.0", max_length=30)


class AssumptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    opportunity_id: UUID
    scenario_id: UUID | None
    assumption_code: str
    version: int
    value: Decimal
    unit: str
    currency_code: str | None
    source: str
    confidence_score: Decimal
    superseded: bool
    created_at: datetime


class CalculateCreate(BaseModel):
    scenario_id: UUID
    idempotency_key: str = Field(min_length=1, max_length=255)
    reason: str = Field(default="economic_case_calculation", max_length=500)


class CalculationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    opportunity_id: UUID
    scenario_id: UUID
    calculation_version: str
    currency_code: str
    gross_exposure: Decimal
    addressable_exposure: Decimal
    expected_recoverable_value: Decimal
    probability_adjusted_value: Decimal
    recovery_cost: Decimal
    expected_net_benefit: Decimal
    expected_roi: Decimal | None
    payback_period_days: Decimal | None
    zero_cost_policy: str
    calculated_at: datetime


class PrioritizeCreate(BaseModel):
    calculation_id: UUID
    idempotency_key: str = Field(min_length=1, max_length=255)
    profile_code: str = Field(default="default_enterprise", max_length=100)
    urgency_score: Decimal = Field(ge=0, le=1)
    confidence_score: Decimal = Field(ge=0, le=1)
    feasibility_score: Decimal = Field(ge=0, le=1)
    strategic_alignment_score: Decimal = Field(ge=0, le=1)
    risk_score: Decimal = Field(ge=0, le=1)
    dependency_ready: bool = True
    resource_ready: bool = True
    calculation_reason: str = Field(min_length=1, max_length=1000)
    source_references: list[dict[str, object]] = Field(default_factory=list)


class PrioritizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    opportunity_id: UUID
    calculation_id: UUID
    profile_code: str
    model_name: str
    model_version: str
    factor_weights: dict[str, str]
    normalized_factors: dict[str, str]
    factor_contributions: dict[str, str]
    priority_score: Decimal
    priority_category: PriorityCategory
    calculation_reason: str
    limitations: list[str]
    calculated_at: datetime


class OverlapGroupCreate(BaseModel):
    overlap_key: str = Field(min_length=1, max_length=255)
    overlap_type: str = Field(
        pattern=r"^(duplicate|partial|mutually_exclusive|dependent|parent_child|shared_source)$"
    )
    decision_reason: str | None = Field(default=None, max_length=4000)


class OverlapMemberCreate(BaseModel):
    opportunity_id: UUID
    parent_opportunity_id: UUID | None = None
    allocation_percentage: Decimal = Field(ge=0, le=1)
    inclusion_status: str = Field(pattern=r"^(included|excluded|superseded|conditional)$")


class DecisionCreate(BaseModel):
    decision: OpportunityStatus
    decision_reason: str = Field(min_length=1, max_length=4000)
    idempotency_key: str = Field(min_length=1, max_length=255)
    scenario_id: UUID | None = None
    prioritization_id: UUID | None = None
    conditions: list[str] = Field(default_factory=list)
    review_at: datetime | None = None


class DecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    opportunity_id: UUID
    prior_status: str | None
    decision: OpportunityStatus
    decision_reason: str
    actor_user_id: UUID
    actor_role: str
    scenario_id: UUID | None
    baseline_version: int | None
    conditions: list[str]
    decided_at: datetime


class EconomicAuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    opportunity_id: UUID
    event_type: str
    actor_user_id: UUID
    reason: str
    event_payload: dict[str, object]
    occurred_at: datetime


class BaselineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    opportunity_id: UUID
    scenario_id: UUID
    calculation_id: UUID
    prioritization_id: UUID
    version: int
    currency_code: str
    economic_snapshot: dict[str, object]
    assumption_versions: list[dict[str, object]]
    approved_by_user_id: UUID
    approved_at: datetime


class PortfolioCurrencySummary(BaseModel):
    currency_code: str
    gross_exposure: Decimal
    addressable_exposure: Decimal
    expected_recoverable_value: Decimal
    probability_adjusted_value: Decimal
    recovery_cost: Decimal
    expected_net_benefit: Decimal
    opportunity_count: int


class PortfolioSummary(BaseModel):
    currencies: list[PortfolioCurrencySummary]
    by_priority: dict[str, int]
    by_status: dict[str, int]


class RankingItem(BaseModel):
    opportunity: OpportunityRead
    priority_score: Decimal | None
    included_probability_adjusted_value: Decimal | None
