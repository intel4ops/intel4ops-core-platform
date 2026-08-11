# P3.03D-C.1 Lineage-Aware Feedback Hardening

## Purpose

D-C added `FieldMapping.origin_memory_version_id`: a durable, immutable record of
which Operational Memory suggestion (if any) a `FieldMapping` was accepted from.
D-B's evidence-registration path never read it. The result was a real
self-reinforcement loop:

> memory X suggests a mapping → user accepts X unchanged → `MappingRun` succeeds
> → D-B records the execution as new evidence → X's `support_count` increases →
> X ranks higher in future suggestions → repeated executions of the same
> accepted mapping continue inflating `support_count`

The governing invariant for this package:

> **Memory-derived execution is not automatically independent evidence.**

## What changed

One private classification helper in `app/services/canonical_mapping_service.py`,
called from `_register_single_field_mapping_evidence()` before it would otherwise
unconditionally call `OperationalMemoryService.record_candidate()`:

```python
@staticmethod
def _is_memory_derived_unchanged(
    db: Session,
    organization_id: UUID,
    field_mapping: FieldMapping,
) -> bool: ...
```

If it returns `True`, evidence registration for that field is skipped entirely
for that run — no `record_candidate()` call, no new memory version, no support
count change. Otherwise, D-B's existing, unmodified registration path runs
exactly as before.

## Classification algorithm

1. If `field_mapping.origin_memory_version_id` is `NULL` → not memory-derived.
   Call `record_candidate()` normally (unchanged, pre-existing behavior; `NULL`
   means "no lineage recorded," not proven independent authorship).
2. Otherwise, fetch the referenced `OperationalMemoryVersion`, filtering on
   **both** `id` and `organization_id == organization_id` (tenant filtering is
   mandatory; a foreign-tenant or corrupted reference must never be read).
3. If no same-tenant version resolves → fail safe. Treat as not memory-derived;
   call `record_candidate()` normally.
4. If it resolves, compare the version's own **frozen, historical**
   `value_payload["canonical_field_definition_id"]` against
   `field_mapping.canonical_field_definition_id`.
   - Equal → **memory-derived, unchanged**. Skip registration.
   - Different → **memory-derived, modified**. Call `record_candidate()`
     normally; D-A's existing identity/value matching decides the outcome
     (see below).

## Why the origin's frozen payload, never current item status

The comparison in step 4 deliberately never inspects the memory item's
*current* governance status (`CONFIRMED`/`CORRECTED`/`REJECTED`/`DEPRECATED`/
`AMBIGUOUS`/stale). It only ever reads the specific, immutable
`OperationalMemoryVersion` row pinned by `origin_memory_version_id` at the
moment the `FieldMapping` was created.

This keeps the skip decision deterministic over time. A `FieldMapping` that
was legitimately created from a `CONFIRMED` suggestion X remains classified as
an unchanged use of X for the rest of its life, even after X's item is later
`CORRECT`ed, `DEPRECATE`d, or made `AMBIGUOUS` by unrelated evidence — because
the `FieldMapping` itself was never rewritten and still reflects the original,
once-trustworthy decision. Using live status instead would make the same
`FieldMapping`'s classification flip unpredictably based on unrelated,
concurrent governance activity.

## Memory-derived modified: no new correction semantics

When the submitted target differs from the origin's recorded target,
`record_candidate()` is called with the field's actual, truthful data —
nothing about the call is altered. If that evidence's identity happens to
match the origin item (same organization, subject, and context), D-A's
existing, unmodified `same_value` check naturally detects the divergence and
marks the item `AMBIGUOUS` (`contradiction_count += 1`, `is_stale = True`),
exactly as it already does for any two disagreeing observations. D-C.1
introduces no new auto-`CONFIRM`, auto-`CORRECT`, or auto-`REJECT` behavior —
human governance via `POST .../decisions` remains the only way memory status
changes.

## Tenant isolation and corrupted-data safety

The `OperationalMemoryVersion` lookup always filters on
`organization_id == organization_id`, mirroring D-C's own
`_validate_origin_memory_lineage` pattern. A `FieldMapping` cannot normally
carry a foreign-tenant or nonexistent `origin_memory_version_id` — D-C's
write-time validation prevents it — but if corrupted or direct-database data
ever produced one, the lookup simply fails to resolve a same-tenant match and
classification falls through to "not memory-derived," i.e. ordinary,
independent evidence registration for the executing tenant. No foreign
tenant's memory is ever read or affected, and the authoritative `MappingRun`
is never put at risk: the classification lives inside D-B's existing
per-field `try/except Exception: db.rollback(); continue` failure-isolation
boundary, unchanged.

## What did not change

- `app/models/operational_memory.py`, `app/schemas/operational_memory.py`,
  `app/services/operational_memory_service.py`,
  `app/api/operational_memory_routes.py` — untouched. No D-A contract change.
- `MemoryProvenance` — unchanged. The durable lineage fact already lives on
  `FieldMapping.origin_memory_version_id`; duplicating it into every
  subsequent evidence record's provenance would be redundant.
- `source_fingerprint` composition — unchanged. It already includes
  `field_mapping_id`, which 1:1-determines the (immutable) origin lineage.
- `support_count` / `confirmation_count` semantics — unchanged. D-C.1 only
  narrows *when* D-B calls `record_candidate()`; it never redefines what
  either counter means.
- Trust — unchanged. This package only affects Operational Memory evidence
  registration, which already runs strictly after `MappingRun`'s own commit
  and has never mutated `TrustAssessment`.
- No new table, column, or migration. Alembic head remains `20260815_0041`.

## Deferred

- Structured observability for skip decisions (e.g. an audit event recording
  "evidence registration was skipped for field X because it was an unchanged
  use of memory version Y"). The current best-effort, silent-continue
  registration path has never emitted such events for any of its existing
  failure/skip modes; adding this is a natural, separately-scoped
  enhancement, not required for correctness here.
- D-D effectiveness/acceptance-rate measurement built on top of this
  classification.
