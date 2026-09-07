from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from uuid import UUID, uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi.testclient import TestClient

from app.storage.local_storage import LocalFileStorage
from app.validation_program.batch_controller import SimulationBatchController
from app.validation_program.simulation_package_staging import (
    SimulationPackageStagingError,
    SimulationPackageStagingService,
)


def _create_organization(client: TestClient, slug: str) -> UUID:
    response = client.post(
        "/api/v1/organizations",
        json={
            "name": slug,
            "slug": f"{slug}-{uuid4().hex[:8]}",
            "country_code": "US",
            "default_currency": "USD",
            "timezone": "UTC",
        },
    )
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


def _valid_package_zip(simulation_id: str = "SIM-AC002A-001") -> bytes:
    prefix = f"Rental/{simulation_id}"
    documents: dict[str, bytes] = {
        f"{prefix}/customer-data/work_orders.csv": b"work_order_id,amount\nWO-1,100\n",
        f"{prefix}/hidden-truth/expected_findings.json": json.dumps(
            {
                "expected_findings": [
                    {
                        "finding_id": "F-1",
                        "expected_severity": "high",
                        "detection_family": "test_family",
                    }
                ]
            }
        ).encode(),
        f"{prefix}/hidden-truth/leakage_truth.json": b'{"leakage":[]}',
        f"{prefix}/hidden-truth/causal_truth.json": b'{"causal":[]}',
        f"{prefix}/hidden-truth/data_quality_truth.json": b'{"data_quality":[]}',
    }
    inventory = [
        {
            "file": path.removeprefix(f"{prefix}/"),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        for path, content in documents.items()
    ]
    documents[f"{prefix}/hidden-truth/truth_manifest.json"] = json.dumps(
        {
            "simulation_id": simulation_id,
            "sealed_at": "2026-09-07T00:00:00Z",
            "files": inventory,
            "summary": {"leakage_count": 0, "total_true_leakage_value": 0},
        }
    ).encode()

    buffer = io.BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for path, content in documents.items():
            archive.writestr(path, content)
    return buffer.getvalue()


def test_staging_accepts_exactly_one_sealed_package(tmp_path: Path) -> None:
    service = SimulationPackageStagingService(tmp_path, 10_000_000)
    staged = service.stage_zip(uuid4(), io.BytesIO(_valid_package_zip()))
    assert staged.package.simulation_id == "SIM-AC002A-001"
    assert staged.package.package_status.value == "READY"
    assert staged.package.customer_artifact_references == ("work_orders.csv",)


def test_staging_rejects_zip_path_traversal(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("../escape.txt", "no")
    buffer.seek(0)

    service = SimulationPackageStagingService(tmp_path, 10_000_000)
    with pytest.raises(SimulationPackageStagingError) as exc:
        service.stage_zip(uuid4(), buffer)
    assert exc.value.code == "UNSAFE_ARCHIVE_PATH"
    assert not (tmp_path / "escape.txt").exists()


def test_staging_rejects_an_archive_that_expands_past_the_configured_limit(
    tmp_path: Path,
) -> None:
    """A legitimate (honestly-labeled) archive whose declared uncompressed
    total exceeds the configured cap must be rejected before any bytes are
    written to disk. (A member lying about its own declared size to sneak
    a larger real payload past this pre-check was investigated and found
    not to be exploitable against the stdlib zipfile reader used here --
    CPython's ZipExtFile enforces the declared size/CRC-32 against the
    actual decompressed bytes on every read, independent of compression
    method, so a mismatched declared size surfaces as a corrupt-archive
    error rather than silently over-reading.)"""
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("payload.bin", b"\x00" * 5_000)
    buffer.seek(0)

    service = SimulationPackageStagingService(tmp_path, 1_000)
    with pytest.raises(SimulationPackageStagingError) as exc:
        service.stage_zip(uuid4(), buffer)
    assert exc.value.code == "ARCHIVE_EXPANDS_TOO_LARGE"
    assert not any(tmp_path.rglob("payload.bin"))


def test_admin_can_stage_one_package_over_http(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.validation_program import simulation_controller_routes

    org_id = _create_organization(client, "ac002a-stage")
    staging = SimulationPackageStagingService(tmp_path, 10_000_000)
    controller = SimulationBatchController(LocalFileStorage(str(tmp_path / "raw")))

    monkeypatch.setattr(simulation_controller_routes, "_staging_service", lambda: staging)
    monkeypatch.setattr(simulation_controller_routes, "_controller", lambda: controller)

    response = client.post(
        f"/api/v1/organizations/{org_id}/simulation-controller/batches/stage",
        data={"name": "AC-002A one-simulation proof"},
        files={"package": ("simulation.zip", _valid_package_zip(), "application/zip")},
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["status"] == "active"
    assert len(payload["items"]) == 1
    assert payload["items"][0]["simulation_id"] == "SIM-AC002A-001"


def test_batch_status_is_organization_scoped(client: TestClient) -> None:
    org_id = _create_organization(client, "ac002a-scope")
    response = client.get(f"/api/v1/organizations/{org_id}/simulation-controller/batches/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "BATCH_NOT_FOUND"
