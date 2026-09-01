# P3.xxV.2A — Wave 1 Remediation, Fix #1 Report

**Role:** Claude operated as validation operator for this controlled before/after
experiment, exactly as in Wave 1. No production logic was modified beyond the
single change under test (PR #97, already merged before this report's mission
began). No other fix, threshold, or model change was introduced during this
pass.

---

## A. PR / CI / Merge / Deploy

| Item | Value |
|---|---|
| PR | [#97](https://github.com/intel4ops/intel4ops-core-platform/pull/97) — "recognize dispatch_id as an operational_event_id alias" |
| Implementation SHA (branch head) | `0657c01810a7be288ea698ec4a67424e2ffd0582` |
| Merge SHA / final main SHA | `8ecceac3d86124e84e064063747f6b3d44cc1e6f` |
| CI | Green — "Ruff, Mypy, Pytest, and Alembic" passed in 19m12s |
| Merged at | 2026-09-01T11:27:39Z |
| Deployment | Confirmed live functionally: `dispatch.csv` classified `domain:operations` (basis `["asset_id","dispatch_id"]`) on every fresh case created after merge, which is only possible with the new alias present. `/api/v1/health` returned `{"status":"ok"}` throughout. |
| Migration state | Unchanged — this PR added no Alembic revision (pure Python data change to `app/domain_registry.py`); no migration ran as part of this deploy. |
| Unrelated production changes | None. The only other commit on `main` since the Wave 1 baseline (`c081936`) is `be4c29c`, the docs-only Wave 1 report — no code. |

## B. Controlled Rerun Baseline

Fresh `AnalysisCase`s were created for all 10 Wave 1 simulations via the normal
production pipeline (`POST /analysis-cases` → `POST .../artifacts` (multipart
customer-data upload) → `POST .../run`), concurrency 1, sequential. No case ID
or run ID from Wave 1 was reused. A new `ValidationSimulation` was registered
per case (`{sim}-RERUN1`) and the same frozen ground truth
(`ExternalSimulationPackage.build_ground_truth_payload()` output, byte-identical
to what Wave 1 used) was re-uploaded against it — the corpus, hidden truth, and
manifests were never touched. All 10 runs reached a terminal status
(`review_required` for 9, `partial` for FIELDMAINT-005) with zero
infrastructure failures.

## C. Semantic Before/After

**Domain detection basis for `dispatch_id`-bearing datasets (drives `domain_registry.py` → shared by domain detection, field mapping, and legacy entity linking):**

| | BEFORE (Wave 1) | AFTER (PR #97) |
|---|---|---|
| `dispatch.csv` | `domain: null` or unconfirmed — `dispatch_id` had no alias | `domain: operations`, status `confirmed`, basis `["asset_id","dispatch_id"]` |
| `field_tickets.csv` | no operational-event signal | `domain: operations`, status `needs_review`, basis `["dispatch_id"]` (a foreign-key reference to dispatch, picked up by the same alias with no extra code) |

**P3.xxE.1 Semantic Interpretation layer (separate system — concept candidate generators, `AUTO_ACCEPTED`/`ACCEPTED_WITH_FLAG`/`REVIEW_REQUIRED`/`UNRESOLVED`):** checked directly on RENTAL-001's rerun via `GET .../semantic?run_id=`. `dispatch_id`'s field decision:

```json
{"source_field":"dispatch_id","selected_concept":null,"confidence":0,
 "status":"unresolved","evidence_summary":["no candidate concept was proposed by any generator"]}
```

**This is unchanged from Wave 1 and is expected.** PR #97 only edited
`app/domain_registry.py`'s `CANONICAL_FIELD_ALIASES` table, which feeds the
*older*, simpler `canonicalize_field()` mechanism (domain detection, field
mapping, and the legacy `entity_resolution_service.py`). It does not touch the
*newer* P3.xxE.1/E.2 semantic candidate-generator vocabulary, which is a wholly
separate system with its own concept registry. `dispatch_id` was never added
there, so it correctly stays `UNRESOLVED` at that layer. This distinction
matters for Section D below.

**Trigger mechanism confirmed generic, not simulation-specific:** the alias
fired identically on `dispatch.csv` and, independently, on `field_tickets.csv`
(a file that has nothing to do with the alias addition's original target),
purely because both happen to contain a `dispatch_id` column. No simulation ID,
family name, filename, or scenario type appears anywhere in the changed code
(confirmed by re-reading the diff: `app/domain_registry.py` and
`tests/test_domain_detection_service.py` only).

## D. Entity Before/After

**Legacy entity-presence gate (what governed activation's `legacy_entity:operational_event` and `field:operational_event_id` requirements actually check — confirmed by requirement text disappearing from `governed_missing_summary`, Section E):** satisfied on all 6 Rental reruns. This is the mechanism PR #97 targeted, and it worked.

**P3.xxE.3 canonical entity graph (`GET .../entities`, `CanonicalCaseEntity`, semantic-confidence-gated):** checked on all 6 Rental reruns.

| Simulation | Entity type counts (AFTER) |
|---|---|
| RENTAL-001 | `{"ASSET": 40}` |
| RENTAL-003 | `{"ASSET": 40}` |
| RENTAL-011 | `{"ASSET": 45}` |
| RENTAL-012 | `{"ASSET": 45}` |
| RENTAL-015 | `{"ASSET": 350}` |
| RENTAL-018 | `{"ASSET": 50}` |

**Zero `OPERATIONAL_EVENT` canonical entities were produced on any Rental case, before or after.** This is consistent with Section C: since the E.1 semantic layer's own concept vocabulary was never touched by this fix, the E.3 canonical-entity pipeline (which is gated on that semantic layer's `AUTO_ACCEPTED` confidence, not on `domain_registry.py`'s alias table) has no new evidence to act on. **No unintended entity types appeared** — no `WORK_ORDER`, `CUSTOMER`, or spurious `ASSET` inflation beyond what a 9-file customer-data upload would normally produce; ASSET counts are stable and proportional to each simulation's fleet size.

**Conclusion: this fix operates entirely through the legacy `canonicalize_field`-driven path (domain detection → field mapping → `entity_resolution_service.py`'s `ENTITY_ID_FIELDS`), which is what governed activation's requirement-presence checks read. It does not populate the newer semantic/E.3 canonical entity graph.** That is a distinct, deeper system with its own vocabulary gap — see Section O.

## E. Capability Readiness Before/After

| | XDOM-A | XDOM-B |
|---|---|---|
| **FieldMaintenance (4/4), BEFORE** | BLOCKED — `domain:maintenance, field:downtime_hours, trust:maintenance` | READY (3/4) / BLOCKED (005) — `trust:operations` |
| **FieldMaintenance (4/4), AFTER** | BLOCKED — identical missing set, unchanged | READY (3/4) / BLOCKED (005) — identical, unchanged |
| **Rental (6/6), BEFORE** | BLOCKED — `domain:operations, field:operational_event_id, legacy_entity:operational_event` | BLOCKED — same 3 plus `trust:operations` |
| **Rental (6/6), AFTER** | **PARTIAL** — `governed_missing_summary: []`, `below_confidence_threshold: ["entity_identity.ASSET"]`, `agree: false` (legacy=True) | **READY** — `governed_missing_summary: []`, `agree: true` (legacy=True) |

XDOM-B fully unblocked on all 6 Rental simulations: every domain/field/entity/trust
requirement that was previously missing is now satisfied, and the governed
decision agrees with the (also newly-true) legacy condition.

XDOM-A moved from BLOCKED to **PARTIAL**, not fully READY, on all 6 — its
presence-level requirements (`domain:operations`, `field:operational_event_id`,
`legacy_entity:operational_event`) are all cleared (`governed_missing_summary`
is empty), but a **separate, legitimate confidence gate**
(`below_confidence_threshold: ["entity_identity.ASSET"]`) still holds it back:
the ASSET entities' `entity_identity_confidence` (0.65, single-dataset,
uncorroborated per the entity evidence summary) doesn't clear whatever bar
governed XDOM-A requires. `agree: false` here reflects that the simpler legacy
condition (presence-only) doesn't check this confidence dimension at all —
this is the governed gate being *stricter* than legacy, exactly the P3.xxE.5
design intent, not a new divergence introduced by this fix. This is a textbook
example of the exact scenario Section 8 of the mission anticipated: **the
original blocker was removed and replaced by a later, legitimate one.**

## F. Findings Before/After

| Simulation | Findings BEFORE | Findings AFTER |
|---|---|---|
| FIELDMAINT-001/002/005/007 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |
| RENTAL-001/003/011/012/015/018 | 0 / 0 / 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 / 0 |

Zero findings on every case, before and after, including the 6 Rental cases
where XDOM-B moved fully to READY. Per the mission's explicit framing, this
does **not** mean the fix failed — Wave 1's own report (Section I) already
established, on FieldMaintenance data where XDOM-B was READY from the start,
that activation alone doesn't guarantee detections: XDOM-B's specific matching
logic doesn't fire even on data conceptually adjacent to what it looks for.
The Rental result is consistent with that same, already-identified, deeper
rule-logic layer — not a new, unexplained failure of this fix.

## G. Full-Truth Metrics Before/After

| Simulation | TP/FP/FN BEFORE | TP/FP/FN AFTER |
|---|---|---|
| FIELDMAINT-001 | 0/0/63 | 0/0/63 |
| FIELDMAINT-002 | 0/0/114 | 0/0/114 |
| FIELDMAINT-005 | 0/0/387 | 0/0/387 |
| FIELDMAINT-007 | 0/0/65 | 0/0/65 |
| RENTAL-001 | 0/0/16 | 0/0/16 |
| RENTAL-003 | 0/0/9 | 0/0/9 |
| RENTAL-011 | 0/0/15 | 0/0/15 |
| RENTAL-012 | 0/0/46 | 0/0/46 |
| RENTAL-015 | 0/0/52 | 0/0/52 |
| RENTAL-018 | 0/0/21 | 0/0/21 |
| **Total** | **0/0/788** | **0/0/788** |

Full-truth recall: 0.0% before and after, wave-wide. Unchanged, as expected
given Section F.

## H. Capability-Scoped Metrics Before/After

Scoping to the 3 registered families changes nothing numerically (still 0
recall), but the *reason* changed materially for Rental: before, 6/6 Rental
simulations were outside the capability-scoped population entirely (both
models BLOCKED, no rule ever executed). After, XDOM-B is now IN the
capability-scoped population for all 6 (READY, executed, found nothing) and
XDOM-A is PARTIAL (not executed, confidence-gated). This is a real, measurable
shift in *which* layer is responsible for the zero result — from "never
attempted" to "attempted, rule logic found nothing" for XDOM-B specifically —
even though the scored metric itself (0.0%) is unchanged.

## I. FieldMaintenance Regression Check

All 4 FieldMaintenance cases were rerun fresh (not reused from Wave 1) and
compared field-by-field against Wave 1:

- Domain detection basis for `maintenance_events.csv`: identical
  (`domain: operations`, basis `["asset_id","work_order_id"]`) on all 4.
- XDOM-A: BLOCKED, identical missing set, on all 4.
- XDOM-B: READY (001/002/007) / BLOCKED-on-`trust:operations` (005), identical
  to Wave 1, on all 4.
- Finding count: 0, identical, on all 4.
- TP/FP/FN: identical to Wave 1's original numbers, on all 4 (Section G).

**No regression. No falsely-improved readiness. No new activation.** This is
expected and required: `dispatch_id`/`dispatch_date`/`return_date` do not
appear anywhere in FieldMaintenance's schema, so the new aliases have no
surface to act on there.

## J. False-Activation Safety

- The alias is a **presence** signal only (a column name match), consumed
  through the same governed-readiness pipeline every other alias already goes
  through — it does not bypass any confidence, trust, or governance check.
  Concrete proof: XDOM-A on Rental still did **not** reach READY despite its
  presence-level requirements clearing, because a separate confidence gate
  (`entity_identity.ASSET`) still applies (Section E).
- No entity was created from an "unrelated ID" — `dispatch_id` only ever
  produces an `operational_event`-typed link where a `dispatch_id` column
  literally exists in the uploaded data; no inference beyond that column match
  occurred.
- No XDOM activation happened "based only on alias name" — XDOM-B's own
  activation still required `trust:operations` to independently resolve
  (confirmed: this was the one requirement that differed between the 3
  READY-eligible FieldMaintenance cases and FIELDMAINT-005, and it is computed
  by the Trust engine from actual data quality, not from domain/alias
  presence).
- Governed readiness requirements (`governed_missing_summary`,
  `governed_confidence_summary`) remained mandatory and enforced throughout —
  every AFTER decision was still produced by the same governed evaluator, not
  bypassed.

## K. Tenant Isolation

All 20 new cases (10 reruns + their validation registrations) were created
under the single pre-existing pilot organization
(`41f93780-1840-426b-95ed-31a5a4478765`, "SOTRA Pilot") using the operator's own
authenticated session — consistent with how Wave 1 itself operated, no
cross-tenant action was taken or tested in this pass. Tenant-boundary
correctness at the database/migration level is covered by the standing
Postgres tenant-integrity test suite (`test_postgres_migrations.py`), which
ran clean (83/83) as part of PR #97's own pre-merge full-suite pass (Section A)
and was not touched by this fix.

## L. Ground-Truth Isolation

`app/domain_registry.py` and `tests/test_domain_detection_service.py` are the
only two files this fix touched — neither is in
`app/ground_truth_validation/` or imports from it (confirmed by the AST-guarded
`tests/test_validation_import_boundary.py`, which passed as part of the same
pre-merge full-suite run). The rerun procedure itself only read persisted,
terminal-state production output for scoring, consistent with the Validation
Plane's one-way dependency rule — no hidden truth was consulted before or
during any of the 10 production runs.

## M. 10-Case Comparison Matrix

| Simulation | op_event semantic BEFORE | op_event semantic AFTER | op_event entities B/A | XDOM-A readiness B/A | XDOM-B readiness B/A | findings B/A | TP B/A | FN B/A | primary remaining blocker AFTER |
|---|---|---|---|---|---|---|---|---|---|
| FIELDMAINT-001 | n/a (no dispatch_id) | n/a | 0 / 0 | BLOCKED / BLOCKED | READY / READY | 0 / 0 | 0/0 | 63/63 | domain:maintenance never detected; rule-logic mismatch |
| FIELDMAINT-002 | n/a | n/a | 0 / 0 | BLOCKED / BLOCKED | READY / READY | 0 / 0 | 0/0 | 114/114 | same |
| FIELDMAINT-005 | n/a | n/a | 0 / 0 | BLOCKED / BLOCKED | BLOCKED / BLOCKED | 0 / 0 | 0/0 | 387/387 | domain:maintenance + trust:operations |
| FIELDMAINT-007 | n/a | n/a | 0 / 0 | BLOCKED / BLOCKED | READY / READY | 0 / 0 | 0/0 | 65/65 | domain:maintenance; rule-logic mismatch |
| RENTAL-001 | UNRESOLVED (no alias) | UNRESOLVED (alias exists elsewhere; concept still unresolved) | 0 / 0 | BLOCKED / **PARTIAL** | BLOCKED / **READY** | 0 / 0 | 0/0 | 16/16 | entity_identity.ASSET confidence (XDOM-A); rule-logic mismatch (XDOM-B) |
| RENTAL-003 | UNRESOLVED | UNRESOLVED | 0 / 0 | BLOCKED / **PARTIAL** | BLOCKED / **READY** | 0 / 0 | 0/0 | 9/9 | same |
| RENTAL-011 | UNRESOLVED | UNRESOLVED | 0 / 0 | BLOCKED / **PARTIAL** | BLOCKED / **READY** | 0 / 0 | 0/0 | 15/15 | same |
| RENTAL-012 | UNRESOLVED | UNRESOLVED | 0 / 0 | BLOCKED / **PARTIAL** | BLOCKED / **READY** | 0 / 0 | 0/0 | 46/46 | same |
| RENTAL-015 | UNRESOLVED | UNRESOLVED | 0 / 0 | BLOCKED / **PARTIAL** | BLOCKED / **READY** | 0 / 0 | 0/0 | 52/52 | same |
| RENTAL-018 | UNRESOLVED | UNRESOLVED | 0 / 0 | BLOCKED / **PARTIAL** | BLOCKED / **READY** | 0 / 0 | 0/0 | 21/21 | same |

("op_event semantic" = the P3.xxE.1 concept-decision status for the
`dispatch_id`/`operational_event_id` field specifically, distinct from the
domain-detection-basis change reported in Section C.)

## N. Fix Classification

**FIX #1 PARTIALLY VALIDATED**

The alias corrected its intended systemic defect exactly as designed, at
exactly the layer it targeted (domain detection → field mapping → legacy
entity-presence checks → governed readiness), and downstream behavior advanced
safely: 6/6 Rental simulations moved XDOM-B from BLOCKED to fully READY and
XDOM-A from BLOCKED to PARTIAL (a legitimate, stricter, unrelated confidence
gate), with zero regression on FieldMaintenance and zero false activation.

It is "partially" rather than fully validated only in the sense the mission's
own Section 8 anticipated as an acceptable outcome ("a change from one blocker
to another may still mean FIX #1 worked") — an additional issue in the
*same general semantic/entity layer* remains: the newer P3.xxE.1 concept
candidate-generator vocabulary (a system separate from the alias table this
fix edited) still has no concept for `dispatch_id`, so the E.3 canonical
`OPERATIONAL_EVENT` entity graph remains empty on Rental even though the
legacy presence-check path that governed activation actually reads is now
satisfied. All 8 success criteria from Section 14 are met on their own terms
(1, 2, 3, 4, 5, 6, 7, 8 all hold) — the "partial" qualifier is about the
existence of this second, deeper semantic-layer gap, not about any criterion
failing.

## O. Next Systemic Blocker — Not Implemented

**NEXT SYSTEMIC BLOCKER: XDOM-B rule-logic / leakage-taxonomy mismatch**

- **Layer:** Intelligence (the XDOM-B rule's own matching logic), one layer
  downstream of everything fixed so far.
- **Evidence:** XDOM-B is now READY and actually executing on 3/4
  FieldMaintenance cases (unchanged from Wave 1) and, as of this fix, all 6/6
  Rental cases — 9 of 10 simulations total — and finds zero true positives on
  every one of them. Wave 1's report (Section I) already traced this on
  FieldMaintenance to a mismatch between XDOM-B's "lost activity, no revenue
  record" pattern and the corpus's actual injected leakage types
  (`overtime_leakage`, `unbilled_parts`, `contract_rate_mismatch`, etc.); this
  rerun extends the same observed symptom to Rental's taxonomy
  (`excessive_asset_downtime`, `rental_rate_mismatch`, `late_return_leakage`,
  etc.), none of which is a "missing revenue record" pattern either.
- **Affected cases:** 9/10 (all except FIELDMAINT-005, which is still blocked
  one layer earlier by `trust:operations`).
- **Frequency:** 100% of cases where XDOM-B reaches READY produce zero true
  positives — a consistent, reproducible pattern, not intermittent.
- **Downstream impact:** this is now the single largest lever on wave-level
  recall — with FieldMaintenance's `domain:maintenance` gap and Rental's
  now-fixed `domain:operations` gap no longer masking it, XDOM-B's own
  detection logic is the visible bottleneck on 9/10 simulations.
- **Recommended next remediation target:** re-examine XDOM-B's matching
  conditions against the specific leakage shapes it activates on but misses
  (FieldMaintenance: `unbilled_parts`/`unbilled_labor_hours`/
  `missing_field_ticket_billing`; Rental: whichever scenario types share the
  closest structural shape to "activity occurred, no corresponding revenue
  record"), rather than the domain/entity/trust layer, which per this report
  is now confirmed working correctly for 9/10 cases.

Two smaller, secondary items also remain from Wave 1 and are unaffected by this
fix: FieldMaintenance's `domain:maintenance` gap (still blocking XDOM-A on all
4 FieldMaintenance cases) and FIELDMAINT-005's isolated `trust:operations` gap
— both are earlier-layer and lower-frequency than the XDOM-B rule-logic issue
above, but neither was touched or was in scope for this pass.

---

## Final Classification

**FIX #1 PARTIALLY VALIDATED**
