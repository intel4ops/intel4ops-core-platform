from __future__ import annotations

import hashlib
from enum import StrEnum

# ---------------------------------------------------------------------------
# P3.xxE.3 Entity + Relationship Intelligence: the canonical operational
# entity-type vocabulary. Extends app/semantic/concept_registry.py's
# existing CanonicalConcept.compatible_entity_types values (ASSET,
# WORK_ORDER, CUSTOMER, INVOICE, PERSON, PART) rather than the unrelated
# lowercase BASE_CANONICAL_ENTITY_TYPES (app/models/analysis_case.py) or
# Canonical Mapping's separate governed CanonicalEntityType DB registry --
# see the P3.xxE.3 plan's reconciliation table.
#
# LOCATION/CONTRACT/PRODUCT/TRANSACTION/EVENT are defined here but have no
# backing CanonicalConcept registered yet -- an accepted, documented gap
# (concept curation is P3.xxE.1's job, not P3.xxE.3's). infer_entity_type()
# will simply never produce them until someone registers the concepts.
#
# OTHER is reserved for a future catch-all and is never asserted by any
# code in this milestone -- asserting it on ambiguous/unresolved evidence
# would violate "no entity type inferred without a governed concept".
# ---------------------------------------------------------------------------


class EntityType(StrEnum):
    ASSET = "ASSET"
    WORK_ORDER = "WORK_ORDER"
    CUSTOMER = "CUSTOMER"
    INVOICE = "INVOICE"
    PERSON = "PERSON"
    PART = "PART"
    LOCATION = "LOCATION"
    CONTRACT = "CONTRACT"
    PRODUCT = "PRODUCT"
    TRANSACTION = "TRANSACTION"
    EVENT = "EVENT"
    OTHER = "OTHER"


# Entity types whose identifiers may carry personal data -- gates the raw
# raw_value persistence policy in app/models/entities_canonical.py's
# CanonicalEntityObservation (plan review correction: do not unconditionally
# duplicate potentially-sensitive raw identifiers into the new layer).
SENSITIVE_ENTITY_TYPES = frozenset({EntityType.PERSON.value, EntityType.CUSTOMER.value})


def observation_value_fields(entity_type: str, raw_value: str) -> tuple[str | None, str | None]:
    """Returns (raw_value_to_persist, raw_value_hash_to_persist). For
    sensitive entity types, raw_value stays None and a sha256 hash is
    persisted instead -- enough for dedup/explainability audit without
    duplicating the raw identifier. Pragmatic (one boolean lookup), not a
    PII-classification subsystem."""
    if entity_type in SENSITIVE_ENTITY_TYPES:
        return None, hashlib.sha256(raw_value.encode("utf-8")).hexdigest()
    return raw_value, None
