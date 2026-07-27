from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PackCreate(BaseModel):
    code: str = Field(pattern=r"^PACK-[A-Z0-9-]+$", max_length=50)
    name: str = Field(min_length=1, max_length=150)
    entitlement_key: str = Field(pattern=r"^industry\.[a-z0-9_]+$", max_length=150)


class PackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    code: str
    name: str
    entitlement_key: str
    status: str


class PackVersionCreate(BaseModel):
    semantic_version: str = Field(pattern=r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
    manifest_json: dict[str, object]
    minimum_platform_revision: str = "20260726_0018"


class PackVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    pack_id: UUID
    semantic_version: str
    lifecycle_status: str
    manifest_json: dict[str, object]
    minimum_platform_revision: str
    validated_at: datetime | None
    approved_at: datetime | None
    published_at: datetime | None


class PackComponentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    pack_version_id: UUID
    component_type: str
    code: str
    universal_parent: str
    configuration: dict[str, object]


class PackComponentWrite(BaseModel):
    component_type: str = Field(
        pattern=r"^(ontology_mapping|canonical_extension|metric_definition|rule_binding|"
        r"evidence_policy|economic_mapping|recovery_playbook|command_capability|"
        r"usage_meter_binding)$"
    )
    code: str = Field(min_length=1, max_length=150)
    universal_parent: str = Field(min_length=1, max_length=180)
    configuration: dict[str, object] = Field(default_factory=dict)


class PackTransition(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class PackAssignmentRequest(BaseModel):
    pack_code: str = Field(pattern=r"^PACK-[A-Z0-9-]+$")
    semantic_version: str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$")
    effective_at: datetime
    expires_at: datetime | None = None
    configuration_overrides: dict[str, object] = Field(default_factory=dict)


class PackAssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    assignment_id: UUID
    pack_version_id: UUID
    status: str
    configuration_overrides: dict[str, object]
    activated_at: datetime | None
    suspended_at: datetime | None


class PackExecutionCreate(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=255)
    readiness: str = Field(pattern=r"^(ready|supported|partially_ready|blocked)$")
    rule_code: str = Field(min_length=1, max_length=150)
    record: dict[str, object]


class PackExecutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    assignment_id: UUID
    pack_version_id: UUID
    status: str
    readiness: str
    result_json: dict[str, object]
    error_code: str | None
    created_at: datetime
    completed_at: datetime | None
