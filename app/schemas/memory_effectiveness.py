from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class MemoryEffectivenessScope(BaseModel):
    source_schema_id: UUID | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


class MemoryEffectivenessCoverage(BaseModel):
    source_field_count: int
    covered_field_count: int
    exact_context_coverage_pct: float | None
    no_match_rate_pct: float | None


class MemoryEffectivenessReuse(BaseModel):
    field_mapping_count: int
    memory_derived_mapping_count: int
    memory_reuse_rate_pct: float | None
    unchanged_reuse_count: int
    unchanged_reuse_pct: float | None
    modified_reuse_count: int
    modified_reuse_pct: float | None
    unresolved_origin_count: int


class MemoryEffectivenessQuality(BaseModel):
    memory_item_count: int
    contradiction_item_count: int
    contradiction_rate_pct: float | None
    stale_memory_count: int
    stale_memory_rate_pct: float | None
    stale_reason_breakdown: dict[str, int] = Field(default_factory=dict)


class MemoryEffectivenessTrendPoint(BaseModel):
    source_schema_id: UUID
    case_sequence: int
    discovered_at: datetime
    field_count: int
    covered_field_count: int
    exact_context_coverage_pct: float | None
    no_match_rate_pct: float | None


class MemoryEffectivenessAudit(BaseModel):
    retrieved_event_count: int
    no_match_event_count: int


class MemoryEffectivenessRead(BaseModel):
    organization_id: UUID
    generated_at: datetime
    scope: MemoryEffectivenessScope
    coverage: MemoryEffectivenessCoverage
    reuse: MemoryEffectivenessReuse
    quality: MemoryEffectivenessQuality
    trend: list[MemoryEffectivenessTrendPoint]
    audit: MemoryEffectivenessAudit
