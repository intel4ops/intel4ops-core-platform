from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from decimal import Decimal
from typing import TypeVar
from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.models.actions import ActionEvent, ActionOutcome, OperationalAction
from app.models.decision_intelligence import (
    DecisionApproval,
    DecisionExecution,
    DecisionRecommendation,
    DecisionScenarioInput,
    DecisionSolution,
)
from app.models.entities import Finding
from app.models.recovery_ledger import (
    RecoveryAuditEvent,
    RecoveryCase,
    RecoveryExecution,
    RecoveryFinanceVerification,
    RecoveryValueMeasurement,
    VerifiedValueLedgerEntry,
)
from app.schemas.recovery_portfolio import (
    PortfolioCurrencyValue,
    RecoveryPortfolioItem,
    RecoveryPortfolioPagination,
    RecoveryPortfolioPipeline,
    RecoveryPortfolioRead,
    RecoveryPortfolioSummary,
)

ACTIVE_ACTION_STATUSES = {
    "approved",
    "assigned",
    "scheduled",
    "in_progress",
    "blocked",
    "completed",
    "verification_pending",
    "verification_rejected",
}
TERMINAL_ACTION_STATUSES = {"verified", "rejected", "cancelled"}
VERIFICATION_ATTENTION_STATUSES = {"needs_information", "rejected"}
T = TypeVar("T")


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class RecoveryPortfolioService:
    def get(
        self,
        db: Session,
        organization_id: UUID,
        *,
        page: int,
        page_size: int,
        owner_user_id: UUID | None = None,
        owner_role: str | None = None,
        currency: str | None = None,
        overdue_only: bool = False,
        verification_status: str | None = None,
        finding_id: UUID | None = None,
        action_id: UUID | None = None,
        recovery_case_id: UUID | None = None,
    ) -> RecoveryPortfolioRead:
        now = datetime.now(UTC)
        base = (
            select(Finding, DecisionRecommendation, OperationalAction)
            .join(
                DecisionScenarioInput,
                (DecisionScenarioInput.source_id == Finding.id)
                & (DecisionScenarioInput.organization_id == Finding.organization_id)
                & (DecisionScenarioInput.input_kind == "finding"),
            )
            .join(
                DecisionExecution,
                (DecisionExecution.scenario_id == DecisionScenarioInput.scenario_id)
                & (DecisionExecution.organization_id == DecisionScenarioInput.organization_id),
            )
            .join(
                DecisionSolution,
                (DecisionSolution.execution_id == DecisionExecution.id)
                & (DecisionSolution.organization_id == DecisionExecution.organization_id),
            )
            .join(
                DecisionRecommendation,
                (DecisionRecommendation.solution_id == DecisionSolution.id)
                & (DecisionRecommendation.organization_id == DecisionSolution.organization_id),
            )
            .outerjoin(
                OperationalAction,
                (OperationalAction.id == DecisionRecommendation.converted_action_id)
                & (OperationalAction.organization_id == DecisionRecommendation.organization_id),
            )
            .where(Finding.organization_id == organization_id)
        )
        if finding_id is not None:
            base = base.where(Finding.id == finding_id)
        if action_id is not None:
            base = base.where(OperationalAction.id == action_id)
        if owner_user_id is not None:
            base = base.where(OperationalAction.assigned_user_id == owner_user_id)
        if owner_role is not None:
            base = base.where(OperationalAction.assigned_role == owner_role)
        if currency is not None:
            base = base.where(OperationalAction.currency_code == currency)
        if overdue_only:
            base = base.where(
                OperationalAction.due_at < now,
                OperationalAction.status.not_in(TERMINAL_ACTION_STATUSES),
            )
        if recovery_case_id is not None:
            base = base.where(
                exists(
                    select(RecoveryExecution.id).where(
                        RecoveryExecution.organization_id == organization_id,
                        RecoveryExecution.action_id == OperationalAction.id,
                        RecoveryExecution.recovery_case_id == recovery_case_id,
                    )
                )
            )
        if verification_status is not None:
            base = base.where(
                exists(
                    select(RecoveryFinanceVerification.id)
                    .join(
                        RecoveryValueMeasurement,
                        RecoveryValueMeasurement.id == RecoveryFinanceVerification.measurement_id,
                    )
                    .join(
                        RecoveryExecution,
                        RecoveryExecution.id == RecoveryValueMeasurement.execution_id,
                    )
                    .where(
                        RecoveryFinanceVerification.organization_id == organization_id,
                        RecoveryExecution.action_id == OperationalAction.id,
                        RecoveryFinanceVerification.decision == verification_status,
                    )
                )
            )
        count_query = select(func.count()).select_from(base.order_by(None).subquery())
        total = int(db.scalar(count_query) or 0)
        rows = db.execute(
            base.order_by(DecisionRecommendation.created_at.desc(), DecisionRecommendation.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        items = self._items(
            db,
            organization_id,
            [(row[0], row[1], row[2]) for row in rows],
            now,
        )
        return RecoveryPortfolioRead(
            organization_id=organization_id,
            summary=self._summary(db, organization_id, now),
            pipeline=self._pipeline(db, organization_id),
            items=items,
            pagination=RecoveryPortfolioPagination(page=page, page_size=page_size, total=total),
        )

    def _items(
        self,
        db: Session,
        organization_id: UUID,
        rows: list[tuple[Finding, DecisionRecommendation, OperationalAction | None]],
        now: datetime,
    ) -> list[RecoveryPortfolioItem]:
        recommendation_ids = [row[1].id for row in rows]
        action_ids = [row[2].id for row in rows if row[2] is not None]
        approvals = self._latest_by(
            db.scalars(
                select(DecisionApproval)
                .where(
                    DecisionApproval.organization_id == organization_id,
                    DecisionApproval.recommendation_id.in_(recommendation_ids),
                )
                .order_by(DecisionApproval.decided_at.desc(), DecisionApproval.id.desc())
            ),
            lambda item: item.recommendation_id,
        )
        executions = self._latest_by(
            db.scalars(
                select(RecoveryExecution)
                .where(
                    RecoveryExecution.organization_id == organization_id,
                    RecoveryExecution.action_id.in_(action_ids),
                )
                .order_by(RecoveryExecution.created_at.desc(), RecoveryExecution.id.desc())
            ),
            lambda item: item.action_id,
        )
        case_ids = [item.recovery_case_id for item in executions.values()]
        cases = {
            item.id: item
            for item in db.scalars(
                select(RecoveryCase).where(
                    RecoveryCase.organization_id == organization_id,
                    RecoveryCase.id.in_(case_ids),
                )
            )
        }
        execution_ids = [item.id for item in executions.values()]
        measurements = self._latest_by(
            db.scalars(
                select(RecoveryValueMeasurement)
                .where(
                    RecoveryValueMeasurement.organization_id == organization_id,
                    RecoveryValueMeasurement.execution_id.in_(execution_ids),
                )
                .order_by(
                    RecoveryValueMeasurement.created_at.desc(),
                    RecoveryValueMeasurement.id.desc(),
                )
            ),
            lambda item: item.execution_id,
        )
        measurement_ids = [item.id for item in measurements.values()]
        verifications = self._latest_by(
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
            ),
            lambda item: item.measurement_id,
        )
        outcomes = self._latest_by(
            db.scalars(
                select(ActionOutcome)
                .where(
                    ActionOutcome.organization_id == organization_id,
                    ActionOutcome.action_id.in_(action_ids),
                )
                .order_by(ActionOutcome.created_at.desc(), ActionOutcome.id.desc())
            ),
            lambda item: item.action_id,
        )
        ledger_by_case: dict[UUID, list[VerifiedValueLedgerEntry]] = defaultdict(list)
        for ledger_row in db.scalars(
            select(VerifiedValueLedgerEntry)
            .where(
                VerifiedValueLedgerEntry.organization_id == organization_id,
                VerifiedValueLedgerEntry.recovery_case_id.in_(case_ids),
            )
            .order_by(VerifiedValueLedgerEntry.posted_at, VerifiedValueLedgerEntry.entry_sequence)
        ):
            ledger_by_case[ledger_row.recovery_case_id].append(ledger_row)
        action_activity: dict[UUID, datetime] = {
            action_key: occurred_at
            for action_key, occurred_at in db.execute(
                select(ActionEvent.action_id, func.max(ActionEvent.occurred_at))
                .where(
                    ActionEvent.organization_id == organization_id,
                    ActionEvent.action_id.in_(action_ids),
                )
                .group_by(ActionEvent.action_id)
            ).all()
        }
        case_activity: dict[UUID, datetime] = {
            case_key: occurred_at
            for case_key, occurred_at in db.execute(
                select(
                    RecoveryAuditEvent.recovery_case_id, func.max(RecoveryAuditEvent.occurred_at)
                )
                .where(
                    RecoveryAuditEvent.organization_id == organization_id,
                    RecoveryAuditEvent.recovery_case_id.in_(case_ids),
                )
                .group_by(RecoveryAuditEvent.recovery_case_id)
            ).all()
        }
        result: list[RecoveryPortfolioItem] = []
        for finding, recommendation, action in rows:
            approval = approvals.get(recommendation.id)
            execution = executions.get(action.id) if action is not None else None
            case = cases.get(execution.recovery_case_id) if execution is not None else None
            measurement = measurements.get(execution.id) if execution is not None else None
            verification = verifications.get(measurement.id) if measurement is not None else None
            outcome = outcomes.get(action.id) if action is not None else None
            ledger = ledger_by_case.get(case.id, []) if case is not None else []
            verified_value = (
                sum((entry.amount for entry in ledger), Decimal("0")) if ledger else None
            )
            latest_ledger = ledger[-1] if ledger else None
            stage = self._stage(
                recommendation,
                approval,
                action,
                execution,
                outcome,
                measurement,
                verification,
                ledger,
            )
            overdue = bool(
                action is not None
                and action.due_at is not None
                and _utc(action.due_at) < now
                and action.status not in TERMINAL_ACTION_STATUSES
            )
            attention = (
                overdue
                or stage
                in {
                    "approved_no_action",
                    "verification_pending",
                    "verification_attention",
                }
                or (action is not None and action.status == "blocked")
            )
            activity: list[datetime | None] = [recommendation.updated_at]
            if action is not None:
                activity.extend([action.updated_at, action_activity.get(action.id)])
            if case is not None:
                activity.extend([case.updated_at, case_activity.get(case.id)])
            if measurement is not None:
                activity.extend([measurement.submitted_at, measurement.created_at])
            if verification is not None:
                activity.append(verification.reviewed_at)
            if latest_ledger is not None:
                activity.append(latest_ledger.posted_at)
            result.append(
                RecoveryPortfolioItem(
                    finding_id=finding.id,
                    finding_title=finding.title,
                    finding_summary=finding.summary,
                    finding_status=finding.status,
                    finding_domain=finding.domain,
                    recommendation_id=recommendation.id,
                    approval_id=approval.id if approval else None,
                    approval_decision=approval.decision if approval else None,
                    action_id=action.id if action else None,
                    action_status=action.status if action else None,
                    assigned_user_id=action.assigned_user_id if action else None,
                    assigned_role=action.assigned_role if action else None,
                    due_at=action.due_at if action else None,
                    action_created_at=action.created_at if action else None,
                    action_completed_at=action.completed_at if action else None,
                    recovery_case_id=case.id if case else None,
                    recovery_case_status=case.status if case else None,
                    recovery_execution_id=execution.id if execution else None,
                    recovery_execution_status=execution.status if execution else None,
                    execution_started_at=execution.started_at if execution else None,
                    execution_completed_at=execution.completed_at if execution else None,
                    outcome_id=outcome.id if outcome else None,
                    outcome_type=outcome.outcome_type if outcome else None,
                    measurement_id=measurement.id if measurement else None,
                    measurement_status=measurement.status if measurement else None,
                    measurement_submitted_at=measurement.submitted_at if measurement else None,
                    verification_id=verification.id if verification else None,
                    verification_decision=verification.decision if verification else None,
                    verification_reviewer_user_id=(
                        verification.reviewer_user_id if verification else None
                    ),
                    verification_rationale=verification.rationale if verification else None,
                    verification_reviewed_at=verification.reviewed_at if verification else None,
                    ledger_entry_id=latest_ledger.id if latest_ledger else None,
                    ledger_posted_at=latest_ledger.posted_at if latest_ledger else None,
                    currency_code=(
                        case.currency_code if case else action.currency_code if action else None
                    ),
                    expected_value=(
                        case.expected_value
                        if case
                        else action.expected_avoided_cost
                        if action
                        else None
                    ),
                    realized_value=measurement.realized_value if measurement else None,
                    verified_value=verified_value,
                    stage=stage,
                    overdue=overdue,
                    attention_required=attention,
                    last_activity_at=max(_utc(item) for item in activity if item is not None),
                )
            )
        return result

    @staticmethod
    def _latest_by(rows: Iterable[T], key: Callable[[T], UUID]) -> dict[UUID, T]:
        result: dict[UUID, T] = {}
        for item in rows:
            result.setdefault(key(item), item)
        return result

    @staticmethod
    def _stage(
        recommendation: DecisionRecommendation,
        approval: DecisionApproval | None,
        action: OperationalAction | None,
        execution: RecoveryExecution | None,
        outcome: ActionOutcome | None,
        measurement: RecoveryValueMeasurement | None,
        verification: RecoveryFinanceVerification | None,
        ledger: list[VerifiedValueLedgerEntry],
    ) -> str:
        if ledger:
            return "verified"
        if verification is not None and verification.decision in VERIFICATION_ATTENTION_STATUSES:
            return "verification_attention"
        if measurement is not None and measurement.status == "submitted":
            return "verification_pending"
        if measurement is not None:
            return "measured"
        if outcome is not None:
            return "outcome_recorded"
        if execution is not None and execution.status == "in_progress":
            return "execution_active"
        if execution is not None:
            return "recovery_execution"
        if action is not None and action.status in ACTIVE_ACTION_STATUSES:
            return "action_active"
        if action is not None:
            return "action_created"
        if approval is not None and approval.decision == "approve":
            return "approved_no_action"
        return "recommendation_review"

    def _summary(
        self, db: Session, organization_id: UUID, now: datetime
    ) -> RecoveryPortfolioSummary:
        finding_count = int(
            db.scalar(
                select(func.count(func.distinct(DecisionScenarioInput.source_id)))
                .select_from(DecisionScenarioInput)
                .join(
                    DecisionExecution,
                    DecisionExecution.scenario_id == DecisionScenarioInput.scenario_id,
                )
                .join(
                    DecisionSolution,
                    DecisionSolution.execution_id == DecisionExecution.id,
                )
                .join(
                    DecisionRecommendation,
                    DecisionRecommendation.solution_id == DecisionSolution.id,
                )
                .where(
                    DecisionScenarioInput.organization_id == organization_id,
                    DecisionExecution.organization_id == organization_id,
                    DecisionSolution.organization_id == organization_id,
                    DecisionRecommendation.organization_id == organization_id,
                    DecisionScenarioInput.input_kind == "finding",
                )
            )
            or 0
        )
        active = int(
            db.scalar(
                select(func.count())
                .select_from(OperationalAction)
                .join(
                    DecisionRecommendation,
                    DecisionRecommendation.converted_action_id == OperationalAction.id,
                )
                .where(
                    OperationalAction.organization_id == organization_id,
                    OperationalAction.status.in_(ACTIVE_ACTION_STATUSES),
                )
            )
            or 0
        )
        overdue = int(
            db.scalar(
                select(func.count())
                .select_from(OperationalAction)
                .join(
                    DecisionRecommendation,
                    DecisionRecommendation.converted_action_id == OperationalAction.id,
                )
                .where(
                    OperationalAction.organization_id == organization_id,
                    OperationalAction.due_at < now,
                    OperationalAction.status.not_in(TERMINAL_ACTION_STATUSES),
                )
            )
            or 0
        )
        awaiting = int(
            db.scalar(
                select(func.count())
                .select_from(RecoveryValueMeasurement)
                .join(
                    RecoveryExecution, RecoveryExecution.id == RecoveryValueMeasurement.execution_id
                )
                .join(
                    DecisionRecommendation,
                    DecisionRecommendation.converted_action_id == RecoveryExecution.action_id,
                )
                .where(
                    RecoveryValueMeasurement.organization_id == organization_id,
                    RecoveryValueMeasurement.status == "submitted",
                )
            )
            or 0
        )
        attention = int(
            db.scalar(
                select(func.count())
                .select_from(RecoveryFinanceVerification)
                .join(
                    RecoveryValueMeasurement,
                    RecoveryValueMeasurement.id == RecoveryFinanceVerification.measurement_id,
                )
                .join(
                    RecoveryExecution, RecoveryExecution.id == RecoveryValueMeasurement.execution_id
                )
                .join(
                    DecisionRecommendation,
                    DecisionRecommendation.converted_action_id == RecoveryExecution.action_id,
                )
                .where(
                    RecoveryFinanceVerification.organization_id == organization_id,
                    RecoveryFinanceVerification.decision.in_(VERIFICATION_ATTENTION_STATUSES),
                )
            )
            or 0
        )
        values: dict[str, dict[str, Decimal]] = defaultdict(
            lambda: {"expected": Decimal("0"), "realized": Decimal("0"), "verified": Decimal("0")}
        )
        for currency_code, amount in db.execute(
            select(RecoveryCase.currency_code, func.sum(RecoveryCase.expected_value))
            .where(
                RecoveryCase.organization_id == organization_id,
                exists(
                    select(RecoveryExecution.id)
                    .join(
                        DecisionRecommendation,
                        DecisionRecommendation.converted_action_id == RecoveryExecution.action_id,
                    )
                    .where(RecoveryExecution.recovery_case_id == RecoveryCase.id)
                ),
            )
            .group_by(RecoveryCase.currency_code)
        ):
            values[currency_code]["expected"] += amount or Decimal("0")
        for currency_code, amount in db.execute(
            select(
                OperationalAction.currency_code, func.sum(OperationalAction.expected_avoided_cost)
            )
            .join(
                DecisionRecommendation,
                DecisionRecommendation.converted_action_id == OperationalAction.id,
            )
            .where(
                OperationalAction.organization_id == organization_id,
                OperationalAction.currency_code.is_not(None),
                ~exists(
                    select(RecoveryExecution.id).where(
                        RecoveryExecution.action_id == OperationalAction.id
                    )
                ),
            )
            .group_by(OperationalAction.currency_code)
        ):
            values[currency_code]["expected"] += amount or Decimal("0")
        for currency_code, amount in db.execute(
            select(
                RecoveryValueMeasurement.currency_code,
                func.sum(RecoveryValueMeasurement.realized_value),
            )
            .join(RecoveryExecution, RecoveryExecution.id == RecoveryValueMeasurement.execution_id)
            .join(
                DecisionRecommendation,
                DecisionRecommendation.converted_action_id == RecoveryExecution.action_id,
            )
            .where(RecoveryValueMeasurement.organization_id == organization_id)
            .group_by(RecoveryValueMeasurement.currency_code)
        ):
            values[currency_code]["realized"] += amount or Decimal("0")
        for currency_code, amount in db.execute(
            select(
                VerifiedValueLedgerEntry.currency_code, func.sum(VerifiedValueLedgerEntry.amount)
            )
            .where(
                VerifiedValueLedgerEntry.organization_id == organization_id,
                exists(
                    select(RecoveryExecution.id)
                    .join(
                        DecisionRecommendation,
                        DecisionRecommendation.converted_action_id == RecoveryExecution.action_id,
                    )
                    .where(
                        RecoveryExecution.recovery_case_id
                        == VerifiedValueLedgerEntry.recovery_case_id
                    )
                ),
            )
            .group_by(VerifiedValueLedgerEntry.currency_code)
        ):
            values[currency_code]["verified"] += amount or Decimal("0")
        return RecoveryPortfolioSummary(
            finding_count=finding_count,
            active_recovery_count=active,
            overdue_count=overdue,
            awaiting_verification_count=awaiting,
            disputed_or_rejected_verification_count=attention,
            value_by_currency=[
                PortfolioCurrencyValue(
                    currency_code=currency_code,
                    expected_value=amounts["expected"],
                    realized_value=amounts["realized"],
                    verified_value=amounts["verified"],
                )
                for currency_code, amounts in sorted(values.items())
            ],
        )

    def _pipeline(self, db: Session, organization_id: UUID) -> RecoveryPortfolioPipeline:
        recommendations = int(
            db.scalar(
                select(func.count())
                .select_from(DecisionRecommendation)
                .where(
                    DecisionRecommendation.organization_id == organization_id,
                    DecisionRecommendation.lifecycle_status == "approved",
                    DecisionRecommendation.converted_action_id.is_(None),
                    exists(
                        select(DecisionScenarioInput.id)
                        .join(
                            DecisionExecution,
                            DecisionExecution.scenario_id == DecisionScenarioInput.scenario_id,
                        )
                        .join(
                            DecisionSolution,
                            DecisionSolution.execution_id == DecisionExecution.id,
                        )
                        .where(
                            DecisionSolution.id == DecisionRecommendation.solution_id,
                            DecisionScenarioInput.organization_id == organization_id,
                            DecisionExecution.organization_id == organization_id,
                            DecisionSolution.organization_id == organization_id,
                            DecisionScenarioInput.input_kind == "finding",
                        )
                    ),
                )
            )
            or 0
        )
        action_active = int(
            db.scalar(
                select(func.count())
                .select_from(OperationalAction)
                .where(
                    OperationalAction.organization_id == organization_id,
                    OperationalAction.status.in_(ACTIVE_ACTION_STATUSES),
                    exists(
                        select(DecisionRecommendation.id).where(
                            DecisionRecommendation.organization_id == organization_id,
                            DecisionRecommendation.converted_action_id == OperationalAction.id,
                        )
                    ),
                )
            )
            or 0
        )
        execution_active = int(
            db.scalar(
                select(func.count())
                .select_from(RecoveryExecution)
                .where(
                    RecoveryExecution.organization_id == organization_id,
                    RecoveryExecution.status == "in_progress",
                    exists(
                        select(DecisionRecommendation.id).where(
                            DecisionRecommendation.organization_id == organization_id,
                            DecisionRecommendation.converted_action_id
                            == RecoveryExecution.action_id,
                        )
                    ),
                )
            )
            or 0
        )
        outcomes = int(
            db.scalar(
                select(func.count())
                .select_from(ActionOutcome)
                .where(
                    ActionOutcome.organization_id == organization_id,
                    exists(
                        select(DecisionRecommendation.id).where(
                            DecisionRecommendation.organization_id == organization_id,
                            DecisionRecommendation.converted_action_id == ActionOutcome.action_id,
                        )
                    ),
                )
            )
            or 0
        )
        measurement_pending = int(
            db.scalar(
                select(func.count())
                .select_from(RecoveryValueMeasurement)
                .join(
                    RecoveryExecution,
                    RecoveryExecution.id == RecoveryValueMeasurement.execution_id,
                )
                .join(
                    DecisionRecommendation,
                    DecisionRecommendation.converted_action_id == RecoveryExecution.action_id,
                )
                .where(
                    RecoveryValueMeasurement.organization_id == organization_id,
                    RecoveryExecution.organization_id == organization_id,
                    DecisionRecommendation.organization_id == organization_id,
                    RecoveryValueMeasurement.status.in_({"draft", "measured"}),
                )
            )
            or 0
        )
        verification_pending = int(
            db.scalar(
                select(func.count())
                .select_from(RecoveryValueMeasurement)
                .join(
                    RecoveryExecution,
                    RecoveryExecution.id == RecoveryValueMeasurement.execution_id,
                )
                .join(
                    DecisionRecommendation,
                    DecisionRecommendation.converted_action_id == RecoveryExecution.action_id,
                )
                .where(
                    RecoveryValueMeasurement.organization_id == organization_id,
                    RecoveryExecution.organization_id == organization_id,
                    DecisionRecommendation.organization_id == organization_id,
                    RecoveryValueMeasurement.status == "submitted",
                )
            )
            or 0
        )
        verification_attention = int(
            db.scalar(
                select(func.count())
                .select_from(RecoveryValueMeasurement)
                .join(
                    RecoveryExecution,
                    RecoveryExecution.id == RecoveryValueMeasurement.execution_id,
                )
                .join(
                    DecisionRecommendation,
                    DecisionRecommendation.converted_action_id == RecoveryExecution.action_id,
                )
                .where(
                    RecoveryValueMeasurement.organization_id == organization_id,
                    RecoveryExecution.organization_id == organization_id,
                    DecisionRecommendation.organization_id == organization_id,
                    RecoveryValueMeasurement.status.in_(VERIFICATION_ATTENTION_STATUSES),
                )
            )
            or 0
        )
        verified = int(
            db.scalar(
                select(func.count(func.distinct(VerifiedValueLedgerEntry.recovery_case_id))).where(
                    VerifiedValueLedgerEntry.organization_id == organization_id,
                    exists(
                        select(RecoveryExecution.id)
                        .join(
                            DecisionRecommendation,
                            DecisionRecommendation.converted_action_id
                            == RecoveryExecution.action_id,
                        )
                        .where(
                            RecoveryExecution.recovery_case_id
                            == VerifiedValueLedgerEntry.recovery_case_id,
                            RecoveryExecution.organization_id == organization_id,
                            DecisionRecommendation.organization_id == organization_id,
                        )
                    ),
                )
            )
            or 0
        )
        closed = int(
            db.scalar(
                select(func.count())
                .select_from(RecoveryCase)
                .where(
                    RecoveryCase.organization_id == organization_id,
                    RecoveryCase.status == "closed",
                    exists(
                        select(RecoveryExecution.id)
                        .join(
                            DecisionRecommendation,
                            DecisionRecommendation.converted_action_id
                            == RecoveryExecution.action_id,
                        )
                        .where(
                            RecoveryExecution.recovery_case_id == RecoveryCase.id,
                            RecoveryExecution.organization_id == organization_id,
                            DecisionRecommendation.organization_id == organization_id,
                        )
                    ),
                )
            )
            or 0
        )
        return RecoveryPortfolioPipeline(
            approved_no_action=recommendations,
            action_active=action_active,
            execution_active=execution_active,
            outcome_recorded=outcomes,
            measurement_pending=measurement_pending,
            verification_pending=verification_pending,
            verification_attention=verification_attention,
            verified=verified,
            closed=closed,
        )


recovery_portfolio_service = RecoveryPortfolioService()
