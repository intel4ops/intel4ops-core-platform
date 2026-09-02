from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.semantic.candidate import (
    EvidenceComponentType,
    InterpretationDecision,
    InterpretationEvidence,
    SemanticCandidate,
)
from app.semantic.candidate_generator import generate_candidates
from app.semantic.case_context import CaseSemanticContext
from app.semantic.concept_registry import (
    CanonicalConceptRegistry,
    default_canonical_concept_registry,
)
from app.semantic.confidence_engine import ConfidenceThresholds, reconcile
from app.semantic.cross_dataset_context import generate_cross_dataset_evidence
from app.semantic.neighbor_context import generate_neighbor_context_evidence
from app.semantic.profiler import DatasetProfile, DatasetProfiler, dataset_profiler
from app.semantic.provider import (
    FieldInterpretationContext,
    SemanticInterpretationRequest,
    SemanticInterpretationResponse,
    SemanticReasoningProvider,
    default_semantic_reasoning_provider,
)
from app.semantic.provider_factory import SemanticAIBudget
from app.semantic.role_classifier import (
    DatasetRoleClassifier,
    DatasetRoleInterpretation,
    dataset_role_classifier,
)
from app.semantic.sampling import representative_sample
from app.semantic.sibling_concept_corroboration import (
    generate_sibling_concept_corroboration_evidence,
)

# ---------------------------------------------------------------------------
# Section 14/30 item 14: the single orchestration-facing entry point.
# AnalysisCase orchestration (app/services/analysis_case_orchestration_
# service.py) calls interpret_dataset() once per registered dataset,
# additively alongside (never replacing) the existing mapping bridge --
# see the module docstring in app/semantic/__init__.py for the staged
# migration story. No branch here on a simulation identifier, industry, or
# specific client field name -- every domain-specific step is either
# generic profiling/classification or a CanonicalConceptRegistry lookup.
#
# P3.xxE.2: case_context (app/semantic/case_context.py) carries every
# dataset's Pass-1 profile/role for the whole case, built once before any
# dataset's field interpretation runs -- this is what makes cross-dataset
# evidence order-independent (see the orchestration service's two-pass
# semantic stage). A provider failure (timeout/malformed output/anything)
# is caught here, never propagated -- deterministic interpretation always
# completes regardless of AI availability.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DatasetInterpretationResult:
    dataset_profile: DatasetProfile
    role_interpretation: DatasetRoleInterpretation
    field_decisions: list[InterpretationDecision]


def profile_and_classify(
    dataset_label: str,
    dataframe: pd.DataFrame,
    *,
    profiler: DatasetProfiler | None = None,
    role_classifier: DatasetRoleClassifier | None = None,
) -> tuple[DatasetProfile, DatasetRoleInterpretation]:
    """Pass 1 of the two-pass semantic stage -- profiling + role
    classification only, no candidate generation, no AI call, no
    persistence. Exposed as a standalone function so orchestration can
    build a CaseSemanticContext covering every dataset in a case before
    any dataset's Pass 2 (field interpretation) begins."""
    profiler = profiler or dataset_profiler
    role_classifier = role_classifier or dataset_role_classifier
    profile = profiler.profile(dataset_label, dataframe)
    role = role_classifier.classify(profile)
    return profile, role


def _request_ai_proposals(
    provider: SemanticReasoningProvider,
    budget: SemanticAIBudget | None,
    dataset_label: str,
    role: DatasetRoleInterpretation,
    concept_registry: CanonicalConceptRegistry,
    field_contexts: list[FieldInterpretationContext],
) -> SemanticInterpretationResponse:
    """Never raises -- a provider failure or an exhausted budget both
    degrade to zero proposals (deterministic-only), matching
    NullSemanticReasoningProvider's own honest-default behavior."""
    if budget is not None and not budget.try_consume():
        return SemanticInterpretationResponse(
            proposals=[],
            provider_name=provider.provider_name,
            provider_version=provider.provider_version,
        )
    try:
        return provider.propose(
            SemanticInterpretationRequest(
                dataset_label=dataset_label,
                dataset_role_hint=role.primary_role,
                known_concept_codes=[c.concept_code for c in concept_registry.active()],
                fields=field_contexts,
            )
        )
    except Exception:  # noqa: BLE001 -- a provider failure must never block interpretation
        return SemanticInterpretationResponse(
            proposals=[],
            provider_name=provider.provider_name,
            provider_version=provider.provider_version,
        )


def interpret_dataset(
    dataset_id: str,
    dataset_label: str,
    dataframe: pd.DataFrame,
    *,
    profiler: DatasetProfiler | None = None,
    role_classifier: DatasetRoleClassifier | None = None,
    concept_registry: CanonicalConceptRegistry | None = None,
    provider: SemanticReasoningProvider | None = None,
    thresholds: ConfidenceThresholds | None = None,
    case_context: CaseSemanticContext | None = None,
    budget: SemanticAIBudget | None = None,
) -> DatasetInterpretationResult:
    concept_registry = concept_registry or default_canonical_concept_registry
    provider = provider or default_semantic_reasoning_provider

    profile, role = profile_and_classify(
        dataset_label, dataframe, profiler=profiler, role_classifier=role_classifier
    )

    # One compact AI request per dataset (never per field, never per row) --
    # section 28's "never send every row to an LLM" / "compact
    # representative sample" sequencing.
    field_contexts = [
        FieldInterpretationContext(
            source_field=fp.source_field,
            physical_type=fp.physical_type,
            sample_values=representative_sample(dataframe[fp.source_field])
            if fp.source_field in dataframe.columns
            else fp.sample_values,
            value_patterns=fp.value_patterns,
            null_rate=fp.null_rate,
            uniqueness_ratio=fp.uniqueness_ratio,
            neighbor_field_names=[
                other.source_field
                for other in profile.fields
                if other.source_field != fp.source_field
            ],
        )
        for fp in profile.fields
    ]
    ai_response = _request_ai_proposals(
        provider, budget, dataset_label, role, concept_registry, field_contexts
    )
    ai_proposals_by_field: dict[str, list[SemanticCandidate]] = {}
    for proposal in ai_response.proposals:
        # P3.xxE.2 section 9: every returned concept_code must exist in
        # CanonicalConceptRegistry before it can enter candidate
        # reconciliation -- a hallucinated/unknown concept is dropped here,
        # never silently trusted into the candidate list.
        if concept_registry.get(proposal.proposed_concept) is None:
            continue
        ai_proposals_by_field.setdefault(proposal.source_field, []).append(
            SemanticCandidate(
                source_dataset_id=dataset_id,
                source_field=proposal.source_field,
                candidate_concept=proposal.proposed_concept,
                confidence=proposal.provider_confidence,
                evidence_components=[
                    InterpretationEvidence(
                        component_type=EvidenceComponentType.AI_PROPOSAL.value,
                        weight=proposal.provider_confidence,
                        description=(
                            f"{ai_response.provider_name} v{ai_response.provider_version} proposed "
                            f"{proposal.proposed_concept!r}: {proposal.rationale}"
                        ),
                        supports_concept=proposal.proposed_concept,
                    )
                ],
                candidate_rank=99,
                generated_by=f"{ai_response.provider_name}:{ai_response.provider_version}",
            )
        )

    decisions: list[InterpretationDecision] = []
    for fp in profile.fields:
        deterministic_candidates = generate_candidates(
            dataset_id, profile, role, fp, concept_registry
        )
        candidate_concepts = {c.candidate_concept for c in deterministic_candidates}
        neighbor_candidates = generate_neighbor_context_evidence(
            dataset_id, profile, fp, candidate_concepts, concept_registry
        )
        sibling_concept_candidates = generate_sibling_concept_corroboration_evidence(
            dataset_id, profile, fp, candidate_concepts, concept_registry
        )
        cross_dataset_candidates = generate_cross_dataset_evidence(
            dataset_id, fp, candidate_concepts, case_context, concept_registry
        )
        candidates = (
            deterministic_candidates
            + neighbor_candidates
            + sibling_concept_candidates
            + cross_dataset_candidates
            + ai_proposals_by_field.get(fp.source_field, [])
        )
        # AI proposals never bypass reconciliation (section 8/10): they are
        # additional candidates the SAME confidence engine scores, never a
        # shortcut straight to AUTO_ACCEPTED.
        decisions.append(reconcile(dataset_id, fp.source_field, candidates, thresholds))

    return DatasetInterpretationResult(
        dataset_profile=profile, role_interpretation=role, field_decisions=decisions
    )
