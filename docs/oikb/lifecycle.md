# OIKB Lifecycle

New versions always begin in `draft`. Submission moves a version to `in_review`.
Deterministic validation cases are persisted with results, engine version, execution
identity, and definition fingerprint. A version can become `validated` only after its
current cases pass.

Approval records the approver, role, decision, notes, and timestamp. Activation records
the actor, timestamp, effective start, and final fingerprint. An effective end must be
later than its start. Future-effective versions are excluded from resolution.

Active versions cannot be edited and cannot receive new validation cases. Changes require
a higher semantic version. An active version may be deprecated and then retired; neither
operation deletes its provenance or history. A rejected version cannot re-enter the
lifecycle; authors create a new version.

Invalid shortcuts, parallel active versions in one scope, duplicate content, and
non-increasing semantic versions return stable conflict or validation errors.
