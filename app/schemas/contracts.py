from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.entities import OrganizationStatus


class OrganizationBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    legal_name: str | None = Field(default=None, max_length=250)
    industry: str | None = Field(default=None, max_length=100)
    country_code: str = Field(min_length=2, max_length=2)
    default_currency: str = Field(min_length=3, max_length=3)
    timezone: str = Field(default="UTC", min_length=1, max_length=100)
    description: str | None = None
    is_demo: bool = False

    @field_validator("country_code", "default_currency")
    @classmethod
    def uppercase_alpha_code(cls, value: str) -> str:
        normalized = value.upper()
        if not normalized.isascii() or not normalized.isalpha():
            raise ValueError("must contain only ASCII letters")
        return normalized


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(
        default=None, min_length=2, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    )
    legal_name: str | None = Field(default=None, max_length=250)
    industry: str | None = Field(default=None, max_length=100)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    default_currency: str | None = Field(default=None, min_length=3, max_length=3)
    timezone: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    is_demo: bool | None = None

    @field_validator("country_code", "default_currency")
    @classmethod
    def uppercase_optional_alpha_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.upper()
        if not normalized.isascii() or not normalized.isalpha():
            raise ValueError("must contain only ASCII letters")
        return normalized

    @model_validator(mode="after")
    def reject_null_for_required_fields(self) -> "OrganizationUpdate":
        required_fields = {"name", "slug", "country_code", "default_currency", "timezone"}
        null_fields = [
            field
            for field in required_fields & self.model_fields_set
            if getattr(self, field) is None
        ]
        if null_fields:
            raise ValueError(
                f"cannot set required fields to null: {', '.join(sorted(null_fields))}"
            )
        return self


class OrganizationRead(OrganizationBase):
    id: UUID
    status: OrganizationStatus
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class EvidenceCreate(BaseModel):
    source_system: str
    source_record_id: str
    evidence_type: str
    payload: dict[str, object]


class FindingCreate(BaseModel):
    rule_id: str
    title: str
    summary: str
    domain: str
    severity: str = "medium"
    priority: int = Field(default=3, ge=1, le=5)
    exposure_low: float = 0
    exposure_high: float = 0
    currency: str = "USD"
    confidence_score: float = Field(default=0, ge=0, le=1)
    ontology_concept_ids: list[str] = Field(default_factory=list)
    causal_chain_id: str | None = None
    evidence: list[EvidenceCreate] = Field(default_factory=list)


class FindingRead(FindingCreate):
    id: UUID
    organization_id: UUID
    status: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class RecoveryActionCreate(BaseModel):
    finding_id: UUID
    title: str
    owner: str
    expected_recovery: float = 0
    due_date: datetime | None = None


class RecoveryActionRead(RecoveryActionCreate):
    id: UUID
    organization_id: UUID
    status: str
    measured_recovery: float
    verified_recovery: float
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class TrustIssue(BaseModel):
    row_number: int | None = None
    field: str | None = None
    issue_type: str
    message: str
    severity: str = "warning"


class TrustReport(BaseModel):
    dataset_name: str
    row_count: int
    completeness_score: float
    duplicate_score: float
    validity_score: float
    overall_trust_score: float
    issues: list[TrustIssue]
