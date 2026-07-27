from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.actions import OperationalAction
from app.models.economics import EconomicCalculation, RecoveryOpportunity
from app.models.entities import Finding
from app.models.recovery_ledger import (
    RecoveryCase,
    RecoveryValueMeasurement,
    VerifiedValueLedgerEntry,
)
from app.schemas.executive_command import (
    AttentionItem,
    CurrencyExecutiveSummary,
    ExecutiveSummary,
    RecoveryPortfolio,
    TrendPoint,
)


class ExecutiveCommandService:
    def summary(self, db: Session, org: UUID, start: datetime, end: datetime) -> ExecutiveSummary:
        calculation_history = list(
            db.scalars(
                select(EconomicCalculation)
                .where(EconomicCalculation.organization_id == org)
                .order_by(EconomicCalculation.calculated_at)
            )
        )
        latest_by_opportunity = {row.opportunity_id: row for row in calculation_history}
        calculations = list(latest_by_opportunity.values())
        measurements = list(
            db.scalars(
                select(RecoveryValueMeasurement).where(
                    RecoveryValueMeasurement.organization_id == org
                )
            )
        )
        ledger = list(
            db.scalars(
                select(VerifiedValueLedgerEntry).where(
                    VerifiedValueLedgerEntry.organization_id == org
                )
            )
        )
        totals: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
        for row in calculations:
            bucket = totals[row.currency_code]
            bucket["exposure"] += row.gross_exposure
            bucket["addressable"] += row.addressable_exposure
            bucket["expected"] += row.expected_recoverable_value
        for measurement in measurements:
            totals[measurement.currency_code]["realized"] += measurement.realized_value
        for entry in ledger:
            key = (
                "adjustments"
                if entry.entry_type
                in {"adjustment_positive", "adjustment_negative", "reinstatement"}
                else "reversals"
                if entry.entry_type == "reversal"
                else "verified"
            )
            totals[entry.currency_code][key] += entry.amount
        cases = list(db.scalars(select(RecoveryCase).where(RecoveryCase.organization_id == org)))
        actions = list(
            db.scalars(select(OperationalAction).where(OperationalAction.organization_id == org))
        )
        findings = list(db.scalars(select(Finding).where(Finding.organization_id == org)))
        attention = self.attention(db, org, limit=10)
        awaiting: dict[str, Decimal] = defaultdict(Decimal)
        for measurement in measurements:
            if measurement.status in {"submitted", "under_review"}:
                awaiting[measurement.currency_code] += measurement.realized_value
        return ExecutiveSummary(
            period_start=start,
            period_end=end,
            currencies=[
                CurrencyExecutiveSummary(
                    currency_code=currency,
                    exposure=value["exposure"],
                    addressable_exposure=value["addressable"],
                    expected_recoverable_value=value["expected"],
                    realized_value=value["realized"],
                    verified_value=value["verified"],
                    adjustments=value["adjustments"],
                    reversals=value["reversals"],
                )
                for currency, value in sorted(totals.items())
            ],
            active_recovery_cases=sum(row.status in {"approved", "active"} for row in cases),
            overdue_actions=sum(
                bool(
                    row.due_at and row.due_at < end and row.status not in {"completed", "verified"}
                )
                for row in actions
            ),
            unresolved_critical_findings=sum(
                row.severity == "critical" and row.status not in {"resolved", "closed"}
                for row in findings
            ),
            value_awaiting_verification=dict(awaiting),
            data_confidence_status="reduced"
            if any((row.confidence_score or Decimal("1")) < Decimal("0.7") for row in findings)
            else "supported",
            top_attention_items=attention,
        )

    def attention(self, db: Session, org: UUID, limit: int = 50) -> list[AttentionItem]:
        rows = list(
            db.scalars(
                select(RecoveryOpportunity)
                .where(RecoveryOpportunity.organization_id == org)
                .order_by(RecoveryOpportunity.created_at.desc())
                .limit(limit)
            )
        )
        return [
            AttentionItem(
                item_type="recovery_opportunity",
                item_id=row.id,
                reason=row.description,
                priority=row.priority_category or "unranked",
                value=None,
                currency_code=row.currency_code,
                owner_user_id=row.owner_user_id,
                status=row.status,
                next_action="review opportunity",
                evidence_reference=None,
            )
            for row in rows
        ]

    def recovery_portfolio(self, db: Session, org: UUID, at: datetime) -> RecoveryPortfolio:
        cases = list(db.scalars(select(RecoveryCase).where(RecoveryCase.organization_id == org)))
        actions = list(
            db.scalars(select(OperationalAction).where(OperationalAction.organization_id == org))
        )
        measurements = list(
            db.scalars(
                select(RecoveryValueMeasurement).where(
                    RecoveryValueMeasurement.organization_id == org
                )
            )
        )
        stages: dict[str, int] = defaultdict(int)
        owners: dict[str, int] = defaultdict(int)
        for row in cases:
            stages[row.status] += 1
        for action in actions:
            owners[str(action.assigned_user_id or action.assigned_role or "unassigned")] += 1
        return RecoveryPortfolio(
            by_stage=dict(stages),
            by_owner=dict(owners),
            overdue_actions=sum(
                bool(row.due_at and row.due_at < at and row.status not in {"completed", "verified"})
                for row in actions
            ),
            blocked_cases=sum(row.status == "blocked" for row in cases),
            verification_backlog=sum(
                row.status in {"submitted", "under_review"} for row in measurements
            ),
        )

    def trends(self, db: Session, org: UUID, start: datetime, end: datetime) -> list[TrendPoint]:
        totals: dict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
        calculations = db.scalars(
            select(EconomicCalculation).where(
                EconomicCalculation.organization_id == org,
                EconomicCalculation.calculated_at >= start,
                EconomicCalculation.calculated_at < end,
            )
        )
        for row in calculations:
            day = row.calculated_at.date().isoformat()
            totals[(day, row.currency_code, "exposure")] += row.gross_exposure
            totals[(day, row.currency_code, "expected_recoverable_value")] += (
                row.expected_recoverable_value
            )
        entries = db.scalars(
            select(VerifiedValueLedgerEntry).where(
                VerifiedValueLedgerEntry.organization_id == org,
                VerifiedValueLedgerEntry.posted_at >= start,
                VerifiedValueLedgerEntry.posted_at < end,
            )
        )
        for entry in entries:
            totals[(entry.posted_at.date().isoformat(), entry.currency_code, "verified_value")] += (
                entry.amount
            )
        return [
            TrendPoint(period=period, currency_code=currency, measure=measure, value=value)
            for (period, currency, measure), value in sorted(totals.items())
        ]


executive_command_service = ExecutiveCommandService()
