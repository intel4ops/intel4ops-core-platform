from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.engines.economics_engine import (
    WEIGHTING_PROFILES,
    EconomicInput,
    OpportunityStatus,
    PriorityInput,
    calculate_economics,
    calculate_priority,
    portfolio_included_value,
    require_transition,
)
from app.models.actions import OperationalAction
from app.models.economics import (
    EconomicAssumption,
    EconomicAuditEvent,
    EconomicBaselineVersion,
    EconomicCalculation,
    EconomicScenario,
    OpportunityAction,
    OpportunityDecision,
    OpportunityFinding,
    OpportunityOverlapGroup,
    OpportunityOverlapMember,
    PrioritizationAssessment,
    RecoveryOpportunity,
)
from app.models.entities import Finding
from app.schemas.economics import (
    ActionLinkCreate,
    AssumptionCreate,
    CalculateCreate,
    DecisionCreate,
    FindingLinkCreate,
    OpportunityCreate,
    OpportunityUpdate,
    OverlapGroupCreate,
    OverlapMemberCreate,
    PortfolioCurrencySummary,
    PortfolioSummary,
    PrioritizeCreate,
    RankingItem,
    ScenarioCreate,
)


class EconomicsServiceError(ValueError):
    def __init__(self, code: str, message: str, status: int = 422) -> None:
        self.code = code
        self.status = status
        super().__init__(message)


class EconomicsService:
    def create(
        self, db: Session, organization_id: UUID, payload: OpportunityCreate, actor: UUID
    ) -> RecoveryOpportunity:
        existing = db.scalar(
            select(RecoveryOpportunity).where(
                RecoveryOpportunity.organization_id == organization_id,
                (
                    (RecoveryOpportunity.idempotency_key == payload.idempotency_key)
                    | (RecoveryOpportunity.economic_source_key == payload.economic_source_key)
                ),
            )
        )
        if existing is not None:
            return existing
        opportunity = RecoveryOpportunity(
            organization_id=organization_id,
            opportunity_code=f"ROP-{uuid4().hex[:12].upper()}",
            created_by_user_id=actor,
            status=OpportunityStatus.DRAFT.value,
            **payload.model_dump(),
        )
        db.add(opportunity)
        db.flush()
        self._event(
            db,
            opportunity,
            OpportunityStatus.DRAFT,
            "Opportunity created",
            actor,
            "system",
            f"created:{payload.idempotency_key}",
            prior=None,
        )
        self._audit(
            db,
            opportunity,
            "opportunity_created",
            actor,
            f"audit:created:{payload.idempotency_key}",
            "Recovery opportunity created",
            {"economic_source_key": payload.economic_source_key},
        )
        db.commit()
        db.refresh(opportunity)
        return opportunity

    def get(self, db: Session, organization_id: UUID, opportunity_id: UUID) -> RecoveryOpportunity:
        row = db.scalar(
            select(RecoveryOpportunity).where(
                RecoveryOpportunity.id == opportunity_id,
                RecoveryOpportunity.organization_id == organization_id,
            )
        )
        if row is None:
            raise EconomicsServiceError("NOT_FOUND", "Recovery opportunity not found", 404)
        return row

    def list_opportunities(
        self,
        db: Session,
        organization_id: UUID,
        page: int,
        page_size: int,
        *,
        status: str | None = None,
        priority: str | None = None,
        currency: str | None = None,
        minimum_net_benefit: Decimal | None = None,
    ) -> tuple[list[RecoveryOpportunity], int]:
        filters = [RecoveryOpportunity.organization_id == organization_id]
        if status:
            filters.append(RecoveryOpportunity.status == status)
        if priority:
            filters.append(RecoveryOpportunity.priority_category == priority)
        if currency:
            filters.append(RecoveryOpportunity.currency_code == currency)
        if minimum_net_benefit is not None:
            latest = (
                select(
                    EconomicCalculation.opportunity_id,
                    func.max(EconomicCalculation.calculated_at).label("calculated_at"),
                )
                .where(EconomicCalculation.organization_id == organization_id)
                .group_by(EconomicCalculation.opportunity_id)
                .subquery()
            )
            filters.append(
                RecoveryOpportunity.id.in_(
                    select(EconomicCalculation.opportunity_id)
                    .join(
                        latest,
                        (latest.c.opportunity_id == EconomicCalculation.opportunity_id)
                        & (latest.c.calculated_at == EconomicCalculation.calculated_at),
                    )
                    .where(EconomicCalculation.expected_net_benefit >= minimum_net_benefit)
                )
            )
        total = (
            db.scalar(select(func.count()).select_from(RecoveryOpportunity).where(*filters)) or 0
        )
        rows = list(
            db.scalars(
                select(RecoveryOpportunity)
                .where(*filters)
                .order_by(RecoveryOpportunity.created_at.desc(), RecoveryOpportunity.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return rows, total

    def update(
        self,
        db: Session,
        organization_id: UUID,
        opportunity_id: UUID,
        payload: OpportunityUpdate,
        actor: UUID,
    ) -> RecoveryOpportunity:
        row = self.get(db, organization_id, opportunity_id)
        if row.status == OpportunityStatus.APPROVED_FOR_ACTION.value:
            raise EconomicsServiceError(
                "APPROVED_OPPORTUNITY_IMMUTABLE",
                "Approved opportunity economics require controlled recalculation",
            )
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(row, field, value)
        self._audit(
            db,
            row,
            "opportunity_updated",
            actor,
            f"audit:update:{uuid4()}",
            "Recovery opportunity metadata updated",
            {"fields": sorted(payload.model_dump(exclude_unset=True))},
        )
        db.commit()
        db.refresh(row)
        return row

    def add_finding(
        self,
        db: Session,
        organization_id: UUID,
        opportunity_id: UUID,
        payload: FindingLinkCreate,
        actor: UUID,
    ) -> OpportunityFinding:
        self.get(db, organization_id, opportunity_id)
        if (
            db.scalar(
                select(Finding.id).where(
                    Finding.id == payload.finding_id,
                    Finding.organization_id == organization_id,
                )
            )
            is None
        ):
            raise EconomicsServiceError("FINDING_NOT_FOUND", "Tenant finding not found", 404)
        existing = db.scalar(
            select(OpportunityFinding).where(
                OpportunityFinding.opportunity_id == opportunity_id,
                OpportunityFinding.finding_id == payload.finding_id,
            )
        )
        if existing:
            return existing
        row = OpportunityFinding(
            organization_id=organization_id,
            opportunity_id=opportunity_id,
            created_by_user_id=actor,
            **payload.model_dump(),
        )
        db.add(row)
        self._audit(
            db,
            self.get(db, organization_id, opportunity_id),
            "finding_linked",
            actor,
            f"audit:finding:{opportunity_id}:{payload.finding_id}",
            "Finding linked to recovery opportunity",
            {"finding_id": str(payload.finding_id)},
        )
        db.commit()
        db.refresh(row)
        return row

    def add_action(
        self,
        db: Session,
        organization_id: UUID,
        opportunity_id: UUID,
        payload: ActionLinkCreate,
        actor: UUID,
    ) -> OpportunityAction:
        self.get(db, organization_id, opportunity_id)
        if (
            db.scalar(
                select(OperationalAction.id).where(
                    OperationalAction.id == payload.action_id,
                    OperationalAction.organization_id == organization_id,
                )
            )
            is None
        ):
            raise EconomicsServiceError("ACTION_NOT_FOUND", "Tenant action not found", 404)
        existing = db.scalar(
            select(OpportunityAction).where(
                OpportunityAction.opportunity_id == opportunity_id,
                OpportunityAction.action_id == payload.action_id,
            )
        )
        if existing:
            return existing
        row = OpportunityAction(
            organization_id=organization_id,
            opportunity_id=opportunity_id,
            created_by_user_id=actor,
            **payload.model_dump(),
        )
        db.add(row)
        self._audit(
            db,
            self.get(db, organization_id, opportunity_id),
            "action_linked",
            actor,
            f"audit:action:{opportunity_id}:{payload.action_id}",
            "Operational action linked to recovery opportunity",
            {"action_id": str(payload.action_id)},
        )
        db.commit()
        db.refresh(row)
        return row

    def create_scenario(
        self,
        db: Session,
        organization_id: UUID,
        opportunity_id: UUID,
        payload: ScenarioCreate,
        actor: UUID,
    ) -> EconomicScenario:
        opportunity = self.get(db, organization_id, opportunity_id)
        self._require_mutable(opportunity)
        if payload.currency_code != opportunity.currency_code:
            raise EconomicsServiceError(
                "CURRENCY_MISMATCH", "Scenario currency must match opportunity currency"
            )
        version = (
            db.scalar(
                select(func.max(EconomicScenario.version)).where(
                    EconomicScenario.opportunity_id == opportunity_id,
                    EconomicScenario.scenario_code == payload.scenario_code,
                )
            )
            or 0
        ) + 1
        row = EconomicScenario(
            organization_id=organization_id,
            opportunity_id=opportunity_id,
            version=version,
            created_by_user_id=actor,
            **payload.model_dump(),
        )
        db.add(row)
        self._audit(
            db,
            opportunity,
            "scenario_created",
            actor,
            f"audit:scenario:{payload.scenario_code}:{version}",
            "Economic scenario version created",
            {"scenario_id": str(row.id), "scenario_code": row.scenario_code, "version": version},
        )
        db.commit()
        db.refresh(row)
        return row

    def scenarios(
        self, db: Session, organization_id: UUID, opportunity_id: UUID
    ) -> list[EconomicScenario]:
        self.get(db, organization_id, opportunity_id)
        return list(
            db.scalars(
                select(EconomicScenario)
                .where(
                    EconomicScenario.organization_id == organization_id,
                    EconomicScenario.opportunity_id == opportunity_id,
                )
                .order_by(EconomicScenario.scenario_code, EconomicScenario.version)
            )
        )

    def get_scenario(
        self, db: Session, organization_id: UUID, opportunity_id: UUID, scenario_id: UUID
    ) -> EconomicScenario:
        self.get(db, organization_id, opportunity_id)
        row = db.scalar(
            select(EconomicScenario).where(
                EconomicScenario.id == scenario_id,
                EconomicScenario.opportunity_id == opportunity_id,
                EconomicScenario.organization_id == organization_id,
            )
        )
        if row is None:
            raise EconomicsServiceError("SCENARIO_NOT_FOUND", "Economic scenario not found", 404)
        return row

    def add_assumption(
        self,
        db: Session,
        organization_id: UUID,
        opportunity_id: UUID,
        payload: AssumptionCreate,
        actor: UUID,
    ) -> EconomicAssumption:
        opportunity = self.get(db, organization_id, opportunity_id)
        self._require_mutable(opportunity)
        if payload.scenario_id is not None:
            self.get_scenario(db, organization_id, opportunity_id, payload.scenario_id)
        if payload.currency_code is not None and payload.currency_code != opportunity.currency_code:
            raise EconomicsServiceError(
                "CURRENCY_MISMATCH", "Assumption currency must match opportunity currency"
            )
        previous = db.scalar(
            select(EconomicAssumption)
            .where(
                EconomicAssumption.opportunity_id == opportunity_id,
                EconomicAssumption.assumption_code == payload.assumption_code,
                EconomicAssumption.superseded.is_(False),
            )
            .order_by(EconomicAssumption.version.desc())
        )
        version = 1 if previous is None else previous.version + 1
        if previous is not None:
            previous.superseded = True
        row = EconomicAssumption(
            organization_id=organization_id,
            opportunity_id=opportunity_id,
            version=version,
            entered_by_user_id=actor,
            **payload.model_dump(),
        )
        db.add(row)
        self._audit(
            db,
            opportunity,
            "assumption_version_created",
            actor,
            f"audit:assumption:{payload.assumption_code}:{version}",
            "Economic assumption version created",
            {
                "assumption_id": str(row.id),
                "assumption_code": row.assumption_code,
                "version": version,
            },
        )
        db.commit()
        db.refresh(row)
        return row

    def calculate(
        self,
        db: Session,
        organization_id: UUID,
        opportunity_id: UUID,
        payload: CalculateCreate,
        actor: UUID,
    ) -> EconomicCalculation:
        opportunity = self.get(db, organization_id, opportunity_id)
        scenario = self.get_scenario(db, organization_id, opportunity_id, payload.scenario_id)
        existing = db.scalar(
            select(EconomicCalculation).where(
                EconomicCalculation.opportunity_id == opportunity_id,
                EconomicCalculation.idempotency_key == payload.idempotency_key,
            )
        )
        if existing:
            return existing
        result = calculate_economics(
            EconomicInput(
                gross_exposure=scenario.gross_exposure,
                addressability_rate=scenario.addressability_rate,
                recoverability_rate=scenario.recoverability_rate,
                success_probability=scenario.success_probability,
                recovery_cost=scenario.recovery_cost,
                benefit_period_days=scenario.benefit_period_days,
            )
        )
        row = EconomicCalculation(
            organization_id=organization_id,
            opportunity_id=opportunity_id,
            scenario_id=scenario.id,
            idempotency_key=payload.idempotency_key,
            calculated_by_user_id=actor,
            currency_code=scenario.currency_code,
            input_snapshot={
                "scenario_id": str(scenario.id),
                "scenario_version": scenario.version,
                "reason": payload.reason,
            },
            limitations=list(opportunity.limitations),
            **result.__dict__,
        )
        db.add(row)
        opportunity.selected_scenario_id = scenario.id
        self._audit(
            db,
            opportunity,
            "calculation_run",
            actor,
            f"audit:calculation:{payload.idempotency_key}",
            payload.reason,
            {"calculation_id": str(row.id), "scenario_id": str(scenario.id)},
        )
        db.commit()
        db.refresh(row)
        return row

    def prioritize(
        self,
        db: Session,
        organization_id: UUID,
        opportunity_id: UUID,
        payload: PrioritizeCreate,
        actor: UUID,
    ) -> PrioritizationAssessment:
        opportunity = self.get(db, organization_id, opportunity_id)
        calculation = db.scalar(
            select(EconomicCalculation).where(
                EconomicCalculation.id == payload.calculation_id,
                EconomicCalculation.opportunity_id == opportunity_id,
                EconomicCalculation.organization_id == organization_id,
            )
        )
        if calculation is None:
            raise EconomicsServiceError(
                "CALCULATION_NOT_FOUND", "Tenant economic calculation not found", 404
            )
        existing = db.scalar(
            select(PrioritizationAssessment).where(
                PrioritizationAssessment.opportunity_id == opportunity_id,
                PrioritizationAssessment.idempotency_key == payload.idempotency_key,
            )
        )
        if existing:
            return existing
        weights = WEIGHTING_PROFILES.get(payload.profile_code)
        if weights is None:
            raise EconomicsServiceError(
                "PROFILE_NOT_FOUND", "Unsupported prioritization profile", 404
            )
        result = calculate_priority(
            PriorityInput(
                probability_adjusted_value=calculation.probability_adjusted_value,
                expected_net_benefit=calculation.expected_net_benefit,
                expected_roi=calculation.expected_roi,
                payback_period_days=calculation.payback_period_days,
                urgency_score=payload.urgency_score,
                confidence_score=payload.confidence_score,
                feasibility_score=payload.feasibility_score,
                strategic_alignment_score=payload.strategic_alignment_score,
                risk_score=payload.risk_score,
                dependency_ready=payload.dependency_ready,
                resource_ready=payload.resource_ready,
            ),
            weights,
        )
        row = PrioritizationAssessment(
            organization_id=organization_id,
            opportunity_id=opportunity_id,
            calculation_id=calculation.id,
            idempotency_key=payload.idempotency_key,
            profile_code=payload.profile_code,
            calculation_reason=payload.calculation_reason,
            source_references=payload.source_references,
            calculated_by_user_id=actor,
            model_name=result.model_name,
            model_version=result.model_version,
            factor_weights=result.weights,
            normalized_factors=result.normalized_factors,
            factor_contributions=result.contributions,
            priority_score=result.score,
            priority_category=result.category.value,
            limitations=list(result.limitations),
        )
        db.add(row)
        opportunity.priority_category = result.category.value
        self._audit(
            db,
            opportunity,
            "prioritization_run",
            actor,
            f"audit:priority:{payload.idempotency_key}",
            payload.calculation_reason,
            {"prioritization_id": str(row.id), "profile_code": payload.profile_code},
        )
        db.commit()
        db.refresh(row)
        return row

    def create_overlap_group(
        self,
        db: Session,
        organization_id: UUID,
        payload: OverlapGroupCreate,
        actor: UUID,
    ) -> OpportunityOverlapGroup:
        existing = db.scalar(
            select(OpportunityOverlapGroup).where(
                OpportunityOverlapGroup.organization_id == organization_id,
                OpportunityOverlapGroup.overlap_key == payload.overlap_key,
            )
        )
        if existing:
            return existing
        row = OpportunityOverlapGroup(
            organization_id=organization_id,
            created_by_user_id=actor,
            **payload.model_dump(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def add_overlap_member(
        self,
        db: Session,
        organization_id: UUID,
        group_id: UUID,
        payload: OverlapMemberCreate,
        actor: UUID,
    ) -> OpportunityOverlapMember:
        group = db.scalar(
            select(OpportunityOverlapGroup).where(
                OpportunityOverlapGroup.id == group_id,
                OpportunityOverlapGroup.organization_id == organization_id,
            )
        )
        if group is None:
            raise EconomicsServiceError("OVERLAP_NOT_FOUND", "Overlap group not found", 404)
        self.get(db, organization_id, payload.opportunity_id)
        if payload.parent_opportunity_id is not None:
            self.get(db, organization_id, payload.parent_opportunity_id)
        existing = db.scalar(
            select(OpportunityOverlapMember).where(
                OpportunityOverlapMember.overlap_group_id == group_id,
                OpportunityOverlapMember.opportunity_id == payload.opportunity_id,
            )
        )
        if existing:
            return existing
        row = OpportunityOverlapMember(
            organization_id=organization_id,
            overlap_group_id=group_id,
            **payload.model_dump(),
        )
        db.add(row)
        self._audit(
            db,
            self.get(db, organization_id, payload.opportunity_id),
            "overlap_registered",
            actor,
            f"audit:overlap:{group_id}:{payload.opportunity_id}",
            "Opportunity overlap allocation registered",
            {
                "overlap_group_id": str(group_id),
                "allocation_percentage": str(payload.allocation_percentage),
                "inclusion_status": payload.inclusion_status,
            },
        )
        db.commit()
        db.refresh(row)
        return row

    def decide(
        self,
        db: Session,
        organization_id: UUID,
        opportunity_id: UUID,
        payload: DecisionCreate,
        actor: UUID,
        actor_role: str,
    ) -> tuple[RecoveryOpportunity, OpportunityDecision, EconomicBaselineVersion | None]:
        opportunity = self.get(db, organization_id, opportunity_id)
        existing = db.scalar(
            select(OpportunityDecision).where(
                OpportunityDecision.opportunity_id == opportunity_id,
                OpportunityDecision.idempotency_key == payload.idempotency_key,
            )
        )
        if existing:
            return opportunity, existing, None
        requested = payload.decision
        try:
            require_transition(OpportunityStatus(opportunity.status), requested)
        except ValueError as exc:
            raise EconomicsServiceError("INVALID_TRANSITION", str(exc), 409) from exc
        baseline = None
        prioritization = None
        calculation = None
        scenario = None
        if requested in {
            OpportunityStatus.ECONOMICALLY_QUALIFIED,
            OpportunityStatus.APPROVED_FOR_ACTION,
        }:
            scenario, calculation, prioritization = self._required_economics(
                db, organization_id, opportunity, payload
            )
        if requested == OpportunityStatus.APPROVED_FOR_ACTION:
            if actor_role not in {"organization_admin", "platform_admin"}:
                raise EconomicsServiceError(
                    "APPROVAL_FORBIDDEN", "Organization administrator approval required", 403
                )
            assert scenario is not None and calculation is not None and prioritization is not None
            baseline = self._freeze_baseline(
                db,
                opportunity,
                scenario,
                calculation,
                prioritization,
                actor,
                payload.idempotency_key,
            )
        prior = opportunity.status
        opportunity.status = requested.value
        decision = self._event(
            db,
            opportunity,
            requested,
            payload.decision_reason,
            actor,
            actor_role,
            payload.idempotency_key,
            prior=prior,
            scenario_id=payload.scenario_id,
            baseline_version=baseline.version if baseline else None,
            conditions=payload.conditions,
            review_at=payload.review_at,
        )
        self._audit(
            db,
            opportunity,
            "decision_recorded",
            actor,
            f"audit:decision:{payload.idempotency_key}",
            payload.decision_reason,
            {
                "prior_status": prior,
                "decision": requested.value,
                "baseline_version": baseline.version if baseline else None,
            },
        )
        db.commit()
        db.refresh(opportunity)
        db.refresh(decision)
        if baseline:
            db.refresh(baseline)
        return opportunity, decision, baseline

    def audit(
        self, db: Session, organization_id: UUID, opportunity_id: UUID
    ) -> list[EconomicAuditEvent]:
        self.get(db, organization_id, opportunity_id)
        return list(
            db.scalars(
                select(EconomicAuditEvent)
                .where(
                    EconomicAuditEvent.organization_id == organization_id,
                    EconomicAuditEvent.opportunity_id == opportunity_id,
                )
                .order_by(EconomicAuditEvent.occurred_at, EconomicAuditEvent.id)
            )
        )

    def latest_economics(
        self, db: Session, organization_id: UUID, opportunity_id: UUID
    ) -> EconomicCalculation:
        self.get(db, organization_id, opportunity_id)
        row = db.scalar(
            select(EconomicCalculation)
            .where(
                EconomicCalculation.organization_id == organization_id,
                EconomicCalculation.opportunity_id == opportunity_id,
            )
            .order_by(EconomicCalculation.calculated_at.desc(), EconomicCalculation.id.desc())
        )
        if row is None:
            raise EconomicsServiceError(
                "ECONOMICS_NOT_FOUND", "No economic calculation exists", 404
            )
        return row

    def latest_priority(
        self, db: Session, organization_id: UUID, opportunity_id: UUID
    ) -> PrioritizationAssessment:
        self.get(db, organization_id, opportunity_id)
        row = db.scalar(
            select(PrioritizationAssessment)
            .where(
                PrioritizationAssessment.organization_id == organization_id,
                PrioritizationAssessment.opportunity_id == opportunity_id,
            )
            .order_by(
                PrioritizationAssessment.calculated_at.desc(),
                PrioritizationAssessment.id.desc(),
            )
        )
        if row is None:
            raise EconomicsServiceError("PRIORITY_NOT_FOUND", "No prioritization exists", 404)
        return row

    def portfolio(
        self, db: Session, organization_id: UUID
    ) -> tuple[PortfolioSummary, list[RankingItem]]:
        opportunities = list(
            db.scalars(
                select(RecoveryOpportunity).where(
                    RecoveryOpportunity.organization_id == organization_id,
                    RecoveryOpportunity.status.not_in(
                        [
                            OpportunityStatus.REJECTED.value,
                            OpportunityStatus.SUPERSEDED.value,
                            OpportunityStatus.CANCELLED.value,
                        ]
                    ),
                )
            )
        )
        allocation_by_opportunity: dict[UUID, tuple[Decimal, str]] = {}
        for member in db.scalars(
            select(OpportunityOverlapMember).where(
                OpportunityOverlapMember.organization_id == organization_id
            )
        ):
            allocation_by_opportunity[member.opportunity_id] = (
                member.allocation_percentage,
                member.inclusion_status,
            )
        totals: dict[str, dict[str, Decimal | int]] = defaultdict(
            lambda: {
                "gross_exposure": Decimal("0"),
                "addressable_exposure": Decimal("0"),
                "expected_recoverable_value": Decimal("0"),
                "probability_adjusted_value": Decimal("0"),
                "recovery_cost": Decimal("0"),
                "expected_net_benefit": Decimal("0"),
                "opportunity_count": 0,
            }
        )
        ranking: list[RankingItem] = []
        for opportunity in opportunities:
            calculation = db.scalar(
                select(EconomicCalculation)
                .where(EconomicCalculation.opportunity_id == opportunity.id)
                .order_by(EconomicCalculation.calculated_at.desc(), EconomicCalculation.id.desc())
            )
            priority = db.scalar(
                select(PrioritizationAssessment)
                .where(PrioritizationAssessment.opportunity_id == opportunity.id)
                .order_by(
                    PrioritizationAssessment.calculated_at.desc(),
                    PrioritizationAssessment.id.desc(),
                )
            )
            included_value = None
            if calculation:
                allocation, inclusion = allocation_by_opportunity.get(
                    opportunity.id, (Decimal("1"), "included")
                )
                included_value = portfolio_included_value(
                    calculation.probability_adjusted_value, allocation, inclusion
                )
                currency = calculation.currency_code
                bucket = totals[currency]
                bucket["gross_exposure"] = Decimal(str(bucket["gross_exposure"])) + (
                    calculation.gross_exposure * allocation if inclusion == "included" else 0
                )
                bucket["addressable_exposure"] = Decimal(str(bucket["addressable_exposure"])) + (
                    calculation.addressable_exposure * allocation if inclusion == "included" else 0
                )
                bucket["expected_recoverable_value"] = Decimal(
                    str(bucket["expected_recoverable_value"])
                ) + (
                    calculation.expected_recoverable_value * allocation
                    if inclusion == "included"
                    else 0
                )
                bucket["probability_adjusted_value"] = (
                    Decimal(str(bucket["probability_adjusted_value"])) + included_value
                )
                bucket["recovery_cost"] = Decimal(str(bucket["recovery_cost"])) + (
                    calculation.recovery_cost * allocation if inclusion == "included" else 0
                )
                bucket["expected_net_benefit"] = Decimal(str(bucket["expected_net_benefit"])) + (
                    calculation.expected_net_benefit * allocation if inclusion == "included" else 0
                )
                bucket["opportunity_count"] = int(bucket["opportunity_count"]) + 1
            ranking.append(
                RankingItem(
                    opportunity=opportunity,
                    priority_score=priority.priority_score if priority else None,
                    included_probability_adjusted_value=included_value,
                )
            )
        ranking.sort(key=lambda item: item.priority_score or Decimal("-1"), reverse=True)
        currencies = [
            PortfolioCurrencySummary(currency_code=currency, **values)
            for currency, values in sorted(totals.items())
        ]
        return (
            PortfolioSummary(
                currencies=currencies,
                by_priority=dict(
                    Counter(item.priority_category or "unscored" for item in opportunities)
                ),
                by_status=dict(Counter(item.status for item in opportunities)),
            ),
            ranking,
        )

    def _required_economics(
        self,
        db: Session,
        organization_id: UUID,
        opportunity: RecoveryOpportunity,
        payload: DecisionCreate,
    ) -> tuple[EconomicScenario, EconomicCalculation, PrioritizationAssessment]:
        if payload.scenario_id is None or payload.prioritization_id is None:
            raise EconomicsServiceError(
                "ECONOMIC_INPUTS_REQUIRED",
                "Scenario and prioritization are required for economic qualification",
            )
        scenario = self.get_scenario(db, organization_id, opportunity.id, payload.scenario_id)
        prioritization = db.scalar(
            select(PrioritizationAssessment).where(
                PrioritizationAssessment.id == payload.prioritization_id,
                PrioritizationAssessment.opportunity_id == opportunity.id,
                PrioritizationAssessment.organization_id == organization_id,
            )
        )
        if prioritization is None:
            raise EconomicsServiceError(
                "PRIORITY_NOT_FOUND", "Tenant prioritization not found", 404
            )
        calculation = db.scalar(
            select(EconomicCalculation).where(
                EconomicCalculation.id == prioritization.calculation_id,
                EconomicCalculation.scenario_id == scenario.id,
                EconomicCalculation.organization_id == organization_id,
            )
        )
        if calculation is None:
            raise EconomicsServiceError(
                "CALCULATION_NOT_FOUND", "Selected scenario calculation not found", 404
            )
        return scenario, calculation, prioritization

    def _freeze_baseline(
        self,
        db: Session,
        opportunity: RecoveryOpportunity,
        scenario: EconomicScenario,
        calculation: EconomicCalculation,
        prioritization: PrioritizationAssessment,
        actor: UUID,
        idempotency_key: str,
    ) -> EconomicBaselineVersion:
        version = (opportunity.current_baseline_version or 0) + 1
        assumptions = list(
            db.scalars(
                select(EconomicAssumption).where(
                    EconomicAssumption.opportunity_id == opportunity.id,
                    EconomicAssumption.superseded.is_(False),
                )
            )
        )
        baseline = EconomicBaselineVersion(
            organization_id=opportunity.organization_id,
            opportunity_id=opportunity.id,
            scenario_id=scenario.id,
            calculation_id=calculation.id,
            prioritization_id=prioritization.id,
            version=version,
            idempotency_key=idempotency_key,
            currency_code=calculation.currency_code,
            economic_snapshot={
                "gross_exposure": str(calculation.gross_exposure),
                "addressable_exposure": str(calculation.addressable_exposure),
                "expected_recoverable_value": str(calculation.expected_recoverable_value),
                "probability_adjusted_value": str(calculation.probability_adjusted_value),
                "recovery_cost": str(calculation.recovery_cost),
                "expected_net_benefit": str(calculation.expected_net_benefit),
                "expected_roi": (
                    str(calculation.expected_roi) if calculation.expected_roi is not None else None
                ),
                "priority_score": str(prioritization.priority_score),
                "priority_category": prioritization.priority_category,
                "calculation_version": calculation.calculation_version,
                "priority_model_version": prioritization.model_version,
            },
            assumption_versions=[
                {
                    "id": str(item.id),
                    "code": item.assumption_code,
                    "version": item.version,
                    "value": str(item.value),
                    "unit": item.unit,
                }
                for item in assumptions
            ],
            approved_by_user_id=actor,
        )
        db.add(baseline)
        db.flush()
        opportunity.current_baseline_version = version
        opportunity.selected_scenario_id = scenario.id
        return baseline

    @staticmethod
    def _require_mutable(opportunity: RecoveryOpportunity) -> None:
        if opportunity.status == OpportunityStatus.APPROVED_FOR_ACTION.value:
            raise EconomicsServiceError(
                "APPROVED_BASELINE_IMMUTABLE",
                "Approved economics cannot be changed; create a controlled recalculation",
            )

    @staticmethod
    def _event(
        db: Session,
        opportunity: RecoveryOpportunity,
        decision: OpportunityStatus,
        reason: str,
        actor: UUID,
        role: str,
        key: str,
        *,
        prior: str | None,
        scenario_id: UUID | None = None,
        baseline_version: int | None = None,
        conditions: list[str] | None = None,
        review_at: datetime | None = None,
    ) -> OpportunityDecision:
        row = OpportunityDecision(
            organization_id=opportunity.organization_id,
            opportunity_id=opportunity.id,
            idempotency_key=key,
            prior_status=prior,
            decision=decision.value,
            decision_reason=reason,
            actor_user_id=actor,
            actor_role=role,
            scenario_id=scenario_id,
            baseline_version=baseline_version,
            conditions=conditions or [],
            review_at=review_at,
            decided_at=datetime.now(UTC),
        )
        db.add(row)
        return row

    @staticmethod
    def _audit(
        db: Session,
        opportunity: RecoveryOpportunity,
        event_type: str,
        actor: UUID,
        key: str,
        reason: str,
        payload: dict[str, object],
    ) -> EconomicAuditEvent:
        row = EconomicAuditEvent(
            organization_id=opportunity.organization_id,
            opportunity_id=opportunity.id,
            event_type=event_type,
            actor_user_id=actor,
            idempotency_key=key,
            reason=reason,
            event_payload=payload,
        )
        db.add(row)
        return row


economics_service = EconomicsService()
