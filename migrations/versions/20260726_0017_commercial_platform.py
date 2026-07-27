"""commercial plans entitlements usage metering and catalog

Revision ID: 20260726_0017
Revises: 20260726_0016
"""

import json
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from alembic import op

import app.models  # noqa: F401
from app.commercial.catalog import (
    CAPABILITY_KEYS,
    FEATURES,
    INDUSTRY_PACKS,
    LIMITS,
    PLANS,
    PRODUCTS,
    USAGE_METERS,
    catalog_id,
)
from app.db.session import Base

revision: str = "20260726_0017"
down_revision: str | None = "20260726_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COMMERCIAL_TABLES = (
    "products",
    "product_versions",
    "features",
    "plans",
    "plan_versions",
    "plan_version_entitlements",
    "usage_meter_definitions",
    "industry_pack_definitions",
    "limit_definitions",
    "subscriptions",
    "contracts",
    "contract_overrides",
    "entitlements",
    "usage_events",
    "usage_periods",
    "industry_pack_assignments",
    "feature_flags",
    "limit_evaluations",
    "commercial_audit_events",
)


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in COMMERCIAL_TABLES:
        Base.metadata.tables[table_name].create(bind=bind, checkfirst=False)
    _seed_catalog()


def _seed_catalog() -> None:
    effective = date(2026, 7, 26)
    op.bulk_insert(
        Base.metadata.tables["products"],
        [
            {
                "id": catalog_id("product", code),
                "code": code,
                "name": name,
                "description": description,
                "status": "active",
            }
            for code, name, description in PRODUCTS
        ],
    )
    op.bulk_insert(
        Base.metadata.tables["product_versions"],
        [
            {
                "id": catalog_id("product-version", code),
                "product_id": catalog_id("product", code),
                "version": 1,
                "effective_date": effective,
                "expires_date": None,
                "specification": _json_literal({"catalog_version": "2.0"}),
            }
            for code, _, _ in PRODUCTS
        ],
        multiinsert=False,
    )
    op.bulk_insert(
        Base.metadata.tables["features"],
        [
            {
                "id": catalog_id("feature", key),
                "key": key,
                "name": name,
                "description": f"Commercial feature governed by {key}.",
                "status": "active",
            }
            for key, name in FEATURES
        ],
    )
    op.bulk_insert(
        Base.metadata.tables["plans"],
        [
            {
                "id": catalog_id("plan", code),
                "code": code,
                "name": name,
                "plan_type": plan_type,
                "status": "active",
            }
            for code, name, plan_type in PLANS
        ],
    )
    op.bulk_insert(
        Base.metadata.tables["plan_versions"],
        [
            {
                "id": catalog_id("plan-version", code),
                "plan_id": catalog_id("plan", code),
                "version": 1,
                "effective_date": effective,
                "expires_date": None,
                "replaces_plan_version_id": None,
                "migration_policy": "explicit",
                "terms": _json_literal({"catalog_version": "2.0", "edition": code}),
                "created_by_user_id": None,
            }
            for code, _, _ in PLANS
        ],
        multiinsert=False,
    )
    op.bulk_insert(
        Base.metadata.tables["usage_meter_definitions"],
        [
            {
                "id": catalog_id("meter", code),
                "code": code,
                "product": product,
                "meter_kind": kind,
                "unit": unit,
                "aggregation": aggregation,
                "currency_behavior": (
                    "separate_by_currency" if code == "verified_value_events" else "not_applicable"
                ),
                "active": True,
            }
            for code, product, kind, unit, aggregation in USAGE_METERS
        ],
    )
    op.bulk_insert(
        Base.metadata.tables["industry_pack_definitions"],
        [
            {
                "id": catalog_id("pack", code),
                "code": code,
                "name": name,
                "entitlement_key": key,
                "status": "planned"
                if code in {"PACK-J2C", "PACK-MFG", "PACK-PORTS", "PACK-MOB"}
                else "future",
            }
            for code, name, key in INDUSTRY_PACKS
        ],
    )
    op.bulk_insert(
        Base.metadata.tables["limit_definitions"],
        [
            {
                "id": catalog_id("limit", key),
                "entitlement_key": key,
                "meter_code": meter,
                "default_enforcement_type": enforcement,
                "default_reset_period": "monthly",
                "warning_percentage": Decimal("0.8"),
                "grace_percentage": Decimal("0.1") if enforcement == "soft" else Decimal("0"),
            }
            for key, meter, enforcement, _, _ in LIMITS
        ],
    )
    entitlements: list[dict[str, object]] = []
    for plan_code, _, _ in PLANS:
        plan_version_id = catalog_id("plan-version", plan_code)
        for product_code, _, _ in PRODUCTS:
            entitlements.append(
                _plan_entitlement(
                    plan_version_id,
                    f"product.{product_code}",
                    "product",
                    enabled=not (plan_code == "PILOT" and product_code == "I4O-COMMAND"),
                )
            )
        for key, _ in FEATURES:
            enabled = (
                plan_code == "ENTERPRISE"
                or (
                    plan_code == "GROWTH"
                    and key
                    in {
                        "features.sso",
                        "features.audit_export",
                        "intelligence.forecasting",
                        "intelligence.optimization",
                        "recovery.value_ledger",
                        "command.executive_kpis",
                        "commercial.api_access",
                    }
                )
                or (
                    plan_code == "PILOT"
                    and key
                    in {
                        "intelligence.forecasting",
                        "intelligence.optimization",
                        "recovery.value_ledger",
                    }
                )
            )
            entitlements.append(_plan_entitlement(plan_version_id, key, "feature", enabled=enabled))
        feature_keys = {key for key, _ in FEATURES}
        for capability_key in CAPABILITY_KEYS:
            if capability_key in feature_keys:
                continue
            entitlements.append(
                _plan_entitlement(
                    plan_version_id,
                    capability_key,
                    "capability",
                    enabled=not (
                        plan_code == "PILOT" and capability_key == "intelligence.survival"
                    ),
                )
            )
        for _, _, pack_key in INDUSTRY_PACKS:
            entitlements.append(
                _plan_entitlement(
                    plan_version_id,
                    pack_key,
                    "industry_pack",
                    enabled=pack_key == "industry.job_to_cash",
                )
            )
        for key, meter, enforcement, pilot, growth in LIMITS:
            value = pilot if plan_code == "PILOT" else growth if plan_code == "GROWTH" else None
            entitlements.append(
                _plan_entitlement(
                    plan_version_id,
                    key,
                    "limit",
                    enabled=True,
                    limit_value=Decimal(value) if value is not None else None,
                    limit_unit=meter,
                    enforcement_type=enforcement,
                )
            )
    op.bulk_insert(
        Base.metadata.tables["plan_version_entitlements"],
        entitlements,
        multiinsert=False,
    )


def _plan_entitlement(
    plan_version_id: object,
    key: str,
    entitlement_type: str,
    *,
    enabled: bool,
    limit_value: Decimal | None = None,
    limit_unit: str | None = None,
    enforcement_type: str | None = None,
) -> dict[str, object]:
    return {
        "id": catalog_id("plan-entitlement", f"{plan_version_id}:{key}"),
        "plan_version_id": plan_version_id,
        "entitlement_type": entitlement_type,
        "entitlement_key": key,
        "enabled": enabled,
        "limit_value": limit_value,
        "limit_unit": limit_unit,
        "enforcement_type": enforcement_type,
        "reset_period": "monthly" if entitlement_type == "limit" else None,
        "metadata_json": _json_literal({"catalog_version": "2.0"}),
    }


def _json_literal(value: dict[str, object]) -> object:
    return op.inline_literal(json.dumps(value, sort_keys=True))


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(COMMERCIAL_TABLES):
        Base.metadata.tables[table_name].drop(bind=bind, checkfirst=False)
