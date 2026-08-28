from __future__ import annotations

from app.ground_truth_validation.ontology import IntegrityIssue, NormalizedPackage

# Generic package-integrity checks (section 10). Operate purely on the
# normalized ontology -- never on a specific adapter's source field names.
# error severity should block persistence; warning should not (the caller
# decides, see app/ground_truth_validation/service.py).

_VALID_CURRENCY_LENGTH = 3


def validate_package_integrity(package: NormalizedPackage) -> list[IntegrityIssue]:
    issues: list[IntegrityIssue] = []

    finding_ids = _check_duplicates(
        [f.truth_finding_id for f in package.expected_findings], "expected_findings", issues
    )
    leakage_ids = _check_duplicates(
        [leakage.truth_leakage_id for leakage in package.leakage_truth], "leakage_truth", issues
    )
    _check_duplicates([c.truth_causal_id for c in package.causal_truth], "causal_truth", issues)
    _check_duplicates(
        [d.truth_dq_id for d in package.data_quality_truth], "data_quality_truth", issues
    )

    # Dangling references: an expected finding or causal-truth record that
    # links to a leakage_id no leakage_truth record actually declares.
    for finding in package.expected_findings:
        if finding.linked_leakage_id and finding.linked_leakage_id not in leakage_ids:
            issues.append(
                IntegrityIssue(
                    severity="error",
                    code="dangling_leakage_reference",
                    message=(
                        f"expected finding {finding.truth_finding_id!r} references "
                        f"leakage_id {finding.linked_leakage_id!r}, which does not exist "
                        "in leakage_truth"
                    ),
                    document_role="expected_findings",
                    truth_ref=finding.truth_finding_id,
                )
            )
    for causal in package.causal_truth:
        if causal.linked_leakage_id and causal.linked_leakage_id not in leakage_ids:
            issues.append(
                IntegrityIssue(
                    severity="error",
                    code="dangling_leakage_reference",
                    message=(
                        f"causal truth {causal.truth_causal_id!r} references "
                        f"leakage_id {causal.linked_leakage_id!r}, which does not exist "
                        "in leakage_truth"
                    ),
                    document_role="causal_truth",
                    truth_ref=causal.truth_causal_id,
                )
            )
        if causal.linked_finding_id and causal.linked_finding_id not in finding_ids:
            issues.append(
                IntegrityIssue(
                    severity="warning",
                    code="dangling_finding_reference",
                    message=(
                        f"causal truth {causal.truth_causal_id!r} references "
                        f"finding_id {causal.linked_finding_id!r}, which does not exist "
                        "in expected_findings"
                    ),
                    document_role="causal_truth",
                    truth_ref=causal.truth_causal_id,
                )
            )

    # Invalid currency codes -- never guessed, only shape-checked.
    for finding in package.expected_findings:
        if finding.currency and (
            len(finding.currency) != _VALID_CURRENCY_LENGTH or not finding.currency.isupper()
        ):
            issues.append(
                IntegrityIssue(
                    severity="warning",
                    code="invalid_currency_code",
                    message=(
                        f"expected finding {finding.truth_finding_id!r} has "
                        f"non-ISO4217-shaped currency {finding.currency!r}"
                    ),
                    document_role="expected_findings",
                    truth_ref=finding.truth_finding_id,
                )
            )
    for leakage in package.leakage_truth:
        if leakage.currency and (
            len(leakage.currency) != _VALID_CURRENCY_LENGTH or not leakage.currency.isupper()
        ):
            issues.append(
                IntegrityIssue(
                    severity="warning",
                    code="invalid_currency_code",
                    message=(
                        f"leakage truth {leakage.truth_leakage_id!r} has "
                        f"non-ISO4217-shaped currency {leakage.currency!r}"
                    ),
                    document_role="leakage_truth",
                    truth_ref=leakage.truth_leakage_id,
                )
            )

    # Malformed time windows -- present but not shaped like a window at all.
    for leakage in package.leakage_truth:
        window = leakage.time_window
        if window is not None and not ({"start", "end"} & set(window.keys())):
            issues.append(
                IntegrityIssue(
                    severity="warning",
                    code="malformed_time_window",
                    message=(
                        f"leakage truth {leakage.truth_leakage_id!r} has a time_window "
                        "with no recognizable start/end keys"
                    ),
                    document_role="leakage_truth",
                    truth_ref=leakage.truth_leakage_id,
                )
            )

    # Manifest checksum / declared-document consistency.
    if package.manifest is not None:
        for document in package.documents:
            if not document.checksum:
                continue
            expected_checksum = None
            if document.storage_reference:
                filename = document.storage_reference.rsplit("/", 1)[-1]
                expected_checksum = package.manifest.checksums.get(filename)
            if expected_checksum and expected_checksum != document.checksum:
                issues.append(
                    IntegrityIssue(
                        severity="error",
                        code="manifest_checksum_mismatch",
                        message=(
                            f"document role {document.detected_role or document.declared_role!r} "
                            "checksum does not match the manifest's declared checksum"
                        ),
                        document_role=document.detected_role or document.declared_role,
                    )
                )

    return issues


def _check_duplicates(ids: list[str], document_role: str, issues: list[IntegrityIssue]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for truth_id in ids:
        if truth_id in seen:
            duplicates.add(truth_id)
        seen.add(truth_id)
    for duplicate in sorted(duplicates):
        issues.append(
            IntegrityIssue(
                severity="error",
                code="duplicate_truth_id",
                message=f"duplicate truth id {duplicate!r} in {document_role}",
                document_role=document_role,
                truth_ref=duplicate,
            )
        )
    return seen
