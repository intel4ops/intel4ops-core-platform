# P3.xxI.2 — Revenue Amount / Billing Variance Capability Report

## A. Baseline

- Repository: `intel4ops/intel4ops-core-platform`
- Starting `main`: `f05523174142c044646a64564849a9d40ddc6d4d` (P3.xxI.1 merged, PR #107)
- Reconciliation confirmed: `HEAD == origin/main`, clean worktree, no open PRs,
  no competing P3.xxI.2 branch, before any edit.
- Existing capability (`docs/p3xxi1-intelligence-capability-coverage-architecture.md`)
  recommendation reused as-is: Revenue Amount / Billing Variance, the largest
  reusable mechanism in the PARTIALLY_IMPLEMENTED scope (166/263 items).

## B. Pre-implementation reconciliation

Traced directly against `app/semantic/concept_registry.py` before writing any
rule code.

| Concept | Registered? | Aliases (pre-existing) | Dataset-role scope (pre-existing) | Wave 1 availability |
|---|---|---|---|---|
| `quantity` | Yes | `quantity`, `qty`, `count`, `units` | `inventory`, `measurement` only | present (`parts_usage.csv.quantity`), but role-incompatible on a work-order-linked consumption dataset and with no `expected_value_patterns` declared -- capped at `accepted_with_flag` (0.85), never `auto_accepted` |
| `unit_price` | Yes | `unit_price`, `price`, `rate`, `amount` | `invoice`, `inventory` only | present, same role-incompatibility issue; `amount` alias also shared with `invoice_amount`/`cost_amount` (documented, intentional ambiguity) |
| `invoice_amount` | Yes | `invoice_amount`, `total_amount`, `amount_due`, `bill_amount`, `amount` | `invoice`, `ledger` | present in principle, but the shared `amount` alias means a raw "amount" column can resolve to `unit_price` instead, depending on what else co-occurs in the case |
| `cost_amount` | Yes | `cost_amount`, `cost`, `expense_amount`, `amount` | `invoice`, `ledger`, `work_order` | not exercised by live Wave 1 evidence this pass |
| `currency_code` | Yes | `currency`, `currency_code`, `ccy` | none declared | **absent from Wave 1 entirely** -- confirmed in `p3xxv1b` Section N/J: no currency field in either family's truth or customer-data schema |
| rate/price/revenue/billing-quantity/contract-quantity/unit-of-measure | No dedicated concepts | -- | -- | no governed UOM concept exists at all; Section E explains why none was added |

No dedicated "rate" or "unit-of-measure" concept exists in this registry
today, and none was added -- Section E explains the deliberate, narrower
unit-safety design used instead.

**Cross-dataset semantic authority behavior discovered (not assumed):**
`unit_price`/`invoice_amount`/`cost_amount` sharing the raw alias `"amount"`
means the SAME raw column, on the SAME dataset, can score identically across
all three candidates unless one gets an extra `CROSS_DATASET_OVERLAP`
corroboration bonus from another dataset in the case independently resolving
to that same concept. This is pre-existing, deliberate, documented ambiguity
(`app/semantic/concept_registry.py`'s own P3.xxE.2 comment) -- not something
this milestone weakens or "fixes." Section C/D explain how the capability's
own execution logic, not the shared semantic registry, absorbs this
ambiguity.

## C. Capability contract

- **Capability/rule code:** `REVENUE-AMOUNT-VARIANCE`, pack `REV-VAR`, version `1.0`.
- **Business question:** for a work order (or equivalent billable unit), is
  the actual invoiced amount materially below the expected amount computed
  from governed consumption/rate or reference-cost evidence?
- **Required canonical evidence:** a `WORK_ORDER`-typed canonical entity
  (E.3) clearing `minimum_entity_identity_confidence=0.70`; `quantity` and
  `unit_price` concepts present somewhere in the case (readiness-level
  presence gate).
- **Optional canonical evidence:** `invoice_amount`, `cost_amount`,
  `currency_code`.
- **Required domains:** none. Deliberately not domain-coupled -- Section D.
- **Entity scope:** work order (narrowest stable business subject; never
  defaults to asset).
- **Time scope:** none -- a pure amount comparison, no window/interval logic.
- **Readiness contract:** governed, participates in the same
  `build_case_capability_index`/`evaluate_readiness`/`compare_shadow`
  machinery XDOM-A/XDOM-B already use (`migrated_rule_codes`,
  `_GOVERNED_RULE_CODES` both additively extended by one entry each).
  `confidence_aggregation_policy="max"` (mirrors XDOM-A's own
  PER_ENTITY/candidate-local justification exactly). `currency_behavior=
  "currency_agnostic"` (currency safety is judged per work order inside the
  rule, a finer grain than the case-level gate could provide).
  `unit_behavior="unit_aware"`.
- **Candidate construction:** for each dataset carrying a resolved
  `work_order_id` concept, resolve `quantity`/`unit_price`/`invoice_amount`/
  `cost_amount`/`currency_code` fields independently; group rows by work
  order key, restricted to the E.3-eligible work-order population.
- **Calculation contract (forms supported):**
  - **Form A (primary, live-evidenced):** same-row `quantity x unit_price`
    -- inherently unit-safe by construction (never a cross-record rate
    assumption).
  - **Form B (contract-supported, not live-evidenced in Wave 1):** a direct
    reference amount (`cost_amount`) on the same row as `work_order_id`
    (e.g. an approved/agreed job amount).
  - **Actual amount:** `invoice_amount` on a row sharing `work_order_id`;
    when `invoice_amount` doesn't resolve on a given dataset (the
    `amount`-alias ambiguity in Section B) but `unit_price` does, on a
    dataset carrying no co-located `quantity`, that value is read as a flat
    billed amount instead of a rate -- the only interpretation left once "a
    rate multiplying some quantity" is structurally ruled out (Section E).
  - Multiple rows on either side are summed (Section 12 -- multi-line
    billing/progressive invoicing/multiple consumption records all
    aggregate correctly by construction).
- **Finding condition:** `expected_amount > 0` and
  `expected_amount - actual_amount` exceeds the governed materiality
  tolerance (Section F).
- **Evidence requirements:** `StableFindingIdentityReference(subject,
  "work_order", <key>)`; per-line `CALCULATION_TRACE` evidence for every
  contributing expected/actual row (dataset, row reference, basis, amount,
  currency); descriptive `summary` stating the expected/actual amounts,
  contributing record counts, and computed variance.
- **Uncertainty behavior:** BLOCKED/READY at the case level (binary, like
  XDOM-A/B); per-work-order silent skip (no finding, not a failure) for
  currency mismatch, internally inconsistent currency, incompatible units,
  ineligible linkage, or sub-tolerance variance (Section H).
- **Economic-value representation:** `exposure_value`/`exposure_value_type`/
  `exposure_currency` (Section D) -- `economic_status="governed_pending"`,
  never "recovered."
- **False-positive controls:** Section F/H/17.

## D. Architecture decisions

1. **Additive sibling, never a XDOM-B modification.** New files
   (`app/services/canonical_revenue_variance_evidence.py`,
   `app/services/revenue_variance_intelligence_service.py`); XDOM-A/XDOM-B/
   MAINT-001 source files are byte-for-byte untouched (confirmed by `git
   diff` scope in Section H).
2. **`exposure_value`/`exposure_value_type`/`exposure_currency` are newly
   threaded, not newly invented.** `IntelligenceExecution` and `Finding`
   already had these columns; `CandidateFindingCreate` already validated
   this exact triad (currency required iff type is CURRENCY). Every prior
   P3.xxC.1 rule simply never populated them. `GovernedFindingRequest`
   gained these as optional fields (default `None`), preserving every
   existing caller's behavior exactly.
3. **`supporting_evidence` is a new optional field on
   `GovernedFindingRequest`**, appended into the publisher's own evidence
   list after identity evidence -- additive, empty by default.
4. **Entity-scoped readiness, not domain-scoped.** Fix #8's own
   certification showed a work-order-linked consumption dataset (parts/
   labor usage) can resolve to `maintenance`, `operations`, or no domain at
   all depending on which columns happen to co-occur. Coupling this
   capability's readiness to a specific domain would inherit that same
   fragility. Readiness instead reads `required_canonical_entities={WORK_ORDER}`
   + `required_canonical_measures={quantity, unit_price}`, both
   domain-classification-independent.
5. **Small, additive `concept_registry.py` extensions** (mirroring the
   Fix #4/#5/#6 precedent of extending an *existing* concept's
   aliases/roles, never inventing a new subsystem):
   - `quantity`: added aliases `hours`/`hrs`; added `work_order`/`labor`
     dataset-role compatibility; added `expected_value_patterns=
     {digits, decimal}` (a counted/measured quantity is always numeric --
     every other registered concept already declared its own expected
     value shape; `quantity` previously declared none).
   - `unit_price`: added alias `labor_rate` (a specific, observed column
     name); added `work_order`/`labor`/`contract` role compatibility.
   - `work_order_id`: added `inventory` role compatibility (a parts/
     materials consumption record linked to a work order is generically
     inventory-shaped by `role_classifier.py`'s own scoring).
   These three extensions were each independently required and verified via
   live semantic-decision inspection (Section H) -- not applied
   speculatively.
6. **P3.xxV.2D's canonical-evidence-completeness correction path is reused,
   per-dataset, not invented anew.** Trust's early
   `RawFieldCompletenessRule` blocks parts_usage.csv/invoices.csv on this
   corpus (they carry none of `maintenance`'s literal required raw fields --
   confirmed live, Section H) exactly the way it originally blocked
   XDOM-A/B before Fix #3. `analysis_case_orchestration_service.py` computes
   a `CanonicalEvidenceCompletenessResult` per dataset (using THIS
   capability's own concept set, not a domain's), threaded through
   `DatasetConceptFields`, and the finding this capability publishes for a
   given work order uses the primary contributing dataset's own
   completeness result -- the same corrected-readiness mechanism XDOM-A/B
   already use, applied per-dataset since this capability spans several.

## E. Currency / unit governance

**Currency (Section 6):** `app/services/canonical_revenue_variance_evidence.py`
defines `CurrencyComparability` with four named states: `same_known`,
`different_known`, `unknown_both`, `mixed_known_unknown`. Only `same_known`
and `unknown_both` ever produce a finding; `different_known` and
`mixed_known_unknown` are always skipped -- no FX rate is ever invented, no
currency is ever assumed. A special case: when a work order has expected-side
evidence but zero actual/invoice rows at all, the actual side's "currency" is
vacuously compatible with any known expected currency (summing zero elements
of any currency is the additive identity, never a real conflict) -- this is
distinct from a genuinely *observed but unconfirmed* currency, which stays
blocked. Wave 1 has **no currency field anywhere** (Section B), so every live
finding this milestone can produce falls into `unknown_both` --
`exposure_value_type=DECIMAL` (never `CURRENCY`) with `exposure_currency=None`,
and an explicit limitation stating the amount is a same-unit magnitude only,
never assumed USD.

**Units (Section 7):** no governed unit-of-measure concept was added. Instead,
Form A's `quantity x unit_price` multiplication is restricted to same-row,
same-dataset pairs only -- the rate is, by construction, "price per this
row's own unit," so no cross-record unit assumption (hours vs. daily rate,
feet vs. meters) is structurally possible. A bare quantity with no co-located
rate on the same dataset (test I) produces no expected-amount line at all,
never a guessed unit. This is deliberately narrower than a full UOM ontology
would allow, exactly per Section 24's stop-gate guidance against inventing a
new ontology this milestone.

## F. Materiality

No reusable materiality/tolerance framework existed to extend (Trust's
`numeric_range_validity`/`maximum_affected_percentage` config shape was the
closest analog, reused as inspiration only). Implemented the smallest generic
deterministic policy: `tolerance = max(absolute=1.00, expected_amount x
relative=0.02)` -- "greater of an absolute floor or 2%," a standard,
industry-generic financial-reconciliation pattern, not tuned to any
simulation's specific numbers. Both constants are named module-level
constants (`DEFAULT_ABSOLUTE_TOLERANCE`, `DEFAULT_RELATIVE_TOLERANCE`) for a
future governed-config migration to read from.

## G. Implementation

New files:
- `app/services/canonical_revenue_variance_evidence.py` -- framework-free
  concept-field resolution (mirrors `canonical_temporal_evidence.py`'s exact
  shape, deliberately NOT shared code with it) + `CurrencyComparability`.
- `app/services/revenue_variance_intelligence_service.py` --
  `run_revenue_amount_variance`, `DatasetConceptFields`, materiality
  constants.

Modified files (all additive):
- `app/semantic/concept_registry.py` -- Section D.5 extensions.
- `app/services/governed_finding_publisher.py` -- `exposure_value`/
  `exposure_value_type`/`exposure_currency`/`supporting_evidence` on
  `GovernedFindingRequest`, threaded into `IntelligenceExecution` and
  `CandidateFindingCreate`; docstring updated for accuracy.
- `app/intelligence_packs/registry.py` -- new `IntelligencePackDefinition`.
- `app/registries/rule_registry.py` -- new `RuleDefinition` (required by
  `FindingPublicationService._definition_operation`; discovered during
  testing, not assumed).
- `app/services/analysis_case_orchestration_service.py` -- new static
  `_resolve_canonical_concept_field` (generalizes
  `_resolve_canonical_temporal_field`'s shape to any concept, deliberately a
  separate method so XDOM-A's own dependency is never touched); new
  execution block after XDOM-B's, spanning all `case_datasets` (never
  domain-grouped); `migrated_rule_codes`/`_GOVERNED_RULE_CODES` each gained
  one additive entry.

`git diff main --stat` confirms: 5 modified application-code files (all
additive changes, verified above), 3 new files, one modified pre-existing
test file (`tests/test_capability_shadow_stage.py`, Section H's allowlist
fix), zero lines touched in `cross_domain_intelligence_service.py`,
`analysis_case_intelligence_service.py`, or any XDOM-A/XDOM-B/MAINT-001
source or dedicated test file.

## H. Test matrix and regression results

All 18 items from the mission's Section 17 matrix implemented in
`tests/test_revenue_amount_variance.py`, plus orchestration-level readiness
and generalization tests:

| Item | Test | Result |
|---|---|---|
| A | expected 1000, actual 800, same currency -> shortfall 200 | pass |
| B | multiple invoice lines (500+300) against expected 1000 -> shortfall 200 | pass |
| C | actual=0 with existing billing context -> governed full shortfall | pass |
| D | quantity x rate correctly yields expected value | pass |
| E | actual == expected -> no finding | pass |
| F | actual > expected -> no underbilling finding | pass |
| G | $0.50 variance within tolerance -> no finding | pass |
| H | different currency (USD vs EUR) without FX -> no finding | pass |
| I | bare quantity, no co-located rate -> no finding (unit safety) | pass |
| J | work order not in eligible set -> no finding | pass |
| K | unrelated invoice does not distort another work order's finding | pass |
| L | repeat publication -> idempotent (same finding id) | pass |
| M | two different work orders, same variance -> two independent findings | pass |
| -- | unknown currency both sides -> proceeds, DECIMAL exposure type | pass |
| -- | `classify_currency_comparability` unit coverage (4 states) | pass |
| -- | orchestration wiring produces an `IntelligenceActivationDecision` row | pass |
| -- | generalization: different raw schema reaches READY | pass |

**17/17 pass.** Live semantic-decision inspection during test development
(not assumed) surfaced and drove the three registry corrections in Section
D.5 and the `unit_price`-as-flat-amount fallback and per-dataset
`canonical_evidence_completeness` correction in Section D.6 -- each verified
against real `SemanticInterpretationDecision`/`AnalyticalReadinessDecision`
rows before being accepted, not guessed.

**Regression suites** (all pre-existing, unmodified):
`test_capability_governed_activation_xdom_a.py`,
`test_capability_governed_activation.py`,
`test_governed_finding_publisher_identity.py`, `test_domain_detection_service.py`,
`test_trust_representative_sampling.py`,
`test_capability_architecture_guardrails.py`, `test_validation_import_boundary.py`,
`test_semantic_multilingual.py`, `test_entities_order_independence.py` --
**79/79 pass**, confirming zero behavioral change to XDOM-A, XDOM-B,
MAINT-001, Trust, semantic interpretation, or the architecture guardrails.

**Full suite:** `ruff format .` clean (789 files), `ruff format --check .`
clean, `ruff check .` clean (`All checks passed!`), `mypy .` clean (609
source files). Full `pytest` against a freshly reset disposable PostgreSQL
schema: **1707/1707 passed** (772.65s). One pre-existing test,
`tests/test_capability_shadow_stage.py::test_capability_shadow_evaluation_stage_completes_and_persists_decisions`,
initially failed on its own hardcoded rule-code allowlist (it asserted only
`{XDOM-A, XDOM-B}` could ever appear in `IntelligenceActivationDecision`
rows) -- expected, not a regression: `REVENUE-AMOUNT-VARIANCE` is a genuine,
additive third rule now participating in the same shadow-evaluation stage.
Updated the allowlist to include it (the only non-additive-file edit in this
milestone, confined to that one assertion and its comment); re-ran green.

## I. Wave 1 capability-scoped evaluation

Post-merge certification was performed on production `main` at
`4860713a12bbd319efc80ba18e561ef24df27dd1` (PR #108). The worktree was clean
and `HEAD == origin/main` before the live evidence was reconciled. Existing
completed runs were recovered rather than repeated; the remaining Rental
cases were run on their already-loaded frozen Wave 1 cases.

`NR` means the production Navigator did not expose a capability-level
readiness or candidate count for that run; it is not interpreted as zero.
`READY*` is proven by governed capability findings. Total findings include
other capabilities; the capability column is the scoped count used for
scoring.

| Frozen case | Live case / latest run | Terminal state | Readiness | Candidates | Total findings | Capability findings |
|---|---|---|---:|---:|---:|---:|
| FIELDMAINT-001 | `35e99211-0953-47f8-ab8e-5147f2596106` / `5621692e-9e67-40d9-bcae-4b7b98e8edab` | Review Required | NR | NR | 2 | 0 |
| FIELDMAINT-002 | `083edfba-c255-42b1-ba17-c60da64b4698` / `f2f337b1-4615-4dd4-a895-1e7e1ec63df3` | Review Required | READY* | 178 | 179 | 178 |
| FIELDMAINT-005 | `0ef2988a-6a3c-4bf6-af76-7624a5fe8777` / `141ec19a-a3bc-44b4-9481-5547ada15e44` | Review Required | READY | NR | 1 | 0 |
| FIELDMAINT-007 | `e2d3fcef-01fe-45b6-9084-0d718d7a128a` / `f7db600f-fb9d-4182-ac17-802a0648a60c` | Review Required | NR | NR | 1 | 0 |
| RENTAL-001 | `70f860e5-98dc-4075-9b10-c3c540671242` / `d67ce15d-2e12-4601-b9c0-d842a83fbfb9` | Review Required | NR | NR | 0 | 0 |
| RENTAL-003 | `cc2e1724-d814-44ea-a44a-8ac8eed3c7bb` / `a96d879d-bc9b-4e00-aa24-4c60302c3109` | Review Required | NR | NR | 0 | 0 |
| RENTAL-011 | `23d8e43d-b3fe-45f7-b974-e1bfe2e8e969` / `d01e8427-9b54-48f0-9669-bc36548e396a` | Review Required | NR | NR | 0 | 0 |
| RENTAL-012 | `b91f9550-b22d-4720-9874-7b8168117318` / `e3c161f5-b049-48db-b41f-0aa5322ab213` | Review Required | NR | NR | 0 | 0 |
| RENTAL-015 | `0cd01327-5ab3-4721-85e4-5e5c76d70955` / `837bba25-daae-4b10-b379-ee1eb2a7324d` | Review Required | NR | NR | 0 | 0 |
| RENTAL-018 | `260a0b35-cb0d-4568-befa-1cd07dfbd810` / `715fab0a-ae52-47e1-b484-f7a158dba622` | Review Required | NR | NR | 0 | 0 |

The Review Required state came from source-domain review flags and is not a
failed orchestration state. The Navigator did not report per-capability pack
totals, so missing values remain NR rather than being manufactured.

### I.1 179-finding anomaly diagnosis

FIELDMAINT-002 contained one pre-existing cross-domain finding and **178
REVENUE-AMOUNT-VARIANCE findings**. Every capability finding described an
expected parts amount and "actual billed amount is 0 ... from 0 invoice
record(s)." This is not genuine underbilling:

- `parts_usage.csv` has 259 rows across 178 unique `work_order_id` values;
- `invoices.csv` has 254 rows across 254 unique `work_order_id` values;
- all 178 candidate work orders have a directly linked invoice row;
- no invoice row has a blank work-order key; and
- false expected-side exposure sums to 168,713, while the invoice file
  contains 421,653 of actual billed amount.

The source linkage exists. The raw invoice column is named `amount`; on the
real corpus it remains `accepted_with_flag` because that alias is shared by
`unit_price`, `invoice_amount`, and `cost_amount`. The capability consequently
constructed zero actual invoice records and treated evidence absence as the
numeric value zero. Primary failure: `SEMANTIC_EVIDENCE_GAP`, with a
downstream `CAPABILITY_MODEL_GAP`. This is not a source `LINKAGE_GAP`; all 178
records are false positives.

### I.2 `unit_price` ambiguity diagnosis

The ambiguity is legitimate at the isolated raw-header level: `amount` alone
does not prove rate, invoice total, or cost. It is correctly
`accepted_with_flag`; lowering the shared semantic threshold would be unsafe.
However, the recurring dataset structure supplies reusable evidence that is
not yet governed: an invoice-shaped dataset with `invoice_id`,
`work_order_id`, `invoice_date`, and `status` makes its `amount` materially
different from a consumption-row unit price. Classification:
`LEGITIMATE_AMBIGUITY` for the raw token and `SEMANTIC_EVIDENCE_GAP` for the
missing dataset-role/co-column evidence. It is not a truth-authoring defect.

### I.3 Missing evidence versus observed zero

The capability does **not** safely distinguish these states in production.
An observed invoice amount of zero may support a full-shortfall finding, but
zero resolved invoice records is absence of actual-side evidence. The latter
must be blocked or represented as uncertain; it must not become
`actual_amount=0`. FIELDMAINT-002 proves the current model publishes the same
business conclusion for both states.

## J. TP/FP/FN

The frozen capability truth family is the architecture-defined Revenue
Leakage -- Amount Variance family: `unbilled_parts` (113),
`unbilled_labor_hours` (32), `missing_field_ticket_billing` (7),
`unbilled_rental_days` (2), and `late_return_leakage` (12), for **166 truth
items**. Contract/rental rate mismatches belong to the separate Contract /
Rate Compliance family and are not added to this denominator.

| Metric | Result |
|---|---:|
| TP | 0 |
| FP | 178 |
| FN | 166 |
| Precision | 0 / 178 = **0.00%** |
| Capability-scoped recall | 0 / 166 = **0.00%** |

Full-truth recall across the complete 788-item Wave 1 truth corpus is also
**0 / 788 = 0.00%**. It is supplied for full-truth transparency, not as the
capability acceptance denominator. No ambiguous match credit was assigned:
FIELDMAINT-002 has no amount-variance truth and all 178 published subjects
have source invoice evidence.

## K. Economic-value capture

The 166 in-family truth items carry **324,804.76** of economic value:
60,102.76 unbilled parts + 9,470.00 unbilled labor + 14,182.00 missing field
ticket billing + 51,400.00 unbilled rental days + 189,650.00 late-return
leakage. True-positive captured value is **0**, so economic-value capture is
**0 / 324,804.76 = 0.00%**. The 168,713 published on FIELDMAINT-002 is false
exposure and is excluded from captured value.

## L. Generalization test

`test_generalization_different_schema_same_invariant` -- a second raw schema
(`order_id`/`sku`/`qty`/`price` for consumption, `order_id`/`bill_id`/
`total_amount` for billing; none of these column names match the
FieldMaintenance-shaped fixture's own names) reaches governed `READY` purely
through canonical semantic resolution: `work_order_id` and `quantity` each
independently reach `auto_accepted` from their own alias/role/value-pattern
evidence on this schema, with no filename or column-literal branch anywhere
in the capability. Whether a finding is *also* produced on this specific
two-file fixture depends on `total_amount`'s own confidence tier (it shares
the `amount`-family ambiguity from Section B and this fixture doesn't happen
to provide the cross-dataset corroboration that pushes it to
`auto_accepted`) -- asserted honestly as a readiness-level generalization
proof, not forced into also producing a finding.

## M. Known limitations

- **`invoice_amount`'s cross-dataset-overlap dependency (Section B).** A raw
  "amount" column's resolution among `unit_price`/`invoice_amount`/
  `cost_amount` depends on which sibling concept happens to be independently,
  decisively present elsewhere in the same case. This capability's own
  `unit_price`-as-flat-amount fallback (Section C) absorbs the common case
  where `unit_price` wins the tie, but a case where NEITHER concept reaches
  `auto_accepted` (no cross-dataset corroboration at all) will not produce a
  finding even with genuine underbilling present -- an honest,
  uncertainty-preserving gap, not a defect to be closed by weakening the
  shared semantic-authority threshold.
- **Form B (`cost_amount` reference) is contract-supported but has zero live
  Wave 1 evidence** -- untested against real data, only against the direct
  rule-logic test suite.
- **No governed FX or UOM subsystem** -- by design (Section 24 stop-gate);
  `different_known`/`mixed_known_unknown` currency and any quantity without
  a co-located rate are always left uncertain, never bridged.
- **Wave 1 certification failed:** 0 TP, 178 FP, 166 FN (Sections I/J).
- **Multi-line credit/adjustment records** (a distinct billing-reduction
  concept) are not modeled -- only positive `invoice_amount` rows are summed;
  no `credit_amount`/negative-adjustment concept exists in the registry
  today.

## N. Next recommended capability

The next bounded milestone should remain inside P3.xxI.2: govern invoice-side
amount semantics from dataset-role/co-column evidence and add an explicit
actual-evidence-presence state so missing evidence blocks instead of becoming
zero. It should prove linked multi-line invoice aggregation on the frozen
corpus before rerunning certification. This is a recommendation only; no
Fix #9 or new capability work was started.

## O. Final classification

**P3.xxI.2 FAILED**

The local implementation and regression suites remain green, but the
post-merge frozen-corpus evidence fails decisively: 0.00% precision, 0.00%
capability-scoped recall, 0.00% economic-value capture, and 178 false
positives created by equating structurally missing actual-billing evidence
with an observed billed amount of zero. The next dominant failure category
is **SEMANTIC_EVIDENCE_GAP**, followed by **CAPABILITY_MODEL_GAP**. Remaining
zeros in cases containing in-family truth are consistent with the same
evidence-resolution gap; no evidence supports reclassifying truth, weakening
thresholds, or changing XDOM-A, XDOM-B, or MAINT-001.

No application code, truth, XDOM-A/B, MAINT-001, Wave 2, E.6, E.7, frontend,
or next-capability work was changed during certification.
