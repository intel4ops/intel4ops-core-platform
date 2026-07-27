from __future__ import annotations

from uuid import UUID, uuid5

PACK_NAMESPACE = UUID("49022351-ea4b-4df8-a3b5-14c15bec5099")


def pack_id(kind: str, code: str) -> UUID:
    return uuid5(PACK_NAMESPACE, f"{kind}:{code}")


PACKS: tuple[tuple[str, str, str, str], ...] = (
    ("PACK-J2C", "Job-to-Cash", "job_to_cash", "industry.job_to_cash"),
    ("PACK-MFG", "Manufacturing", "manufacturing", "industry.manufacturing"),
    ("PACK-PORTS", "Ports and Terminals", "ports", "industry.ports"),
    ("PACK-MOB", "Mobility and Public Transport", "mobility", "industry.mobility"),
)

RULES: dict[str, tuple[str, ...]] = {
    "PACK-J2C": ("CNI-001", "UNDERBILL", "MARGIN", "DOC", "PAYMENT", "REWORK"),
    "PACK-MFG": ("DOWNTIME", "SCRAP", "YIELD", "MAINT", "INVENTORY", "ENERGY"),
    "PACK-PORTS": ("BERTH", "CRANE", "GATE", "DWELL", "EQUIP", "BILLING"),
    "PACK-MOB": ("TRIP", "FUEL", "FARE", "MAINT", "STAFF", "AVAIL"),
}


def components(code: str) -> list[dict[str, object]]:
    prefix = {"PACK-J2C": "J2C", "PACK-MFG": "MFG", "PACK-PORTS": "PORT", "PACK-MOB": "MOB"}[code]
    result: list[dict[str, object]] = [
        {
            "type": "ontology_mapping",
            "code": f"{prefix}.ONTOLOGY",
            "universal_parent": "operations.process",
            "config": {"mapping": prefix.lower()},
        },
        {
            "type": "canonical_extension",
            "code": f"{prefix}.CANONICAL",
            "universal_parent": "canonical.operational_record",
            "config": {"required_fields": ["record_id", "observed_at", "value"]},
        },
        {
            "type": "metric_definition",
            "code": f"{prefix}.EXPOSURE",
            "universal_parent": "metrics.exposure",
            "config": {"unit_behavior": "declared", "currency_behavior": "organization_default"},
        },
        {
            "type": "evidence_policy",
            "code": f"{prefix}.EVIDENCE",
            "universal_parent": "findings.evidence_policy",
            "config": {
                "required": ["record_id", "observed_at", "value", "threshold"],
                "retain_lineage": True,
            },
        },
        {
            "type": "economic_mapping",
            "code": f"{prefix}.ECONOMICS",
            "universal_parent": "economics.exposure",
            "config": {
                "value_field": "exposure",
                "currency_behavior": "organization_default",
                "aggregation": "no_cross_currency_sum",
            },
        },
        {
            "type": "command_capability",
            "code": f"{prefix}.COMMAND",
            "universal_parent": "command.pack_summary",
            "config": {"dimensions": ["rule_code", "readiness", "status"]},
        },
        {
            "type": "usage_meter_binding",
            "code": f"{prefix}.RULE_EXECUTION",
            "universal_parent": "commercial.usage_meter",
            "config": {"meter_code": "rule_executions", "quantity": 1},
        },
    ]
    for suffix in RULES[code]:
        rule_code = f"{prefix}-{suffix}"
        result.extend(
            (
                {
                    "type": "rule_binding",
                    "code": rule_code,
                    "universal_parent": "oikb.deterministic_rule",
                    "config": {
                        "operator": "greater_than",
                        "input_field": "value",
                        "threshold_field": "threshold",
                        "evidence": ["record_id", "observed_at", "value", "threshold"],
                    },
                },
                {
                    "type": "recovery_playbook",
                    "code": f"{rule_code}.RECOVERY",
                    "universal_parent": "recovery.playbook",
                    "config": {
                        "rule_code": rule_code,
                        "action": f"Investigate and remediate {rule_code}",
                    },
                },
            )
        )
    return result


def manifest(code: str, name: str, industry: str, entitlement: str) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "pack_code": code,
        "version": "1.0.0",
        "name": name,
        "industry": industry,
        "entitlement_key": entitlement,
        "minimum_platform_revision": "20260726_0018",
        "trust_policy": {"minimum_readiness": "supported", "block_unready": True},
        "components": components(code),
    }


MANIFESTS = {
    code: manifest(code, name, industry, entitlement) for code, name, industry, entitlement in PACKS
}
