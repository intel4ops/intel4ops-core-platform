from __future__ import annotations

from dataclasses import dataclass, field

from app.models.ground_truth_validation import ValidationDimensionStatus

# Causal reasoning dimension (section 11C). The persisted Finding model
# (app/models/entities.py) carries no root-cause / causal-chain claim
# today -- causal_chain_id is an unrelated identifier used elsewhere, not
# a governed causal explanation Intelligence emits. Rather than fabricate
# a comparison against nothing, this honestly reports NOT_AVAILABLE for
# every run, exactly matching section 12's own worked example. The moment
# a rule starts publishing a causal claim (a genuinely new production
# capability, out of scope for this validation-only pass), this function
# is where that comparison gets wired in -- no other module changes.


@dataclass(frozen=True)
class CausalScoreSummary:
    status: str
    summary: str
    expected_count: int
    root_cause_matched_count: int | None = None
    causal_chain_matched_count: int | None = None
    metadata: dict[str, object] = field(default_factory=dict)


def score_causal(expected_causal_truth_count: int) -> CausalScoreSummary:
    if expected_causal_truth_count == 0:
        return CausalScoreSummary(
            status=ValidationDimensionStatus.NOT_AVAILABLE.value,
            summary="No causal truth was uploaded for this ground-truth version.",
            expected_count=0,
        )
    return CausalScoreSummary(
        status=ValidationDimensionStatus.NOT_AVAILABLE.value,
        summary=(
            "Causal truth was uploaded, but Intelligence does not currently emit a "
            "root-cause or causal-chain claim on any Finding to compare it against."
        ),
        expected_count=expected_causal_truth_count,
    )
