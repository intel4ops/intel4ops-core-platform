# P3.xxI.5A Contract / Rate Compliance

## Status

**Implementation:** merged in PR #121; merge commit
`cf25345411bbb11305503e45e0d290a7625ecbba`

**Live hidden-truth certification:** complete

**P3.xxI.5A FAILED**

**P3.xxI.5A-R remediation implementation:** complete on branch
`feature/p3xxi5ar-derived-actual-rate`; local quality gates pass. See the
`P3.xxI.5A-R REMEDIATION IMPLEMENTATION` section at the end of this document.
Merge and post-merge live certification remain owner-gated.

## P3.xxI.5A FAILURE RECONCILIATION

This reconciliation is diagnosis only. It does not change the frozen truth,
semantic thresholds, application code, or the certified `0 / 0 / 48` result.
It answers why the dedicated capability found nothing even though Revenue
Amount Variance had previously surfaced 24 genuine FieldMaintenance
`contract_rate_mismatch` items.

### Exact FN distribution

| Slice | FN | Authored exposure | Mechanically rate-derivable from customer data | Still unsupported |
|---|---:|---:|---:|---:|
| FieldMaintenance, single-cause rate mismatch | 24 | $7,022.26 | 24 | 0 |
| FieldMaintenance, rate mismatch plus unbilled labor | 2 | $350.06 | 0 | 2 |
| Rental | 22 | $416,247.40 | 0 under the governed evidence contract | 22 |
| **Total** | **48** | **$423,619.72** | **24** | **24** |

The exact 24 directly derivable FieldMaintenance truth IDs are `LK-1`,
`LK-2`, `LK-5`, `LK-6`, `LK-8`, `LK-10`, `LK-16`, `LK-18`, `LK-20`,
`LK-22`, `LK-25`, `LK-26`, `LK-28`, `LK-30`, `LK-31`, `LK-32`,
`LK-34`, `LK-36`, `LK-37`, `LK-39`, `LK-40`, `LK-42`, `LK-45`, and
`LK-52`.

The two unsupported FieldMaintenance truth items are:

- `LK-14`, WO-000043, $206.35: 8 logged labor hours include 3 unbilled
  hours. Hidden truth uses 5 billed hours and an invoiced rate of $98.73/hr.
  Dividing the invoice labor residual by all 8 source hours instead produces
  $61.71/hr.
- `LK-49`, WO-000171, $143.71: 11 logged labor hours include 4 unbilled
  hours. Hidden truth uses 7 billed hours and an invoiced rate of $74.47/hr.
  Dividing the invoice labor residual by all 11 source hours instead produces
  $47.39/hr.

The customer files do not identify billed versus unbilled labor quantity.
Using the hidden billed-hour counts would leak examiner truth into production.
The two records must therefore abstain until governed billed-quantity or
invoice-line allocation evidence exists.

This also corrects an imprecise value statement in the earlier breadth
summary: $7,372.32 is the value of all 26 FieldMaintenance rate-mismatch
truths. The 24 individually reproducible items total $7,022.26; the two
mixed-cause items total $350.06.

### Evidence path used by the prior 24 findings

The earlier detections were **total Revenue Amount comparisons**, not actual
rate detections. Their governed path was:

1. Link `invoices.work_order_id` to one work order and
   `invoices.contract_id` to one service contract.
2. Sum `labor_entries.hours` for the work order.
3. Resolve the applicable `service_contracts.labor_rate` through the exact
   contract link and effective window; `labor_rate` supplies the governed
   hourly rate basis.
4. Compute governed labor value as `hours * labor_rate`.
5. Add every same-work-order `parts_usage.quantity * parts_usage.unit_price`.
6. Compare that expected work-order total with `invoices.amount`.

For WO-000011, the calculation was `(10 hr * $95/hr) + $211 parts =
$1,161.00 expected`; invoice INV-000011 was $867.10; the $293.90 amount
variance exactly matched `LK-1`. The Revenue capability did not calculate or
publish the hidden $65.61/hr invoiced rate.

For the 24 single-cause rows, the same evidence can be rearranged into a
genuinely rate-level observation without relabeling the Revenue finding:

`derived actual labor rate = (invoice amount - governed parts amount) /
governed labor hours`

Across those 24 rows, this derived rate matches hidden truth's
`invoiced_rate` to the cent, and
`abs(derived actual rate - applicable contract rate) * labor hours` matches
the authored rate-mismatch exposure. The dedicated finding would still have
its own rule, identity, rate comparison, and lineage.

### Actual-rate evidence availability

- **Explicit actual rate:** 0 of 48 truth items. No frozen Wave 1 source has
  an `actual_applied_rate`, `invoice_unit_rate`, `charged_rate`, or equivalent
  field.
- **FieldMaintenance derived actual rate:** mechanically available for 24 of
  26 items through the residual calculation above. The other 2 lack an
  attributable billed labor denominator.
- **Rental arithmetic rate:** all 22 hidden billed rates equal
  `invoices.amount / elapsed contract days` to the cent. This arithmetic is
  not governed rate evidence because the source never says the bare contract
  `rate` is per day and never declares currency.

The implementation requires an explicit `actual_applied_rate` canonical field
on the same governed subject-attributable dataset. Its readiness contract and
service do not admit a derived amount/quantity alternative. That requirement
is narrower than the approved architecture contract, which explicitly
allowed derivation from attributable billed amount and governed positive
quantity.

### Contract/reference-rate evidence availability

- **FieldMaintenance:** `service_contracts.labor_rate` is present for all 26
  items, uniquely linked by `invoices.contract_id`, bounded by contract dates,
  and canonically carries an hourly denominator. The source does not declare
  currency.
- **Rental:** `contracts.rate` is numerically present for all 22 items and the
  invoice has a unique `contract_id`. The field resolves as generic
  `unit_price`; no source column declares day/hour/week basis, UOM, or
  currency. Contract start/end dates govern elapsed duration but do not prove
  the denominator of `rate`.

### Safe derivation boundary

A reusable actual-rate derivation is safe only when all of these gates pass:

- one governed subject and one billing record;
- one applicable contract/rate row at the transaction or service timestamp;
- a positive governed billable quantity with an explicit or inherently
  governed UOM;
- billed amount uniquely attributable to the same charge scope;
- every subtracted non-rate component is governed, complete, and linked to
  that same scope;
- compatible, positively governed currency on amount and reference rate;
- no competing allocation, aggregation, or billed-quantity interpretation.

Missing billing evidence remains distinct from a billed amount of zero. A
zero residual or zero rate may participate only when the underlying amount,
scope, and quantity are positively evidenced. Failure of any gate must emit a
specific abstention reason, never an inferred rate.

This derivation remains distinct from Revenue Amount Variance. Revenue asks
whether the total expected amount differs from the billed total. Contract/Rate
Compliance asks whether a derived per-unit charged rate differs from one
applicable reference rate. The two may describe the same economic loss, but
their calculations, finding identities, explanations, and portfolio impact
deduplication remain separate.

### Unsupported cases and predicted ceiling

After adding only the derived-actual-rate model path:

- **24 of 48** truths, representing **$7,022.26**, become mechanically
  rate-derivable before the currency publication gate.
- **2 FieldMaintenance** truths remain blocked by ambiguous billed quantity
  and charge allocation.
- **22 Rental** truths remain blocked by missing governed contract rate basis,
  UOM, and currency, even though examiner-side arithmetic reproduces their
  hidden rates.

The unchanged frozen files declare no currency for either FieldMaintenance or
Rental. Therefore the strictly publishable denominator remains **0 of 48** if
the existing positive currency requirement is preserved and no separate
governed case/tenant currency evidence exists. With governed compatible
currency supplied outside hidden truth, the predicted publishable ceiling is
**24 of 48 ($7,022.26)**. Recovering the remaining 24 requires source/data-
contract evidence, not a broader inference in the capability.

### Capability-model gap and smallest reusable remediation

The dedicated capability's mechanical contract is too narrow: it implements
only the explicit-rate branch of the approved evidence contract. The smallest
reusable change is to add one alternative, provenance-complete
`derived_actual_applied_rate` input to Contract/Rate Compliance:

`(attributable billed amount - governed non-rate components) /
positive governed rate quantity`

The alternative should reuse the existing canonical subject/linkage,
applicable-rate, temporal, UOM, currency, and evidence-completeness services.
Readiness should become `explicit actual rate OR safe derived actual rate`;
the comparison service should consume either through one common applied-rate
evidence object. It must not broaden aliases, lower semantic thresholds,
assume a currency or rate basis, infer billed quantity from truth, or call and
relabel a Revenue Amount finding.

Required abstention codes should distinguish at least missing currency,
missing rate basis, non-positive quantity, ambiguous billed quantity,
non-attributable invoice amount, incomplete residual components, ambiguous
subject/invoice linkage, multiple applicable rates, and temporal mismatch.

### False-positive risks

The remediation must explicitly guard against:

- dividing an invoice header by a quantity for only one of several charge
  lines;
- subtracting incomplete parts or fee components and mislabeling the residual
  as labor;
- using total logged quantity when some quantity was unbilled, as in `LK-14`
  and `LK-49`;
- treating a bare Rental `rate` as daily solely because contract dates exist;
- accepting two missing currencies as proof of compatibility;
- selecting a stale or multiply applicable contract rate;
- double-counting economic impact across Revenue Amount and Contract/Rate
  findings.

### Decision gate

**A. P3.xxI.5A-R — REMEDIATE CONTRACT/RATE COMPLIANCE**

The remediation is justified because 24 frozen truths expose a reusable,
mechanically valid derived-rate path that the approved architecture allowed
but the implementation omitted. Graduation must remain conditional on
governed currency evidence; the remediation must preserve abstention for the
two mixed-scope FieldMaintenance items and all 22 rate-basis-deficient Rental
items.

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

## P3.xxI.5A-R REMEDIATION IMPLEMENTATION

### Baseline and handoff

Authoritative pre-remediation `main`: `5ac6b20bfcbcbe0b7537371fd371c138491b78fb`
(PR #122, the certification above). Codex implemented the bulk of this
remediation directly against that baseline on
`feature/p3xxi5ar-derived-actual-rate` before hitting its usage limit, leaving
three modified files uncommitted: `app/services/contract_rate_compliance_service.py`
(+558/-1 at handoff), `app/services/analysis_case_orchestration_service.py`
(+17/-13), `app/intelligence_packs/registry.py` (+17/-14), plus the failure-
reconciliation addendum already recorded above. Claude reconciled the handoff
per the mission's own required first step (`git fetch --all --prune`;
inspected branch, HEAD, `origin/main`, full diff, and untracked files; no
reset, no discard) before writing or changing any further code.

### Codex's implementation reviewed against the approved design

All of Codex's own code was read line-by-line before any further change.
Findings:

- **Correctly implements the approved design.** `derive_actual_applied_rates`
  (new, in `contract_rate_compliance_service.py`) computes exactly
  `(attributable billed amount - governed non-target components) / positive
  governed target quantity`, gated by: single billing line per subject
  (`len(billing_lines) != 1` aborts), at most one non-target component
  *dataset* (`len(component_groups) > 1` aborts), a single agreeing quantity
  total and unit across every quantity-bearing dataset for that subject
  (disagreement aborts), a positive quantity, one consistent currency across
  billing and every component line (`None` or disagreement aborts), governed
  subject-contract linkage (reused `_subject_contract_map`, ambiguity-safe,
  identical shape to Revenue Amount Variance's own), and per-row
  `canonical_evidence_completeness` gating before any line is even collected.
  `is_rate_card_shaped` datasets are excluded from derivation inputs entirely
  at the top of the function -- a rate-card row can never become a billing,
  quantity, or component line (Section 15's required separation, preserving
  P3.xxI.3's own latent-bug fix).
- **Readiness was not broadened unsafely.** The new
  `alternative_canonical_measure_sets` entries in `registry.py`
  (`invoice_amount`+`quantity`/`duration_hours`+`unit_price`/`hourly_rate`)
  are purely structural (do the concepts exist anywhere in the case), exactly
  mirroring the established P3.xxI.2C/P3.xxI.3 precedent where readiness is
  intentionally broader than execution; every actual safety gate lives in
  `run_contract_rate_compliance`/`derive_actual_applied_rates`, not in
  readiness.
- **Generic, no leaked domain logic.** Grepped the full diff for
  FieldMaintenance/Rental filenames, customer names, or truth-item
  identifiers (`LK-`) -- none found. Every field reference is a
  canonical-concept field name supplied by the orchestration layer.
- **No hidden-truth dependency.** No import of, or reference to, any
  ground-truth module or truth-item identifier anywhere in the service file.
- **The mechanical size is justified, not gratuitous.** The derivation
  requires per-subject aggregation across up to three dataset roles
  (billing/quantity/component), ambiguity detection across multiple
  candidate quantity datasets, and full evidentiary lineage construction
  (mission Section 11) -- comparable in shape and necessity to
  `revenue_variance_intelligence_service.py`'s own `_collect_lines`. Left
  unmodified except one `mypy` fix (below); not rewritten for style.

Two incomplete/broken pieces were found and are the only additions made
beyond finishing tests and the report:

1. **`mypy` error** (pre-existing in Codex's own diff, never reported since no
   quality gate had run against the combined tree yet): `sum(line.value for
   line in lines)` at the quantity-aggregation step inferred
   `Decimal | Literal[0]` because an empty-iterable-safe `sum()` defaults to
   `int` `0`. Fixed with an explicit `Decimal("0")` start value. No behavior
   change.
2. **Missing rule-definition version.** `_publish_derived_rate_comparison`
   publishes with `definition_version="1.1"`, but `app/registries/rule_registry.py`
   only registered `CONTRACT-RATE-COMPLIANCE` version `"1.0"` -- every derived-
   rate publish attempt failed with `DEFINITION_REFERENCE_INVALID` /
   `Registered definition not found`. Added a `"1.1"` `RuleDefinition` entry
   (additive; `"1.0"` is untouched and remains the explicit-rate path's own
   definition).

### Two orchestration wiring gaps found and fixed during testing

Writing the required positive tests (Section 14 of the mission) surfaced two
further gaps that made the derived path structurally unreachable even when
every dataset-level concept resolved correctly. Both are fixed in
`app/services/analysis_case_orchestration_service.py`, inside the same
`CONTRACT-RATE-COMPLIANCE` per-dataset loop Codex added:

1. **`allow_bridge` was tied to the wrong condition.** The subject-field
   resolver was called with `allow_bridge=actual_rate_field is not None` --
   correct for the original explicit-only capability (only actual-rate rows
   needed subject resolution at all), but it silently excludes every target-
   quantity or non-target-component dataset that carries no *directly*
   AUTO_ACCEPTED subject identifier of its own (the same governed-bridge
   shape Revenue Amount Variance's own `labor_entries.csv`/`parts_usage.csv`
   already rely on). Fixed to `allow_bridge=not is_contract_rate_shaped`,
   the exact established Revenue Amount Variance pattern
   (`allow_bridge=not is_rate_card_shaped`) applied to this capability's own
   rate-card-shaped flag. Confirmed via a real, unmodified `execute()` run
   with an instrumented trace: before the fix, the quantity/component
   datasets never appeared in `applied_rate_datasets` at all; after, they
   resolve correctly (directly or via the governed one-hop bridge) exactly
   as the design intended.
2. **Evidence-completeness used the wrong concept key when quantity fell back
   to `duration_hours`.** When a dataset's quantity comes from the
   `duration_hours` concept (e.g. an "hours" column) rather than a bare
   `quantity` concept, `rate_required_concepts` still recorded the
   requirement under the literal key `"quantity"`. The evidence-completeness
   lookup matches on each semantic decision's own `selected_concept`, which
   for an "hours" column is `"duration_hours"`, never `"quantity"` -- so the
   completeness check permanently reported the quantity requirement as
   unsatisfied even though it had, in fact, resolved with real governed
   evidence, and every subject on that dataset was silently added to
   `invalid_subjects`. Fixed by keying the requirement dict entry on whichever
   concept actually supplied the field (`"duration_hours"` when the fallback
   was used, `"quantity"` otherwise) -- mirroring P3.xxI.3's own
   `optional_resolved_concepts` pattern of only recording the concept that
   was actually used.

**This second fix is materially important for live certification**: the
real, frozen FieldMaintenance corpus's own `labor_entries.csv` carries an
`hours` column (which resolves as `duration_hours`, confirmed by direct
inspection of the frozen file), the exact same shape that exposed this bug
in testing. Without this fix, the derived-rate path would have silently
abstained on every one of the 24 target FieldMaintenance truth items in live
certification even with every other piece of the implementation correct.

Both fixes were found and confirmed exclusively through direct testing
(Section 17 of the mission: "test before continuing") against a real,
unmodified `execute()` run -- neither was hypothesized in advance.

### Derived-rate contract (as implemented)

```
derived_actual_applied_rate = (attributable_billed_amount - governed_non_target_components) / governed_target_quantity
```

Implemented in `contract_rate_compliance_service.py`'s
`derive_actual_applied_rates` / `DerivedAppliedRateEvidence`. Every gate named
in the mission's Section 7 is enforced before a candidate is even
constructed: unique subject/billing/quantity/component attribution, positive
quantity with a resolved UOM (explicit `unit_of_measure` field or the
dataset's own governed `implicit_quantity_unit`), one agreeing currency
across billing and every component line, and governed subject/contract
linkage. `run_contract_rate_compliance` then re-validates the *contract* side
independently through the unmodified, pre-existing
`resolve_applicable_rate` (P3.xxI.4) -- requiring its own governed
`currency`, `unit`, and `rate_basis` before any comparison is attempted. A
subject with a valid **explicit** `actual_applied_rate` is authoritative and
is recorded in `explicit_subjects`; the derived path is never attempted for
that subject, so no subject can ever receive two competing
`CONTRACT-RATE-COMPLIANCE` findings from the two evidence paths.

### Ambiguity rules

Unchanged from the approved design and confirmed by test: a bare `rate` /
`unit_price` concept never acquires an implicit UOM (P3.xxI.4's own rule,
reused unmodified); multiple quantity-bearing datasets that disagree on
total or unit abstain entirely, never silently prefer one; two billing lines
for the same subject abstain (no unique attribution); an incomplete
component row (missing price with quantity present, or vice versa) abstains
the whole subject rather than treating the missing side as zero. Missing
evidence is never converted to zero anywhere in the derivation.

### Currency and UOM gates

Currency: every input line (billing and every component line) must
independently resolve a 3-letter currency code, and all resolved currencies
for one subject must be identical; the contract side must independently
resolve its own governed currency through `resolve_applicable_rate`. Neither
side ever assumes USD or any other default. UOM: the target quantity's unit
comes only from an explicit `unit_of_measure` field or the dataset's own
governed `implicit_quantity_unit` (never guessed); the contract rate's unit
comes only through P3.xxI.4's own two governed sources (explicit column or
the `hourly_rate` concept's name). The two must match exactly
(`resolve_applicable_rate`'s pre-existing strict equality) or the subject
abstains.

### Lineage

`DerivedAppliedRateEvidence.evidence` carries one `EvidenceItemCreate` per
billing line, per quantity line (one per contributing dataset), per
component line, plus explicit `derived_rate_target_amount` and
`derived_actual_applied_rate` calculation-trace items showing the exact
arithmetic (`billed - components = target`, `target / quantity = rate`).
`_publish_derived_rate_comparison` appends the applicable-contract-rate line,
the rate-comparison line, and the exposure calculation, and records every
contributing dataset id. The full chain -- invoice amount, non-target
component(s), derived target amount, target quantity, derived actual rate,
contract rate, rate basis/UOM, currency, effective window, and subject/
contract relationship -- is reconstructable from the persisted evidence
alone, satisfying Section 11 of the mission.

### Reachable denominator (mechanical, pre-certification)

Unchanged from the failure reconciliation above: **24 of 48** truth items
($7,022.26) are mechanically rate-derivable from governed customer data
using this contract; 2 FieldMaintenance items (`LK-14`/`LK-49` internally,
never referenced by name or ID anywhere in production code) remain
unreachable because the source data does not distinguish billed from
unbilled labor quantity; 22 Rental items remain unreachable because
`contracts.csv` declares no rate basis, UOM, or currency (P3.xxI.4's own
confirmed `DATA_CONTRACT_GAP`). This remediation does not attempt to close
either unreachable category -- doing so would require either new source
evidence or an explicit, separately-scoped, owner-authorized business rule,
neither of which is implemented here.

### Tests

Added to `tests/test_contract_rate_compliance.py` (all new tests below;
the pre-existing 16 explicit-actual-rate tests are unchanged and still pass):

| # | Test | Mission requirement |
|---|---|---|
| Positive A | `test_derived_a_worked_example_produces_finding` | Section 14A -- exact worked example (1200-200=1000/10=100/hr vs 90/hr contract -> exposure 100) |
| Positive B | `test_derived_b_actual_equals_contract_no_finding` | Section 14B |
| Positive C | `test_derived_c_multiple_subjects_have_distinct_findings` | Section 14C |
| Positive D | `test_derived_d_generic_non_fieldmaintenance_orchestration_end_to_end` | Section 14D -- full, unmodified `execute()`, no FieldMaintenance-shaped column names |
| Negative A | `test_derived_negative_a_missing_quantity_abstains` | Section 15A |
| Negative B | `test_derived_negative_b_zero_quantity_abstains` | Section 15B |
| Negative C | `test_derived_negative_c_conflicting_quantity_abstains` | Section 15C |
| Negative D | `test_derived_negative_d_incomplete_component_row_abstains` | Section 15D |
| Negative E | `test_derived_negative_e_missing_currency_no_publication` | Section 15E |
| Negative F | `test_derived_negative_f_incompatible_uom_abstains` | Section 15F |
| Negative G | `test_derived_negative_g_ambiguous_invoice_attribution_abstains` | Section 15G |
| Negative H | `test_derived_negative_h_rate_card_dataset_never_becomes_actual_rate_input` | Section 15H |
| Negative I | `test_derived_negative_i_bare_rental_rate_without_uom_abstains` | Section 15I |
| Negative J | `test_derived_negative_j_generic_quantity_ambiguity_abstains_without_identifiers` | Section 15J -- same underlying gate as C, proven again on a distinct, non-identifying fixture |

Plus two additional regression-safety tests not explicitly enumerated but
required by the design: `test_derived_path_never_double_publishes_when_explicit_rate_also_present`
(a subject with both valid explicit and derivable evidence produces exactly
one finding, from the explicit path) and
`test_derive_actual_applied_rates_returns_empty_for_no_datasets`.

### Regression

| Suite | Result |
|---|---:|
| `tests/test_contract_rate_compliance.py` | 32 passed |
| Focused sweep (rate/uom/duration/revenue/semantic/readiness/relationship/trust/lineage/validation_isolation/tenant/contract) | 661 passed |
| Full non-PostgreSQL suite | 1730 passed |
| Disposable PostgreSQL migration/tenant-boundary suite (fresh schema reset) | 83 passed |
| `ruff format --check .` | all files formatted |
| `ruff check .` | all checks passed |
| `mypy .` | 619 source files, no issues |

Revenue Amount / Billing Variance control, P3.xxI.2C subject generalization,
P3.xxI.3 duration evidence, and P3.xxI.4 rate-basis/UOM evidence test suites
all re-run and pass unchanged as part of the focused sweep and full suite
above -- zero regression.

### Implementation PR

Opened after this report section was committed; see commit history / PR
list for the exact number, head SHA, and CI status. Not merged -- awaiting
explicit owner authorization naming that PR, per standing house rule and
Section 22 of the mission.

### Post-merge live certification (not yet performed)

Per the mission's explicit instruction (Section 23), live hidden-truth
certification is **not** run before an owner-authorized merge and
deployment. When it runs, it will report, against the frozen Wave 1 corpus:

- reachable-denominator recall = TP / 24
- full-family recall = TP / 48
- TP / FP / FN, precision, economic-value capture
- mechanical/fabricated FP count (target: 0)

both denominators reported side by side, per Section 23's own requirement,
never collapsing the full-family denominator into the reachable one.
