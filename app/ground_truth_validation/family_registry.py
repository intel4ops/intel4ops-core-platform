from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# P3.xxD.1E section 7/8: authored ground truth expresses business
# semantics through expected_detection_family (WORKFORCE_PRODUCTIVITY,
# REVENUE_RECOGNITION, ...), never a required "domain" field. This
# registry is the ONLY place that translates an authored family into the
# production rule_ids/domains that could plausibly satisfy it -- modeled
# on this codebase's existing DOMAIN_SIGNATURES/EngineRegistry pattern.
# Belongs to Validation only: never imported by Intelligence, never
# influences rule selection (see
# tests/test_validation_import_boundary.py). New families are new
# registry entries, never new matcher code.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationFindingFamilyMapping:
    authored_family: str
    production_rule_families: frozenset[str]
    production_domains: frozenset[str] | None
    version: str = "1.0"
    active: bool = True
    metadata: dict[str, object] | None = None


class ValidationFindingFamilyMappingRegistry:
    def __init__(self) -> None:
        self._mappings: dict[str, ValidationFindingFamilyMapping] = {}

    def register(self, mapping: ValidationFindingFamilyMapping) -> None:
        self._mappings[mapping.authored_family] = mapping

    def lookup(self, authored_family: str | None) -> ValidationFindingFamilyMapping | None:
        if not authored_family:
            return None
        mapping = self._mappings.get(authored_family)
        if mapping is None or not mapping.active:
            return None
        return mapping

    def all(self) -> list[ValidationFindingFamilyMapping]:
        return list(self._mappings.values())


def default_family_mapping_registry() -> ValidationFindingFamilyMappingRegistry:
    registry = ValidationFindingFamilyMappingRegistry()
    # Fixture-evidence examples (section 8/19) -- illustrative configuration,
    # not hard-coded matcher behavior. A future family (PRESSURE_PUMPING_
    # EFFICIENCY, WIRELINE_REVENUE_LEAKAGE, ...) is another call to
    # .register(), never a matcher code change.
    registry.register(
        ValidationFindingFamilyMapping(
            authored_family="MAINTENANCE_ECONOMICS",
            production_rule_families=frozenset({"MAINT-001-REPEATED-FAILURE"}),
            production_domains=frozenset({"maintenance"}),
        )
    )
    registry.register(
        ValidationFindingFamilyMapping(
            authored_family="WORKFORCE_PRODUCTIVITY",
            production_rule_families=frozenset({"XDOM-A-ASSET-FAILURE-LOST-ACTIVITY"}),
            production_domains=frozenset({"maintenance", "operations"}),
        )
    )
    registry.register(
        ValidationFindingFamilyMapping(
            authored_family="REVENUE_RECOGNITION",
            production_rule_families=frozenset({"XDOM-B-LOST-ACTIVITY-REVENUE-GAP"}),
            production_domains=frozenset({"operations", "revenue"}),
        )
    )
    return registry


default_validation_finding_family_mapping_registry = default_family_mapping_registry()
