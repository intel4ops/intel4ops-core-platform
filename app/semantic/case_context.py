from __future__ import annotations

from dataclasses import dataclass

from app.semantic.profiler import DatasetProfile
from app.semantic.role_classifier import DatasetRoleInterpretation

# ---------------------------------------------------------------------------
# P3.xxE.2: case-level semantic context, built once per run (Pass 1 of the
# two-pass semantic stage in AnalysisCaseOrchestrationService) and read by
# every dataset's field interpretation (Pass 2) -- never mutated after
# construction. This is the mechanism that makes cross-dataset evidence
# order-independent: every dataset's Pass-2 interpretation sees the SAME
# fully-populated context regardless of which dataset was profiled first in
# Pass 1, so a field's evidence never depends on `case_datasets` iteration
# order.
#
# Keyed by a caller-chosen string key (in practice, str(AnalysisCaseDataset.id)
# -- deliberately not a UUID import here to keep this module a pure,
# framework-free data holder like the rest of app/semantic/*).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CaseSemanticContext:
    profiles: dict[str, DatasetProfile]
    roles: dict[str, DatasetRoleInterpretation]
