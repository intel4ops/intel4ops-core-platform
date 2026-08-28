from __future__ import annotations

from dataclasses import dataclass

from app.domain_registry import (
    DOMAIN_SIGNATURES,
    GENERIC_CANONICAL_FIELDS,
    DomainSignature,
    canonicalize_field,
)
from app.models.analysis_case import DetectionStatus


@dataclass(frozen=True)
class DomainDetectionResult:
    domain: str | None
    basis: list[str]
    status: str
    # P3.xxC.2E: every domain whose signature tied for the best matched-
    # field count, not just the one ultimately chosen -- lets a caller see
    # a genuine ambiguity (e.g. "could be operations or fuel_energy")
    # instead of a single silently-picked guess. Not yet persisted
    # anywhere (dataset registration runs before a Run/stage-event
    # exists to log it against) -- available on the result for direct
    # callers and future wiring, per "if the existing contract supports
    # it."
    candidate_domains: list[str]


@dataclass(frozen=True)
class _SignatureMatch:
    signature: DomainSignature
    matched_fields: frozenset[str]


def detect_domain(columns: list[str]) -> DomainDetectionResult:
    """Deterministic schema-signature matching only -- no fabricated
    confidence score.

    CONFIRMED: every field the chosen signature requires is present.
    NEEDS_REVIEW: a partial match that includes at least one domain-
      specific field (i.e. not just generic entity/context signals) --
      plausible evidence a human should confirm.
    UNKNOWN: no signature matched at all, or the only evidence is generic
      fields (GENERIC_CANONICAL_FIELDS) that are shared across every
      domain and therefore confirm none of them. A dataset containing
      only asset_id must never become "maintenance" on that basis alone.
    """
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
        return DomainDetectionResult(
            domain=None, basis=[], status=DetectionStatus.UNKNOWN, candidate_domains=[]
        )

    candidate_domains = sorted({c.signature.domain for c in candidates})

    # Prefer a fully-satisfied signature over a partial one at the same
    # matched-field count: e.g. asset_id alone fully satisfies the
    # single-field asset_master signature and should resolve to that,
    # not be coerced into a 3-field maintenance signature it only
    # partially satisfies just because maintenance has more required
    # fields overall.
    confirmed_candidates = [
        c for c in candidates if c.matched_fields == c.signature.required_canonical_fields
    ]
    pool = confirmed_candidates or candidates
    # Among remaining ties, prefer the signature with the most required
    # fields overall -- a more specific signature is a better guess than
    # a generic one that happens to share the same overlap size.
    chosen = max(pool, key=lambda m: len(m.signature.required_canonical_fields))
    basis = sorted(basis_by_field[field] for field in chosen.matched_fields)
    is_confirmed = chosen.matched_fields == chosen.signature.required_canonical_fields
    is_generic_only = chosen.matched_fields <= GENERIC_CANONICAL_FIELDS

    if is_confirmed:
        return DomainDetectionResult(
            domain=chosen.signature.domain,
            basis=basis,
            status=DetectionStatus.CONFIRMED,
            candidate_domains=candidate_domains,
        )
    if is_generic_only:
        # Plausible-looking overlap, but every matched field is a generic
        # signal -- not domain-specific evidence, so no domain guess is
        # recorded even though candidate_domains still shows what tied.
        return DomainDetectionResult(
            domain=None,
            basis=basis,
            status=DetectionStatus.UNKNOWN,
            candidate_domains=candidate_domains,
        )
    return DomainDetectionResult(
        domain=chosen.signature.domain,
        basis=basis,
        status=DetectionStatus.NEEDS_REVIEW,
        candidate_domains=candidate_domains,
    )
