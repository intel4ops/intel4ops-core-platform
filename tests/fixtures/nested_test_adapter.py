from __future__ import annotations

from app.ground_truth_validation.adapters.base import GroundTruthFormatError
from app.ground_truth_validation.ontology import NormalizedExpectedFinding, NormalizedPackage

# Test-only adapter (P3.xxD.1E section 0/20 carve-out: "except inside
# tests/fixtures"). Deliberately uses a genuinely different authored
# schema from SIM-005's own adapter -- nested one level under
# "case_findings", terser field names (id/sev/fam/who), and a different
# entity-reference shape ({"kind","key"} instead of {"entity_type",
# "canonical_key"}). Proves the architecture generalizes to an
# unanticipated vocabulary via a brand-new adapter, without any change to
# app/ground_truth_validation/matcher.py, integrity.py, or service.py.

ADAPTER_CODE = "test_nested_v1"
ADAPTER_VERSION = "1.0"


class NestedTestAdapter:
    adapter_code = ADAPTER_CODE
    adapter_version = ADAPTER_VERSION
    supported_schema_version = ADAPTER_CODE

    def can_handle(self, package_metadata: dict[str, object]) -> bool:
        # Pure shape detection (P3.xxD.1E.1): documents.expected_findings
        # is an object keyed by "case_findings", never a bare list -- that
        # alone distinguishes it from simulation_truth_v1's shape (a list)
        # and simple_v1's shape (no "documents" envelope at all).
        documents = package_metadata.get("documents")
        if not isinstance(documents, dict):
            return False
        container = documents.get("expected_findings")
        return isinstance(container, dict) and "case_findings" in container

    def normalize(self, package_documents: dict[str, object]) -> NormalizedPackage:
        documents = package_documents.get("documents")
        if not isinstance(documents, dict):
            raise GroundTruthFormatError("documents required")
        container = documents.get("expected_findings")
        if not isinstance(container, dict) or "case_findings" not in container:
            raise GroundTruthFormatError("expected_findings.case_findings required")
        records = container["case_findings"]
        if not isinstance(records, list):
            raise GroundTruthFormatError("case_findings must be a list")

        findings = []
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                raise GroundTruthFormatError(f"case_findings[{index}] must be an object")
            truth_id = record.get("id")
            severity = record.get("sev")
            if not isinstance(truth_id, str) or not truth_id:
                raise GroundTruthFormatError(f"case_findings[{index}].id required")
            if not isinstance(severity, str) or not severity:
                raise GroundTruthFormatError(f"case_findings[{index}].sev required")
            who = record.get("who", [])
            entities = [
                {"entity_type": w.get("kind"), "canonical_key": w.get("key")}
                for w in who
                if isinstance(w, dict)
            ]
            findings.append(
                NormalizedExpectedFinding(
                    truth_finding_id=truth_id,
                    scenario_code=None,
                    severity=severity,
                    expected_detection_family=record.get("fam")
                    if isinstance(record.get("fam"), str)
                    else None,
                    entities=entities,
                )
            )

        return NormalizedPackage(
            adapter_code=self.adapter_code,
            adapter_version=self.adapter_version,
            schema_version=self.supported_schema_version,
            manifest=None,
            expected_findings=findings,
        )


nested_test_adapter = NestedTestAdapter()
