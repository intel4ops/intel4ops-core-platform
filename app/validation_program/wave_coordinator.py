from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.orm import Session

from app.ground_truth_validation.repository import validation_ground_truth_repository
from app.ground_truth_validation.service import validation_service
from app.services.analysis_case_orchestration_service import analysis_case_orchestration_service
from app.storage.base import StorageBackend

# ---------------------------------------------------------------------------
# P3.xxV.1: the minimal Validation Program wave coordinator. Default
# concurrency is 1 by construction -- members are processed strictly in
# dict-iteration order, one full run-and-validate cycle at a time, never
# threaded or batched. This is deliberate: the Render starter-instance
# concurrency issue already observed elsewhere in this project makes
# sequential the only currently-safe default, and nothing here builds a
# generic workflow/scheduling platform.
#
# AnalysisCase creation and customer-data ingestion (AnalysisCaseService)
# happen BEFORE this coordinator is invoked, and simulation/ground-truth
# registration (ValidationService.register_corpus()) also happens before --
# case_ids_by_simulation is the coordinator's only input describing "what
# to run," not "how to set it up." This keeps each concern (ingest,
# register, execute+validate) independently testable and keeps this
# module's own responsibility narrow: launch a run, wait for it to finish
# (execute() is itself synchronous/blocking in this codebase, so no
# separate polling loop is needed locally), then validate it.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WaveMemberResult:
    simulation_code: str
    analysis_case_id: UUID
    analysis_case_run_id: UUID | None
    outcome: str  # scored | already_scored | not_registered | run_failed | validation_failed
    detail: str


@dataclass(frozen=True)
class WaveSummary:
    members: int = 0
    scored: int = 0
    already_scored: int = 0
    not_registered: int = 0
    failed: int = 0
    results: tuple[WaveMemberResult, ...] = field(default_factory=tuple)


class WaveCoordinator:
    def run_wave(
        self,
        db: Session,
        storage: StorageBackend,
        organization_id: UUID,
        case_ids_by_simulation: dict[str, UUID],
        actor_user_id: UUID,
    ) -> WaveSummary:
        results: list[WaveMemberResult] = []
        for simulation_code, case_id in case_ids_by_simulation.items():
            results.append(
                self._run_member(
                    db, storage, organization_id, simulation_code, case_id, actor_user_id
                )
            )

        counts = {"scored": 0, "already_scored": 0, "not_registered": 0, "failed": 0}
        for result in results:
            if result.outcome == "scored":
                counts["scored"] += 1
            elif result.outcome == "already_scored":
                counts["already_scored"] += 1
            elif result.outcome == "not_registered":
                counts["not_registered"] += 1
            else:
                counts["failed"] += 1

        return WaveSummary(
            members=len(results),
            scored=counts["scored"],
            already_scored=counts["already_scored"],
            not_registered=counts["not_registered"],
            failed=counts["failed"],
            results=tuple(results),
        )

    def _run_member(
        self,
        db: Session,
        storage: StorageBackend,
        organization_id: UUID,
        simulation_code: str,
        case_id: UUID,
        actor_user_id: UUID,
    ) -> WaveMemberResult:
        simulation = validation_ground_truth_repository.get_simulation_by_code(
            db, organization_id, simulation_code
        )
        if simulation is None:
            return WaveMemberResult(
                simulation_code,
                case_id,
                None,
                "not_registered",
                "no ValidationSimulation registered for this code -- run "
                "ValidationService.register_corpus() first",
            )

        # Resume-after-interruption (section 18/20-S): if this simulation
        # already has ANY prior validation result, treat the wave member as
        # already done and skip re-running it -- re-invoking run_wave with
        # the same members after a partial failure only processes the
        # remainder, never re-executes what already succeeded.
        existing = validation_service.get_results(db, organization_id, simulation.id)
        if existing:
            return WaveMemberResult(
                simulation_code,
                case_id,
                existing[-1][0].analysis_case_run_id,
                "already_scored",
                f"{len(existing)} prior validation result(s) already exist for this simulation",
            )

        try:
            run = analysis_case_orchestration_service.start_run(
                db, organization_id, case_id, actor_user_id
            )
            analysis_case_orchestration_service.execute(
                db, storage, organization_id, case_id, run.id, actor_user_id
            )
        except Exception as exc:  # noqa: BLE001 -- one bad member must not stop the wave
            return WaveMemberResult(
                simulation_code, case_id, None, "run_failed", f"production run failed: {exc}"
            )

        try:
            validation_service.validate_run(
                db, organization_id, simulation.id, run.id, actor_user_id
            )
        except Exception as exc:  # noqa: BLE001 -- one bad member must not stop the wave
            return WaveMemberResult(
                simulation_code, case_id, run.id, "validation_failed", f"validate_run failed: {exc}"
            )

        return WaveMemberResult(simulation_code, case_id, run.id, "scored", "validated")


wave_coordinator = WaveCoordinator()
