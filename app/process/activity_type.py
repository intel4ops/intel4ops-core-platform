from __future__ import annotations

from enum import StrEnum

# ---------------------------------------------------------------------------
# P3.xxE.4 Operational Process Interpretation: the canonical process
# ontology. Deliberately compact and generic (spec section 4) -- no
# industry-specific values (no "PRESSURE_PUMPING_STAGE", no
# "WORKOVER_ACTIVITY"). GENERIC is the explicit escape hatch: an activity
# whose existence is well-supported but whose type cannot be named at
# sufficient confidence (plan review correction 1) stays GENERIC rather
# than being forced into a named type.
# ---------------------------------------------------------------------------


class ActivityType(StrEnum):
    CREATE = "CREATE"
    SCHEDULE = "SCHEDULE"
    START = "START"
    PERFORM = "PERFORM"
    COMPLETE = "COMPLETE"
    CLOSE = "CLOSE"
    CANCEL = "CANCEL"
    INVOICE = "INVOICE"
    PAY = "PAY"
    INSPECT = "INSPECT"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    TRANSFER = "TRANSFER"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"
    # Plan review correction 1: the placeholder used when existence is
    # supported but naming the type is not (REVIEW_REQUIRED-tier evidence
    # alone, or an uncorroborated ACCEPTED_WITH_FLAG observation).
    GENERIC = "GENERIC"


class ParticipationRole(StrEnum):
    """Never inferred solely from entity_type (spec section 14) -- a
    PERSON could be ACTOR/CUSTOMER/APPROVER/OWNER depending on evidence."""

    SUBJECT = "SUBJECT"
    ACTOR = "ACTOR"
    RESOURCE = "RESOURCE"
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"
    REFERENCE = "REFERENCE"
    LOCATION = "LOCATION"
    UNKNOWN = "UNKNOWN"


class ProcessEdgeType(StrEnum):
    PRECEDES = "PRECEDES"
    CONCURRENT = "CONCURRENT"
    OPTIONAL_BRANCH = "OPTIONAL_BRANCH"
    LOOP = "LOOP"
    STATE_TRANSITION = "STATE_TRANSITION"
    ORDER_UNRESOLVED = "ORDER_UNRESOLVED"


class BoundaryStatus(StrEnum):
    LEFT_CENSORED = "LEFT_CENSORED"
    RIGHT_CENSORED = "RIGHT_CENSORED"
    PARTIAL = "PARTIAL"
    COMPLETE = "COMPLETE"
    UNKNOWN = "UNKNOWN"


class ProcessStatus(StrEnum):
    AUTO_ACCEPTED = "AUTO_ACCEPTED"
    ACCEPTED_WITH_FLAG = "ACCEPTED_WITH_FLAG"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    CONFLICTED = "CONFLICTED"
