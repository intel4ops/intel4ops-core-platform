"""Enterprise Operational Knowledge Graph foundation.

Revision ID: 20260728_0022
Revises: 20260727_0021
"""

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid5

import sqlalchemy as sa
from alembic import op

import app.models  # noqa: F401
from app.db.session import Base
from app.knowledge_graph.catalog import (
    ENTITY_SOURCE_REGISTRIES,
    ENTITY_TYPE_CODES,
    RELATIONSHIP_TYPE_CODES,
    definition_hash,
    graph_id,
)

revision: str = "20260728_0022"
down_revision: str | None = "20260727_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEEDED_AT = datetime(2026, 7, 28, tzinfo=UTC)
CERTIFICATION_NAMESPACE = UUID("fc68194e-f651-4857-b22f-388b7864d97f")
TABLES = (
    "knowledge_graph_entity_types",
    "knowledge_graph_entity_type_versions",
    "knowledge_graph_relationship_types",
    "knowledge_graph_relationship_type_versions",
    "knowledge_graph_governance_events",
    "knowledge_graph_versions",
    "knowledge_graph_nodes",
    "knowledge_graph_edges",
    "knowledge_graph_edge_evidence",
    "knowledge_graph_changes",
    "knowledge_graph_query_runs",
    "knowledge_graph_query_steps",
    "knowledge_graph_projection_checkpoints",
)
FEATURE_KEY = "intelligence.enterprise_knowledge_graph"
METERS = (
    "graph_nodes_materialized",
    "graph_edges_materialized",
    "graph_traversals",
)
LIMITS = {
    "limits.graph_nodes": METERS[0],
    "limits.graph_edges": METERS[1],
    "limits.graph_traversals": METERS[2],
    "limits.graph_depth": METERS[2],
    "limits.graph_result_nodes": METERS[2],
    "limits.graph_result_edges": METERS[2],
    "limits.graph_result_paths": METERS[2],
    "limits.graph_query_evidence_retention_days": METERS[2],
}


def _json(value: object) -> Any:
    return op.inline_literal(json.dumps(value, separators=(",", ":")))


def _certification_id(kind: str, code: str) -> UUID:
    return uuid5(CERTIFICATION_NAMESPACE, f"{kind}:{code}")


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in TABLES:
        Base.metadata.tables[table_name].create(bind=bind, checkfirst=False)

    entity_table = Base.metadata.tables["knowledge_graph_entity_types"]
    entity_version_table = Base.metadata.tables["knowledge_graph_entity_type_versions"]
    for code in ENTITY_TYPE_CODES:
        entity_id = graph_id("entity_type", code)
        op.bulk_insert(
            entity_table,
            [
                {
                    "id": entity_id,
                    "code": code,
                    "name": code.replace("_", " ").title(),
                    "description": f"Governed reference to an authoritative {code} record.",
                    "lifecycle_status": "active",
                    "owner": "Enterprise Intelligence Architecture",
                    "security_classification": "internal",
                    "tags": _json(["wp-3.01", "governed"]),
                    "documentation_reference": (
                        "docs/phase3/wp-3.01-knowledge-graph-specification.md"
                    ),
                    "created_at": SEEDED_AT,
                    "updated_at": SEEDED_AT,
                }
            ],
            multiinsert=False,
        )
        op.bulk_insert(
            entity_version_table,
            [
                {
                    "id": graph_id("entity_type_version", code),
                    "entity_type_id": entity_id,
                    "semantic_version": "1.0.0",
                    "source_registries": _json([ENTITY_SOURCE_REGISTRIES[code]]),
                    "reference_contract": _json({"authoritative_reference_required": True}),
                    "property_contract": _json({"raw_payloads_forbidden": True}),
                    "validation_contract": _json({"tenant_reference_required": True}),
                    "retention_policy": _json({"policy": "source-governed"}),
                    "known_limitations": _json([]),
                    "definition_hash": definition_hash("entity_type", code),
                    "approved_at": SEEDED_AT,
                    "created_at": SEEDED_AT,
                }
            ],
            multiinsert=False,
        )

    relationship_table = Base.metadata.tables["knowledge_graph_relationship_types"]
    relationship_version_table = Base.metadata.tables["knowledge_graph_relationship_type_versions"]
    for code in RELATIONSHIP_TYPE_CODES:
        relationship_id = graph_id("relationship_type", code)
        op.bulk_insert(
            relationship_table,
            [
                {
                    "id": relationship_id,
                    "code": code,
                    "name": code.replace("_", " ").title(),
                    "description": f"Governed non-causal operational relationship: {code}.",
                    "lifecycle_status": "active",
                    "directed": code != "correlated_with",
                    "symmetric": code == "correlated_with",
                    "owner": "Enterprise Intelligence Architecture",
                    "security_classification": "internal",
                    "documentation_reference": (
                        "docs/phase3/wp-3.01-knowledge-graph-specification.md"
                    ),
                    "created_at": SEEDED_AT,
                    "updated_at": SEEDED_AT,
                }
            ],
            multiinsert=False,
        )
        op.bulk_insert(
            relationship_version_table,
            [
                {
                    "id": graph_id("relationship_type_version", code),
                    "relationship_type_id": relationship_id,
                    "semantic_version": "1.0.0",
                    "allowed_from_entity_codes": _json(list(ENTITY_TYPE_CODES)),
                    "allowed_to_entity_codes": _json(list(ENTITY_TYPE_CODES)),
                    "evidence_contract": _json({"minimum_references": 1}),
                    "confidence_policy": _json({"minimum": 0, "maximum": 1}),
                    "temporal_policy": _json({"point_in_time": True}),
                    "revalidation_policy": _json({"on_source_change": True}),
                    "known_limitations": _json(["Relationship is non-causal."]),
                    "definition_hash": definition_hash("relationship_type", code),
                    "approved_at": SEEDED_AT,
                    "created_at": SEEDED_AT,
                }
            ],
            multiinsert=False,
        )

    op.bulk_insert(
        Base.metadata.tables["features"],
        [
            {
                "id": graph_id("feature", FEATURE_KEY),
                "key": FEATURE_KEY,
                "name": "Enterprise Operational Knowledge Graph",
                "description": "Governed tenant graph projection and bounded traversal.",
                "status": "active",
                "created_at": SEEDED_AT,
            }
        ],
    )
    meter_table = Base.metadata.tables["usage_meter_definitions"]
    for code in METERS:
        op.bulk_insert(
            meter_table,
            [
                {
                    "id": graph_id("meter", code),
                    "code": code,
                    "product": "enterprise_intelligence",
                    "meter_kind": "counter",
                    "unit": "count",
                    "aggregation": "sum",
                    "currency_behavior": "not_applicable",
                    "active": True,
                }
            ],
        )
    limit_table = Base.metadata.tables["limit_definitions"]
    for key, meter in LIMITS.items():
        op.bulk_insert(
            limit_table,
            [
                {
                    "id": graph_id("limit", key),
                    "entitlement_key": key,
                    "meter_code": meter,
                    "default_enforcement_type": "hard",
                    "default_reset_period": "contract",
                    "warning_percentage": Decimal("0.8"),
                    "grace_percentage": Decimal("0"),
                }
            ],
        )
    op.bulk_insert(
        Base.metadata.tables["validation_suites"],
        [
            {
                "id": _certification_id("suite", "knowledge_graph"),
                "code": "knowledge_graph",
                "display_name": "Enterprise Knowledge Graph",
                "required": True,
                "configuration": _json({"tenant_isolation": True, "bounded_traversal": True}),
            }
        ],
        multiinsert=False,
    )
    op.bulk_insert(
        Base.metadata.tables["release_gate_definitions"],
        [
            {
                "id": _certification_id("gate", "KNOWLEDGE_GRAPH"),
                "code": "KNOWLEDGE_GRAPH",
                "suite_code": "knowledge_graph",
                "mandatory": True,
                "waivable": False,
                "failure_policy": "block",
                "configuration": _json({"migration_head": revision}),
            }
        ],
        multiinsert=False,
    )


def downgrade() -> None:
    op.execute(
        sa.delete(Base.metadata.tables["release_gate_definitions"]).where(
            Base.metadata.tables["release_gate_definitions"].c.code == "KNOWLEDGE_GRAPH"
        )
    )
    op.execute(
        sa.delete(Base.metadata.tables["validation_suites"]).where(
            Base.metadata.tables["validation_suites"].c.code == "knowledge_graph"
        )
    )
    op.execute(
        sa.delete(Base.metadata.tables["limit_definitions"]).where(
            Base.metadata.tables["limit_definitions"].c.entitlement_key.in_(tuple(LIMITS))
        )
    )
    op.execute(
        sa.delete(Base.metadata.tables["usage_meter_definitions"]).where(
            Base.metadata.tables["usage_meter_definitions"].c.code.in_(METERS)
        )
    )
    op.execute(
        sa.delete(Base.metadata.tables["features"]).where(
            Base.metadata.tables["features"].c.key == FEATURE_KEY
        )
    )
    for table_name in reversed(TABLES):
        op.drop_table(table_name)
