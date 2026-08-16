from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.learning import LearningRead, ProvenanceType

PackLifecycle = Literal["draft", "in_review", "approved", "rejected", "superseded", "retired"]
PackPatternProcessStage = Literal[
    "job_creation",
    "field_execution",
    "evidence_capture",
    "resource_validation",
    "contract_rate_validation",
    "invoicing",
    "payment",
    "recovery",
]


class KnowledgePackCreate(BaseModel):
    name: str = Field(min_length=1, max_length=250)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=150)
    description: str = Field(min_length=1, max_length=5000)
    industry: str = Field(min_length=1, max_length=100)
    domain: str = Field(min_length=1, max_length=100)
    scope: str = Field(min_length=1, max_length=2000)
    change_summary: str = Field(min_length=1, max_length=2000)


class KnowledgePackVersionCreate(BaseModel):
    change_summary: str = Field(min_length=1, max_length=2000)


class KnowledgePackLearningAdd(BaseModel):
    learning_id: UUID
    inclusion_rationale: str = Field(min_length=1, max_length=2000)


class KnowledgePackTransition(BaseModel):
    rationale: str = Field(min_length=1, max_length=2000)


class KnowledgePackPatternCreate(BaseModel):
    pattern_key: str = Field(pattern=r"^[A-Z0-9]+(?:-[A-Z0-9]+)*$", max_length=60)
    name: str = Field(min_length=1, max_length=250)
    process_stage: PackPatternProcessStage
    description: str = Field(min_length=1, max_length=5000)
    provenance_type: ProvenanceType
    content: dict[str, object]


class KnowledgePackPatternRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    pattern_key: str
    name: str
    process_stage: PackPatternProcessStage
    description: str
    provenance_type: ProvenanceType
    content_json: dict[str, object]
    created_at: datetime


class KnowledgePackAuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    event_type: str
    knowledge_pack_version_id: UUID | None
    prior_status: str | None
    new_status: str | None
    actor_user_id: UUID
    actor_role: str
    rationale: str | None
    metadata_json: dict[str, object]
    occurred_at: datetime


class KnowledgePackMemberRead(BaseModel):
    learning: LearningRead
    inclusion_rationale: str
    created_at: datetime


class KnowledgePackVersionRead(BaseModel):
    id: UUID
    organization_id: UUID
    knowledge_pack_id: UUID
    version_number: int
    lifecycle_status: PackLifecycle
    change_summary: str
    provenance_summary: ProvenanceType | None
    created_by_user_id: UUID
    reviewed_by_user_id: UUID | None
    approved_by_user_id: UUID | None
    created_at: datetime
    reviewed_at: datetime | None
    approved_at: datetime | None
    superseded_at: datetime | None
    retired_at: datetime | None
    members: list[KnowledgePackMemberRead]
    patterns: list[KnowledgePackPatternRead]


class KnowledgePackRead(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    slug: str
    description: str
    industry: str
    domain: str
    scope: str
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime
    current_approved_version: KnowledgePackVersionRead | None
    latest_draft_version: KnowledgePackVersionRead | None
    versions: list[KnowledgePackVersionRead]
    audit_history: list[KnowledgePackAuditRead]


class KnowledgePackPage(BaseModel):
    items: list[KnowledgePackRead]
    page: int
    page_size: int
    total: int
