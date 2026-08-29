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
from app.semantic.concept_registry import (
    CanonicalConceptRegistry,
    default_canonical_concept_registry,
)
from app.semantic.confidence_engine import ConfidenceThresholds, reconcile
from app.semantic.profiler import DatasetProfile, DatasetProfiler, dataset_profiler
from app.semantic.provider import (
    FieldInterpretationContext,
    SemanticInterpretationRequest,
    SemanticReasoningProvider,
    default_semantic_reasoning_provider,
)
from app.semantic.role_classifier import (
    DatasetRoleClassifier,
    DatasetRoleInterpretation,
    dataset_role_classifier,
)
from app.semantic.sampling import representative_sample

# ---------------------------------------------------------------------------
# Section 14/30 item 14: the single orchestration-facing entry point.
# AnalysisCase orchestration (app/services/analysis_case_orchestration_
# service.py) calls interpret_dataset() once per registered dataset,
# additively alongside (never replacing) the existing mapping bridge --
# see the module docstring in app/semantic/__init__.py for the staged
# migration story. No branch here on a simulation identifier, industry, or
# specific client field name -- every domain-specific step is either
# generic profiling/classification or a CanonicalConceptRegistry lookup.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DatasetInterpretationResult:
    dataset_profile: DatasetProfile
    role_interpretation: DatasetRoleInterpretation
    field_decisions: list[InterpretationDecision]


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
) -> DatasetInterpretationResult:
    profiler = profiler or dataset_profiler
    role_classifier = role_classifier or dataset_role_classifier
    concept_registry = concept_registry or default_canonical_concept_registry
    provider = provider or default_semantic_reasoning_provider

    profile = profiler.profile(dataset_label, dataframe)
    role = role_classifier.classify(profile)

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
        )
        for fp in profile.fields
    ]
    ai_response = provider.propose(
        SemanticInterpretationRequest(
            dataset_label=dataset_label,
            dataset_role_hint=role.primary_role,
            known_concept_codes=[c.concept_code for c in concept_registry.active()],
            fields=field_contexts,
        )
    )
    ai_proposals_by_field: dict[str, list[SemanticCandidate]] = {}
    for proposal in ai_response.proposals:
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
        candidates = deterministic_candidates + ai_proposals_by_field.get(fp.source_field, [])
        # AI proposals never bypass reconciliation (section 8/10): they are
        # additional candidates the SAME confidence engine scores, never a
        # shortcut straight to AUTO_ACCEPTED.
        decisions.append(reconcile(dataset_id, fp.source_field, candidates, thresholds))

    return DatasetInterpretationResult(
        dataset_profile=profile, role_interpretation=role, field_decisions=decisions
    )
