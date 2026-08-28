from __future__ import annotations

from app.ground_truth_validation.adapters.base import GroundTruthPackageAdapter
from app.ground_truth_validation.adapters.simple_v1 import simple_v1_adapter
from app.ground_truth_validation.adapters.simulation_truth_v1 import simulation_truth_v1_adapter

# Modeled on this codebase's existing EngineRegistry/TrustRuleRegistry/
# ArtifactParserRegistry pattern. select() returning None is the honest
# "no adapter recognizes this package shape yet" signal -- callers must
# never guess or fall back to a mismatched adapter.


class GroundTruthPackageAdapterRegistry:
    def __init__(self) -> None:
        self._adapters: list[GroundTruthPackageAdapter] = []

    def register(self, adapter: GroundTruthPackageAdapter) -> None:
        self._adapters.append(adapter)

    def all(self) -> list[GroundTruthPackageAdapter]:
        return list(self._adapters)

    def select(self, package_metadata: dict[str, object]) -> GroundTruthPackageAdapter | None:
        for adapter in self._adapters:
            if adapter.can_handle(package_metadata):
                return adapter
        return None

    def get_by_code(self, adapter_code: str) -> GroundTruthPackageAdapter | None:
        for adapter in self._adapters:
            if adapter.adapter_code == adapter_code:
                return adapter
        return None


def default_adapter_registry() -> GroundTruthPackageAdapterRegistry:
    registry = GroundTruthPackageAdapterRegistry()
    # Order matters only in that simple_v1 must not accidentally claim a
    # package another adapter's can_handle() would also match -- both
    # adapters' can_handle() are mutually exclusive by construction
    # (simple_v1 requires the ABSENCE of a documents map).
    registry.register(simulation_truth_v1_adapter)
    registry.register(simple_v1_adapter)
    return registry


default_ground_truth_package_adapter_registry = default_adapter_registry()
