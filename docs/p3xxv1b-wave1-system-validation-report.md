# P3.xxV.1B — Wave 1 System Validation Report

**Role executed:** Claude operated exclusively as a TEMPORARY VALIDATION OPERATOR against the deployed
Intel4Ops application (`https://intel4ops-core-api.onrender.com`, frontend `intelops-navigator.lovable.app`)
using only existing, unmodified APIs and services. No production intelligence, thresholds, semantic
decisions, entity/relationship outputs, or process outputs were created, edited, or bypassed at any point.
No simulation was patched to pass. No hidden truth was used to steer interpretation before scoring. This
report is the operator's factual record of what happened; it recommends but does not perform remediation.

**Baseline (frozen before execution, re-verified unchanged after):**
- Application: main @ `c0819368276e622b07edddbf0831c08912002baa` (PR #96, "minimal wave coordinator" — the
  last merge prior to this wave; P3.xxE.5 GOVERNED activation for XDOM-A/XDOM-B and P3.xxV.1A corpus
  discovery/registration both already live at this SHA).
- Validation Plane: `simple_v1` (v1.0) and `simulation_truth_v1` (v1.0) adapters; `family_registry.py`
  mapping `MAINTENANCE_ECONOMICS → MAINT-001-REPEATED-FAILURE`, `WORKFORCE_PRODUCTIVITY → XDOM-A`,
  `REVENUE_RECOGNITION → XDOM-B`.
- Corpus root: `Intel4Ops - AI Factory/simulation-lab/OFS/{FieldMaintenance,Rental}` — live, externally
  authored, independently generated (`intel4ops_connection: "NONE"`, `intel4ops_api_calls: 0` in every
  package's own generation report), discovered dynamically (29 → 32 packages grew during this session with
  zero code change, confirming folder-based discovery works as designed).

All 10 designated Wave 1 members were re-verified `READY`/sealed/hash-valid/independent immediately before
execution; none had changed since P3.xxV.1A registration.

---

## A. Wave 1 membership (exact, as specified — no substitutions)

| # | Simulation | Family |
|---|---|---|
| 1 | SIM-OFS-FIELDMAINT-001 | FieldMaintenance |
| 2 | SIM-OFS-FIELDMAINT-002 | FieldMaintenance |
| 3 | SIM-OFS-FIELDMAINT-005 | FieldMaintenance |
| 4 | SIM-OFS-FIELDMAINT-007 | FieldMaintenance |
| 5 | SIM-OFS-RENTAL-001 | Rental |
| 6 | SIM-OFS-RENTAL-003 | Rental |
| 7 | SIM-OFS-RENTAL-011 | Rental |
| 8 | SIM-OFS-RENTAL-012 | Rental |
| 9 | SIM-OFS-RENTAL-015 | Rental |
| 10 | SIM-OFS-RENTAL-018 | Rental |

## B. Capability coverage matrix (frozen family_registry, as of the baseline SHA)

| Registered family / model | Domain(s) required | Wave 1 members it could theoretically apply to |
|---|---|---|
| `MAINT-001-REPEATED-FAILURE` (MAINTENANCE_ECONOMICS) | maintenance | all 10 (all carry MAINTENANCE_ECONOMICS-tagged truth or equivalent leakage) |
| `XDOM-A` (WORKFORCE_PRODUCTIVITY) | maintenance + operations (governed) | all 10 |
| `XDOM-B` (REVENUE_RECOGNITION) | operations + revenue (governed) | all 10 |

Only 3 detection families are registered/governed at all. The Simulation Factory's actual injected leakage
taxonomy spans at least 12 distinct `scenario_id` values across the wave (see Section P) — most of which
have **no corresponding registered family**, regardless of activation outcome. This is a coverage-matrix
fact, established before any run, not a result of the runs.

## C. Execution summary — operability

10/10 simulations executed to terminal state. 0 infrastructure failures. 0 retries needed. 0 operator
interventions of any kind beyond invoking existing, unmodified APIs (create case → upload customer-data →
trigger run → poll to terminal → register `ValidationSimulation` → upload ground truth → validate-run).
Concurrency was 1 (sequential) throughout, per instruction.

| Simulation | case_id | run_id | val_sim_id | TP | FP | FN |
|---|---|---|---|---|---|---|
| FIELDMAINT-001 | `abbde023-9840-4f46-bd18-abf2e1b1a9cb` | `7c90f24f-f027-4d37-b39f-2c741dff1be8` | `02b2fa30-34bb-42e9-83fd-cf6a7cc4a6da` | 0 | 0 | 63 |
| FIELDMAINT-002 | `8e3498da-12c9-4ee3-b494-427473c649da` | `7d954722-b996-4c09-ace5-70bb5de4abff` | `d23745a6-4d99-4f94-a649-7e7726c2fc80` | 0 | 0 | 114 |
| FIELDMAINT-005 | `52c48f76-0a6f-4ea6-b15e-b89408fa2a07` | `fdc18f00-2f3a-4def-acc6-46b4409cc7cd` | `cc4507f0-5097-486c-a1b8-a24361deb024` | 0 | 0 | 387 |
| FIELDMAINT-007 | `090c44fc-52c7-4e3c-acb1-e716111b85a1` | `9c9df89d-3ef1-41f2-b36c-a9b1e392a0f2` | `77d0a68f-37cf-49c0-8e71-e6ae8958ffa1` | 0 | 0 | 65 |
| RENTAL-001 | `f3aba1ea-31f7-43d5-9d85-b688c095a97b` | `a4db7a86-4f31-4508-825d-9ffef435b4f9` | `ea6dfc93-f013-47bd-ac95-c55b94acd763` | 0 | 0 | 16 |
| RENTAL-003 | `2ac17773-fa2b-4c01-9d4b-00e6316f4078` | `badb5144-6970-45f8-8ab5-d70e6314873e` | `ed6d575b-d45e-4ffe-9438-a5791b1e8b77` | 0 | 0 | 9 |
| RENTAL-011 | `39af3b18-d003-496a-a27a-7622be1fdb08` | `ed9b5430-f8e0-4230-8118-b8fe68b52d12` | `b390881e-08f5-4fd5-83a4-cfe22c41acd2` | 0 | 0 | 15 |
| RENTAL-012 | `a5ad3614-c9c2-4fcf-99d5-bb9215d3da44` | `3ac02364-fed5-4d0c-971a-a3b17046d734` | `f0b9e0df-8242-4afb-8bfe-c86f0109dde4` | 0 | 0 | 46 |
| RENTAL-015 | `7f97e984-952f-411e-9604-284c96cc6185` | `93ae1f74-081a-40d6-bc41-c88650e4a1d0` | `8c58f261-3087-41cf-9244-095609a6962f` | 0 | 0 | 52 |
| RENTAL-018 | `86dafa2e-5ef5-4927-80ef-da9b90ab854a` | `af20a1cc-756e-4a00-afce-3446d3dbfac9` | `9d3b2478-ce32-46a1-8854-3b111005b9f7` | 0 | 0 | 21 |
| **Total** | | | | **0** | **0** | **788** |

## D. Operator Intervention Log (all 10 simulations)

For every simulation in the table above: `changed_intelligence_result = FALSE`,
`PRODUCT_GAP_INTERVENTION_ATTEMPTED = FALSE`. No manual mapping, joining, entity activation, threshold
change, finding injection, or result alteration occurred at any point. The only direct-DB reads performed
were the two read-backs in Section N (RENTAL-011 ground truth, engineering diagnosis only, no writes) —
recorded here per instruction; they do not count toward or against zero-intervention operation.

## E. Full-truth effectiveness (wave level)

Recall = 0/788 = **0.0%**. Precision is undefined (0 findings published by Intelligence across all 10 runs).
This is the headline result and it is uniform — not concentrated in one family or one simulation.

## F. Capability-scoped effectiveness (wave level)

Scoping to only the 3 registered families (MAINT-001, XDOM-A, XDOM-B) does not change the result: recall
is still 0/788. The capability-scoped view exists to separate "Intelligence didn't have a model for this"
from "Intelligence had a model and it still missed" — Section G shows both failure modes are present, so
even the narrower, capability-scoped denominator does not produce a nonzero recall.

## G. Model activation correctness (this IS where the two failure modes fork)

Confirmed via the `activation-decisions` API (`governed_status`, `legacy_activated`, `agree`,
`governed_missing_summary`) for all 10 simulations:

| Family | XDOM-A | XDOM-B |
|---|---|---|
| FieldMaintenance (4/4) | **BLOCKED**, all 4 — missing `domain:maintenance`, `field:downtime_hours`, `trust:maintenance` | **READY, executed** in 3/4 (001, 002, 007); **BLOCKED** in 005 — missing `trust:operations` only |
| Rental (6/6) | **BLOCKED**, all 6 — missing `domain:operations`, `field:operational_event_id`, `legacy_entity:operational_event` | **BLOCKED**, all 6 — same three plus `trust:operations` |

`agree=true` and `legacy_activated` match the governed decision in every single case — the governed
activation gate is not the cause of any of this; it faithfully reproduces what the pre-existing legacy
condition would have done. This wave surfaces no activation-gate regression.

**MAINT-001 is not observable through this endpoint** (`activation-decisions` only tracks the two
"migrated"/governed rules, XDOM-A and XDOM-B). Whether MAINT-001 activated on any of the 10 cases could not
be confirmed operator-side; flagged as an operability/observability gap in Section T, not assumed either
way.

Two distinct failure modes are now evidenced:
1. **Never activates** (XDOM-A on all 10; XDOM-B on 6 Rental + 1 FieldMaintenance) — the failure is upstream
   of the rule, in domain detection / entity typing / trust (Section H).
2. **Activates, finds nothing** (XDOM-B on 3 FieldMaintenance cases: 001, 002, 007) — the failure is in the
   rule's own detection logic not matching the corpus's actual leakage shapes (Section I).

## H. Root cause — activation layer (earliest reusable failure point)

Traced via each dataset's `detected_domain` (per-file, `analysis-cases/{id}/datasets`) against the
`governed_missing_summary` each BLOCKED decision reported:

- **FieldMaintenance's `maintenance_events.csv`-equivalent dataset is classified `domain:operations`, never
  `domain:maintenance`**, uniformly across all 4 FieldMaintenance sims (confirmed directly on
  FIELDMAINT-001; the identical per-file domain distribution — `asset_master:1, operations:5, revenue:2,
  null:4` — repeats byte-for-byte across 002/007, and 005 differs only in trust, not domain). This alone
  fully explains XDOM-A's 4/4 BLOCKED: the domain-detection layer (Semantic, P3.xxE.1) never produces the
  label the rule requires, regardless of what the rule's own logic could do downstream.
- **Rental data never produces a `domain:operations`-classified dataset at all**, and never produces an
  `operational_event`-typed canonical entity (`legacy_entity:operational_event` missing on every Rental
  BLOCKED decision, all 6/6). This is the single root cause behind both XDOM-A and XDOM-B being BLOCKED on
  100% of Rental simulations — a domain-detection and entity-typing gap, not a rule-logic gap, and it sits
  one layer earlier (Semantic + Entity Resolution, P3.xxE.1/E.3) than either rule.
- **Trust is the differentiator for FIELDMAINT-005 specifically**: identical domain distribution to
  001/002/007, but `trust:operations` was never established, blocking XDOM-B where it otherwise would have
  run. FIELDMAINT-005 is also the largest single dataset in the wave (387 expected findings vs. 63–114 for
  the other three) — worth a targeted look at whether trust scoring degrades with scale/density, but that
  is a hypothesis for engineering to confirm, not something this operator role is positioned to establish.

**Attribution: the earliest reusable failure layer for 9 of 10 simulations (all except the 3 FieldMaintenance
cases where XDOM-B activated) is Semantic domain detection, not Intelligence.** Fixing domain detection to
recognize FieldMaintenance's operational dataset as `maintenance` (or broadening XDOM-A's requirement) and
to recognize Rental's operational dataset as `operations` at all would change activation outcomes for 9/10
simulations — though, per Section I, would not by itself produce nonzero recall, since even successful
activation found zero true positives in this wave.

## I. Root cause — rule-logic / leakage-taxonomy mismatch (the deeper finding)

Where XDOM-B did activate (FIELDMAINT-001, 002, 007) it still found nothing. Cross-referencing the wave's
actual injected `scenario_id` taxonomy (pulled from each package's own `leakage_truth`, not authored by the
operator) against XDOM-B's known detection pattern ("lost activity with no corresponding revenue record")
shows why:

**FieldMaintenance scenario_id distribution (629 expected findings, 4 sims):**

| scenario_id | count | conceptually near XDOM-B's pattern? |
|---|---|---|
| overtime_leakage | 301 | no — a labor-cost pattern, not a missing-revenue-record pattern |
| unbilled_parts | 113 | partially — closest match, still zero detections |
| repeat_repair | 76 | no — this is MAINT-001's own territory (repeated failure), not XDOM-B's |
| unbilled_labor_hours | 32 | partially — closest match, still zero detections |
| preventive_maintenance_missed | 51 | no |
| technician_idle_time | 23 | no |
| contract_rate_mismatch | 26 | no — a rate-discrepancy pattern, not a missing-record pattern |
| missing_field_ticket_billing | 7 | partially — closest match, still zero detections |

At most ~152/629 (24%) of FieldMaintenance's injected leakage is even conceptually adjacent to what XDOM-B
looks for, and XDOM-B still found 0 of those. **This means the gap is not solely "wrong data shape" — even
on the subset of leakage that most resembles XDOM-B's intended pattern, the rule's specific matching logic
(likely exact-join/threshold conditions on particular column names) does not fire.** This is a rule-logic
defect distinct from and downstream of the activation-layer defect in Section H, and it is the
correct-scope explanation for why capability-scoped recall is still 0% even where the capability-scoped
gate opened.

**Rental scenario_id distribution (159 expected findings, 6 sims):** `excessive_asset_downtime`(44),
`late_maintenance`(26), `rental_rate_mismatch`(22), `delayed_invoicing`(21), `late_return_leakage`(12),
`unbilled_rental_days`(2), `fuel_discrepancy`(7), plus 25 records with no `scenario_id` recorded at all
(see Section N). None of these is registered to any of the 3 governed families at all — Rental's entire
injected taxonomy sits outside current product coverage, independent of the activation-layer finding in
Section H.

## J. Value / financial effectiveness

Total expected leakage value in the wave (`true_leakage_value`, summed from each package's own
`leakage_truth`, independently authored):

| Family | Expected findings | Expected value |
|---|---|---|
| FieldMaintenance | 629 | $413,414.73 |
| Rental | 159 | $1,872,323.83 |
| **Wave total** | **788** | **$2,285,738.56** |

Value recall = $0 / $2,285,738.56 = **0.0%**, matching count-based recall exactly (TP=0 everywhere, so there
is no partial-value case to distinguish). No currency field was present in either family's `leakage_truth`
schema, so a by-currency breakdown is not obtainable from this corpus as authored (flagged as a validation
authoring gap in Section N, not assumed to be USD).

## K. Semantic / entity / relationship / process performance (spot-checked, FIELDMAINT-001)

Semantic and entity-resolution outputs are substantial and non-trivial despite the zero-finding result —
the failure is not upstream of these layers in any blanket sense: the `semantic` endpoint returned a
74KB decision payload and the `entities` endpoint returned a 174KB canonical-entity payload for
FIELDMAINT-001's single run. This confirms Semantic Interpretation and Entity Resolution are actively
producing substantial structured output; the specific defect is the narrower domain-label and
trust-establishment gaps identified in Section H, not a wholesale breakdown of the understanding layers.
Process interpretation (P3.xxE.4) and relationship discovery were not independently spot-checked this wave
— out of scope for what activation-decisions and the domain/entity endpoints already explained.

## L. Model activation correctness — governed-gate integrity check

Every BLOCKED/READY decision observed had `agree=true` between the shadow-derived legacy condition and the
governed decision. **The P3.xxE.5 GOVERNED activation gate introduced zero new false-BLOCKED or
false-READY outcomes in this wave** — every blocked or activated outcome matches what the pre-existing
legacy logic would independently have done. This is a clean bill of health for the E.5 activation
infrastructure specifically, distinct from (and not an excuse for) the domain-detection and rule-logic
findings above.

## M. Defect clustering

| Cluster | Simulations affected | Layer | Severity |
|---|---|---|---|
| 1. FieldMaintenance operational dataset never classified `domain:maintenance` | 4/4 FieldMaintenance | Semantic (domain detection) | HIGH |
| 2. Rental operational dataset never classified `domain:operations`; no `operational_event` entity type ever produced | 6/6 Rental | Semantic + Entity Resolution | HIGH |
| 3. `trust:operations` not established despite correct domain classification | 1/4 FieldMaintenance (005) | Trust | MEDIUM |
| 4. XDOM-B activates but 0/152 conceptually-adjacent findings detected | 3/4 FieldMaintenance (001, 002, 007) | Intelligence (XDOM-B rule logic) | HIGH |
| 5. No registered detection family for 6/8 distinct injected scenario types across the wave | all 10 | Product coverage / capability registry | HIGH |
| 6. `expected_detection_family` absent from 100% of Rental truth records (159/159) | 6/6 Rental | Validation truth authoring (external, Simulation Factory side) | MEDIUM — affects reporting fidelity, not production |
| 7. MAINT-001 activation status not observable via any operator-accessible API | all 10 | Operability / observability | LOW–MEDIUM |

Clusters 1, 2, and 4 are the systemic, high-confidence findings; cluster 3 needs one more data point
(engineering should check trust scoring on a second large FieldMaintenance case) before being called
systemic rather than case-specific.

## N. Validation / truth quality issues (kept separate from production capability gaps, per instruction)

- **Rental `leakage_truth` records never carry `expected_detection_family`** — confirmed by direct
  inspection of the source truth files (not an adapter parsing bug): 0/159 Rental leakage records include
  this key at all, vs. 629/629 (100%) for FieldMaintenance. Read back live via
  `GET .../validation/simulations/{id}`, RENTAL-011: `expected_detection_family: null`, `currency: null`,
  `entities: []`, while `expected_economic_impact: 8400` (mapped from the shared `expected_value`/
  `true_leakage_value` field, which both families do populate) came through correctly. This is a Simulation
  Factory authoring completeness gap on the Rental side, not a bug in `SimulationTruthV1Adapter` — the
  adapter faithfully reports what isn't there.
- **25 Rental leakage records (of 159) carry no `scenario_id` at all** ("MISSING" in Section I's
  distribution) — a second, distinct authoring-completeness gap on the same family.
- **No `currency` field exists in either family's `leakage_truth` schema** — the wave's $2.29M expected-value
  total in Section J should not be assumed to be a single currency without confirming with the Simulation
  Factory's authoring conventions.
- These three items reduce the precision of capability-scoped and value-based reporting for Rental
  specifically; they do not change the wave's headline 0% recall result (Section E), since TP=0 regardless
  of how complete the truth metadata is.

## O. Infrastructure issues

None. Zero run failures, zero timeouts, zero corpus integrity failures, zero checksum mismatches across all
10 registrations and validations. The one operational friction encountered was tooling-side (browser
upload-path allowlisting, bearer-token refresh cadence) and is already resolved procedurally — it is not a
defect in the application under test and is not included in the defect clusters above.

## P. Product / capability coverage gaps

The Simulation Factory's actual injected leakage taxonomy across this wave spans at least 15 distinct
`scenario_id` values (8 FieldMaintenance + 7 Rental, excluding the 25 unlabeled Rental records). Only 3
detection families are registered in `family_registry.py` at all (MAINT-001, XDOM-A, XDOM-B), and — per
Section I — even those 3 do not reliably fire on the scenario types most conceptually adjacent to them.
This is the single largest structural fact this wave surfaces: **the registered capability surface is
narrow relative to the corpus's real-world leakage variety**, independent of any bug. `unbilled_parts`,
`unbilled_labor_hours`, `overtime_leakage`, `contract_rate_mismatch`, `technician_idle_time`,
`preventive_maintenance_missed`, `excessive_asset_downtime`, `rental_rate_mismatch`, `delayed_invoicing`,
`late_return_leakage`, `unbilled_rental_days`, and `fuel_discrepancy` have no registered detection family at
all today.

## Q. Validation Lab frontend requirements (discovered, ranked)

An existing `/operator/validation` nav link was found in the Navigator sidebar during wave execution but was
not opened or exercised (out of scope for this wave — noted here as a concrete existing-frontend data point
only). Based on the manual, browser-scripted operator workflow actually required to run this wave, ranked
requirements for a real Validation Lab UI:

- **P0** — Corpus browser (list discovered packages with `package_status`, family, seal/hash state) so an
  operator doesn't need direct API calls to confirm a package is `READY`.
  **P0** — One-click "register + run + validate" per simulation, replacing the ~7-call manual API sequence
  used throughout this wave.
  **P0** — A results table shaped like Section C (TP/FP/FN per simulation, sortable/filterable by family) —
  this exact table was hand-assembled from scattered API calls in this session.
- **P1** — Activation-decision viewer showing `governed_status`/`missing_summary`/`legacy_activated`/`agree`
  per rule per case, without needing to know the raw endpoint shape — this was the single most-repeated
  manual query pattern in this wave (Sections G–H).
  **P1** — A capability-coverage view cross-referencing registered families against the corpus's actual
  `scenario_id`/`expected_detection_family` distribution (Section P) — would have surfaced this wave's
  biggest finding without any run being executed at all.
- **P2** — Truth-quality linting on corpus registration (flag packages missing `expected_detection_family`,
  `scenario_id`, or `currency` before they're used in a wave) — would have caught Section N automatically.
  **P2** — Bearer-token/session handling suited to long-running operator sessions (this wave hit expired
  tokens multiple times, requiring manual re-authentication via page reload).

## R. Prioritized remediation backlog (recommendation only — not performed this wave)

1. Fix FieldMaintenance domain detection to classify the operational dataset as `maintenance` (or relax
   XDOM-A's `domain:maintenance` requirement if `operations` is an acceptable substitute) — unblocks XDOM-A
   on all 4 FieldMaintenance sims.
2. Investigate why no Rental dataset is ever classified `domain:operations` and why no
   `operational_event`-typed entity is ever produced from Rental data — unblocks both XDOM-A and XDOM-B on
   all 6 Rental sims.
3. Investigate FIELDMAINT-005's `trust:operations` gap specifically — confirm whether it's scale-sensitive
   before generalizing.
4. Re-examine XDOM-B's detection logic against `unbilled_parts`/`unbilled_labor_hours`/
   `missing_field_ticket_billing` (the 152 conceptually-closest FieldMaintenance findings) — it activated on
   3 cases carrying this leakage and still found none.
5. Expand the registered capability surface (new detection families or broadened existing ones) to cover
   the 12 currently-unregistered scenario types identified in Section P — the largest lever for improving
   wave-level recall, but also the largest scope item; needs its own milestone, not a quick fix.
6. Ask the Simulation Factory to backfill `expected_detection_family` and `scenario_id` on the 159 Rental /
   25-unlabeled leakage records (Section N) — improves future wave reporting fidelity, does not block
   production remediation.
7. Add a MAINT-001-specific activation-visibility endpoint or extend `activation-decisions` to cover
   non-governed/legacy-only rules (Section G's observability gap).

## S. Family-level aggregates

| | FieldMaintenance (4 sims) | Rental (6 sims) |
|---|---|---|
| Expected findings | 629 | 159 |
| Expected value | $413,414.73 | $1,872,323.83 |
| TP / FP | 0 / 0 | 0 / 0 |
| Recall | 0.0% | 0.0% |
| XDOM-A | BLOCKED 4/4 (domain gap) | BLOCKED 6/6 (domain + entity gap) |
| XDOM-B | READY 3/4, BLOCKED 1/4 (trust gap) | BLOCKED 6/6 (domain + entity gap) |
| Distinct unregistered scenario types | 8 | 7 (+25 unlabeled) |

## T. Operability metrics

- Wave execution time: single operator session, sequential (concurrency=1), 10/10 completed.
- Infrastructure failures: 0. Retries needed: 0. Manual interventions beyond standard API use: 0.
- Known observability gap: MAINT-001 activation status not retrievable via any endpoint used this wave
  (Section G).

## U. Root-cause distribution summary

Of 10 simulations: **9/10** have their earliest reusable failure in Semantic domain detection / Entity
Resolution (never activates). **3/10** (FIELDMAINT-001, 002, 007) additionally exercise a second, deeper
failure in Intelligence rule-matching logic once activation succeeds. **1/10** (FIELDMAINT-005) has its
earliest failure in Trust specifically rather than domain detection. **0/10** show any defect in the
P3.xxE.5 governed-activation gate itself (Section L). **10/10** are additionally bounded by a product
coverage ceiling (Section P) that no activation or rule fix alone would fully close.

## V. Severity classification

No finding this wave meets CRITICAL (no tenant-isolation breach, no fabricated evidence, no corrupted
scoring, no unsafe cross-currency aggregation, no simulation-specific code path, no hidden-truth leakage
into production interpretation — all checked). Clusters 1, 2, 4, and 5 (Section M) are HIGH: they are
systemic, reproduce across every simulation in their affected family, and together fully explain the wave's
0% recall. Cluster 3 is MEDIUM pending a second confirming data point. Clusters 6 and 7 are
MEDIUM/LOW — they affect reporting fidelity and operability, not production correctness.

## W. What this wave does NOT establish

This wave does not establish that Intelligence's existing 3 registered detection families are broadly
broken — only that, on this specific 10-simulation sample, activation-layer gaps prevented most attempts
outright, and where activation succeeded, the specific leakage shapes present in this sample didn't match.
A future wave against simulations engineered to isolate the rule-logic question alone (post activation-layer
fix) would be needed to characterize XDOM-B's true detection accuracy independent of the domain-detection
confound identified here.

## X. Compliance confirmation

- No production intelligence, thresholds, semantic/entity/relationship/process outputs were modified.
- No manual mapping, joining, entity activation, or finding injection occurred.
- No hidden truth was used to decide interpretation before scoring; ground truth was only read back after
  terminal state for validation and for this report's diagnostic sections (H, I, N), consistent with the
  Validation Plane's one-way dependency rule.
- No simulation was rerun after inspecting its own truth.
- No remediation, threshold tuning, or model addition was performed.
- Wave 2, E.6/E.7, frontend implementation, and infrastructure redesign were not started.

## Y. Wave 1 decision

**READY FOR SYSTEMIC REMEDIATION**

Rationale: every finding this wave produced is structural, reproducible, and traceable to a specific,
narrow layer (domain detection, entity typing, trust establishment, one rule's matching logic, and the
registered-capability surface) — none is a validation-infrastructure defect, none is an activation-gate
regression (Section L), and none is a safety/isolation failure (Section V). The wave's own machinery
(discovery, registration, execution, scoring, isolation) performed correctly throughout with zero
infrastructure failures. The path forward is fixing the specific, evidenced product gaps in Section R, not
fixing the validation system itself.
