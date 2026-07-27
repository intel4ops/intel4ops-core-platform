"""Simulation, governance, and release certification.

Revision ID: 20260727_0020
Revises: 20260727_0019
"""

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid5

from alembic import op

import app.models  # noqa: F401
from app.db.session import Base
from app.industry_packs.catalog import pack_id
from app.validation.simulation import ORACLE_REGISTRY, SCENARIO_REGISTRY

revision: str = "20260727_0020"
down_revision: str | None = "20260727_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CERTIFICATION_NAMESPACE = UUID("fc68194e-f651-4857-b22f-388b7864d97f")
SEEDED_AT = datetime(2026, 7, 27, tzinfo=UTC)

TABLES = (
    "validation_scenario_versions",
    "validation_oracle_versions",
    "validation_suites",
    "analytical_artifact_versions",
    "release_candidates",
    "validation_runs",
    "release_gate_definitions",
    "release_gate_results",
    "release_waivers",
    "release_certifications",
)

SUITES = (
    "core_platform",
    "migrations",
    "tenancy",
    "authorization",
    "industry_packs",
    "golden_scenarios",
    "commercial_enforcement",
    "model_governance",
    "security",
    "resilience",
    "observability",
    "release_readiness",
)

GATES: tuple[tuple[str, str, bool], ...] = (
    ("CORE_PLATFORM", "core_platform", False),
    ("MIGRATION_INTEGRITY", "migrations", False),
    ("TENANT_ISOLATION", "tenancy", False),
    ("AUTHORIZATION", "authorization", False),
    ("INDUSTRY_PACKS", "industry_packs", False),
    ("GOLDEN_SCENARIOS", "golden_scenarios", False),
    ("COMMERCIAL_ENFORCEMENT", "commercial_enforcement", False),
    ("MODEL_GOVERNANCE", "model_governance", False),
    ("SECURITY", "security", False),
    ("RESILIENCE", "resilience", False),
    ("OBSERVABILITY", "observability", True),
    ("RELEASE_READINESS", "release_readiness", False),
)


def _id(kind: str, code: str) -> UUID:
    return uuid5(CERTIFICATION_NAMESPACE, f"{kind}:{code}")


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in TABLES:
        Base.metadata.tables[table_name].create(bind=bind, checkfirst=False)

    suite_table = Base.metadata.tables["validation_suites"]
    for code in SUITES:
        op.bulk_insert(
            suite_table,
            [
                {
                    "id": _id("suite", code),
                    "code": code,
                    "display_name": code.replace("_", " ").title(),
                    "required": True,
                    "configuration": op.inline_literal("{}"),
                }
            ],
            multiinsert=False,
        )

    gate_table = Base.metadata.tables["release_gate_definitions"]
    for code, suite_code, waivable in GATES:
        op.bulk_insert(
            gate_table,
            [
                {
                    "id": _id("gate", code),
                    "code": code,
                    "suite_code": suite_code,
                    "mandatory": True,
                    "waivable": waivable,
                    "failure_policy": "conditional" if waivable else "reject",
                    "configuration": op.inline_literal("{}"),
                }
            ],
            multiinsert=False,
        )

    scenario_table = Base.metadata.tables["validation_scenario_versions"]
    oracle_table = Base.metadata.tables["validation_oracle_versions"]
    for code, scenario in SCENARIO_REGISTRY.items():
        scenario_id = scenario.scenario_id
        op.bulk_insert(
            scenario_table,
            [
                {
                    "id": scenario_id,
                    "scenario_code": code,
                    "version": scenario.scenario_version,
                    "industry_pack_version_id": pack_id(
                        "version", f"{scenario.industry_pack_code}:{scenario.industry_pack_version}"
                    ),
                    "display_name": scenario.display_name,
                    "description": scenario.description,
                    "seed": scenario.seed,
                    "generator_reference": scenario.generator_reference,
                    "manifest_json": op.inline_literal(
                        json.dumps(scenario.model_dump(mode="json"), separators=(",", ":"))
                    ),
                    "lifecycle_status": scenario.lifecycle_status,
                    "owner": scenario.owner,
                    "approved_at": SEEDED_AT,
                    "created_at": SEEDED_AT,
                }
            ],
            multiinsert=False,
        )
        oracle = ORACLE_REGISTRY[code]
        op.bulk_insert(
            oracle_table,
            [
                {
                    "id": oracle.oracle_id,
                    "scenario_version_id": scenario_id,
                    "version": oracle.version,
                    "assertions_json": op.inline_literal(
                        json.dumps(
                            [item.model_dump(mode="json") for item in oracle.assertions],
                            separators=(",", ":"),
                        )
                    ),
                    "evidence_contract_json": op.inline_literal(
                        json.dumps(
                            {"required_evidence_types": oracle.required_evidence_types},
                            separators=(",", ":"),
                        )
                    ),
                    "approved": oracle.approved,
                    "owner": oracle.owner,
                    "approved_at": SEEDED_AT,
                    "created_at": SEEDED_AT,
                }
            ],
            multiinsert=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(TABLES):
        Base.metadata.tables[table_name].drop(bind=bind, checkfirst=False)
