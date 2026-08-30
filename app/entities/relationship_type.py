from __future__ import annotations

from enum import StrEnum

# ---------------------------------------------------------------------------
# P3.xxE.3 sections 14/17/19: relationship vocabulary. Deliberately NO
# type-pair-to-meaning lookup table here (removed per plan review
# correction 2) -- entity-type pairs may constrain which relationship
# types are structurally plausible, but must never by themselves ASSERT
# which one applies. See app/entities/relationship_discovery.py for the
# evidence-gated algorithm that actually assigns a type.
#
# USES/GENERATES/PERFORMED_BY/LOCATED_AT are defined here (forward-
# declared for P3.xxE.4 Process Interpretation to populate with real
# process-semantic evidence) but are NEVER asserted by any code this
# milestone -- an explicit, documented gap, not an oversight.
# ---------------------------------------------------------------------------


class RelationshipType(StrEnum):
    REFERENCES = "REFERENCES"
    BELONGS_TO = "BELONGS_TO"
    HAS = "HAS"
    USES = "USES"
    GENERATES = "GENERATES"
    PERFORMED_BY = "PERFORMED_BY"
    LOCATED_AT = "LOCATED_AT"
    ASSOCIATED_WITH = "ASSOCIATED_WITH"


# Relationship types this milestone's evidence sources (FK-overlap,
# co-occurrence, cardinality, coarse temporal consistency) can actually
# justify without inventing business/process meaning. Everything else in
# RelationshipType stays defined but unreachable until a future milestone
# adds the evidence source that would justify it.
STRUCTURALLY_REACHABLE_THIS_MILESTONE = frozenset(
    {
        RelationshipType.REFERENCES.value,
        RelationshipType.BELONGS_TO.value,
        RelationshipType.ASSOCIATED_WITH.value,
    }
)


class Cardinality(StrEnum):
    ONE_TO_ONE = "ONE_TO_ONE"
    ONE_TO_MANY = "ONE_TO_MANY"
    MANY_TO_ONE = "MANY_TO_ONE"
    MANY_TO_MANY = "MANY_TO_MANY"
    UNKNOWN = "UNKNOWN"


class RelationshipStatus(StrEnum):
    AUTO_ACCEPTED = "AUTO_ACCEPTED"
    ACCEPTED_WITH_FLAG = "ACCEPTED_WITH_FLAG"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    CONFLICTED = "CONFLICTED"
