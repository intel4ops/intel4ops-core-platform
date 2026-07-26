from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.engines.action_engine import (
    ActionStatus,
    PriorityInput,
    calculate_approval,
    calculate_priority,
    classify_feedback,
    dependencies_ready,
    idempotency_fingerprint,
    realized_value_eligible,
    require_transition,
    resources_ready,
)
from app.models.actions import (
    ActionDependency,
    ActionEvent,
    ActionEvidence,
    ActionModelFeedback,
    ActionOutcome,
    ActionPlanStep,
    ActionResourceRequirement,
    OperationalAction,
)
from app.models.entities import Finding, OrganizationMembership
from app.models.forecasting import ForecastExecution
from app.models.orchestration import IntelligenceOrchestrationRequest
from app.models.reliability import ReliabilityExecution
from app.schemas.actions import (
    ActionAssignmentCreate,
    ActionCreate,
    ActionDependencyCreate,
    ActionEvidenceCreate,
    ActionFeedbackCreate,
    ActionOutcomeCreate,
    ActionPlanStepCreate,
    ActionResourceCreate,
    ActionTransitionCreate,
)


class ActionServiceError(ValueError):
    def __init__(self, code: str, message: str, status: int = 422) -> None:
        self.code = code
        self.status = status
        super().__init__(message)


class ActionService:
    def create(
        self, db: Session, organization_id: UUID, payload: ActionCreate, actor: UUID
    ) -> OperationalAction:
        self._validate_source(db, organization_id, payload)
        fingerprint = idempotency_fingerprint(
            organization_id,
            payload.source_type,
            payload.source_reference,
            payload.recommendation_type,
            payload.recommendation_rule_version,
        )
        existing = db.scalar(
            select(OperationalAction).where(
                OperationalAction.organization_id == organization_id,
                OperationalAction.idempotency_fingerprint == fingerprint,
            )
        )
        if existing is not None:
            return existing
        priority = calculate_priority(
            PriorityInput(
                failure_probability=payload.failure_probability,
                severity=payload.severity,
                horizon_days=payload.prediction_horizon_days,
                confidence=payload.confidence_score,
                financial_exposure=payload.expected_avoided_cost,
            )
        )
        approval = calculate_approval(
            intervention_cost=payload.expected_intervention_cost or Decimal("0"),
            avoided_cost=payload.expected_avoided_cost or Decimal("0"),
            confidence=payload.confidence_score or Decimal("0"),
            sensitive=payload.sensitive,
        )
        action = OperationalAction(
            organization_id=organization_id,
            source_type=payload.source_type,
            source_reference=payload.source_reference,
            reliability_execution_id=payload.reliability_execution_id,
            finding_id=payload.finding_id,
            forecast_execution_id=payload.forecast_execution_id,
            orchestration_request_id=payload.orchestration_request_id,
            recommendation_type=payload.recommendation_type,
            recommendation_rule_version=payload.recommendation_rule_version,
            title=payload.title,
            description=payload.description,
            rationale=payload.rationale,
            asset_reference=payload.asset_reference,
            component_reference=payload.component_reference,
            failure_mode=payload.failure_mode,
            priority=priority.classification,
            priority_score=priority.score,
            priority_components=priority.components,
            status=ActionStatus.PROPOSED.value,
            approval_required=approval.required,
            approval_level=approval.level,
            approval_role=approval.role,
            approval_status="required" if approval.required else "not_required",
            verification_required=payload.verification_required,
            due_at=payload.due_at,
            expected_avoided_cost=payload.expected_avoided_cost,
            expected_intervention_cost=payload.expected_intervention_cost,
            currency_code=payload.currency_code,
            confidence_score=payload.confidence_score,
            limitations=[*payload.limitations, *priority.limitations],
            evidence_references=payload.evidence_references,
            idempotency_fingerprint=fingerprint,
            created_by_user_id=actor,
        )
        db.add(action)
        db.flush()
        self._event(db, action, "created", actor, "system", "ACTION_CREATED", fingerprint)
        db.commit()
        db.refresh(action)
        return action

    def _validate_source(self, db: Session, organization_id: UUID, payload: ActionCreate) -> None:
        pairs = (
            (payload.reliability_execution_id, ReliabilityExecution),
            (payload.finding_id, Finding),
            (payload.forecast_execution_id, ForecastExecution),
            (payload.orchestration_request_id, IntelligenceOrchestrationRequest),
        )
        for identifier, model in pairs:
            if (
                identifier is not None
                and db.scalar(
                    select(model.id).where(
                        model.id == identifier, model.organization_id == organization_id
                    )
                )
                is None
            ):
                raise ActionServiceError("SOURCE_NOT_FOUND", "Action source not found", 404)

    def get(self, db: Session, organization_id: UUID, action_id: UUID) -> OperationalAction:
        row = db.scalar(
            select(OperationalAction).where(
                OperationalAction.id == action_id,
                OperationalAction.organization_id == organization_id,
            )
        )
        if row is None:
            raise ActionServiceError("NOT_FOUND", "Operational action not found", 404)
        return row

    def list(
        self,
        db: Session,
        organization_id: UUID,
        page: int,
        page_size: int,
        status: str | None = None,
    ) -> tuple[list[OperationalAction], int]:
        conditions = [OperationalAction.organization_id == organization_id]
        if status:
            conditions.append(OperationalAction.status == status)
        total = (
            db.scalar(select(func.count()).select_from(OperationalAction).where(*conditions)) or 0
        )
        return (
            list(
                db.scalars(
                    select(OperationalAction)
                    .where(*conditions)
                    .order_by(OperationalAction.created_at.desc(), OperationalAction.id)
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ),
            total,
        )

    def transition(
        self,
        db: Session,
        organization_id: UUID,
        action_id: UUID,
        payload: ActionTransitionCreate,
        actor: UUID,
        actor_role: str,
    ) -> OperationalAction:
        action = self.get(db, organization_id, action_id)
        existing = db.scalar(
            select(ActionEvent).where(
                ActionEvent.action_id == action.id,
                ActionEvent.idempotency_key == payload.idempotency_key,
            )
        )
        if existing:
            return action
        current = ActionStatus(action.status)
        require_transition(current, payload.new_status)
        if (
            payload.new_status == ActionStatus.APPROVED
            and action.approval_required
            and actor_role not in {"organization_admin", "platform_admin"}
        ):
            raise ActionServiceError("APPROVAL_FORBIDDEN", "Authorized approval role required", 403)
        if payload.new_status == ActionStatus.PENDING_APPROVAL:
            action.approval_status = "pending"
        elif payload.new_status == ActionStatus.APPROVED:
            action.approval_status = "approved"
        elif payload.new_status == ActionStatus.REJECTED:
            action.approval_status = "rejected"
        if payload.new_status == ActionStatus.COMPLETED:
            dependency_pairs = [
                (item.mandatory, item.status == "resolved")
                for item in db.scalars(
                    select(ActionDependency).where(ActionDependency.action_id == action.id)
                )
            ]
            resource_pairs = [
                (item.mandatory, not item.shortage and item.inventory_check_status == "confirmed")
                for item in db.scalars(
                    select(ActionResourceRequirement).where(
                        ActionResourceRequirement.action_id == action.id
                    )
                )
            ]
            if not dependencies_ready(dependency_pairs):
                raise ActionServiceError("DEPENDENCY_BLOCKED", "Mandatory dependency unresolved")
            if not resources_ready(resource_pairs):
                raise ActionServiceError("RESOURCE_BLOCKED", "Mandatory resource unavailable")
        action.status = payload.new_status.value
        now = datetime.now(UTC)
        if payload.new_status == ActionStatus.COMPLETED:
            action.completed_at = now
        elif payload.new_status == ActionStatus.VERIFIED:
            evidence_count = (
                db.scalar(
                    select(func.count())
                    .select_from(ActionEvidence)
                    .where(
                        ActionEvidence.action_id == action.id,
                        ActionEvidence.lifecycle_stage == "verification",
                    )
                )
                or 0
            )
            if evidence_count == 0:
                raise ActionServiceError(
                    "VERIFICATION_EVIDENCE_REQUIRED", "Verification evidence is required"
                )
            action.verified_at = now
        self._event(
            db,
            action,
            "transition",
            actor,
            actor_role,
            payload.reason_code,
            payload.idempotency_key,
            prior=current.value,
            new=payload.new_status.value,
            note=payload.note,
        )
        db.commit()
        db.refresh(action)
        return action

    def assign(
        self,
        db: Session,
        organization_id: UUID,
        action_id: UUID,
        payload: ActionAssignmentCreate,
        actor: UUID,
        actor_role: str,
    ) -> OperationalAction:
        action = self.get(db, organization_id, action_id)
        if (
            payload.assigned_user_id is not None
            and db.scalar(
                select(OrganizationMembership.id).where(
                    OrganizationMembership.organization_id == organization_id,
                    OrganizationMembership.user_id == payload.assigned_user_id,
                    OrganizationMembership.status == "active",
                )
            )
            is None
        ):
            raise ActionServiceError("ASSIGNEE_NOT_FOUND", "Active tenant assignee not found", 404)
        action.assigned_user_id = payload.assigned_user_id
        action.assigned_role = payload.assigned_role
        action.assigned_team = payload.assigned_team
        action.due_at = payload.due_at or action.due_at
        self._event(
            db, action, "assignment", actor, actor_role, "ACTION_ASSIGNED", payload.idempotency_key
        )
        db.commit()
        db.refresh(action)
        return action

    def add_plan_step(
        self, db: Session, organization_id: UUID, action_id: UUID, payload: ActionPlanStepCreate
    ) -> ActionPlanStep:
        self.get(db, organization_id, action_id)
        row = ActionPlanStep(
            organization_id=organization_id, action_id=action_id, **payload.model_dump()
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def add_dependency(
        self, db: Session, organization_id: UUID, action_id: UUID, payload: ActionDependencyCreate
    ) -> ActionDependency:
        self.get(db, organization_id, action_id)
        self.get(db, organization_id, payload.prerequisite_action_id)
        if action_id == payload.prerequisite_action_id:
            raise ActionServiceError("SELF_DEPENDENCY", "An action cannot depend on itself")
        reverse = db.scalar(
            select(ActionDependency.id).where(
                ActionDependency.action_id == payload.prerequisite_action_id,
                ActionDependency.prerequisite_action_id == action_id,
            )
        )
        if reverse:
            raise ActionServiceError("DEPENDENCY_CYCLE", "Direct dependency cycle detected")
        row = ActionDependency(
            organization_id=organization_id, action_id=action_id, **payload.model_dump()
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def add_resource(
        self, db: Session, organization_id: UUID, action_id: UUID, payload: ActionResourceCreate
    ) -> ActionResourceRequirement:
        self.get(db, organization_id, action_id)
        available = payload.available_quantity
        row = ActionResourceRequirement(
            organization_id=organization_id,
            action_id=action_id,
            **payload.model_dump(exclude={"available_quantity"}),
            available_quantity=available,
            inventory_check_status="confirmed" if available is not None else "unknown",
            shortage=available is not None and available < payload.required_quantity,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def add_evidence(
        self,
        db: Session,
        organization_id: UUID,
        action_id: UUID,
        payload: ActionEvidenceCreate,
        actor: UUID,
    ) -> ActionEvidence:
        self.get(db, organization_id, action_id)
        row = ActionEvidence(
            organization_id=organization_id,
            action_id=action_id,
            actor_user_id=actor,
            **payload.model_dump(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def record_outcome(
        self,
        db: Session,
        organization_id: UUID,
        action_id: UUID,
        payload: ActionOutcomeCreate,
        actor: UUID,
    ) -> ActionOutcome:
        action = self.get(db, organization_id, action_id)
        if payload.outcome_type == "realized":
            count = (
                db.scalar(
                    select(func.count())
                    .select_from(ActionEvidence)
                    .where(
                        ActionEvidence.action_id == action.id,
                        ActionEvidence.lifecycle_stage == "verification",
                    )
                )
                or 0
            )
            if not realized_value_eligible(ActionStatus(action.status), count):
                raise ActionServiceError(
                    "REALIZED_VALUE_NOT_ELIGIBLE",
                    "Realized value requires verified action and evidence",
                )
        row = ActionOutcome(
            organization_id=organization_id,
            action_id=action_id,
            verified_by_user_id=actor if payload.outcome_type == "realized" else None,
            verified_at=datetime.now(UTC) if payload.outcome_type == "realized" else None,
            **payload.model_dump(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def feedback(
        self,
        db: Session,
        organization_id: UUID,
        action_id: UUID,
        payload: ActionFeedbackCreate,
    ) -> ActionModelFeedback:
        action = self.get(db, organization_id, action_id)
        if action.status != ActionStatus.VERIFIED.value or action.reliability_execution_id is None:
            raise ActionServiceError(
                "FEEDBACK_NOT_ELIGIBLE", "Verified reliability action required"
            )
        row = ActionModelFeedback(
            organization_id=organization_id,
            action_id=action_id,
            reliability_execution_id=action.reliability_execution_id,
            prediction_outcome_classification=classify_feedback(
                predicted_positive=payload.predicted_positive,
                failure_occurred=payload.failure_occurred,
                intervention_performed=payload.intervention_performed,
                observation_window_complete=payload.observation_window_complete,
            ),
            **payload.model_dump(exclude={"predicted_positive", "observation_window_complete"}),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def _event(
        db: Session,
        action: OperationalAction,
        event_type: str,
        actor: UUID,
        actor_role: str,
        reason: str,
        key: str,
        prior: str | None = None,
        new: str | None = None,
        note: str | None = None,
    ) -> None:
        db.add(
            ActionEvent(
                organization_id=action.organization_id,
                action_id=action.id,
                event_type=event_type,
                prior_status=prior,
                new_status=new,
                actor_user_id=actor,
                actor_role=actor_role,
                reason_code=reason,
                note=note,
                idempotency_key=key,
            )
        )


action_service = ActionService()
