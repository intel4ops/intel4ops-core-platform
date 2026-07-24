from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class EvidenceCreate(BaseModel):
    source_system: str
    source_record_id: str
    evidence_type: str
    payload: dict


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
    ontology_concept_ids: list[str] = []
    causal_chain_id: str | None = None
    evidence: list[EvidenceCreate] = []


class FindingRead(FindingCreate):
    id: str
    organization_id: str
    status: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class RecoveryActionCreate(BaseModel):
    finding_id: str
    title: str
    owner: str
    expected_recovery: float = 0
    due_date: datetime | None = None


class RecoveryActionRead(RecoveryActionCreate):
    id: str
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
