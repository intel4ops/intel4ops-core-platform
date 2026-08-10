# CM-01 Canonical Mapping Execution Provenance Hardening

## Problem

Before CM-01, a `MappingRun` durably recorded which `DatasetVersion` it executed against, but not
which concrete `SourceSchema`. A `DatasetVersion` can have more than one discovered `SourceSchema`
(`SourceSchemaService.for_dataset_version` returns a list, not a single row), so `DatasetVersion`
alone cannot answer "which exact schema governed this mapping execution?" `MappingExecutionService`
never queried `SourceSchema`/`SourceField` at all — each field's value was read directly from the
caller-supplied record dictionary by `source_field_path`, independent of any discovered schema.

This gap blocked P3.03D-B (governed feedback into Operational Memory), which needs a `source_field_type`
and `schema_fingerprint` for every `FIELD_MAPPING` fact — neither of which existed anywhere in the
execution path. CM-01 closes that gap. It does not implement P3.03D-B, Trust changes, or any
Operational Memory behavior.

## Explicit schema selection

`MappingRunCreate.source_schema_id` is now a required field. The caller must supply the exact
`SourceSchema` the execution is governed by — obtained via the existing
`GET /source-schemas/{dataset_version_id}` endpoint, which already lists every candidate schema for
a dataset version. CM-01 introduces no new listing endpoint and no new frontend work; the data needed
to make the choice was already exposed before this change.

There is no inference of a "latest" or "most likely" schema anywhere in `MappingExecutionService.execute`.
If the caller omits `source_schema_id`, the request fails Pydantic validation before it ever reaches
the service.

## New MappingRun fields

Two nullable columns were added to the existing `mapping_runs` table (migration `20260814_0040`):

- `source_schema_id` (`UUID`, nullable) — the concrete schema selected for this execution.
- `schema_fingerprint_snapshot` (`VARCHAR(255)`, nullable) — `SourceSchema.schema_fingerprint`,
  copied once at execution time and never re-read afterward.

A tenant-safe composite foreign key, `fk_mapping_runs_org_source_schema`, ties
`(organization_id, source_schema_id)` to `(source_schemas.organization_id, source_schemas.id)` with
`ON DELETE RESTRICT` — matching every other tenant-owned relationship in this module. A supporting
index, `ix_mapping_runs_org_source_schema`, covers `(organization_id, source_schema_id)`.

No new table was created. No historical migration was modified.

## Why the columns are nullable at the database level

`SourceSchema` was never recorded for any run created before CM-01, and there is no reliable way to
reconstruct which schema (if any specific one) governed a historical execution — multiple schemas may
have existed for the same dataset version at that time, and the raw-dictionary field lookup never
referenced any of them. **CM-01 does not backfill, infer, or guess historical provenance.** Historical
rows keep `source_schema_id = NULL` and `schema_fingerprint_snapshot = NULL` permanently, which
honestly means "concrete schema provenance was not captured for this run." Every row created after
this migration is required, at the application layer, to supply a real schema — the database-level
nullability exists solely to accommodate rows that already existed, not to permit new gaps.

## Execution validation

Before creating a `MappingRun`, `MappingExecutionService.execute` now:

1. Resolves `SourceSchema` by `(id = payload.source_schema_id, organization_id = organization_id)`.
   A missing or cross-tenant schema returns a safe `404 SOURCE_SCHEMA_NOT_FOUND` — tenants cannot
   distinguish "doesn't exist" from "belongs to another tenant."
2. Requires `SourceSchema.dataset_version_id == payload.dataset_version_id`. A mismatch returns
   `409 SOURCE_SCHEMA_DATASET_VERSION_MISMATCH`. There is no substitution and no selection of a
   different schema from the same dataset — the request simply fails.
3. Rejects schemas whose `status` is `changed` or `incompatible` (the existing `SchemaStatus`
   vocabulary, the same two values Operational Memory's own staleness detection already treats as
   invalid) with `409 SOURCE_SCHEMA_NOT_USABLE`. `discovered`, `stable`, `approved`, and `unknown`
   remain usable, unchanged from existing repository semantics.

None of this changes existing missing-field or validation-failure execution semantics.
`FieldMapping.source_field_path` is still read directly from the caller-supplied record dictionary,
exactly as before CM-01. **CM-01 does not require that a `FieldMapping.source_field_path` exist as a
discovered `SourceField` in the selected schema.** That is a real, separate, behavior-changing
decision (it would introduce a new class of execution failure) and is explicitly deferred — see
Known Limitations.

## Idempotency

No new idempotency mechanism was introduced. `MappingRun`'s existing idempotency key + request
fingerprint already covers the full `MappingRunCreate` payload (`_fingerprint(payload.model_dump(mode="json"))`),
and `source_schema_id` is now a field on that same payload — so it is automatically included in the
fingerprint with no additional code. Replaying the same idempotency key with the same
`source_schema_id` returns the original run. Replaying the same idempotency key with a *different*
`source_schema_id` returns `409 IDEMPOTENCY_CONFLICT`, exactly like any other payload change — a run
is never silently reused across a different schema selection.

## Tenant isolation

Defense in depth, matching the rest of `canonical_mapping_service.py`: an explicit service-level
tenant check (returning a safe 404, not a raw constraint violation) backed by a real composite
foreign key at the database level. A direct SQL insert referencing another tenant's `SourceSchema`
is rejected by PostgreSQL itself, independent of the service layer.

## Reproducibility

`SourceSchema` itself is not immutability-guarded in this repository (no `before_update`/`before_delete`
event listeners, unlike `MappingTemplateVersion` or `OperationalMemoryVersion`) — CM-01 does not change
that. `schema_fingerprint_snapshot` exists specifically so a `MappingRun`'s provenance survives even if
the live `SourceSchema` row is later mutated: the snapshot is copied once and never re-read. A newer
schema discovered after a run was created never changes that run's recorded provenance.

## Auditability

For any `MappingRun` created after this change, the existing, already-immutable records answer: who
executed it (`created_by_user_id`), what dataset version and template version it used, which exact
`SourceSchema` governed it, what that schema's fingerprint was at execution time, and when it ran.
No new audit table was introduced — this reuses `mapping_runs` itself as the auditable record. This
contributes evidence toward auditability and change-traceability controls; it does not by itself
constitute or claim SOC 2 compliance.

## No Trust change, no Operational Memory change

`MappingTrustSignalService` does not read `source_schema_id` or `schema_fingerprint_snapshot` — it
was not modified and its behavior is unchanged. No Operational Memory model, schema, service, or API
was touched. CM-01 does not implement P3.03D-B; it produces the provenance that a future,
independently-scoped P3.03D-B revisit would need in order to resolve `source_field_type` and
`schema_fingerprint` for a `FIELD_MAPPING` fact.

## Known limitations / deferred

- **Field-level enforcement deferred.** Whether `FieldMapping.source_field_path` must exist as a
  discovered `SourceField` in the selected schema is a genuine, separate product/architecture decision
  with its own risk profile (it would reject mapping runs that currently succeed). Not implemented here.
- **`SourceSchema` immutability hardening deferred.** The live schema row can still be mutated after
  a `MappingRun` references it; `schema_fingerprint_snapshot` mitigates this for provenance purposes
  but does not close the underlying gap.
- **P3.03D-B governed feedback deferred.** CM-01 makes `source_field_type` and `schema_fingerprint`
  resolvable for the first time, but does not itself decide how or whether Canonical Mapping feedback
  should flow into Operational Memory.
- **P3.03D-C retrieval/reuse integration deferred**, unaffected by this change either way.
