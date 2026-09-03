# P3.xxI.2B — Governed Cross-Dataset Rate Lookup

## Status

Implementation complete on the dedicated branch; local gates pass. Merge,
deployment, and post-merge Wave 1 certification remain owner-gated.

## Handoff reconciliation

- Authoritative base: `origin/main` at
  `0e5b96e04b231d8f597a20c8fd103526c02bd84f`.
- The starting checkout was clean and still on the already-completed
  P3.xxI.2 report branch.
- No Claude worktree, stash, local/remote P3.xxI.2B branch, untracked source,
  or reachable in-progress commit existed in this clone. Nothing was reset,
  discarded, or overwritten.
- Work continued on `feature/p3xxi2b-governed-cross-dataset-rate` from the
  authoritative base.

## Problem and confidence evidence

Real contract/rate data could identify `contract_id` and `labor_rate`, but
the generic confidence components stopped near `accepted_with_flag` (~0.85):

| Evidence component | Before | Diagnosis |
|---|---:|---|
| `FIELD_NAME_ALIAS_MATCH` | present | Necessary but not independently authoritative. |
| `VALUE_PATTERN_MATCH` | absent/inadequate | Numeric shape alone cannot prove a value is a rate. |
| `DATASET_ROLE_COMPATIBILITY` | present | Contract/labor role helps but is not decisive. |
| `DATATYPE_COMPATIBILITY` | present | Numeric/identifier datatype is necessary but generic. |
| `CROSS_DATASET_OVERLAP` | fixture-dependent | Useful for repeated identifiers, not guaranteed for a rate field. |
| `NEIGHBOR_FIELD_CONTEXT` | present where roles overlap | Generic context, still insufficient. |
| `SIBLING_CONCEPT_CORROBORATION` | missing | The reusable decisive evidence was a governed contract reference co-located with an explicitly hourly rate, plus a work-order/contract bridge. |

No threshold changed and no `accepted_with_flag` decision is manually
promoted. The registry now distinguishes the canonical meanings
`duration_hours`, `hourly_rate`, `contract_id`,
`effective_from_timestamp`, `effective_to_timestamp`, and
`unit_of_measure`. Exact sibling-context alternatives let a concept gain
authority from one of several legitimate shapes without global score
inflation. The semantic calibration suite caught and prevented an initially
broader identifier-pattern approach.

## Governed execution chain

The implementation follows this bounded chain:

1. a governed work-order quantity record;
2. a unique governed work-order-to-contract reference;
3. exactly one governed rate row for that contract;
4. effective-from/effective-to applicability at the activity timestamp;
5. normalized, compatible quantity/rate unit;
6. compatible known currency, or both sides unknown under the existing
   currency policy;
7. expected amount = quantity × applicable rate;
8. the unchanged P3.xxI.2A safe actual-billing side; and
9. the existing `REVENUE-AMOUNT-VARIANCE` materiality comparison and
   governed publisher.

The lookup contains no filename, tenant, customer, simulation, or industry
branch. Relationship ambiguity, multiple applicable rates, missing temporal
evidence for bounded rates, unresolved units, and known currency mismatch all
abstain. Missing rate evidence never becomes zero. Rate-dataset lineage is
included as a contributing dataset and in calculation-trace references.

## Safety and generalization

- Same-row quantity × unit price remains unchanged.
- P3.xxI.2A's `NO_GOVERNED_EVIDENCE != ZERO` gates remain intact.
- Multiple equally applicable rates abstain.
- Wrong contract relationships do not match.
- Expired and future rates do not match.
- Unit and currency mismatches abstain; no UOM or FX value is invented.
- Unresolved rate or quantity semantics abstain because orchestration passes
  only effectively governed fields.
- A non-labor fixture using an explicit `each`/`unit` basis resolves through
  the same lookup invariant.
- The orchestration-level fixture proves the full labor-hours → contract →
  hourly-rate → invoice → finding chain without raw-schema control flow.

## Tests

| Gate | Result |
|---|---:|
| Cross-dataset rate, readiness, and complete revenue variance tests | 55 passed |
| Ordered semantic/entity/process/capability/publisher/Trust/validation regression | 181 passed |
| Full non-PostgreSQL suite | 1,656 passed, 82 PostgreSQL-only deselected |
| Ruff format check | 795 files already formatted |
| Ruff lint | pass |
| Mypy | 613 source files, pass |
| Disposable PostgreSQL | unavailable locally; required in GitHub Quality Gate before merge |

Two dependency-level deprecation warnings (`fastapi.testclient` and
Starlette's AnyIO alias) remain pre-existing and non-failing.

## Changed scope

- canonical registry/pack data, alternative-measure readiness, and generic
  sibling-context corroboration;
- one framework-light governed rate resolver;
- Revenue Amount Variance orchestration/data-field wiring;
- focused unit, integration, safety, semantic, and orchestration tests; and
- this report.

No schema migration was required. No truth, XDOM-A, XDOM-B, MAINT-001,
Rental entity scope, new capability, frontend, Wave 2, E.6, E.7, FX
subsystem, UOM ontology, contract engine, or E.3/E.4 redesign was introduced.

## Pre-merge classification

**P3.xxI.2B IMPLEMENTED — AWAITING CI AND OWNER MERGE AUTHORIZATION**

Post-merge certification must compare against the P3.xxI.2A baseline:
precision 100%, capability-scoped recall 20.48%, and economic-value capture
12.06%. No live certification is claimed before authorized merge/deploy.
