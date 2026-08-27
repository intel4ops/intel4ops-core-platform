from __future__ import annotations

from dataclasses import dataclass

from app.domain_registry import DOMAIN_SIGNATURES, DomainSignature, canonicalize_field
from app.models.analysis_case import DetectionStatus


@dataclass(frozen=True)
class DomainDetectionResult:
    domain: str | None
    basis: list[str]
    status: str


@dataclass(frozen=True)
class _SignatureMatch:
    signature: DomainSignature
    matched_fields: frozenset[str]


def detect_domain(columns: list[str]) -> DomainDetectionResult:
    """Deterministic schema-signature matching only -- no fabricated
    confidence score. `confirmed` requires every signature field present;
    `needs_review` on a partial match against the strongest candidate;
    `unknown` if nothing matches at all."""
    basis_by_field: dict[str, str] = {}
    for column in columns:
        canonical = canonicalize_field(column)
        if canonical is not None:
            basis_by_field[canonical] = column
    canonical_present = set(basis_by_field.keys())

    candidates: list[_SignatureMatch] = []
    best_score = 0
    for signature in DOMAIN_SIGNATURES:
        matched = signature.required_canonical_fields & canonical_present
        if not matched:
            continue
        if len(matched) > best_score:
            best_score = len(matched)
            candidates = [_SignatureMatch(signature, matched)]
        elif len(matched) == best_score:
            candidates.append(_SignatureMatch(signature, matched))

    if not candidates:
        return DomainDetectionResult(domain=None, basis=[], status=DetectionStatus.UNKNOWN)

    # Prefer the signature with the most required fields overall when tied
    # on matched-field count -- a more specific signature is a better guess
    # than a generic one that happens to share the same overlap size.
    chosen = max(candidates, key=lambda m: len(m.signature.required_canonical_fields))
    basis = sorted(basis_by_field[field] for field in chosen.matched_fields)
    is_confirmed = chosen.matched_fields == chosen.signature.required_canonical_fields
    return DomainDetectionResult(
        domain=chosen.signature.domain,
        basis=basis,
        status=DetectionStatus.CONFIRMED if is_confirmed else DetectionStatus.NEEDS_REVIEW,
    )
