# P3.xxI.5A Contract / Rate Compliance

## Status

**Implementation:** complete on feature branch; local quality gates complete

**Live hidden-truth certification:** not started; prohibited until merge and deployment

**Expected frozen Wave 1 denominator:** 48 truth items

This milestone adds `CONTRACT-RATE-COMPLIANCE` as an independent governed capability. It does not modify or relabel `REVENUE-AMOUNT-VARIANCE`, XDOM-A, XDOM-B, or MAINT-001.

## Baseline

- Repository baseline: `origin/main` at `a9609e36b95df0d85fabf04cc51a6a1673eae0a5`.
- Phase 1 reconciliation commit retained: `42a457e7902705a0694aebb835bf02bf88378f6b`.
- No application-code change existed on the Phase 1 branch before this implementation.
- No open or newer conflicting pull request existed at implementation start.
- Pre-implementation breadth was 40% registered portfolio breadth, 10% graduated-family breadth, and 19.04% observed certified TP coverage.

## Pre-implementation architecture diagnosis

### A. Safe actual applied rate

Before P3.xxI.5A, actual applied rate was not represented as a distinct canonical concept. `unit_price` could represent a per-unit price and `hourly_rate` a reference rate, while `invoice_amount` represented a total. None alone proved an actual charged rate.

The implementation adds `actual_applied_rate`, restricted to explicit generic aliases:

- `actual_applied_rate`
- `applied_rate`
- `billed_rate`
- `charged_rate`
- `invoiced_rate`
- `invoice_unit_rate`

A bare `rate`, `price`, `unit_price`, `amount`, contract/reference rate, standard cost, or invoice total is not promoted to actual-rate evidence.

### B. Governed contract rate

The existing cross-dataset rate resolver remains authoritative. It resolves exactly one contract-keyed rate using:

- governed contract identity;
- explicit rate value;
- explicit UOM or the existing `hourly_rate` implicit-hour contract;
- native currency compatibility;
- `effective_from` / `effective_to` applicability;
- ambiguity abstention.

There is no nearest-rate fallback and no truth-directed selection.

### C. Separate concepts

Actual and contractual rates are now separate at the canonical evidence boundary:

- actual: `actual_applied_rate`;
- applicable contract rate: existing `unit_price` or `hourly_rate` on a governed contract/reference rate row.

An invoice-shaped unit price is excluded from contract-rate input when billing identity/status or explicit actual-rate evidence shows that the row is transactional.

### D. Direct rate-level comparison

The capability compares rates directly. It never reconstructs an actual rate from an invoice total and never calls Revenue Amount Variance to manufacture or relabel a result.

### E. Finding subject

The governed billable subject is reused from the graduated amount capability:

1. `WORK_ORDER` first;
2. `CONTRACT` as the declared alternative.

Each candidate must have an eligible canonical subject and an unambiguous direct or governed one-hop contract relationship.

### F. Generically supported rate families

The mechanical contract supports explicit actual-rate rows for labor, service, equipment, rental, and material/unit pricing when the same canonical evidence contract is satisfied. The implementation does not branch on industry, simulation, tenant, filename, or source schema.

### G. Unsupported evidence classes

The capability abstains on:

- bare or semantically ambiguous rates;
- invoice totals or bare amounts used as a substitute for rate;
- actual rates without governed denominator UOM;
- missing or incompatible currencies;
- missing or ambiguous subject/contract linkage;
- multiple applicable contract rates;
- effective-dated rates without an observed transaction/service timestamp;
- incompatible rate bases without an already-governed exact conversion;
- foreign exchange without a governed FX subsystem;
- quantity whose attribution is insufficient for economic exposure.

## Mechanical contract

For each eligible governed subject and explicit actual-rate row:

1. Resolve the subject and its unique contract.
2. Require an explicit actual applied rate, denominator UOM, and native currency.
3. Resolve exactly one contract rate applicable at the observed timestamp.
4. Require identical normalized denominator units and identical known currencies.
5. Compare the two `Decimal` rates using exact inequality.
6. Publish a Contract/Rate Compliance finding when the rates differ.

No percentage materiality threshold was added. Exact inequality is the authorized safe comparison and the registered rule operator is `NOT_EQUALS`.

Missing evidence is never represented as zero. A positively observed actual rate of zero remains a valid comparison input.

## Actual-rate evidence policy

`actual_applied_rate` is an additive monetary canonical concept with explicit transaction-rate aliases. It participates in the existing semantic confidence engine without changing its thresholds. Its UOM and currency receive the same local sibling-corroboration mechanism used by existing governed rate/amount evidence.

The capability does not accept `unit_price` as actual rate merely because it appears on an invoice. An explicitly named `invoice_unit_rate` is accepted because the source itself distinguishes its role.

## Contract-rate evidence policy

The capability reuses `RateDatasetFields` and `resolve_applicable_rate` without weakening them. A reference rate must retain:

- rate row and dataset lineage;
- contract key;
- rate basis source (`EXPLICIT_UNIT_COLUMN` or the existing governed `IMPLICIT_UNIT_CONCEPT` for `hourly_rate`);
- normalized unit;
- native currency;
- exact effective window.

Overlapping matches, unresolved temporal authority, negative/missing rates, unknown basis, and incompatible currency/UOM all abstain.

## UOM and currency policy

- Bare rate without governed basis: abstain.
- Compatible normalized basis, such as hour/hour: compare.
- Day/hour or unit/hour: abstain unless a future governed conversion exists.
- Both currencies must be known and equal.
- No implicit FX or cross-currency aggregation occurs.
- Rate evidence remains native-currency evidence.

## Temporal applicability

If a rate row declares an effective boundary, the actual-rate row must carry a governed observation timestamp. Expired and future rates are excluded. More than one surviving rate is ambiguous and produces no finding. A timestamp is optional only when the rate row declares no temporal boundary.

## Readiness

The independent registry entry requires:

- one eligible governed `WORK_ORDER` or `CONTRACT` subject;
- an explicit `actual_applied_rate` concept;
- a governed `unit_price` or `hourly_rate` contract-rate concept.

This is the case-level structural gate. Candidate evaluation then applies the stricter evidence requirements declared by the pack: governed subject linkage, governed contract rate, explicit actual rate, compatible basis, compatible currency, and unambiguous temporal applicability. A structurally READY case may therefore contain individual abstaining rows; it cannot publish from incomplete candidate evidence.

The capability uses the same governed activation-decision persistence and finding publication path as the existing packs.

## Finding identity and lineage

Every finding preserves two stable identity roles:

- subject: concrete governed `work_order` or `contract` key;
- material condition: actual dataset/row, applicable contract-rate dataset/row, compared rates, UOM, and currency.

Distinct subjects and distinct rate conditions cannot collapse into a case-wide finding.

Evidence includes:

- subject and contract entities;
- actual applied rate, UOM, currency, dataset, row, and observed timestamp;
- applicable contract rate, UOM, currency, dataset, row, rate-basis source, and effective window;
- absolute rate variance;
- relative rate variance when the contract rate is nonzero;
- exact comparison method;
- exposure calculation when available;
- all contributing datasets through the governed publisher.

## Exposure semantics

The finding remains valid when quantity is unavailable; exposure is then `None` with no currency metadata.

When a positive governed quantity is co-located and attributable to the actual-rate row:

`economic exposure = absolute(actual rate - contract rate) × governed quantity`

This is exposure magnitude, not a recovered value. Contract/Rate Compliance and Revenue Amount Variance remain distinct findings. Any future portfolio recovery rollup requires a governed overlap policy before summing their economic effects.

## Test matrix

The dedicated suite covers:

| Case | Expected result |
|---|---|
| Actual 120/hour vs contract 100/hour | One rate-compliance finding |
| Equal actual and contract rates | No finding |
| Temporally applicable rate among historical/future alternatives | Correct applicable rate selected |
| Generic equipment/service fixture | Finding without domain-specific branch |
| Multiple subjects | Distinct finding identities |
| Bare actual rate without UOM | Abstain |
| Different currencies | Abstain |
| Different rate bases | Abstain |
| Multiple applicable contract rates | Abstain |
| Unresolved actual-rate semantics | Abstain |
| Missing contract linkage | Abstain |
| Rate-card value offered as actual billing | Abstain |
| Missing quantity | Finding retained; exposure unavailable |
| Explicit actual rate zero | Valid mismatch, not treated as missing |
| Contract as governed subject | Supported |
| Generic orchestration fixture | Governed READY and six independent findings |

Current focused evidence:

- Dedicated capability matrix: 16 passed.
- Capability plus Revenue Amount and activation regression slice: 41 passed.
- Broader required focus matrix: 227 passed.
- Full non-PostgreSQL suite: 1,714 passed, 82 deselected, with one unrelated
  `test_mapping_execution_contract` newest-row ordering assertion failing once; the isolated
  test passed twice immediately afterward. No mapping-execution application code was changed.
- Fresh disposable PostgreSQL suite: 82 passed, 1,715 deselected.
- `ruff format --check .`: 806 files already formatted.
- `ruff check .`: passed.
- `mypy .`: 619 source files passed.

The pull-request CI run remains the authoritative clean-run check for the isolated
mapping-order timing failure.

## Regression controls

The implementation does not modify the Revenue Amount calculation or finding contract. Its tests remain the direct regression control for:

- FieldMaintenance 61 / 0 / 86 / 26 behavior;
- certified TP 150, FN 16, recall 90.36%;
- zero mechanical/fabricated FP;
- subject generalization;
- governed duration;
- governed rate-basis/UOM;
- XDOM-A, XDOM-B, and MAINT-001;
- finding identity, lineage, Trust, validation isolation, and tenant isolation.

No hidden truth has been read by the new service or used in a pre-merge production run.

## Expected post-merge certification denominator

The authoritative frozen Wave 1 Contract/Rate Compliance family contains:

- 26 `contract_rate_mismatch` items;
- 22 `rental_rate_mismatch` items;
- total: **48**.

The denominator is fixed before certification and will not be changed after observing results. Prior independently certified evidence showed 24 mechanically correct FieldMaintenance rate mismatches, but this implementation does not relabel those historical findings.

Rental remains expected to abstain where the customer/source data lacks governed rate-basis evidence. That is a data-contract boundary, not authorization to infer a day/hour/unit basis.

## Implementation PR and CI state

- Branch: `feature/p3xxi5a-contract-rate-compliance`
- Implementation commit: pending
- Pull request: pending
- CI: pending
- Merge authorization: not granted

## Post-merge certification placeholder

Live certification must occur only after owner-authorized merge and deployment. It will record separately:

- READY and abstention counts;
- supported and unsupported evidence counts;
- TP / FP / FN, precision, recall, and economic-value capture;
- overlap with Revenue Amount Variance;
- mechanical/fabricated false positives;
- exact remaining failure classifications;
- before/after registered, graduated-family, truth-weighted, and measurable economic breadth.

No live hidden-truth certification result is claimed by this implementation report.
