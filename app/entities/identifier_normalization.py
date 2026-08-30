from __future__ import annotations

# ---------------------------------------------------------------------------
# P3.xxE.3 section 8: identifier normalization. The algorithm shape is
# reused from Canonical Mapping's EntityResolutionService
# (app/services/canonical_mapping_service.py's _normalized(): trim +
# casefold + whitespace-collapse) -- rewritten fresh here, not imported,
# per the P3.xxE.3 reconciliation decision to keep this milestone's
# resolution logic structurally independent of that system's cross-run,
# org-wide entity master (see the plan's reconciliation table).
#
# Versioned so a future policy change (e.g. stripping leading zeros,
# unicode NFKC normalization) is a new version string, never a silent
# behavior change -- stored on every EntityObservation/CanonicalEntity.
# ---------------------------------------------------------------------------

NORMALIZATION_POLICY_VERSION = "v1"


def normalize_identifier(value: object) -> str:
    """Trim + casefold + collapse internal whitespace. Deliberately does
    NOT strip punctuation/separators or leading zeros -- those are real
    collision risks (see spec section 8's "only where collision risk/
    evidence permits") left for a future normalization_policy_version,
    not silently applied here."""
    return " ".join(str(value).strip().casefold().split())
