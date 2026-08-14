from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.actions import ActionEvent, ActionEvidence, ActionOutcome, OperationalAction
from app.models.recovery_ledger import (
    RecoveryAuditEvent,
    RecoveryCase,
    RecoveryEvidenceLink,
    RecoveryExecution,
    RecoveryFinanceVerification,
    RecoveryValueMeasurement,
    VerifiedValueLedgerEntry,
)
from app.schemas.actions import ActionRead
from app.schemas.decision_intelligence import (
    DecisionApprovalRead,
    DecisionWorkspaceRecommendationRead,
)
from app.schemas.recovery_ledger import CaseRead, ExecutionRead, LedgerRead, MeasurementRead
from app.schemas.recovery_workspace import (
    RecoveryWorkspaceActionEventRead,
    RecoveryWorkspaceActionEvidenceRead,
    RecoveryWorkspaceActionOutcomeRead,
    RecoveryWorkspaceAuditEventRead,
    RecoveryWorkspaceEvidenceRead,
    RecoveryWorkspaceRead,
    RecoveryWorkspaceVerificationRead,
)
from app.services.decision_intelligence_service import finding_decision_workspace_service


class RecoveryWorkspaceService:
    def get(self, db: Session, organization_id: UUID, finding_id: UUID) -> RecoveryWorkspaceRead:
        recommendation, approval, _ = finding_decision_workspace_service.get(
            db, organization_id, finding_id
        )
        empty: dict[str, object] = {
            "action_evidence": [],
            "action_outcomes": [],
            "action_history": [],
            "recovery_case": None,
            "recovery_execution": None,
            "measurements": [],
            "measurement_evidence": [],
            "latest_verification": None,
            "verification_history": [],
            "verified_ledger": [],
            "recovery_history": [],
        }
        recommendation_read = (
            DecisionWorkspaceRecommendationRead.model_validate(recommendation)
            if recommendation is not None
            else None
        )
        approval_read = (
            DecisionApprovalRead.model_validate(approval) if approval is not None else None
        )
        if recommendation is None or recommendation.converted_action_id is None:
            return RecoveryWorkspaceRead(
                finding_id=finding_id,
                recommendation=recommendation_read,
                approval=approval_read,
                action=None,
                **empty,
            )

        action = db.scalar(
            select(OperationalAction).where(
                OperationalAction.id == recommendation.converted_action_id,
                OperationalAction.organization_id == organization_id,
            )
        )
        if action is None:
            return RecoveryWorkspaceRead(
                finding_id=finding_id,
                recommendation=recommendation_read,
                approval=approval_read,
                action=None,
                **empty,
            )

        action_evidence = list(
            db.scalars(
                select(ActionEvidence)
                .where(
                    ActionEvidence.organization_id == organization_id,
                    ActionEvidence.action_id == action.id,
                )
                .order_by(ActionEvidence.created_at, ActionEvidence.id)
            )
        )
        action_outcomes = list(
            db.scalars(
                select(ActionOutcome)
                .where(
                    ActionOutcome.organization_id == organization_id,
                    ActionOutcome.action_id == action.id,
                )
                .order_by(ActionOutcome.created_at, ActionOutcome.id)
            )
        )
        action_history = list(
            db.scalars(
                select(ActionEvent)
                .where(
                    ActionEvent.organization_id == organization_id,
                    ActionEvent.action_id == action.id,
                )
                .order_by(ActionEvent.occurred_at, ActionEvent.id)
            )
        )
        execution = db.scalar(
            select(RecoveryExecution)
            .where(
                RecoveryExecution.organization_id == organization_id,
                RecoveryExecution.action_id == action.id,
            )
            .order_by(RecoveryExecution.created_at.desc(), RecoveryExecution.id.desc())
            .limit(1)
        )
        if execution is None:
            return RecoveryWorkspaceRead(
                finding_id=finding_id,
                recommendation=recommendation_read,
                approval=approval_read,
                action=ActionRead.model_validate(action),
                action_evidence=[
                    RecoveryWorkspaceActionEvidenceRead.model_validate(item)
                    for item in action_evidence
                ],
                action_outcomes=[
                    RecoveryWorkspaceActionOutcomeRead.model_validate(item)
                    for item in action_outcomes
                ],
                action_history=[
                    RecoveryWorkspaceActionEventRead.model_validate(item) for item in action_history
                ],
                **{key: value for key, value in empty.items() if not key.startswith("action_")},
            )

        case = db.scalar(
            select(RecoveryCase).where(
                RecoveryCase.organization_id == organization_id,
                RecoveryCase.id == execution.recovery_case_id,
            )
        )
        measurements = list(
            db.scalars(
                select(RecoveryValueMeasurement)
                .where(
                    RecoveryValueMeasurement.organization_id == organization_id,
                    RecoveryValueMeasurement.execution_id == execution.id,
                )
                .order_by(RecoveryValueMeasurement.created_at, RecoveryValueMeasurement.id)
            )
        )
        measurement_ids = [item.id for item in measurements]
        evidence = (
            list(
                db.scalars(
                    select(RecoveryEvidenceLink)
                    .where(
                        RecoveryEvidenceLink.organization_id == organization_id,
                        RecoveryEvidenceLink.measurement_id.in_(measurement_ids),
                    )
                    .order_by(RecoveryEvidenceLink.created_at, RecoveryEvidenceLink.id)
                )
            )
            if measurement_ids
            else []
        )
        verifications = (
            list(
                db.scalars(
                    select(RecoveryFinanceVerification)
                    .where(
                        RecoveryFinanceVerification.organization_id == organization_id,
                        RecoveryFinanceVerification.measurement_id.in_(measurement_ids),
                    )
                    .order_by(
                        RecoveryFinanceVerification.reviewed_at.desc(),
                        RecoveryFinanceVerification.id.desc(),
                    )
                )
            )
            if measurement_ids
            else []
        )
        ledger = (
            list(
                db.scalars(
                    select(VerifiedValueLedgerEntry)
                    .where(
                        VerifiedValueLedgerEntry.organization_id == organization_id,
                        VerifiedValueLedgerEntry.recovery_case_id == case.id,
                    )
                    .order_by(VerifiedValueLedgerEntry.entry_sequence)
                )
            )
            if case is not None
            else []
        )
        recovery_history = (
            list(
                db.scalars(
                    select(RecoveryAuditEvent)
                    .where(
                        RecoveryAuditEvent.organization_id == organization_id,
                        RecoveryAuditEvent.recovery_case_id == case.id,
                    )
                    .order_by(RecoveryAuditEvent.occurred_at, RecoveryAuditEvent.id)
                )
            )
            if case is not None
            else []
        )
        return RecoveryWorkspaceRead(
            finding_id=finding_id,
            recommendation=recommendation_read,
            approval=approval_read,
            action=ActionRead.model_validate(action),
            action_evidence=[
                RecoveryWorkspaceActionEvidenceRead.model_validate(item) for item in action_evidence
            ],
            action_outcomes=[
                RecoveryWorkspaceActionOutcomeRead.model_validate(item) for item in action_outcomes
            ],
            action_history=[
                RecoveryWorkspaceActionEventRead.model_validate(item) for item in action_history
            ],
            recovery_case=CaseRead.model_validate(case) if case is not None else None,
            recovery_execution=ExecutionRead.model_validate(execution),
            measurements=[MeasurementRead.model_validate(item) for item in measurements],
            measurement_evidence=[
                RecoveryWorkspaceEvidenceRead.model_validate(item) for item in evidence
            ],
            latest_verification=(
                RecoveryWorkspaceVerificationRead.model_validate(verifications[0])
                if verifications
                else None
            ),
            verification_history=[
                RecoveryWorkspaceVerificationRead.model_validate(item) for item in verifications
            ],
            verified_ledger=[LedgerRead.model_validate(item) for item in ledger],
            recovery_history=[
                RecoveryWorkspaceAuditEventRead.model_validate(item) for item in recovery_history
            ],
        )


recovery_workspace_service = RecoveryWorkspaceService()
