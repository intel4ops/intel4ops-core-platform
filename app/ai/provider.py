from __future__ import annotations

from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.executive_narrative import StructuredNarrativeDraft


class StructuredInferenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inference_type: str = Field(min_length=1, max_length=60)
    proposed_code: str | None = Field(default=None, max_length=150)
    proposed_value: str | None = Field(default=None, max_length=500)
    display_value: str | None = Field(default=None, max_length=500)
    confidence: str = Field(pattern=r"^(HIGH|MEDIUM|LOW)$")
    evidence_references: list[str] = Field(default_factory=list, max_length=25)
    reasoning_summary: str = Field(min_length=1, max_length=500)
    alternative_candidates: list[str] = Field(default_factory=list, max_length=5)


class StructuredInferenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: UUID
    inferences: list[StructuredInferenceItem] = Field(max_length=25)
    limitations: list[str] = Field(default_factory=list, max_length=20)


class StructuredInferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: UUID
    template_code: str
    template_version: str
    governed_context: dict[str, object]
    allowed_inference_types: tuple[str, ...]
    max_inference_items: int
    max_clarification_questions: int


class ProviderInvocationResult(BaseModel):
    response: StructuredInferenceResponse
    provider_code: str
    model_code: str
    model_version: str | None = None
    latency_ms: int = Field(ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    retry_count: int = Field(default=0, ge=0)


class StructuredNarrativeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: UUID
    scan_id: UUID
    template_code: str
    template_version: str
    schema_version: str
    audience: str = Field(pattern=r"^EXECUTIVE$")
    governed_context: dict[str, object]
    allowed_source_reference_ids: tuple[str, ...]
    allowed_value_reference_ids: tuple[str, ...]


class NarrativeProviderInvocationResult(BaseModel):
    response: StructuredNarrativeDraft
    provider_code: str
    model_code: str
    model_version: str | None = None
    latency_ms: int = Field(ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    retry_count: int = Field(default=0, ge=0)


class ProviderUnavailableError(RuntimeError):
    pass


class ProviderResponseError(RuntimeError):
    pass


class OperationalProfileInferenceProvider(Protocol):
    def generate_profile(self, request: StructuredInferenceRequest) -> ProviderInvocationResult: ...


class GroundedExecutiveNarrativeProvider(Protocol):
    def generate_narrative(
        self, request: StructuredNarrativeRequest
    ) -> NarrativeProviderInvocationResult: ...
