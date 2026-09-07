from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


AutonomyDecision = Literal[
    "AUTO_EXECUTE",
    "AUTO_MERGE",
    "AUTO_DEPLOY_STAGING",
    "OWNER_APPROVAL_PRODUCTION",
    "OWNER_APPROVAL_R3",
    "ESCALATE_ON_REGRESSION",
    "BLOCKED",
]


class AutonomousEngineeringPolicyRequest(BaseModel):
    risk_class: Literal["R0", "R1", "R2", "R3"]
    lifecycle_stage: Literal[
        "implementation",
        "verified_candidate",
        "merged_release_candidate",
        "deployment",
    ]
    verification_decision: Literal[
        "NOT_APPLICABLE",
        "VERIFIED_IMPROVEMENT",
        "NO_MEANINGFUL_IMPROVEMENT",
        "REGRESSION",
    ] = "NOT_APPLICABLE"
    quality_gate_green: bool = False
    target_environment: Literal["none", "staging", "production"] = "none"
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
