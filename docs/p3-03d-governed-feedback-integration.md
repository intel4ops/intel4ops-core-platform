# P3.03D-B Governed Feedback Integration

## Purpose

D-B connects Canonical Mapping execution to Tenant Operational Memory. It is the first
live producer of governed memory evidence — before this package, `record_candidate()`
existed in D-A but had no caller anywhere in the codebase.

The governing invariant is unchanged from D-A:

> Memory suggests. Canonical Mapping executes. Trust independently validates.

D-B does not make memory authoritative. It makes Canonical Mapping capable of producing
governed, tenant-scoped `FIELD_MAPPING` evidence from its own successful executions.

## What is learned

Exactly `FIELD_MAPPING` evidence, from a successful `MappingRun`. Nothing else:
`SCHEMA_PATTERN`, `TERMINOLOGY`, customer context, Findings, Trust, Economics,
Recovery, AI profiling, and cross-tenant/global/industry-shared learning are all
out of scope for D-B v1.

## Trigger

`MappingExecutionService.execute()`, strictly after the authoritative `MappingRun`
has already been committed. Evidence is registered only when:

- `run.status == MappingRunStatus.COMPLETED.value` (a `PARTIALLY_COMPLETED` run
  produces no evidence — a mixed-outcome run is not treated as clean confirmation
  that the template's field mappings work for this schema), and
- `run.source_schema_id is not None` (historical pre-CM-01 runs never produce
  evidence).

One candidate is registered per `FieldMapping` row belonging to the run's
`MappingTemplateVersion` — not per record, since the field-to-canonical binding is
template-level and does not vary across the records in a run.

## Field resolution

For each `FieldMapping`:

- `source_field_path` — from the `FieldMapping` row itself.
- `source_field_type` — resolved by an exact `(organization_id, source_schema_id,
  field_path)` lookup against `SourceField`. If no matching row exists (the template
  references a field path that was never discovered into this schema), that field is
  **skipped** — never fabricated, guessed, or inferred from raw record values.
- `canonical_type_kind` / `canonical_type_id` / `canonical_field_definition_id` /
  `canonical_field_code` — resolved from the authoritative `CanonicalFieldDefinition`
  referenced by the `FieldMapping`.
- `schema_fingerprint` — `MappingRun.schema_fingerprint_snapshot` (CM-01's frozen,
  execution-time snapshot), never the current live `SourceSchema` fingerprint.
- `mapping_transform_code` — the first `MappingTransformation.transformation_type`
  for the field mapping, if one exists; otherwise `None`.
- `unit_context` — always `None`. No structural source exists for it in the current
  schema, and it is optional on `FieldMappingPayload`.

## Actor semantics

Registration always calls `record_candidate(..., actor_user_id=None,
actor_role="system")`. The person who triggered the mapping run is never treated as
the person confirming a field mapping — those are different acts. D-A's
`record_candidate()` signature already defaulted to a system actor before D-B existed;
this package is its first caller.

## Memory status

The resulting memory is always `OBSERVED`. D-B never calls `decide()`. Promotion to
`CONFIRMED` / `CORRECTED` / `REJECTED` remains exclusively a human decision through
the existing `POST /operational-memories/{id}/decisions` endpoint. Because
`OperationalMemoryService.retrieve()` only ever returns `CONFIRMED`/`CORRECTED`
memories, D-B-produced evidence cannot influence anything — including a later
mapping run — until a human has independently reviewed and confirmed it.

## CM-02 replay interaction

`MappingExecutionService.execute()` has two return points that both occur strictly
before evidence registration: the up-front idempotency check (sequential replay) and
CM-02's `except IntegrityError` recovery branch (concurrent-race replay). Evidence
registration sits after the mapping loop and after the run's own `db.commit()`, so
neither replay path can ever reach it. A five-way concurrent identical execution
therefore still produces exactly one evidence registration per eligible field per
round, proven under real PostgreSQL load in
`tests/test_postgres_migrations.py::test_dbfeedback_concurrent_identical_execution_registers_evidence_exactly_once`.

## Transaction and failure isolation

Evidence registration happens strictly *after* `execute()`'s own `db.commit()` for the
`MappingRun`. This is a hard requirement, not a convenience: `record_candidate()`
performs its own internal commit and, on an unrecognized `IntegrityError`, its own
internal rollback. If it were called before the `MappingRun`'s commit, a rollback
inside `record_candidate()` would silently destroy the entire in-progress mapping
transaction as well. Placing registration after the run is durably committed makes
that impossible.

Each field's registration is independently wrapped in a broad
`try/except Exception: db.rollback(); continue`. Evidence registration is best-effort:
one field's failure does not prevent other eligible fields in the same run from being
registered, and no failure of any kind can affect the already-persisted `MappingRun`,
which the caller always receives regardless.

## Provenance

`MemoryProvenance(source_schema_id=run.source_schema_id,
mapping_template_version_id=run.template_version_id,
canonical_field_definition_ids=[field_mapping.canonical_field_definition_id])`.
`mapping_record_result_id` is left `None` — this evidence describes the template's
field mapping against a concrete schema, not any single raw record.

## Idempotency and source fingerprint

The per-field evidence idempotency key is deterministic:
`mapping-run:{run.id}:field-mapping:{field_mapping.id}`. The source fingerprint is a
SHA-256 (via the module's existing `_fingerprint()` helper) over the run id, field
mapping id, source field path/type, canonical field definition id, and schema
fingerprint. Repeated matching observations across separate runs against the same
schema increase `support_count` on the existing memory item through D-A's own
identity/versioning logic; they never fabricate a new identity or promote lifecycle
state.

## Boundaries unchanged by this package

No new table, column, index, or migration. No new entitlement, role, or public API
endpoint — registration is an internal call inside an already-authorized
`MappingExecutionService.execute()`. `MappingReview.override_value` is not
interpreted automatically; no automatic `CORRECT` or `REJECT` is introduced. No AI,
embedding, or vector dependency of any kind.

## Deferred

- Registering evidence for `PARTIALLY_COMPLETED` runs, filtered to the fields that
  succeeded.
- `MappingReview` → automatic `CORRECT` (blocked on `override_value`'s untyped,
  record-level shape).
- D-C retrieval/reuse integration and memory-origin lineage.
- `SCHEMA_PATTERN` / `TERMINOLOGY` evidence sources.
