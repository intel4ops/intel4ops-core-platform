from __future__ import annotations

from uuid import UUID, uuid5

CATALOG_NAMESPACE = UUID("6914f2ed-d7cb-43ff-a255-4f0c91d4f217")


def catalog_id(kind: str, code: str) -> UUID:
    return uuid5(CATALOG_NAMESPACE, f"{kind}:{code}")


PRODUCTS = (
    ("I4O-CONNECT", "Intel4Ops Connect", "Connect operational data without replacing systems."),
    ("I4O-TRUST", "Intel4Ops Trust", "Determine whether data is reliable for decisions."),
    ("I4O-INTEL", "Intel4Ops Intelligence", "Detect, explain, predict, and optimize leakage."),
    ("I4O-COMMAND", "Intel4Ops Command", "Show leaders what requires attention and why."),
    ("I4O-RECOVERY", "Intel4Ops Recovery", "Convert intelligence into verified value."),
    ("I4O-PLATFORM", "Intel4Ops Platform", "Secure, govern, commercialize, and scale products."),
)

PLANS = (
    ("PILOT", "Pilot / Value Scan", "pilot"),
    ("GROWTH", "Growth", "growth"),
    ("ENTERPRISE", "Enterprise", "enterprise"),
    ("PARTNER", "Partner Delivery", "partner"),
    ("OEM", "OEM / Embedded", "oem"),
)

FEATURES = (
    ("features.sso", "Enterprise SSO"),
    ("features.scim", "SCIM Provisioning"),
    ("features.audit_export", "Advanced Audit Export"),
    ("features.simulation_suite", "Simulation Suite"),
    ("features.custom_pack_extensions", "Custom Industry Pack Extension"),
    ("support.premium", "Premium Support"),
    ("deployment.dedicated", "Dedicated Deployment"),
    ("commercial.oem_api", "OEM API Rights"),
    ("commercial.white_label", "White-label Presentation"),
    ("intelligence.forecasting", "Forecasting"),
    ("intelligence.optimization", "Optimization"),
    ("recovery.value_ledger", "Verified-value Ledger"),
    ("command.executive_kpis", "Executive KPIs"),
    ("commercial.api_access", "API Access"),
    ("commercial.partner_apis", "Partner APIs"),
)

CAPABILITY_KEYS = (
    "platform.tenancy",
    "platform.postgresql",
    "security.memberships",
    "security.permissions",
    "security.tenant_isolation",
    "registry.industry_packs",
    "registry.capabilities",
    "connect.source_systems",
    "connect.ingestion_batches",
    "connect.datasets",
    "connect.lineage",
    "connect.canonical_mapping",
    "connect.mapping_versions",
    "connect.api_ingestion",
    "connect.file_ingestion",
    "trust.rule_execution",
    "trust.readiness",
    "trust.evidence",
    "trust.policies",
    "intelligence.arithmetic",
    "intelligence.rules",
    "intelligence.findings",
    "intelligence.finding_evidence",
    "intelligence.recommendations",
    "intelligence.causal_links",
    "intelligence.orchestrator",
    "intelligence.model_registry",
    "intelligence.advanced_analytics",
    "intelligence.statistics",
    "intelligence.anomaly_detection",
    "intelligence.change_detection",
    "intelligence.forecasting",
    "intelligence.forecast_confidence",
    "intelligence.reliability",
    "intelligence.survival",
    "intelligence.optimization",
    "recovery.action_orchestration",
    "recovery.action_lifecycle",
    "recovery.exposure",
    "recovery.scenarios",
    "recovery.economics",
    "recovery.prioritization",
    "recovery.overlap_control",
    "recovery.economic_baselines",
    "recovery.workflow",
    "recovery.measurement",
    "recovery.value_states",
    "recovery.verification",
    "recovery.finance_approval",
    "recovery.value_ledger",
    "recovery.adjustments",
    "recovery.currency_safe_reporting",
)

USAGE_METERS = (
    ("active_users", "Platform", "snapshot", "users", "maximum"),
    ("active_sources", "Connect", "snapshot", "sources", "maximum"),
    ("files_ingested", "Connect", "event", "files", "sum"),
    ("rows_processed", "Connect / Trust", "event", "rows", "sum"),
    ("api_requests", "Platform", "event", "requests", "sum"),
    ("storage_gb_month", "Platform", "snapshot", "GB-month", "maximum"),
    ("rule_executions", "Intelligence", "event", "executions", "sum"),
    ("model_runs", "Intelligence", "event", "runs", "sum"),
    ("forecast_points", "Intelligence", "event", "forecast points", "sum"),
    ("assets_analyzed", "Intelligence", "snapshot", "assets", "distinct"),
    ("optimization_runs", "Intelligence", "event", "runs", "sum"),
    ("recovery_opportunities", "Recovery", "snapshot", "active opportunities", "maximum"),
    ("verification_reviews", "Recovery", "event", "reviews", "sum"),
    ("ledger_entries", "Recovery", "event", "entries", "sum"),
    ("verified_value_events", "Recovery", "event", "events", "sum"),
    ("dashboard_queries", "Command", "event", "queries", "sum"),
    ("simulation_runs", "Platform", "event", "runs", "sum"),
    ("enabled_packs", "Platform", "snapshot", "packs", "maximum"),
)

INDUSTRY_PACKS = (
    ("PACK-J2C", "Job-to-Cash", "industry.job_to_cash"),
    ("PACK-MFG", "Manufacturing", "industry.manufacturing"),
    ("PACK-PORTS", "Ports and Terminals", "industry.ports"),
    ("PACK-MOB", "Mobility and Public Transport", "industry.mobility"),
    ("PACK-OIL-UP", "Oil & Gas Upstream", "industry.oil_gas_upstream"),
    ("PACK-UTIL", "Utilities", "industry.utilities"),
    ("PACK-MINING", "Mining", "industry.mining"),
)

# key, meter, enforcement, Pilot, Growth. Enterprise is contract-defined.
LIMITS = (
    ("limits.active_users", "active_users", "hard", "10", "50"),
    ("limits.source_systems", "active_sources", "hard", "3", "10"),
    ("limits.files_ingested", "files_ingested", "soft", "100", "2000"),
    ("limits.rows_processed", "rows_processed", "soft", "5000000", "100000000"),
    ("limits.api_requests", "api_requests", "soft", "25000", "500000"),
    ("limits.storage_gb", "storage_gb_month", "soft", "25", "500"),
    ("limits.industry_packs", "enabled_packs", "hard", "1", "3"),
    ("limits.models", "model_runs", "hard", "10", "100"),
    ("limits.model_runs", "model_runs", "soft", "500", "20000"),
    ("limits.optimization_runs", "optimization_runs", "soft", "50", "2000"),
    ("limits.recovery_opportunities", "recovery_opportunities", "soft", "50", "1000"),
    ("limits.verification_reviews", "verification_reviews", "soft", "20", "500"),
    ("limits.simulation_runs", "simulation_runs", "soft", "10", "250"),
)
