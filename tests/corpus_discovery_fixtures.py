"""Shared synthetic simulation-package fixture builders for
test_corpus_discovery.py and test_corpus_registration.py -- small,
test-only, shaped exactly like the real external Simulation Factory
contract (see app/ground_truth_validation/corpus_discovery.py's own header
comment). Never the real, un-committed corpus."""

import hashlib
import json
from pathlib import Path


def write_customer_data(pkg_dir: Path, files: dict[str, str] | None = None) -> None:
    customer_dir = pkg_dir / "customer-data"
    customer_dir.mkdir(parents=True, exist_ok=True)
    for name, content in (files or {"events.csv": "a,b\n1,2\n"}).items():
        (customer_dir / name).write_text(content)


def write_valid_truth(
    pkg_dir: Path, simulation_id: str = "SIM-TEST-FAMILY-001", leakage_value: float = 100.0
) -> None:
    hidden_truth = pkg_dir / "hidden-truth"
    hidden_truth.mkdir(parents=True, exist_ok=True)
    documents = {
        "expected_findings.json": {
            "expected_findings": [
                {
                    "finding_id": "EF-LK-1",
                    "scenario_id": "test_scenario",
                    "affected_records": ["A-1"],
                    "expected_severity": "MEDIUM",
                    "expected_value": leakage_value,
                    "expected_detection_family": "MAINTENANCE_ECONOMICS",
                }
            ]
        },
        "leakage_truth.json": {
            "leakage": [
                {
                    "leakage_id": "LK-1",
                    "scenario_id": "test_scenario",
                    "true_leakage_value": leakage_value,
                    "expected_detection_family": "MAINTENANCE_ECONOMICS",
                }
            ]
        },
        "causal_truth.json": {"causal": []},
        "data_quality_truth.json": {"data_quality": []},
    }
    files_hashes = []
    for name, content in documents.items():
        path = hidden_truth / name
        text = json.dumps(content)
        path.write_text(text)
        files_hashes.append(
            {"file": f"hidden-truth/{name}", "sha256": hashlib.sha256(text.encode()).hexdigest()}
        )
    manifest = {
        "simulation_id": simulation_id,
        "sealed_at": "2026-08-30T00:00:00.000Z",
        "summary": {"leakage_count": 1, "total_true_leakage_value": leakage_value},
        "files": files_hashes,
    }
    (hidden_truth / "truth_manifest.json").write_text(json.dumps(manifest))


def valid_package(
    root: Path, family: str, simulation_id: str, leakage_value: float = 100.0
) -> Path:
    pkg_dir = root / family / simulation_id
    write_customer_data(pkg_dir)
    write_valid_truth(pkg_dir, simulation_id, leakage_value)
    return pkg_dir
