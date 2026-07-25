# OIKB Governance

Definitions have stable uppercase dot-separated codes that are never version numbers or
database identifiers. Versions use `MAJOR.MINOR.PATCH`; a new version must sort after all
existing versions for its definition. Duplicate fingerprints are rejected.

Quality and lifecycle are separate. Quality values are experimental, provisional,
validated, production, and reference grade. Lifecycle values are:

```text
DRAFT -> IN_REVIEW -> VALIDATED -> APPROVED -> ACTIVE -> DEPRECATED -> RETIRED
                    \-> REJECTED
```

Validation cases must pass before `VALIDATED`. An approval record is created at
`APPROVED`. Approval and validation are required for `ACTIVE`; only one active version
is allowed per definition specialization. Active versions and their validation cases
are immutable. Deprecated and retired knowledge remains queryable and auditable.

Every lifecycle transition writes `oikb_change_log`. Approval identity, activation
identity and time, effective dates, validation status, source links, and deterministic
fingerprint remain attached to the version.

Existing membership roles are mapped conservatively: organization administrators
govern and activate; administrators and analysts author and validate; active members
read. Platform administrators govern shared system definitions. The conceptual fine
grained reviewer roles remain a future authorization enhancement.

Name matches do not imply equivalence. Relationships can classify true duplicates,
industry specializations, parameter variants, unit variants, semantic collisions,
version candidates, and definitions requiring domain review.
