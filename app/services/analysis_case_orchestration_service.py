from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pandas as pd
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    # P3.xxE.3: type-hint-only usages. Kept out of the real (module-level,
    # ruff-isort-sorted) import block on purpose -- app.entities.entity_resolution
    # transitively imports app.semantic.candidate, which imports
    # app.models.entities; a plain top-of-file import here, sorted
    # alphabetically before the app.models.* block below, would re-trigger
    # a pre-existing circular-import ordering quirk in this codebase (only
    # a problem for the FIRST import in the chain to touch app.semantic.candidate
    # before app.models has fully initialized). PEP 563 (from __future__
    # import annotations` above) means annotations are never evaluated at
    # runtime, so TYPE_CHECKING-only is sufficient and always safe here;
    # the few call sites that need these at runtime import them locally
    # (see _run_case_level_entity_resolution / _run_case_level_relationship_discovery).
    from app.entities.entity_candidate import EntityCandidate
    from app.entities.entity_resolution import EntityResolutionOutcome
    from app.entities.relationship_candidate import RelationshipCandidate

from app.core.config import get_settings
from app.models.analysis_case import (
    AnalysisCase,
    AnalysisCaseDataset,
    AnalysisCaseEntityLink,
    AnalysisCaseFieldMapping,
    AnalysisCaseFinding,
    AnalysisCaseRun,
    AnalysisCaseRunStatus,
    AnalysisCaseStageEvent,
    AnalysisCaseStatus,
    DetectionStatus,
    EntityLinkStatus,
    MappingStatus,
    SourceArtifact,
    StageEventStatus,
)
from app.models.entities import utc_now
from app.models.entities_canonical import (
    CanonicalCaseEntity,
    CanonicalCaseRelationship,
    CanonicalEntityObservation,
)
from app.models.process_canonical import (
    CanonicalOperationalProcess,
    CanonicalProcessActivity,
    CanonicalProcessEdge,
)
from app.models.semantic import (
    SemanticDatasetProfile,
    SemanticInterpretationDecision,
    SemanticRoleInterpretation,
)
from app.schemas.trust import TrustAssessmentCreate
from app.semantic.candidate import InterpretationDecision, SemanticCandidate
from app.semantic.case_context import CaseSemanticContext
from app.semantic.concept_registry import default_canonical_concept_registry
from app.semantic.interpreter import interpret_dataset, profile_and_classify
from app.semantic.profiler import DatasetProfile, FieldProfile
from app.semantic.provider_factory import SemanticAIBudget, select_semantic_reasoning_provider
from app.semantic.role_classifier import DatasetRoleInterpretation
from app.services.analysis_case_intelligence_service import run_maintenance_pack
from app.services.analysis_case_mapping_service import analysis_case_mapping_service
from app.services.canonical_evidence_completeness import (
    CanonicalEvidenceCompletenessResult,
    RawFieldSemanticEvidence,
    evaluate_canonical_evidence_completeness,
)
from app.services.cross_domain_intelligence_service import (
    run_asset_failure_to_lost_activity,
    run_lost_activity_to_revenue_gap,
)
from app.services.entity_resolution_service import DatasetEntityInput, entity_resolution_service
from app.services.trust_service import trust_assessment_service
from app.storage.base import StorageBackend

# Minimal, conservative per-domain Trust rule configuration -- required-
# field-completeness on the domain's own key fields, plus one validity rule
# so the ARITHMETIC readiness level (needed for governed finding
# publication) can actually reach READY rather than being blocked on an
# unassessed dimension. This is intentionally generic/config-driven, not
# per-industry hard-coded logic.
_DOMAIN_TRUST_RULES: dict[str, dict[str, dict[str, object]]] = {
    "maintenance": {
        "required_field_completeness": {
            "required_fields": ["asset_id", "failure_code", "downtime_hours"]
        },
        "numeric_range_validity": {
            "numeric_ranges": {"downtime_hours": {"minimum": 0, "maximum": 100000}}
        },
    },
    "operations": {
        "required_field_completeness": {"required_fields": ["operational_event_id", "asset_id"]},
        "date_timestamp_validity": {"date_fields": ["event_date"]},
    },
    "revenue": {
        "required_field_completeness": {"required_fields": ["transaction_amount"]},
        "numeric_range_validity": {
            "numeric_ranges": {"transaction_amount": {"minimum": 0, "maximum": 1_000_000_000}}
        },
    },
}

# The only domains any wired intelligence path actually consumes (see
# run_maintenance_pack / run_asset_failure_to_lost_activity /
# run_lost_activity_to_revenue_gap below, all keyed on these same three
# domain strings). An uncertain (NEEDS_REVIEW) classification into a
# domain outside this set has no intelligence path to block, so it must
# not force the run into review_required -- reused, not duplicated, from
# _DOMAIN_TRUST_RULES's own key set.
_INTELLIGENCE_RELEVANT_DOMAINS = frozenset(_DOMAIN_TRUST_RULES.keys())


def _required_canonical_fields(domain: str) -> frozenset[str]:
    """Typed accessor for _DOMAIN_TRUST_RULES[domain]["required_field_completeness"]
    ["required_fields"] -- reuses the SAME single declared list Trust's own
    RawFieldCompletenessRule already runs against (never a second, drifting
    copy), just read with a concrete type for
    _evaluate_canonical_evidence_completeness's callers."""
    raw = _DOMAIN_TRUST_RULES[domain]["required_field_completeness"]["required_fields"]
    assert isinstance(raw, list)
    return frozenset(str(item) for item in raw)


# P3.xxE.5 Phase 2: rule codes promoted to GOVERNED activation authority --
# an explicit, reviewed rollout list, exactly like _INTELLIGENCE_RELEVANT_DOMAINS
# above. This is an ORCHESTRATION-level rollout decision, never a branch
# inside the generic readiness evaluator itself (evaluate_readiness() stays
# rule-code-agnostic -- see tests/test_capability_architecture_guardrails.py's
# AST guardrail). XDOM-B was promoted first because its corrected corpus-wide
# shadow certification exercised BOTH outcomes live (READY on
# FIELDMAINT-001/002/003, BLOCKED on the rest) with 22/22 legacy agreement.
# XDOM-A is promoted here on the strength of a dedicated positive-path
# certification fixture (its READY path has never fired on the real 11-case
# corpus -- domain detection has never classified a dataset as 'maintenance'
# there -- so live corpus evidence alone could not prove it; see
# tests/test_capability_governed_activation_xdom_a.py for the controlled
# proof that governed READY, legacy activation, and finding equivalence all
# hold when the underlying evidence genuinely satisfies XDOM-A's real,
# unmodified capability contract).
_GOVERNED_RULE_CODES = frozenset(
    {"XDOM-A-ASSET-FAILURE-LOST-ACTIVITY", "XDOM-B-LOST-ACTIVITY-REVENUE-GAP"}
)


# ---------------------------------------------------------------------------
# P3.xxC.2E: review_required actionability. Two conditions set
# any_review_required (see execute() below):
#   1. A CONFIRMED-domain dataset whose mapping bridge still could not
#      resolve every required field (MAPPING_REVIEW_REQUIRED) -- kept as
#      a safety net; structurally unreachable in ordinary operation since
#      P3.xxC.2E now only enforces required fields once detection is
#      itself CONFIRMED (see analysis_case_mapping_service.apply).
#   2. A dataset whose domain detection is NEEDS_REVIEW (plausible but
#      unconfirmed evidence) in a domain that actually feeds a wired
#      intelligence path (DOMAIN_REVIEW_REQUIRED) -- this is the
#      corrected replacement for the old false-positive trigger, where a
#      dataset with only generic fields (e.g. asset_id alone) was
#      wrongly coerced into a specific domain and then flagged for
#      "missing" fields it was never plausibly going to have.
# review_reasons() reuses the exact same persisted signals
# (AnalysisCaseDataset.mapping_status / detection_status,
# AnalysisCaseFieldMapping rows), never a parallel issue subsystem. Only
# the review-reason codes the backend genuinely produces are represented
# -- new codes must come with a new any_review_required trigger in
# execute(), not be added speculatively here.
# ---------------------------------------------------------------------------
_REVIEW_TARGET_BY_CODE = {
    "MAPPING_REVIEW_REQUIRED": "mapping",
    "DOMAIN_REVIEW_REQUIRED": "sources",
}


@dataclass(frozen=True)
class ReviewReason:
    code: str
    stage: str
    review_target: str
    dataset_id: UUID
    source_label: str
    domain: str | None
    missing_fields: list[str]
    message: str


@dataclass(frozen=True)
class SemanticInterpretationOutcome:
    """P3.xxE.3: what _run_case_level_semantic_interpretation hands back
    for the new canonical_entity_resolution stage to consume in-memory,
    rather than re-querying SemanticInterpretationDecision rows from the
    DB -- avoids both a redundant round-trip and any drift between
    persisted and reasoned-about state. decisions_by_case_dataset is
    keyed by AnalysisCaseDataset.id (the persistence-relevant id), unlike
    case_context.profiles/roles which stay keyed by the underlying
    Dataset.id (str(case_dataset.dataset_id)) to match interpret_dataset's
    own existing convention."""

    case_context: CaseSemanticContext
    decisions_by_case_dataset: dict[UUID, list[InterpretationDecision]]


class AnalysisCaseOrchestrationError(ValueError):
    def __init__(self, message: str, *, code: str, status: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def _reload_canonical_dataframe(
    db: Session, storage: StorageBackend, case_dataset: AnalysisCaseDataset
) -> pd.DataFrame | None:
    """Deterministically resolves a logical dataset back to its persisted
    raw source (Amendment 1) -- re-reads the SourceArtifact's bytes and
    re-runs the same parser rather than persisting the dataframe itself."""
    from app.ingestion.parsers import default_parser_registry

    artifact = db.get(SourceArtifact, case_dataset.source_artifact_id)
    if artifact is None or artifact.parser_code is None:
        return None
    registry = default_parser_registry()
    parser = registry.select(artifact.mime_type, artifact.extension)
    if parser is None:
        return None
    raw_bytes = b"".join(storage.open_stream(artifact.storage_reference))
    result = parser.extract(raw_bytes, artifact.original_filename)
    for extracted in result.datasets:
        if extracted.label == case_dataset.source_label:
            return extracted.dataframe
    return None


def _field_profile_to_dict(profile: FieldProfile) -> dict[str, object]:
    return asdict(profile)


def _candidate_to_dict(candidate: SemanticCandidate) -> dict[str, object]:
    return {
        "candidate_concept": candidate.candidate_concept,
        "confidence": candidate.confidence,
        "candidate_rank": candidate.candidate_rank,
        "generated_by": candidate.generated_by,
        "evidence_components": [
            {
                "component_type": e.component_type,
                "weight": e.weight,
                "description": e.description,
            }
            for e in candidate.evidence_components
        ],
    }


class AnalysisCaseOrchestrationService:
    def _record_stage(
        self,
        db: Session,
        organization_id: UUID,
        analysis_case_id: UUID,
        run_id: UUID,
        stage: str,
        status: str,
        detail: dict[str, object] | None = None,
        source_artifact_id: UUID | None = None,
    ) -> None:
        db.add(
            AnalysisCaseStageEvent(
                organization_id=organization_id,
                analysis_case_id=analysis_case_id,
                run_id=run_id,
                stage=stage,
                source_artifact_id=source_artifact_id,
                status=status,
                detail=detail or {},
            )
        )
        db.commit()

    def _run_case_level_semantic_interpretation(
        self,
        db: Session,
        organization_id: UUID,
        analysis_case_id: UUID,
        run_id: UUID,
        case_datasets: list[AnalysisCaseDataset],
        raw_dfs: dict[UUID, pd.DataFrame],
    ) -> SemanticInterpretationOutcome:
        """P3.xxE.1/P3.xxE.2: two-pass, order-independent semantic
        interpretation across the whole case (app/semantic/). Read-only
        with respect to everything downstream -- results are persisted for
        Navigator inspection and future milestones, but mapping/Trust/
        Intelligence below never read these rows in this milestone.

        Pass 1 profiles + classifies every dataset (cheap, no AI, no
        persistence) into a CaseSemanticContext covering the whole case;
        Pass 2 interprets each dataset's fields using that FULL context
        (all datasets, not just earlier-processed ones), so cross-dataset
        evidence is identical regardless of case_datasets iteration order
        -- see app/semantic/case_context.py and
        app/semantic/cross_dataset_context.py.

        P3.xxE.3: returns a SemanticInterpretationOutcome carrying the
        CaseSemanticContext and every dataset's in-memory
        InterpretationDecision list, for the new canonical_entity_resolution
        stage to consume directly -- see SemanticInterpretationOutcome."""
        profiles: dict[str, DatasetProfile] = {}
        roles: dict[str, DatasetRoleInterpretation] = {}
        for case_dataset in case_datasets:
            raw_df = raw_dfs.get(case_dataset.id)
            if raw_df is None:
                continue
            dataset_key = str(case_dataset.dataset_id)
            profile, role = profile_and_classify(case_dataset.source_label, raw_df)
            profiles[dataset_key] = profile
            roles[dataset_key] = role
        case_context = CaseSemanticContext(profiles=profiles, roles=roles)

        settings = get_settings()
        provider = select_semantic_reasoning_provider(settings)
        budget = SemanticAIBudget(max_calls=settings.semantic_ai_max_calls_per_case)

        datasets_interpreted = 0
        fields_interpreted = 0
        auto_accepted = 0
        review_required = 0
        unresolved = 0
        decisions_by_case_dataset: dict[UUID, list[InterpretationDecision]] = {}

        for case_dataset in case_datasets:
            raw_df = raw_dfs.get(case_dataset.id)
            if raw_df is None:
                continue
            result = interpret_dataset(
                str(case_dataset.dataset_id),
                case_dataset.source_label,
                raw_df,
                provider=provider,
                case_context=case_context,
                budget=budget,
            )

            db.add(
                SemanticDatasetProfile(
                    organization_id=organization_id,
                    analysis_case_dataset_id=case_dataset.id,
                    run_id=run_id,
                    dataset_label=result.dataset_profile.dataset_label,
                    row_count=result.dataset_profile.row_count,
                    column_count=result.dataset_profile.column_count,
                    field_profiles=[
                        _field_profile_to_dict(fp) for fp in result.dataset_profile.fields
                    ],
                )
            )
            db.add(
                SemanticRoleInterpretation(
                    organization_id=organization_id,
                    analysis_case_dataset_id=case_dataset.id,
                    run_id=run_id,
                    primary_role=result.role_interpretation.primary_role,
                    confidence=result.role_interpretation.confidence,
                    evidence=result.role_interpretation.evidence,
                    secondary_roles=result.role_interpretation.secondary_roles,
                    alternative_roles=[
                        {"role": s.role, "confidence": s.confidence, "evidence": s.evidence}
                        for s in result.role_interpretation.alternative_roles
                    ],
                )
            )
            for decision in result.field_decisions:
                db.add(
                    SemanticInterpretationDecision(
                        organization_id=organization_id,
                        analysis_case_dataset_id=case_dataset.id,
                        run_id=run_id,
                        source_field=decision.source_field,
                        selected_concept=decision.selected_concept,
                        confidence=decision.confidence,
                        status=decision.status,
                        evidence_summary=decision.evidence_summary,
                        alternative_candidates=[
                            _candidate_to_dict(c) for c in decision.alternative_candidates
                        ],
                        decision_source=decision.decision_source,
                        decision_version=decision.decision_version,
                        ai_provenance=decision.ai_provenance,
                    )
                )
            db.commit()

            decisions_by_case_dataset[case_dataset.id] = result.field_decisions

            datasets_interpreted += 1
            fields_interpreted += len(result.field_decisions)
            auto_accepted += sum(1 for d in result.field_decisions if d.status == "auto_accepted")
            review_required += sum(
                1 for d in result.field_decisions if d.status == "review_required"
            )
            unresolved += sum(1 for d in result.field_decisions if d.status == "unresolved")

        self._record_stage(
            db,
            organization_id,
            analysis_case_id,
            run_id,
            "semantic_interpretation",
            StageEventStatus.COMPLETED.value,
            {
                "datasets_interpreted": datasets_interpreted,
                "fields_interpreted": fields_interpreted,
                "auto_accepted": auto_accepted,
                "review_required": review_required,
                "unresolved": unresolved,
                "provider": provider.provider_name,
                "ai_budget_max_calls": budget.max_calls,
                "ai_calls_made": budget.calls_made,
                "ai_budget_exhausted": budget.calls_made >= budget.max_calls
                and settings.semantic_ai_enabled,
            },
        )

        return SemanticInterpretationOutcome(
            case_context=case_context, decisions_by_case_dataset=decisions_by_case_dataset
        )

    def _run_case_level_entity_resolution(
        self,
        db: Session,
        organization_id: UUID,
        analysis_case_id: UUID,
        run_id: UUID,
        case_datasets: list[AnalysisCaseDataset],
        raw_dfs: dict[UUID, pd.DataFrame],
        semantic_outcome: SemanticInterpretationOutcome,
    ) -> tuple[dict[tuple[str, str], UUID], list[EntityCandidate]]:
        """P3.xxE.3: consumes P3.xxE.1A EFFECTIVE semantic decisions
        (never raw field names) to resolve entities within this run only
        -- see app/entities/entity_resolution.py. Returns a
        (entity_type, canonical_key) -> CanonicalCaseEntity.id lookup plus the
        resolved EntityCandidate list itself, both needed by the
        relationship-discovery stage that follows. Stage failure never
        fails the run, mirroring semantic_interpretation's own blanket
        try/except (see execute())."""
        from app.entities.entity_resolution import CaseDatasetEntityInput, resolve_entities_for_case
        from app.entities.entity_type import observation_value_fields
        from app.entities.identifier_normalization import NORMALIZATION_POLICY_VERSION

        dataset_inputs = [
            CaseDatasetEntityInput(
                analysis_case_dataset_id=str(case_dataset.id),
                dataset_label=case_dataset.source_label,
                decisions=semantic_outcome.decisions_by_case_dataset.get(case_dataset.id, []),
                raw_dataframe=raw_dfs[case_dataset.id],
            )
            for case_dataset in case_datasets
            if case_dataset.id in raw_dfs
        ]
        outcome: EntityResolutionOutcome = resolve_entities_for_case(
            dataset_inputs, default_canonical_concept_registry
        )

        entity_ids: dict[tuple[str, str], UUID] = {}
        for candidate in outcome.candidates:
            raw_value, raw_value_hash = observation_value_fields(
                candidate.entity_type, candidate.display_label
            )
            entity_row = CanonicalCaseEntity(
                organization_id=organization_id,
                analysis_case_id=analysis_case_id,
                run_id=run_id,
                entity_type=candidate.entity_type,
                canonical_key=candidate.normalized_key,
                display_label=raw_value or "[redacted]",
                entity_type_confidence=candidate.entity_type_confidence,
                entity_identity_confidence=candidate.entity_identity_confidence,
                resolution_method=candidate.resolution_method,
                evidence_summary=candidate.evidence_summary,
                resolution_policy_version=NORMALIZATION_POLICY_VERSION,
            )
            db.add(entity_row)
            db.flush()
            entity_ids[(candidate.entity_type, candidate.normalized_key)] = entity_row.id

            for obs in candidate.observations:
                obs_raw_value, obs_raw_value_hash = observation_value_fields(
                    obs.entity_type, obs.raw_value
                )
                db.add(
                    CanonicalEntityObservation(
                        organization_id=organization_id,
                        canonical_entity_id=entity_row.id,
                        analysis_case_dataset_id=UUID(obs.analysis_case_dataset_id),
                        source_field=obs.source_field,
                        concept_code=obs.concept_code,
                        raw_value=obs_raw_value,
                        raw_value_hash=obs_raw_value_hash,
                        normalized_value=obs.normalized_value,
                        semantic_confidence=obs.semantic_confidence,
                        semantic_source=obs.semantic_source,
                        human_validated=obs.human_validated,
                    )
                )
        db.commit()

        self._record_stage(
            db,
            organization_id,
            analysis_case_id,
            run_id,
            "canonical_entity_resolution",
            StageEventStatus.COMPLETED.value,
            {
                "fields_considered": outcome.fields_considered,
                "fields_typed": outcome.fields_typed,
                "entities_resolved": len(outcome.candidates),
                "fuzzy_candidate_scores": len(outcome.fuzzy_scores),
            },
        )
        return entity_ids, outcome.candidates

    def _run_case_level_relationship_discovery(
        self,
        db: Session,
        organization_id: UUID,
        analysis_case_id: UUID,
        run_id: UUID,
        entity_candidates: list[EntityCandidate],
        entity_ids: dict[tuple[str, str], UUID],
        raw_dfs_by_case_dataset: dict[UUID, pd.DataFrame],
    ) -> list[RelationshipCandidate]:
        """P3.xxE.3: discovers structural/operational relationships
        between this run's resolved entities -- see
        app/entities/relationship_discovery.py. Stage failure never fails
        the run.

        P3.xxE.4: returns the in-memory RelationshipCandidate list (mirrors
        _run_case_level_entity_resolution's own entity_candidates return)
        so the process_interpretation stage that follows can consume it
        directly, avoiding a redundant DB round-trip -- the same
        established philosophy already used for semantic_outcome and
        entity resolution."""
        from app.entities.confidence_decomposition import RELATIONSHIP_POLICY_VERSION
        from app.entities.relationship_discovery import discover_relationships_for_case

        raw_dfs_by_str = {str(cd_id): df for cd_id, df in raw_dfs_by_case_dataset.items()}
        relationship_candidates = discover_relationships_for_case(entity_candidates, raw_dfs_by_str)

        persisted = 0
        for candidate in relationship_candidates:
            left_id = entity_ids.get((candidate.left_entity_type, candidate.left_normalized_key))
            right_id = entity_ids.get((candidate.right_entity_type, candidate.right_normalized_key))
            if left_id is None or right_id is None or left_id == right_id:
                continue
            db.add(
                CanonicalCaseRelationship(
                    organization_id=organization_id,
                    analysis_case_id=analysis_case_id,
                    run_id=run_id,
                    left_entity_id=left_id,
                    right_entity_id=right_id,
                    relationship_type=candidate.relationship_type,
                    cardinality=candidate.cardinality,
                    left_entity_identity_confidence=candidate.confidence.left_entity_identity_confidence,
                    right_entity_identity_confidence=candidate.confidence.right_entity_identity_confidence,
                    structural_evidence_confidence=candidate.confidence.structural_evidence_confidence,
                    relationship_confidence=candidate.confidence.relationship_confidence,
                    status=candidate.status,
                    evidence_summary=candidate.evidence_summary,
                    conflict_reason=candidate.conflict_reason,
                    relationship_policy_version=RELATIONSHIP_POLICY_VERSION,
                )
            )
            persisted += 1
        db.commit()

        self._record_stage(
            db,
            organization_id,
            analysis_case_id,
            run_id,
            "relationship_discovery",
            StageEventStatus.COMPLETED.value,
            {
                "relationship_candidates": len(relationship_candidates),
                "relationships_persisted": persisted,
            },
        )
        return relationship_candidates

    def _run_case_level_process_interpretation(
        self,
        db: Session,
        organization_id: UUID,
        analysis_case_id: UUID,
        run_id: UUID,
        case_datasets: list[AnalysisCaseDataset],
        raw_dfs: dict[UUID, pd.DataFrame],
        semantic_outcome: SemanticInterpretationOutcome,
        entity_candidates: list[EntityCandidate],
        entity_ids: dict[tuple[str, str], UUID],
    ) -> None:
        """P3.xxE.4: interprets operational process structure (activities,
        precedence/state-transition edges) from this run's already-resolved
        canonical entities -- see app/process/process_interpretation.py.
        Consumes the FULL 5-tier semantic evidence hierarchy for
        TIMESTAMP/STATUS concepts (plan review correction 1) -- deliberately
        NOT gated through resolve_effective_decision the way E.3's entity
        typing is, since that resolver collapses accepted_with_flag into
        the same "review_required" bucket process interpretation must keep
        distinct. Reads E.3's CanonicalCaseEntity identity read-only, never
        rewrites it (Invariant N). Stage failure never fails the run,
        mirroring semantic_interpretation/canonical_entity_resolution's own
        blanket try/except (see execute()).

        E.3's discovered CanonicalCaseRelationship rows are threaded
        in-memory to this stage (via the caller's relationship_candidates,
        avoiding a redundant DB round-trip) but are not yet consumed here:
        this milestone's process instances are anchor-entity-scoped (every
        activity in one instance shares the same primary entity), so
        E.3's relationship-support corroboration gate
        (app/process/process_relationship_support.py, spec section 15) has
        no structurally-applicable cross-entity edge to corroborate against
        until a future milestone attaches multi-entity participation --
        the module ships fully tested and ready for that, deliberately not
        wired into a case where it cannot yet do anything real (given the
        real-corpus baseline: zero CanonicalCaseRelationship rows
        corpus-wide)."""
        from app.process.process_interpretation import (
            ACTIVITY_POLICY_VERSION,
            EDGE_POLICY_VERSION,
            PROCESS_POLICY_VERSION,
            CaseDatasetProcessInput,
            interpret_process_for_case,
        )

        def _dataset_role(case_dataset: AnalysisCaseDataset) -> str:
            role = semantic_outcome.case_context.roles.get(str(case_dataset.dataset_id))
            return role.primary_role if role is not None else "unknown"

        dataset_inputs = [
            CaseDatasetProcessInput(
                analysis_case_dataset_id=str(case_dataset.id),
                dataset_label=case_dataset.source_label,
                dataset_role=_dataset_role(case_dataset),
                decisions=semantic_outcome.decisions_by_case_dataset.get(case_dataset.id, []),
                raw_dataframe=raw_dfs[case_dataset.id],
            )
            for case_dataset in case_datasets
            if case_dataset.id in raw_dfs
        ]

        outcome = interpret_process_for_case(dataset_inputs, entity_candidates)

        processes_persisted = 0
        activities_persisted = 0
        edges_persisted = 0

        for instance in outcome.process_instances:
            anchor_entity_db_id = None
            if instance.anchor_entity_type is not None and instance.anchor_entity_id is not None:
                anchor_entity_db_id = entity_ids.get(
                    (instance.anchor_entity_type, instance.anchor_entity_id)
                )
            process_row = CanonicalOperationalProcess(
                organization_id=organization_id,
                analysis_case_id=analysis_case_id,
                run_id=run_id,
                anchor_entity_id=anchor_entity_db_id,
                anchor_entity_type=instance.anchor_entity_type,
                anchor_confidence=instance.anchor_confidence,
                process_type=instance.process_type,
                process_label=instance.process_label,
                process_family=instance.process_family,
                process_family_confidence=0.0,
                boundary_status=instance.boundary_status,
                status=instance.status,
                coverage_confidence=instance.coverage_confidence,
                activity_confidence=instance.activity_confidence,
                entity_participation_confidence=instance.entity_participation_confidence,
                temporal_confidence=instance.temporal_confidence,
                precedence_consistency_confidence=instance.precedence_consistency_confidence,
                state_transition_confidence=instance.state_transition_confidence,
                overall_confidence=instance.overall_confidence,
                activity_count=len(instance.activities),
                edge_count=len(instance.edges),
                evidence_summary=instance.evidence_summary,
                conflict_reason=instance.conflict_reason,
                process_policy_version=PROCESS_POLICY_VERSION,
            )
            db.add(process_row)
            db.flush()
            processes_persisted += 1

            activity_db_ids: list[UUID] = []
            for activity in instance.activities:
                primary_entity_db_id = None
                if (
                    activity.primary_entity_type is not None
                    and activity.primary_entity_id is not None
                ):
                    primary_entity_db_id = entity_ids.get(
                        (activity.primary_entity_type, activity.primary_entity_id)
                    )
                activity_row = CanonicalProcessActivity(
                    organization_id=organization_id,
                    process_id=process_row.id,
                    activity_type=activity.activity_type,
                    activity_label=activity.activity_label,
                    state_value=activity.state_value,
                    primary_entity_id=primary_entity_db_id,
                    activity_type_confidence=activity.activity_type_confidence,
                    activity_existence_confidence=activity.activity_existence_confidence,
                    temporal_confidence=activity.temporal_confidence,
                    participation_confidence=activity.participation_confidence,
                    activity_confidence=activity.activity_confidence,
                    state_existence_confidence=activity.state_existence_confidence,
                    state_meaning_confidence=activity.state_meaning_confidence,
                    temporal_evidence_tier=activity.temporal_evidence_tier,
                    occurred_at=activity.occurred_at,
                    occurred_at_precision=activity.occurred_at_precision,
                    timezone_source=activity.timezone_source,
                    is_explicit_event=activity.is_explicit_event,
                    corroboration_signals=activity.corroboration_signals,
                    alternative_activity_types=activity.alternative_activity_types,
                    participation=[],
                    source_refs=[
                        {
                            "analysis_case_dataset_id": obs.analysis_case_dataset_id,
                            "source_field": obs.source_field,
                            "concept_code": obs.concept_code,
                        }
                        for obs in activity.observations
                    ],
                    evidence_summary=activity.evidence_summary,
                    activity_policy_version=ACTIVITY_POLICY_VERSION,
                )
                db.add(activity_row)
                db.flush()
                activity_db_ids.append(activity_row.id)
                activities_persisted += 1

            for edge in instance.edges:
                if edge.left_index >= len(activity_db_ids) or edge.right_index >= len(
                    activity_db_ids
                ):
                    continue
                from_id = activity_db_ids[edge.left_index]
                to_id = activity_db_ids[edge.right_index]
                if from_id == to_id:
                    continue
                db.add(
                    CanonicalProcessEdge(
                        organization_id=organization_id,
                        process_id=process_row.id,
                        from_activity_id=from_id,
                        to_activity_id=to_id,
                        edge_type=edge.edge_type,
                        from_state=edge.from_state,
                        to_state=edge.to_state,
                        support_count=edge.support_count,
                        a_before_b_count=edge.a_before_b_count,
                        b_before_a_count=edge.b_before_a_count,
                        same_time_count=edge.same_time_count,
                        unknown_order_count=edge.unknown_order_count,
                        observation_count=edge.observation_count,
                        temporal_evidence_tier=edge.temporal_evidence_tier,
                        semantic_confidence=edge.semantic_confidence,
                        entity_participation_confidence=edge.entity_participation_confidence,
                        temporal_confidence=edge.temporal_confidence,
                        repetition_confidence=edge.repetition_confidence,
                        consistency_confidence=edge.consistency_confidence,
                        conflict_penalty=edge.conflict_penalty,
                        precedence_confidence=edge.precedence_confidence,
                        contradiction_count=edge.contradiction_count,
                        status=edge.status,
                        evidence_summary=edge.evidence_summary,
                        conflict_reason=edge.conflict_reason,
                        edge_policy_version=EDGE_POLICY_VERSION,
                    )
                )
                edges_persisted += 1
        db.commit()

        self._record_stage(
            db,
            organization_id,
            analysis_case_id,
            run_id,
            "process_interpretation",
            StageEventStatus.COMPLETED.value,
            {
                "activities_discovered": outcome.activities_discovered,
                "entity_types_considered": outcome.entity_types_considered,
                "processes_persisted": processes_persisted,
                "activities_persisted": activities_persisted,
                "edges_persisted": edges_persisted,
            },
        )

    def _evaluate_canonical_evidence_completeness(
        self,
        db: Session,
        organization_id: UUID,
        run_id: UUID,
        case_dataset: AnalysisCaseDataset,
        required_canonical_fields: frozenset[str],
    ) -> CanonicalEvidenceCompletenessResult:
        """P3.xxV.2D: the POST-SEMANTIC, POST-MAPPING evidence-completeness
        check governed finding publication needs -- distinct from, and never
        a replacement for, Trust's own early RawFieldCompletenessRule (see
        app/services/canonical_evidence_completeness.py's module docstring
        for the full rationale). Adapts the two persisted representations
        that already carry this information (AnalysisCaseFieldMapping:
        which raw field mapping resolved to which canonical concept;
        SemanticInterpretationDecision: that SAME raw field's own machine
        semantic authority) into the framework-free RawFieldSemanticEvidence
        shape, then delegates the actual authority judgment entirely to
        evaluate_canonical_evidence_completeness -- no duplicate logic here."""
        mappings = list(
            db.scalars(
                select(AnalysisCaseFieldMapping).where(
                    AnalysisCaseFieldMapping.organization_id == organization_id,
                    AnalysisCaseFieldMapping.analysis_case_dataset_id == case_dataset.id,
                    AnalysisCaseFieldMapping.canonical_field.in_(required_canonical_fields),
                    AnalysisCaseFieldMapping.mapping_status == MappingStatus.AUTO_MAPPED.value,
                )
            ).all()
        )
        candidates: list[RawFieldSemanticEvidence] = []
        for mapping in mappings:
            decision = db.scalar(
                select(SemanticInterpretationDecision).where(
                    SemanticInterpretationDecision.organization_id == organization_id,
                    SemanticInterpretationDecision.analysis_case_dataset_id == case_dataset.id,
                    SemanticInterpretationDecision.run_id == run_id,
                    SemanticInterpretationDecision.source_field == mapping.source_field,
                )
            )
            if decision is None or mapping.canonical_field is None:
                continue
            candidates.append(
                RawFieldSemanticEvidence(
                    canonical_field=mapping.canonical_field,
                    source_field=mapping.source_field,
                    machine_status=decision.status,
                    machine_selected_concept=decision.selected_concept,
                    machine_confidence=decision.confidence,
                )
            )
        return evaluate_canonical_evidence_completeness(required_canonical_fields, candidates)

    def _evaluate_intelligence_capabilities(
        self,
        db: Session,
        organization_id: UUID,
        analysis_case_id: UUID,
        run_id: UUID,
        by_domain: dict[str, list[AnalysisCaseDataset]],
        trust_assessment_ids: dict[UUID, UUID],
        canonical_frames: dict[UUID, pd.DataFrame],
        semantic_outcome: SemanticInterpretationOutcome | None,
        raw_dfs_for_semantic: dict[UUID, pd.DataFrame],
    ) -> dict[str, str]:
        """P3.xxE.5 Phase 2: compares the pre-existing, hard-coded
        cross_domain_intelligence activation condition against the new
        generic registry/readiness evaluator for XDOM-A/XDOM-B, and persists
        one IntelligenceActivationDecision row per rule. Runs BEFORE any
        cross-domain execution decision below so its result can actually
        gate a GOVERNED rule (see _GOVERNED_RULE_CODES) -- for rules not yet
        promoted (XDOM-A), this remains a read-only SHADOW comparison and
        never influences what executes. Returns {rule_code: governed_status}
        so the caller can gate execution without re-deriving readiness.
        See app/intelligence_packs/shadow_comparison.py."""
        from app.intelligence_packs.registry import default_intelligence_pack_registry
        from app.intelligence_packs.shadow_comparison import compare_shadow
        from app.models.intelligence_activation import IntelligenceActivationDecision
        from app.semantic.concept_registry import default_canonical_concept_registry
        from app.services.case_capability_index_service import build_case_capability_index

        available_domains = frozenset(by_domain.keys())
        available_canonical_fields: set[str] = set()
        for datasets in by_domain.values():
            for cd in datasets:
                df = canonical_frames.get(cd.id)
                if df is not None:
                    available_canonical_fields.update(str(c) for c in df.columns)

        domains_with_resolved_trust = {
            domain
            for domain, datasets in by_domain.items()
            if any(trust_assessment_ids.get(cd.id) is not None for cd in datasets)
        }

        decisions_by_dataset = (
            semantic_outcome.decisions_by_case_dataset if semantic_outcome is not None else {}
        )

        index = build_case_capability_index(
            db,
            organization_id,
            analysis_case_id,
            run_id,
            available_domains=available_domains,
            available_canonical_fields=frozenset(available_canonical_fields),
            domains_with_resolved_trust=frozenset(domains_with_resolved_trust),
            decisions_by_dataset=decisions_by_dataset,
            raw_dataframes=raw_dfs_for_semantic,
            concept_registry=default_canonical_concept_registry,
        )

        migrated_rule_codes = {
            "XDOM-A-ASSET-FAILURE-LOST-ACTIVITY",
            "XDOM-B-LOST-ACTIVITY-REVENUE-GAP",
        }
        evaluated = 0
        agree_count = 0
        disagree_count = 0
        governed_status_by_rule: dict[str, str] = {}
        for pack in default_intelligence_pack_registry().all():
            if pack.rule_code not in migrated_rule_codes:
                continue
            result = compare_shadow(pack, index)
            governed_status_by_rule[pack.rule_code] = result.governed.status
            mode = "governed" if pack.rule_code in _GOVERNED_RULE_CODES else "shadow"
            missing_summary = [
                *(f"domain:{d}" for d in sorted(result.governed.missing_domains)),
                *(f"field:{f}" for f in sorted(result.governed.missing_fields)),
                *(f"legacy_entity:{e}" for e in sorted(result.governed.missing_entities)),
                *(
                    f"canonical_entity:{e}"
                    for e in sorted(result.governed.missing_canonical_entities)
                ),
                *(f"relationship:{r}" for r in sorted(result.governed.missing_relationships)),
                *(f"activity:{a}" for a in sorted(result.governed.missing_activities)),
                *(
                    f"sequence:{a}->{b}"
                    for a, b in sorted(result.governed.missing_activity_sequences)
                ),
                *(f"state:{s}" for s in sorted(result.governed.missing_states)),
                *(f"measure:{m}" for m in sorted(result.governed.missing_canonical_measures)),
                *(f"trust:{d}" for d in sorted(result.governed.missing_resolved_trust_domains)),
            ]
            db.add(
                IntelligenceActivationDecision(
                    organization_id=organization_id,
                    analysis_case_id=analysis_case_id,
                    run_id=run_id,
                    pack_code=pack.pack_code,
                    rule_code=pack.rule_code,
                    pack_version=pack.version,
                    activation_policy_version=pack.activation_policy_version,
                    mode=mode,
                    legacy_activated=result.legacy.activated,
                    legacy_reason=result.legacy.reason,
                    governed_status=result.governed.status,
                    governed_missing_summary=missing_summary,
                    governed_confidence_summary={
                        "below_confidence_threshold": sorted(
                            result.governed.below_confidence_threshold
                        ),
                        "currency_violation": result.governed.currency_violation,
                        "unit_violation": result.governed.unit_violation,
                    },
                    agree=result.agree,
                    evidence_summary=result.evidence_summary,
                )
            )
            evaluated += 1
            if result.agree:
                agree_count += 1
            else:
                disagree_count += 1
        db.commit()

        self._record_stage(
            db,
            organization_id,
            analysis_case_id,
            run_id,
            "capability_shadow_evaluation",
            StageEventStatus.COMPLETED.value,
            {
                "packs_evaluated": evaluated,
                "agree_count": agree_count,
                "disagree_count": disagree_count,
                "governed_rule_codes": sorted(_GOVERNED_RULE_CODES),
            },
        )
        return governed_status_by_rule

    def start_run(
        self, db: Session, organization_id: UUID, analysis_case_id: UUID, actor_user_id: UUID
    ) -> AnalysisCaseRun:
        case = db.scalar(
            select(AnalysisCase).where(
                AnalysisCase.id == analysis_case_id, AnalysisCase.organization_id == organization_id
            )
        )
        if case is None:
            raise AnalysisCaseOrchestrationError(
                "Case not found", code="case_not_found", status=404
            )
        existing_running = db.scalar(
            select(AnalysisCaseRun).where(
                AnalysisCaseRun.analysis_case_id == analysis_case_id,
                AnalysisCaseRun.status == AnalysisCaseRunStatus.RUNNING.value,
            )
        )
        if existing_running is not None:
            raise AnalysisCaseOrchestrationError(
                "A run is already in progress for this case",
                code="run_already_in_progress",
                status=409,
            )
        last_run_number = db.scalar(
            select(AnalysisCaseRun.run_number)
            .where(AnalysisCaseRun.analysis_case_id == analysis_case_id)
            .order_by(AnalysisCaseRun.run_number.desc())
            .limit(1)
        )
        run = AnalysisCaseRun(
            organization_id=organization_id,
            analysis_case_id=analysis_case_id,
            run_number=(last_run_number or 0) + 1,
            status=AnalysisCaseRunStatus.CREATED.value,
            created_by_user_id=actor_user_id,
        )
        db.add(run)
        case.status = AnalysisCaseStatus.RUNNING.value
        db.add(case)
        db.commit()
        db.refresh(run)
        return run

    def execute(
        self,
        db: Session,
        storage: StorageBackend,
        organization_id: UUID,
        analysis_case_id: UUID,
        run_id: UUID,
        actor_user_id: UUID,
    ) -> None:
        """The actual pipeline -- called from a FastAPI BackgroundTasks
        callback after POST /run has already returned. Never silently
        drops a failed dataset: failures are recorded per-stage and the
        case ends partial/failed rather than completed if anything failed
        or needs review."""
        run = db.get(AnalysisCaseRun, run_id)
        case = db.get(AnalysisCase, analysis_case_id)
        if run is None or case is None:
            return
        run.status = AnalysisCaseRunStatus.RUNNING.value
        run.started_at = utc_now()
        run.execution_lease_id = uuid4()
        run.heartbeat_at = utc_now()
        db.add(run)
        db.commit()

        any_failure = False
        any_review_required = False

        case_datasets = list(
            db.scalars(
                select(AnalysisCaseDataset).where(
                    AnalysisCaseDataset.organization_id == organization_id,
                    AnalysisCaseDataset.analysis_case_id == analysis_case_id,
                )
            ).all()
        )

        canonical_frames: dict[UUID, pd.DataFrame] = {}
        raw_dfs_for_semantic: dict[UUID, pd.DataFrame] = {}
        trust_assessment_ids: dict[UUID, UUID] = {}

        # --- TRUST + MAPPING (per dataset) ---
        for case_dataset in case_datasets:
            raw_df = _reload_canonical_dataframe(db, storage, case_dataset)
            if raw_df is None:
                case_dataset.trust_status = "failed"
                case_dataset.mapping_status = "failed"
                db.add(case_dataset)
                db.commit()
                any_failure = True
                self._record_stage(
                    db,
                    organization_id,
                    analysis_case_id,
                    run_id,
                    "connect",
                    StageEventStatus.FAILED.value,
                    {"reason": "could not reload dataset from persisted source"},
                )
                continue

            # P3.xxE.2: cached here for the case-level semantic stage run
            # after this loop (see below) -- reuses the same already-
            # loaded dataframe rather than a second storage read.
            raw_dfs_for_semantic[case_dataset.id] = raw_df

            rule_config = _DOMAIN_TRUST_RULES.get(case_dataset.detected_domain or "", {})
            trust_status = "not_assessed"
            trust_assessment_id: UUID | None = None
            if rule_config:
                try:
                    assessment = trust_assessment_service.create_and_execute(
                        db,
                        organization_id,
                        case_dataset.dataset_id,
                        TrustAssessmentCreate(
                            records=raw_df.to_dict("records"), rule_configurations=rule_config
                        ),
                    )
                    trust_assessment_id = assessment.id
                    trust_status = assessment.status
                    trust_assessment_ids[case_dataset.id] = assessment.id
                    self._record_stage(
                        db,
                        organization_id,
                        analysis_case_id,
                        run_id,
                        "trust",
                        StageEventStatus.COMPLETED.value,
                        {
                            "dataset_id": str(case_dataset.dataset_id),
                            "overall_score": str(assessment.overall_score),
                        },
                    )
                except ValueError as exc:
                    trust_status = "failed"
                    any_failure = True
                    self._record_stage(
                        db,
                        organization_id,
                        analysis_case_id,
                        run_id,
                        "trust",
                        StageEventStatus.FAILED.value,
                        {"error": str(exc)},
                    )
            else:
                self._record_stage(
                    db,
                    organization_id,
                    analysis_case_id,
                    run_id,
                    "trust",
                    StageEventStatus.SKIPPED.value,
                    {"reason": f"no Trust rule config for domain {case_dataset.detected_domain!r}"},
                )

            case_dataset.trust_status = trust_status
            case_dataset.trust_assessment_id = trust_assessment_id

            mapping_result = analysis_case_mapping_service.apply(
                organization_id,
                case_dataset.id,
                raw_df,
                case_dataset.detected_domain,
                case_dataset.detection_status,
            )
            analysis_case_mapping_service.persist(db, case_dataset.id, mapping_result)
            case_dataset.mapping_status = mapping_result.overall_status
            if mapping_result.overall_status == "needs_review":
                # Kept as a safety net for a genuine mapping-level problem
                # on an already-CONFIRMED domain -- structurally distinct
                # from (and, since P3.xxC.2E, no longer triggered by) an
                # uncertain domain classification, which is handled below.
                any_review_required = True
            if (
                case_dataset.detection_status == DetectionStatus.NEEDS_REVIEW.value
                and case_dataset.detected_domain in _INTELLIGENCE_RELEVANT_DOMAINS
            ):
                # Only a domain that actually feeds a wired intelligence
                # path warrants operator review -- an uncertain guess in a
                # domain nothing downstream consumes has no path to block.
                any_review_required = True
            db.add(case_dataset)
            db.commit()

            canonical_frames[case_dataset.id] = mapping_result.canonical_dataframe
            self._record_stage(
                db,
                organization_id,
                analysis_case_id,
                run_id,
                "mapping",
                StageEventStatus.COMPLETED.value,
                {
                    "dataset_id": str(case_dataset.dataset_id),
                    "status": mapping_result.overall_status,
                },
            )

        # P3.xxE.1/P3.xxE.2: additive semantic interpretation, running
        # alongside (never replacing) the mapping bridge above -- see
        # app/semantic/__init__.py. Operates on the RAW dataframes (not
        # canonically mapped) since it interprets what the client's own
        # field names mean. Runs once per run, across the whole case, after
        # Trust/Mapping so it never affects that loop's behavior; never
        # blocking -- a semantic-layer failure is recorded and skipped,
        # never a run failure.
        semantic_outcome: SemanticInterpretationOutcome | None = None
        try:
            semantic_outcome = self._run_case_level_semantic_interpretation(
                db, organization_id, analysis_case_id, run_id, case_datasets, raw_dfs_for_semantic
            )
        except Exception as exc:  # noqa: BLE001 -- additive layer, must never fail the run
            self._record_stage(
                db,
                organization_id,
                analysis_case_id,
                run_id,
                "semantic_interpretation",
                StageEventStatus.FAILED.value,
                {"error": str(exc)},
            )

        # P3.xxE.3: additive canonical entity resolution + relationship
        # discovery, running alongside (never replacing) the legacy
        # exact-match entity_resolution stage below -- see the P3.xxE.3
        # plan's legacy cutover roadmap. Consumes EFFECTIVE semantic
        # decisions from the stage just above; skipped entirely (not
        # failed) if that stage itself didn't complete, since there is
        # nothing governed to resolve against.
        if semantic_outcome is not None:
            try:
                entity_ids, entity_candidates = self._run_case_level_entity_resolution(
                    db,
                    organization_id,
                    analysis_case_id,
                    run_id,
                    case_datasets,
                    raw_dfs_for_semantic,
                    semantic_outcome,
                )
            except Exception as exc:  # noqa: BLE001 -- additive layer, must never fail the run
                entity_ids, entity_candidates = {}, []
                self._record_stage(
                    db,
                    organization_id,
                    analysis_case_id,
                    run_id,
                    "canonical_entity_resolution",
                    StageEventStatus.FAILED.value,
                    {"error": str(exc)},
                )

            try:
                self._run_case_level_relationship_discovery(
                    db,
                    organization_id,
                    analysis_case_id,
                    run_id,
                    entity_candidates,
                    entity_ids,
                    raw_dfs_for_semantic,
                )
            except Exception as exc:  # noqa: BLE001 -- additive layer, must never fail the run
                self._record_stage(
                    db,
                    organization_id,
                    analysis_case_id,
                    run_id,
                    "relationship_discovery",
                    StageEventStatus.FAILED.value,
                    {"error": str(exc)},
                )

            # P3.xxE.4: additive process interpretation, running after
            # relationship_discovery -- see app/process/process_interpretation.py.
            # Runs whenever semantic_outcome completed, even if entity
            # resolution itself degraded to empty results above, so a
            # (possibly near-empty) UNKNOWN_PROCESS outcome is still
            # produced rather than silently skipped -- never fails the run.
            try:
                self._run_case_level_process_interpretation(
                    db,
                    organization_id,
                    analysis_case_id,
                    run_id,
                    case_datasets,
                    raw_dfs_for_semantic,
                    semantic_outcome,
                    entity_candidates,
                    entity_ids,
                )
            except Exception as exc:  # noqa: BLE001 -- additive layer, must never fail the run
                self._record_stage(
                    db,
                    organization_id,
                    analysis_case_id,
                    run_id,
                    "process_interpretation",
                    StageEventStatus.FAILED.value,
                    {"error": str(exc)},
                )
        else:
            self._record_stage(
                db,
                organization_id,
                analysis_case_id,
                run_id,
                "canonical_entity_resolution",
                StageEventStatus.SKIPPED.value,
                {"reason": "semantic_interpretation did not complete"},
            )
            self._record_stage(
                db,
                organization_id,
                analysis_case_id,
                run_id,
                "relationship_discovery",
                StageEventStatus.SKIPPED.value,
                {"reason": "semantic_interpretation did not complete"},
            )
            self._record_stage(
                db,
                organization_id,
                analysis_case_id,
                run_id,
                "process_interpretation",
                StageEventStatus.SKIPPED.value,
                {"reason": "semantic_interpretation did not complete"},
            )

        # --- ENTITY RESOLUTION (across all successfully mapped datasets) ---
        entity_inputs = [
            DatasetEntityInput(cd.id, cd.dataset_id, canonical_frames[cd.id])
            for cd in case_datasets
            if cd.id in canonical_frames
        ]
        links = entity_resolution_service.resolve(entity_inputs)
        db.execute(
            delete(AnalysisCaseEntityLink).where(
                AnalysisCaseEntityLink.analysis_case_id == analysis_case_id
            )
        )
        for link in links:
            link.organization_id = organization_id
            link.analysis_case_id = analysis_case_id
            db.add(link)
        db.commit()
        self._record_stage(
            db,
            organization_id,
            analysis_case_id,
            run_id,
            "entity_resolution",
            StageEventStatus.COMPLETED.value,
            {"link_count": len(links)},
        )
        matched_assets = {
            link.canonical_key
            for link in links
            if link.entity_type == "asset" and link.status == EntityLinkStatus.MATCHED.value
        }

        # --- DOMAIN INTELLIGENCE ---
        by_domain: dict[str, list[AnalysisCaseDataset]] = {}
        for cd in case_datasets:
            if cd.id in canonical_frames and cd.detected_domain:
                by_domain.setdefault(cd.detected_domain, []).append(cd)

        published_finding_ids: set[UUID] = set()
        for cd in by_domain.get("maintenance", []):
            trust_id = trust_assessment_ids.get(cd.id)
            if trust_id is None:
                continue
            try:
                findings = run_maintenance_pack(
                    db,
                    organization_id,
                    cd.dataset_id,
                    trust_id,
                    canonical_frames[cd.id],
                    actor_user_id,
                )
                for finding in findings:
                    published_finding_ids.add(finding.id)
                self._record_stage(
                    db,
                    organization_id,
                    analysis_case_id,
                    run_id,
                    "domain_intelligence",
                    StageEventStatus.COMPLETED.value,
                    {"pack": "MAINT", "finding_count": len(findings)},
                )
            except ValueError as exc:
                self._record_stage(
                    db,
                    organization_id,
                    analysis_case_id,
                    run_id,
                    "domain_intelligence",
                    StageEventStatus.FAILED.value,
                    {"pack": "MAINT", "error": str(exc)},
                )

        # --- CROSS-DOMAIN INTELLIGENCE ---
        maint_datasets = by_domain.get("maintenance", [])
        ops_datasets = by_domain.get("operations", [])
        revenue_datasets = by_domain.get("revenue", [])

        # P3.xxE.5 Phase 2: capability readiness is evaluated HERE, before
        # any cross-domain execution decision below, so a GOVERNED rule's
        # gate (see _GOVERNED_RULE_CODES) can actually use the result.
        # Failure-safe: any exception degrades to "no rule ready" -- never
        # silently falls back to running a governed rule -- and never fails
        # the run, matching this file's established additive-stage pattern.
        governed_status_by_rule: dict[str, str] = {}
        try:
            governed_status_by_rule = self._evaluate_intelligence_capabilities(
                db,
                organization_id,
                analysis_case_id,
                run_id,
                by_domain,
                trust_assessment_ids,
                canonical_frames,
                semantic_outcome,
                raw_dfs_for_semantic,
            )
        except Exception as exc:  # noqa: BLE001 -- safe default is NOT ACTIVATED, never fail the run
            self._record_stage(
                db,
                organization_id,
                analysis_case_id,
                run_id,
                "capability_shadow_evaluation",
                StageEventStatus.FAILED.value,
                {"error": str(exc)},
            )
        xdom_a_governed_ready = (
            governed_status_by_rule.get("XDOM-A-ASSET-FAILURE-LOST-ACTIVITY") == "READY"
        )
        xdom_b_governed_ready = (
            governed_status_by_rule.get("XDOM-B-LOST-ACTIVITY-REVENUE-GAP") == "READY"
        )

        # P3.xxE.5 Phase 2 (XDOM-A promotion): XDOM-A is GOVERNED -- same
        # gating shape as XDOM-B below. Proven via a dedicated positive-path
        # certification fixture (tests/test_capability_governed_activation_xdom_a.py)
        # since the real 11-case corpus has never produced a maintenance-domain
        # detection, and therefore never a READY case, for this rule.
        if xdom_a_governed_ready:
            for maint_cd in maint_datasets:
                trust_id = trust_assessment_ids.get(maint_cd.id)
                if trust_id is None:
                    continue
                maint_canonical_evidence = self._evaluate_canonical_evidence_completeness(
                    db,
                    organization_id,
                    run_id,
                    maint_cd,
                    _required_canonical_fields("maintenance"),
                )
                for ops_cd in ops_datasets:
                    findings = run_asset_failure_to_lost_activity(
                        db,
                        organization_id,
                        maint_cd.dataset_id,
                        canonical_frames[maint_cd.id],
                        ops_cd.dataset_id,
                        canonical_frames[ops_cd.id],
                        trust_id,
                        matched_assets,
                        actor_user_id,
                        canonical_evidence_completeness=maint_canonical_evidence,
                    )
                    for finding in findings:
                        published_finding_ids.add(finding.id)
                    self._record_stage(
                        db,
                        organization_id,
                        analysis_case_id,
                        run_id,
                        "cross_domain_intelligence",
                        StageEventStatus.COMPLETED.value,
                        {"rule": "XDOM-A", "finding_count": len(findings)},
                    )
        # P3.xxE.5 Phase 2: XDOM-B is GOVERNED -- the readiness evaluator
        # computed above is now the authority for whether this rule
        # executes at all, replacing the ad-hoc per-dataset trust check as
        # the entry gate. When not READY, XDOM-B does not execute and no
        # XDOM-B findings are emitted; the activation decision persisted by
        # _evaluate_intelligence_capabilities above already records why.
        if xdom_b_governed_ready:
            for ops_cd in ops_datasets:
                trust_id = trust_assessment_ids.get(ops_cd.id)
                if trust_id is None:
                    continue
                ops_canonical_evidence = self._evaluate_canonical_evidence_completeness(
                    db,
                    organization_id,
                    run_id,
                    ops_cd,
                    _required_canonical_fields("operations"),
                )
                for rev_cd in revenue_datasets:
                    findings = run_lost_activity_to_revenue_gap(
                        db,
                        organization_id,
                        ops_cd.dataset_id,
                        canonical_frames[ops_cd.id],
                        rev_cd.dataset_id,
                        canonical_frames[rev_cd.id],
                        trust_id,
                        actor_user_id,
                        canonical_evidence_completeness=ops_canonical_evidence,
                    )
                    for finding in findings:
                        published_finding_ids.add(finding.id)
                    self._record_stage(
                        db,
                        organization_id,
                        analysis_case_id,
                        run_id,
                        "cross_domain_intelligence",
                        StageEventStatus.COMPLETED.value,
                        {"rule": "XDOM-B", "finding_count": len(findings)},
                    )

        for finding_id in published_finding_ids:
            db.add(
                AnalysisCaseFinding(
                    organization_id=organization_id,
                    analysis_case_id=analysis_case_id,
                    run_id=run_id,
                    finding_id=finding_id,
                )
            )
        db.commit()

        run.completed_at = utc_now()
        run.heartbeat_at = utc_now()
        if any_failure:
            run.status = AnalysisCaseRunStatus.PARTIAL.value
            case.status = AnalysisCaseStatus.PARTIAL.value
        elif any_review_required:
            run.status = AnalysisCaseRunStatus.REVIEW_REQUIRED.value
            case.status = AnalysisCaseStatus.REVIEW_REQUIRED.value
        else:
            run.status = AnalysisCaseRunStatus.COMPLETED.value
            case.status = AnalysisCaseStatus.COMPLETED.value
        db.add(run)
        db.add(case)
        db.commit()
        self._record_stage(
            db,
            organization_id,
            analysis_case_id,
            run_id,
            "completion",
            StageEventStatus.COMPLETED.value,
            {"run_status": run.status, "findings_published": len(published_finding_ids)},
        )

    def review_reasons(
        self, db: Session, organization_id: UUID, analysis_case_id: UUID
    ) -> list[ReviewReason]:
        """Every AnalysisCaseDataset currently in mapping_status
        NEEDS_REVIEW, one reason per dataset, each carrying the exact
        missing canonical fields recorded by the mapping bridge. Dataset
        mapping_status reflects the case's most recent run (see
        analysis_case_mapping_service.persist's docstring: recomputed
        fresh on every run, never accumulated) -- the same latest-state
        semantics the existing /datasets endpoint already exposes, not a
        new inconsistency introduced here."""
        needs_review_datasets = list(
            db.scalars(
                select(AnalysisCaseDataset).where(
                    AnalysisCaseDataset.organization_id == organization_id,
                    AnalysisCaseDataset.analysis_case_id == analysis_case_id,
                    AnalysisCaseDataset.mapping_status == MappingStatus.NEEDS_REVIEW.value,
                )
            ).all()
        )
        reasons: list[ReviewReason] = []
        for case_dataset in needs_review_datasets:
            missing_fields = sorted(
                canonical_field
                for canonical_field in db.scalars(
                    select(AnalysisCaseFieldMapping.canonical_field).where(
                        AnalysisCaseFieldMapping.analysis_case_dataset_id == case_dataset.id,
                        AnalysisCaseFieldMapping.mapping_status
                        == MappingStatus.MISSING_REQUIRED_FIELD.value,
                    )
                ).all()
                if canonical_field is not None
            )
            domain_clause = (
                f"detected as {case_dataset.detected_domain!r}"
                if (case_dataset.detected_domain)
                else "detected domain could not be confirmed"
            )
            reasons.append(
                ReviewReason(
                    code="MAPPING_REVIEW_REQUIRED",
                    stage="mapping",
                    review_target=_REVIEW_TARGET_BY_CODE["MAPPING_REVIEW_REQUIRED"],
                    dataset_id=case_dataset.dataset_id,
                    source_label=case_dataset.source_label,
                    domain=case_dataset.detected_domain,
                    missing_fields=missing_fields,
                    message=(
                        f"Dataset {case_dataset.source_label!r} ({domain_clause}) is missing "
                        f"required field(s): {', '.join(missing_fields) or 'unknown'}."
                    ),
                )
            )

        # DOMAIN_REVIEW_REQUIRED: a NEEDS_REVIEW domain classification in a
        # domain a wired intelligence path actually consumes -- the exact
        # same condition execute() uses to set any_review_required, so
        # this list can never disagree with why the run actually ended
        # review_required.
        ambiguous_datasets = list(
            db.scalars(
                select(AnalysisCaseDataset).where(
                    AnalysisCaseDataset.organization_id == organization_id,
                    AnalysisCaseDataset.analysis_case_id == analysis_case_id,
                    AnalysisCaseDataset.detection_status == DetectionStatus.NEEDS_REVIEW.value,
                    AnalysisCaseDataset.detected_domain.in_(_INTELLIGENCE_RELEVANT_DOMAINS),
                )
            ).all()
        )
        for case_dataset in ambiguous_datasets:
            basis = ", ".join(case_dataset.detection_basis) or "no domain-specific fields"
            reasons.append(
                ReviewReason(
                    code="DOMAIN_REVIEW_REQUIRED",
                    stage="domain_detection",
                    review_target=_REVIEW_TARGET_BY_CODE["DOMAIN_REVIEW_REQUIRED"],
                    dataset_id=case_dataset.dataset_id,
                    source_label=case_dataset.source_label,
                    domain=case_dataset.detected_domain,
                    missing_fields=[],
                    message=(
                        f"Dataset {case_dataset.source_label!r} looks like it might be "
                        f"{case_dataset.detected_domain!r} (matched: {basis}) but not enough "
                        "domain-specific evidence was found to confirm it. Confirm or correct "
                        "the source classification before this dataset's intelligence can run."
                    ),
                )
            )
        return reasons

    def findings_availability(
        self,
        db: Session,
        organization_id: UUID,
        analysis_case_id: UUID,
        run_id: UUID,
        run_status: str,
        reasons: list[ReviewReason],
    ) -> tuple[bool, str | None]:
        """Makes explicit whether an empty findings list means 'nothing
        was found' vs. 'processing didn't get far enough to find
        anything' -- never leave Navigator inferring this itself."""
        finding_count = db.scalar(
            select(func.count())
            .select_from(AnalysisCaseFinding)
            .where(
                AnalysisCaseFinding.organization_id == organization_id,
                AnalysisCaseFinding.analysis_case_id == analysis_case_id,
                AnalysisCaseFinding.run_id == run_id,
            )
        )
        if finding_count:
            return True, None
        if run_status == AnalysisCaseRunStatus.REVIEW_REQUIRED.value and reasons:
            stages = sorted({reason.stage for reason in reasons})
            labels = sorted({reason.source_label for reason in reasons})
            return False, (
                f"Findings not produced because {', '.join(stages)} review is required "
                f"for {len(labels)} dataset(s): {', '.join(labels)}."
            )
        if run_status == AnalysisCaseRunStatus.PARTIAL.value:
            return False, (
                "Findings not produced because processing failed for one or more datasets."
            )
        return False, None

    def mark_stale_if_needed(
        self, db: Session, run: AnalysisCaseRun, stale_after_seconds: float
    ) -> bool:
        if run.status != AnalysisCaseRunStatus.RUNNING.value or run.heartbeat_at is None:
            return False
        elapsed = (utc_now() - run.heartbeat_at).total_seconds()
        if elapsed <= stale_after_seconds:
            return False
        run.status = AnalysisCaseRunStatus.INTERRUPTED.value
        run.error_summary = f"Heartbeat stale for {elapsed:.0f}s -- marked interrupted"
        db.add(run)
        db.commit()
        return True


analysis_case_orchestration_service = AnalysisCaseOrchestrationService()
