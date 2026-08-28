from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

# Ground truth's own, deliberately separate normalizer -- never routed
# through app.ingestion.parsers / ArtifactParserRegistry, which exists to
# parse customer operational data. This module owns the machine-readable
# ground-truth schema end to end.


@dataclass(frozen=True)
class NormalizedExpectedFinding:
    expected_finding_code: str
    domain: str
    severity: str
    entities: list[dict[str, object]] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    expected_economic_impact: Decimal | None = None
    currency: str | None = None
    description: str = ""


@dataclass(frozen=True)
class NormalizedGroundTruth:
    expected_findings: list[NormalizedExpectedFinding]
    expected_clean_areas: list[str]
    tolerance: dict[str, object]


class GroundTruthFormatError(ValueError):
    """Raised when an uploaded ground-truth payload does not match the
    normalized schema -- never silently coerced into something plausible-
    looking."""


def normalize_ground_truth(payload: dict[str, object]) -> NormalizedGroundTruth:
    raw_findings = payload.get("expected_findings")
    if not isinstance(raw_findings, list):
        raise GroundTruthFormatError("expected_findings must be a list")

    findings: list[NormalizedExpectedFinding] = []
    seen_codes: set[str] = set()
    for index, raw in enumerate(raw_findings):
        if not isinstance(raw, dict):
            raise GroundTruthFormatError(f"expected_findings[{index}] must be an object")
        code = raw.get("expected_finding_code")
        domain = raw.get("domain")
        severity = raw.get("severity")
        if not isinstance(code, str) or not code:
            raise GroundTruthFormatError(
                f"expected_findings[{index}].expected_finding_code required"
            )
        if code in seen_codes:
            raise GroundTruthFormatError(f"duplicate expected_finding_code {code!r}")
        seen_codes.add(code)
        if not isinstance(domain, str) or not domain:
            raise GroundTruthFormatError(f"expected_findings[{index}].domain required")
        if not isinstance(severity, str) or not severity:
            raise GroundTruthFormatError(f"expected_findings[{index}].severity required")
        entities = raw.get("entities", [])
        if not isinstance(entities, list):
            raise GroundTruthFormatError(f"expected_findings[{index}].entities must be a list")
        evidence_refs = raw.get("evidence_refs", [])
        if not isinstance(evidence_refs, list):
            raise GroundTruthFormatError(f"expected_findings[{index}].evidence_refs must be a list")
        impact = raw.get("expected_economic_impact")
        findings.append(
            NormalizedExpectedFinding(
                expected_finding_code=code,
                domain=domain,
                severity=severity,
                entities=list(entities),
                evidence_refs=[str(e) for e in evidence_refs],
                expected_economic_impact=(Decimal(str(impact)) if impact is not None else None),
                currency=raw.get("currency"),
                description=str(raw.get("description", "")),
            )
        )

    clean_areas = payload.get("expected_clean_areas", [])
    if not isinstance(clean_areas, list):
        raise GroundTruthFormatError("expected_clean_areas must be a list")
    tolerance = payload.get("tolerance", {})
    if not isinstance(tolerance, dict):
        raise GroundTruthFormatError("tolerance must be an object")

    return NormalizedGroundTruth(
        expected_findings=findings,
        expected_clean_areas=[str(a) for a in clean_areas],
        tolerance=tolerance,
    )
