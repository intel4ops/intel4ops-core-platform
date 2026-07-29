# Phase 1B Deferred Decision Register

These items were deliberately excluded from bounded Phase 1B remediation.

| Finding | Subject | Reason deferred | Risk | Required decision | Recommended phase |
|---|---|---|---|---|---|
| FR-013 | Source history and versioning | Requires a new immutable aggregate, retention policy, and migration strategy. | Historical source configuration cannot be reconstructed fully. | Approve version identity, change capture, retention, and references from downstream records. | New WP-2.x foundation extension |
| FR-015 | Governed Trust input | Requires immutable selection snapshots, data access policy, lineage, limits, and synchronous/asynchronous execution design. | Inline/manual records are not provably the governed stored records. | Approve input modes, snapshot contract, digest, retention, and reproducibility semantics. | New WP-2.x foundation extension before broader Phase 3 |
| FR-016 | Canonical schema and mapping persistence | Requires versioned schema and mapping aggregates, ownership, lifecycle, compatibility, and materialization design. | Prior assessments cannot bind to exact canonical and mapping versions. | Approve aggregate model, ownership scopes, transformation registry, compatibility, and temporal rules. | New WP-2.x foundation extension before broader Phase 3 |
| FR-017 | Trust dispute and override workflow | Changes governance authority, evidence, lifecycle, and audit responsibilities. | Corrections and disputes remain outside a governed platform workflow. | Define roles, states, evidence requirements, immutable history, and downstream effects. | Later Trust governance work package |
| FR-038 | Shared audit-history architecture | Cross-domain standardization exceeds bounded remediation and may affect every service. | Audit queries and retention remain heterogeneous. | Decide common event envelope, storage, retention, access, and migration strategy. | Platform governance architecture phase |
| FR-039 | Repository/DAL normalization | Broad refactoring carries transaction and regression risk without a bounded business capability. | Persistence and transaction conventions remain inconsistent. | Define repository boundaries, unit-of-work conventions, and incremental adoption rules. | Dedicated maintainability work package |

FR-015 and FR-016 are evaluated in
`docs/phase-1-governed-trust-input-proposal.md`. That document is a proposal only; it is not
implemented, approved, or certified.

Its proposed sequence—governed-input snapshots, persistent canonical and source schema
versions, governed mapping versions, mapped materialization/projections, and Trust binding to
exact input and mapping versions—remains future work.
