from __future__ import annotations

from dataclasses import dataclass, field

from app.intelligence_packs.registry import IntelligencePackDefinition


@dataclass(frozen=True)
class IntelligenceReadinessResult:
    pack: IntelligencePackDefinition
    status: str  # READY | PARTIAL | BLOCKED
    missing_domains: frozenset[str] = field(default_factory=frozenset)
    missing_fields: frozenset[str] = field(default_factory=frozenset)
    missing_entities: frozenset[str] = field(default_factory=frozenset)
    unresolved_currency: bool = False
    reason: str = ""


def evaluate_readiness(
    pack: IntelligencePackDefinition,
    available_domains: set[str],
    available_fields: set[str],
    resolved_entity_types: set[str],
    currency_unresolved: bool = False,
) -> IntelligenceReadinessResult:
    """Explainable readiness -- never a generic 'engine unavailable'.
    BLOCKED names exactly what's missing so Navigator can say e.g. "this
    intelligence could run if job_start_time were available"."""
    missing_domains = pack.required_domains - available_domains
    missing_fields = pack.required_canonical_fields - available_fields
    missing_entities = pack.required_entities - resolved_entity_types
    unresolved_currency = pack.currency_required and currency_unresolved

    if (
        not missing_domains
        and not missing_fields
        and not missing_entities
        and not unresolved_currency
    ):
        return IntelligenceReadinessResult(pack=pack, status="READY")

    reasons = []
    if missing_domains:
        reasons.append(f"missing domains: {', '.join(sorted(missing_domains))}")
    if missing_fields:
        reasons.append(f"missing canonical fields: {', '.join(sorted(missing_fields))}")
    if missing_entities:
        reasons.append(f"missing resolved entities: {', '.join(sorted(missing_entities))}")
    if unresolved_currency:
        reasons.append("currency required but unresolved")
    return IntelligenceReadinessResult(
        pack=pack,
        status="BLOCKED",
        missing_domains=frozenset(missing_domains),
        missing_fields=frozenset(missing_fields),
        missing_entities=frozenset(missing_entities),
        unresolved_currency=unresolved_currency,
        reason="; ".join(reasons),
    )
