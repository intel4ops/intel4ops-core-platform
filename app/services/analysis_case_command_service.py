from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis_case import AnalysisCaseFinding
from app.models.entities import Finding

# ---------------------------------------------------------------------------
# operational_priority_v1 -- the explicit, versioned, deterministic
# prioritization method used whenever governed economics are unavailable
# (i.e. every finding this pass, since none carry an exposure_value).
# Future economics-enabled findings may use a different, separately
# versioned priority profile (e.g. "economic_priority_v1" built on
# economics_engine.calculate_priority()) -- callers should treat the
# method identifier as part of the contract, not assume it's constant.
#
# Ordering (all descending, most-attention-worthy first):
#   1. severity_rank      -- critical=4, high=3, medium=2, low=1, info=0.
#                             Missing/unrecognized severity ranks as info (0),
#                             never fabricated as higher.
#   2. confidence_rank     -- very_high=4, high=3, moderate=2, low=1,
#                             unknown=0. Missing/unrecognized confidence
#                             ranks as unknown (0).
#   3. affected_record_count -- missing/None treated as 0.
#   4. detected_at (ascending) -- tie-break: an older, longer-standing
#                             issue with identical severity/confidence/scale
#                             surfaces before a newer one. Missing
#                             detected_at sorts last (treated as "just now").
#   5. finding.id (str)    -- final deterministic tie-break so the ordering
#                             never depends on incidental input/DB order.
# ---------------------------------------------------------------------------
COMMAND_PRIORITY_METHOD = "operational_priority_v1"

_SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
_CONFIDENCE_RANK = {"very_high": 4, "high": 3, "moderate": 2, "low": 1, "unknown": 0}


@dataclass(frozen=True)
class PrioritizedFinding:
    finding: Finding
    impacted_domains: list[str]
    observed_values_by_currency: dict[str, float]
    priority_method: str = COMMAND_PRIORITY_METHOD


class AnalysisCaseCommandService:
    """Read-only aggregator (styled on executive_command_service.py) --
    computes a prioritized view, writes nothing new.

    Deliberately does NOT call economics_engine.calculate_priority(): that
    function's default weighting is 60% economics-derived (economic_value/
    net_benefit/roi/payback), so forcing our economics-free findings
    through it with zero-substitute values would produce a misleadingly
    low, economics-shaped score rather than an honest severity/confidence
    ranking. Instead implements COMMAND_PRIORITY_METHOD
    ("operational_priority_v1", module docstring above has the full
    ordering spec) -- an explicit, versioned, deterministic, non-monetary
    ranking. Never sums monetary observations across currencies (Section
    13) -- each finding's observed value stays grouped by its own
    currency. A future economics-enabled profile would be a distinctly
    named, separately versioned method, not a silent change to this one."""

    def priorities(
        self, db: Session, organization_id: UUID, analysis_case_id: UUID, run_id: UUID | None = None
    ) -> list[PrioritizedFinding]:
        stmt = (
            select(Finding)
            .join(AnalysisCaseFinding, AnalysisCaseFinding.finding_id == Finding.id)
            .where(
                AnalysisCaseFinding.organization_id == organization_id,
                AnalysisCaseFinding.analysis_case_id == analysis_case_id,
            )
        )
        if run_id is not None:
            stmt = stmt.where(AnalysisCaseFinding.run_id == run_id)
        findings = list(db.scalars(stmt).all())

        def sort_key(finding: Finding) -> tuple[int, int, int, float, str]:
            severity_rank = _SEVERITY_RANK.get((finding.severity or "").lower(), 0)
            confidence_rank = _CONFIDENCE_RANK.get((finding.confidence_level or "").lower(), 0)
            affected_count = finding.affected_record_count or 0
            detected_at: datetime | None = finding.detected_at
            # Descending on rank/count is expressed as negation so the
            # whole tuple can sort ascending in one pass; detected_at and
            # id are already in their desired ascending order.
            recency_key = detected_at.timestamp() if detected_at is not None else float("inf")
            return (-severity_rank, -confidence_rank, -affected_count, recency_key, str(finding.id))

        findings.sort(key=sort_key)

        results = []
        for finding in findings:
            observed: dict[str, float] = {}
            if finding.measured_value is not None and finding.measured_currency:
                observed[finding.measured_currency] = float(finding.measured_value)
            results.append(
                PrioritizedFinding(
                    finding=finding,
                    impacted_domains=finding.domains_json
                    or ([finding.domain_code] if finding.domain_code else []),
                    observed_values_by_currency=observed,
                )
            )
        return results


analysis_case_command_service = AnalysisCaseCommandService()
