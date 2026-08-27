from __future__ import annotations

from uuid import UUID, uuid4

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.analysis_case import (
    AnalysisCase,
    AnalysisCaseDataset,
    AnalysisCaseEntityLink,
    AnalysisCaseFinding,
    AnalysisCaseRun,
    AnalysisCaseRunStatus,
    AnalysisCaseStageEvent,
    AnalysisCaseStatus,
    EntityLinkStatus,
    SourceArtifact,
    StageEventStatus,
)
from app.models.entities import utc_now
from app.schemas.trust import TrustAssessmentCreate
from app.services.analysis_case_intelligence_service import run_maintenance_pack
from app.services.analysis_case_mapping_service import analysis_case_mapping_service
from app.services.cross_domain_intelligence_service import (
    run_asset_failure_to_lost_activity,
    run_lost_activity_to_revenue_gap,
)
from app.services.entity_resolution_service import DatasetEntityInput, entity_resolution_service
from app.services.trust_service import trust_assessment_service
from app.storage.base import StorageBackend

# Minimal, conservative per-domain Trust rule configuration -- required-
# field-completeness on the domain's own key fields, plus one validity rule
# so the ARITHMETIC readiness level (needed for governed finding
# publication) can actually reach READY rather than being blocked on an
# unassessed dimension. This is intentionally generic/config-driven, not
# per-industry hard-coded logic.
_DOMAIN_TRUST_RULES: dict[str, dict[str, dict[str, object]]] = {
    "maintenance": {
        "required_field_completeness": {
            "required_fields": ["asset_id", "failure_code", "downtime_hours"]
        },
        "numeric_range_validity": {
            "numeric_ranges": {"downtime_hours": {"minimum": 0, "maximum": 100000}}
        },
    },
    "operations": {
        "required_field_completeness": {"required_fields": ["operational_event_id", "asset_id"]},
        "date_timestamp_validity": {"date_fields": ["event_date"]},
    },
    "revenue": {
        "required_field_completeness": {"required_fields": ["transaction_amount"]},
        "numeric_range_validity": {
            "numeric_ranges": {"transaction_amount": {"minimum": 0, "maximum": 1_000_000_000}}
        },
    },
}


class AnalysisCaseOrchestrationError(ValueError):
    def __init__(self, message: str, *, code: str, status: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def _reload_canonical_dataframe(
    db: Session, storage: StorageBackend, case_dataset: AnalysisCaseDataset
) -> pd.DataFrame | None:
    """Deterministically resolves a logical dataset back to its persisted
    raw source (Amendment 1) -- re-reads the SourceArtifact's bytes and
    re-runs the same parser rather than persisting the dataframe itself."""
    from app.ingestion.parsers import default_parser_registry

    artifact = db.get(SourceArtifact, case_dataset.source_artifact_id)
    if artifact is None or artifact.parser_code is None:
        return None
    registry = default_parser_registry()
    parser = registry.select(artifact.mime_type, artifact.extension)
    if parser is None:
        return None
    raw_bytes = b"".join(storage.open_stream(artifact.storage_reference))
    result = parser.extract(raw_bytes, artifact.original_filename)
    for extracted in result.datasets:
        if extracted.label == case_dataset.source_label:
            return extracted.dataframe
    return None


class AnalysisCaseOrchestrationService:
    def _record_stage(
        self,
        db: Session,
        organization_id: UUID,
        analysis_case_id: UUID,
        run_id: UUID,
        stage: str,
        status: str,
        detail: dict[str, object] | None = None,
        source_artifact_id: UUID | None = None,
    ) -> None:
        db.add(
            AnalysisCaseStageEvent(
                organization_id=organization_id,
                analysis_case_id=analysis_case_id,
                run_id=run_id,
                stage=stage,
                source_artifact_id=source_artifact_id,
                status=status,
                detail=detail or {},
            )
        )
        db.commit()

    def start_run(
        self, db: Session, organization_id: UUID, analysis_case_id: UUID, actor_user_id: UUID
    ) -> AnalysisCaseRun:
        case = db.scalar(
            select(AnalysisCase).where(
                AnalysisCase.id == analysis_case_id, AnalysisCase.organization_id == organization_id
            )
        )
        if case is None:
            raise AnalysisCaseOrchestrationError(
                "Case not found", code="case_not_found", status=404
            )
        existing_running = db.scalar(
            select(AnalysisCaseRun).where(
                AnalysisCaseRun.analysis_case_id == analysis_case_id,
                AnalysisCaseRun.status == AnalysisCaseRunStatus.RUNNING.value,
            )
        )
        if existing_running is not None:
            raise AnalysisCaseOrchestrationError(
                "A run is already in progress for this case",
                code="run_already_in_progress",
                status=409,
            )
        last_run_number = db.scalar(
            select(AnalysisCaseRun.run_number)
            .where(AnalysisCaseRun.analysis_case_id == analysis_case_id)
            .order_by(AnalysisCaseRun.run_number.desc())
            .limit(1)
        )
        run = AnalysisCaseRun(
            organization_id=organization_id,
            analysis_case_id=analysis_case_id,
            run_number=(last_run_number or 0) + 1,
            status=AnalysisCaseRunStatus.CREATED.value,
            created_by_user_id=actor_user_id,
        )
        db.add(run)
        case.status = AnalysisCaseStatus.RUNNING.value
        db.add(case)
        db.commit()
        db.refresh(run)
        return run

    def execute(
        self,
        db: Session,
        storage: StorageBackend,
        organization_id: UUID,
        analysis_case_id: UUID,
        run_id: UUID,
        actor_user_id: UUID,
    ) -> None:
        """The actual pipeline -- called from a FastAPI BackgroundTasks
        callback after POST /run has already returned. Never silently
        drops a failed dataset: failures are recorded per-stage and the
        case ends partial/failed rather than completed if anything failed
        or needs review."""
        run = db.get(AnalysisCaseRun, run_id)
        case = db.get(AnalysisCase, analysis_case_id)
        if run is None or case is None:
            return
        run.status = AnalysisCaseRunStatus.RUNNING.value
        run.started_at = utc_now()
        run.execution_lease_id = uuid4()
        run.heartbeat_at = utc_now()
        db.add(run)
        db.commit()

        any_failure = False
        any_review_required = False

        case_datasets = list(
            db.scalars(
                select(AnalysisCaseDataset).where(
                    AnalysisCaseDataset.organization_id == organization_id,
                    AnalysisCaseDataset.analysis_case_id == analysis_case_id,
                )
            ).all()
        )

        canonical_frames: dict[UUID, pd.DataFrame] = {}
        trust_assessment_ids: dict[UUID, UUID] = {}

        # --- TRUST + MAPPING (per dataset) ---
        for case_dataset in case_datasets:
            raw_df = _reload_canonical_dataframe(db, storage, case_dataset)
            if raw_df is None:
                case_dataset.trust_status = "failed"
                case_dataset.mapping_status = "failed"
                db.add(case_dataset)
                db.commit()
                any_failure = True
                self._record_stage(
                    db,
                    organization_id,
                    analysis_case_id,
                    run_id,
                    "connect",
                    StageEventStatus.FAILED.value,
                    {"reason": "could not reload dataset from persisted source"},
                )
                continue

            rule_config = _DOMAIN_TRUST_RULES.get(case_dataset.detected_domain or "", {})
            trust_status = "not_assessed"
            trust_assessment_id: UUID | None = None
            if rule_config:
                try:
                    assessment = trust_assessment_service.create_and_execute(
                        db,
                        organization_id,
                        case_dataset.dataset_id,
                        TrustAssessmentCreate(
                            records=raw_df.to_dict("records"), rule_configurations=rule_config
                        ),
                    )
                    trust_assessment_id = assessment.id
                    trust_status = assessment.status
                    trust_assessment_ids[case_dataset.id] = assessment.id
                    self._record_stage(
                        db,
                        organization_id,
                        analysis_case_id,
                        run_id,
                        "trust",
                        StageEventStatus.COMPLETED.value,
                        {
                            "dataset_id": str(case_dataset.dataset_id),
                            "overall_score": str(assessment.overall_score),
                        },
                    )
                except ValueError as exc:
                    trust_status = "failed"
                    any_failure = True
                    self._record_stage(
                        db,
                        organization_id,
                        analysis_case_id,
                        run_id,
                        "trust",
                        StageEventStatus.FAILED.value,
                        {"error": str(exc)},
                    )
            else:
                self._record_stage(
                    db,
                    organization_id,
                    analysis_case_id,
                    run_id,
                    "trust",
                    StageEventStatus.SKIPPED.value,
                    {"reason": f"no Trust rule config for domain {case_dataset.detected_domain!r}"},
                )

            case_dataset.trust_status = trust_status
            case_dataset.trust_assessment_id = trust_assessment_id

            mapping_result = analysis_case_mapping_service.apply(
                organization_id, case_dataset.id, raw_df, case_dataset.detected_domain
            )
            analysis_case_mapping_service.persist(db, case_dataset.id, mapping_result)
            case_dataset.mapping_status = mapping_result.overall_status
            if mapping_result.overall_status == "needs_review":
                any_review_required = True
            db.add(case_dataset)
            db.commit()

            canonical_frames[case_dataset.id] = mapping_result.canonical_dataframe
            self._record_stage(
                db,
                organization_id,
                analysis_case_id,
                run_id,
                "mapping",
                StageEventStatus.COMPLETED.value,
                {
                    "dataset_id": str(case_dataset.dataset_id),
                    "status": mapping_result.overall_status,
                },
            )

        # --- ENTITY RESOLUTION (across all successfully mapped datasets) ---
        entity_inputs = [
            DatasetEntityInput(cd.id, cd.dataset_id, canonical_frames[cd.id])
            for cd in case_datasets
            if cd.id in canonical_frames
        ]
        links = entity_resolution_service.resolve(entity_inputs)
        db.execute(
            delete(AnalysisCaseEntityLink).where(
                AnalysisCaseEntityLink.analysis_case_id == analysis_case_id
            )
        )
        for link in links:
            link.organization_id = organization_id
            link.analysis_case_id = analysis_case_id
            db.add(link)
        db.commit()
        self._record_stage(
            db,
            organization_id,
            analysis_case_id,
            run_id,
            "entity_resolution",
            StageEventStatus.COMPLETED.value,
            {"link_count": len(links)},
        )
        matched_assets = {
            link.canonical_key
            for link in links
            if link.entity_type == "asset" and link.status == EntityLinkStatus.MATCHED.value
        }

        # --- DOMAIN INTELLIGENCE ---
        by_domain: dict[str, list[AnalysisCaseDataset]] = {}
        for cd in case_datasets:
            if cd.id in canonical_frames and cd.detected_domain:
                by_domain.setdefault(cd.detected_domain, []).append(cd)

        published_finding_ids: set[UUID] = set()
        for cd in by_domain.get("maintenance", []):
            trust_id = trust_assessment_ids.get(cd.id)
            if trust_id is None:
                continue
            try:
                findings = run_maintenance_pack(
                    db,
                    organization_id,
                    cd.dataset_id,
                    trust_id,
                    canonical_frames[cd.id],
                    actor_user_id,
                )
                for finding in findings:
                    published_finding_ids.add(finding.id)
                self._record_stage(
                    db,
                    organization_id,
                    analysis_case_id,
                    run_id,
                    "domain_intelligence",
                    StageEventStatus.COMPLETED.value,
                    {"pack": "MAINT", "finding_count": len(findings)},
                )
            except ValueError as exc:
                self._record_stage(
                    db,
                    organization_id,
                    analysis_case_id,
                    run_id,
                    "domain_intelligence",
                    StageEventStatus.FAILED.value,
                    {"pack": "MAINT", "error": str(exc)},
                )

        # --- CROSS-DOMAIN INTELLIGENCE ---
        maint_datasets = by_domain.get("maintenance", [])
        ops_datasets = by_domain.get("operations", [])
        revenue_datasets = by_domain.get("revenue", [])
        for maint_cd in maint_datasets:
            trust_id = trust_assessment_ids.get(maint_cd.id)
            if trust_id is None:
                continue
            for ops_cd in ops_datasets:
                findings = run_asset_failure_to_lost_activity(
                    db,
                    organization_id,
                    maint_cd.dataset_id,
                    canonical_frames[maint_cd.id],
                    ops_cd.dataset_id,
                    canonical_frames[ops_cd.id],
                    trust_id,
                    matched_assets,
                    actor_user_id,
                )
                for finding in findings:
                    published_finding_ids.add(finding.id)
                self._record_stage(
                    db,
                    organization_id,
                    analysis_case_id,
                    run_id,
                    "cross_domain_intelligence",
                    StageEventStatus.COMPLETED.value,
                    {"rule": "XDOM-A", "finding_count": len(findings)},
                )
        for ops_cd in ops_datasets:
            trust_id = trust_assessment_ids.get(ops_cd.id)
            if trust_id is None:
                continue
            for rev_cd in revenue_datasets:
                findings = run_lost_activity_to_revenue_gap(
                    db,
                    organization_id,
                    ops_cd.dataset_id,
                    canonical_frames[ops_cd.id],
                    rev_cd.dataset_id,
                    canonical_frames[rev_cd.id],
                    trust_id,
                    actor_user_id,
                )
                for finding in findings:
                    published_finding_ids.add(finding.id)
                self._record_stage(
                    db,
                    organization_id,
                    analysis_case_id,
                    run_id,
                    "cross_domain_intelligence",
                    StageEventStatus.COMPLETED.value,
                    {"rule": "XDOM-B", "finding_count": len(findings)},
                )

        for finding_id in published_finding_ids:
            db.add(
                AnalysisCaseFinding(
                    organization_id=organization_id,
                    analysis_case_id=analysis_case_id,
                    run_id=run_id,
                    finding_id=finding_id,
                )
            )
        db.commit()

        run.completed_at = utc_now()
        run.heartbeat_at = utc_now()
        if any_failure:
            run.status = AnalysisCaseRunStatus.PARTIAL.value
            case.status = AnalysisCaseStatus.PARTIAL.value
        elif any_review_required:
            run.status = AnalysisCaseRunStatus.REVIEW_REQUIRED.value
            case.status = AnalysisCaseStatus.REVIEW_REQUIRED.value
        else:
            run.status = AnalysisCaseRunStatus.COMPLETED.value
            case.status = AnalysisCaseStatus.COMPLETED.value
        db.add(run)
        db.add(case)
        db.commit()
        self._record_stage(
            db,
            organization_id,
            analysis_case_id,
            run_id,
            "completion",
            StageEventStatus.COMPLETED.value,
            {"run_status": run.status, "findings_published": len(published_finding_ids)},
        )

    def mark_stale_if_needed(
        self, db: Session, run: AnalysisCaseRun, stale_after_seconds: float
    ) -> bool:
        if run.status != AnalysisCaseRunStatus.RUNNING.value or run.heartbeat_at is None:
            return False
        elapsed = (utc_now() - run.heartbeat_at).total_seconds()
        if elapsed <= stale_after_seconds:
            return False
        run.status = AnalysisCaseRunStatus.INTERRUPTED.value
        run.error_summary = f"Heartbeat stale for {elapsed:.0f}s -- marked interrupted"
        db.add(run)
        db.commit()
        return True


analysis_case_orchestration_service = AnalysisCaseOrchestrationService()
