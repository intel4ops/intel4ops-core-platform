from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.ground_truth_validation.adapters.base import GroundTruthFormatError
from app.ground_truth_validation.ontology import (
    NormalizedCausalTruth,
    NormalizedDataQualityTruth,
    NormalizedExpectedFinding,
    NormalizedLeakageTruth,
    NormalizedManifest,
    NormalizedPackage,
)

# ---------------------------------------------------------------------------
# Adapter for the multi-document truth-package shape first observed on
# SIM-OFS-FIELDMAINT-005 (truth_manifest.json / expected_findings.json /
# leakage_truth.json / causal_truth.json / data_quality_truth.json --
# section 3). Keyed to this SCHEMA, not to that simulation: any future
# package using the same authored field names (finding_id,
# expected_severity, leakage_id, business_type, ...) is handled
# identically, and SIM-005 is exercised through this adapter exactly like
# any other package would be (section 19) -- there is no branch here on a
# simulation_id.
#
# Every "authored name -> ontology name" translation lives in this one
# file (section 6). The deterministic EF-<leakage_id> join convention
# (section 9) is also adapter-local: it produces a normalized
# linked_leakage_id value, never a rule the central engine re-derives.
# ---------------------------------------------------------------------------

ADAPTER_CODE = "intel4ops_simulation_truth_v1"
ADAPTER_VERSION = "1.0"

_KNOWN_LEAKAGE_KEYS = {
    "leakage_id",
    "scenario_id",
    "business_type",
    "affected_records",
    "time_window",
    "root_cause",
    "causal_chain",
    "severity",
    "recoverable",
    "expected_detection_family",
    "expected_evidence",
    "true_leakage_value",
    "recoverable_value",
    "currency",
}


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise GroundTruthFormatError(f"expected a numeric value, got {value!r}") from None


def _require_str(record: dict[str, object], key: str, where: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value:
        raise GroundTruthFormatError(f"{where}.{key} required")
    return value


def _infer_entities(record: dict[str, object]) -> list[dict[str, object]]:
    """ "...domain-specific entity identifiers" (section 3): any key
    ending in "_id" that isn't one of this schema's own structural keys is
    treated as an entity reference -- e.g. asset_id, technician_id,
    work_order_id. Generic by construction: no specific identifier name is
    hard-coded."""
    entities: list[dict[str, object]] = []
    for key, value in record.items():
        if key in _KNOWN_LEAKAGE_KEYS or key in {"finding_id", "dq_id", "defect_id", "record_id"}:
            continue
        if key.endswith("_id") and isinstance(value, (str, int)):
            entities.append({"entity_type": key[: -len("_id")], "canonical_key": str(value)})
    return entities


def _derive_linked_leakage_id(finding_id: str) -> str | None:
    """EF-<leakage_id> is this schema's own deterministic join convention
    (section 9) -- e.g. "EF-LK-1" -> "LK-1". A package using a different
    convention needs a different adapter, not a change here."""
    if finding_id.startswith("EF-"):
        return finding_id[len("EF-") :]
    return None


class SimulationTruthV1Adapter:
    adapter_code = ADAPTER_CODE
    adapter_version = ADAPTER_VERSION
    supported_schema_version = ADAPTER_CODE

    def can_handle(self, package_metadata: dict[str, object]) -> bool:
        # Pure shape detection -- schema_version routing is the registry's
        # job, not this adapter's (P3.xxD.1E.1). This is exactly what the
        # real SIM-OFS-FIELDMAINT-005 truth_manifest.json needs: it has no
        # schema_version at all, so selection must work from shape alone.
        documents = package_metadata.get("documents")
        if not isinstance(documents, dict):
            return False
        findings = documents.get("expected_findings")
        if isinstance(findings, list) and findings and isinstance(findings[0], dict):
            return "finding_id" in findings[0] and "expected_severity" in findings[0]
        leakage = documents.get("leakage_truth")
        if isinstance(leakage, list) and leakage and isinstance(leakage[0], dict):
            return "leakage_id" in leakage[0]
        return False

    def normalize(self, package_documents: dict[str, object]) -> NormalizedPackage:
        documents = package_documents.get("documents")
        if not isinstance(documents, dict):
            raise GroundTruthFormatError(
                "package must declare a 'documents' map of role -> content"
            )

        manifest = self._normalize_manifest(package_documents.get("manifest"))
        findings = self._normalize_expected_findings(documents.get("expected_findings"))
        leakage = self._normalize_leakage_truth(documents.get("leakage_truth"))
        causal = self._normalize_causal_truth(documents.get("causal_truth"))
        data_quality = self._normalize_data_quality_truth(documents.get("data_quality_truth"))

        return NormalizedPackage(
            adapter_code=self.adapter_code,
            adapter_version=self.adapter_version,
            schema_version=self.supported_schema_version,
            manifest=manifest,
            expected_findings=findings,
            leakage_truth=leakage,
            causal_truth=causal,
            data_quality_truth=data_quality,
        )

    def _normalize_manifest(self, raw: object) -> NormalizedManifest | None:
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise GroundTruthFormatError("manifest document must be an object")
        files = raw.get("files", [])
        inventory: list[dict[str, object]] = []
        checksums: dict[str, str] = {}
        if isinstance(files, list):
            for entry in files:
                if not isinstance(entry, dict):
                    continue
                inventory.append(dict(entry))
                filename = entry.get("file")
                sha256 = entry.get("sha256")
                if isinstance(filename, str) and isinstance(sha256, str):
                    checksums[filename] = sha256
        summary = raw.get("summary")
        return NormalizedManifest(
            simulation_code=raw.get("simulation_id")
            if isinstance(raw.get("simulation_id"), str)
            else None,
            truth_schema_version=raw.get("truth_schema_version")
            if isinstance(raw.get("truth_schema_version"), str)
            else None,
            sealed_at=raw.get("sealed_at") if isinstance(raw.get("sealed_at"), str) else None,
            summary=summary if isinstance(summary, dict) else {},
            document_inventory=inventory,
            checksums=checksums,
        )

    def _normalize_expected_findings(self, raw: object) -> list[NormalizedExpectedFinding]:
        if raw is None:
            return []
        records = _as_record_list(raw, "expected_findings")
        results = []
        for index, record in enumerate(records):
            where = f"expected_findings[{index}]"
            finding_id = _require_str(record, "finding_id", where)
            severity = _require_str(record, "expected_severity", where)
            scenario_code = record.get("scenario_id")
            family = record.get("expected_detection_family")
            affected = record.get("affected_records", [])
            results.append(
                NormalizedExpectedFinding(
                    truth_finding_id=finding_id,
                    scenario_code=scenario_code if isinstance(scenario_code, str) else None,
                    severity=severity,
                    expected_detection_family=family if isinstance(family, str) else None,
                    linked_leakage_id=_derive_linked_leakage_id(finding_id),
                    entities=_infer_entities(record),
                    affected_records=[str(a) for a in affected]
                    if isinstance(affected, list)
                    else [],
                    expected_economic_impact=_decimal(record.get("expected_value")),
                    currency=record.get("currency")
                    if isinstance(record.get("currency"), str)
                    else None,
                )
            )
        return results

    def _normalize_leakage_truth(self, raw: object) -> list[NormalizedLeakageTruth]:
        if raw is None:
            return []
        records = _as_record_list(raw, "leakage_truth")
        results = []
        for index, record in enumerate(records):
            where = f"leakage_truth[{index}]"
            leakage_id = _require_str(record, "leakage_id", where)
            scenario_code = record.get("scenario_id")
            affected = record.get("affected_records", [])
            causal_chain = record.get("causal_chain", [])
            evidence = record.get("expected_evidence", [])
            time_window = record.get("time_window")
            results.append(
                NormalizedLeakageTruth(
                    truth_leakage_id=leakage_id,
                    scenario_code=scenario_code if isinstance(scenario_code, str) else None,
                    business_context=record.get("business_type")
                    if isinstance(record.get("business_type"), str)
                    else None,
                    affected_records=[str(a) for a in affected]
                    if isinstance(affected, list)
                    else [],
                    entities=_infer_entities(record),
                    time_window=time_window if isinstance(time_window, dict) else None,
                    root_cause=record.get("root_cause")
                    if isinstance(record.get("root_cause"), str)
                    else None,
                    causal_chain=list(causal_chain) if isinstance(causal_chain, list) else [],
                    severity=record.get("severity")
                    if isinstance(record.get("severity"), str)
                    else None,
                    recoverable=record.get("recoverable")
                    if isinstance(record.get("recoverable"), bool)
                    else None,
                    detection_family=record.get("expected_detection_family")
                    if isinstance(record.get("expected_detection_family"), str)
                    else None,
                    expected_evidence=[str(e) for e in evidence]
                    if isinstance(evidence, list)
                    else [],
                    true_leakage_value=_decimal(record.get("true_leakage_value")),
                    recoverable_value=_decimal(record.get("recoverable_value")),
                    currency=record.get("currency")
                    if isinstance(record.get("currency"), str)
                    else None,
                )
            )
        return results

    def _normalize_causal_truth(self, raw: object) -> list[NormalizedCausalTruth]:
        if raw is None:
            return []
        records = _as_record_list(raw, "causal_truth")
        results = []
        for index, record in enumerate(records):
            where = f"causal_truth[{index}]"
            leakage_id = _require_str(record, "leakage_id", where)
            scenario_code = record.get("scenario_id")
            causal_chain = record.get("causal_chain", [])
            results.append(
                NormalizedCausalTruth(
                    truth_causal_id=leakage_id,
                    scenario_code=scenario_code if isinstance(scenario_code, str) else None,
                    linked_leakage_id=leakage_id,
                    expected_root_cause=record.get("root_cause")
                    if isinstance(record.get("root_cause"), str)
                    else None,
                    expected_causal_chain=list(causal_chain)
                    if isinstance(causal_chain, list)
                    else [],
                )
            )
        return results

    def _normalize_data_quality_truth(self, raw: object) -> list[NormalizedDataQualityTruth]:
        if raw is None:
            return []
        records = _as_record_list(raw, "data_quality_truth")
        results = []
        for index, record in enumerate(records):
            where = f"data_quality_truth[{index}]"
            truth_id = record.get("defect_id") or record.get("dq_id")
            if not isinstance(truth_id, str) or not truth_id:
                raise GroundTruthFormatError(f"{where}.defect_id or dq_id required")
            record_ref = record.get("record_id")
            results.append(
                NormalizedDataQualityTruth(
                    truth_dq_id=truth_id,
                    affected_record=record_ref if isinstance(record_ref, str) else None,
                    detail=record.get("detail") if isinstance(record.get("detail"), str) else None,
                    severity=record.get("severity")
                    if isinstance(record.get("severity"), str)
                    else None,
                )
            )
        return results


def _as_record_list(raw: object, where: str) -> list[dict[str, Any]]:
    """Accepts either an array of records (fixtures A/C-array-style) or an
    object keyed by record id (fixture C: object-map records) -- section
    20's "object-map keyed by ID" case. Never assumes one shape globally."""
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                raise GroundTruthFormatError(f"{where} entries must be objects")
        return list(raw)
    if isinstance(raw, dict):
        records = []
        for key, value in raw.items():
            if not isinstance(value, dict):
                raise GroundTruthFormatError(f"{where}[{key!r}] must be an object")
            records.append(value)
        return records
    raise GroundTruthFormatError(f"{where} must be a list or an object map")


simulation_truth_v1_adapter = SimulationTruthV1Adapter()
