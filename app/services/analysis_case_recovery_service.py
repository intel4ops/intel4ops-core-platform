from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis_case import AnalysisCaseRecoveryRecord, RecoveryStatus


class AnalysisCaseRecoveryServiceError(ValueError):
    def __init__(self, message: str, *, code: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class AnalysisCaseRecoveryService:
    """Do NOT claim value is verified merely because an action was closed
    (Section 14/15): verified_value may only be set when recovery_status is
    explicitly 'verified' AND evidence_json is non-empty -- enforced here,
    not left to the caller's discretion."""

    def upsert(
        self,
        db: Session,
        organization_id: UUID,
        analysis_case_id: UUID,
        action_id: UUID,
        finding_id: UUID,
        baseline_condition: str | None,
        intervention_summary: str | None,
        recovery_status: str,
        observed_post_condition: dict[str, object] | None,
        observed_value: float | None,
        estimated_value: float | None,
        verified_value: float | None,
        currency_detail: dict[str, object] | None,
        evidence_json: dict[str, object] | None,
    ) -> AnalysisCaseRecoveryRecord:
        if verified_value is not None:
            if recovery_status != RecoveryStatus.VERIFIED.value:
                raise AnalysisCaseRecoveryServiceError(
                    "verified_value requires recovery_status=verified",
                    code="verification_not_eligible",
                    status=422,
                )
            if not evidence_json:
                raise AnalysisCaseRecoveryServiceError(
                    "verified_value requires non-empty evidence",
                    code="verification_evidence_required",
                    status=422,
                )

        record = db.scalar(
            select(AnalysisCaseRecoveryRecord).where(
                AnalysisCaseRecoveryRecord.organization_id == organization_id,
                AnalysisCaseRecoveryRecord.action_id == action_id,
                AnalysisCaseRecoveryRecord.finding_id == finding_id,
            )
        )
        if record is None:
            record = AnalysisCaseRecoveryRecord(
                organization_id=organization_id,
                analysis_case_id=analysis_case_id,
                action_id=action_id,
                finding_id=finding_id,
            )
            db.add(record)

        record.baseline_condition = baseline_condition
        record.intervention_summary = intervention_summary
        record.recovery_status = recovery_status
        record.observed_post_condition = observed_post_condition
        record.observed_value = observed_value
        record.estimated_value = estimated_value
        record.verified_value = verified_value
        record.currency_detail = currency_detail
        record.evidence_json = evidence_json
        db.commit()
        db.refresh(record)
        return record

    def get(
        self, db: Session, organization_id: UUID, action_id: UUID, finding_id: UUID
    ) -> AnalysisCaseRecoveryRecord | None:
        return db.scalar(
            select(AnalysisCaseRecoveryRecord).where(
                AnalysisCaseRecoveryRecord.organization_id == organization_id,
                AnalysisCaseRecoveryRecord.action_id == action_id,
                AnalysisCaseRecoveryRecord.finding_id == finding_id,
            )
        )


analysis_case_recovery_service = AnalysisCaseRecoveryService()
