"""P3.xxE.3 section 8: identifier normalization policy edge cases."""

from app.entities.identifier_normalization import (
    NORMALIZATION_POLICY_VERSION,
    normalize_identifier,
)


def test_trims_and_casefolds() -> None:
    assert normalize_identifier("  WO-123  ") == "wo-123"


def test_collapses_internal_whitespace() -> None:
    assert normalize_identifier("WO   123") == "wo 123"


def test_case_insensitive_equality() -> None:
    assert normalize_identifier("Asset-1") == normalize_identifier("asset-1")


def test_does_not_strip_separators_or_leading_zeros() -> None:
    """Deliberately conservative -- collision risk (section 8), not
    silently applied without a new policy version."""
    assert normalize_identifier("WO-00123") != normalize_identifier("WO00123")
    assert normalize_identifier("007") != normalize_identifier("7")


def test_empty_and_whitespace_only_normalize_to_empty_string() -> None:
    assert normalize_identifier("") == ""
    assert normalize_identifier("   ") == ""


def test_policy_version_is_a_stable_string() -> None:
    assert isinstance(NORMALIZATION_POLICY_VERSION, str)
    assert NORMALIZATION_POLICY_VERSION
