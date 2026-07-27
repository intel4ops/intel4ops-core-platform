"""Governed industry pack framework and four commercial packs.

Revision ID: 20260727_0019
Revises: 20260726_0018
"""

import json
from collections.abc import Sequence
from datetime import UTC, datetime

from alembic import op

import app.models  # noqa: F401
from app.commercial.catalog import catalog_id
from app.db.session import Base
from app.industry_packs.catalog import MANIFESTS, PACKS, components, pack_id

revision: str = "20260727_0019"
down_revision: str | None = "20260726_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "industry_pack_versions",
    "industry_pack_assignment_states",
    "industry_pack_components",
    "industry_pack_validation_results",
    "industry_pack_executions",
    "industry_pack_governance_events",
)
SEEDED_AT = datetime(2026, 7, 27, tzinfo=UTC)


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in TABLES:
        Base.metadata.tables[table_name].create(bind=bind, checkfirst=False)

    version_table = Base.metadata.tables["industry_pack_versions"]
    component_table = Base.metadata.tables["industry_pack_components"]
    for code, _name, _industry, _entitlement in PACKS:
        version_id = pack_id("version", f"{code}:1.0.0")
        op.bulk_insert(
            version_table,
            [
                {
                    "id": version_id,
                    "pack_id": catalog_id("pack", code),
                    "semantic_version": "1.0.0",
                    "lifecycle_status": "published",
                    "manifest_json": op.inline_literal(
                        json.dumps(MANIFESTS[code], separators=(",", ":"))
                    ),
                    "minimum_platform_revision": "20260726_0018",
                    "validated_at": SEEDED_AT,
                    "approved_at": SEEDED_AT,
                    "published_at": SEEDED_AT,
                    "created_at": SEEDED_AT,
                    "updated_at": SEEDED_AT,
                }
            ],
            multiinsert=False,
        )
        for item in components(code):
            component_code = str(item["code"])
            op.bulk_insert(
                component_table,
                [
                    {
                        "id": pack_id("component", f"{code}:1.0.0:{item['type']}:{component_code}"),
                        "pack_version_id": version_id,
                        "component_type": item["type"],
                        "code": component_code,
                        "universal_parent": item["universal_parent"],
                        "configuration": op.inline_literal(
                            json.dumps(item["config"], separators=(",", ":"))
                        ),
                        "created_at": SEEDED_AT,
                    }
                ],
                multiinsert=False,
            )


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(TABLES):
        Base.metadata.tables[table_name].drop(bind=bind, checkfirst=False)
