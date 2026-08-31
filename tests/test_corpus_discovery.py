"""P3.xxV.1A: Validation-only folder discovery for the external Simulation
Factory corpus. Uses small synthetic fixtures (never the real, un-committed
corpus) shaped exactly like the real contract reconciled directly against
sealed packages -- see app/ground_truth_validation/corpus_discovery.py's
own header comment for the reconciliation."""

import json
from pathlib import Path

from corpus_discovery_fixtures import valid_package, write_customer_data, write_valid_truth

from app.ground_truth_validation.corpus_discovery import (
    PackageStatus,
    SimulationCorpusDiscovery,
)


def test_a_discovers_valid_simulation_directories(tmp_path: Path) -> None:
    valid_package(tmp_path, "TestFamily", "SIM-TEST-FAMILY-001")
    valid_package(tmp_path, "TestFamily", "SIM-TEST-FAMILY-002")
    packages = SimulationCorpusDiscovery().discover(tmp_path)
    ids = {p.simulation_id for p in packages}
    assert ids == {"SIM-TEST-FAMILY-001", "SIM-TEST-FAMILY-002"}
    assert all(p.package_status == PackageStatus.READY for p in packages)


def test_b_unrelated_directory_ignored(tmp_path: Path) -> None:
    valid_package(tmp_path, "TestFamily", "SIM-TEST-FAMILY-001")
    (tmp_path / "TestFamily" / "not_a_simulation").mkdir(parents=True)
    (tmp_path / "TestFamily" / "not_a_simulation" / "readme.txt").write_text("hello")
    (tmp_path / "TestFamily.zip").write_bytes(b"PK\x03\x04")
    packages = SimulationCorpusDiscovery().discover(tmp_path)
    assert [p.simulation_id for p in packages] == ["SIM-TEST-FAMILY-001"]


def test_c_invalid_package_does_not_break_corpus_scan(tmp_path: Path) -> None:
    valid_package(tmp_path, "TestFamily", "SIM-TEST-FAMILY-001")
    broken_dir = tmp_path / "TestFamily" / "SIM-TEST-FAMILY-BROKEN"
    write_customer_data(broken_dir)  # no hidden-truth/ at all
    packages = SimulationCorpusDiscovery().discover(tmp_path)
    statuses = {p.simulation_id: p.package_status for p in packages}
    assert statuses["SIM-TEST-FAMILY-001"] == PackageStatus.READY
    assert statuses["SIM-TEST-FAMILY-BROKEN"] == PackageStatus.MISSING_TRUTH


def test_d_customer_truth_separation_enforced(tmp_path: Path) -> None:
    """A hidden-truth filename duplicated into customer-data/ must flip the
    package INVALID rather than silently including it in the customer
    artifact list."""
    pkg_dir = tmp_path / "TestFamily" / "SIM-TEST-FAMILY-001"
    write_customer_data(pkg_dir, {"events.csv": "a,b\n1,2\n", "truth_manifest.json": "{}"})
    write_valid_truth(pkg_dir)
    packages = SimulationCorpusDiscovery().discover(tmp_path)
    assert packages[0].package_status == PackageStatus.INVALID
    assert "truth_manifest.json" in packages[0].status_detail


def test_e_truth_file_cannot_enter_customer_artifact_list(tmp_path: Path) -> None:
    pkg_dir = valid_package(tmp_path, "TestFamily", "SIM-TEST-FAMILY-001")
    packages = SimulationCorpusDiscovery().discover(tmp_path)
    truth_filenames = {p.name for p in (pkg_dir / "hidden-truth").iterdir()}
    assert not (truth_filenames & set(packages[0].customer_artifact_references))


def test_f_valid_manifest_and_hash_accepted(tmp_path: Path) -> None:
    valid_package(tmp_path, "TestFamily", "SIM-TEST-FAMILY-001")
    packages = SimulationCorpusDiscovery().discover(tmp_path)
    assert packages[0].package_status == PackageStatus.READY
    assert packages[0].leakage_count == 1
    assert packages[0].total_true_leakage_value == 100.0


def test_g_tampered_hash_rejected(tmp_path: Path) -> None:
    pkg_dir = valid_package(tmp_path, "TestFamily", "SIM-TEST-FAMILY-001")
    (pkg_dir / "hidden-truth" / "leakage_truth.json").write_text(
        json.dumps({"leakage": [{"leakage_id": "LK-TAMPERED"}]})
    )
    packages = SimulationCorpusDiscovery().discover(tmp_path)
    assert packages[0].package_status == PackageStatus.HASH_MISMATCH


def test_h_simulation_id_mismatch_rejected(tmp_path: Path) -> None:
    pkg_dir = tmp_path / "TestFamily" / "SIM-TEST-FAMILY-001"
    write_customer_data(pkg_dir)
    write_valid_truth(pkg_dir, simulation_id="SIM-TEST-FAMILY-DIFFERENT")
    packages = SimulationCorpusDiscovery().discover(tmp_path)
    assert packages[0].package_status == PackageStatus.INVALID
    assert "does not match" in packages[0].status_detail


def test_i_unsealed_truth_not_certification_eligible(tmp_path: Path) -> None:
    pkg_dir = valid_package(tmp_path, "TestFamily", "SIM-TEST-FAMILY-001")
    manifest_path = pkg_dir / "hidden-truth" / "truth_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    del manifest["sealed_at"]
    manifest_path.write_text(json.dumps(manifest))
    packages = SimulationCorpusDiscovery().discover(tmp_path)
    # a mutated manifest also changes its own byte content, so hash
    # validation (which reads the CURRENT file) still passes -- the point
    # here is specifically that a manifest missing sealed_at is UNSEALED,
    # not that hashes must fail too.
    assert packages[0].package_status == PackageStatus.UNSEALED


def test_missing_customer_data(tmp_path: Path) -> None:
    pkg_dir = tmp_path / "TestFamily" / "SIM-TEST-FAMILY-001"
    write_valid_truth(pkg_dir)
    (pkg_dir / "customer-data").mkdir(parents=True)  # present but empty
    packages = SimulationCorpusDiscovery().discover(tmp_path)
    assert packages[0].package_status == PackageStatus.MISSING_CUSTOMER_DATA


def test_deterministic_ordering(tmp_path: Path) -> None:
    valid_package(tmp_path, "TestFamily", "SIM-TEST-FAMILY-002")
    valid_package(tmp_path, "TestFamily", "SIM-TEST-FAMILY-001")
    first = [p.simulation_id for p in SimulationCorpusDiscovery().discover(tmp_path)]
    second = [p.simulation_id for p in SimulationCorpusDiscovery().discover(tmp_path)]
    assert first == second == sorted(first)


def test_nonexistent_corpus_root_returns_empty(tmp_path: Path) -> None:
    assert SimulationCorpusDiscovery().discover(tmp_path / "does-not-exist") == []


def test_t_discovery_module_contains_no_hard_coded_simulation_identifiers() -> None:
    """The generic discovery/registration engine must work for ANY
    corpus member -- it must never special-case a specific simulation_id,
    family name, or business type."""
    import ast

    repo_root = Path(__file__).resolve().parent.parent
    for relative in (
        "app/ground_truth_validation/corpus_discovery.py",
        "app/ground_truth_validation/service.py",
    ):
        source = (repo_root / relative).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=relative)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert "SIM-OFS" not in node.value, f"{relative} contains a literal simulation ID"
                assert "FIELDMAINT" not in node.value, f"{relative} contains a hard-coded family"
                assert "RENTAL" not in node.value, f"{relative} contains a hard-coded family"
