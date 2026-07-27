"""Operational feature and proprietary signature intelligence platform.

Revision ID: 20260727_0021
Revises: 20260727_0020
"""

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid5

import sqlalchemy as sa
from alembic import op

import app.models  # noqa: F401
from app.commercial.catalog import catalog_id
from app.db.session import Base
from app.signatures.catalog import (
    FEATURE_CATALOG,
    SIGNATURE_CATALOG,
    asset_id,
)
from app.validation.simulation import SCENARIO_REGISTRY

revision: str = "20260727_0021"
down_revision: str | None = "20260727_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEEDED_AT = datetime(2026, 7, 27, tzinfo=UTC)
CERTIFICATION_NAMESPACE = UUID("fc68194e-f651-4857-b22f-388b7864d97f")
TABLES = (
    "operational_feature_definitions",
    "operational_feature_versions",
    "operational_signature_definitions",
    "operational_signature_versions",
    "operational_signature_validations",
    "operational_signature_lifecycle_events",
    "operational_signature_deployments",
    "operational_signature_executions",
    "operational_signature_execution_evidence",
    "operational_signature_performance_history",
    "operational_signature_monitoring_results",
)


def _json(value: object) -> Any:
    return op.inline_literal(json.dumps(value, separators=(",", ":")))


def _certification_id(kind: str, code: str) -> UUID:
    return uuid5(CERTIFICATION_NAMESPACE, f"{kind}:{code}")


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in TABLES:
        Base.metadata.tables[table_name].create(bind=bind, checkfirst=False)

    with op.batch_alter_table("findings") as batch:
        batch.add_column(sa.Column("signature_version_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("signature_execution_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_findings_signature_version",
            "operational_signature_versions",
            ["signature_version_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_findings_signature_execution",
            "operational_signature_executions",
            ["signature_execution_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index(
            "ix_findings_org_signature",
            ["organization_id", "signature_version_id"],
            unique=False,
        )

    feature_table = Base.metadata.tables["operational_feature_definitions"]
    feature_version_table = Base.metadata.tables["operational_feature_versions"]
    for code, feature in FEATURE_CATALOG.items():
        feature_id = asset_id("feature", code)
        op.bulk_insert(
            feature_table,
            [
                {
                    "id": feature_id,
                    "code": code,
                    "name": feature["name"],
                    "description": feature["description"],
                    "lifecycle_status": "active",
                    "owner": feature["owner"],
                    "tags": _json(["shared", "operational_feature"]),
                    "documentation_reference": "docs/operational-signatures.md",
                    "created_at": SEEDED_AT,
                    "updated_at": SEEDED_AT,
                }
            ],
            multiinsert=False,
        )
        op.bulk_insert(
            feature_version_table,
            [
                {
                    "id": asset_id("feature_version", code),
                    "feature_id": feature_id,
                    "semantic_version": "1.0.0",
                    "entity_grain": feature["entity_grain"],
                    "time_grain": feature["time_grain"],
                    "value_type": feature["value_type"],
                    "unit_behavior": feature["unit_behavior"],
                    "currency_behavior": feature["currency_behavior"],
                    "required_canonical_objects": _json(feature["required_canonical_objects"]),
                    "input_contract": _json(feature["input_contract"]),
                    "computation_reference": _json(feature["computation_reference"]),
                    "validation_contract": _json(feature["validation_contract"]),
                    "known_limitations": _json(feature["known_limitations"]),
                    "approved_at": SEEDED_AT,
                    "created_at": SEEDED_AT,
                }
            ],
            multiinsert=False,
        )

    signature_table = Base.metadata.tables["operational_signature_definitions"]
    signature_version_table = Base.metadata.tables["operational_signature_versions"]
    validation_table = Base.metadata.tables["operational_signature_validations"]
    lifecycle_table = Base.metadata.tables["operational_signature_lifecycle_events"]
    for code, signature in SIGNATURE_CATALOG.items():
        signature_id = asset_id("signature", code)
        version_id = asset_id("signature_version", code)
        op.bulk_insert(
            signature_table,
            [
                {
                    "id": signature_id,
                    "code": code,
                    "name": signature["name"],
                    "description": signature["description"],
                    "signature_type": signature["signature_type"],
                    "industry": signature["industry"],
                    "lifecycle_status": "production",
                    "canonical_governance_status": "active",
                    "owner": signature["owner"],
                    "tags": _json(["proprietary", "operational_signature"]),
                    "documentation_reference": "docs/operational-signatures.md",
                    "created_at": SEEDED_AT,
                    "updated_at": SEEDED_AT,
                }
            ],
            multiinsert=False,
        )
        op.bulk_insert(
            signature_version_table,
            [
                {
                    "id": version_id,
                    "signature_id": signature_id,
                    "semantic_version": "1.0.0",
                    "applicable_pack_versions": _json(signature["applicable_pack_versions"]),
                    "required_canonical_objects": _json(signature["required_canonical_objects"]),
                    "required_features": _json(signature["required_features"]),
                    "required_events": _json(signature["required_events"]),
                    "required_conditions": _json(signature["required_conditions"]),
                    "exclusion_conditions": _json(signature["exclusion_conditions"]),
                    "evidence_requirements": _json(signature["evidence_requirements"]),
                    "confidence_model": _json(signature["confidence_model"]),
                    "economic_impact_policy": _json(signature["economic_impact_policy"]),
                    "expected_outcome": _json(signature["expected_outcome"]),
                    "supporting_algorithms": _json(signature["supporting_algorithms"]),
                    "supporting_rules": _json(signature["supporting_rules"]),
                    "supporting_models": _json(signature["supporting_models"]),
                    "dependencies": _json(signature["dependencies"]),
                    "monitoring_policy": _json(signature["monitoring_policy"]),
                    "known_limitations": _json(signature["known_limitations"]),
                    "definition_hash": signature["definition_hash"],
                    "approved_at": SEEDED_AT,
                    "created_at": SEEDED_AT,
                }
            ],
            multiinsert=False,
        )
        op.bulk_insert(
            validation_table,
            [
                {
                    "id": asset_id("signature_validation", code),
                    "signature_version_id": version_id,
                    "scenario_version_id": SCENARIO_REGISTRY[
                        str(signature["scenario_code"])
                    ].scenario_id,
                    "status": "passed",
                    "metrics": _json(
                        {
                            "deterministic_replay": True,
                            "oracle_reconciled": True,
                            "tenant_isolation": True,
                        }
                    ),
                    "false_positive_count": 0,
                    "false_negative_count": 0,
                    "evidence_references": _json(
                        [{"type": "scenario", "code": signature["scenario_code"]}]
                    ),
                    "limitations": _json(signature["known_limitations"]),
                    "approved": True,
                    "created_at": SEEDED_AT,
                }
            ],
            multiinsert=False,
        )
        op.bulk_insert(
            lifecycle_table,
            [
                {
                    "id": asset_id("signature_lifecycle", code),
                    "signature_id": signature_id,
                    "prior_status": "approved",
                    "new_status": "production",
                    "actor_user_id": asset_id("system_actor", "platform_migration"),
                    "actor_role": "platform_admin",
                    "reason": "WP-2.21 deterministic scenario and oracle validation passed",
                    "approval_reference": str(asset_id("signature_validation", code)),
                    "idempotency_key": f"seed:{code}:production",
                    "occurred_at": SEEDED_AT,
                }
            ],
            multiinsert=False,
        )

    feature_catalog = Base.metadata.tables["features"]
    op.bulk_insert(
        feature_catalog,
        [
            {
                "id": catalog_id("feature", "intelligence.operational_signatures"),
                "key": "intelligence.operational_signatures",
                "name": "Operational Signature Intelligence",
                "description": "Governed proprietary operational signature execution.",
                "status": "active",
                "created_at": SEEDED_AT,
            }
        ],
    )
    meter_table = Base.metadata.tables["usage_meter_definitions"]
    op.bulk_insert(
        meter_table,
        [
            {
                "id": catalog_id("meter", "signature_executions"),
                "code": "signature_executions",
                "product": "Intelligence",
                "meter_kind": "event",
                "unit": "executions",
                "aggregation": "sum",
                "currency_behavior": "not_applicable",
                "active": True,
            }
        ],
    )
    op.bulk_insert(
        Base.metadata.tables["validation_suites"],
        [
            {
                "id": _certification_id("suite", "operational_signatures"),
                "code": "operational_signatures",
                "display_name": "Operational Signatures",
                "required": True,
                "configuration": _json(
                    {
                        "requires": [
                            "deterministic_replay",
                            "evidence_completeness",
                            "tenant_isolation",
                            "lifecycle_governance",
                        ]
                    }
                ),
            }
        ],
        multiinsert=False,
    )
    op.bulk_insert(
        Base.metadata.tables["release_gate_definitions"],
        [
            {
                "id": _certification_id("gate", "OPERATIONAL_SIGNATURES"),
                "code": "OPERATIONAL_SIGNATURES",
                "suite_code": "operational_signatures",
                "mandatory": True,
                "waivable": False,
                "failure_policy": "reject",
                "configuration": _json({}),
            }
        ],
        multiinsert=False,
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM release_gate_definitions WHERE code = 'OPERATIONAL_SIGNATURES'")
    )
    op.execute(sa.text("DELETE FROM validation_suites WHERE code = 'operational_signatures'"))
    op.execute(sa.text("DELETE FROM usage_meter_definitions WHERE code = 'signature_executions'"))
    op.execute(sa.text("DELETE FROM features WHERE key = 'intelligence.operational_signatures'"))
    with op.batch_alter_table("findings") as batch:
        batch.drop_index("ix_findings_org_signature")
        batch.drop_constraint("fk_findings_signature_execution", type_="foreignkey")
        batch.drop_constraint("fk_findings_signature_version", type_="foreignkey")
        batch.drop_column("signature_execution_id")
        batch.drop_column("signature_version_id")

    bind = op.get_bind()
    for table_name in reversed(TABLES):
        Base.metadata.tables[table_name].drop(bind=bind, checkfirst=False)
