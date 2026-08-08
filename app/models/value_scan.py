from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.entities import portable_json, utc_now


class DirectionalValueScan(Base):
    __tablename__ = "directional_value_scans"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_directional_value_scans_org_id",
        ),
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_directional_value_scans_org_idempotency",
        ),
        UniqueConstraint(
            "organization_id",
            "input_fingerprint",
            name="uq_directional_value_scans_org_input_fingerprint",
        ),
        CheckConstraint(
            "status IN ('completed', 'partial', 'refused')",
            name="ck_directional_value_scans_status",
        ),
        CheckConstraint(
            "candidate_finding_count >= 0",
            name="ck_directional_value_scans_candidate_count_non_negative",
        ),
        CheckConstraint(
            "opportunity_count >= 0",
            name="ck_directional_value_scans_opportunity_count_non_negative",
        ),
        CheckConstraint(
            "data_gap_count >= 0",
            name="ck_directional_value_scans_data_gap_count_non_negative",
        ),
        CheckConstraint(
            "opportunity_count <= candidate_finding_count",
            name="ck_directional_value_scans_opportunity_within_candidates",
        ),
        Index(
            "ix_directional_value_scans_org_generated_at",
            "organization_id",
            "generated_at",
        ),
        Index(
            "ix_directional_value_scans_org_status",
            "organization_id",
            "status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    requested_by_user_id: Mapped[UUID] = mapped_column(Uuid)
    idempotency_key: Mapped[str] = mapped_column(String(255))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    ranking_policy_code: Mapped[str] = mapped_column(String(100))
    ranking_policy_version: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    candidate_finding_count: Mapped[int] = mapped_column(Integer)
    opportunity_count: Mapped[int] = mapped_column(Integer)
    data_gap_count: Mapped[int] = mapped_column(Integer)
    data_coverage_snapshot: Mapped[dict[str, object]] = mapped_column(portable_json)
    trust_readiness_snapshot: Mapped[dict[str, object]] = mapped_column(portable_json)
    customer_context_snapshot: Mapped[dict[str, object]] = mapped_column(portable_json)
    opportunity_snapshot: Mapped[list[dict[str, object]]] = mapped_column(portable_json)
    data_gap_snapshot: Mapped[list[dict[str, object]]] = mapped_column(portable_json)
    next_investigation_snapshot: Mapped[dict[str, object] | None] = mapped_column(
        portable_json, nullable=True
    )
    provenance_snapshot: Mapped[dict[str, object]] = mapped_column(portable_json)
    limitations: Mapped[list[str]] = mapped_column(portable_json)
    result_content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


def _prevent_directional_value_scan_mutation(*_: object) -> None:
    raise ValueError("directional value scans are immutable")


event.listen(DirectionalValueScan, "before_update", _prevent_directional_value_scan_mutation)
event.listen(DirectionalValueScan, "before_delete", _prevent_directional_value_scan_mutation)
