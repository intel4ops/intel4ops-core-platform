from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

# ---------------------------------------------------------------------------
# P3.xxV.1A: Validation-only folder discovery for the external Intel4Ops
# Simulation Factory corpus. Framework-free (no SQLAlchemy/FastAPI import,
# no DB access) -- pure filesystem + hashlib, mirroring
# app/ground_truth_validation/integrity.py's own "generic, adapter-agnostic
# checks" convention. Lives under app/ground_truth_validation/ specifically
# so it inherits that package's existing release-blocking import-boundary
# guarantee (tests/test_validation_import_boundary.py's blanket
# "app.ground_truth_validation" forbidden-prefix check already covers this
# module -- no separate guardrail needed for that half of the boundary).
#
# Reconciled folder contract (verified directly against real sealed
# packages, not assumed):
#   <package_root>/
#     customer-data/*.csv          -- production-facing source files ONLY
#     hidden-truth/truth_manifest.json
#     hidden-truth/expected_findings.json   {"expected_findings": [...]}
#     hidden-truth/leakage_truth.json       {"leakage": [...]}
#     hidden-truth/causal_truth.json        {"causal": [...]}
#     hidden-truth/data_quality_truth.json  {"data_quality": [...]}
#     manifest/customer_data_manifest.json  (customer-data's own manifest --
#                                             not consulted here; that's a
#                                             production-ingestion concern)
#     reports/simulation_generation_report.json  (generator/seal provenance)
#     simulation-spec/scenario.yaml               (JSON-compatible YAML)
#
# No simulation.json exists in the real corpus today -- business_type,
# generator_version, capability_registry_version/hash, and simulation_id
# are already carried by reports/simulation_generation_report.json and
# hidden-truth/truth_manifest.json, so this module reads those rather than
# inventing a new required file. A future simulation.json (section 5) can
# be layered in as an additional/overriding metadata source without
# changing this module's public shape.
# ---------------------------------------------------------------------------

_TRUTH_DOCUMENT_FILES = (
    "expected_findings.json",
    "leakage_truth.json",
    "causal_truth.json",
    "data_quality_truth.json",
)
_TRUTH_MANIFEST_FILE = "truth_manifest.json"

# authored key -> the flat list each holds (section: adapter contract --
# mirrors adapters/simulation_truth_v1.py's own expected `documents` role
# names exactly; the wrapper key inside each file is this schema's own
# convention, not the adapter's).
_TRUTH_DOCUMENT_WRAPPER_KEYS = {
    "expected_findings.json": ("expected_findings", "expected_findings"),
    "leakage_truth.json": ("leakage", "leakage_truth"),
    "causal_truth.json": ("causal", "causal_truth"),
    "data_quality_truth.json": ("data_quality", "data_quality_truth"),
}


class PackageStatus(StrEnum):
    READY = "READY"
    INVALID = "INVALID"
    UNSEALED = "UNSEALED"
    MISSING_CUSTOMER_DATA = "MISSING_CUSTOMER_DATA"
    MISSING_TRUTH = "MISSING_TRUTH"
    HASH_MISMATCH = "HASH_MISMATCH"
    UNSUPPORTED_SCHEMA = "UNSUPPORTED_SCHEMA"


@dataclass(frozen=True)
class ExternalSimulationPackage:
    simulation_id: str
    family: str  # the package's parent directory name -- structural, never hard-coded
    package_reference: str  # path relative to the corpus root that was scanned
    package_status: PackageStatus
    status_detail: str

    customer_artifact_references: tuple[str, ...] = field(default_factory=tuple)
    truth_manifest_reference: str | None = None
    expected_findings_reference: str | None = None
    leakage_truth_reference: str | None = None
    causal_truth_reference: str | None = None
    data_quality_truth_reference: str | None = None

    generator_version: str | None = None
    registry_version: str | None = None
    registry_hash: str | None = None
    seed: str | None = None
    sealed_at: str | None = None
    business_type: str | None = None
    leakage_count: int | None = None
    total_true_leakage_value: float | None = None
    truth_schema_version: str = "intel4ops_simulation_truth_v1"
    adapter_code: str = "intel4ops_simulation_truth_v1"

    def build_ground_truth_payload(self, package_root: Path) -> dict[str, object]:
        """Assembles the exact GroundTruthPackageUploadV2 envelope shape
        ValidationService.upload_ground_truth() expects: {manifest,
        documents: {role: [...]}}. Only callable on a READY package -- the
        caller is responsible for checking package_status first (this
        method does not re-validate)."""
        manifest = json.loads((package_root / "hidden-truth" / _TRUTH_MANIFEST_FILE).read_text())
        documents: dict[str, object] = {}
        for filename, (wrapper_key, doc_role) in _TRUTH_DOCUMENT_WRAPPER_KEYS.items():
            raw = json.loads((package_root / "hidden-truth" / filename).read_text())
            documents[doc_role] = raw[wrapper_key]
        return {"schema_version": None, "manifest": manifest, "documents": documents}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_package(package_dir: Path, corpus_root: Path) -> ExternalSimulationPackage:
    family = package_dir.parent.name
    folder_simulation_id = package_dir.name
    reference = str(package_dir.relative_to(corpus_root)).replace("\\", "/")

    customer_data_dir = package_dir / "customer-data"
    hidden_truth_dir = package_dir / "hidden-truth"

    def _package(
        status: PackageStatus, detail: str, **overrides: object
    ) -> ExternalSimulationPackage:
        return ExternalSimulationPackage(
            simulation_id=folder_simulation_id,
            family=family,
            package_reference=reference,
            package_status=status,
            status_detail=detail,
            **overrides,  # type: ignore[arg-type]
        )

    if not customer_data_dir.is_dir() or not any(customer_data_dir.iterdir()):
        return _package(PackageStatus.MISSING_CUSTOMER_DATA, "customer-data/ is missing or empty")

    customer_artifacts = tuple(sorted(p.name for p in customer_data_dir.iterdir() if p.is_file()))

    if not hidden_truth_dir.is_dir():
        return _package(
            PackageStatus.MISSING_TRUTH,
            "hidden-truth/ directory is missing",
            customer_artifact_references=customer_artifacts,
        )

    manifest_path = hidden_truth_dir / _TRUTH_MANIFEST_FILE
    missing_docs = [
        f
        for f in (_TRUTH_MANIFEST_FILE, *_TRUTH_DOCUMENT_FILES)
        if not (hidden_truth_dir / f).is_file()
    ]
    if missing_docs:
        return _package(
            PackageStatus.MISSING_TRUTH,
            f"hidden-truth/ is missing required document(s): {', '.join(missing_docs)}",
            customer_artifact_references=customer_artifacts,
        )

    # section 6: structural allow-list -- no hidden-truth filename may ever
    # appear in the customer-data ingestion set, checked directly against
    # the actual directory listings, not inferred from convention.
    hidden_truth_filenames = {p.name for p in hidden_truth_dir.iterdir() if p.is_file()}
    overlap = hidden_truth_filenames & set(customer_artifacts)
    if overlap:
        return _package(
            PackageStatus.INVALID,
            f"hidden-truth filename(s) also present in customer-data/: {sorted(overlap)}",
            customer_artifact_references=customer_artifacts,
        )

    try:
        manifest = json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return _package(
            PackageStatus.INVALID,
            f"truth_manifest.json could not be parsed: {exc}",
            customer_artifact_references=customer_artifacts,
        )

    manifest_simulation_id = manifest.get("simulation_id")
    if not isinstance(manifest_simulation_id, str) or not manifest_simulation_id:
        return _package(
            PackageStatus.INVALID,
            "truth_manifest.json has no simulation_id",
            customer_artifact_references=customer_artifacts,
        )
    if manifest_simulation_id != folder_simulation_id:
        return _package(
            PackageStatus.INVALID,
            f"folder name {folder_simulation_id!r} does not match "
            f"truth_manifest.json simulation_id {manifest_simulation_id!r}",
            customer_artifact_references=customer_artifacts,
        )

    sealed_at = manifest.get("sealed_at")
    if not isinstance(sealed_at, str) or not sealed_at:
        return _package(
            PackageStatus.UNSEALED,
            "truth_manifest.json has no sealed_at timestamp",
            customer_artifact_references=customer_artifacts,
        )

    manifest_files = manifest.get("files")
    if not isinstance(manifest_files, list) or not manifest_files:
        return _package(
            PackageStatus.INVALID,
            "truth_manifest.json has no files[] hash inventory",
            customer_artifact_references=customer_artifacts,
        )
    for entry in manifest_files:
        rel_file = entry.get("file") if isinstance(entry, dict) else None
        expected_hash = entry.get("sha256") if isinstance(entry, dict) else None
        if not isinstance(rel_file, str) or not isinstance(expected_hash, str):
            return _package(
                PackageStatus.INVALID,
                f"truth_manifest.json files[] entry malformed: {entry!r}",
                customer_artifact_references=customer_artifacts,
            )
        target = package_dir / rel_file
        if not target.is_file():
            return _package(
                PackageStatus.HASH_MISMATCH,
                f"manifest-listed file missing on disk: {rel_file}",
                customer_artifact_references=customer_artifacts,
            )
        if _sha256(target) != expected_hash:
            return _package(
                PackageStatus.HASH_MISMATCH,
                f"sha256 mismatch for {rel_file} -- truth package may be tampered",
                customer_artifact_references=customer_artifacts,
            )

    # shape-detection against the one adapter this module knows about --
    # a package using a genuinely different schema is UNSUPPORTED_SCHEMA,
    # never silently coerced.
    try:
        findings_doc = json.loads((hidden_truth_dir / "expected_findings.json").read_text())
        findings_list = findings_doc.get("expected_findings")
    except (json.JSONDecodeError, OSError):
        findings_list = None
    if not (
        isinstance(findings_list, list)
        and findings_list
        and isinstance(findings_list[0], dict)
        and "finding_id" in findings_list[0]
        and "expected_severity" in findings_list[0]
    ):
        return _package(
            PackageStatus.UNSUPPORTED_SCHEMA,
            "expected_findings.json does not match the intel4ops_simulation_truth_v1 shape",
            customer_artifact_references=customer_artifacts,
        )

    summary = manifest.get("summary") if isinstance(manifest.get("summary"), dict) else {}

    return _package(
        PackageStatus.READY,
        "all package validation checks passed",
        customer_artifact_references=customer_artifacts,
        truth_manifest_reference=f"{reference}/hidden-truth/{_TRUTH_MANIFEST_FILE}",
        expected_findings_reference=f"{reference}/hidden-truth/expected_findings.json",
        leakage_truth_reference=f"{reference}/hidden-truth/leakage_truth.json",
        causal_truth_reference=f"{reference}/hidden-truth/causal_truth.json",
        data_quality_truth_reference=f"{reference}/hidden-truth/data_quality_truth.json",
        sealed_at=sealed_at,
        leakage_count=summary.get("leakage_count")
        if isinstance(summary.get("leakage_count"), int)
        else None,
        total_true_leakage_value=float(summary["total_true_leakage_value"])
        if isinstance(summary.get("total_true_leakage_value"), (int, float))
        else None,
        **_generation_report_fields(package_dir),
    )


def _generation_report_fields(package_dir: Path) -> dict[str, object]:
    report_path = package_dir / "reports" / "simulation_generation_report.json"
    if not report_path.is_file():
        return {}
    try:
        report = json.loads(report_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return {
        "generator_version": report.get("generator_version"),
        "registry_version": report.get("capability_registry_version"),
        "registry_hash": report.get("capability_registry_hash"),
        "seed": report.get("random_seed"),
        "business_type": report.get("business_type"),
    }


class SimulationCorpusDiscovery:
    """Recursive, structure-based scan: any directory containing a
    `customer-data/` or `hidden-truth/` subdirectory is treated as a
    candidate simulation package, at whatever depth it's found -- no
    hard-coded corpus layout, no hard-coded simulation ID list, no
    assumption about how many business-type/family levels sit above it.
    Deterministic ordering (sorted by package_reference). A directory that
    isn't a candidate (no customer-data/ or hidden-truth/ child) is
    descended into further but never itself reported. Non-directory
    entries (e.g. a sibling .zip export) are skipped, never crash the scan."""

    def discover(self, corpus_root: str | Path) -> list[ExternalSimulationPackage]:
        root = Path(corpus_root)
        if not root.is_dir():
            return []
        candidates = sorted(self._find_candidate_dirs(root), key=lambda p: str(p))
        return [_validate_package(candidate, root) for candidate in candidates]

    def _find_candidate_dirs(self, node: Path) -> list[Path]:
        found: list[Path] = []
        try:
            children = sorted(node.iterdir(), key=lambda p: p.name)
        except OSError:
            return found
        for child in children:
            if not child.is_dir():
                continue
            if (child / "customer-data").is_dir() or (child / "hidden-truth").is_dir():
                found.append(child)
                continue  # a package directory is a leaf -- never scan inside it further
            found.extend(self._find_candidate_dirs(child))
        return found


default_simulation_corpus_discovery = SimulationCorpusDiscovery()
