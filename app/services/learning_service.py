from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import Finding
from app.models.findings import FindingEvidenceBundle, FindingEvidenceItem
from app.models.ingestion import DatasetVersion, IngestionBatch
from app.models.intelligence import IntelligenceExecution
from app.models.learning import LearningAuditEvent, LearningSourceCase, OperationalLearning
from app.schemas.learning import (
    LearningAuditRead,
    LearningCreate,
    LearningEligibilityRead,
    LearningPage,
    LearningRead,
    LearningSourceCaseRead,
    LearningTransition,
    MemoryEvidenceRead,
    MemoryFindingRead,
    OperationalMemoryRead,
)
from app.schemas.recovery_workspace import RecoveryWorkspaceRead
from app.services.recovery_workspace_service import recovery_workspace_service


class LearningServiceError(ValueError):
    def __init__(self, code: str, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class LearningService:
    def operational_memory(
        self, db: Session, organization_id: UUID, finding_id: UUID
    ) -> OperationalMemoryRead:
        finding = self._finding(db, organization_id, finding_id)
        workspace = recovery_workspace_service.get(db, organization_id, finding_id)
        bundle = db.scalar(
            select(FindingEvidenceBundle)
            .where(
                FindingEvidenceBundle.organization_id == organization_id,
                FindingEvidenceBundle.finding_id == finding_id,
            )
            .order_by(FindingEvidenceBundle.bundle_version.desc())
            .limit(1)
        )
        evidence = (
            list(
                db.scalars(
                    select(FindingEvidenceItem)
                    .where(
                        FindingEvidenceItem.organization_id == organization_id,
                        FindingEvidenceItem.evidence_bundle_id == bundle.id,
                    )
                    .order_by(FindingEvidenceItem.sequence_number)
                )
            )
            if bundle is not None
            else []
        )
        provenance = self._provenance(db, organization_id, finding)
        eligibility = self._eligibility(
            workspace,
            bool(evidence or workspace.action_evidence or workspace.measurement_evidence),
            provenance,
        )
        learnings = self.list_learning(
            db, organization_id, page=1, page_size=100, source_finding_id=finding_id
        ).items
        return OperationalMemoryRead(
            organization_id=organization_id,
            finding=MemoryFindingRead(
                id=finding.id,
                title=finding.title,
                summary=finding.summary,
                status=finding.status,
                finding_type=finding.finding_type,
                domain=finding.domain,
                confidence_score=float(finding.confidence_score),
                exposure_value=(
                    str(finding.exposure_value) if finding.exposure_value is not None else None
                ),
                exposure_currency=finding.exposure_currency,
                causal_chain_id=finding.causal_chain_id,
                created_at=finding.created_at,
            ),
            finding_evidence=[
                MemoryEvidenceRead(
                    id=item.id,
                    evidence_type=item.evidence_type,
                    source_type=item.reference_type,
                    source_identifier=str(
                        item.reference_id or item.reference_uri or item.canonical_record_reference
                    ),
                    observed_at=None,
                    created_at=item.created_at,
                )
                for item in evidence
            ],
            recovery_workspace=workspace,
            eligibility=eligibility,
            learnings=learnings,
        )

    def create(
        self,
        db: Session,
        organization_id: UUID,
        payload: LearningCreate,
        actor_user_id: UUID,
        actor_role: str,
    ) -> LearningRead:
        findings = [
            self._finding(db, organization_id, finding_id)
            for finding_id in payload.source_finding_ids
        ]
        provenances: list[str] = []
        for finding in findings:
            workspace = recovery_workspace_service.get(db, organization_id, finding.id)
            provenance = self._provenance(db, organization_id, finding)
            evidence_exists = db.scalar(
                select(FindingEvidenceBundle.id).where(
                    FindingEvidenceBundle.organization_id == organization_id,
                    FindingEvidenceBundle.finding_id == finding.id,
                    FindingEvidenceBundle.completeness_status == "complete",
                )
            ) is not None or bool(workspace.action_evidence or workspace.measurement_evidence)
            eligibility = self._eligibility(workspace, evidence_exists, provenance)
            if not eligibility.eligible:
                raise LearningServiceError(
                    "LEARNING_CASE_INELIGIBLE",
                    f"Finding {finding.id} is not mature enough for governed learning: "
                    f"{', '.join(eligibility.reasons)}",
                )
            if payload.value_basis == "realized_measurement" and not eligibility.has_realized_value:
                raise LearningServiceError(
                    "REALIZED_VALUE_REQUIRED", "Realized learning requires a Recovery measurement"
                )
            if payload.value_basis == "verified_ledger" and not eligibility.has_verified_value:
                raise LearningServiceError(
                    "VERIFIED_VALUE_REQUIRED", "Verified learning requires a posted ledger entry"
                )
            if (
                payload.value_basis == "expected"
                and workspace.recovery_case is None
                and (workspace.action is None or workspace.action.expected_avoided_cost is None)
            ):
                raise LearningServiceError(
                    "EXPECTED_VALUE_REQUIRED",
                    "Expected learning requires an authoritative Recovery forecast",
                )
            provenances.append(provenance)
        aggregate_provenance = provenances[0] if len(set(provenances)) == 1 else "mixed"
        learning = OperationalLearning(
            organization_id=organization_id,
            learning_type=payload.learning_type,
            title=payload.title,
            statement=payload.statement,
            scope=payload.scope,
            status="candidate",
            provenance_type=aggregate_provenance,
            value_basis=payload.value_basis,
            created_by_user_id=actor_user_id,
        )
        db.add(learning)
        db.flush()
        for finding, provenance in zip(findings, provenances, strict=True):
            db.add(
                LearningSourceCase(
                    organization_id=organization_id,
                    learning_id=learning.id,
                    finding_id=finding.id,
                    provenance_type=provenance,
                )
            )
        db.add(
            self._audit(
                learning, "candidate_created", None, "candidate", actor_user_id, actor_role, None
            )
        )
        db.commit()
        return self.get(db, organization_id, learning.id)

    def transition(
        self,
        db: Session,
        organization_id: UUID,
        learning_id: UUID,
        payload: LearningTransition,
        actor_user_id: UUID,
        actor_role: str,
    ) -> LearningRead:
        learning = self._learning(db, organization_id, learning_id)
        transitions = {
            ("candidate", "review"): "reviewed",
            ("reviewed", "approve"): "approved_for_reuse",
            ("reviewed", "reject"): "rejected",
            ("approved_for_reuse", "retire"): "retired",
        }
        target = transitions.get((learning.status, payload.transition))
        if target is None:
            raise LearningServiceError(
                "INVALID_LEARNING_TRANSITION",
                f"Cannot {payload.transition} learning in {learning.status} state",
            )
        prior = learning.status
        learning.status = target
        learning.rationale = payload.rationale
        learning.reviewed_by_user_id = actor_user_id
        learning.reviewed_at = datetime.now(UTC)
        db.add(
            self._audit(
                learning,
                payload.transition,
                prior,
                target,
                actor_user_id,
                actor_role,
                payload.rationale,
            )
        )
        db.commit()
        return self.get(db, organization_id, learning.id)

    def list_learning(
        self,
        db: Session,
        organization_id: UUID,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
        provenance: str | None = None,
        learning_type: str | None = None,
        source_finding_id: UUID | None = None,
    ) -> LearningPage:
        query = select(OperationalLearning).where(
            OperationalLearning.organization_id == organization_id
        )
        if status:
            query = query.where(OperationalLearning.status == status)
        if provenance:
            query = query.where(OperationalLearning.provenance_type == provenance)
        if learning_type:
            query = query.where(OperationalLearning.learning_type == learning_type)
        if source_finding_id:
            query = query.where(
                OperationalLearning.id.in_(
                    select(LearningSourceCase.learning_id).where(
                        LearningSourceCase.organization_id == organization_id,
                        LearningSourceCase.finding_id == source_finding_id,
                    )
                )
            )
        total = int(
            db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
        )
        rows = list(
            db.scalars(
                query.order_by(OperationalLearning.created_at.desc(), OperationalLearning.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return LearningPage(
            items=self._reads(db, organization_id, rows),
            page=page,
            page_size=page_size,
            total=total,
        )

    def get(self, db: Session, organization_id: UUID, learning_id: UUID) -> LearningRead:
        return self._reads(db, organization_id, [self._learning(db, organization_id, learning_id)])[
            0
        ]

    def _reads(
        self, db: Session, organization_id: UUID, rows: list[OperationalLearning]
    ) -> list[LearningRead]:
        ids = [row.id for row in rows]
        sources = (
            list(
                db.scalars(
                    select(LearningSourceCase).where(
                        LearningSourceCase.organization_id == organization_id,
                        LearningSourceCase.learning_id.in_(ids),
                    )
                )
            )
            if ids
            else []
        )
        audits = (
            list(
                db.scalars(
                    select(LearningAuditEvent)
                    .where(
                        LearningAuditEvent.organization_id == organization_id,
                        LearningAuditEvent.learning_id.in_(ids),
                    )
                    .order_by(LearningAuditEvent.occurred_at)
                )
            )
            if ids
            else []
        )
        return [
            LearningRead.model_validate(row).model_copy(
                update={
                    "source_cases": [
                        LearningSourceCaseRead.model_validate(item)
                        for item in sources
                        if item.learning_id == row.id
                    ],
                    "audit_history": [
                        LearningAuditRead.model_validate(item)
                        for item in audits
                        if item.learning_id == row.id
                    ],
                }
            )
            for row in rows
        ]

    @staticmethod
    def _eligibility(
        workspace: RecoveryWorkspaceRead, evidence_complete: bool, provenance: str
    ) -> LearningEligibilityRead:
        recommendation = workspace.recommendation
        approval = workspace.approval
        action = workspace.action
        has_outcome = bool(workspace.action_outcomes)
        has_realized = bool(workspace.measurements)
        has_verified = bool(workspace.verified_ledger)
        reasons: list[str] = []
        if recommendation is None:
            reasons.append("recommendation_missing")
        if approval is None or approval.decision != "approve":
            reasons.append("approval_missing")
        execution_mature = (
            workspace.recovery_execution is not None
            and workspace.recovery_execution.status
            in {"completed", "awaiting_measurement", "measured", "verified"}
        )
        if action is None or (
            action.status not in {"completed", "verified"} and not execution_mature
        ):
            reasons.append("action_not_completed")
        if not has_outcome:
            reasons.append("outcome_missing")
        if not evidence_complete:
            reasons.append("supporting_evidence_incomplete")
        return LearningEligibilityRead(
            eligible=not reasons,
            reasons=reasons,
            has_outcome=has_outcome,
            has_realized_value=has_realized,
            has_verified_value=has_verified,
            provenance_type=provenance,
        )

    @staticmethod
    def _provenance(db: Session, organization_id: UUID, finding: Finding) -> str:
        if finding.source_execution_id is None:
            return "manual"
        batch = db.scalar(
            select(IngestionBatch)
            .join(DatasetVersion, DatasetVersion.ingestion_batch_id == IngestionBatch.id)
            .join(
                IntelligenceExecution, IntelligenceExecution.dataset_version_id == DatasetVersion.id
            )
            .where(
                IntelligenceExecution.id == finding.source_execution_id,
                IntelligenceExecution.organization_id == organization_id,
                DatasetVersion.organization_id == organization_id,
                IngestionBatch.organization_id == organization_id,
            )
        )
        if batch is None:
            return "manual"
        return (
            "simulation"
            if batch.ingestion_method == "simulated" or batch.trigger_type == "simulation"
            else "production"
        )

    @staticmethod
    def _finding(db: Session, organization_id: UUID, finding_id: UUID) -> Finding:
        finding = db.scalar(
            select(Finding).where(
                Finding.organization_id == organization_id, Finding.id == finding_id
            )
        )
        if finding is None:
            raise LearningServiceError("FINDING_NOT_FOUND", "Finding not found", 404)
        return finding

    @staticmethod
    def _learning(db: Session, organization_id: UUID, learning_id: UUID) -> OperationalLearning:
        learning = db.scalar(
            select(OperationalLearning).where(
                OperationalLearning.organization_id == organization_id,
                OperationalLearning.id == learning_id,
            )
        )
        if learning is None:
            raise LearningServiceError("LEARNING_NOT_FOUND", "Learning not found", 404)
        return learning

    @staticmethod
    def _audit(
        learning: OperationalLearning,
        event: str,
        prior: str | None,
        target: str,
        actor: UUID,
        role: str,
        rationale: str | None,
    ) -> LearningAuditEvent:
        return LearningAuditEvent(
            organization_id=learning.organization_id,
            learning_id=learning.id,
            event_type=event,
            prior_status=prior,
            new_status=target,
            actor_user_id=actor,
            actor_role=role,
            rationale=rationale,
            metadata_json={
                "provenance_type": learning.provenance_type,
                "value_basis": learning.value_basis,
            },
        )


learning_service = LearningService()
