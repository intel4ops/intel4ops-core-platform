# Recovery execution and verified-value ledger

WP-2.16 extends an approved WP-2.15 economic baseline through controlled execution,
measurement, finance verification, and append-only value accounting.

## Value semantics

- Expected value is copied from the immutable approved baseline for traceability.
- Realized value is calculated from measurement-period inputs and evidence.
- Verified value is the amount approved by an authorized finance reviewer.
- Adjustments and reversals are new signed ledger entries; posted history is never rewritten.
- Net verified value is rebuilt by summing ledger entries per recovery case and currency.

Revenue recovery and margin protection use actual minus baseline. Cost reduction uses baseline
minus actual. Cash acceleration records time value (`amount × annual rate × days / 365`) rather
than presenting accelerated cash as profit. All calculations use `Decimal`.

## Controls

Every query is organization-scoped. A case must reference an approved WP-2.15 baseline, and an
execution must reference an approved operational action linked to the same opportunity. A
measurement requires evidence before submission. The submitter cannot finance-approve the same
measurement. Approval and the first ledger entry are committed in one transaction and protected
by organization-scoped idempotency keys.

Posted ledger rows have no update or delete API and ORM mutation guards reject changes. Corrections
are append-only adjustments or bounded reversals with explicit lineage. The ledger is Intel4Ops'
verified recovery-value subledger; it is not a customer's statutory general ledger.

## Migration validation

Use revision `20260726_0016`. SQLite is suitable for isolated tests. Live PostgreSQL validation
requires an explicit `TEST_POSTGRES_URL` whose database name contains a disposable safety marker,
plus `CONFIRM_DISPOSABLE_POSTGRES=1`. Never point those settings at production or customer data.
