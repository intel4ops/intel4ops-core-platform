from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis_case import AnalysisCaseDataset
from app.models.entities import utc_now
from app.models.semantic import SemanticInterpretationDecision
from app.models.semantic_review import (
    SemanticDecisionAuditEvent,
    SemanticDecisionVersion,
    SemanticReview,
)
from app.semantic.concept_registry import default_canonical_concept_registry
from app.semantic.review import (
    EffectiveDecision,
    ReviewGroup,
    SemanticReviewAction,
    StoredVersionView,
    classify_review_group,
    effective_status_and_source_for_action,
    resolve_effective_decision,
    validate_action_payload,
)

# ---------------------------------------------------------------------------
# P3.xxE.1A Semantic Review & Governance Foundation. Production execution
# surface -- never imports app.ground_truth_validation (see
# tests/test_validation_import_boundary.py /
# tests/test_semantic_architecture_guardrails.py). Read-only with respect
# to Mapping/Intelligence/Command/Recovery: nothing here is called from
# those modules, and this service writes nothing they read.
#
# Deliberately NOT here: any cross-run reuse/inheritance. Every method
# operates on exactly one SemanticInterpretationDecision.id -- see the
# approved P3.xxE.1A plan's Out of Scope section.
# ---------------------------------------------------------------------------


class SemanticReviewServiceError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def _fail(code: str, message: str, status: int = 400) -> NoReturn:
    raise SemanticReviewServiceError(code, message, status)


@dataclass(frozen=True)
class ReviewQueueItem:
    decision: SemanticInterpretationDecision
    dataset_label: str
    latest_version: SemanticDecisionVersion | None
    group: ReviewGroup


@dataclass(frozen=True)
class ReviewHistoryEntry:
    review: SemanticReview
    version: SemanticDecisionVersion


def _to_view(version: SemanticDecisionVersion | None) -> StoredVersionView | None:
    if version is None:
        return None
    return StoredVersionView(
        version_number=version.version_number,
        effective_status=version.effective_status,  # type: ignore[arg-type]
        effective_concept=version.effective_concept,
        effective_confidence=version.effective_confidence,
    )


def _audit(
    db: Session,
    organization_id: UUID,
    event_type: str,
    entity_id: UUID,
    actor_user_id: UUID,
    summary: str,
) -> None:
    db.add(
        SemanticDecisionAuditEvent(
            organization_id=organization_id,
            event_type=event_type,
            entity_type="semantic_interpretation_decision",
            entity_id=entity_id,
            actor_type="user",
            actor_user_id=actor_user_id,
            summary=summary,
        )
    )


_EVENT_TYPE_BY_ACTION = {
    SemanticReviewAction.CONFIRM: "semantic_proposal_confirmed",
    SemanticReviewAction.CORRECT: "semantic_proposal_corrected",
    SemanticReviewAction.REJECT: "semantic_proposal_rejected",
    SemanticReviewAction.MARK_UNRESOLVED: "semantic_proposal_marked_unresolved",
}


class SemanticReviewService:
    def _get_decision(
        self, db: Session, organization_id: UUID, decision_id: UUID
    ) -> SemanticInterpretationDecision:
        decision = db.scalar(
            select(SemanticInterpretationDecision).where(
                SemanticInterpretationDecision.organization_id == organization_id,
                SemanticInterpretationDecision.id == decision_id,
            )
        )
        if decision is None:
            _fail("SEMANTIC_DECISION_NOT_FOUND", "Semantic decision not found", 404)
        return decision

    def _latest_version(
        self, db: Session, organization_id: UUID, decision_id: UUID
    ) -> SemanticDecisionVersion | None:
        return db.scalar(
            select(SemanticDecisionVersion)
            .where(
                SemanticDecisionVersion.organization_id == organization_id,
                SemanticDecisionVersion.decision_id == decision_id,
            )
            .order_by(SemanticDecisionVersion.version_number.desc())
            .limit(1)
        )

    def list_review_queue(
        self,
        db: Session,
        organization_id: UUID,
        case_id: UUID,
        run_id: UUID | None = None,
        group: str | None = None,
    ) -> list[ReviewQueueItem]:
        case_datasets = {
            row.id: row.source_label
            for row in db.scalars(
                select(AnalysisCaseDataset).where(
                    AnalysisCaseDataset.organization_id == organization_id,
                    AnalysisCaseDataset.analysis_case_id == case_id,
                )
            ).all()
        }
        if not case_datasets:
            return []

        decisions_stmt = select(SemanticInterpretationDecision).where(
            SemanticInterpretationDecision.organization_id == organization_id,
            SemanticInterpretationDecision.analysis_case_dataset_id.in_(case_datasets.keys()),
        )
        if run_id is not None:
            decisions_stmt = decisions_stmt.where(SemanticInterpretationDecision.run_id == run_id)
        else:
            decisions_stmt = decisions_stmt.order_by(
                SemanticInterpretationDecision.created_at.desc()
            )
        decisions = list(db.scalars(decisions_stmt).all())
        if run_id is None:
            latest_by_dataset_field: dict[tuple[UUID, str], SemanticInterpretationDecision] = {}
            for decision in decisions:
                key = (decision.analysis_case_dataset_id, decision.source_field)
                if key not in latest_by_dataset_field:
                    latest_by_dataset_field[key] = decision
            decisions = list(latest_by_dataset_field.values())

        default_groups = {ReviewGroup.PENDING_REVIEW, ReviewGroup.NEEDS_RESOLUTION}
        if group == "all":
            wanted_groups = None
        elif group:
            wanted_groups = {ReviewGroup(group)}
        else:
            wanted_groups = default_groups

        items: list[ReviewQueueItem] = []
        for decision in decisions:
            latest_version = self._latest_version(db, organization_id, decision.id)
            item_group = classify_review_group(
                machine_status=decision.status, latest_version=_to_view(latest_version)
            )
            if item_group is None:
                continue
            if wanted_groups is not None and item_group not in wanted_groups:
                continue
            items.append(
                ReviewQueueItem(
                    decision=decision,
                    dataset_label=case_datasets[decision.analysis_case_dataset_id],
                    latest_version=latest_version,
                    group=item_group,
                )
            )
        items.sort(key=lambda item: item.decision.confidence)
        return items

    def get_review_item(
        self, db: Session, organization_id: UUID, decision_id: UUID
    ) -> tuple[SemanticInterpretationDecision, SemanticDecisionVersion | None, EffectiveDecision]:
        decision = self._get_decision(db, organization_id, decision_id)
        latest_version = self._latest_version(db, organization_id, decision_id)
        effective = resolve_effective_decision(
            machine_status=decision.status,
            machine_selected_concept=decision.selected_concept,
            machine_confidence=decision.confidence,
            latest_version=_to_view(latest_version),
        )
        return decision, latest_version, effective

    def get_history(
        self, db: Session, organization_id: UUID, decision_id: UUID
    ) -> list[ReviewHistoryEntry]:
        self._get_decision(db, organization_id, decision_id)
        versions = list(
            db.scalars(
                select(SemanticDecisionVersion)
                .where(
                    SemanticDecisionVersion.organization_id == organization_id,
                    SemanticDecisionVersion.decision_id == decision_id,
                )
                .order_by(SemanticDecisionVersion.version_number.asc())
            ).all()
        )
        reviews_by_id = {
            row.id: row
            for row in db.scalars(
                select(SemanticReview).where(
                    SemanticReview.organization_id == organization_id,
                    SemanticReview.id.in_([v.review_id for v in versions]),
                )
            ).all()
        }
        return [
            ReviewHistoryEntry(review=reviews_by_id[version.review_id], version=version)
            for version in versions
        ]

    def submit_review(
        self,
        db: Session,
        organization_id: UUID,
        decision_id: UUID,
        *,
        action: str,
        corrected_concept: str | None,
        notes: str | None,
        expected_version: int,
        reviewer_user_id: UUID,
        reviewer_role: str,
    ) -> tuple[SemanticReview, SemanticDecisionVersion]:
        try:
            review_action = SemanticReviewAction(action)
        except ValueError:
            _fail("SEMANTIC_REVIEW_INVALID_ACTION", f"Unknown review action: {action}", 400)

        payload_error = validate_action_payload(review_action, corrected_concept)
        if payload_error is not None:
            _fail("SEMANTIC_REVIEW_INVALID_ACTION", payload_error, 400)

        if review_action == SemanticReviewAction.CORRECT:
            assert corrected_concept is not None
            if default_canonical_concept_registry.get(corrected_concept) is None:
                _fail(
                    "SEMANTIC_REVIEW_INVALID_CONCEPT",
                    f"Unknown canonical concept: {corrected_concept}",
                    400,
                )

        # Row lock on the decision itself -- it always exists and is stable
        # per (dataset, field, run), so no separate "current pointer" row
        # is needed (see the plan's Optimistic Concurrency section).
        decision = db.scalar(
            select(SemanticInterpretationDecision)
            .where(
                SemanticInterpretationDecision.organization_id == organization_id,
                SemanticInterpretationDecision.id == decision_id,
            )
            .with_for_update()
        )
        if decision is None:
            _fail("SEMANTIC_DECISION_NOT_FOUND", "Semantic decision not found", 404)

        latest_version = self._latest_version(db, organization_id, decision_id)
        current_version_number = latest_version.version_number if latest_version else 0
        if current_version_number != expected_version:
            _fail(
                "SEMANTIC_REVIEW_VERSION_CONFLICT",
                "Semantic decision version changed since expected_version was read",
                409,
            )

        review = SemanticReview(
            organization_id=organization_id,
            decision_id=decision_id,
            action=review_action.value,
            corrected_concept=corrected_concept,
            notes=notes,
            reviewer_user_id=reviewer_user_id,
            reviewer_role=reviewer_role,
            reviewed_at=utc_now(),
        )
        db.add(review)
        db.flush()

        effective_status, source = effective_status_and_source_for_action(review_action)
        if review_action == SemanticReviewAction.CONFIRM:
            effective_concept = decision.selected_concept
            effective_confidence = decision.confidence
        elif review_action == SemanticReviewAction.CORRECT:
            effective_concept = corrected_concept
            effective_confidence = None
        else:
            effective_concept = None
            effective_confidence = None

        version = SemanticDecisionVersion(
            organization_id=organization_id,
            decision_id=decision_id,
            version_number=current_version_number + 1,
            supersedes_version_id=latest_version.id if latest_version else None,
            effective_status=effective_status.value,
            effective_concept=effective_concept,
            review_id=review.id,
            source=source.value,
            effective_confidence=effective_confidence,
            created_by_user_id=reviewer_user_id,
        )
        db.add(version)

        _audit(
            db,
            organization_id,
            "semantic_review_created",
            decision_id,
            reviewer_user_id,
            f"Review submitted: action={review_action.value}",
        )
        _audit(
            db,
            organization_id,
            _EVENT_TYPE_BY_ACTION[review_action],
            decision_id,
            reviewer_user_id,
            f"Decision now effective_status={effective_status.value} (version "
            f"{current_version_number + 1})",
        )
        if latest_version is not None:
            _audit(
                db,
                organization_id,
                "semantic_decision_superseded",
                decision_id,
                reviewer_user_id,
                f"Version {latest_version.version_number} superseded by version "
                f"{current_version_number + 1}",
            )

        db.commit()
        db.refresh(review)
        db.refresh(version)
        return review, version

    def get_effective_for_run(
        self, db: Session, organization_id: UUID, case_id: UUID, run_id: UUID
    ) -> list[tuple[SemanticInterpretationDecision, EffectiveDecision]]:
        case_dataset_ids = list(
            db.scalars(
                select(AnalysisCaseDataset.id).where(
                    AnalysisCaseDataset.organization_id == organization_id,
                    AnalysisCaseDataset.analysis_case_id == case_id,
                )
            ).all()
        )
        if not case_dataset_ids:
            return []
        decisions = list(
            db.scalars(
                select(SemanticInterpretationDecision).where(
                    SemanticInterpretationDecision.organization_id == organization_id,
                    SemanticInterpretationDecision.analysis_case_dataset_id.in_(case_dataset_ids),
                    SemanticInterpretationDecision.run_id == run_id,
                )
            ).all()
        )
        results = []
        for decision in decisions:
            latest_version = self._latest_version(db, organization_id, decision.id)
            effective = resolve_effective_decision(
                machine_status=decision.status,
                machine_selected_concept=decision.selected_concept,
                machine_confidence=decision.confidence,
                latest_version=_to_view(latest_version),
            )
            results.append((decision, effective))
        return results


semantic_review_service = SemanticReviewService()
