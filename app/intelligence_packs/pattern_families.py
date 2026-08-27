from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CausalPatternFamily:
    code: str
    description: str
    stage_sequence: tuple[str, ...]


# Reusable causal pattern templates (Section 6 of the plan). P3.xxC.1
# implements concrete SOTRA-data instances of exactly the first two;
# the remaining three are named now so a future industry pack can register
# an instance of the same family without any orchestration change.
ASSET_FAILURE_TO_LOST_ACTIVITY = CausalPatternFamily(
    code="ASSET_FAILURE_TO_LOST_ACTIVITY",
    description="Asset Failure -> Operational Interruption -> Lost/Missing Business Activity",
    stage_sequence=("asset_failure", "operational_interruption", "lost_business_activity"),
)
LOST_ACTIVITY_TO_REVENUE_GAP = CausalPatternFamily(
    code="LOST_ACTIVITY_TO_REVENUE_GAP",
    description="Business Activity -> Expected Revenue/Billing Event",
    stage_sequence=("business_activity", "expected_revenue_event"),
)
RESOURCE_CONSUMPTION_TO_ACTIVITY = CausalPatternFamily(
    code="RESOURCE_CONSUMPTION_TO_ACTIVITY",
    description="Resource Consumption -> Operating Activity",
    stage_sequence=("resource_consumption", "operating_activity"),
)
WORK_ORDER_TO_BILLING = CausalPatternFamily(
    code="WORK_ORDER_TO_BILLING",
    description="Job/Work Order -> Labor + Materials -> Billing",
    stage_sequence=("work_order", "labor_and_materials", "billing"),
)
INVENTORY_CONSTRAINT_TO_DELAY = CausalPatternFamily(
    code="INVENTORY_CONSTRAINT_TO_DELAY",
    description="Inventory Constraint -> Operational Delay",
    stage_sequence=("inventory_constraint", "operational_delay"),
)
