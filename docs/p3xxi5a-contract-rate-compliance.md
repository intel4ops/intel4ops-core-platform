# P3.xxI.5A Contract / Rate Compliance

## Status

**Implementation:** merged in PR #121; merge commit
`cf25345411bbb11305503e45e0d290a7625ecbba`

**Live hidden-truth certification:** complete

**P3.xxI.5A FAILED**

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
- Implementation commit: `4863a56`
- Documentation/quality-gate commit: `60e5c29`
- Pull request: [#121](https://github.com/intel4ops/intel4ops-core-platform/pull/121)
- CI: passed (`Ruff, Mypy, Pytest, and Alembic`, 19m54s)
- Merge: owner-authorized; merge commit
  `cf25345411bbb11305503e45e0d290a7625ecbba`
- Local `main`: synchronized exactly to `origin/main`; worktree clean before
  certification.
- Backend health: HTTP 200 from
  `https://intel4ops-core-api.onrender.com/api/v1/health`, response
  `{"status":"ok","platform":"Intel4Ops Core","phase":2}`.

## Post-merge live certification

### Frozen denominator

The denominator was frozen before scoring and was not changed after findings
were observed:

| Truth slice | Items | Truth-authored value |
|---|---:|---:|
| FieldMaintenance `contract_rate_mismatch` | 26 | $7,372.32 |
| Rental `rental_rate_mismatch` | 22 | $416,247.40 |
| **Total** | **48** | **$423,619.72** |

All 26 FieldMaintenance items occur in `FIELDMAINT-001`. The 22 Rental items
occur in `RENTAL-011` (3) and `RENTAL-015` (19). The nine older Rental
`UNDER_BILLING` records in RENTAL-001/003 remain in the separately frozen
missing-`scenario_id` truth-authoring bucket and were not moved into this
denominator after the run.

### Production run results

Fresh runs reused the exact P3.xxI.4 certified orchestrated cases and their
already-loaded frozen inputs. Each run reached a terminal `review_required`
state before examiner-side scoring. This terminal state is not a failed run;
its review issues are the established mapping/domain-review signals.

The Navigator does not expose the per-pack activation payload for these
cases (`PACKS READY 0`, `PACKS BLOCKED 0`, and “backend has not reported
intelligence readiness”). The registered activation contract and persisted
semantic evidence nevertheless resolve the capability deterministically:
every case lacks the required `actual_applied_rate` canonical measure, so
the exact structural result is **BLOCKED on
`measure:actual_applied_rate`**. Candidate count is therefore zero.

| Frozen case | Case ID | Fresh run ID | Contract/Rate readiness | Candidates | Contract/Rate findings | Total persisted findings | Revenue Amount control |
|---|---|---|---|---:|---:|---:|---:|
| FIELDMAINT-001 | `680bc4f2-7dae-4f3c-8189-8f260c309647` | `aaa9e92a-fd2e-463e-83c0-213108f9a162` | BLOCKED: `measure:actual_applied_rate` | 0 | 0 | 63 | 61 |
| FIELDMAINT-002 | `5183aa02-0244-45f5-89fa-a269d137ee58` | `b944224d-ff95-409f-99ff-103946856a17` | BLOCKED: `measure:actual_applied_rate` | 0 | 0 | 1 | 0 |
| FIELDMAINT-005 | `13b35dc0-6d39-49fb-9118-5472309ca820` | `4053af01-65d6-4db8-8e5b-5cd097d58be8` | BLOCKED: `measure:actual_applied_rate` | 0 | 0 | 87 | 86 |
| FIELDMAINT-007 | `ab26536a-c8c5-4643-b705-a006168e8474` | `f8e95d3c-8de2-420f-8aa2-0a3d5cf664d5` | BLOCKED: `measure:actual_applied_rate` | 0 | 0 | 27 | 26 |
| RENTAL-001 | `e4010321-624d-48c1-82cb-6ee2896b3ca1` | `d1faeb5e-5de1-4e4a-b35b-27f67d690ea3` | BLOCKED: `measure:actual_applied_rate` | 0 | 0 | 0 | 0 |
| RENTAL-003 | `0454cd8d-bc01-475d-9b58-45a07166ad89` | `72c47c66-4ad0-4124-98cf-f05bb418549b` | BLOCKED: `measure:actual_applied_rate` | 0 | 0 | 0 | 0 |
| RENTAL-011 | `b0bb051f-4edc-4240-a809-e5e0554c87a4` | `b9fd2200-495e-4560-b522-a992b148727c` | BLOCKED: `measure:actual_applied_rate` | 0 | 0 | 0 | 0 |
| RENTAL-012 | `c2962932-9c20-42c1-8f4b-c25fd48b2a5e` | `8ced8dd0-d850-4bde-bac1-91b5750e479f` | BLOCKED: `measure:actual_applied_rate` | 0 | 0 | 0 | 0 |
| RENTAL-015 | `9e4b4081-a809-4195-96a9-9a1b424a485e` | `5d9ec851-a1e8-4f1f-908e-9affaddd9422` | BLOCKED: `measure:actual_applied_rate` | 0 | 0 | 0 | 0 |
| RENTAL-018 | `f2151483-9984-496c-9698-2b5d0e5a8ac0` | `007ddedd-454a-4f4c-8bb6-6186ca729d70` | BLOCKED: `measure:actual_applied_rate` | 0 | 0 | 0 | 0 |

READY cases: **0/10**. Structural abstentions: **10/10**. Unsupported
evidence cases: **10/10**. Candidate-level abstentions: **0**, because no
case passed the structural gate. Published Contract/Rate findings: **0**.

### Evidence diagnosis and certification questions

The source-schema reconciliation is uniform:

- FieldMaintenance invoices contain `amount`, but no explicit applied-rate
  field. Contract rows contain `labor_rate`, and labor/parts rows contain
  governed quantities, but the implementation intentionally does not derive
  an applied rate from attributable invoice amount divided by billable scope.
  No FieldMaintenance source carries currency either.
- Rental invoices contain `amount`, contracts contain bare `rate`, and
  dispatch rows provide governed duration. No Rental source carries an
  explicit applied rate, a rate-basis/UOM column, or currency.

Consequently:

- activation where governed actual-rate and contract-rate evidence exists:
  **not live-exercised**; no frozen case supplies the required explicit
  actual-rate concept;
- actual/reference-rate separation: **safely preserved**; no contract or
  reference rate was misused as actual evidence;
- UOM, currency, temporal applicability, and governed subject/contract
  linkage: **not reached in live candidate evaluation** because the earlier
  actual-rate gate blocked every case; their pre-merge test evidence remains
  valid but is not promoted to live certification evidence;
- subject-aware finding identity and quantity-gated exposure: **not
  live-exercised**, because no finding was produced;
- missing evidence versus actual rate zero: **safely separated by the
  implementation and tests**, but zero-rate evidence is absent from Wave 1.

### Examiner scoring

| Metric | Result |
|---|---:|
| TP | 0 |
| FP | 0 |
| FN | 48 |
| Precision | N/A (no positive predictions) |
| Recall | 0 / 48 = **0.00%** |
| Economic-value capture | $0 / $423,619.72 = **0.00%** |
| Mechanical/fabricated FP | **0** |

Exact FN classification:

- **26 FieldMaintenance FN — `CAPABILITY_MODEL_GAP` (primary).** The frozen
  sources provide governed contract rate, subject linkage, billable scope,
  and invoice amount. Prior independent Revenue Amount certification
  mechanically reproduced 24 finding rows covering 24 of the 26 authored items to
  the cent. The dedicated capability nevertheless accepts only an explicit
  `actual_applied_rate`; it does not implement the architecture program’s
  governed attributable amount/quantity derivation path. Missing source
  currency is a secondary `SEMANTIC_EVIDENCE_GAP`.
- **22 Rental FN — `SEMANTIC_EVIDENCE_GAP` / `DATA_CONTRACT_GAP`.** The
  frozen customer data lacks explicit actual-rate evidence and also lacks
  governed rate basis/UOM and currency. Correct abstention avoids fabricated
  findings, but produces no truth-family recall.

Finding overlap with Revenue Amount Variance is **0 current dedicated
findings**. Economically, the previously certified 24 FieldMaintenance
Revenue Amount findings cover 24 of the 26 authored rate-mismatch items, but
they were not relabeled and do not count as Contract/Rate TP.

### Regression control

The exact Revenue Amount / Billing Variance control is preserved:

- FIELDMAINT-001 = 61
- FIELDMAINT-002 = 0
- FIELDMAINT-005 = 86
- FIELDMAINT-007 = 26
- TP = 150, FN = 16, recall = 90.36%
- mechanical/fabricated FP = 0

The additional persisted totals (63/1/87/27) are the same pre-existing
cross-domain findings documented by P3.xxI.4 and are not regressions.

### Final classification

The implementation preserves safety and existing behavior, but it does not
activate on any frozen Wave 1 case and achieves 0% recall against its exact
48-item truth family. The preferred graduation threshold is therefore not
met, and multiple required live controls remain unexercised.

**P3.xxI.5A FAILED**
