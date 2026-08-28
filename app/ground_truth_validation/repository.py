from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ground_truth_validation import (
    ValidationExpectedFinding,
    ValidationGroundTruth,
    ValidationSimulation,
)

# The ONLY place ground truth is queryable. Production execution modules
# must never import this class (see the package docstring and
# tests/test_validation_import_boundary.py). Every read is logged --
# who/when/which simulation, never the ground-truth content itself.

_audit_log = logging.getLogger("app.ground_truth_validation.audit")


class ValidationGroundTruthRepository:
    def get_simulation(
        self, db: Session, organization_id: UUID, simulation_id: UUID
    ) -> ValidationSimulation | None:
        return db.scalar(
            select(ValidationSimulation).where(
                ValidationSimulation.organization_id == organization_id,
                ValidationSimulation.id == simulation_id,
            )
        )

    def get_simulation_by_code(
        self, db: Session, organization_id: UUID, simulation_code: str
    ) -> ValidationSimulation | None:
        return db.scalar(
            select(ValidationSimulation).where(
                ValidationSimulation.organization_id == organization_id,
                ValidationSimulation.simulation_code == simulation_code,
            )
        )

    def latest_ground_truth(
        self, db: Session, organization_id: UUID, simulation_id: UUID
    ) -> ValidationGroundTruth | None:
        ground_truth = db.scalar(
            select(ValidationGroundTruth)
            .where(
                ValidationGroundTruth.organization_id == organization_id,
                ValidationGroundTruth.simulation_id == simulation_id,
            )
            .order_by(ValidationGroundTruth.version.desc())
            .limit(1)
        )
        _audit_log.info(
            "ground_truth_read",
            extra={
                "organization_id": str(organization_id),
                "simulation_id": str(simulation_id),
                "found": ground_truth is not None,
            },
        )
        return ground_truth

    def get_ground_truth(
        self, db: Session, organization_id: UUID, ground_truth_id: UUID
    ) -> ValidationGroundTruth | None:
        ground_truth = db.scalar(
            select(ValidationGroundTruth).where(
                ValidationGroundTruth.organization_id == organization_id,
                ValidationGroundTruth.id == ground_truth_id,
            )
        )
        _audit_log.info(
            "ground_truth_read",
            extra={
                "organization_id": str(organization_id),
                "ground_truth_id": str(ground_truth_id),
            },
        )
        return ground_truth

    def list_expected_findings(
        self, db: Session, organization_id: UUID, ground_truth_id: UUID
    ) -> list[ValidationExpectedFinding]:
        return list(
            db.scalars(
                select(ValidationExpectedFinding).where(
                    ValidationExpectedFinding.organization_id == organization_id,
                    ValidationExpectedFinding.ground_truth_id == ground_truth_id,
                )
            ).all()
        )


validation_ground_truth_repository = ValidationGroundTruthRepository()
