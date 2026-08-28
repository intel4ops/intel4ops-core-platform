from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ValidationSimulationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    simulation_code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    analysis_case_id: UUID


class ValidationSimulationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    simulation_code: str
    name: str
    analysis_case_id: UUID
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


class ExpectedFindingUpload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_finding_code: str = Field(min_length=1, max_length=100)
    domain: str = Field(min_length=1, max_length=100)
    severity: str = Field(min_length=1, max_length=50)
    entities: list[dict[str, object]] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    expected_economic_impact: float | None = None
    currency: str | None = Field(default=None, max_length=3)
    description: str = ""


class GroundTruthUpload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_findings: list[ExpectedFindingUpload] = Field(min_length=1)
    expected_clean_areas: list[str] = Field(default_factory=list)
    tolerance: dict[str, object] = Field(default_factory=dict)


class ExpectedFindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    expected_finding_code: str
    domain: str
    severity: str
    entities: list[dict[str, object]]
    evidence_refs: list[str]
    expected_economic_impact: float | None
    currency: str | None
    description: str


class GroundTruthRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    simulation_id: UUID
    version: int
    checksum: str
    expected_clean_areas: list[str]
    tolerance: dict[str, object]
    uploaded_by_user_id: UUID
    uploaded_at: datetime
    expected_findings: list[ExpectedFindingRead] = Field(default_factory=list)


class ValidationSimulationDetail(ValidationSimulationRead):
    ground_truth_versions: list[GroundTruthRead] = Field(default_factory=list)


class ValidationFindingMatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    match_type: str
    expected_finding_id: UUID | None
    actual_finding_id: UUID | None
    severity_match: bool | None
    entity_match: bool | None
    evidence_match: bool | None
    economic_variance_pct: float | None


class ValidationScoreRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    true_positive_count: int
    false_positive_count: int
    false_negative_count: int
    precision: float | None
    recall: float | None
    f1: float | None
    severity_accuracy: float | None
    entity_accuracy: float | None
    evidence_accuracy: float | None
    economic_variance_avg_pct: float | None
    critical_leakage_recall: float | None
    computed_at: datetime


class SimulationValidationRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    simulation_id: UUID
    ground_truth_id: UUID
    analysis_case_run_id: UUID
    status: str
    triggered_by_user_id: UUID
    started_at: datetime
    completed_at: datetime | None
    error_summary: str | None


class ValidationResultRead(BaseModel):
    run: SimulationValidationRunRead
    score: ValidationScoreRead | None
    matches: list[ValidationFindingMatchRead] = Field(default_factory=list)


class ValidationResultsHistoryRead(BaseModel):
    simulation_id: UUID
    results: list[ValidationResultRead] = Field(default_factory=list)
