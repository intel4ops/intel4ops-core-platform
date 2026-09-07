"""AGENTIC-CONTROL-001 Phase H/I/J/K: the Simulation Controller.

A thin orchestration layer over already-existing, already-tested
infrastructure -- this module does not re-implement corpus discovery,
ground-truth registration, production execution, or scoring:

- Discovery:    app.ground_truth_validation.corpus_discovery.SimulationCorpusDiscovery
- Registration: app.ground_truth_validation.service.validation_service.register_corpus
- Run + score:  app.validation_program.wave_coordinator.wave_coordinator (already
                calls analysis_case_orchestration_service.execute() synchronously,
                then validation_service.validate_run() -- see that module's own
                docstring for why synchronous-in-process sidesteps the
                RUN-RELIABILITY-001 BackgroundTasks failure mode entirely)

What is new here: a persistent micro-batch state machine (Phase H's 14
states plus an honest BLOCKED state), the 5-simulation micro-batch
cadence with safety-gate pausing (Phase I), AgentJob-driven miss
classification (Phase J: one job per reusable truth family, never one
per raw truth item or one gap per simulation), and the owner-approval
DecisionPackage gate (Phase K). No remediation code is ever proposed or
written by this controller -- v1 stops at OWNER_REVIEW_REQUIRED.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ground_truth_validation.corpus_discovery import (
    ExternalSimulationPackage,
    PackageStatus,
    SimulationCorpusDiscovery,
)
from app.ground_truth_validation.repository import validation_ground_truth_repository
from app.ground_truth_validation.service import validation_service
from app.models.agent_jobs import AgentJobStatus
from app.models.entities import utc_now
from app.models.ground_truth_validation import (
    ValidationExpectedFinding,
    ValidationFindingMatch,
    ValidationLeakageTruth,
    ValidationMatchType,
)
from app.models.simulation_batch import (
    SimulationBatch,
    SimulationBatchItem,
    SimulationBatchItemState,
    SimulationBatchStatus,
)
from app.schemas.agent_jobs import (
    AgentJobCreate,
    EvidenceCodeContext,
    EvidenceControl,
    EvidenceEvidence,
    EvidenceImpact,
    EvidenceObservation,
    EvidencePackage,
    EvidenceSafety,
)
from app.services.agent_job_service import AgentJobService
from app.services.analysis_case_service import AnalysisCaseService, UploadedFile
from app.storage.base import StorageBackend
from app.validation_program.wave_coordinator import wave_coordinator

# Kept in sync with app.ground_truth_validation.service._TERMINAL_RUN_STATUSES
# by tests, not by importing that private module attribute directly.
_TERMINAL_RUN_STATUSES = frozenset(
    {"interrupted", "review_required", "partial", "completed", "failed", "cancelled"}
)

_DEFAULT_MICRO_BATCH_SIZE = 5


class SimulationControllerError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class TruthIsolationViolation(RuntimeError):
    """Raised if any code path attempts to read/score truth for an item
    that has not been frozen -- this must never be caught and silently
    ignored anywhere in this codebase."""


class SimulationBatchController:
    def __init__(self, storage: StorageBackend) -> None:
        self._storage = storage
        self._case_service = AnalysisCaseService(storage=storage)
        self._agent_jobs = AgentJobService(storage=storage)

    # -- discovery -----------------------------------------------------
    def discover_candidates(
        self, db: Session, organization_id: UUID, corpus_root: str | Path
    ) -> list[ExternalSimulationPackage]:
        packages = SimulationCorpusDiscovery().discover(corpus_root)
        already_tracked = set(
            db.scalars(
                select(SimulationBatchItem.simulation_id).where(
                    SimulationBatchItem.organization_id == organization_id
                )
            ).all()
        )
        return [
            p
            for p in packages
            if p.package_status == PackageStatus.READY and p.simulation_id not in already_tracked
        ]

    # -- Phase I: micro-batch selection ---------------------------------
    def select_batch(
        self,
        db: Session,
        organization_id: UUID,
        corpus_root: str | Path,
        actor_user_id: UUID,
        name: str,
        batch_size: int = _DEFAULT_MICRO_BATCH_SIZE,
    ) -> SimulationBatch:
        if self._has_open_safety_gate(db, organization_id):
            raise SimulationControllerError(
                "SAFETY_GATE_OPEN",
                "Cannot start a new batch while a prior batch is paused on a safety gate or "
                "awaiting owner review",
                409,
            )
        candidates = self.discover_candidates(db, organization_id, corpus_root)[:batch_size]
        if not candidates:
            raise SimulationControllerError(
                "NO_CANDIDATES", "No unregistered, sealed simulations found", 404
            )
        batch = SimulationBatch(
            organization_id=organization_id,
            name=name,
            status=SimulationBatchStatus.ACTIVE.value,
            created_by_user_id=actor_user_id,
        )
        db.add(batch)
        db.flush()
        for package in candidates:
            db.add(
                SimulationBatchItem(
                    batch_id=batch.id,
                    organization_id=organization_id,
                    simulation_id=package.simulation_id,
                    state=SimulationBatchItemState.SELECTED.value,
                )
            )
        db.commit()
        return batch

    def _has_open_safety_gate(self, db: Session, organization_id: UUID) -> bool:
        return (
            db.scalar(
                select(SimulationBatch.id).where(
                    SimulationBatch.organization_id == organization_id,
                    SimulationBatch.status.in_(
                        [
                            SimulationBatchStatus.PAUSED_SAFETY_GATE.value,
                            SimulationBatchStatus.OWNER_REVIEW_REQUIRED.value,
                        ]
                    ),
                )
            )
            is not None
        )

    # -- Phase H: prepare (IMPORTING) + run (PRODUCTION_RUNNING..SCORED) --
    def prepare_batch(
        self, db: Session, batch_id: UUID, corpus_root: str | Path, actor_user_id: UUID
    ) -> None:
        """CONNECT stage only: creates the AnalysisCase, uploads
        customer-data-only artifacts (never hidden-truth files), and
        registers ground truth via the existing, one-way
        `register_corpus` -- this method never reads truth content
        itself, only file paths under `customer-data/`."""
        root = Path(corpus_root)
        batch = self._get_batch(db, batch_id)
        packages = {p.simulation_id: p for p in SimulationCorpusDiscovery().discover(root)}
        items = list(
            db.scalars(select(SimulationBatchItem).where(SimulationBatchItem.batch_id == batch_id))
        )
        case_ids_by_simulation: dict[str, UUID] = {}

        for item in items:
            if item.state != SimulationBatchItemState.SELECTED.value:
                continue
            package = packages.get(item.simulation_id)
            if package is None:
                item.state = SimulationBatchItemState.BLOCKED.value
                item.block_reason = "package no longer discoverable at corpus_root"
                continue
            item.state = SimulationBatchItemState.IMPORTING.value
            case = self._case_service.create(
                db,
                item.organization_id,
                f"AC001-{item.simulation_id}",
                "orchestrated",
                actor_user_id,
            )
            item.analysis_case_id = case.id
            # customer_artifact_references are bare filenames within the
            # package's own customer-data/ directory (see
            # SimulationCorpusDiscovery/_validate_package) -- never
            # anything under hidden-truth/, which this method never reads.
            customer_data_dir = root / package.package_reference / "customer-data"
            uploaded = [
                UploadedFile(filename, (customer_data_dir / filename).read_bytes())
                for filename in package.customer_artifact_references
            ]
            self._case_service.register_artifacts(
                db, item.organization_id, case.id, uploaded, actor_user_id
            )
            case_ids_by_simulation[item.simulation_id] = case.id

        db.commit()

        if not case_ids_by_simulation:
            return

        registration = validation_service.register_corpus(
            db, batch.organization_id, root, case_ids_by_simulation, actor_user_id
        )
        registered_ok = {
            o.simulation_id
            for o in registration.outcomes
            if o.outcome in ("newly_registered", "already_registered")
        }
        for item in items:
            if item.analysis_case_id is None:
                continue
            if item.simulation_id not in registered_ok:
                item.state = SimulationBatchItemState.BLOCKED.value
                item.block_reason = "ground truth registration did not succeed"
        db.commit()

    def run_batch(self, db: Session, batch_id: UUID, actor_user_id: UUID) -> None:
        """Runs production + validation for every item that reached
        IMPORTING successfully. Delegates entirely to `wave_coordinator`
        (already synchronous, already calls `validate_run()` which
        itself enforces the terminal-status gate) -- never fabricates a
        terminal status for an item that isn't genuinely there (Phase H:
        "never fabricate terminal status")."""
        batch = self._get_batch(db, batch_id)
        items = {
            i.simulation_id: i
            for i in db.scalars(
                select(SimulationBatchItem).where(SimulationBatchItem.batch_id == batch_id)
            )
            if i.analysis_case_id is not None
            and i.state == SimulationBatchItemState.IMPORTING.value
        }
        if not items:
            return
        for item in items.values():
            item.state = SimulationBatchItemState.PRODUCTION_RUNNING.value
        db.commit()

        case_ids_by_simulation: dict[str, UUID] = {
            sim: item.analysis_case_id
            for sim, item in items.items()
            if item.analysis_case_id is not None
        }
        summary = wave_coordinator.run_wave(
            db, self._storage, batch.organization_id, case_ids_by_simulation, actor_user_id
        )

        for result in summary.results:
            item = items[result.simulation_code]
            item.run_id = result.analysis_case_run_id
            if result.outcome in ("scored", "already_scored"):
                simulation = validation_ground_truth_repository.get_simulation_by_code(
                    db, batch.organization_id, result.simulation_code
                )
                item.validation_simulation_id = simulation.id if simulation else None
                item.state = SimulationBatchItemState.TERMINAL.value
                self._freeze_and_score(db, item, batch.organization_id)
            else:
                # run_failed / validation_failed / not_registered -- an
                # honest, explicit block. Never silently marked TERMINAL
                # or SCORED (this is exactly the discipline
                # RUN-RELIABILITY-001 found missing on the production
                # run-status path).
                item.state = SimulationBatchItemState.BLOCKED.value
                item.block_reason = f"{result.outcome}: {result.detail}"
        db.commit()

    def _freeze_and_score(
        self, db: Session, item: SimulationBatchItem, organization_id: UUID
    ) -> None:
        # FROZEN is only reachable once wave_coordinator has already
        # confirmed a terminal, validated run (validate_run() itself
        # raises if the run is not terminal -- see
        # app.ground_truth_validation.service._TERMINAL_RUN_STATUSES).
        item.state = SimulationBatchItemState.FROZEN.value
        item.frozen_at = utc_now()
        item.state = SimulationBatchItemState.VALIDATING.value

        assert item.validation_simulation_id is not None  # set moments earlier in run_batch
        results = validation_service.get_results(db, organization_id, item.validation_simulation_id)
        if not results:
            item.state = SimulationBatchItemState.BLOCKED.value
            item.block_reason = "validation reported success but no ValidationScore was found"
            return
        _run, score, _dimensions, _matches = results[-1]
        item.truth_accessed_at = utc_now()
        if score is not None:
            item.true_positive_count = score.true_positive_count
            item.false_positive_count = score.false_positive_count
            item.false_negative_count = score.false_negative_count
            item.precision = score.precision
            item.recall = score.recall
        item.scored_at = utc_now()
        item.state = SimulationBatchItemState.SCORED.value

    def _resolve_family_and_value(
        self, db: Session, miss: ValidationFindingMatch
    ) -> tuple[str, float | None, str | None]:
        """A single missed scenario is often expressed on both the
        FINDING_DETECTION and LEAKAGE_VALUE dimensions (see
        ValidationFindingMatch's own docstring) -- resolve whichever side
        this particular match row is linked to so both dimensions of the
        same underlying miss land in the same reusable-gap-family
        bucket, never split into two spurious jobs for one real miss."""
        if miss.expected_finding_id is not None:
            expected = db.get(ValidationExpectedFinding, miss.expected_finding_id)
            if expected is not None:
                value = (
                    float(expected.expected_economic_impact)
                    if expected.expected_economic_impact
                    else None
                )
                return (
                    expected.expected_detection_family or "UNSPECIFIED",
                    value,
                    expected.currency,
                )
        if miss.expected_leakage_truth_id is not None:
            leakage = db.get(ValidationLeakageTruth, miss.expected_leakage_truth_id)
            if leakage is not None:
                value = float(leakage.true_leakage_value) if leakage.true_leakage_value else None
                return (leakage.detection_family or "UNSPECIFIED", value, leakage.currency)
        return ("UNSPECIFIED", None, None)

    # -- Phase J: miss classification (Qwen R0) -------------------------
    def create_miss_classification_jobs(
        self, db: Session, batch_id: UUID, created_by_user_id: UUID | None
    ) -> list[UUID]:
        """One R0 AgentJob per reusable truth *family* per simulation --
        never one per raw truth item (would create job-volume noise) and
        never one gap per simulation (Phase J's explicit prohibition;
        gap clustering happens later, across jobs, in
        `build_decision_package`). Guarded: only items already at SCORED
        (i.e. already frozen) are eligible -- this is the one place a
        `validation`-plane EvidencePackage may legally be constructed."""
        items = list(
            db.scalars(
                select(SimulationBatchItem).where(
                    SimulationBatchItem.batch_id == batch_id,
                    SimulationBatchItem.state == SimulationBatchItemState.SCORED.value,
                )
            )
        )
        created_job_ids: list[UUID] = []
        for item in items:
            if item.frozen_at is None:
                # Structurally unreachable given the state filter above,
                # but checked explicitly -- this is the truth-isolation
                # invariant that must never be bypassed.
                raise TruthIsolationViolation(
                    f"simulation_batch_item {item.id} reached SCORED without frozen_at set"
                )
            assert item.validation_simulation_id is not None  # set once TERMINAL is reached
            results = validation_service.get_results(
                db, item.organization_id, item.validation_simulation_id
            )
            if not results:
                continue
            _run, _score, _dimensions, matches = results[-1]
            misses = [
                m for m in matches if m.match_type == ValidationMatchType.FALSE_NEGATIVE.value
            ]
            by_family: dict[str, list] = defaultdict(list)
            for miss in misses:
                family, _value, _currency = self._resolve_family_and_value(db, miss)
                by_family[family].append(miss)

            for family, family_misses in by_family.items():
                total_value = 0.0
                currency = None
                for miss in family_misses:
                    _family, value, miss_currency = self._resolve_family_and_value(db, miss)
                    if value is not None:
                        total_value += value
                        currency = currency or miss_currency

                item.state = SimulationBatchItemState.MISS_CLASSIFICATION.value
                package = EvidencePackage(
                    work_item_id=f"{item.simulation_id}:{family}",
                    evidence_plane="validation",
                    simulation_ids=[item.simulation_id],
                    analysis_case_ids=[str(item.analysis_case_id)],
                    run_ids=[str(item.run_id)] if item.run_id else [],
                    risk_class="R0",
                    observation=EvidenceObservation(
                        observed_behavior=(
                            f"{len(family_misses)} expected finding(s) in family {family!r} "
                            "were not produced by production for this simulation"
                        ),
                        expected_capability_behavior=None,
                    ),
                    impact=EvidenceImpact(
                        affected_items=len(family_misses),
                        affected_economic_value=total_value if total_value else None,
                        currency=currency,
                        simulations_affected=1,
                    ),
                    evidence=EvidenceEvidence(
                        production_output_refs=[str(item.run_id)] if item.run_id else [],
                    ),
                    control=EvidenceControl(),
                    safety=EvidenceSafety(fp_exposure="low"),
                    code_context=EvidenceCodeContext(),
                    question=(
                        f"Classify the reusable gap family for {len(family_misses)} missed "
                        f"finding(s) (family={family!r}) in simulation {item.simulation_id}. "
                        "Return the structured gap-classification result."
                    ),
                )
                job = self._agent_jobs.create_job(
                    db,
                    item.organization_id,
                    AgentJobCreate(
                        job_type="MISS_CLASSIFICATION",
                        risk_class="R0",
                        requested_capability="gap_classification_v1",
                        evidence_plane="validation",
                        analysis_case_id=item.analysis_case_id,
                        run_id=item.run_id,
                        simulation_id=item.simulation_id,
                        evidence_package=package,
                        client_idempotency_key=f"miss-classify:{item.id}:{family}",
                    ),
                    created_by_user_id,
                )
                created_job_ids.append(job.id)
        db.commit()
        return created_job_ids

    # -- Phase J/K: gap clustering + decision package --------------------
    def build_decision_package(self, db: Session, batch_id: UUID) -> str:
        from app.models.agent_jobs import AgentJob

        batch = self._get_batch(db, batch_id)
        jobs = list(
            db.scalars(
                select(AgentJob).where(
                    AgentJob.organization_id == batch.organization_id,
                    AgentJob.job_type == "MISS_CLASSIFICATION",
                    AgentJob.status.in_(
                        [AgentJobStatus.SUCCEEDED.value, AgentJobStatus.ESCALATED.value]
                    ),
                )
            )
        )
        clusters: dict[str, dict] = defaultdict(
            lambda: {"gap_class": None, "jobs": [], "simulations": set(), "total_value": 0.0}
        )
        for job in jobs:
            if job.simulation_id:
                pass
            if job.result_ref is None:
                continue
            result = self._agent_jobs._read_json(job.result_ref)  # noqa: SLF001 -- controller-internal read
            gap_class = result.get("primary_gap_class", "UNSPECIFIED")
            cluster = clusters[gap_class]
            cluster["gap_class"] = gap_class
            cluster["jobs"].append(str(job.id))
            if job.simulation_id:
                cluster["simulations"].add(job.simulation_id)

        items = list(
            db.scalars(select(SimulationBatchItem).where(SimulationBatchItem.batch_id == batch_id))
        )
        decision_package = {
            "batch_id": str(batch_id),
            "generated_at": utc_now().isoformat(),
            "items": [
                {
                    "simulation_id": i.simulation_id,
                    "state": i.state,
                    "true_positive_count": i.true_positive_count,
                    "false_positive_count": i.false_positive_count,
                    "false_negative_count": i.false_negative_count,
                    "precision": i.precision,
                    "recall": i.recall,
                }
                for i in items
            ],
            "gap_clusters": [
                {
                    "gap_class": gap_class,
                    "job_ids": cluster["jobs"],
                    "simulations_affected": sorted(cluster["simulations"]),
                    "job_count": len(cluster["jobs"]),
                }
                for gap_class, cluster in clusters.items()
            ],
            "recommendation": (
                "OWNER_REVIEW_REQUIRED -- no remediation implementation proposed by v1 controller"
            ),
        }
        ref = self._agent_jobs._write_json(  # noqa: SLF001 -- controller-internal write
            f"simulation-batches/{batch_id}/decision-package.json", decision_package
        )
        batch.decision_package_ref = ref
        batch.status = SimulationBatchStatus.OWNER_REVIEW_REQUIRED.value
        for item in items:
            if item.state == SimulationBatchItemState.MISS_CLASSIFICATION.value:
                item.state = SimulationBatchItemState.GAP_CLUSTERING.value
        db.commit()
        return ref

    # -- Phase I: safety gate --------------------------------------------
    def pause_for_safety(self, db: Session, batch_id: UUID, reason: str) -> None:
        batch = self._get_batch(db, batch_id)
        batch.status = SimulationBatchStatus.PAUSED_SAFETY_GATE.value
        batch.safety_gate_reason = reason
        db.commit()

    def _get_batch(self, db: Session, batch_id: UUID) -> SimulationBatch:
        batch = db.get(SimulationBatch, batch_id)
        if batch is None:
            raise SimulationControllerError("BATCH_NOT_FOUND", "Simulation batch not found", 404)
        return batch


def build_simulation_batch_controller(storage: StorageBackend) -> SimulationBatchController:
    return SimulationBatchController(storage=storage)
