# P3.xxV.2C — Systemic Remediation, Fix #2 Report

**Canonical Operational-State Normalization for XDOM-B**

Scope discipline maintained throughout: only XDOM-B's raw-status-literal dependency
was touched. Revenue/matching logic, entity confidence, `ACCEPTED_WITH_FLAG`
behavior, XDOM-A's own logic, and domain classification were all left frozen, as
instructed — confirmed unchanged in Section L.

---

## A. Existing State Ontology Reconciliation

Before writing any code, the existing semantic/process ontology was inspected for a
reusable operational-state concept. Found: **`app/process/state_normalization.py`**
(shipped under P3.xxE.4), which already defines exactly the concept this fix needed:

```python
_CANONICAL_STATE_ALIASES: dict[str, frozenset[str]] = {
    "OPEN": frozenset({"open", "new", "created"}),
    "ASSIGNED": frozenset({"assigned"}),
    "IN_PROGRESS": frozenset({"active", "in_progress", "in progress", "ongoing", "started"}),
    "COMPLETED": frozenset({"completed", "complete", "done", "finished"}),
    "CLOSED": frozenset({"closed", "close"}),
    "CANCELLED": frozenset({"cancelled", "canceled", "voided", "void"}),
}
```

- **Existing concepts:** a small, generic, English-language raw-value alias table
  (the same registry-of-data pattern as `app/semantic/concept_registry.py`),
  producing six canonical state names.
- **Existing canonical representation:** bare uppercase strings (`"COMPLETED"`,
  `"CLOSED"`, etc.), not an enum — matched for consistency.
- **Current consumers (before this fix):** `normalize_state_value()` (E.4 process
  activities/state-transition discovery, gated by per-field semantic-decision tier)
  and `find_state_sequence()` (E.4 state-transition discovery). XDOM-B was not a
  consumer at all — it compared a raw literal directly.
- **Gap found:** no public, machine-status-independent lookup existed. The only
  entry point, `normalize_state_value()`, requires per-field semantic-decision
  metadata (`machine_status`, `machine_confidence`, `is_independently_corroborated`)
  that XDOM-B's call signature (a plain canonical `DataFrame`) does not carry — that
  metadata answers a different question ("is this column's *concept identity* itself
  confirmed"), not the one XDOM-B actually has ("given this column is already known
  to be `operational_event_status`, what does *this row's value* mean").
- **Recommendation followed:** reuse the existing alias table via a **new, small,
  public function** rather than building a second ontology. No new canonical state
  names were introduced. `COMPLETED` and `CLOSED` were kept as the two distinct
  states the existing vocabulary already defines — never merged into one, honoring
  "exact names must follow existing ontology if available."

## B. Canonical State Architecture

Two additive pieces, both minimal:

1. **`app/process/state_normalization.py`**: extracted the existing normalization
   step into `_normalize_raw_state_text()` (used identically by both callers now,
   zero behavior change to `normalize_state_value()`), and added a new public
   function:

   ```python
   def lookup_canonical_state(raw_value: object) -> str | None:
       """Deterministic raw-value -> canonical-state-name lookup ... for callers
       that already know a column IS a state/status field ... without the
       machine_status/confidence-tier gating normalize_state_value applies."""
       return _lookup_canonical_state(_normalize_raw_state_text(raw_value))
   ```

   Returns `None` — never a fabricated name — for anything not in the alias table.

2. **`app/services/cross_domain_intelligence_service.py`**: a new,
   rule-scoped constant declaring which of the *shared* vocabulary's canonical
   states satisfy Rule B's own business condition:

   ```python
   _REVENUE_EXPECTED_OPERATIONAL_STATES = frozenset({"COMPLETED", "CLOSED"})
   ```

   This is the business-rule interpretation layer (XDOM-B's own concern), kept
   separate from the raw-vocabulary layer (the process module's concern) — exactly
   the separation instructed in Section 4 ("do not put raw vocabulary handling
   inside XDOM-B").

**Relation to the E.4 Process Graph (Section 9):** no new, separate ontology was
created alongside the existing one. `lookup_canonical_state()` is additive read
access to the *same* table `state_normalization.py` already owns; the E.4 process
module's own consumers (`normalize_state_value`, `find_state_sequence`) are
unmodified and unaffected.

## C. Implementation

```python
# before
if "operational_event_status" not in operations_df.columns:
    return []
completed = operations_df[
    operations_df["operational_event_status"].astype(str).str.lower() == "completed"
]
if completed.empty:
    return []

# after
if "operational_event_status" not in operations_df.columns:
    return []
canonical_states = operations_df["operational_event_status"].map(lookup_canonical_state)
completed = operations_df[canonical_states.isin(_REVENUE_EXPECTED_OPERATIONAL_STATES)]
if completed.empty:
    return []
```

A missing `operational_event_status` column (Rental's real shape) still
short-circuits on the first line, before any lookup — unchanged, no completion
fabricated. An unrecognized raw value maps to `None` via `lookup_canonical_state`,
which is not in the frozenset, so it is excluded, never assumed complete. Everything
downstream of this point (identifier matching, temporal matching, revenue existence
logic, finding publication) is byte-for-byte unchanged.

## D. Tests

- **`tests/test_process_state_normalization.py`** — 5 new unit tests for
  `lookup_canonical_state()`: completed variants, closed variants, case/whitespace
  insensitivity, open/in_progress/cancelled excluded, unrecognized value → `None`.
- **`tests/test_cross_domain_intelligence_operational_state.py`** (new file) —
  end-to-end tests through the real orchestrator (same harness pattern as
  `test_capability_governed_activation.py`): `"completed"` and `"CLOSED"` (plus case/
  whitespace variants) both produce a real XDOM-B finding; `open`/`in_progress`/
  `cancelled`/an unrecognized value/a missing status column all still produce zero;
  a source-text guardrail asserting `cross_domain_intelligence_service.py` contains
  no `== "completed"` / `== 'completed'` / `.str.lower()` pattern anywhere.
- All existing XDOM-A/XDOM-B/E.5/E.4/semantic tests re-run unmodified and green
  (Section L).

## E. PR / CI / Merge / Deploy

| Item | Value |
|---|---|
| Branch | `fix/p3xxv2c-xdom-b-canonical-operational-state` |
| Implementation SHA | `c8fbdcdca695ee88b3ce1b2c20769e2cf8e56f8a` |
| PR | [#98](https://github.com/intel4ops/intel4ops-core-platform/pull/98) |
| CI | Green — 18m29s |
| Merge SHA / final main SHA | `e235534d458de4639ff191b0c717ca5eb6448ee8` |
| Deployment | Confirmed live functionally: fresh reruns of all 10 Wave 1 simulations against the deployed API show the new behavior (Section G) |
| Migration | None — pure Python logic change, no schema change |
| Full pytest | 1607 passed (disposable Postgres reset before the run) |
| `ruff` / `mypy` | clean |

## F. Wave 1 Controlled Rerun

Fresh `AnalysisCase`s were created for all 10 Wave 1 simulations against post-merge
production (concurrency 1, sequential), reusing the exact frozen customer-data CSVs
and the same normal production pipeline as Fix #1's rerun. No truth, manifest, or
membership was touched.

## G. 10-Case Before/After Matrix

| Simulation | Raw status evidence | Canonical state | XDOM-B readiness | Source op. rows | Stage-0-eligible rows | Findings | Primary remaining blocker |
|---|---|---|---|---|---|---|---|
| FIELDMAINT-001 | `work_orders.status = "CLOSED"` (227/227) | CLOSED | READY | 227 | **227** (was 0) | 0 | **NEW**: arithmetic-level trust readiness `BLOCKED` (`required_field_completeness`) — Section N |
| FIELDMAINT-002 | same | CLOSED | READY | 254 | **254** (was 0) | 0 | same |
| FIELDMAINT-005 | n/a — case-wide trust `failed` (Section F, prior diagnosis) | n/a | BLOCKED | 1,405 | 0 (never reached) | 0 | unrelated, pre-existing, untouched by this fix |
| FIELDMAINT-007 | `work_orders.status = "CLOSED"` (201/201) | CLOSED | READY | 201 | **201** (was 0) | 0 | same as 001/002 |
| RENTAL-001 | no status column on `dispatch.csv`/`field_tickets.csv` | n/a | READY | 55 | 0 (unchanged) | 0 | missing status evidence, correctly not fabricated |
| RENTAL-003 | same | n/a | READY | 29 | 0 | 0 | same |
| RENTAL-011 | same | n/a | READY | 67 | 0 | 0 | same |
| RENTAL-012 | same | n/a | READY | 76 | 0 | 0 | same |
| RENTAL-015 | same | n/a | READY | 150 | 0 | 0 | same |
| RENTAL-018 | same | n/a | READY | 89 | 0 | 0 | same |

("Stage-0-eligible rows" = rows whose canonical state is in
`{COMPLETED, CLOSED}`, i.e. candidates that now survive the precondition XDOM-B's
own `run_lost_activity_to_revenue_gap` applies first.)

## H. Finding Metrics

| | Before Fix #2 | After Fix #2 |
|---|---|---|
| Findings (all 10) | 0 | 0 |
| TP / FP / FN | 0/0/788 | 0/0/788 |

Unchanged, exactly as the mission anticipated is acceptable ("It is NOT necessary
for Wave 1 recall to become high yet"). What changed is **where** the pipeline stops
— see Section N.

## I. False-Positive Safety

No false activation was introduced. Confirmed directly: on all 4 FieldMaintenance
cases, XDOM-B's activation decision is unchanged (`READY`/`BLOCKED` identical to
before this fix — Fix #2 doesn't touch activation, only the rule's own internal
candidate filter). `open`/`in_progress`/`cancelled`/an unrecognized status value all
still correctly produce zero eligible rows (unit-tested, Section D). No candidate
was ever incorrectly treated as `COMPLETED`/`CLOSED`.

## J. FieldMaintenance Result

**The fix worked exactly as designed.** All 227/254/201 `"CLOSED"` work orders on
FIELDMAINT-001/002/007 now correctly normalize to a canonical state XDOM-B accepts
— Stage 0's collapse-to-zero is gone. Candidates advanced to a **new, previously
invisible** blocker (Section N) rather than producing findings — per the mission's
own framing, this is direct evidence the fix worked, not evidence it failed.

## K. Rental Result

**No completion was fabricated, as required.** `dispatch.csv` and `field_tickets.csv`
still have no status-aliased column at all on any of the 6 Rental cases; the function
still returns `[]` at its first line, unchanged. No independent completion evidence
(e.g., `dispatch_date`/`return_date` presence) was used to infer completion — that
would require wiring in E.4 process-boundary evidence, a materially larger change
this milestone explicitly did not authorize ("only use such evidence if it is
already supported by Intel4Ops semantic/process architecture" — no such wiring
exists today connecting E.4 process-boundary state to XDOM-B). Rental remains
without eligible completed-state candidates. This is the correct, honest,
governance-preserving outcome, not a fix shortfall.

## L. Regressions

- Full pytest: 1607/1607 passed.
- XDOM-A: unchanged on all 10 cases (identical `governed_status`/`missing`/`agree`
  to the Fix #1 rerun) — Fix #2 touches only XDOM-B's own function.
- E.5 activation regression: 38/38 passed (capability/shadow/governed-activation
  suites).
- E.4 process + semantic regression: 178/178 passed.
- No unrelated semantic concepts changed — `normalize_state_value()`'s own behavior
  and its 6 existing tests are untouched (only its internal normalization line was
  factored out, not its logic).
- Tenant isolation: all 10 reruns scoped to the single pre-existing pilot
  organization, consistent with every prior wave/fix pass; no cross-tenant action
  taken.
- Ground-truth isolation: `state_normalization.py` and
  `cross_domain_intelligence_service.py` are both in the AST-guarded
  `PRODUCTION_EXECUTION_MODULES` list in `tests/test_validation_import_boundary.py`
  and neither imports from `app.ground_truth_validation` — guardrail test passed.
- No simulation-specific or filename-specific code: confirmed by the new source-text
  guardrail test (Section D) and by direct reading of the diff — no simulation ID,
  business family name, or filename appears anywhere in the changed files.
- No raw truth values used in production: this fix touched no validation-plane code
  and consulted no hidden truth at any point.

## M. Fix Classification

**FIX #2 VALIDATED**

All 7 stated success criteria hold:
1. XDOM-B no longer depends on the raw literal `"completed"` (confirmed by the
   source-text guardrail test and the diff itself).
2. `CLOSED` (FieldMaintenance's real vocabulary) normalizes through the shared
   canonical mechanism and becomes eligible, confirmed live on 3/4 FieldMaintenance
   cases (227/254/201 rows respectively).
3. Valid FieldMaintenance candidates advance beyond Stage 0 — confirmed live,
   Section G.
4. Missing Rental status is not fabricated — confirmed live, Section K.
5. No false positives / unsafe activation introduced — Section I.
6. No simulation-specific vocabulary was added — the alias table used is the
   pre-existing, generic E.4 vocabulary; only two rule-scoped canonical *names*
   (already-existing state names, not new raw strings) were referenced.
7. All regressions remain green — Section L.

## N. Next Empirically Observed Blocker

**Not** the anticipated DC-6 (binary revenue-existence check) — a **new, more
upstream, previously invisible** blocker was empirically discovered instead, because
Fix #2 is the first time in this entire remediation program that
`governed_finding_publisher.publish()` has ever actually been called on real
production data (every prior run eliminated all candidates at Stage 0 before
`publish()` was reached).

**`NEXT-1`: Arithmetic-level trust readiness is `BLOCKED` on every FieldMaintenance
case that reaches it**, confirmed identically on FIELDMAINT-001 and FIELDMAINT-007:

```json
{"analytical_level": "arithmetic", "readiness_status": "blocked",
 "blocking_rule_codes": ["required_field_completeness"],
 "explanation": "critical trust rules failed"}
```

Traced to its root by reading `RequiredFieldCompletenessRule.execute()`
(`app/engines/trust_engine.py:158-193`) together with the orchestration call site
(`analysis_case_orchestration_service.py:1015,1043-1048`): the Trust engine's
`required_field_completeness` rule is executed against `raw_df.to_dict("records")`
— the dataset's **original, pre-canonicalization** column names (confirmed via
`_reload_canonical_dataframe`, which re-parses the source file directly and returns
it unmapped) — while its `required_fields` configuration
(`_DOMAIN_TRUST_RULES["operations"] = ["operational_event_id", "asset_id"]`) is
written in **canonical** field names. `record.get("operational_event_id")` is
therefore `None` for every record in every dataset where that concept is only
present under an alias (`work_order_id`, `dispatch_id`, `trip_id`, etc. — i.e.
virtually every real dataset in this corpus), producing a 100%-affected,
always-failing rule result — confirmed live: 227/227 records "have missing required
fields" on FIELDMAINT-001, identically on FIELDMAINT-007, despite `asset_id` and the
`operational_event_id`-aliased `work_order_id` column both being genuinely,
completely populated in the source data. Trust runs *before* mapping in the
orchestration loop, so this mismatch is structural, not case-specific.

`governed_finding_publisher.publish()` requires this ARITHMETIC-level decision to be
`READY`/`READY_WITH_WARNINGS` (`governed_finding_publisher.py:82-93`) and silently
returns `None` otherwise — with **no error, no warning, no visible signal at the
activation-decision level** (which is a *separate* gate, already confirmed correct
in the prior diagnosis). This is why FIELDMAINT-001/002/007 show `finding_count: 0`
despite 227/254/201 candidates now correctly surviving XDOM-B's own Stage 0 filter.

**This has almost certainly been blocking every governed cross-domain finding on
every canonical-field-aliased dataset, in every case, for as long as the governed
finding-publication gate has existed** — invisible until now purely because
XDOM-B's own Stage 0 defect always eliminated candidates first. Its scope is larger
than DC-6: it sits in the shared `governed_finding_publisher`, not inside any one
rule, so it would block XDOM-A's findings too, and any future capability, the moment
its own candidate logic ever produces something to publish.

Whether DC-6 (existence-only vs. amount-based revenue matching) is *also* a real
blocker for FieldMaintenance's 187 candidate leakage items could not be empirically
confirmed this pass, because NEXT-1 sits upstream of it and prevented any finding
from reaching the publish stage regardless of what the match-key logic found. NEXT-1
must be resolved (or at minimum its match-stage behavior directly inspected) before
DC-6's true empirical scope can be measured.

**Not fixed in this pass**, per instruction.

---

## Final Classification

**FIX #2 VALIDATED**
