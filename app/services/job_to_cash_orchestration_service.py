from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engines.job_to_cash_engine import detect_job_to_cash
from app.models.gateway import JobToCashRecord, JobToCashRun
from app.models.source_system import SourceSystem
from app.schemas.commercial import UsageEventCreate
from app.schemas.contracts import EvidenceCreate, FindingCreate
from app.schemas.economics import FindingLinkCreate, OpportunityCreate
from app.schemas.job_to_cash import JobToCashRunCreate, JobToCashRunRead, LeakageRead
from app.services.commercial_service import CommercialServiceError, usage_meter_service
from app.services.economics_service import economics_service
from app.services.finding_service import FindingService


class JobToCashOrchestrationService:
    def execute(
        self, db: Session, org: UUID, payload: JobToCashRunCreate, actor: UUID
    ) -> JobToCashRunRead:
        existing = db.scalar(
            select(JobToCashRun).where(
                JobToCashRun.organization_id == org,
                JobToCashRun.idempotency_key == payload.idempotency_key,
            )
        )
        if existing is not None:
            return self._read(existing)
        if payload.source_system_id is not None:
            source = db.scalar(
                select(SourceSystem.id).where(
                    SourceSystem.id == payload.source_system_id,
                    SourceSystem.organization_id == org,
                )
            )
            if source is None:
                raise ValueError("Tenant-owned Job-to-Cash source system not found")
        records = [item.engine_record() for item in payload.records]
        leaks = detect_job_to_cash(records, payload.as_of)
        counts = Counter(item.type for item in payload.records)
        exposure = sum((item.exposure for item in leaks), Decimal())
        run = JobToCashRun(
            organization_id=org,
            source_system_id=payload.source_system_id,
            idempotency_key=payload.idempotency_key,
            status="completed",
            currency_code=payload.currency_code,
            source_totals={"records": len(records), "by_type": dict(counts)},
            reconciliation={
                "finding_count": len(leaks),
                "finding_exposure": str(exposure),
                "findings": [
                    {
                        "code": item.code,
                        "job_id": item.job_id,
                        "exposure": str(item.exposure),
                        "reason": item.reason,
                        "evidence_ids": list(item.evidence_ids),
                    }
                    for item in leaks
                ],
            },
            created_by_user_id=actor,
            completed_at=datetime.now(UTC),
        )
        db.add(run)
        db.flush()
        for item in payload.records:
            canonical = item.engine_record()
            encoded = json.dumps(canonical, sort_keys=True, default=str)
            db.add(
                JobToCashRecord(
                    organization_id=org,
                    run_id=run.id,
                    record_type=item.type,
                    external_id=item.id,
                    source_reference=f"job-to-cash:{item.type}:{item.id}",
                    integrity_fingerprint=hashlib.sha256(encoded.encode()).hexdigest(),
                    canonical_data=canonical,
                )
            )
        db.commit()
        finding_ids: list[str] = []
        opportunity_ids: list[str] = []
        finding_service = FindingService()
        for leak in leaks:
            finding = finding_service.create(
                db,
                org,
                FindingCreate(
                    rule_id=f"J2C.{leak.code}",
                    title=leak.code.replace("_", " ").title(),
                    summary=leak.reason,
                    domain="job_to_cash",
                    severity="high",
                    priority=2,
                    exposure_low=float(leak.exposure),
                    exposure_high=float(leak.exposure),
                    currency=payload.currency_code,
                    confidence_score=1,
                    evidence=[
                        EvidenceCreate(
                            source_system="job_to_cash_canonical",
                            source_record_id=reference,
                            evidence_type="canonical_record",
                            payload={"run_id": str(run.id), "job_id": leak.job_id},
                        )
                        for reference in leak.evidence_ids
                    ],
                ),
            )
            opportunity = economics_service.create(
                db,
                org,
                OpportunityCreate(
                    idempotency_key=f"j2c:{run.id}:{leak.code}:{leak.job_id}",
                    economic_source_key=f"j2c:{run.id}:{leak.code}:{leak.job_id}",
                    title=finding.title,
                    description=leak.reason,
                    currency_code=payload.currency_code,
                    business_domain="job_to_cash",
                    industry_pack_code="PACK-J2C",
                    capability_code=leak.code,
                ),
                actor,
            )
            economics_service.add_finding(
                db,
                org,
                opportunity.id,
                FindingLinkCreate(finding_id=finding.id),
                actor,
            )
            finding_ids.append(str(finding.id))
            opportunity_ids.append(str(opportunity.id))
        run.reconciliation = {
            **run.reconciliation,
            "finding_ids": finding_ids,
            "opportunity_ids": opportunity_ids,
        }
        db.commit()
        for meter_code, quantity in (
            ("rows_processed", Decimal(len(records))),
            ("rule_executions", Decimal(len(leaks))),
        ):
            if quantity == 0:
                continue
            try:
                usage_meter_service.record(
                    db,
                    org,
                    UsageEventCreate(
                        meter_code=meter_code,
                        idempotency_key=f"j2c:{run.id}:{meter_code}",
                        quantity=quantity,
                        source_type="job_to_cash_run",
                        source_id=str(run.id),
                        occurred_at=datetime.now(UTC),
                    ),
                )
            except CommercialServiceError:
                db.rollback()  # Meter definitions may be absent in isolated unit tests.
        db.refresh(run)
        return self._read(run)

    @staticmethod
    def _read(row: JobToCashRun) -> JobToCashRunRead:
        raw_findings = row.reconciliation.get("findings", [])
        findings = (
            [LeakageRead(**item) for item in raw_findings if isinstance(item, dict)]
            if isinstance(raw_findings, list)
            else []
        )
        return JobToCashRunRead(
            id=row.id,
            organization_id=row.organization_id,
            status=row.status,
            currency_code=row.currency_code,
            findings=findings,
            source_totals=row.source_totals,
            reconciliation=row.reconciliation,
            created_at=row.created_at,
        )


job_to_cash_orchestration_service = JobToCashOrchestrationService()
