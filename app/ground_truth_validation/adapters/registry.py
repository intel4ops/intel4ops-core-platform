from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.ground_truth_validation.adapters.base import GroundTruthPackageAdapter
from app.ground_truth_validation.adapters.simple_v1 import simple_v1_adapter
from app.ground_truth_validation.adapters.simulation_truth_v1 import simulation_truth_v1_adapter

# Modeled on this codebase's existing EngineRegistry/TrustRuleRegistry/
# ArtifactParserRegistry pattern. select_for_package() returning no adapter
# is the honest "no adapter recognizes this package yet" signal -- callers
# must never guess or silently fall back to a mismatched adapter.
#
# P3.xxD.1E.1: the API envelope version (GroundTruthPackageUploadV2) and the
# authored ground-truth schema identifier (schema_version) are separate
# concepts -- see the package docstring. Selection is deterministic:
#   A. schema_version supplied and recognized  -> that adapter, no shape
#      detection at all.
#   B. schema_version supplied but NOT recognized -> unknown_package_
#      schema_version (never silently shape-detects instead -- a typo in
#      an explicit declaration must not fall through to a guess).
#   C. schema_version absent/null -> evaluate every adapter's can_handle();
#      exactly one match selects it, zero matches is
#      unrecognized_package_schema, more than one is
#      ambiguous_package_schema (never "pick the first one").


class AdapterSelectionError(StrEnum):
    UNKNOWN_SCHEMA_VERSION = "unknown_package_schema_version"
    UNRECOGNIZED = "unrecognized_package_schema"
    AMBIGUOUS = "ambiguous_package_schema"


@dataclass(frozen=True)
class AdapterSelectionResult:
    adapter: GroundTruthPackageAdapter | None
    error: AdapterSelectionError | None = None
    # Populated for AMBIGUOUS: every adapter_code that matched.
    candidate_codes: list[str] = field(default_factory=list)
    # Populated for UNKNOWN_SCHEMA_VERSION: every schema_version this
    # registry actually supports, so the caller can self-correct.
    supported_schema_versions: list[str] = field(default_factory=list)


class GroundTruthPackageAdapterRegistry:
    def __init__(self) -> None:
        self._adapters: list[GroundTruthPackageAdapter] = []

    def register(self, adapter: GroundTruthPackageAdapter) -> None:
        self._adapters.append(adapter)

    def all(self) -> list[GroundTruthPackageAdapter]:
        return list(self._adapters)

    def get_by_code(self, adapter_code: str) -> GroundTruthPackageAdapter | None:
        for adapter in self._adapters:
            if adapter.adapter_code == adapter_code:
                return adapter
        return None

    def select_for_package(self, package_metadata: dict[str, object]) -> AdapterSelectionResult:
        declared = package_metadata.get("schema_version")
        if declared:
            adapter = self.get_by_code(str(declared))
            if adapter is not None:
                return AdapterSelectionResult(adapter=adapter)
            return AdapterSelectionResult(
                adapter=None,
                error=AdapterSelectionError.UNKNOWN_SCHEMA_VERSION,
                supported_schema_versions=sorted(a.adapter_code for a in self._adapters),
            )

        matches = [a for a in self._adapters if a.can_handle(package_metadata)]
        if len(matches) == 1:
            return AdapterSelectionResult(adapter=matches[0])
        if not matches:
            return AdapterSelectionResult(adapter=None, error=AdapterSelectionError.UNRECOGNIZED)
        return AdapterSelectionResult(
            adapter=None,
            error=AdapterSelectionError.AMBIGUOUS,
            candidate_codes=[a.adapter_code for a in matches],
        )


def default_adapter_registry() -> GroundTruthPackageAdapterRegistry:
    registry = GroundTruthPackageAdapterRegistry()
    # Registration order is irrelevant to selection now: an explicit
    # schema_version is looked up by exact code, and shape-detection
    # collects every match rather than stopping at the first one.
    registry.register(simulation_truth_v1_adapter)
    registry.register(simple_v1_adapter)
    return registry


default_ground_truth_package_adapter_registry = default_adapter_registry()
