from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FeatureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    code: str
    name: str
    description: str
    lifecycle_status: str
    owner: str
    tags: list[str]
    documentation_reference: str


class FeatureVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    feature_id: UUID
    semantic_version: str
    entity_grain: str
    time_grain: str | None
    value_type: str
    unit_behavior: str
    currency_behavior: str
    required_canonical_objects: list[str]
    input_contract: dict[str, object]
    computation_reference: dict[str, object]
    validation_contract: dict[str, object]
    known_limitations: list[str]


class SignatureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    code: str
    name: str
    description: str
    signature_type: str
    industry: str
    lifecycle_status: str
    canonical_governance_status: str
    owner: str
    tags: list[str]
    documentation_reference: str
    created_at: datetime
    updated_at: datetime
    retired_at: datetime | None


class SignatureVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    signature_id: UUID
    semantic_version: str
    applicable_pack_versions: list[str]
    required_canonical_objects: list[str]
    required_features: list[object]
    required_events: list[object]
    required_conditions: list[object]
    exclusion_conditions: list[object]
    evidence_requirements: list[object]
    confidence_model: dict[str, object]
    economic_impact_policy: dict[str, object]
    expected_outcome: dict[str, object]
    supporting_algorithms: list[str]
    supporting_rules: list[str]
    supporting_models: list[str]
    dependencies: list[object]
    monitoring_policy: dict[str, object]
    known_limitations: list[str]
    definition_hash: str
    approved_at: datetime | None


class SignatureTransition(BaseModel):
    target_status: str = Field(
        pattern=r"^(hypothesis|candidate|observed|validated|approved|production|"
        r"suspended|deprecated|retired)$"
    )
    reason: str = Field(min_length=10, max_length=1000)
    idempotency_key: str = Field(min_length=1, max_length=255)
    approval_reference: str | None = Field(default=None, max_length=255)


class SignatureDeploymentCreate(BaseModel):
    signature_version_id: UUID
    environment: str = Field(default="production", pattern=r"^(test|pilot|production)$")
    calibration: dict[str, object] = Field(default_factory=dict)


class SignatureDeploymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    signature_version_id: UUID
    environment: str
    status: str
    calibration: dict[str, object]
    entitlement_snapshot: dict[str, object]
    deployed_at: datetime
    suspended_at: datetime | None


class SignatureEvidenceInput(BaseModel):
    evidence_type: str = Field(min_length=1, max_length=60)
    source_type: str = Field(min_length=1, max_length=60)
    source_identifier: str = Field(min_length=1, max_length=500)
    lineage_node_id: UUID | None = None
    observed_at: datetime | None = None
    integrity_fingerprint: str = Field(min_length=16, max_length=128)
    metadata: dict[str, object] = Field(default_factory=dict)


class SignatureExecutionCreate(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=255)
    observations: dict[str, object]
    evidence: list[SignatureEvidenceInput] = Field(min_length=1, max_length=100)


class SignatureExecutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    deployment_id: UUID
    signature_version_id: UUID
    idempotency_key: str
    input_fingerprint: str
    status: str
    matched: bool | None
    confidence: Decimal | None
    result_json: dict[str, object]
    explanation: dict[str, object]
    finding_id: UUID | None
    error_code: str | None
    started_at: datetime
    completed_at: datetime | None
