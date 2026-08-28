from __future__ import annotations

from decimal import Decimal

from app.ground_truth_validation.adapters.base import GroundTruthFormatError
from app.ground_truth_validation.ontology import NormalizedExpectedFinding, NormalizedPackage

# The original P3.xxD.1B "simple" ground-truth shape: a single JSON object
# with expected_findings/expected_clean_areas/tolerance, no manifest, no
# leakage/causal/data-quality dimensions. Wrapped by
# app/ground_truth_validation/adapters/simple_v1.py as the
# "intel4ops_simple_v1" adapter -- kept for backward compatibility
# (section 15), never required by any other adapter.

ADAPTER_CODE = "intel4ops_simple_v1"
ADAPTER_VERSION = "1.0"


def normalize_ground_truth(payload: dict[str, object]) -> NormalizedPackage:
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
        # V1 contract: domain is the only way to express business semantics
        # (expected_detection_family did not exist yet), so it stays
        # required here -- this is a property of the V1 shape, not a rule
        # the ontology itself imposes (section 7 applies to the ontology
        # broadly and to newer adapters that have expected_detection_family
        # as an alternative).
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
                truth_finding_id=code,
                scenario_code=None,
                severity=severity,
                domain=domain,
                entities=list(entities),
                evidence_refs=[str(e) for e in evidence_refs],
                expected_economic_impact=(Decimal(str(impact)) if impact is not None else None),
                currency=raw.get("currency") if isinstance(raw.get("currency"), str) else None,
                description=str(raw.get("description", "")),
            )
        )

    clean_areas = payload.get("expected_clean_areas", [])
    if not isinstance(clean_areas, list):
        raise GroundTruthFormatError("expected_clean_areas must be a list")
    tolerance = payload.get("tolerance", {})
    if not isinstance(tolerance, dict):
        raise GroundTruthFormatError("tolerance must be an object")

    return NormalizedPackage(
        adapter_code=ADAPTER_CODE,
        adapter_version=ADAPTER_VERSION,
        schema_version=ADAPTER_CODE,
        manifest=None,
        expected_findings=findings,
        expected_clean_areas=[str(a) for a in clean_areas],
        tolerance=tolerance,
    )
