from pydantic import BaseModel, Field


class AutonomousEngineeringPolicyRequest(BaseModel):
    risk_class: str = Field(pattern="^(R0|R1|R2|R3)$")
    lifecycle_stage: str = Field(
        pattern="^(implementation|verified_candidate|merged_release_candidate|deployment)$"
    )
    verification_decision: str = Field(
        default="NOT_APPLICABLE",
        pattern="^(NOT_APPLICABLE|VERIFIED_IMPROVEMENT|NO_MEANINGFUL_IMPROVEMENT|REGRESSION)$",
    )
    quality_gate_green: bool = False
    target_environment: str = Field(default="none", pattern="^(none|staging|production)$")
    security_boundary_change: bool = False
    tenant_boundary_change: bool = False
    evidence_gate_change: bool = False
    truth_isolation_change: bool = False
    destructive_migration: bool = False
    canonical_architecture_change: bool = False
    material_product_logic_change: bool = False
    exact_candidate_bound: bool = False
    exact_merge_commit_bound: bool = False
    note: str | None = Field(default=None, max_length=2000)
