from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class KnowledgeClass(StrEnum):
    KPI = "kpi"
    ARITHMETIC_DEFINITION = "arithmetic_definition"
    DETERMINISTIC_RULE = "deterministic_rule"
    LEAKAGE_RULE = "leakage_rule"
    EXCEPTION_RULE = "exception_rule"
    EVIDENCE_POLICY = "evidence_policy"
    CONTROL_POLICY = "control_policy"
    BENCHMARK = "benchmark"
    RECOVERY_HEURISTIC = "recovery_heuristic"
    STATISTICAL_METHOD = "statistical_method"
    FORECASTING_METHOD = "forecasting_method"
    PREDICTIVE_MODEL = "predictive_model"
    RELIABILITY_METHOD = "reliability_method"
    OPTIMIZATION_MODEL = "optimization_model"
    SIMULATION_MODEL = "simulation_model"


class AnalyticalLevel(StrEnum):
    ARITHMETIC = "arithmetic"
    RULE_BASED = "rule_based"
    STATISTICAL = "statistical"
    FORECASTING = "forecasting"
    PREDICTIVE = "predictive"
    RELIABILITY = "reliability"
    OPTIMIZATION = "optimization"
    SIMULATION = "simulation"
    RECOVERY = "recovery"


class LifecycleStatus(StrEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    VALIDATED = "validated"
    APPROVED = "approved"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    RETIRED = "retired"
    REJECTED = "rejected"


class QualityLevel(StrEnum):
    EXPERIMENTAL = "experimental"
    PROVISIONAL = "provisional"
    VALIDATED = "validated"
    PRODUCTION = "production"
    REFERENCE_GRADE = "reference_grade"


class ScopeType(StrEnum):
    SHARED_CORE = "shared_core"
    INDUSTRY = "industry"
    REGIONAL = "regional"
    ORGANIZATION = "organization"


class FormulaOperation(StrEnum):
    SUM = "sum"
    COUNT = "count"
    COUNT_DISTINCT = "distinct_count"
    AVERAGE = "average"
    MINIMUM = "minimum"
    MAXIMUM = "maximum"
    MEDIAN = "median"
    SUBTRACT = "subtract"
    MULTIPLY = "multiply"
    DIVIDE = "divide"
    RATIO = "ratio"
    PERCENTAGE = "percentage"
    ABSOLUTE_VARIANCE = "absolute_variance"
    PERCENTAGE_VARIANCE = "percentage_variance"
    DATE_DIFFERENCE = "date_difference"
    AGING_BUCKET = "aging_bucket"
    RECONCILE = "reconciliation"
    FILTER = "filter"
    GROUP_BY = "group_by"


StableCode = Annotated[
    str,
    Field(
        pattern=r"^[A-Z][A-Z0-9_]*(?:\.[A-Z][A-Z0-9_]*)+$",
        min_length=3,
        max_length=150,
    ),
]


class FormulaExpression(BaseModel):
    operation: FormulaOperation
    inputs: list[str] = Field(default_factory=list, max_length=30)
    filters: list[dict[str, object]] = Field(default_factory=list, max_length=20)
    grouping: list[str] = Field(default_factory=list, max_length=10)
    parameters: dict[str, object] = Field(default_factory=dict, max_length=30)

    @field_validator("inputs", "grouping")
    @classmethod
    def validate_references(cls, values: list[str]) -> list[str]:
        if any(not value or len(value) > 100 for value in values):
            raise ValueError("Input and grouping references must be 1-100 characters")
        return values


class InputRequirementCreate(BaseModel):
    input_code: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=100)
    canonical_entity: str = Field(min_length=1, max_length=100)
    canonical_field: str = Field(min_length=1, max_length=100)
    required: bool = True
    expected_type: str = Field(min_length=1, max_length=30)
    expected_unit: str | None = Field(default=None, max_length=50)
    currency_code: str | None = Field(default=None, min_length=3, max_length=3)
    minimum_record_count: int = Field(default=0, ge=0)
    allowed_null_percentage: float = Field(default=0, ge=0, le=100)

    @field_validator("currency_code")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.upper()
        if not value.isascii() or not value.isalpha():
            raise ValueError("Currency must contain three ASCII letters")
        return value


class EvidenceRequirementCreate(BaseModel):
    evidence_type: str = Field(min_length=1, max_length=50)
    requirement_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$", max_length=100)
    description: str = Field(min_length=1, max_length=1000)
    required: bool = True
    minimum_count: int = Field(default=1, ge=0)
    retention_class: str = Field(min_length=1, max_length=50)


class ParameterCreate(BaseModel):
    parameter_code: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=100)
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1000)
    data_type: str = Field(min_length=1, max_length=30)
    default_value: object | None = None
    minimum_value: str | None = Field(default=None, max_length=100)
    maximum_value: str | None = Field(default=None, max_length=100)
    allowed_values: list[object] | None = Field(default=None, max_length=50)
    required: bool = True
    unit: str | None = Field(default=None, max_length=50)


class DefinitionCreate(BaseModel):
    stable_code: StableCode
    name: str = Field(min_length=1, max_length=250)
    description: str = Field(min_length=1, max_length=5000)
    knowledge_class: KnowledgeClass
    analytical_level: AnalyticalLevel
    domain: str = Field(min_length=1, max_length=100)
    subdomain: str | None = Field(default=None, max_length=100)
    owner_organization_id: UUID | None = None
    industry_pack_code: str | None = Field(default=None, max_length=100)
    region_code: str | None = Field(default=None, max_length=30)
    scope_type: ScopeType
    is_system_definition: bool = False

    @model_validator(mode="after")
    def validate_scope(self) -> "DefinitionCreate":
        if self.scope_type == ScopeType.ORGANIZATION and self.owner_organization_id is None:
            raise ValueError("Organization scope requires owner_organization_id")
        if self.scope_type != ScopeType.ORGANIZATION and self.owner_organization_id is not None:
            raise ValueError("Only organization scope may set owner_organization_id")
        if self.scope_type == ScopeType.INDUSTRY and not self.industry_pack_code:
            raise ValueError("Industry scope requires industry_pack_code")
        if self.scope_type == ScopeType.REGIONAL and not self.region_code:
            raise ValueError("Regional scope requires region_code")
        if self.is_system_definition and self.scope_type == ScopeType.ORGANIZATION:
            raise ValueError("System definitions cannot be organization scoped")
        return self


class DefinitionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=250)
    description: str | None = Field(default=None, min_length=1, max_length=5000)
    domain: str | None = Field(default=None, min_length=1, max_length=100)
    subdomain: str | None = Field(default=None, max_length=100)


class DefinitionVersionCreate(BaseModel):
    semantic_version: str = Field(pattern=r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
    quality_level: QualityLevel = QualityLevel.EXPERIMENTAL
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    expression_schema: FormulaExpression
    output_type: str = Field(min_length=1, max_length=50)
    output_unit: str = Field(min_length=1, max_length=50)
    currency_code: str | None = Field(default=None, min_length=3, max_length=3)
    rounding_policy: dict[str, object] = Field(
        default_factory=lambda: {"mode": "half_even", "decimal_places": 2},
        max_length=10,
    )
    null_policy: str = Field(default="exclude", max_length=50)
    zero_denominator_policy: str = Field(default="error", max_length=50)
    trust_requirement: dict[str, object] = Field(default_factory=dict, max_length=20)
    readiness_requirement: dict[str, object] = Field(default_factory=dict, max_length=20)
    parameters: list[ParameterCreate] = Field(default_factory=list, max_length=30)
    input_requirements: list[InputRequirementCreate] = Field(default_factory=list, max_length=50)
    evidence_requirements: list[EvidenceRequirementCreate] = Field(
        default_factory=list, max_length=30
    )

    @field_validator("currency_code")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.upper()
        if not value.isascii() or not value.isalpha():
            raise ValueError("Currency must contain three ASCII letters")
        return value

    @model_validator(mode="after")
    def validate_dates(self) -> "DefinitionVersionCreate":
        if self.effective_from and self.effective_to and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be later than effective_from")
        return self


class GovernanceAction(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)
    notes: str | None = Field(default=None, max_length=2000)
    effective_from: datetime | None = None


class SourceCreate(BaseModel):
    source_type: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=250)
    publisher: str = Field(min_length=1, max_length=200)
    citation: str = Field(min_length=1, max_length=5000)
    source_uri: str | None = Field(default=None, max_length=1000)
    authority_level: str = Field(
        pattern=(
            r"^(regulatory|international_standard|peer_reviewed|industry_reference|"
            r"enterprise_convention|customer_policy|intel4ops_proprietary|experimental)$"
        )
    )
    notes: str | None = Field(default=None, max_length=2000)
    owner_organization_id: UUID | None = None


class SourceLinkCreate(BaseModel):
    source_id: UUID
    relationship_type: str = Field(min_length=1, max_length=50)
    is_primary: bool = False


class ValidationCaseCreate(BaseModel):
    case_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$", max_length=100)
    description: str = Field(min_length=1, max_length=2000)
    input_payload: dict[str, object] = Field(max_length=50)
    expected_output: object
    tolerance: str | None = Field(default=None, max_length=100)
    expected_status: str = Field(default="completed", max_length=30)


class ResolveRequest(BaseModel):
    organization_id: UUID
    stable_code: StableCode
    industry_pack_code: str | None = Field(default=None, max_length=100)
    region_code: str | None = Field(default=None, max_length=30)
    effective_at: datetime | None = None


class DefinitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    stable_code: str
    name: str
    description: str
    knowledge_class: str
    analytical_level: str
    domain: str
    subdomain: str | None
    owner_organization_id: UUID | None
    industry_pack_code: str | None
    region_code: str | None
    scope_type: str
    is_system_definition: bool
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class VersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    definition_id: UUID
    semantic_version: str
    lifecycle_status: str
    quality_level: str
    effective_from: datetime | None
    effective_to: datetime | None
    expression_schema: dict[str, object]
    output_type: str
    output_unit: str
    currency_code: str | None
    rounding_policy: dict[str, object]
    null_policy: str
    zero_denominator_policy: str
    trust_requirement: dict[str, object]
    readiness_requirement: dict[str, object]
    fingerprint: str
    validation_satisfied: bool
    created_by: UUID
    created_at: datetime
    activated_by: UUID | None
    activated_at: datetime | None


class DefinitionPage(BaseModel):
    items: list[DefinitionRead]
    page: int
    page_size: int
    total: int


class ResolutionRead(BaseModel):
    status: str
    definition_id: UUID | None
    definition_version_id: UUID | None
    stable_code: str
    semantic_version: str | None
    scope_selected: str | None
    resolution_path: list[str]
    fallback_steps: list[str]
    warnings: list[str]
    effective_from: datetime | None
    effective_to: datetime | None
    fingerprint: str | None


class ExecutionPackage(BaseModel):
    stable_code: str
    semantic_version: str
    knowledge_class: str
    analytical_level: str
    operation: str
    parameters: list[dict[str, object]]
    input_requirements: list[dict[str, object]]
    output_contract: dict[str, object]
    trust_requirement: dict[str, object]
    readiness_requirement: dict[str, object]
    evidence_requirements: list[dict[str, object]]
    fingerprint: str
    provenance_references: list[dict[str, object]]
    resolution_metadata: dict[str, object]
