# P3.xxV.2K / Fix #8 — FieldMaintenance domain and Trust certification

**Certification date:** 2026-09-02

**Repository baseline:** `main` at merge commit
`910b55a846246167e158c7c0e9ca8e9c9a40709b` (PR #105)

**Scope:** post-merge live certification and documentation only

## 1. Verdict

**Fix #8 is VALIDATED.**

The two defects targeted by Fix #8 are corrected in the live Wave 1 evidence:

- **DC-3 is closed:** FIELDMAINT-005 no longer terminates `partial` because of
  `trust:operations`; it now terminates `review_required`, and XDOM-B is READY.
- **DC-4 is closed:** the FieldMaintenance maintenance-domain classification
  defect is no longer an XDOM-A blocker. XDOM-A is blocked only by
  `field:downtime_hours`, an explicitly out-of-scope capability/input contract.
- **Rental did not regress:** XDOM-A and XDOM-B remain READY on all six Rental
  cases. Zero XDOM-A findings remain a valid result where the maintenance and
  dispatch windows do not overlap.

The remaining `field:downtime_hours` blocker is not a failure of Fix #8 and was
not changed. No application code, XDOM-A, XDOM-B, MAINT-001, simulation truth,
or capability registry was modified during certification.

## 2. Baseline and evidence handling

The local checkout was clean on `main`, and `HEAD` exactly matched the supplied
merge SHA before this report branch was created. PR #105's recorded quality gate
was green: 1,690 tests passed, with Ruff and mypy clean.

The existing live results for FIELDMAINT-001, FIELDMAINT-002,
FIELDMAINT-005, FIELDMAINT-007, RENTAL-001, and RENTAL-003 were recovered from
the handoff and live case ledger rather than rerun. RENTAL-011 was recovered
after its in-progress run completed. RENTAL-012, RENTAL-015, and RENTAL-018
were then run sequentially from their unchanged `customer-data` folders.

The Navigator case ledger and run panels expose terminal status and review
payloads for the fresh single-dataset cases, but show `Findings: Not reported`
and do not expose a governed-readiness payload. Therefore this report does not
misstate those UI omissions as new readiness measurements: governed XDOM status
comes from the established Fix #8 handoff evidence, while the four completed
Rental run IDs below independently confirm terminal non-failure and no observed
Rental regression signal. The existing published-finding ledger is retained for
recall bounds; it is not represented as a new truth reconciliation.

One diagnostic orchestrated RENTAL-011 case was created while checking whether
the absent readiness payload was mode-specific. It produced the same UI
limitation and is excluded from the canonical ten-case result set.

## 3. Reconciled Wave 1 result

| Simulation | XDOM-A | XDOM-B | Terminal status | Findings used for recall | Evidence basis |
|---|---|---|---|---:|---|
| FIELDMAINT-001 | BLOCKED (`field:downtime_hours` only) | READY | `review_required` | 2 | recovered Fix #8 result; retained published ledger |
| FIELDMAINT-002 | BLOCKED (`field:downtime_hours` only) | READY | `review_required` | 1 | recovered Fix #8 result; retained published ledger |
| FIELDMAINT-005 | BLOCKED (`field:downtime_hours` only) | READY | `review_required` | 0 | recovered Fix #8 result; DC-3/DC-4 target proof |
| FIELDMAINT-007 | BLOCKED (`field:downtime_hours` only) | READY | `review_required` | 1 | recovered Fix #8 result; retained published ledger |
| RENTAL-001 | READY | READY | `review_required` | 0 | recovered Fix #8 result |
| RENTAL-003 | READY | READY | `review_required` | 0 | recovered Fix #8 result |
| RENTAL-011 | READY | READY | `review_required` | 0 | recovered case/run; live terminal confirmation |
| RENTAL-012 | READY | READY | `review_required` | 0 | live terminal confirmation |
| RENTAL-015 | READY | READY | `review_required` | 0 | live terminal confirmation |
| RENTAL-018 | READY | READY | `review_required` | 0 | live terminal confirmation |
| **Total** |  |  | **10/10 non-failed** | **4** | no count regression in retained published ledger |

Fix #7 baseline comparison:

- FIELDMAINT-005 improves from `partial` to `review_required` and XDOM-B from
  BLOCKED (`trust:operations`) to READY.
- All four FieldMaintenance cases lose `domain:maintenance` and
  `trust:maintenance` as XDOM-A blockers; only `field:downtime_hours` remains.
- The other nine terminal statuses do not regress.
- Rental remains READY/READY, with zero findings consistent with both the
  unchanged XDOM-B model limits and legitimate XDOM-A window non-overlap.

## 4. Fix #8 case and run ledger

| Simulation | case_id | run_id | Live terminal observation |
|---|---|---|---|
| FIELDMAINT-001 | live case code `CASE-05905185097E` | recovered in handoff | `review_required` |
| FIELDMAINT-002 | live case code `CASE-F9E49E27FD70` | recovered in handoff | `review_required` |
| FIELDMAINT-005 | live case code `CASE-91E58462466D` | recovered in handoff | `review_required` |
| FIELDMAINT-007 | live case code `CASE-D2D4A9EAAF93` | recovered in handoff | `review_required` |
| RENTAL-001 | live case code `CASE-9535D3D8A485` | recovered in handoff | `review_required` |
| RENTAL-003 | live case code `CASE-3672D49C79F0` | recovered in handoff | `review_required` |
| RENTAL-011 | `23d8e43d-b3fe-45f7-b974-e1bfe2e8e969` | `9c16246d-e0e5-4ee7-87f4-509bcf8f18ba` | `review_required` |
| RENTAL-012 | `b91f9550-b22d-4720-9874-7b8168117318` | `52f3b2e2-f972-4064-bf48-0467b4748163` | `review_required` |
| RENTAL-015 | `0cd01327-5ab3-4721-85e4-5e5c76d70955` | `8759ef49-4b7c-4ea1-882e-4e939ea1c8ff` | `review_required` |
| RENTAL-018 | `260a0b35-cb0d-4568-befa-1cd07dfbd810` | `ab54017e-c5d7-4c4c-bc6f-11667e920a7f` | `review_required` |

The completed Rental runs reported operator-review items for conservative
source-domain confirmation (including `maintenance.csv`, `field_tickets.csv`,
and `payments.csv`). They did not fail. These review payloads are recorded as
an interface/operational observation, not reclassified as a Fix #8 regression.

## 5. Full-truth and capability-scoped recall

The frozen Wave 1 truth denominator remains **788 expected findings**. Its last
audited capability classification remains:

- **PARTIALLY_IMPLEMENTED:** 263 (33.4%).
- **OUT_OF_SCOPE_NOT_IMPLEMENTED:** 456 (57.9%).
- **AMBIGUOUS:** 44 (5.6%).
- **Unclassifiable:** 25 (3.2%).
- Check: 263 + 456 + 44 + 25 = 788.

Four governed, published FieldMaintenance findings remain in the retained live
ledger: FIELDMAINT-001 (2), FIELDMAINT-002 (1), FIELDMAINT-007 (1), and all
other cases (0). Because the fresh cases were not independently matched to the
hidden truth ledger, these are honest upper bounds, not measured recall:

- **Capability-scoped recall:** at most **4/263 = 1.5%**.
- **Full-truth recall:** at most **4/788 = 0.5%**.

Fix #8 increases correct capability access by closing DC-3/DC-4; it does not
expand the 263-item reachable taxonomy or prove any of the four findings true
positive. The bounds therefore remain numerically unchanged even though the
foundational readiness state materially improves.

## 6. Remaining failure classification and dominant category

| Category | Remaining item | Status after Fix #8 |
|---|---|---|
| Foundational generalization | DC-3 `trust:operations` establishment | **Closed** |
| Foundational generalization | DC-4 maintenance-domain classification | **Closed** |
| Capability/input contract | FieldMaintenance XDOM-A requires `field:downtime_hours` | Open, explicitly out of scope |
| Intelligence model defect | DC-6: XDOM-B is existence-oriented and does not model amount variance/underbilling/timing | Open |
| Intelligence model defect | MAINT-001 semantics do not match the truth's two-occurrence temporal repeat-repair mechanism | Open |
| Intelligence coverage gap | DC-7: no registered capability for 456/788 expected findings | Open, product-scope gap |
| Simulation/validation authoring | DC-8: Rental truth metadata omissions | Open, external |

**The next dominant failure category is intelligence model/capability
coverage, not foundational plumbing.** Fix #8 completes the wave-wide
transition anticipated by the Fix #7 report: DC-6 limits detection inside the
nominally reachable 263-item set (previous analysis estimated roughly 187 of
263 are exposed to its amount/timing mismatch), while DC-7 leaves 456 of 788
truth items without a registered capability at all. The remaining
`field:downtime_hours` requirement is a narrower access/input-contract blocker
for FieldMaintenance XDOM-A and does not reopen DC-3 or DC-4.

## 7. Scope control and stop condition

Certification made no application-code changes and no changes to XDOM-A,
XDOM-B, MAINT-001, Wave 1 inputs, hidden truth, capability definitions, E.6,
E.7, or frontend code. No Wave 2 work was performed. No Fix #9 was started or
defined.

This docs-only report is the terminal artifact for P3.xxV.2K. After its
docs-only pull request is opened, work stops pending explicit owner
authorization.
