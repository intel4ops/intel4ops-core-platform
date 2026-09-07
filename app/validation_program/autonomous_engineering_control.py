"""AC-003: deterministic autonomy policy for routine engineering work."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from app.schemas.autonomous_engineering_control import AutonomousEngineeringPolicyRequest
from app.storage.base import StorageBackend


@dataclass(frozen=True)
class AutonomousEngineeringDecision:
    decision_id: UUID
    decision: str
    owner_required: bool
    auto_execute_allowed: bool
    auto_merge_allowed: bool
    auto_deploy_staging_allowed: bool
    production_deploy_allowed: bool
    reason: str
    artifact_ref: str


class AutonomousEngineeringControlService:
    def __init__(self, storage: StorageBackend) -> None:
        self._storage = storage

    @staticmethod
    def _safety_flags(payload: AutonomousEngineeringPolicyRequest) -> list[str]:
        flags: list[str] = []
        for field_name in (
            "security_boundary_change",
            "tenant_boundary_change",
            "evidence_gate_change",
            "truth_isolation_change",
            "destructive_migration",
            "canonical_architecture_change",
            "material_product_logic_change",
        ):
            if getattr(payload, field_name):
                flags.append(field_name)
        return flags

    def evaluate(
        self,
        organization_id: UUID,
        payload: AutonomousEngineeringPolicyRequest,
    ) -> AutonomousEngineeringDecision:
        safety_flags = self._safety_flags(payload)
        decision = "BLOCKED"
        owner_required = False
        reason = "Autonomy prerequisites are not satisfied."
        auto_execute = False
        auto_merge = False
        auto_stage = False
        production = False

        if payload.risk_class == "R3" or safety_flags:
            decision = "OWNER_APPROVAL_R3"
            owner_required = True
            reason = "R3 or protected-boundary change requires owner review."
        elif payload.verification_decision == "REGRESSION":
            decision = "ESCALATE_ON_REGRESSION"
            owner_required = True
            reason = "Regression evidence blocks autonomous progression."
        elif payload.lifecycle_stage == "implementation":
            if payload.risk_class in {"R0", "R1", "R2"}:
                decision = "AUTO_EXECUTE"
                auto_execute = True
                reason = "Bounded non-R3 implementation may execute autonomously."
        elif payload.lifecycle_stage == "verified_candidate":
            if (
                payload.verification_decision == "VERIFIED_IMPROVEMENT"
                and payload.quality_gate_green
                and payload.exact_candidate_bound
                and payload.risk_class in {"R0", "R1", "R2"}
            ):
                decision = "AUTO_MERGE"
                auto_execute = True
                auto_merge = True
                reason = "Verified exact candidate with full green quality gate may auto-merge."
            elif payload.verification_decision == "NO_MEANINGFUL_IMPROVEMENT":
                decision = "BLOCKED"
                reason = "Candidate did not prove meaningful improvement."
        elif payload.lifecycle_stage in {"merged_release_candidate", "deployment"}:
            if payload.target_environment == "staging":
                if (
                    payload.quality_gate_green
                    and payload.exact_merge_commit_bound
                    and payload.risk_class in {"R0", "R1", "R2"}
                ):
                    decision = "AUTO_DEPLOY_STAGING"
                    auto_execute = True
                    auto_merge = True
                    auto_stage = True
                    reason = "Exact merged commit may deploy autonomously to staging only."
            elif payload.target_environment == "production":
                decision = "OWNER_APPROVAL_PRODUCTION"
                owner_required = True
                reason = "Production promotion remains owner-gated in AC-003."

        decision_id = uuid4()
        artifact = {
            "schema_version": "ac003-autonomous-engineering-policy-v1",
            "decision_id": str(decision_id),
            "organization_id": str(organization_id),
            "decision": decision,
            "owner_required": owner_required,
            "auto_execute_allowed": auto_execute,
            "auto_merge_allowed": auto_merge,
            "auto_deploy_staging_allowed": auto_stage,
            "production_deploy_allowed": production,
            "risk_class": payload.risk_class,
            "lifecycle_stage": payload.lifecycle_stage,
            "verification_decision": payload.verification_decision,
            "quality_gate_green": payload.quality_gate_green,
            "target_environment": payload.target_environment,
            "exact_candidate_bound": payload.exact_candidate_bound,
            "exact_merge_commit_bound": payload.exact_merge_commit_bound,
            "safety_flags": safety_flags,
            "reason": reason,
            "owner_note": payload.note,
            "policy": {
                "routine_owner_gate_removed": True,
                "r3_owner_gate_required": True,
                "production_owner_gate_required": True,
                "regression_blocks_progression": True,
                "cross_environment_promotion_allowed": False,
            },
        }
        ref = f"autonomy-decisions/{organization_id}/{decision_id}.json"
        self._storage.write_text(ref, __import__("json").dumps(artifact, sort_keys=True, indent=2))
        return AutonomousEngineeringDecision(
            decision_id=decision_id,
            decision=decision,
            owner_required=owner_required,
            auto_execute_allowed=auto_execute,
            auto_merge_allowed=auto_merge,
            auto_deploy_staging_allowed=auto_stage,
            production_deploy_allowed=production,
            reason=reason,
            artifact_ref=ref,
        )
