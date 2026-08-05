from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.causal_intelligence import CausalMethodDefinition
from app.schemas.causal_intelligence import CausalMethodDefinitionCreate
from app.services.causal_intelligence_service import causal_ontology_service


@dataclass(frozen=True)
class CausalMethodSeed:
    method_code: str
    method_name: str
    method_class: str
    default_confidence_weight: Decimal


CAUSAL_METHOD_SEEDS: tuple[CausalMethodSeed, ...] = (
    CausalMethodSeed(
        "deterministic_temporal_rule_v1",
        "Deterministic Temporal Rule",
        "deterministic_temporal_rule",
        Decimal("0.90"),
    ),
    CausalMethodSeed(
        "business_rule_causality_v1",
        "Business Rule Causality",
        "business_rule_causality",
        Decimal("0.80"),
    ),
    CausalMethodSeed(
        "sequence_pattern_v1", "Sequence Pattern", "sequence_pattern", Decimal("0.65")
    ),
    CausalMethodSeed(
        "lagged_association_v1", "Lagged Association", "lagged_association", Decimal("0.55")
    ),
    CausalMethodSeed(
        "conditional_co_occurrence_v1",
        "Conditional Co-occurrence",
        "conditional_co_occurrence",
        Decimal("0.50"),
    ),
    CausalMethodSeed(
        "expert_confirmed_v1", "Expert Confirmed", "expert_confirmed", Decimal("0.95")
    ),
    CausalMethodSeed(
        "before_after_intervention_v1",
        "Before/After Intervention Analysis",
        "before_after_intervention",
        Decimal("0.75"),
    ),
)


def seed_causal_methods(db: Session) -> list[CausalMethodDefinition]:
    created = []
    for seed in CAUSAL_METHOD_SEEDS:
        created.append(
            causal_ontology_service.create_method(
                db,
                CausalMethodDefinitionCreate(
                    method_code=seed.method_code,
                    method_name=seed.method_name,
                    method_class=seed.method_class,
                    method_version="1.0.0",
                    default_confidence_weight=seed.default_confidence_weight,
                    scope_type="shared_core",
                    scope_key=f"shared_core:{seed.method_code}",
                ),
            )
        )
    return created


@dataclass(frozen=True)
class CausalOntologyNodeSeed:
    node_type: str
    causal_role: str
    label: str


@dataclass(frozen=True)
class CausalOntologyEdgeSeed:
    source_label: str
    target_label: str
    edge_type: str
    method_code: str
    lag_window_seconds: int
    minimum_confidence_threshold: Decimal
    required_evidence_kinds: tuple[str, ...]


@dataclass(frozen=True)
class CausalOntologyProfile:
    profile_code: str
    industry_pack_code: str
    nodes: tuple[CausalOntologyNodeSeed, ...]
    edges: tuple[CausalOntologyEdgeSeed, ...]
    ranking_weights: dict[str, Decimal] = field(default_factory=dict)


CAUSAL_ONTOLOGY_PROFILES: tuple[CausalOntologyProfile, ...] = (
    CausalOntologyProfile(
        profile_code="job_to_cash_causal_chain",
        industry_pack_code="PACK-J2C",
        nodes=(
            CausalOntologyNodeSeed("canonical_event", "root_cause", "incomplete_work_order"),
            CausalOntologyNodeSeed("canonical_event", "intermediate_effect", "delayed_invoice"),
            CausalOntologyNodeSeed("canonical_metric", "terminal_impact", "delayed_cash"),
        ),
        edges=(
            CausalOntologyEdgeSeed(
                "incomplete_work_order",
                "delayed_invoice",
                "causes",
                "deterministic_temporal_rule_v1",
                lag_window_seconds=86400 * 7,
                minimum_confidence_threshold=Decimal("0.6"),
                required_evidence_kinds=("canonical_record", "rule_trace"),
            ),
            CausalOntologyEdgeSeed(
                "delayed_invoice",
                "delayed_cash",
                "causes",
                "lagged_association_v1",
                lag_window_seconds=86400 * 30,
                minimum_confidence_threshold=Decimal("0.5"),
                required_evidence_kinds=("canonical_record",),
            ),
        ),
        ranking_weights={"recurrence": Decimal("0.4"), "economic_impact": Decimal("0.6")},
    ),
    CausalOntologyProfile(
        profile_code="oilfield_services_causal_chain",
        industry_pack_code="OILFIELD-SERVICES",
        nodes=(
            CausalOntologyNodeSeed("external_factor", "root_cause", "parts_shortage"),
            CausalOntologyNodeSeed("canonical_event", "mechanism", "repair_delay"),
            CausalOntologyNodeSeed("canonical_event", "intermediate_effect", "asset_downtime"),
            CausalOntologyNodeSeed("canonical_metric", "terminal_impact", "missed_service_revenue"),
        ),
        edges=(
            CausalOntologyEdgeSeed(
                "parts_shortage",
                "repair_delay",
                "causes",
                "business_rule_causality_v1",
                lag_window_seconds=86400 * 3,
                minimum_confidence_threshold=Decimal("0.6"),
                required_evidence_kinds=("rule_trace",),
            ),
            CausalOntologyEdgeSeed(
                "repair_delay",
                "asset_downtime",
                "causes",
                "deterministic_temporal_rule_v1",
                lag_window_seconds=86400,
                minimum_confidence_threshold=Decimal("0.7"),
                required_evidence_kinds=("canonical_record",),
            ),
            CausalOntologyEdgeSeed(
                "asset_downtime",
                "missed_service_revenue",
                "causes",
                "lagged_association_v1",
                lag_window_seconds=86400 * 14,
                minimum_confidence_threshold=Decimal("0.5"),
                required_evidence_kinds=("canonical_record",),
            ),
        ),
        ranking_weights={
            "recurrence": Decimal("0.3"),
            "economic_impact": Decimal("0.4"),
            "downtime_impact": Decimal("0.3"),
        },
    ),
)
