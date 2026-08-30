from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.semantic.openai_provider import OpenAISemanticReasoningProvider
from app.semantic.provider import SemanticReasoningProvider, default_semantic_reasoning_provider

# ---------------------------------------------------------------------------
# P3.xxE.2 section 19: provider selection + a minimal per-run cost budget.
# select_semantic_reasoning_provider() is called once per run (not per
# dataset); SemanticAIBudget is instantiated once per run alongside it and
# threaded through every dataset's interpret_dataset() call in that run.
# When exhausted, interpret_dataset() skips provider.propose() entirely
# (same code path as an unconfigured/Null provider) rather than failing
# the run -- see app/services/analysis_case_orchestration_service.py's
# two-pass semantic stage.
# ---------------------------------------------------------------------------


def select_semantic_reasoning_provider(settings: Settings) -> SemanticReasoningProvider:
    if settings.semantic_ai_enabled and settings.ai_api_key:
        return OpenAISemanticReasoningProvider(settings)
    return default_semantic_reasoning_provider


@dataclass
class SemanticAIBudget:
    max_calls: int
    calls_made: int = 0

    def try_consume(self) -> bool:
        if self.calls_made >= self.max_calls:
            return False
        self.calls_made += 1
        return True
