# P3.xxI.5B-R Semantic Relation Reconciliation

## Scope and status

**Work package:** P3.xxI.5B-R failure reconciliation, then an
owner-authorized foundation-only implementation  
**Merged implementation (P3.xxI.5B):** `f9d1d9455c8a7ff3624c2533a4adf1aae5a6c055`  
**Accepted certification:** P3.xxI.5B FAILED (`TP / FP / FN = 0 / 0 / 76`)  
**Certification PR:** #126, head `48cbf1d9dac63bed74d4d58d68b1cfc8f88a3325`  
**Foundation implementation:** merged in PR #127, merge commit
`ce843257915e52c4e2badf700271d857cf5a19c0` (see the "P3.xxI.5B-R FOUNDATION
IMPLEMENTATION" section)  
**Post-merge live certification:** complete -- **P3.xxI.5B-R PARTIALLY
VALIDATED** (foundation fix VALIDATED; capability effectiveness NOT
VALIDATED, unchanged `0/0/76`; see the "P3.xxI.5B-R POST-MERGE
CERTIFICATION" section)

This diagnosis reused the four terminal production runs and their persisted
findings. It did not restart certification, create cases, or inspect hidden
truth before production was terminal. Hidden truth was used only for the
examiner-side denominator trace and counterfactual scoring below. No
application code, truth, simulation, migration, MAINT-001, XDOM-A, XDOM-B,
Revenue Amount, or frontend artifact was changed by this diagnosis. The
subsequent, separately owner-authorized implementation (final section of
this document) did change two application files -- scope and verification
detailed there.

## Executive determination

Continuing directly from Codex's diagnosis (verified below, not repeated from
scratch): the zero-result has two distinct, independently-confirmed causes,
and this pass adds a precise root cause for the first one plus a check of
whether existing canonical-relationship infrastructure already solves it.

1. **The immediate production stop is a governance-acceptance blocker with a
   precise, generalizable root cause: a dataset-role classification defect,
   not identifier duplication or FK ambiguity.** Direct instrumentation of
   the merged pipeline against the real `FIELDMAINT-002` corpus (Section 6)
   shows `maintenance_events.csv`'s `work_order_id` is populated,
   100%-unique within its own dataset, and unambiguous -- it fails to reach
   `AUTO_ACCEPTED` for exactly one reason: `app/semantic/role_classifier.py`
   classifies `maintenance_events.csv` as `SCHEDULE`-shaped (because it has a
   `scheduled_date` field and no currency field) rather than `EVENT`-shaped,
   and the `EVENT` role is coded to be scored only when `not scores` --
   i.e. only when literally no other role matched. Because `SCHEDULE`
   matched first, `EVENT` is never even considered as a candidate for this
   dataset, `work_order_id` loses the one `DATASET_ROLE_COMPATIBILITY`
   evidence point it needs, and its confidence caps at exactly 0.85 instead
   of >=0.95. This is the same class of gap already fixed twice this program
   (P3.xxI.2C's identifier bridge, P3.xxI.5A-R's `allow_bridge`/
   `duration_hours` fixes): a real, reusable, generalizable code defect, not
   a data-contract gap, and not the customer's fault.
2. **Existing canonical-relationship infrastructure does not already solve
   this.** E.3's `CanonicalCaseRelationship` table is not empty on this
   corpus (1,065 rows for this one case, contradicting an earlier, now-stale
   `P3.xxE.4` planning-time measurement of 0 corpus-wide -- superseded by
   this fresh count, not still true) -- but every one of those rows is a
   `BELONGS_TO` edge between two *different* entity types
   (`ASSET<->WORK_ORDER` at 0.97 confidence, `PERSON<->WORK_ORDER`,
   `CONTRACT<->WORK_ORDER`). Zero `WORK_ORDER<->WORK_ORDER` relationships
   exist. There is no existing same-type sequence/precedence/rework edge
   anywhere in the platform to borrow -- that capability does not exist yet
   (it is P3.xxE.4's still-unbuilt job, currently in planning, not a solved
   problem this milestone is failing to consume correctly).
3. **Clearing the identity stop would not make the capability safe.** The
   corpus has no governed failure code, component relationship, repair type,
   service type, callback/rework marker, semantic parent/child relation, or
   repeat-policy window. Its only governed activity descriptor is the
   two-value `CM`/`PM` field. Exact-category adjacency would produce 1,121
   candidates, only 36 of which match the 76 truth items; 1,085 are non-truth
   pairs. Fixing #1 changes the production outcome from "zero candidates" to
   "up to 1,121 candidates, 3.21% precision" -- it does not change the
   outcome from unsafe to safe.

**Conclusion for the core question (Section 4 of the mission): this is a
combination, with a now-precise split.** The immediate 0/76 is a
`CAPABILITY_MODEL_GAP` (a role-classification ordering defect, fixable,
reusable, and already demonstrated to exist elsewhere via the same class of
bridge/parity fix). The inability to safely discriminate rework from
ordinary maintenance for any of the 76 items is a `DATA_CONTRACT_GAP` that
persists regardless of #1. Fixing #1 alone is real, correct engineering work
with zero recall benefit on this corpus; it converts safe abstention into an
execution path that must itself still abstain (or be blocked) for lack of
relation evidence.

## Current mechanical contract and exact production stop

The registered pack requires maintenance evidence, canonical ASSET identity,
an operational-event/intervention identifier, activity category, a completed
or event timestamp, resolved maintenance Trust, and complete evidence. The
execution path is stricter and dataset-local: one maintenance dataset must
provide authoritative `asset_id`, `work_order_id`, timestamp, and
`activity_category` fields before it can enter pairing.

The pairing service then deduplicates `(asset, intervention)`, groups by
`(asset, normalized activity category)`, rejects conflicting representations
or tied ordering, and emits only adjacent pairs. It reports an observed
interval and does not assert a policy violation or economic exposure.

The representative `FIELDMAINT-002` trace, reproduced from the exact frozen
customer files without truth access, is:

| Evidence | Production result |
|---|---|
| Eligible canonical ASSET subjects | 60 |
| `maintenance_events.asset_id -> asset_id` | `auto_accepted`, 0.98 |
| `maintenance_events.event_type -> activity_category` | `auto_accepted`, 0.95 |
| `maintenance_events.completed_date -> completed_timestamp` | `auto_accepted`, 0.98 |
| `maintenance_events.work_order_id -> work_order_id` | `accepted_with_flag`, 0.85 |
| `maintenance_events.event_id` | unresolved |
| Candidate datasets | 0 |
| Candidate pairs | 0 |
| Published findings | 0 |
| Activation decision in controlled replay | READY |

`resolve_effective_decision` authorizes a machine interpretation only when it
is `auto_accepted` (or when a human governance decision supplies authority).
It deliberately does not promote `accepted_with_flag`. The execution behavior
is therefore correct under the existing semantic-authority policy; the defect
is that readiness and execution do not prove the same dataset-local evidence.

The registry also names `operational_event_id`, while execution asks for
`work_order_id`. That split, plus structural readiness versus effective
semantic authority, explains READY with `candidate_dataset_count = 0`.

## work_order_id governance diagnosis (precise mechanism)

This section replaces speculation with direct instrumentation of the merged
pipeline (`app/services/analysis_case_orchestration_service.execute()`)
against the real `SIM-OFS-FIELDMAINT-002` corpus, reading the persisted
`SemanticInterpretationDecision` rows rather than re-deriving numbers by
hand. Every `work_order_id` decision across all six eligible datasets in the
case:

| Dataset (by evidence content) | Confidence | Status | Missing evidence vs. the 0.98 rows |
|---|---:|---|---|
| `labor_entries.csv` | 0.98 | `auto_accepted` | -- |
| `work_orders.csv` | 0.98 | `auto_accepted` | -- |
| `field_tickets.csv` | 0.98 | `auto_accepted` | -- |
| `maintenance_events.csv` | **0.85** | **`accepted_with_flag`** | `dataset_role_compatibility` (worth +0.15) |
| `parts_usage.csv` | 0.98 | `auto_accepted` | -- |
| (a sixth work-order-shaped dataset) | 0.98 | `auto_accepted` | -- |

`maintenance_events.csv`'s own evidence trail, verbatim from the persisted
decision:

```
"source field 'work_order_id' matches a known alias of 'work_order_id'"
"physical type 'object' is compatible with concept type 'identifier'"
"co-occurs with sibling field(s) recognized as activity_category, asset_id,
  compatible with 'work_order_id''s role context"
"identifier-like values overlap with field_tickets.csv.ticket_id, which
  independently aliases to 'work_order_id'"
```

Every other dataset's decision additionally carries a
`"dataset role '<role>' is compatible with 'work_order_id'"` line (roles seen:
`labor`, `work_order`, `inventory`). `maintenance_events.csv` is the only one
missing this line. `work_order_id`'s registered `compatible_dataset_roles`
are `{transaction, labor, event, inventory, invoice, work_order}`.

**Root cause, confirmed by direct profiling of the real file
(`SIM-OFS-FIELDMAINT-002/customer-data/maintenance_events.csv`):**

- `work_order_id` on this dataset is **100% unique within the case**
  (`row_count == distinct_count == 254`, `uniqueness_ratio = 1.0`). It is not
  a repeated/duplicated identifier and not a foreign-key-shaped column here
  -- `is_candidate_identifier = True`, `is_candidate_reference_identifier =
  False`. Duplicate/repeated-ID ambiguity is **ruled out** as a cause.
- `app/semantic/role_classifier.py`'s `_score_roles` scores
  `maintenance_events.csv` as `SCHEDULE` (0.55 confidence) because it has a
  `scheduled_date` field and no currency-like field (lines 145-155). The
  `EVENT` role -- which *is* in `work_order_id`'s compatible-role set -- is
  gated by `if profile.is_append_or_event_like and not scores:` (line 204):
  it is only even proposed when **no other role scored anything at all**.
  Because `SCHEDULE` already added an entry to `scores`, `EVENT` is never
  evaluated for this dataset, regardless of how event-shaped it actually is
  (it has its own `event_id`, `asset_id`, `work_order_id`,
  `completed_date` -- an intervention-record shape, not a forward-looking
  schedule).
  This is a **role-semantics ordering defect**, not an identity, FK, or
  entity-type-ambiguity problem: the field's identity is unambiguous; only
  its *dataset's* structural-role label is wrong, and that label is wrong
  because of unconditional rule precedence, not because the evidence
  genuinely favors `SCHEDULE` over `EVENT`.
- This single missing `DATASET_ROLE_COMPATIBILITY` component (+0.15) is
  exactly the gap between 0.85 (`accepted_with_flag`) and 0.95-0.98
  (`auto_accepted`) that every sibling dataset clears.

**Answers to the specific sub-questions:**

- *Why is it flagged?* A dataset-role misclassification (`SCHEDULE` instead
  of `EVENT`) caused by unconditional rule-evaluation order in
  `_score_roles`, not by the field's own data quality.
- *Duplicate/repeated IDs?* No -- ruled out; the field is 100% unique
  within the dataset.
- *Role semantics?* Yes -- this is precisely a dataset-role
  misclassification.
- *FK ambiguity?* No -- the field resolves as a primary-shaped identifier
  on this dataset, not a reference/FK shape.
- *Entity-type ambiguity?* No -- `work_order_id` is the only concept this
  field competes for; there is no close second candidate in the persisted
  `alternative_candidates` (empty).
- *Does existing canonical-relationship evidence already solve this?* No --
  see the next section. The relevant existing infrastructure (canonical
  entity/relationship resolution) does not supply a substitute authoritative
  `work_order_id` for this dataset's own rows; it supplies a different,
  already-healthy signal (asset-to-work-order structural linkage) that does
  not address the missing intervention identifier.
- *Would promoting its use be safe?* Fixing the role-classifier ordering
  defect (or adding this dataset to the P3.xxI.2C-style bridge path used by
  Revenue Variance and Contract/Rate Compliance) would be a safe, correct,
  reusable fix **for the identity/governance problem specifically** -- it
  would not misattribute or fabricate any identity. But it would not by
  itself make *publishing* a repeat/rework finding safe, because the
  downstream relation-evidence wall (Sections 8-9 below) is independent and
  unaffected by this fix.
- *Does the existing role-aware ID/FK architecture from prior fixes already
  solve part of this, but P3.xxI.5B isn't consuming it correctly?* **Partly
  yes.** The reusable one-hop identifier bridge
  (`_resolve_identifier_bridge_map` / `_resolve_subject_field_for_dataset`,
  used successfully by Revenue Variance and Contract/Rate Compliance) is
  never called by the `MAINTENANCE-REPEAT-VISIT` orchestration wiring --
  that wiring calls only the strict, non-bridging
  `_resolve_canonical_concept_field` for `asset_id`, `work_order_id`,
  timestamp, and `activity_category` (`analysis_case_orchestration_service.py`,
  the "P3.xxI.5B" block). `work_orders.csv`'s own `work_order_id` is already
  `auto_accepted` at 0.98 -- exactly the kind of already-governed,
  already-authoritative cross-dataset evidence the bridge mechanism exists
  to surface for a dataset whose own local field is flagged. This is a real,
  reusable architecture gap in how P3.xxI.5B was wired, independent of the
  role-classifier defect above.

## Existing canonical relationship analysis

Direct inspection of `CanonicalCaseEntity` / `CanonicalCaseRelationship` for
the same `FIELDMAINT-002` run (not the stale, pre-remediation `P3.xxE.4`
planning-time baseline, which is superseded below):

| Entity type | Count |
|---|---:|
| WORK_ORDER | 497 |
| ASSET | 67 |
| CONTRACT | 40 |
| CUSTOMER | 40 |
| PERSON | 15 |

| Relationship (entity-type pair) | Count | `relationship_type` | Confidence |
|---|---:|---|---:|
| ASSET <-> WORK_ORDER | 254 | `BELONGS_TO` | 0.97 |
| PERSON <-> WORK_ORDER | 497 | `BELONGS_TO` | ~0.97 |
| CONTRACT <-> WORK_ORDER | 254 | `BELONGS_TO` | ~0.97 |
| ASSET <-> CONTRACT | 60 | `BELONGS_TO` | ~0.97 |
| **WORK_ORDER <-> WORK_ORDER** | **0** | -- | -- |

**Correction to this program's own prior planning record:** the `P3.xxE.4`
plan's baseline measurement ("`CanonicalCaseRelationship` rows: 0,
corpus-wide") is stale and superseded by this fresh count. It should not be
relied on going forward; whatever produced that reading either predates
later entity-resolution fixes or measured a different scope. This is exactly
why the mission's own instruction to verify rather than trust cached
findings matters here.

**Answering the mission's question directly: can repeat/rework relatedness
be derived from an existing canonical relationship rather than a raw-field
equality test?**

- **For subject/grouping identity (which work orders belong to which
  asset): partially, yes.** A governed, high-confidence (`0.97`)
  `BELONGS_TO` edge already links each `WORK_ORDER` to its `ASSET`. This
  was not, however, the actual blocker -- `maintenance_events.asset_id`
  already resolves `auto_accepted` at 0.98 directly, with no bridge needed.
  The `BELONGS_TO` edge is healthy, reusable evidence, but it duplicates
  evidence the pairing service already has; it does not unlock anything new.
- **For the actual blocker (an authoritative intervention/`work_order_id`
  identity on `maintenance_events.csv`): no existing relationship
  substitutes for it.** No relationship type connects
  `maintenance_events.csv` rows to `work_orders.csv` rows as an identity
  bridge; the existing P3.xxI.2C bridge mechanism (a different subsystem,
  operating on semantic decisions, not on `CanonicalCaseRelationship` rows)
  is the correct reusable tool here, not the entity/relationship layer.
- **For repeat/rework relatedness itself (is WO_1 a rework of WO_2?): no.**
  Every relationship in the corpus is `BELONGS_TO` between two *different*
  entity types. There is no `PRECEDES`, `RELATED_TO`, `REWORK_OF`, or any
  other same-type sequence/causal edge between two `WORK_ORDER` entities
  anywhere in the platform. This is not an oversight in how P3.xxI.5B reads
  existing evidence -- that evidence does not exist yet. Building it is
  exactly the stated job of the still-unimplemented `P3.xxE.4` (Operational
  Process Interpretation / Canonical Process Graph) milestone, which is
  presently in planning, not a solved capability this milestone failed to
  consume.

## Structured semantic evidence inventory

The inventory covers the four frozen FieldMaintenance customer datasets
(2,087 maintenance-event rows). Identifier uniqueness below is across files
whose case-local identifiers can repeat; it is descriptive, not a cross-case
identity claim.

| Source | Field | Population | Semantic disposition | Relation value |
|---|---|---:|---|---|
| maintenance events | `event_id` | 2,087 / 2,087 | unresolved | Explicit event identity exists but is not governed |
| maintenance events | `asset_id` | 2,087 / 2,087 | `asset_id`, auto 0.98 | Governed subject identity |
| maintenance events | `work_order_id` | 2,087 / 2,087 | `work_order_id`, flagged 0.85 | Exact join key exists; not authoritative in this dataset |
| maintenance events | `event_type` | 2,087 / 2,087 | `activity_category`, auto 0.95 | Only `CM` and `PM`; too coarse to prove rework |
| maintenance events | `scheduled_date` | 710 / 2,087 | `scheduled_timestamp`, flagged 0.80 | Sparse; not a relation descriptor |
| maintenance events | `completed_date` | 2,036 / 2,087 | `completed_timestamp`, auto 0.98 | Governed when populated |
| work orders | `work_order_id` | 2,087 / 2,087 | `work_order_id`, auto 0.98 | Authoritative join-side intervention identity |
| work orders | `asset_id` | 2,087 / 2,087 | `asset_id`, auto 0.98 | Corroborating subject identity |
| work orders | `closed_date` | 2,087 / 2,087 | `completed_timestamp`, auto 0.98 | Can fill three truth-item timestamp gaps through a governed join |
| work orders | `contract_id` | 2,087 / 2,087 | `contract_id`, auto 0.98 | Commercial scope, not maintenance relatedness |
| work orders | `status` | 2,087 / 2,087 | review required; always `CLOSED` | Non-discriminating |
| work orders | `priority` | 2,087 / 2,087 | unresolved; `ROUTINE`/`URGENT` | Urgency, not failure/service equivalence |
| parts usage | `work_order_id` | 2,116 / 2,116 | `work_order_id`, auto 0.98 | Governed join key |
| parts usage | `part_number` | 2,116 / 2,116 | unresolved | Potential component proxy, but no truth pair shares one |
| parts usage | `quantity`, `unit_price` | 2,116 / 2,116 | auto accepted | Measures, not relation descriptors |
| field tickets | `work_order_id` | 2,008 / 2,008 | `work_order_id`, auto 0.98 | Governed join key |
| field tickets | `technician_id` | 2,008 / 2,008 | auto accepted | Assignment identity, not repair equivalence |
| field tickets | `ticket_date` | 2,008 / 2,008 | unresolved | Temporal only |
| labor entries | `work_order_id`, `technician_id` | 3,150 / 3,150 | auto accepted | Join/assignment evidence only |
| labor entries | `entry_date` | 3,150 / 3,150 | `event_timestamp`, auto 0.98 | Temporal only |
| assets | `type` | 520 / 520 | unresolved; five values | Asset class, constant within an asset pair |
| assets | `site_id`, `install_date` | 520 / 520 | unresolved | Context, not repeat/rework semantics |

No customer file contains `failure_code`, `failure_category`, `repair_type`,
`service_type`, `component_id`, `subsystem_id`, `symptom`, `cause`,
`callback_of`, `rework_of`, `parent_work_order_id`, `relation_type`, a
free-text work description/technician note, or an explicit repeat/rework policy
window. Although `part_number` is present, every tested exact-component chain
has length one; it yields no adjacent component pair and reaches 0/76 truth
items.

### Free-text evidence inventory

Every field across all four frozen FieldMaintenance datasets and all twelve
customer files was profiled (Structured semantic evidence inventory table,
above, plus `assets.csv`, `customers.csv`, `technicians.csv`,
`invoices.csv`, `payments.csv`, `sites.csv`, `service_contracts.csv`). None
contains a free-text description, failure narrative, technician note,
service description, or repair comment field. This is not a "free text
exists but is unused" finding -- there is no free text anywhere in this
corpus to extract from. Consequently there is nothing to classify as
`SOURCE_ONLY_HAS_FREE_TEXT`, and no governed semantic-extraction-from-text
capability could add relation evidence for this specific dataset package.
A future governed maintenance semantic-extraction capability (Option B,
below) is still a generically reusable idea for *other* customers whose
exports do carry free text -- it is simply inapplicable to the current
frozen corpus and must not be justified using this corpus as evidence of
its value.

## All 76 truth-item traces and A-F classification

There are two necessary views of “first blocker”:

- **Literal production first blocker:** all 76 are **E — identity/temporal
  blocker**, specifically the refused flagged intervention identity. Production
  never reaches relation evaluation.
- **Downstream relation-evidence audit:** after hypothetically supplying
  authoritative identity, each item is classified below so the immediate code
  stop does not conceal the underlying data contract. This mutually exclusive
  downstream distribution is A=0, B=0, C=0, D=32, E=3, F=41.

Downstream class D means no sufficient structured relation; E means a
maintenance-event timestamp is missing (although the joined work-order close
date exists); F means the existing exact `CM`/`PM` category agrees but is too
coarse to distinguish the item from ordinary maintenance. No item has an
explicit unused semantic relation (A), a safely derivable structured relation
(B), or free-text-only relation evidence (C).

### 76-item classification against the mission's exact taxonomy

The categories above (A-F) are this document's own working labels. Mapped
onto the exact required taxonomy, with totals summing to 76 at each of the
two required layers:

**Layer 1 -- literal production-first blocker** (what actually stops
execution today, for every item, before any relation evidence is ever
evaluated):

| Category | Count |
|---|---:|
| SOURCE_HAS_EXPLICIT_SEMANTIC_EVIDENCE | 0 |
| SOURCE_HAS_DERIVABLE_STRUCTURED_EVIDENCE | 0 |
| SOURCE_ONLY_HAS_FREE_TEXT | 0 |
| SOURCE_HAS_INSUFFICIENT_EVIDENCE | 0 |
| IDENTITY_OR_TEMPORAL_BLOCKER | 0 |
| **GOVERNANCE_ACCEPTANCE_BLOCKER** | **76** |
| OTHER | 0 |
| **Total** | **76** |

All 76 items are `GOVERNANCE_ACCEPTANCE_BLOCKER`, not
`IDENTITY_OR_TEMPORAL_BLOCKER`: the `work_order_id` *value* is present,
unique, and unambiguous on every row (Section 6). What blocks production is
its governance/acceptance status (`accepted_with_flag`, refused by
`resolve_effective_decision`'s auto-accept-only policy), not a missing or
ambiguous identity or timestamp. This is a deliberate correction of this
report's earlier, less precise "E -- identity/temporal blocker" label.

**Layer 2 -- downstream relation-sufficiency blocker** (classified only to
show that clearing Layer 1 would not conceal the deeper problem; truth pairs
are used here only to know which items to inspect, never as production
evidence):

| Category | Count | Value |
|---|---:|---:|
| SOURCE_HAS_EXPLICIT_SEMANTIC_EVIDENCE | 0 | -- |
| SOURCE_HAS_DERIVABLE_STRUCTURED_EVIDENCE | 0 | -- |
| SOURCE_ONLY_HAS_FREE_TEXT | 0 | -- |
| **SOURCE_HAS_INSUFFICIENT_EVIDENCE** | **76** | $117,524.00 |
| IDENTITY_OR_TEMPORAL_BLOCKER | 0 | -- |
| GOVERNANCE_ACCEPTANCE_BLOCKER | 0 | -- |
| OTHER | 0 | -- |
| **Total** | **76** | **$117,524.00** |

All 76 items classify as `SOURCE_HAS_INSUFFICIENT_EVIDENCE` for the relation
question specifically, with a sub-note carried over from the A-F trace: 3 of
the 76 (this report's class E, $3,084) additionally have a missing
maintenance-event timestamp that a governed join to `work_orders.closed_date`
*can* derive (`SOURCE_HAS_DERIVABLE_STRUCTURED_EVIDENCE` for the temporal gap
only) -- but even with that gap closed, their underlying relation evidence is
still only the coarse `CM`/`PM` category, so they remain
`SOURCE_HAS_INSUFFICIENT_EVIDENCE` for relation-sufficiency itself. No item
anywhere in the 76 has an explicit relation field going unused
(`SOURCE_HAS_EXPLICIT_SEMANTIC_EVIDENCE`), and no item's only relation
evidence is free text (`SOURCE_ONLY_HAS_FREE_TEXT`) -- Section 8 confirms no
free-text field exists in this corpus at all.

| Case | Truth | Asset | Event / work-order pair | Type | Maintenance completion | Days | Production first | Downstream |
|---|---|---|---|---|---|---:|---|---|
| 002 | EF-LK-2 | AST-000002 | MEV-000005/WO-000005 -> MEV-000006/WO-000006 | CM -> PM | 2026-01-15 -> 2026-01-27 | 12 | E | D |
| 002 | EF-LK-4 | AST-000002 | MEV-000009/WO-000009 -> MEV-000010/WO-000010 | PM -> CM | 2026-05-02 -> 2026-05-08 | 6 | E | D |
| 002 | EF-LK-5 | AST-000004 | MEV-000017/WO-000017 -> MEV-000018/WO-000018 | CM -> PM | 2026-05-01 -> 2026-05-12 | 11 | E | D |
| 002 | EF-LK-8 | AST-000006 | MEV-000028/WO-000028 -> MEV-000029/WO-000029 | PM -> PM | 2026-07-02 -> 2026-07-10 | 8 | E | F |
| 002 | EF-LK-11 | AST-000007 | MEV-000032/WO-000032 -> MEV-000033/WO-000033 | CM -> CM | 2026-04-22 -> 2026-05-06 | 14 | E | F |
| 002 | EF-LK-12 | AST-000007 | MEV-000033/WO-000033 -> MEV-000034/WO-000034 | CM -> CM | 2026-05-06 -> 2026-05-17 | 11 | E | F |
| 002 | EF-LK-16 | AST-000008 | MEV-000037/WO-000037 -> MEV-000038/WO-000038 | CM -> PM | 2026-04-06 -> 2026-04-13 | 7 | E | D |
| 002 | EF-LK-18 | AST-000009 | MEV-000040/WO-000040 -> MEV-000041/WO-000041 | PM -> CM | 2026-02-02 -> 2026-02-11 | 9 | E | D |
| 002 | EF-LK-20 | AST-000010 | MEV-000044/WO-000044 -> MEV-000045/WO-000045 | CM -> PM | 2026-03-04 -> 2026-03-09 | 5 | E | D |
| 002 | EF-LK-22 | AST-000010 | MEV-000047/WO-000047 -> MEV-000048/WO-000048 | CM -> PM | 2026-06-05 -> 2026-06-13 | 8 | E | D |
| 002 | EF-LK-23 | AST-000011 | MEV-000049/WO-000049 -> MEV-000050/WO-000050 | CM -> CM | 2026-01-22 -> 2026-02-04 | 13 | E | F |
| 002 | EF-LK-24 | AST-000012 | MEV-000053/WO-000053 -> MEV-000054/WO-000054 | CM -> CM | 2026-01-06 -> 2026-01-15 | 9 | E | F |
| 002 | EF-LK-25 | AST-000013 | MEV-000059/WO-000059 -> MEV-000060/WO-000060 | PM -> PM | 2026-07-13 -> 2026-07-22 | 9 | E | F |
| 002 | EF-LK-29 | AST-000016 | MEV-000074/WO-000074 -> MEV-000075/WO-000075 | CM -> PM | 2026-03-10 -> 2026-03-20 | 10 | E | D |
| 002 | EF-LK-32 | AST-000017 | MEV-000076/WO-000076 -> MEV-000077/WO-000077 | PM -> CM | missing -> 2026-01-23 (WO closes 2026-01-16 -> 2026-01-23) | — | E | E |
| 002 | EF-LK-43 | AST-000023 | MEV-000096/WO-000096 -> MEV-000097/WO-000097 | CM -> CM | 2026-01-08 -> 2026-01-13 | 5 | E | F |
| 002 | EF-LK-44 | AST-000023 | MEV-000097/WO-000097 -> MEV-000098/WO-000098 | CM -> PM | 2026-01-13 -> 2026-01-22 | 9 | E | D |
| 002 | EF-LK-51 | AST-000026 | MEV-000113/WO-000113 -> MEV-000114/WO-000114 | PM -> CM | missing -> 2026-03-27 (WO closes 2026-03-19 -> 2026-03-27) | — | E | E |
| 002 | EF-LK-55 | AST-000028 | MEV-000119/WO-000119 -> MEV-000120/WO-000120 | CM -> CM | 2026-03-05 -> 2026-03-12 | 7 | E | F |
| 002 | EF-LK-56 | AST-000028 | MEV-000120/WO-000120 -> MEV-000121/WO-000121 | CM -> CM | 2026-03-12 -> 2026-03-16 | 4 | E | F |
| 002 | EF-LK-57 | AST-000030 | MEV-000128/WO-000128 -> MEV-000129/WO-000129 | CM -> PM | 2026-04-06 -> 2026-04-13 | 7 | E | D |
| 002 | EF-LK-61 | AST-000034 | MEV-000142/WO-000142 -> MEV-000143/WO-000143 | CM -> CM | 2026-01-19 -> 2026-01-25 | 6 | E | F |
| 002 | EF-LK-72 | AST-000038 | MEV-000162/WO-000162 -> MEV-000163/WO-000163 | CM -> CM | 2026-03-14 -> 2026-03-25 | 11 | E | F |
| 002 | EF-LK-75 | AST-000039 | MEV-000166/WO-000166 -> MEV-000167/WO-000167 | CM -> CM | 2026-01-14 -> 2026-01-25 | 11 | E | F |
| 002 | EF-LK-76 | AST-000040 | MEV-000168/WO-000168 -> MEV-000169/WO-000169 | CM -> PM | 2026-01-28 -> 2026-02-06 | 9 | E | D |
| 002 | EF-LK-77 | AST-000040 | MEV-000170/WO-000170 -> MEV-000171/WO-000171 | CM -> PM | 2026-03-05 -> 2026-03-22 | 17 | E | D |
| 002 | EF-LK-79 | AST-000041 | MEV-000173/WO-000173 -> MEV-000174/WO-000174 | CM -> CM | 2026-01-11 -> 2026-01-15 | 4 | E | F |
| 002 | EF-LK-80 | AST-000041 | MEV-000176/WO-000176 -> MEV-000177/WO-000177 | CM -> PM | 2026-03-24 -> 2026-04-02 | 9 | E | D |
| 002 | EF-LK-82 | AST-000043 | MEV-000183/WO-000183 -> MEV-000184/WO-000184 | CM -> PM | 2026-04-15 -> missing (WO closes 2026-04-15 -> 2026-04-23) | — | E | E |
| 002 | EF-LK-85 | AST-000044 | MEV-000187/WO-000187 -> MEV-000188/WO-000188 | PM -> CM | 2026-03-17 -> 2026-03-21 | 4 | E | D |
| 002 | EF-LK-86 | AST-000045 | MEV-000190/WO-000190 -> MEV-000191/WO-000191 | CM -> CM | 2026-01-27 -> 2026-02-04 | 8 | E | F |
| 002 | EF-LK-96 | AST-000050 | MEV-000207/WO-000207 -> MEV-000208/WO-000208 | CM -> PM | 2026-03-06 -> 2026-03-15 | 9 | E | D |
| 002 | EF-LK-99 | AST-000053 | MEV-000219/WO-000219 -> MEV-000220/WO-000220 | PM -> PM | 2026-01-13 -> 2026-01-20 | 7 | E | F |
| 002 | EF-LK-100 | AST-000054 | MEV-000228/WO-000228 -> MEV-000229/WO-000229 | PM -> CM | 2026-07-11 -> 2026-07-22 | 11 | E | D |
| 002 | EF-LK-102 | AST-000055 | MEV-000230/WO-000230 -> MEV-000231/WO-000231 | PM -> CM | 2026-01-24 -> 2026-02-03 | 10 | E | D |
| 002 | EF-LK-104 | AST-000056 | MEV-000236/WO-000236 -> MEV-000237/WO-000237 | PM -> CM | 2026-03-20 -> 2026-03-28 | 8 | E | D |
| 002 | EF-LK-110 | AST-000059 | MEV-000245/WO-000245 -> MEV-000246/WO-000246 | CM -> CM | 2026-03-29 -> 2026-04-12 | 14 | E | F |
| 002 | EF-LK-111 | AST-000059 | MEV-000247/WO-000247 -> MEV-000248/WO-000248 | PM -> CM | 2026-04-17 -> 2026-04-26 | 9 | E | D |
| 007 | EF-LK-4 | AST-000004 | MEV-000012/WO-000012 -> MEV-000013/WO-000013 | PM -> PM | 2026-03-10 -> 2026-03-15 | 5 | E | F |
| 007 | EF-LK-6 | AST-000008 | MEV-000028/WO-000028 -> MEV-000029/WO-000029 | PM -> PM | 2026-04-20 -> 2026-05-02 | 12 | E | F |
| 007 | EF-LK-10 | AST-000012 | MEV-000041/WO-000041 -> MEV-000042/WO-000042 | CM -> PM | 2026-03-03 -> 2026-03-15 | 12 | E | D |
| 007 | EF-LK-11 | AST-000013 | MEV-000045/WO-000045 -> MEV-000046/WO-000046 | CM -> CM | 2026-04-16 -> 2026-04-28 | 12 | E | F |
| 007 | EF-LK-12 | AST-000014 | MEV-000047/WO-000047 -> MEV-000048/WO-000048 | PM -> PM | 2026-01-27 -> 2026-02-01 | 5 | E | F |
| 007 | EF-LK-14 | AST-000015 | MEV-000050/WO-000050 -> MEV-000051/WO-000051 | CM -> PM | 2026-03-01 -> 2026-03-18 | 17 | E | D |
| 007 | EF-LK-16 | AST-000015 | MEV-000052/WO-000052 -> MEV-000053/WO-000053 | PM -> PM | 2026-03-27 -> 2026-04-09 | 13 | E | F |
| 007 | EF-LK-18 | AST-000016 | MEV-000054/WO-000054 -> MEV-000055/WO-000055 | CM -> CM | 2026-01-09 -> 2026-01-22 | 13 | E | F |
| 007 | EF-LK-19 | AST-000016 | MEV-000055/WO-000055 -> MEV-000056/WO-000056 | CM -> PM | 2026-01-22 -> 2026-01-30 | 8 | E | D |
| 007 | EF-LK-21 | AST-000018 | MEV-000063/WO-000063 -> MEV-000064/WO-000064 | CM -> PM | 2026-01-24 -> 2026-02-06 | 13 | E | D |
| 007 | EF-LK-22 | AST-000018 | MEV-000064/WO-000064 -> MEV-000065/WO-000065 | PM -> PM | 2026-02-06 -> 2026-02-19 | 13 | E | F |
| 007 | EF-LK-24 | AST-000018 | MEV-000067/WO-000067 -> MEV-000068/WO-000068 | CM -> CM | 2026-04-25 -> 2026-05-01 | 6 | E | F |
| 007 | EF-LK-26 | AST-000019 | MEV-000070/WO-000070 -> MEV-000071/WO-000071 | CM -> CM | 2026-02-19 -> 2026-02-25 | 6 | E | F |
| 007 | EF-LK-28 | AST-000020 | MEV-000078/WO-000078 -> MEV-000079/WO-000079 | CM -> PM | 2026-05-18 -> 2026-05-28 | 10 | E | D |
| 007 | EF-LK-30 | AST-000021 | MEV-000082/WO-000082 -> MEV-000083/WO-000083 | PM -> CM | 2026-04-11 -> 2026-04-22 | 11 | E | D |
| 007 | EF-LK-31 | AST-000022 | MEV-000085/WO-000085 -> MEV-000086/WO-000086 | CM -> CM | 2026-01-07 -> 2026-01-12 | 5 | E | F |
| 007 | EF-LK-33 | AST-000022 | MEV-000086/WO-000086 -> MEV-000087/WO-000087 | CM -> CM | 2026-01-12 -> 2026-01-22 | 10 | E | F |
| 007 | EF-LK-34 | AST-000024 | MEV-000093/WO-000093 -> MEV-000094/WO-000094 | CM -> CM | 2026-02-01 -> 2026-02-16 | 15 | E | F |
| 007 | EF-LK-35 | AST-000025 | MEV-000098/WO-000098 -> MEV-000099/WO-000099 | CM -> CM | 2026-03-06 -> 2026-03-16 | 10 | E | F |
| 007 | EF-LK-37 | AST-000027 | MEV-000105/WO-000105 -> MEV-000106/WO-000106 | PM -> PM | 2026-01-14 -> 2026-01-21 | 7 | E | F |
| 007 | EF-LK-38 | AST-000028 | MEV-000113/WO-000113 -> MEV-000114/WO-000114 | CM -> CM | 2026-05-27 -> 2026-06-11 | 15 | E | F |
| 007 | EF-LK-40 | AST-000030 | MEV-000122/WO-000122 -> MEV-000123/WO-000123 | PM -> CM | 2026-08-10 -> 2026-08-21 | 11 | E | D |
| 007 | EF-LK-41 | AST-000031 | MEV-000125/WO-000125 -> MEV-000126/WO-000126 | CM -> CM | 2026-03-02 -> 2026-03-12 | 10 | E | F |
| 007 | EF-LK-43 | AST-000032 | MEV-000131/WO-000131 -> MEV-000132/WO-000132 | CM -> PM | 2026-05-24 -> 2026-06-05 | 12 | E | D |
| 007 | EF-LK-44 | AST-000033 | MEV-000135/WO-000135 -> MEV-000136/WO-000136 | PM -> PM | 2026-03-20 -> 2026-03-26 | 6 | E | F |
| 007 | EF-LK-45 | AST-000033 | MEV-000136/WO-000136 -> MEV-000137/WO-000137 | PM -> CM | 2026-03-26 -> 2026-04-04 | 9 | E | D |
| 007 | EF-LK-47 | AST-000036 | MEV-000144/WO-000144 -> MEV-000145/WO-000145 | CM -> PM | 2026-02-11 -> 2026-02-23 | 12 | E | D |
| 007 | EF-LK-49 | AST-000038 | MEV-000150/WO-000150 -> MEV-000151/WO-000151 | CM -> CM | 2026-03-18 -> 2026-03-28 | 10 | E | F |
| 007 | EF-LK-51 | AST-000039 | MEV-000157/WO-000157 -> MEV-000158/WO-000158 | CM -> CM | 2026-06-15 -> 2026-06-26 | 11 | E | F |
| 007 | EF-LK-55 | AST-000042 | MEV-000165/WO-000165 -> MEV-000166/WO-000166 | CM -> CM | 2026-01-28 -> 2026-02-09 | 12 | E | F |
| 007 | EF-LK-56 | AST-000042 | MEV-000166/WO-000166 -> MEV-000167/WO-000167 | CM -> CM | 2026-02-09 -> 2026-02-13 | 4 | E | F |
| 007 | EF-LK-57 | AST-000043 | MEV-000169/WO-000169 -> MEV-000170/WO-000170 | PM -> CM | 2026-01-10 -> 2026-01-13 | 3 | E | D |
| 007 | EF-LK-58 | AST-000044 | MEV-000173/WO-000173 -> MEV-000174/WO-000174 | CM -> PM | 2026-01-16 -> 2026-01-29 | 13 | E | D |
| 007 | EF-LK-59 | AST-000044 | MEV-000174/WO-000174 -> MEV-000175/WO-000175 | PM -> CM | 2026-01-29 -> 2026-02-13 | 15 | E | D |
| 007 | EF-LK-62 | AST-000046 | MEV-000181/WO-000181 -> MEV-000182/WO-000182 | PM -> PM | 2026-01-16 -> 2026-01-23 | 7 | E | F |
| 007 | EF-LK-63 | AST-000047 | MEV-000186/WO-000186 -> MEV-000187/WO-000187 | CM -> CM | 2026-03-05 -> 2026-03-10 | 5 | E | F |
| 007 | EF-LK-64 | AST-000048 | MEV-000189/WO-000189 -> MEV-000190/WO-000190 | CM -> CM | 2026-04-01 -> 2026-04-15 | 14 | E | F |
| 007 | EF-LK-65 | AST-000048 | MEV-000190/WO-000190 -> MEV-000191/WO-000191 | CM -> CM | 2026-04-15 -> 2026-04-28 | 13 | E | F |

The downstream value distribution is D: 32 items / $49,404; E: 3 items /
$3,084; F: 41 items / $65,036. It is examiner-side characterization, not a
production derivation or a proposed scoring rule.

## Generic relation-strategy evaluation

Each counterfactual was applied only after terminal production, across all
four frozen FieldMaintenance cases. Candidate order is deterministic and
adjacent within the stated grouping. Precision is shown to expose safety risk;
no strategy was selected from truth.

| Strategy | TP | Non-truth candidates | FN | Precision | Recall | Governance/generalization conclusion |
|---|---:|---:|---:|---:|---:|---|
| Same asset only | 68 | 1,423 | 8 | 4.56% | 89.47% | Not semantic relatedness; ordinary maintenance dominates |
| Exact governed `event_type` (`CM`/`PM`) | 36 | 1,085 | 40 | 3.21% | 47.37% | Current contract; categories are far too broad |
| Exact failure code/category | 0 | 0 | 76 | N/A | 0.00% | Source field absent |
| Exact component (`part_number`) | 0 | 0 | 76 | N/A | 0.00% | No truth pair shares a part; field is also unresolved |
| Component + activity | 0 | 0 | 76 | N/A | 0.00% | No repeated exact component chain |
| Exact service type | 0 | 0 | 76 | N/A | 0.00% | Source field absent; `event_type` is not service type |
| Failure + component | 0 | 0 | 76 | N/A | 0.00% | Required fields absent/unlinked |
| Same priority | 32 | 1,058 | 44 | 2.94% | 42.11% | Priority is urgency, not semantic relation |
| Same contract | 68 | 1,423 | 8 | 4.56% | 89.47% | Commercial relationship only; equivalent to asset adjacency here |
| Same technician | 10 | 187 | 66 | 5.08% | 13.16% | Assignment is not failure/repair equivalence |

Joining authoritative `work_orders.work_order_id` and `closed_date` to the
maintenance event is mechanically plausible and recovers all three missing
event timestamps. It does not solve semantics: exact-category pairing after
that join gives 36 TP, 1,121 non-truth candidates, and 40 FN. Same-asset
pairing gives 71 TP, 1,470 non-truth candidates, and 5 FN. The join is reusable
evidence composition, but it cannot turn a maintenance sequence into governed
rework evidence.

An explicit governed policy window could narrow ordinary maintenance only if
the customer supplied the policy and its applicability. No such policy exists
here. The observed truth intervals (3–17 days) cannot be reverse-engineered
into a production rule without truth leakage, and proximity alone still does
not establish common failure, component, service, or rework causality.

## Why tests passed

The unit pairing tests inject already-authoritative field names directly into
`InterventionDatasetFields`; they bypass semantic interpretation and the
effective-decision resolver. The end-to-end fixture uses one synthetic table
with an unambiguous `work_order_id`, a rich `service_type`, and a deliberately
related same-category pair. It does not reproduce the frozen shape in which
`event_id` and `work_order_id` coexist and cause the latter to be flagged.

The tests establish deterministic pairing, abstention, deduplication, and
lineage for a valid evidence contract. They do not establish that readiness
and execution share the same authority test, nor do they calibrate the
false-positive surface of a two-value activity vocabulary against realistic
ordinary maintenance volume. A future authorized change would need both a
frozen-shape readiness/execution parity test and a high-volume negative
semantic-relation fixture.

## Code defect versus data-contract gap

| Layer | Finding | Classification | Effect |
|---|---|---|---|
| Dataset-role classification | `_score_roles` gates `EVENT` behind `not scores`, so `SCHEDULE` (a weaker, single-field match) unconditionally preempts it for `maintenance_events.csv` | CAPABILITY_MODEL_GAP | Caps `work_order_id` at 0.85 instead of >=0.95; the precise root cause of the governance-acceptance blocker (Section 6) |
| Readiness/execution parity | READY can coexist with zero admissible datasets | CAPABILITY_MODEL_GAP | Explains the immediate 0-candidate execution |
| Cross-dataset evidence composition | `MAINTENANCE-REPEAT-VISIT` wiring never calls the existing P3.xxI.2C bridge, so `work_orders.csv`'s already-`auto_accepted` `work_order_id` is never offered to `maintenance_events.csv` | CAPABILITY_MODEL_GAP | Hides valid identity/timestamp evidence already available through the existing, reusable bridge mechanism |
| Relation model | Exact `CM`/`PM` equality is treated as “related” | CAPABILITY_MODEL_GAP | Unsafe if identity gate is cleared |
| Customer/source contract | No governed failure/component/service/rework relation or policy window | DATA_CONTRACT_GAP | Prevents safe discrimination of all 76 truth items |
| Canonical relationship coverage | No same-type `WORK_ORDER<->WORK_ORDER` relationship exists anywhere (only cross-type `BELONGS_TO`) | CAPABILITY_MODEL_GAP (future, not this milestone) | This is P3.xxE.4's unbuilt job; not a defect in P3.xxI.5B specifically |

The first four rows are real, reusable architecture concerns, but fixing
them alone cannot produce a safe finding on this corpus. The fifth (data
contract) cannot be repaired by a broader synonym list, threshold reduction,
truth-derived time window, or customer-specific hard-coded category
relation. The production posture must remain abstention until governed
relation evidence exists.

## Reachability and false-positive boundary

| Measure | Estimate on frozen corpus |
|---|---:|
| Current safely reachable denominator | **0 / 76** |
| Current maximum safe recall | **0.00%** |
| Latent matches from exact category if safety is ignored | 36 / 76 |
| Exact-category mechanical/fabricated FP exposure | 1,085 |
| Same-asset latent matches if safety is ignored | 68 / 76 |
| Same-asset mechanical/fabricated FP exposure | 1,423 |
| Items with an explicit unused relation field | 0 |
| Items with free-text-only relation evidence | 0 |

“Maximum safe recall” is deliberately not the highest retrospective match
rate. A high-recall rule that cannot distinguish ordinary maintenance from
rework is not a governed capability.

## Recommended remediation options (ranked, per the mission's exact framing)

### Option A -- Consume already-governed canonical WORK_ORDER identity/relationship evidence correctly

Fix the two concrete code gaps identified in Sections 6-7: (i) the
`SCHEDULE`-before-`EVENT` unconditional precedence defect in
`app/semantic/role_classifier.py::_score_roles`, and/or (ii) wire the
`MAINTENANCE-REPEAT-VISIT` orchestration block to use the existing
`_resolve_subject_field_for_dataset`/`_resolve_identifier_bridge_map` bridge
(already proven in Revenue Variance and Contract/Rate Compliance) instead of
the strict, non-bridging `_resolve_canonical_concept_field`, so
`work_orders.csv`'s already-`auto_accepted` (0.98) `work_order_id` becomes
available as authoritative evidence for `maintenance_events.csv` rows. Also
align readiness's structural check with execution's effective-evidence
check so `READY` cannot coexist with zero admissible datasets.

- **Reachable truth items:** 0 net new *safe* findings. This closes the
  readiness/execution mismatch and produces admissible candidate datasets,
  but candidate *generation* still runs into the Section 9 relation wall.
- **Expected maximum recall (safe):** 0.00% -- unchanged, because nothing
  about this option adds relation evidence; it only removes an identity
  obstacle that was never the thing preventing safe discrimination.
- **False-positive risk:** none by itself (it only restores identity
  parity); risk only appears if the corrected pipeline is then allowed to
  publish on exact-category adjacency alone (see the rejected strategies).
- **Architectural leverage:** high -- reuses two already-built, already-
  tested mechanisms (bridge, role scoring) instead of adding anything new;
  the role-classifier fix also benefits every other capability that reads
  `maintenance_events.csv`-shaped datasets, not just repeat/rework.
- **Implementation complexity:** low -- a role-scoring precedence change
  plus an `allow_bridge` wiring change, both precedented in this program.
- **Dependency on source data:** none.
- **Applicability beyond FieldMaintenance:** high (role classifier and
  bridge are both fully generic, concept-driven, no dataset-name coupling).

### Option B -- Governed maintenance semantic extraction (structured and/or free text -> canonical relation concepts)

Introduce a new capability: raw structured/free-text evidence -> canonical
component/failure/intervention-type concepts, with provenance and ambiguity
handling, producing genuine relation evidence (not just activity existence).

- **Reachable truth items on this corpus:** 0. There is no free text to
  extract from (Section 8), and the only structured fields available
  (`event_type` = `CM`/`PM`, `priority`, `part_number` with zero shared
  parts across any truth pair) contain no extractable failure/component/
  service signal beyond what is already modeled.
- **Expected maximum recall on this corpus:** 0.00%.
- **False-positive risk:** low, if built with the same governed,
  ambiguity-safe philosophy as the rest of the platform -- but unverifiable
  here since there is nothing on this corpus to test it against.
- **Architectural leverage:** potentially high for other customers/corpora
  that do carry free text or richer structured failure/component fields;
  zero leverage for this specific frozen Wave 1 package.
- **Implementation complexity:** high -- a new semantic-extraction stage,
  new canonical concepts, new evidence/lineage plumbing, new governance
  thresholds.
- **Dependency on source data:** total -- this option is only as good as
  what the source actually contains, which on this corpus is nothing.
- **Applicability beyond FieldMaintenance:** potentially high, but
  unproven and unscoped; do not build against a corpus that cannot
  validate it.

### Option C -- Define a customer/source data contract requiring explicit component/failure/service/intervention identifiers

Require the customer to supply governed `failure_code`/`component_id`/
`service_type`/`callback_of`/`rework_of`-shaped fields going forward.

- **Reachable truth items on current, already-frozen corpus:** 0 -- a data
  contract cannot retroactively populate historical exports.
- **Expected maximum recall (once supplied, hypothetically):** unbounded by
  code; bounded entirely by how completely and consistently the customer
  populates the new fields. No numeric prediction is defensible before that
  evidence exists.
- **False-positive risk:** low, since explicit fields are the strongest,
  least ambiguous evidence class available.
- **Architectural leverage:** none additional beyond what the existing
  concept registry/semantic pipeline already supports -- new aliases would
  slot into the existing architecture without new mechanisms.
- **Implementation complexity:** low on the platform side; the cost is
  entirely external (customer onboarding/data-contract negotiation).
- **Dependency on source data:** total, and not owned by this engineering
  program.
- **Applicability beyond FieldMaintenance:** high as a governance pattern
  (the same contract shape -- explicit relation identifiers -- generalizes
  to any maintenance-shaped source), but each customer's willingness/ability
  to supply it is independent and unpredictable.

### Option D -- Combination (A foundation, evaluated independently of B/C's uncertain payoff)

Implement Option A now (it is small, reusable, safe, and fixes two real
defects regardless of this capability's fate); do not implement B or C
against this corpus, since both are correctly predicted at 0/76 recall here
and their cost is not justified by a corpus that cannot exercise them.
Revisit B/C only if/when a real customer data contract or corpus is
identified that actually contains free text or explicit relation fields --
at that point, Option A's foundation (correct identity, correct readiness/
execution parity) will already be in place to receive it.

**Recommendation: Option A alone, now, explicitly not expected to change
recall on this corpus** -- ranked highest because it is the only option with
positive reachable value (two real, reusable, low-risk code defects fixed)
that does not depend on unavailable source evidence. Options B and C remain
correctly predicted at 0/76 on this corpus and should not be built against
it. This is consistent with Codex's original single-option recommendation;
this pass narrows and quantifies it into the four ranked options the mission
requested and grounds Option A in the exact code locations verified in
Sections 6-7.

## Preserved controls

- Revenue Amount remains exactly **61 / 0 / 86 / 26**.
- MAINT-001 behavior and implementation remain unchanged.
- P3.xxI.5B certification remains **0 / 0 / 76**, with 0 mechanical/fabricated
  false positives.
- No new capability, production hardening, Wave 2, E.6/E.7, or frontend work
  was started.

## Explicit owner gate

**Recommended gate: do not authorize a publication remediation against the
current frozen corpus.** First require a governed customer/source data contract
for failure, component, service/repair, or explicit rework relationship
evidence.

Owner choices:

1. **Recommended -- data-contract-first (Option C in Section 11):** accept
   this reconciliation, retain safe abstention, and define/freeze governed
   maintenance-relation evidence before authorizing P3.xxI.5B-R
   implementation.
2. **Foundation-only (Option A in Section 11):** separately authorize the
   role-classifier precedence fix and the identifier-bridge wiring fix,
   explicitly expecting 0/76 recall on this corpus and no capability
   graduation -- justified purely as two small, reusable, low-risk defect
   fixes with value beyond this one capability, not as a path to recall on
   this corpus.
3. **Defer/stop:** leave P3.xxI.5B FAILED and take no further action.

No implementation, commit, push, PR, merge, or new milestone is authorized by
this report. Work stops at this owner gate.

## P3.xxI.5B-R FOUNDATION IMPLEMENTATION

**Owner authorization:** "Authorize the Option A implementation as a
foundation-only P3.xxI.5B-R fix," followed by a required scope decision
(below) once implementation revealed a safety conflict Option A's original
description did not anticipate.

### Scope correction discovered during implementation

Two things changed from Option A's original description in this document,
both discovered by actually implementing and testing against the real
corpus rather than by further analysis:

1. **The bridge-wiring change and the `required_canonical_fields` registry
   rename are not needed.** `_resolve_canonical_concept_field` (used
   unchanged by the existing `MAINTENANCE-REPEAT-VISIT` orchestration
   block) already accepts any `AUTO_ACCEPTED` decision regardless of which
   dataset it came from. Once the role-classifier fix (below) raises
   `maintenance_events.csv`'s own `work_order_id` decision to
   `AUTO_ACCEPTED` directly, the existing, *unmodified* orchestration
   wiring resolves it correctly on its own -- no P3.xxI.2C-style bridge or
   registry change is required. Implementing them anyway would have been
   unnecessary surface area for zero additional benefit, so they were cut.
2. **A required addition Option A's description did not include: a
   relation-sufficiency safety gate.** The role-classifier fix is shared
   platform infrastructure, not capability-scoped -- fixing it
   automatically unblocks the already-merged, unchanged
   `MAINTENANCE-REPEAT-VISIT` pairing/publication logic to run on real data
   for the first time. That logic's already-accepted contract (`tests/
   test_maintenance_repeat_visit.py`, pre-existing tests a-e) publishes a
   `Finding` for every same-asset, same-activity-category adjacent pair,
   with no further gate. Verified directly: on the real `FIELDMAINT-002`
   corpus, the role-classifier fix alone raises `intervention_datasets`
   from 0 to 1 admissible dataset, which -- without a further gate -- would
   have started publishing exactly the unsafe candidate volume already
   quantified in this report's Section 9 (up to 1,121 candidates, 1,085
   non-truth). This was flagged to the owner before proceeding (a genuine
   safety conflict, not implied by the original authorization) and the
   owner selected: implement the identity fix **and** the relation-
   sufficiency gate together, so the net certification effect stays 0/76 as
   originally predicted.

### What was implemented

**1. Role-classifier precedence fix -- `app/semantic/role_classifier.py`
(`_score_roles`).** The `SCHEDULE` role's guard gained one condition:
`and not completion_hits`, where `completion_hits = field_matches("completed",
"closed", "actual", "occurred")`. A dataset with a scheduled/planned date
AND a completed/closed/actual/occurred date is a record of what happened
(EVENT-shaped), not a forward-looking plan (SCHEDULE-shaped), even though
it also carries a scheduled-date column. This is the precise, narrow fix
for the root cause identified in this report's Section 6: `SCHEDULE`
matching first unconditionally preempted `EVENT` (`EVENT` was only
proposed when nothing else matched), even when the dataset was genuinely
event-shaped.

Verified against the pinned calibration fixture
(`tests/semantic_calibration_fixtures.py`'s `work_order_unfamiliar_aliases`,
`expected_dataset_role="schedule"`): that fixture has only a scheduled date,
no completion evidence, so it is unaffected and still correctly classifies
as `schedule` -- confirming the fix is precisely targeted, not a blanket
change to `SCHEDULE`'s behavior. No concept in `app/semantic/
concept_registry.py` lists `"schedule"` in its `compatible_dataset_roles`
(verified by search), so re-classifying an event-shaped dataset from
`schedule` to `event` can only ever add eligibility, never remove
eligibility another concept depended on.

**2. Relation-sufficiency safety gate -- `app/services/
maintenance_repeat_visit_service.py`.** `InterventionDatasetFields` gained
an optional `relation_dimension_field: str | None = None`;
`InterventionEvidence` gained `relation_dimension_value: str | None`.
`build_repeat_visit_pairs` now requires two interventions to share a
non-null relation-dimension value, in addition to asset and activity
category, before they can group into a candidate pair at all. When a
dataset resolves no relation-dimension field (true of every real corpus
certified so far, since the platform has no `failure_code`/`component_id`/
`service_type`/`rework_of`-shaped concept registered yet -- Option B/C in
this report), none of its interventions can ever pair. This is a
structural requirement on whether the concept resolved, never a
customer-specific or simulation-specific carve-out. Evidence/lineage
(`_intervention_evidence`, the published finding's identity references)
were extended to carry the relation-dimension value through for full
lineage when a pair does form.

**3. Orchestration wiring and readiness/registry: unchanged.** Per the
scope correction above, no change was needed to
`analysis_case_orchestration_service.py`'s `MAINTENANCE-REPEAT-VISIT` block
or to the intelligence-pack registry's `required_canonical_fields`.

### Live verification against the real corpus (before/after)

Direct instrumentation of the merged pipeline against
`SIM-OFS-FIELDMAINT-002/customer-data`:

| Measure | Before this fix | After this fix |
|---|---|---|
| `maintenance_events.csv` `work_order_id` decision | `accepted_with_flag`, 0.85 | `auto_accepted`, 0.98 |
| All six `work_order_id` decisions in the case | 5 `auto_accepted` / 1 `accepted_with_flag` | 6 / 6 `auto_accepted` |
| `intervention_datasets` (admissible datasets for pairing) | 0 | 1 |
| `MAINTENANCE-REPEAT-VISIT` activation `governed_status` | `READY` (with 0 admissible datasets -- the parity mismatch) | `READY` (now genuinely backed by 1 admissible dataset) |
| Pairs formed / findings published | 0 | **0** (relation-sufficiency gate correctly withholds, since `relation_dimension_field` is `None`) |
| `REVENUE-AMOUNT-VARIANCE` findings (same case) | 0 (matches the frozen 61/0/86/26 control -- FIELDMAINT-002 is the `0`) | 0 -- unchanged |

Net certification effect: **0/76, exactly as predicted** -- the identity
and readiness/execution defects are genuinely fixed and verified, and the
capability remains safely dormant on this corpus because governed relation
evidence still does not exist in it, not because of an identity or
readiness defect.

### Tests

| # | Test | Proves |
|---|---|---|
| `tests/test_semantic_profiler.py::test_a_scheduled_date_alone_is_genuinely_schedule_shaped` | Regression: a genuinely schedule-only dataset (no completion evidence) still classifies as `schedule` |
| `tests/test_semantic_profiler.py::test_b_scheduled_plus_completed_date_is_event_shaped_not_schedule` | The fix: scheduled + completed evidence together classify as `event`, not `schedule` |
| `tests/test_semantic_profiler.py::test_c_closed_date_alone_also_suppresses_schedule` | The completion signal generalizes beyond the literal word "completed" |
| `tests/test_maintenance_repeat_visit.py::test_negative_i_no_relation_dimension_field_never_pairs` | The exact real-corpus case: no relation-dimension concept resolves -- never pairs, even with clean identity/category/timestamps |
| `tests/test_maintenance_repeat_visit.py::test_negative_j_relation_dimension_field_present_but_value_missing_never_pairs` | An unresolved relation-dimension value is never treated as an implicit wildcard |
| `tests/test_maintenance_repeat_visit.py::test_negative_k_different_relation_dimension_values_do_not_pair` | Two interventions with genuinely different relation-dimension values are correctly kept apart |
| `tests/test_maintenance_repeat_visit.py::test_positive_relation_dimension_present_and_shared_produces_a_pair` | The gate narrows when a pair forms; it does not remove the capability's ability to ever form one |
| `tests/test_maintenance_repeat_visit.py::test_d_generic_service_fixture_reaches_ready_but_abstains_without_relation_dimension` (renamed, rewritten) | Full orchestration: readiness and execution now agree (`READY`, 1 admissible dataset), but publication is correctly zero without relation evidence -- the exact safety property this implementation exists to guarantee |
| All 13 pre-existing `tests/test_maintenance_repeat_visit.py` tests (a-c, e-h) | Unaffected by the gate once given a constant relation-dimension value via the test helper's default -- ordering, deduplication, conflict-abstention, and lineage behavior are all preserved exactly as before |

### Regression

| Suite | Result |
|---|---:|
| `tests/test_maintenance_repeat_visit.py` + `tests/test_semantic_profiler.py` | 30 passed |
| `tests/test_semantic_calibration.py`, `test_semantic_interpreter.py`, `test_semantic_sibling_concept_corroboration.py`, `test_semantic_architecture_guardrails.py` | 26 passed (confirms the pinned `work_order_unfamiliar_aliases` SCHEDULE fixture and all other role/semantic calibration behavior is unaffected) |
| Focused sweep (rate/uom/duration/revenue/semantic/readiness/relationship/trust/lineage/validation_isolation/tenant/contract/maint/xdom/repeat_visit/role) | 758 passed (3 apparent failures traced to stale state in a shared disposable-Postgres instance from an earlier, unrelated run in this session -- re-ran clean after a schema reset: all 3 pass) |
| Disposable PostgreSQL suite (fresh `DROP SCHEMA public CASCADE` reset) | 83 passed |
| Full non-Postgres suite | 1,750 passed |
| `ruff format --check .` / `ruff check .` | clean on every file this change touched (repo-wide run separately flags only the untracked, non-deliverable `tmp_p3xxi5b_reconcile.py` scratch script left from the prior diagnosis pass -- not part of this change) |
| `mypy .` | 622 source files, zero issues in any file this change touched (same untracked scratch script is the only source of the repo-wide error count) |

Revenue Amount Variance, MAINT-001, XDOM-A, and XDOM-B were not modified and
were re-confirmed unchanged wherever the regression sweep and live
verification above touched them.

### Implementation PR

- Branch: `feature/p3xxi5br-foundation`
- Pull request: [#127](https://github.com/intel4ops/intel4ops-core-platform/pull/127)
  ("fix: P3.xxI.5B-R foundation - role-classifier precedence +
  relation-sufficiency gate")
- Head SHA: `193e115650193130b2ce85e51a98d8590e5df2c5`
- Pre-merge CI: passed (`Ruff, Mypy, Pytest, and Alembic`, 20m12s)
- Merge: owner-authorized after explicit confirmation naming PR #127 and
  its exact head SHA; merge commit `ce843257915e52c4e2badf700271d857cf5a19c0`,
  merged 2026-09-06T06:31:00Z. Local `main` confirmed synchronized to
  `origin/main` at the same SHA immediately after.
- Post-merge `main` Quality Gate: triggered automatically
  (run `34016692342`); result recorded in the certification section below.
- Backend health immediately after merge: HTTP 200 from
  `https://intel4ops-core-api.onrender.com/api/v1/health`, response
  `{"status":"ok","platform":"Intel4Ops Core","phase":2}`. The platform's
  health endpoint does not expose a deployed commit SHA or migration-status
  field; none is claimed beyond this.

## P3.xxI.5B-R POST-MERGE CERTIFICATION

### Scope and method

Four fresh orchestrated cases were created against the frozen Wave 1
FieldMaintenance corpus (`FIELDMAINT-001/002/005/007`), production-pipeline-
first: case created, all 12 customer-data files uploaded per case, analysis
run, and each run allowed to reach its own terminal state before any
finding or truth data was read. No case was created against Rental (not in
scope -- Maintenance Repeat Visit/Rework is a FieldMaintenance-only
capability) and no truth file was opened before every run below shows a
terminal `completed_at`.

| Case | Case ID | Run ID | Terminal status | Completed at |
|---|---|---|---|---|
| P3xxI5BR-Cert-FIELDMAINT-001 | `681abaee-d5dc-408f-85b7-b38ae8c112cd` | `bcf79872-081b-43be-90cd-42ec5546835d` | `review_required` | 2026-09-06T06:35:59Z |
| P3xxI5BR-Cert-FIELDMAINT-002 | `cdaeb358-d426-48fe-a017-91d24d37c99e` | `efd58779-09db-4fb4-ba47-2b2dccafdcca` | `review_required` | 2026-09-06T06:37:18Z |
| P3xxI5BR-Cert-FIELDMAINT-005 | `b0b83c4f-2e48-4172-a479-0ff3080fa101` | `558a3220-cfc9-4858-9ee4-e2f8f3aab37a` | `review_required` | 2026-09-06T06:42:23Z |
| P3xxI5BR-Cert-FIELDMAINT-007 | `a684639d-92b3-4ace-97a0-4b3f9471312a` | `9a9d3a47-2548-41dc-bd95-23b64ea66ab6` | `review_required` | 2026-09-06T06:40:46Z |

`review_required` is the same established terminal review outcome used
throughout this program (mapping/domain-review signals, not a failed run).

The Navigator does not expose a per-pack activation-decision or
semantic-decision payload through its API for any rule (confirmed again
here: `.../runs/{id}/intelligence-activation`,
`.../runs/{id}/activation-decisions`, and `.../runs/{id}/semantic-decisions`
all return 404, exactly as found during the original P3.xxI.5A live
certification). Assertion A below is therefore evidenced two ways: (1) a
debug-instrumented run of the exact merged `main` code
(commit `ce843257`) against the same real, frozen customer-data files for
all four cases, reading the persisted `SemanticInterpretationDecision` and
`IntelligenceActivationDecision` rows directly; and (2) the live findings
pulled from these four production cases themselves, which corroborate it
indirectly -- `REVENUE-AMOUNT-VARIANCE` (a rule that depends on several of
the same semantic decisions) reproduces the frozen control exactly, which
would not happen if the merged code were behaving differently in
production than in the debug harness. Orchestration is a deterministic
function of (code version, input files); both evidence sources are
consistent.

### A. Identity/readiness correction

| Case | `work_order_id` decisions (6 datasets) | Remaining `accepted_with_flag` | Admitted intervention datasets | `MAINTENANCE-REPEAT-VISIT` activation |
|---|---|---:|---:|---|
| FIELDMAINT-001 | 6/6 `auto_accepted` | 0 | 1 | `READY` |
| FIELDMAINT-002 | 6/6 `auto_accepted` | 0 | 1 | `READY` |
| FIELDMAINT-005 | 6/6 `auto_accepted` | 0 | 1 | `READY` |
| FIELDMAINT-007 | 6/6 `auto_accepted` | 0 | 1 | `READY` |

`maintenance_events.work_order_id` now resolves `AUTO_ACCEPTED` in every
case (previously `ACCEPTED_WITH_FLAG` at 0.85 in all four). Readiness and
execution agree in every case: `READY` is now backed by 1 genuinely
admissible intervention dataset, not 0. Zero `accepted_with_flag`
decisions remain on `work_order_id` anywhere in this corpus.

### B. Relation-sufficiency gate

| Case | `MAINTENANCE-REPEAT-VISIT` findings published |
|---|---:|
| FIELDMAINT-001 | 0 |
| FIELDMAINT-002 | 0 |
| FIELDMAINT-005 | 0 |
| FIELDMAINT-007 | 0 |

Zero publications despite genuinely admissible datasets and genuine
same-asset/same-category adjacency existing in the real data (confirmed by
the debug harness: candidate pairing was evaluated, not skipped upstream).
No pair published on same-asset + same-activity-category + adjacency
alone. The gate holds exactly as designed.

### C. Safety

**Mechanical/fabricated FP: 0.** Zero `MAINTENANCE-REPEAT-VISIT` findings
were published across all four cases, so zero could be fabricated or
mechanically incorrect.

### D. Revenue Amount regression control

| Case | `REVENUE-AMOUNT-VARIANCE` findings (live) | Frozen control |
|---|---:|---:|
| FIELDMAINT-001 | 61 | 61 |
| FIELDMAINT-002 | 0 | 0 |
| FIELDMAINT-005 | 86 | 86 |
| FIELDMAINT-007 | 26 | 26 |

**Preserved exactly: 61 / 0 / 86 / 26.** Byte-for-byte identical to the
frozen baseline, confirmed both live (production API) and via the debug
harness on the same merged code.

### E. MAINT-001

Not exercised, modified, or referenced by this fix or this certification.
`MAINT-001-REPEATED-FAILURE` shares no code path with
`app/semantic/role_classifier.py` or
`app/services/maintenance_repeat_visit_service.py`. Unchanged.

### Score against the frozen 76

The frozen `repeat_repair` truth family (76 items, $117,524.00, occurring
only in the `FIELDMAINT-002` and `FIELDMAINT-007` case slices, per this
report's own earlier truth-item trace) was read only after all four
production runs above reached their terminal state.

| Metric | Result |
|---|---:|
| TP | 0 |
| FP | 0 |
| FN | 76 |
| Precision | N/A (no positive predictions) |
| Recall | 0 / 76 = **0.00%** |
| Economic-value capture | $0 / $117,524.00 = **0.00%** |
| Mechanical/fabricated FP | **0** |

**This is not a regression.** It is the same safe, predicted outcome
identified before implementation: the identity/readiness defect is fixed
and verified, and the platform correctly continues to abstain because no
governed relation-dimension evidence exists in this corpus.

### Root cause after the foundation fix

With identity and readiness/execution parity now genuinely fixed, TP
remains 0. The remaining blocker is precisely:

**`SEMANTIC_EVIDENCE_GAP` / `DATA_CONTRACT_GAP`** -- not a
`CAPABILITY_MODEL_GAP`. No customer file in this corpus contains
`failure_code`, `failure_category`, `repair_type`, `service_type`,
`component_id`, `subsystem_id`, `symptom`, `cause`, `callback_of`,
`rework_of`, `parent_work_order_id`, `relation_type`, free text, or an
explicit repeat/rework policy window (re-confirmed unchanged from this
report's earlier evidence inventory -- the corpus itself has not changed).
The only governed activity descriptor remains the two-value `CM`/`PM`
field, already shown insufficient to safely distinguish repeat/rework from
ordinary maintenance (Section 9's counterfactual strategy table, unchanged
by this fix). The gate is not weakened to manufacture recall.

### Final status

**FOUNDATION FIX STATUS: VALIDATED.** The diagnosed root cause (a
dataset-role classification ordering defect) is fixed, verified against
the real corpus by two independent methods, and reusable beyond this one
capability. Readiness and execution now agree. The required
relation-sufficiency safety gate holds under live production conditions
exactly as designed. Zero regression: Revenue Amount Variance, MAINT-001,
XDOM-A, and XDOM-B are all unaffected. Zero mechanical/fabricated FP,
live and locally verified.

**CAPABILITY EFFECTIVENESS STATUS: NOT VALIDATED (unchanged).** Maintenance
Repeat Visit/Rework still scores 0/76 live. This is not a defect in the
foundation implementation -- it is a confirmed, pre-identified, unchanged
`DATA_CONTRACT_GAP`: the platform correctly has no way to safely
distinguish rework from ordinary maintenance without governed relation
evidence this corpus does not supply.

**P3.xxI.5B-R PARTIALLY VALIDATED.**

The remediation delivers genuine, verified engineering value (a real,
reusable, low-risk defect fixed; the required safety gate correctly
prevents an FP regression that would otherwise have occurred) without
achieving capability graduation, because graduation depends on evidence
that does not exist in the customer's current data. Capability #3 must
not start without a new owner authorization.

### PR #126 disposition

PR #126 ("docs: certify P3.xxI.5B maintenance repeat visit") documents the
*original*, pre-remediation P3.xxI.5B certification (`0/0/76`, dominant
classification `CAPABILITY_MODEL_GAP` with an immediate
`SEMANTIC_EVIDENCE_GAP`) and a "Capability #2 post-merge scorecard" section
in `docs/p3xxi5-intelligence-breadth-expansion-program.md`. It has not been
merged and does not include this fix (its branch was created before PR
#127 existed).

**Recommendation: still needed as-is; merge it unchanged (with separate
owner authorization), do not rebase or close it.** This mirrors the
established, already-precedented pattern in this exact program: PR #122
(the original P3.xxI.5A `FAILED` certification) was preserved and merged
as the historical record of that milestone's first certification, and PR
#124 (the P3.xxI.5A-R remediation's own live certification) was added
*separately and additively* afterward, in its own document section, rather
than rewriting PR #122. PR #126's certification numbers (`0/0/76`, FP=0,
Revenue Amount/MAINT-001 preserved) are still factually accurate as the
record of the *original* P3.xxI.5B certification and should not be altered
to retroactively describe a fix that had not happened yet at the time it
was written.

The one thing PR #126 does *not* yet reflect is the corrected root-cause
narrative this document now supersedes it with (`CAPABILITY_MODEL_GAP` ->
now fixed; current blocker precisely `SEMANTIC_EVIDENCE_GAP`/
`DATA_CONTRACT_GAP` only). Recommended follow-up (not implemented here,
not requested by this mission): a future, separate docs-only PR adding a
"Capability #2 remediation (P3.xxI.5B-R) post-merge scorecard" section to
`docs/p3xxi5-intelligence-breadth-expansion-program.md`, mirroring the
section this program already added for Capability #1's own remediation.
This is a recommendation only -- no such PR was opened, and PR #126 was
not merged or closed by this work.
