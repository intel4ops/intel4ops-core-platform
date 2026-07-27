from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.validation.certification import evidence_hash
from app.validation.simulation import (
    ORACLE_REGISTRY,
    OracleComparator,
    SimulationArtifact,
    SimulationGenerator,
)

GOLDEN_SCENARIOS = (
    "J2C-OILFIELD-001",
    "MFG-SERVO-DEGRADATION-001",
    "PORT-CRANE-001",
    "MOB-FUEL-001",
)

SECRET_PATTERN = re.compile(
    r"(?i)(password|secret|service[_-]?role|bearer\s+|api[_-]?key|jwt|postgres(?:ql)?://)"
)


class CheckResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    passed: bool
    summary: str
    evidence_hash: str


class GoldenResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    scenario_code: str
    passed: bool
    artifact_hash: str
    assertion_count: int
    failures: tuple[str, ...]


@dataclass(frozen=True)
class GoldenScenarioSuite:
    generator: SimulationGenerator = SimulationGenerator()
    comparator: OracleComparator = OracleComparator()

    def run(self, organization_id: UUID) -> tuple[GoldenResult, ...]:
        return tuple(self._run_scenario(code, organization_id) for code in GOLDEN_SCENARIOS)

    def _run_scenario(self, code: str, organization_id: UUID) -> GoldenResult:
        artifact = self.generator.generate(code, organization_id)
        actual = {
            "scenario_code": artifact.scenario_code,
            "pack_code": artifact.pack_code,
            "defect_count": len(artifact.defects),
        }
        comparison = self.comparator.compare(actual, ORACLE_REGISTRY[code])
        failures = list(comparison.failures)
        if not artifact.records:
            failures.append("scenario produced no source records")
        if {record["organization_id"] for record in artifact.records} != {str(organization_id)}:
            failures.append("scenario contains a cross-tenant record")
        if code == "J2C-OILFIELD-001":
            self._validate_oilfield(artifact, failures)
        return GoldenResult(
            scenario_code=code,
            passed=not failures,
            artifact_hash=artifact.content_hash,
            assertion_count=comparison.assertion_count,
            failures=tuple(failures),
        )

    @staticmethod
    def _validate_oilfield(artifact: SimulationArtifact, failures: list[str]) -> None:
        types = {str(item["record_type"]) for item in artifact.records}
        required = {
            "contract",
            "rate_sheet",
            "purchase_order",
            "field_job",
            "field_ticket",
            "invoice",
            "invoice_line",
            "payment",
            "credit",
            "recovery_action",
            "verified_value",
            "reversal",
        }
        if not required <= types:
            failures.append("oilfield source-to-recovery path is incomplete")
        event_window = artifact.manifest.get("event_window")
        sequence = event_window.get("ordered_event_sequence", []) if event_window else []
        if sequence[-3:] != ["payment", "verified_recovery", "credit_adjustment"]:
            failures.append("oilfield verified-value reversal sequence is incomplete")


class CertificationSuites:
    def tenant_isolation(
        self,
        first: SimulationArtifact,
        second: SimulationArtifact,
    ) -> CheckResult:
        first_ids = {record.get("organization_id") for record in first.records}
        second_ids = {record.get("organization_id") for record in second.records}
        passed = (
            first.organization_id != second.organization_id
            and first_ids == {str(first.organization_id)}
            and second_ids == {str(second.organization_id)}
            and first_ids.isdisjoint(second_ids)
        )
        return self._result(
            "TENANT_ISOLATION",
            passed,
            {"first": sorted(first_ids), "second": sorted(second_ids)},
        )

    def authorization(
        self,
        *,
        authenticated: bool,
        permitted: bool,
        membership_active: bool,
        client_active: bool,
    ) -> CheckResult:
        passed = authenticated and permitted and membership_active and client_active
        return self._result(
            "AUTHORIZATION",
            passed,
            {
                "authenticated": authenticated,
                "permitted": permitted,
                "membership_active": membership_active,
                "client_active": client_active,
            },
        )

    def security(self, payload: dict[str, Any], filename: str) -> CheckResult:
        serialized = repr(payload)
        safe_name = PurePath(filename).name == filename and ".." not in PurePath(filename).parts
        passed = not SECRET_PATTERN.search(serialized) and safe_name
        return self._result(
            "SECURITY",
            passed,
            {
                "secret_pattern_absent": not bool(SECRET_PATTERN.search(serialized)),
                "safe_name": safe_name,
            },
        )

    def idempotency(
        self,
        first: SimulationArtifact,
        replay: SimulationArtifact,
    ) -> CheckResult:
        passed = first.content_hash == replay.content_hash and first.records == replay.records
        return self._result(
            "IDEMPOTENCY",
            passed,
            {"first_hash": first.content_hash, "replay_hash": replay.content_hash},
        )

    def resilience(
        self,
        *,
        original_count: int,
        replay_count: int,
        duplicate_findings: int,
        duplicate_actions: int,
        duplicate_usage: int,
        duplicate_ledger_entries: int,
        failure_audit_emitted: bool,
    ) -> CheckResult:
        passed = (
            original_count == replay_count
            and duplicate_findings == 0
            and duplicate_actions == 0
            and duplicate_usage == 0
            and duplicate_ledger_entries == 0
            and failure_audit_emitted
        )
        return self._result(
            "RESILIENCE",
            passed,
            {
                "original_count": original_count,
                "replay_count": replay_count,
                "duplicates": {
                    "findings": duplicate_findings,
                    "actions": duplicate_actions,
                    "usage": duplicate_usage,
                    "ledger": duplicate_ledger_entries,
                },
                "failure_audit_emitted": failure_audit_emitted,
            },
        )

    def observability(self, event: dict[str, Any]) -> CheckResult:
        required = {
            "correlation_id",
            "organization_id",
            "operation",
            "outcome",
            "duration_ms",
            "occurred_at",
        }
        passed = required <= set(event) and not SECRET_PATTERN.search(repr(event))
        return self._result(
            "OBSERVABILITY",
            passed,
            {"present_fields": sorted(set(event) & required), "required_fields": sorted(required)},
        )

    @staticmethod
    def _result(code: str, passed: bool, evidence: dict[str, Any]) -> CheckResult:
        return CheckResult(
            code=code,
            passed=passed,
            summary=f"{code} {'passed' if passed else 'failed'}",
            evidence_hash=evidence_hash(evidence),
        )
