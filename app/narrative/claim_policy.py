from __future__ import annotations

import re
from enum import StrEnum


class ClaimType(StrEnum):
    GOVERNED_SCAN_FACT = "GOVERNED_SCAN_FACT"
    GOVERNED_FINDING = "GOVERNED_FINDING"
    POTENTIAL_EXPOSURE = "POTENTIAL_EXPOSURE"
    AI_INFERENCE = "AI_INFERENCE"
    CUSTOMER_CONFIRMED_CONTEXT = "CUSTOMER_CONFIRMED_CONTEXT"
    RECOMMENDATION = "RECOMMENDATION"
    LIMITATION = "LIMITATION"
    UNKNOWN = "UNKNOWN"


class ClaimConfidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NOT_ASSESSED = "NOT_ASSESSED"


CONFIDENCE_LANGUAGE = {
    ClaimConfidence.HIGH: "Supported with high confidence within the available governed evidence.",
    ClaimConfidence.MEDIUM: ("Supported with moderate confidence; review the stated limitations."),
    ClaimConfidence.LOW: "Preliminary and supported with low confidence.",
    ClaimConfidence.NOT_ASSESSED: "Confidence has not been assessed.",
}

ZERO_OPPORTUNITY_MESSAGE = (
    "Intel4Ops has not identified any governed, eligible opportunities from the currently "
    "supported analysis. This does not mean the operation is free of problems; additional "
    "governed data or analysis may change the result."
)
PARTIAL_SCAN_MESSAGE = (
    "Supported opportunities exist, but analytical coverage is incomplete. Review the "
    "stated limitations before making decisions."
)
REFUSED_SCAN_MESSAGE = (
    "Available governed data does not support an opportunity assessment. Resolve the "
    "governed data or readiness gap before drawing conclusions."
)

_NUMERIC_PATTERN = re.compile(
    r"(?:\d|[$\u20ac\u00a3\u00a5]|\b(?:USD|EUR|GBP|JPY|CAD|AUD)\b|\bpercent\b|%|"
    r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|hundred|thousand|"
    r"million|billion|trillion)\b)",
    re.IGNORECASE,
)
_PROHIBITED_TRUTH_PATTERN = re.compile(
    r"\b(?:verified\s+(?:value|savings)|realized\s+value|expected\s+recovery|"
    r"root\s+cause(?:\s+identified)?|(?:this|the)\s+intervention\s+will\s+prevent|"
    r"guaranteed\s+outcome|will\s+deliver|caused|causes|causing|drives|driving|"
    r"guarantees?|will\s+prevent|forecast(?:s|ed|ing)?)\b",
    re.IGNORECASE,
)


def contains_generated_number(text: str) -> bool:
    return bool(_NUMERIC_PATTERN.search(text))


def contains_prohibited_truth_claim(text: str) -> bool:
    return bool(_PROHIBITED_TRUTH_PATTERN.search(text))
