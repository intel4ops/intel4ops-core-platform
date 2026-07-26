from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.engines.action_engine import ActionStatus
from app.engines.economics_engine import OpportunityStatus
from app.engines.recovery_ledger_engine import (
    LedgerEntryType,
    MeasurementInput,
    calculate_realized_value,
)
from app.models.actions import OperationalAction
from app.models.economics import EconomicBaselineVersion, OpportunityAction, RecoveryOpportunity
from app.models.recovery_ledger import (
    RecoveryAuditEvent,
    RecoveryCase,
    RecoveryEvidenceLink,
    RecoveryExecution,
    RecoveryFinanceVerification,
    RecoveryValueMeasurement,
    VerifiedValueLedgerEntry,
)
from app.schemas.recovery_ledger import (
    CaseCreate,
    CaseUpdate,
    CurrencyValue,
    ExecutionCreate,
    FinanceReviewCreate,
    LedgerMutationCreate,
    MeasurementCreate,
    ValueSummary,
    VerifyCreate,
)


class RecoveryLedgerError(ValueError):
    def __init__(self, code: str, message: str, status: int = 422) -> None:
        self.code = code
        self.status = status
        super().__init__(message)


class RecoveryLedgerService:
    def create_case(self, db: Session, org: UUID, payload: CaseCreate, actor: UUID) -> RecoveryCase:
        prior = db.scalar(
            select(RecoveryCase).where(
                RecoveryCase.organization_id == org,
                RecoveryCase.idempotency_key == payload.idempotency_key,
            )
        )
        if prior:
            return prior
        opportunity = db.scalar(
            select(RecoveryOpportunity).where(
                RecoveryOpportunity.id == payload.opportunity_id,
                RecoveryOpportunity.organization_id == org,
            )
        )
        baseline = db.scalar(
            select(EconomicBaselineVersion).where(
                EconomicBaselineVersion.id == payload.baseline_id,
                EconomicBaselineVersion.organization_id == org,
            )
        )
        if (
            opportunity is None
            or baseline is None
            or baseline.opportunity_id != payload.opportunity_id
        ):
            raise RecoveryLedgerError("BASELINE_NOT_FOUND", "Approved baseline was not found", 404)
        if opportunity.status != OpportunityStatus.APPROVED_FOR_ACTION.value:
            raise RecoveryLedgerError(
                "BASELINE_NOT_APPROVED", "Opportunity must have an approved baseline"
            )
        expected = Decimal(str(baseline.economic_snapshot["expected_net_benefit"]))
        row = RecoveryCase(
            organization_id=org,
            opportunity_id=opportunity.id,
            baseline_id=baseline.id,
            case_code=f"RCS-{uuid4().hex[:12].upper()}",
            idempotency_key=payload.idempotency_key,
            title=payload.title,
            description=payload.description,
            currency_code=baseline.currency_code,
            expected_value=expected,
            created_by_user_id=actor,
        )
        db.add(row)
        db.flush()
        self._audit(
            db,
            row,
            "case_created",
            actor,
            f"case:{payload.idempotency_key}",
            "Recovery case created",
        )
        db.commit()
        db.refresh(row)
        return row

    def get_case(self, db: Session, org: UUID, case_id: UUID) -> RecoveryCase:
        row = db.scalar(
            select(RecoveryCase).where(
                RecoveryCase.id == case_id, RecoveryCase.organization_id == org
            )
        )
        if row is None:
            raise RecoveryLedgerError("NOT_FOUND", "Recovery case not found", 404)
        return row

    def list_cases(self, db: Session, org: UUID) -> list[RecoveryCase]:
        return list(
            db.scalars(
                select(RecoveryCase)
                .where(RecoveryCase.organization_id == org)
                .order_by(RecoveryCase.created_at.desc())
            )
        )

    def update_case(
        self, db: Session, org: UUID, case_id: UUID, payload: CaseUpdate, actor: UUID
    ) -> RecoveryCase:
        row = self.get_case(db, org, case_id)
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(row, key, value)
        self._audit(
            db, row, "case_updated", actor, f"case-update:{uuid4()}", "Recovery case updated"
        )
        db.commit()
        db.refresh(row)
        return row

    def create_execution(
        self, db: Session, org: UUID, case_id: UUID, payload: ExecutionCreate, actor: UUID
    ) -> RecoveryExecution:
        case = self.get_case(db, org, case_id)
        prior = db.scalar(
            select(RecoveryExecution).where(
                RecoveryExecution.organization_id == org,
                RecoveryExecution.idempotency_key == payload.idempotency_key,
            )
        )
        if prior:
            return prior
        action = db.scalar(
            select(OperationalAction).where(
                OperationalAction.id == payload.action_id, OperationalAction.organization_id == org
            )
        )
        linked = db.scalar(
            select(OpportunityAction).where(
                OpportunityAction.organization_id == org,
                OpportunityAction.opportunity_id == case.opportunity_id,
                OpportunityAction.action_id == payload.action_id,
            )
        )
        allowed = {
            ActionStatus.APPROVED.value,
            ActionStatus.ASSIGNED.value,
            ActionStatus.SCHEDULED.value,
            ActionStatus.IN_PROGRESS.value,
            ActionStatus.BLOCKED.value,
            ActionStatus.COMPLETED.value,
            ActionStatus.VERIFICATION_PENDING.value,
            ActionStatus.VERIFIED.value,
        }
        if action is None or linked is None:
            raise RecoveryLedgerError(
                "ACTION_NOT_LINKED", "Action is not linked to this opportunity", 404
            )
        if action.status not in allowed:
            raise RecoveryLedgerError(
                "ACTION_NOT_APPROVED", "Action must be approved before recovery execution"
            )
        row = RecoveryExecution(
            organization_id=org,
            recovery_case_id=case.id,
            action_id=action.id,
            idempotency_key=payload.idempotency_key,
            execution_notes=payload.execution_notes,
            created_by_user_id=actor,
        )
        db.add(row)
        db.flush()
        self._audit(
            db,
            case,
            "execution_created",
            actor,
            f"execution:{payload.idempotency_key}",
            "Recovery execution created",
        )
        db.commit()
        db.refresh(row)
        return row

    def transition_execution(
        self, db: Session, org: UUID, execution_id: UUID, transition: str, actor: UUID
    ) -> RecoveryExecution:
        row, case = self._execution(db, org, execution_id)
        now = datetime.now(UTC)
        if transition == "start" and row.status == "planned":
            row.status, row.started_at = "in_progress", now
        elif transition == "complete" and row.status == "in_progress":
            row.status, row.completed_at = "awaiting_measurement", now
        else:
            raise RecoveryLedgerError(
                "INVALID_TRANSITION", f"Cannot {transition} execution from {row.status}", 409
            )
        self._audit(
            db,
            case,
            f"execution_{transition}ed",
            actor,
            f"{transition}:{execution_id}:{now.isoformat()}",
            f"Execution {transition}ed",
        )
        db.commit()
        db.refresh(row)
        return row

    def create_measurement(
        self, db: Session, org: UUID, execution_id: UUID, payload: MeasurementCreate, actor: UUID
    ) -> RecoveryValueMeasurement:
        execution, case = self._execution(db, org, execution_id)
        prior = db.scalar(
            select(RecoveryValueMeasurement).where(
                RecoveryValueMeasurement.organization_id == org,
                RecoveryValueMeasurement.idempotency_key == payload.idempotency_key,
            )
        )
        if prior:
            return prior
        if execution.status not in {"awaiting_measurement", "measured"}:
            raise RecoveryLedgerError(
                "EXECUTION_NOT_COMPLETE", "Execution must be completed before measurement"
            )
        if payload.currency_code != case.currency_code:
            raise RecoveryLedgerError(
                "CURRENCY_MISMATCH", "Measurement currency must match approved baseline"
            )
        inputs = payload.calculation_inputs
        realized = calculate_realized_value(
            MeasurementInput(
                payload.category,
                payload.baseline_amount,
                payload.actual_amount,
                payload.currency_code,
                Decimal(str(inputs["days_accelerated"])) if "days_accelerated" in inputs else None,
                Decimal(str(inputs["annual_rate"])) if "annual_rate" in inputs else None,
            )
        )
        values = payload.model_dump(exclude={"evidence"})
        row = RecoveryValueMeasurement(
            organization_id=org,
            execution_id=execution.id,
            realized_value=realized,
            created_by_user_id=actor,
            **values,
        )
        db.add(row)
        db.flush()
        db.add_all(
            [
                RecoveryEvidenceLink(
                    organization_id=org,
                    measurement_id=row.id,
                    created_by_user_id=actor,
                    **e.model_dump(),
                )
                for e in payload.evidence
            ]
        )
        execution.status = "measured"
        self._audit(
            db,
            case,
            "measurement_created",
            actor,
            f"measurement:{payload.idempotency_key}",
            "Realized value measured",
        )
        db.commit()
        db.refresh(row)
        return row

    def list_measurements(
        self, db: Session, org: UUID, execution_id: UUID
    ) -> list[RecoveryValueMeasurement]:
        self._execution(db, org, execution_id)
        return list(
            db.scalars(
                select(RecoveryValueMeasurement).where(
                    RecoveryValueMeasurement.organization_id == org,
                    RecoveryValueMeasurement.execution_id == execution_id,
                )
            )
        )

    def submit_measurement(
        self, db: Session, org: UUID, measurement_id: UUID, actor: UUID
    ) -> RecoveryValueMeasurement:
        row, case = self._measurement(db, org, measurement_id)
        evidence_count = (
            db.scalar(
                select(func.count())
                .select_from(RecoveryEvidenceLink)
                .where(
                    RecoveryEvidenceLink.organization_id == org,
                    RecoveryEvidenceLink.measurement_id == row.id,
                )
            )
            or 0
        )
        if row.status != "draft" or not evidence_count:
            raise RecoveryLedgerError(
                "MEASUREMENT_NOT_SUBMITTABLE", "Draft measurement with evidence is required", 409
            )
        row.status, row.submitted_by_user_id, row.submitted_at = (
            "submitted",
            actor,
            datetime.now(UTC),
        )
        self._audit(
            db,
            case,
            "measurement_submitted",
            actor,
            f"submit:{measurement_id}",
            "Measurement submitted for finance review",
        )
        db.commit()
        db.refresh(row)
        return row

    def finance_review(
        self,
        db: Session,
        org: UUID,
        measurement_id: UUID,
        payload: FinanceReviewCreate,
        actor: UUID,
    ) -> RecoveryValueMeasurement:
        row, case = self._measurement(db, org, measurement_id)
        self._require_separate_reviewer(row, actor)
        if row.status != "submitted":
            raise RecoveryLedgerError(
                "MEASUREMENT_NOT_SUBMITTED", "Measurement is not awaiting finance review", 409
            )
        verification = RecoveryFinanceVerification(
            organization_id=org,
            measurement_id=row.id,
            idempotency_key=payload.idempotency_key,
            decision=payload.decision,
            verified_amount=Decimal("0"),
            currency_code=row.currency_code,
            rationale=payload.rationale,
            reviewer_user_id=actor,
        )
        db.add(verification)
        row.status = payload.decision
        self._audit(
            db,
            case,
            "finance_reviewed",
            actor,
            f"review:{payload.idempotency_key}",
            payload.rationale,
        )
        db.commit()
        db.refresh(row)
        return row

    def verify(
        self, db: Session, org: UUID, measurement_id: UUID, payload: VerifyCreate, actor: UUID
    ) -> VerifiedValueLedgerEntry:
        row, case = self._measurement(db, org, measurement_id, lock=True)
        self._require_separate_reviewer(row, actor)
        prior = db.scalar(
            select(RecoveryFinanceVerification).where(
                RecoveryFinanceVerification.organization_id == org,
                RecoveryFinanceVerification.idempotency_key == payload.idempotency_key,
            )
        )
        if prior:
            ledger = db.scalar(
                select(VerifiedValueLedgerEntry).where(
                    VerifiedValueLedgerEntry.verification_id == prior.id,
                    VerifiedValueLedgerEntry.organization_id == org,
                )
            )
            if ledger:
                return ledger
        if row.status != "submitted":
            raise RecoveryLedgerError(
                "MEASUREMENT_NOT_SUBMITTED", "Measurement is not awaiting finance verification", 409
            )
        if payload.currency_code != row.currency_code:
            raise RecoveryLedgerError(
                "CURRENCY_MISMATCH", "Verification currency must match measurement"
            )
        verification = RecoveryFinanceVerification(
            organization_id=org,
            measurement_id=row.id,
            idempotency_key=payload.idempotency_key,
            decision="approved",
            verified_amount=payload.verified_amount,
            currency_code=payload.currency_code,
            rationale=payload.rationale,
            reviewer_user_id=actor,
        )
        db.add(verification)
        db.flush()
        ledger = self._ledger_entry(
            db,
            case,
            actor,
            payload.idempotency_key,
            LedgerEntryType.VERIFIED_RECOVERY,
            payload.verified_amount,
            payload.rationale,
            measurement_id=row.id,
            verification_id=verification.id,
        )
        row.status = "verified"
        self._audit(
            db,
            case,
            "value_verified",
            actor,
            f"verify:{payload.idempotency_key}",
            payload.rationale,
        )
        db.commit()
        db.refresh(ledger)
        return ledger

    def list_ledger(
        self,
        db: Session,
        org: UUID,
        page: int,
        page_size: int,
        case_id: UUID | None = None,
        currency: str | None = None,
    ) -> tuple[list[VerifiedValueLedgerEntry], int]:
        conditions = [VerifiedValueLedgerEntry.organization_id == org]
        if case_id:
            conditions.append(VerifiedValueLedgerEntry.recovery_case_id == case_id)
        if currency:
            conditions.append(VerifiedValueLedgerEntry.currency_code == currency)
        total = (
            db.scalar(select(func.count()).select_from(VerifiedValueLedgerEntry).where(*conditions))
            or 0
        )
        rows = list(
            db.scalars(
                select(VerifiedValueLedgerEntry)
                .where(*conditions)
                .order_by(
                    VerifiedValueLedgerEntry.posted_at, VerifiedValueLedgerEntry.entry_sequence
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return rows, total

    def get_ledger(self, db: Session, org: UUID, entry_id: UUID) -> VerifiedValueLedgerEntry:
        row = db.scalar(
            select(VerifiedValueLedgerEntry).where(
                VerifiedValueLedgerEntry.id == entry_id,
                VerifiedValueLedgerEntry.organization_id == org,
            )
        )
        if row is None:
            raise RecoveryLedgerError("NOT_FOUND", "Ledger entry not found", 404)
        return row

    def adjustment(
        self, db: Session, org: UUID, entry_id: UUID, payload: LedgerMutationCreate, actor: UUID
    ) -> VerifiedValueLedgerEntry:
        original = self.get_ledger(db, org, entry_id)
        case = self.get_case(db, org, original.recovery_case_id)
        if payload.direction is None:
            raise RecoveryLedgerError("DIRECTION_REQUIRED", "Adjustment direction is required")
        entry_type = (
            LedgerEntryType.ADJUSTMENT_POSITIVE
            if payload.direction == "positive"
            else LedgerEntryType.ADJUSTMENT_NEGATIVE
        )
        amount = payload.amount if payload.direction == "positive" else -payload.amount
        row = self._ledger_entry(
            db,
            case,
            actor,
            payload.idempotency_key,
            entry_type,
            amount,
            payload.reason,
            measurement_id=original.measurement_id,
            adjustment_of=original.id,
        )
        self._audit(
            db, case, "ledger_adjusted", actor, f"adjust:{payload.idempotency_key}", payload.reason
        )
        db.commit()
        db.refresh(row)
        return row

    def reversal(
        self, db: Session, org: UUID, entry_id: UUID, payload: LedgerMutationCreate, actor: UUID
    ) -> VerifiedValueLedgerEntry:
        original = db.scalar(
            select(VerifiedValueLedgerEntry)
            .where(
                VerifiedValueLedgerEntry.id == entry_id,
                VerifiedValueLedgerEntry.organization_id == org,
            )
            .with_for_update()
        )
        if original is None:
            raise RecoveryLedgerError("NOT_FOUND", "Ledger entry not found", 404)
        reversed_total = abs(
            db.scalar(
                select(func.coalesce(func.sum(VerifiedValueLedgerEntry.amount), 0)).where(
                    VerifiedValueLedgerEntry.organization_id == org,
                    VerifiedValueLedgerEntry.reversal_of_ledger_entry_id == entry_id,
                )
            )
            or Decimal("0")
        )
        if payload.amount > abs(original.amount) - reversed_total:
            raise RecoveryLedgerError(
                "REVERSAL_EXCEEDS_REMAINING", "Reversal exceeds remaining posted value", 409
            )
        case = self.get_case(db, org, original.recovery_case_id)
        row = self._ledger_entry(
            db,
            case,
            actor,
            payload.idempotency_key,
            LedgerEntryType.REVERSAL,
            -payload.amount,
            payload.reason,
            measurement_id=original.measurement_id,
            reversal_of=original.id,
        )
        self._audit(
            db, case, "ledger_reversed", actor, f"reverse:{payload.idempotency_key}", payload.reason
        )
        db.commit()
        db.refresh(row)
        return row

    def summary(self, db: Session, org: UUID, case_id: UUID) -> ValueSummary:
        case = self.get_case(db, org, case_id)
        realized = db.scalar(
            select(func.coalesce(func.sum(RecoveryValueMeasurement.realized_value), 0))
            .join(RecoveryExecution, RecoveryExecution.id == RecoveryValueMeasurement.execution_id)
            .where(
                RecoveryValueMeasurement.organization_id == org,
                RecoveryExecution.recovery_case_id == case_id,
            )
        ) or Decimal("0")
        verified = db.scalar(
            select(func.coalesce(func.sum(RecoveryFinanceVerification.verified_amount), 0))
            .join(
                RecoveryValueMeasurement,
                RecoveryValueMeasurement.id == RecoveryFinanceVerification.measurement_id,
            )
            .join(RecoveryExecution, RecoveryExecution.id == RecoveryValueMeasurement.execution_id)
            .where(
                RecoveryFinanceVerification.organization_id == org,
                RecoveryFinanceVerification.decision == "approved",
                RecoveryExecution.recovery_case_id == case_id,
            )
        ) or Decimal("0")
        net = db.scalar(
            select(func.coalesce(func.sum(VerifiedValueLedgerEntry.amount), 0)).where(
                VerifiedValueLedgerEntry.organization_id == org,
                VerifiedValueLedgerEntry.recovery_case_id == case_id,
                VerifiedValueLedgerEntry.currency_code == case.currency_code,
            )
        ) or Decimal("0")
        return ValueSummary(
            recovery_case_id=case.id,
            currencies=[
                CurrencyValue(
                    currency_code=case.currency_code,
                    expected_value=case.expected_value,
                    realized_value=realized,
                    verified_value=verified,
                    net_verified_value=net,
                )
            ],
        )

    def _execution(
        self, db: Session, org: UUID, execution_id: UUID
    ) -> tuple[RecoveryExecution, RecoveryCase]:
        row = db.scalar(
            select(RecoveryExecution).where(
                RecoveryExecution.id == execution_id, RecoveryExecution.organization_id == org
            )
        )
        if row is None:
            raise RecoveryLedgerError("NOT_FOUND", "Recovery execution not found", 404)
        return row, self.get_case(db, org, row.recovery_case_id)

    def _measurement(
        self, db: Session, org: UUID, measurement_id: UUID, *, lock: bool = False
    ) -> tuple[RecoveryValueMeasurement, RecoveryCase]:
        query = select(RecoveryValueMeasurement).where(
            RecoveryValueMeasurement.id == measurement_id,
            RecoveryValueMeasurement.organization_id == org,
        )
        row = db.scalar(query.with_for_update() if lock else query)
        if row is None:
            raise RecoveryLedgerError("NOT_FOUND", "Recovery measurement not found", 404)
        execution, case = self._execution(db, org, row.execution_id)
        return row, case

    @staticmethod
    def _require_separate_reviewer(row: RecoveryValueMeasurement, actor: UUID) -> None:
        if row.submitted_by_user_id == actor:
            raise RecoveryLedgerError(
                "SEGREGATION_OF_DUTIES",
                "Submitter cannot finance-approve the same measurement",
                403,
            )

    def _ledger_entry(
        self,
        db: Session,
        case: RecoveryCase,
        actor: UUID,
        key: str,
        entry_type: LedgerEntryType,
        amount: Decimal,
        reason: str,
        *,
        measurement_id: UUID | None = None,
        verification_id: UUID | None = None,
        reversal_of: UUID | None = None,
        adjustment_of: UUID | None = None,
    ) -> VerifiedValueLedgerEntry:
        prior = db.scalar(
            select(VerifiedValueLedgerEntry).where(
                VerifiedValueLedgerEntry.organization_id == case.organization_id,
                VerifiedValueLedgerEntry.idempotency_key == key,
            )
        )
        if prior:
            return prior
        sequence = (
            db.scalar(
                select(func.max(VerifiedValueLedgerEntry.entry_sequence)).where(
                    VerifiedValueLedgerEntry.recovery_case_id == case.id
                )
            )
            or 0
        ) + 1
        material = (
            f"{case.organization_id}|{case.id}|{sequence}|{entry_type.value}|"
            f"{amount}|{case.currency_code}|{key}"
        )
        row = VerifiedValueLedgerEntry(
            organization_id=case.organization_id,
            recovery_case_id=case.id,
            measurement_id=measurement_id,
            verification_id=verification_id,
            reversal_of_ledger_entry_id=reversal_of,
            adjustment_of_ledger_entry_id=adjustment_of,
            entry_sequence=sequence,
            entry_type=entry_type.value,
            amount=amount,
            currency_code=case.currency_code,
            idempotency_key=key,
            reason=reason,
            entry_hash=hashlib.sha256(material.encode()).hexdigest(),
            posted_by_user_id=actor,
        )
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def _audit(
        db: Session, case: RecoveryCase, event_type: str, actor: UUID, key: str, reason: str
    ) -> None:
        db.add(
            RecoveryAuditEvent(
                organization_id=case.organization_id,
                recovery_case_id=case.id,
                event_type=event_type,
                actor_user_id=actor,
                idempotency_key=key,
                reason=reason,
            )
        )


recovery_ledger_service = RecoveryLedgerService()
