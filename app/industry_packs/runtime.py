from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from sqlalchemy.orm import Session

from app.schemas.industry_packs import PackExecutionCreate
from app.schemas.job_to_cash import JobToCashRunCreate
from app.services.job_to_cash_orchestration_service import job_to_cash_orchestration_service

PackRuntime = Callable[
    [Session, UUID, PackExecutionCreate, UUID],
    dict[str, object],
]


class PackRuntimeRegistry:
    def __init__(self) -> None:
        self._runtimes: dict[str, PackRuntime] = {}

    def register(self, pack_code: str, runtime: PackRuntime) -> None:
        if pack_code in self._runtimes:
            raise ValueError(f"Pack runtime {pack_code} is already registered")
        self._runtimes[pack_code] = runtime

    def resolve(self, pack_code: str) -> PackRuntime | None:
        return self._runtimes.get(pack_code)


def execute_job_to_cash(
    db: Session,
    organization_id: UUID,
    payload: PackExecutionCreate,
    actor: UUID,
) -> dict[str, object]:
    request = JobToCashRunCreate.model_validate(
        {
            **payload.record,
            "idempotency_key": f"industry-pack:{payload.idempotency_key}",
        }
    )
    run = job_to_cash_orchestration_service.execute(db, organization_id, request, actor)
    return {
        "runtime": "wp_2_18_job_to_cash",
        "job_to_cash_run_id": str(run.id),
        "status": run.status,
        "currency_code": run.currency_code,
        "finding_count": len(run.findings),
        "finding_ids": run.reconciliation.get("finding_ids", []),
        "opportunity_ids": run.reconciliation.get("opportunity_ids", []),
        "reconciliation": run.reconciliation,
    }


pack_runtime_registry = PackRuntimeRegistry()
pack_runtime_registry.register("PACK-J2C", execute_job_to_cash)
