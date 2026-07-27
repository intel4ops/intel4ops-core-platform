from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GateStatus(StrEnum):
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"
    BLOCKED = "blocked"
    NOT_RUN = "not_run"


class CertificationDecision(StrEnum):
    CERTIFIED = "certified"
    CONDITIONALLY_CERTIFIED = "conditionally_certified"
    REJECTED = "rejected"
    BLOCKED = "blocked"


class GateDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    mandatory: bool = True
    waivable: bool = False


class GateResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    status: GateStatus
    summary: str
    evidence_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class Waiver(BaseModel):
    model_config = ConfigDict(frozen=True)

    gate_code: str
    approved: bool
    expires_at: datetime
    justification: str = Field(min_length=10)
    compensating_control: str = Field(min_length=10)

    @model_validator(mode="after")
    def timezone_required(self) -> Waiver:
        if self.expires_at.tzinfo is None:
            raise ValueError("waiver expiry must be timezone-aware")
        return self


class CertificationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    commit_sha: str = Field(min_length=7, max_length=64)
    branch: str
    migration_head: str
    environment: str
    decision: CertificationDecision
    gate_results: tuple[GateResult, ...]
    waived_gates: tuple[str, ...]
    generated_at: datetime
    report_hash: str = ""


@dataclass(frozen=True)
class ReleaseGateEvaluator:
    def evaluate(
        self,
        definitions: tuple[GateDefinition, ...],
        results: tuple[GateResult, ...],
        waivers: tuple[Waiver, ...] = (),
        *,
        now: datetime | None = None,
    ) -> tuple[CertificationDecision, tuple[str, ...]]:
        clock = now or datetime.now(UTC)
        result_by_code = {result.code: result for result in results}
        waiver_by_code = {waiver.gate_code: waiver for waiver in waivers}
        waived: list[str] = []
        conditional = False
        for definition in definitions:
            result = result_by_code.get(definition.code)
            if result is None or result.status in {GateStatus.NOT_RUN, GateStatus.BLOCKED}:
                if definition.mandatory:
                    return CertificationDecision.BLOCKED, ()
                continue
            if result.status is GateStatus.FAILED:
                waiver = waiver_by_code.get(definition.code)
                valid_waiver = (
                    definition.waivable
                    and waiver is not None
                    and waiver.approved
                    and waiver.expires_at > clock
                )
                if not valid_waiver:
                    return CertificationDecision.REJECTED, ()
                conditional = True
                waived.append(definition.code)
            elif result.status is GateStatus.WARNING:
                conditional = True
        if conditional:
            return CertificationDecision.CONDITIONALLY_CERTIFIED, tuple(sorted(waived))
        return CertificationDecision.CERTIFIED, ()


ALLOWED_ARTIFACT_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"under_review"}),
    "under_review": frozenset({"draft", "validated"}),
    "validated": frozenset({"under_review", "approved"}),
    "approved": frozenset({"active"}),
    "active": frozenset({"suspended", "deprecated"}),
    "suspended": frozenset({"active", "retired"}),
    "deprecated": frozenset({"retired"}),
    "retired": frozenset(),
}


def validate_artifact_transition(current: str, target: str) -> None:
    if target not in ALLOWED_ARTIFACT_TRANSITIONS.get(current, frozenset()):
        raise ValueError(f"Invalid analytical artifact transition: {current} -> {target}")


def require_production_eligible_artifact(status: str) -> None:
    if status != "active":
        raise PermissionError(f"Analytical artifact status {status!r} cannot execute in production")


def write_certification_reports(
    report: CertificationReport,
    output_directory: Path,
) -> tuple[Path, Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    unsigned = report.model_dump(mode="json", exclude={"report_hash"})
    digest = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    final = report.model_copy(update={"report_hash": digest})
    json_path = output_directory / "release-certification.json"
    markdown_path = output_directory / "release-certification.md"
    json_path.write_text(final.model_dump_json(indent=2), encoding="utf-8")
    markdown_path.write_text(_markdown(final), encoding="utf-8")
    return json_path, markdown_path


def _markdown(report: CertificationReport) -> str:
    rows = "\n".join(
        f"| {result.code} | {result.status} | {result.summary} |" for result in report.gate_results
    )
    return (
        "# Intel4Ops Release Certification\n\n"
        f"- Commit: `{report.commit_sha}`\n"
        f"- Branch: `{report.branch}`\n"
        f"- Migration head: `{report.migration_head}`\n"
        f"- Environment: `{report.environment}`\n"
        f"- Decision: **{report.decision}**\n"
        f"- Report hash: `{report.report_hash}`\n\n"
        "## Gate results\n\n"
        "| Gate | Status | Summary |\n"
        "|---|---|---|\n"
        f"{rows}\n"
    )


def evidence_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
