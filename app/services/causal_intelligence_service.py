from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import NoReturn
from uuid import UUID, uuid4

from sqlalchemy import ColumnElement, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.canonical_mapping import CanonicalEvent, CanonicalMetric, SourceCanonicalLink
from app.models.causal_intelligence import (
    CAUSAL_HYPOTHESIS_TERMINAL_STATUSES,
    CausalAuditEvent,
    CausalChain,
    CausalChainVersion,
    CausalEdge,
    CausalEvidenceLink,
    CausalHypothesis,
    CausalHypothesisStatus,
    CausalIntervention,
    CausalMethodDefinition,
    CausalNode,
    CausalOutcomeAssessment,
    CausalReview,
)
from app.models.trust import AnalyticalReadinessDecision
from app.schemas.causal_intelligence import (
    CausalEvidenceLinkCreate,
    CausalHypothesisCreate,
    CausalInterventionCreate,
    CausalMethodDefinitionCreate,
    CausalNodeCreate,
    CausalOutcomeAssessmentCreate,
    CausalReviewCreate,
    RootCauseRankingEntry,
)

BLOCKING_MAPPING_STATUSES = {
    "unresolved",
    "ambiguous",
    "conflicting",
    "missing_required_field",
    "rejected",
    "superseded",
}
ASSOCIATION_ONLY_EDGE_TYPES = {"correlates_with", "associated_with"}
NON_OVERLAP_EDGE_TYPES = {"causes", "precedes"}
MINIMUM_MAPPING_CONFIDENCE_THRESHOLD = Decimal("0.5")
PROBABLE_CONFIDENCE_THRESHOLD = Decimal("0.6")
TEMPORAL_PRECISION_SECONDS = {
    "instant": 0,
    "second": 1,
    "minute": 60,
    "hour": 3600,
    "day": 86400,
    "period": 86400,
}


class CausalIntelligenceServiceError(RuntimeError):
    def __init__(self, code: str, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def _fail(code: str, message: str, status: int = 422) -> NoReturn:
    raise CausalIntelligenceServiceError(code, message, status)


def _stable_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: object) -> str:
    return hashlib.sha256(_stable_json(value).encode()).hexdigest()


def _audit(
    db: Session,
    organization_id: UUID,
    event_type: str,
    entity_type: str,
    entity_id: UUID,
    actor_type: str,
    actor_user_id: UUID | None,
    summary: str,
    metadata: dict[str, object] | None = None,
) -> None:
    db.add(
        CausalAuditEvent(
            organization_id=organization_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_type=actor_type,
            actor_user_id=actor_user_id,
            summary=summary,
            metadata_json=metadata or {},
        )
    )


class CausalOntologyService:
    def create_method(
        self, db: Session, payload: CausalMethodDefinitionCreate
    ) -> CausalMethodDefinition:
        content_hash = _fingerprint(
            {
                "method_code": payload.method_code,
                "method_class": payload.method_class,
                "method_version": payload.method_version,
                "scope_key": payload.scope_key,
                "parameters_schema": payload.parameters_schema,
            }
        )
        method = CausalMethodDefinition(
            method_code=payload.method_code,
            method_name=payload.method_name,
            method_class=payload.method_class,
            method_version=payload.method_version,
            default_confidence_weight=payload.default_confidence_weight,
            parameters_schema=payload.parameters_schema,
            status="draft",
            effective_from=payload.effective_from,
            effective_to=payload.effective_to,
            content_hash=content_hash,
            scope_type=payload.scope_type,
            scope_key=payload.scope_key,
            owner_organization_id=payload.owner_organization_id,
        )
        db.add(method)
        db.commit()
        db.refresh(method)
        return method

    def list_methods(
        self, db: Session, organization_id: UUID | None
    ) -> list[CausalMethodDefinition]:
        stmt = select(CausalMethodDefinition).where(
            (CausalMethodDefinition.scope_type != "organization")
            | (CausalMethodDefinition.owner_organization_id == organization_id)
        )
        return list(db.scalars(stmt))


class CausalNodeService:
    def _identity_filters(
        self,
        organization_id: UUID,
        node_type: str,
        target_kind: str | None,
        target_id: UUID | None,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = [
            CausalNode.organization_id == organization_id,
            CausalNode.node_type == node_type,
        ]
        filters.append(
            CausalNode.target_kind == target_kind
            if target_kind is not None
            else CausalNode.target_kind.is_(None)
        )
        filters.append(
            CausalNode.target_id == target_id
            if target_id is not None
            else CausalNode.target_id.is_(None)
        )
        return filters

    def get_or_create(
        self, db: Session, organization_id: UUID, payload: CausalNodeCreate
    ) -> CausalNode:
        target_kind = None if payload.node_type == "external_factor" else payload.node_type
        # External factors have no backing record (target_kind/target_id are both NULL for
        # every one), so there is no natural dedup key: each call creates a distinct node,
        # relying on the DB unique index treating NULLs as distinct.
        if payload.node_type == "external_factor":
            node = CausalNode(
                organization_id=organization_id,
                node_type=payload.node_type,
                target_kind=None,
                target_id=None,
                external_description=payload.external_description,
                content_fingerprint=_fingerprint(
                    {
                        "node_type": payload.node_type,
                        "external_description": payload.external_description,
                        "nonce": str(uuid4()),
                    }
                ),
            )
            db.add(node)
            db.commit()
            db.refresh(node)
            return node
        filters = self._identity_filters(
            organization_id, payload.node_type, target_kind, payload.target_id
        )
        existing = db.scalar(select(CausalNode).where(*filters))
        if existing is not None:
            return existing
        node = CausalNode(
            organization_id=organization_id,
            node_type=payload.node_type,
            target_kind=target_kind,
            target_id=payload.target_id,
            external_description=payload.external_description,
            content_fingerprint=_fingerprint(
                {
                    "node_type": payload.node_type,
                    "target_id": str(payload.target_id) if payload.target_id else None,
                    "external_description": payload.external_description,
                }
            ),
        )
        db.add(node)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = db.scalar(select(CausalNode).where(*filters))
            if existing is None:
                raise
            return existing
        db.refresh(node)
        return node


class CausalHypothesisService:
    def create(
        self,
        db: Session,
        organization_id: UUID,
        payload: CausalHypothesisCreate,
        actor: UUID,
    ) -> CausalHypothesis:
        if payload.source_node_id == payload.target_node_id:
            _fail("self_referential_node", "a causal hypothesis cannot target its own source node")
        content_hash = _fingerprint(
            {
                "source_node_id": str(payload.source_node_id),
                "target_node_id": str(payload.target_node_id),
                "proposed_edge_type": payload.proposed_edge_type,
                "method_id": str(payload.method_id),
            }
        )
        existing = db.scalar(
            select(CausalHypothesis).where(
                CausalHypothesis.organization_id == organization_id,
                CausalHypothesis.content_hash == content_hash,
            )
        )
        if existing is not None:
            return existing
        hypothesis = CausalHypothesis(
            organization_id=organization_id,
            source_node_id=payload.source_node_id,
            target_node_id=payload.target_node_id,
            proposed_edge_type=payload.proposed_edge_type,
            method_id=payload.method_id,
            lifecycle_status=CausalHypothesisStatus.DRAFT.value,
            causal_role=payload.causal_role,
            cause_category=payload.cause_category,
            temporal_lag_seconds=payload.temporal_lag_seconds,
            hard_gate_failure_reasons=[],
            content_hash=content_hash,
            validity_from=payload.validity_from,
            validity_to=payload.validity_to,
            created_by_user_id=actor,
        )
        db.add(hypothesis)
        db.flush()
        _audit(
            db,
            organization_id,
            "hypothesis_created",
            "causal_hypothesis",
            hypothesis.id,
            "user",
            actor,
            f"Hypothesis proposed: {payload.proposed_edge_type}",
        )
        db.commit()
        db.refresh(hypothesis)
        return hypothesis

    def propose(self, db: Session, organization_id: UUID, hypothesis_id: UUID) -> CausalHypothesis:
        hypothesis = self._get(db, organization_id, hypothesis_id)
        if hypothesis.lifecycle_status != CausalHypothesisStatus.DRAFT.value:
            _fail("invalid_transition", "only draft hypotheses can be proposed")
        hypothesis.lifecycle_status = CausalHypothesisStatus.PROPOSED.value
        db.commit()
        db.refresh(hypothesis)
        return hypothesis

    def _get(self, db: Session, organization_id: UUID, hypothesis_id: UUID) -> CausalHypothesis:
        hypothesis = db.scalar(
            select(CausalHypothesis).where(
                CausalHypothesis.organization_id == organization_id,
                CausalHypothesis.id == hypothesis_id,
            )
        )
        if hypothesis is None:
            _fail("hypothesis_not_found", "causal hypothesis not found", status=404)
        return hypothesis


class CausalEvidenceService:
    def attach(
        self,
        db: Session,
        organization_id: UUID,
        hypothesis_id: UUID,
        payload: CausalEvidenceLinkCreate,
    ) -> CausalEvidenceLink:
        hypothesis = db.scalar(
            select(CausalHypothesis).where(
                CausalHypothesis.organization_id == organization_id,
                CausalHypothesis.id == hypothesis_id,
            )
        )
        if hypothesis is None:
            _fail("hypothesis_not_found", "causal hypothesis not found", status=404)
        if hypothesis.lifecycle_status in CAUSAL_HYPOTHESIS_TERMINAL_STATUSES:
            _fail("hypothesis_terminal", "cannot attach evidence to a terminal hypothesis")
        link = CausalEvidenceLink(
            organization_id=organization_id,
            hypothesis_id=hypothesis_id,
            evidence_kind=payload.evidence_kind,
            evidence_id=payload.evidence_id,
            supports=payload.supports,
            weight=payload.weight,
            notes=payload.notes,
        )
        db.add(link)
        db.flush()
        self._recount(db, hypothesis)
        if hypothesis.lifecycle_status in {
            CausalHypothesisStatus.DRAFT.value,
            CausalHypothesisStatus.PROPOSED.value,
        }:
            hypothesis.lifecycle_status = CausalHypothesisStatus.EVIDENCE_PENDING.value
        db.commit()
        db.refresh(link)
        return link

    def _recount(self, db: Session, hypothesis: CausalHypothesis) -> None:
        links = list(
            db.scalars(
                select(CausalEvidenceLink).where(CausalEvidenceLink.hypothesis_id == hypothesis.id)
            )
        )
        hypothesis.evidence_count = sum(1 for link in links if link.supports)
        hypothesis.contradiction_count = sum(1 for link in links if not link.supports)


def _resolve_mapping_confidence(
    db: Session, evidence_kind: str, evidence_id: UUID
) -> tuple[Decimal | None, str | None]:
    model = {
        "canonical_record": None,
        "source_canonical_link": SourceCanonicalLink,
    }.get(evidence_kind)
    record: CanonicalEvent | CanonicalMetric | SourceCanonicalLink | None = None
    if evidence_kind == "canonical_record":
        record = db.get(CanonicalEvent, evidence_id) or db.get(CanonicalMetric, evidence_id)
    elif model is not None:
        record = db.get(model, evidence_id)
    if record is None:
        return None, None
    status = getattr(record, "mapping_status", None)
    return getattr(record, "mapping_confidence_score", None), status


def _resolve_occurrence(
    db: Session, node: CausalNode
) -> tuple[datetime | None, datetime | None, str | None]:
    record: CanonicalEvent | CanonicalMetric | None
    if node.target_kind == "canonical_event" and node.target_id is not None:
        record = db.get(CanonicalEvent, node.target_id)
    elif node.target_kind == "canonical_metric" and node.target_id is not None:
        record = db.get(CanonicalMetric, node.target_id)
    else:
        return None, None, None
    if record is None:
        return None, None, None
    return record.occurrence_start, record.occurrence_end, record.occurrence_precision


class CausalEvaluationService:
    def evaluate(self, db: Session, organization_id: UUID, hypothesis_id: UUID) -> CausalHypothesis:
        hypothesis = db.scalar(
            select(CausalHypothesis).where(
                CausalHypothesis.organization_id == organization_id,
                CausalHypothesis.id == hypothesis_id,
            )
        )
        if hypothesis is None:
            _fail("hypothesis_not_found", "causal hypothesis not found", status=404)
        if hypothesis.lifecycle_status in CAUSAL_HYPOTHESIS_TERMINAL_STATUSES:
            _fail("hypothesis_terminal", "cannot evaluate a terminal hypothesis")

        reasons: list[object] = []
        confidences: list[Decimal] = []

        links = list(
            db.scalars(
                select(CausalEvidenceLink).where(
                    CausalEvidenceLink.hypothesis_id == hypothesis.id,
                    CausalEvidenceLink.supports.is_(True),
                )
            )
        )
        if not links:
            reasons.append(
                {
                    "code": "missing_required_evidence",
                    "message": "no supporting evidence attached",
                }
            )
        for link in links:
            mapping_confidence, mapping_status = _resolve_mapping_confidence(
                db, link.evidence_kind, link.evidence_id
            )
            if mapping_status in BLOCKING_MAPPING_STATUSES:
                reasons.append(
                    {
                        "code": "blocking_mapping_status",
                        "message": f"supporting evidence has mapping_status={mapping_status}",
                    }
                )
            if mapping_confidence is not None:
                confidences.append(mapping_confidence)

        minimum_mapping_confidence = min(confidences) if confidences else None
        if (
            minimum_mapping_confidence is not None
            and minimum_mapping_confidence < MINIMUM_MAPPING_CONFIDENCE_THRESHOLD
        ):
            reasons.append(
                {
                    "code": "insufficient_mapping_confidence",
                    "message": (
                        f"minimum supporting mapping confidence {minimum_mapping_confidence} "
                        f"below threshold {MINIMUM_MAPPING_CONFIDENCE_THRESHOLD}"
                    ),
                }
            )

        source_node = db.get(CausalNode, hypothesis.source_node_id)
        target_node = db.get(CausalNode, hypothesis.target_node_id)
        precision = None
        if source_node is not None and target_node is not None:
            source_start, source_end, source_precision = _resolve_occurrence(db, source_node)
            target_start, _target_end, target_precision = _resolve_occurrence(db, target_node)
            if source_start is not None and target_start is not None:
                if hypothesis.proposed_edge_type in NON_OVERLAP_EDGE_TYPES:
                    boundary = source_end or source_start
                    if boundary > target_start:
                        reasons.append(
                            {
                                "code": "temporal_precedence_violation",
                                "message": "source occurrence does not precede target occurrence",
                            }
                        )
                precision = source_precision or target_precision
                if hypothesis.temporal_lag_seconds is not None and precision is not None:
                    precision_seconds = TEMPORAL_PRECISION_SECONDS.get(precision, 0)
                    if precision_seconds > hypothesis.temporal_lag_seconds:
                        reasons.append(
                            {
                                "code": "insufficient_temporal_precision",
                                "message": (
                                    f"precision {precision} cannot support a "
                                    f"{hypothesis.temporal_lag_seconds}s lag claim"
                                ),
                            }
                        )

        readiness = db.scalar(
            select(AnalyticalReadinessDecision)
            .where(AnalyticalReadinessDecision.organization_id == organization_id)
            .order_by(AnalyticalReadinessDecision.created_at.desc())
        )
        if readiness is not None and readiness.readiness_status == "blocked":
            reasons.append(
                {
                    "code": "readiness_blocked",
                    "message": "organization analytical readiness is blocked",
                }
            )

        hypothesis.minimum_supporting_mapping_confidence = minimum_mapping_confidence
        hypothesis.evaluated_temporal_precision = precision
        hypothesis.causal_evaluation_time = datetime.now(tz=hypothesis.created_at.tzinfo)

        if reasons:
            hypothesis.hard_gate_outcome = "blocked"
            hypothesis.hard_gate_failure_reasons = reasons
            if hypothesis.lifecycle_status not in {
                CausalHypothesisStatus.EVIDENCE_PENDING.value,
                CausalHypothesisStatus.UNDER_REVIEW.value,
            }:
                hypothesis.lifecycle_status = CausalHypothesisStatus.EVIDENCE_PENDING.value
            db.commit()
            db.refresh(hypothesis)
            return hypothesis

        method = db.get(CausalMethodDefinition, hypothesis.method_id)
        base_weight = method.default_confidence_weight if method is not None else Decimal("0.5")
        components: dict[str, object] = {
            "method_weight": str(base_weight),
            "minimum_mapping_confidence": (
                str(minimum_mapping_confidence) if minimum_mapping_confidence is not None else None
            ),
            "evidence_count": hypothesis.evidence_count,
            "contradiction_count": hypothesis.contradiction_count,
        }
        confidence = base_weight
        if minimum_mapping_confidence is not None:
            confidence = min(confidence, minimum_mapping_confidence)
        if hypothesis.contradiction_count:
            confidence = confidence / (1 + hypothesis.contradiction_count)

        hypothesis.hard_gate_outcome = "passed"
        hypothesis.hard_gate_failure_reasons = []
        hypothesis.confidence_score = confidence
        hypothesis.confidence_components = components
        hypothesis.method_code = method.method_code if method is not None else None
        hypothesis.method_version = method.method_version if method is not None else None
        hypothesis.confidence_interpretation = (
            f"Derived from method weight capped by minimum supporting mapping confidence; "
            f"{hypothesis.contradiction_count} contradicting evidence item(s) discount the result."
        )
        hypothesis.confidence_limitations = (
            "Deterministic heuristic combination, not a statistical causal-discovery estimate."
        )

        if hypothesis.proposed_edge_type in ASSOCIATION_ONLY_EDGE_TYPES:
            hypothesis.lifecycle_status = CausalHypothesisStatus.PROBABLE.value
        elif confidence >= PROBABLE_CONFIDENCE_THRESHOLD:
            hypothesis.lifecycle_status = CausalHypothesisStatus.UNDER_REVIEW.value
        else:
            hypothesis.lifecycle_status = CausalHypothesisStatus.EVIDENCE_PENDING.value

        db.commit()
        db.refresh(hypothesis)
        return hypothesis


class CausalReviewService:
    _RESULTING_STATUS = {
        "confirm": CausalHypothesisStatus.CONFIRMED.value,
        "probable": CausalHypothesisStatus.PROBABLE.value,
        "reject": CausalHypothesisStatus.REJECTED.value,
        "revoke": CausalHypothesisStatus.REVOKED.value,
    }

    def review(
        self,
        db: Session,
        organization_id: UUID,
        hypothesis_id: UUID,
        payload: CausalReviewCreate,
        actor: UUID,
    ) -> CausalReview:
        hypothesis = db.scalar(
            select(CausalHypothesis).where(
                CausalHypothesis.organization_id == organization_id,
                CausalHypothesis.id == hypothesis_id,
            )
        )
        if hypothesis is None:
            _fail("hypothesis_not_found", "causal hypothesis not found", status=404)
        prior_status = hypothesis.lifecycle_status
        if payload.decision == "revoke" and prior_status != CausalHypothesisStatus.CONFIRMED.value:
            _fail("invalid_transition", "only confirmed hypotheses can be revoked")
        if payload.decision != "defer":
            resulting_status = self._RESULTING_STATUS[payload.decision]
            hypothesis.lifecycle_status = resulting_status
        else:
            resulting_status = prior_status

        review = CausalReview(
            organization_id=organization_id,
            hypothesis_id=hypothesis_id,
            decision=payload.decision,
            reviewer_user_id=actor,
            notes=payload.notes,
            evidence_summary=payload.evidence_summary,
            limitations_acknowledged=payload.limitations_acknowledged,
            prior_lifecycle_status=prior_status,
            resulting_lifecycle_status=resulting_status,
        )
        db.add(review)
        try:
            db.flush()
            _audit(
                db,
                organization_id,
                "hypothesis_reviewed",
                "causal_hypothesis",
                hypothesis_id,
                "user",
                actor,
                f"Review decision={payload.decision}: {prior_status} -> {resulting_status}",
            )
            if (
                resulting_status
                in {
                    CausalHypothesisStatus.CONFIRMED.value,
                    CausalHypothesisStatus.PROBABLE.value,
                }
                and payload.decision != "defer"
            ):
                self._materialize_edge(db, hypothesis)
            db.commit()
        except IntegrityError:
            db.rollback()
            _fail(
                "association_cannot_confirm",
                "association-only edge types cannot reach confirmed status",
            )
        db.refresh(review)
        return review

    def _materialize_edge(self, db: Session, hypothesis: CausalHypothesis) -> CausalEdge:
        existing = db.scalar(
            select(CausalEdge).where(
                CausalEdge.organization_id == hypothesis.organization_id,
                CausalEdge.source_node_id == hypothesis.source_node_id,
                CausalEdge.target_node_id == hypothesis.target_node_id,
                CausalEdge.edge_type == hypothesis.proposed_edge_type,
            )
        )
        if existing is not None:
            existing.hypothesis_id = hypothesis.id
            existing.confidence_score = hypothesis.confidence_score
            existing.confidence_level = hypothesis.confidence_level
            existing.evidence_count = hypothesis.evidence_count
            existing.contradiction_count = hypothesis.contradiction_count
            return existing
        edge = CausalEdge(
            organization_id=hypothesis.organization_id,
            source_node_id=hypothesis.source_node_id,
            target_node_id=hypothesis.target_node_id,
            hypothesis_id=hypothesis.id,
            edge_type=hypothesis.proposed_edge_type,
            causal_role=hypothesis.causal_role,
            cause_category=hypothesis.cause_category,
            temporal_lag_seconds=hypothesis.temporal_lag_seconds,
            validity_from=hypothesis.validity_from,
            validity_to=hypothesis.validity_to,
            confidence_score=hypothesis.confidence_score,
            confidence_level=hypothesis.confidence_level,
            method_code=hypothesis.method_code,
            method_version=hypothesis.method_version,
            confidence_components=hypothesis.confidence_components,
            confidence_interpretation=hypothesis.confidence_interpretation,
            confidence_limitations=hypothesis.confidence_limitations,
            minimum_supporting_mapping_confidence=hypothesis.minimum_supporting_mapping_confidence,
            evidence_count=hypothesis.evidence_count,
            contradiction_count=hypothesis.contradiction_count,
        )
        db.add(edge)
        db.flush()
        return edge


class RootCauseRankingService:
    def traverse(
        self, db: Session, organization_id: UUID
    ) -> tuple[dict[UUID, list[CausalEdge]], dict[UUID, list[CausalEdge]]]:
        edges = list(
            db.scalars(
                select(CausalEdge)
                .join(CausalHypothesis, CausalEdge.hypothesis_id == CausalHypothesis.id)
                .where(
                    CausalEdge.organization_id == organization_id,
                    CausalHypothesis.lifecycle_status.in_(
                        [
                            CausalHypothesisStatus.CONFIRMED.value,
                            CausalHypothesisStatus.PROBABLE.value,
                        ]
                    ),
                )
            )
        )
        outgoing: dict[UUID, list[CausalEdge]] = {}
        incoming: dict[UUID, list[CausalEdge]] = {}
        for edge in edges:
            outgoing.setdefault(edge.source_node_id, []).append(edge)
            incoming.setdefault(edge.target_node_id, []).append(edge)
        return outgoing, incoming

    def detect_cycles(self, db: Session, organization_id: UUID) -> list[list[UUID]]:
        """Whole-graph DFS cycle check over confirmed/probable edges.

        A cycle anywhere in the organization's confirmed causal graph is a data-integrity
        alert regardless of which two nodes a specific chain query traverses between, so
        this is checked independently of find_paths (which only walks one root->terminal
        pair and would miss a cycle that lies off that particular path).
        """
        outgoing, _incoming = self.traverse(db, organization_id)
        visiting: set[UUID] = set()
        visited: set[UUID] = set()
        cycles: list[list[UUID]] = []

        def _dfs(node_id: UUID, stack: list[UUID]) -> None:
            if node_id in visiting:
                cycle_start = stack.index(node_id)
                cycles.append([*stack[cycle_start:], node_id])
                return
            if node_id in visited:
                return
            visiting.add(node_id)
            stack.append(node_id)
            for edge in outgoing.get(node_id, []):
                _dfs(edge.target_node_id, stack)
            stack.pop()
            visiting.discard(node_id)
            visited.add(node_id)

        for node_id in list(outgoing.keys()):
            if node_id not in visited:
                _dfs(node_id, [])
        return cycles

    def find_paths(
        self, db: Session, organization_id: UUID, root_node_id: UUID, terminal_node_id: UUID
    ) -> list[list[CausalEdge]]:
        if self.detect_cycles(db, organization_id):
            _fail("cycle_detected", "a cycle was detected among confirmed causal edges")
        outgoing, _incoming = self.traverse(db, organization_id)
        paths: list[list[CausalEdge]] = []

        def _walk(node_id: UUID, path: list[CausalEdge], visited: set[UUID]) -> None:
            if node_id == terminal_node_id and path:
                paths.append(list(path))
                return
            visited = visited | {node_id}
            for edge in outgoing.get(node_id, []):
                path.append(edge)
                _walk(edge.target_node_id, path, visited)
                path.pop()

        _walk(root_node_id, [], set())
        return paths

    def score_path(self, path: list[CausalEdge]) -> tuple[Decimal, Decimal | None]:
        score = Decimal("1")
        weakest: Decimal | None = None
        for edge in path:
            weight = edge.confidence_score if edge.confidence_score is not None else Decimal("0.5")
            score *= weight
            if weakest is None or weight < weakest:
                weakest = weight
        return score, weakest

    def compute_chain_version(
        self, db: Session, organization_id: UUID, chain: CausalChain
    ) -> CausalChainVersion:
        paths = self.find_paths(
            db, organization_id, chain.root_cause_node_id, chain.terminal_impact_node_id
        )
        best_path = max(paths, key=lambda path: self.score_path(path)[0]) if paths else []
        path_score, weakest = self.score_path(best_path) if best_path else (Decimal("0"), None)
        last_version = db.scalar(
            select(CausalChainVersion)
            .where(CausalChainVersion.chain_id == chain.id)
            .order_by(CausalChainVersion.version_number.desc())
        )
        next_version = (last_version.version_number + 1) if last_version else 1
        version = CausalChainVersion(
            organization_id=organization_id,
            chain_id=chain.id,
            version_number=next_version,
            edge_ids=[str(edge.id) for edge in best_path],
            path_score=path_score,
            weakest_link_confidence=weakest,
            occurrence_count=len(best_path),
        )
        db.add(version)
        db.commit()
        db.refresh(version)
        return version

    def rank_root_causes(
        self, db: Session, organization_id: UUID, limit: int = 20
    ) -> list[RootCauseRankingEntry]:
        chains = list(
            db.scalars(select(CausalChain).where(CausalChain.organization_id == organization_id))
        )
        entries: list[RootCauseRankingEntry] = []
        for chain in chains:
            version = db.scalar(
                select(CausalChainVersion)
                .where(CausalChainVersion.chain_id == chain.id)
                .order_by(CausalChainVersion.version_number.desc())
            )
            if version is None:
                continue
            intervention_coverage = (
                db.scalar(
                    select(CausalIntervention.id).where(
                        CausalIntervention.organization_id == organization_id,
                        CausalIntervention.targeted_node_id == chain.root_cause_node_id,
                    )
                )
                is not None
            )
            operational_total = None
            economic_total = None
            if version.operational_impact_summary:
                operational_total = version.operational_impact_summary.get("total")
            if version.economic_impact_summary:
                economic_total = version.economic_impact_summary.get("total")
            entries.append(
                RootCauseRankingEntry(
                    chain_id=chain.id,
                    chain_code=chain.chain_code,
                    root_cause_node_id=chain.root_cause_node_id,
                    terminal_impact_node_id=chain.terminal_impact_node_id,
                    path_score=version.path_score,
                    weakest_link_confidence=version.weakest_link_confidence,
                    occurrence_count=version.occurrence_count,
                    trend_direction=version.trend_direction,
                    total_economic_impact=economic_total,
                    total_operational_impact=operational_total,
                    intervention_coverage=intervention_coverage,
                )
            )
        entries.sort(key=lambda entry: entry.path_score, reverse=True)
        return entries[:limit]


class CausalChainService:
    def create(
        self,
        db: Session,
        organization_id: UUID,
        chain_code: str,
        root_cause_node_id: UUID,
        terminal_impact_node_id: UUID,
        industry_pack_code: str | None = None,
    ) -> CausalChain:
        existing = db.scalar(
            select(CausalChain).where(
                CausalChain.organization_id == organization_id,
                CausalChain.chain_code == chain_code,
            )
        )
        if existing is not None:
            return existing
        chain = CausalChain(
            organization_id=organization_id,
            chain_code=chain_code,
            root_cause_node_id=root_cause_node_id,
            terminal_impact_node_id=terminal_impact_node_id,
            industry_pack_code=industry_pack_code,
        )
        db.add(chain)
        db.commit()
        db.refresh(chain)
        return chain


class CausalInterventionService:
    def create(
        self,
        db: Session,
        organization_id: UUID,
        payload: CausalInterventionCreate,
        actor: UUID,
    ) -> CausalIntervention:
        if bool(payload.targeted_node_id) == bool(payload.targeted_edge_id):
            _fail(
                "invalid_target",
                "an intervention must target exactly one causal node or causal edge",
            )
        intervention = CausalIntervention(
            organization_id=organization_id,
            action_id=payload.action_id,
            targeted_node_id=payload.targeted_node_id,
            targeted_edge_id=payload.targeted_edge_id,
            expected_mechanism=payload.expected_mechanism,
            expected_causal_interruption=payload.expected_causal_interruption,
            created_by_user_id=actor,
        )
        db.add(intervention)
        db.flush()
        _audit(
            db,
            organization_id,
            "intervention_created",
            "causal_intervention",
            intervention.id,
            "user",
            actor,
            "Intervention linked to action",
        )
        db.commit()
        db.refresh(intervention)
        return intervention


class CausalOutcomeAssessmentService:
    def create(
        self,
        db: Session,
        organization_id: UUID,
        payload: CausalOutcomeAssessmentCreate,
        actor: UUID,
    ) -> CausalOutcomeAssessment:
        intervention = db.scalar(
            select(CausalIntervention).where(
                CausalIntervention.organization_id == organization_id,
                CausalIntervention.id == payload.intervention_id,
            )
        )
        if intervention is None:
            _fail("intervention_not_found", "causal intervention not found", status=404)
        assessment = CausalOutcomeAssessment(
            organization_id=organization_id,
            intervention_id=payload.intervention_id,
            action_outcome_id=payload.action_outcome_id,
            hypothesis_effect=payload.hypothesis_effect,
            chain_interrupted=payload.chain_interrupted,
            assessed_by_user_id=actor,
            notes=payload.notes,
            evidence_summary=payload.evidence_summary,
        )
        db.add(assessment)
        db.flush()
        self._feed_hypothesis_revision(db, organization_id, intervention, payload, actor)
        _audit(
            db,
            organization_id,
            "outcome_assessed",
            "causal_intervention",
            intervention.id,
            "user",
            actor,
            f"Outcome effect recorded: {payload.hypothesis_effect}",
        )
        db.commit()
        db.refresh(assessment)
        return assessment

    def _feed_hypothesis_revision(
        self,
        db: Session,
        organization_id: UUID,
        intervention: CausalIntervention,
        payload: CausalOutcomeAssessmentCreate,
        actor: UUID,
    ) -> None:
        if payload.hypothesis_effect not in {"weakened", "refuted"}:
            return
        if intervention.targeted_edge_id is None:
            return
        edge = db.get(CausalEdge, intervention.targeted_edge_id)
        if edge is None:
            return
        hypothesis = db.get(CausalHypothesis, edge.hypothesis_id)
        if (
            hypothesis is None
            or hypothesis.lifecycle_status != CausalHypothesisStatus.CONFIRMED.value
        ):
            return
        revision = CausalHypothesis(
            organization_id=organization_id,
            source_node_id=hypothesis.source_node_id,
            target_node_id=hypothesis.target_node_id,
            proposed_edge_type=hypothesis.proposed_edge_type,
            method_id=hypothesis.method_id,
            lifecycle_status=CausalHypothesisStatus.UNDER_REVIEW.value,
            causal_role=hypothesis.causal_role,
            cause_category=hypothesis.cause_category,
            temporal_lag_seconds=hypothesis.temporal_lag_seconds,
            hard_gate_failure_reasons=[],
            content_hash=_fingerprint(
                {
                    "source_node_id": str(hypothesis.source_node_id),
                    "target_node_id": str(hypothesis.target_node_id),
                    "proposed_edge_type": hypothesis.proposed_edge_type,
                    "method_id": str(hypothesis.method_id),
                    "revision_of": str(hypothesis.id),
                    "outcome_effect": payload.hypothesis_effect,
                }
            ),
            confidence_interpretation=(
                f"Reopened after outcome assessment reported {payload.hypothesis_effect} evidence "
                f"against hypothesis {hypothesis.id}."
            ),
            created_by_user_id=actor,
        )
        db.add(revision)
        db.flush()
        hypothesis.superseded_by_hypothesis_id = revision.id
        hypothesis.lifecycle_status = CausalHypothesisStatus.SUPERSEDED.value


causal_ontology_service = CausalOntologyService()
causal_node_service = CausalNodeService()
causal_hypothesis_service = CausalHypothesisService()
causal_evidence_service = CausalEvidenceService()
causal_evaluation_service = CausalEvaluationService()
causal_review_service = CausalReviewService()
causal_chain_service = CausalChainService()
root_cause_ranking_service = RootCauseRankingService()
causal_intervention_service = CausalInterventionService()
causal_outcome_assessment_service = CausalOutcomeAssessmentService()
