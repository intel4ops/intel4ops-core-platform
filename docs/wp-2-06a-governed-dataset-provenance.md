# WP-2.06A Governed Dataset Provenance

## Decision and scope

Reliability, Statistical, and Forecasting execution previously accepted dataset
references, fingerprints, and lineage strings asserted by the caller. Those strings
remain readable compatibility/audit fields, but they are no longer accepted by create
contracts or trusted as governed identity.

The authoritative execution inputs are now `dataset_id` and `dataset_version_id`.
`dataset_version_id` is the lineage anchor. The server resolves the exact tenant-owned
`DatasetVersion`, derives its `IngestionBatch` and `SourceSystem`, and cross-checks the
source system against `Dataset.source_system_id`. It never selects a latest version.
Trust remains bound to the selected dataset, and version and batch lifecycle states
must be execution-eligible.

`LineageNode` is deliberately not an execution gate. It is a broader graph and
tenant-integrity concern; the immutable DatasetVersion-to-batch chain is sufficient
for this bounded package. Composite tenant foreign keys remain deferred to WP-2.TI.

## Contracts and identity

Direct Reliability, Statistical, Forecasting, and Forecast Actual creates require both
governed UUIDs and use Pydantic `extra="forbid"`. Supplying the removed legacy fields
therefore returns deterministic validation errors. Orchestration also requires the
exact dataset version and derives the display reference from the dataset. Statistical
and Forecasting adapters pass governed IDs, and direct adapter validation failures are
translated to the orchestration `{code, message}` error contract.

The persisted execution identity includes organization, dataset, version, derived
batch and source system, Trust and readiness identities, governed definition/version,
method/version, and normalized analytical inputs. Forecast actuals independently bind
their own dataset and version. Server-derived compatibility values are:

- `dataset_reference`: `Dataset.code`;
- `dataset_fingerprint`: the normalized source checksum, or a deterministic version
  identity fingerprint when no checksum is available;
- `source_lineage_reference`: an audit string containing the exact dataset, version,
  batch, and source-system UUIDs.

## Migration

Alembic revision `20260730_0024` adds nullable UUID foreign keys to the three execution
tables and forecast actuals, using `ON DELETE RESTRICT`, plus dataset and
dataset-version indexes. Historical migrations are unchanged.

The migration backfills execution rows only when the organization-scoped dataset code,
version checksum/fingerprint, batch relationship, and dataset/batch source system agree
and produce exactly one match. It does not infer a latest version and does not backfill
forecast actuals without deterministic evidence. Unmatched or ambiguous historical
rows remain null. A later migration may enforce non-null only after an operational
inventory proves that all retained rows are mapped or explicitly archived.

## Rollout, rollback, and validation

Deploy the migration before the API version that requires governed IDs. A one-revision
downgrade removes only the new indexes, constraints, and columns; callers must be
rolled back at the same time. Existing read fields remain backward compatible.

Validation covers strict schemas, tenant isolation, Trust binding, lifecycle rejection,
identity-safe replay, both orchestration bridges, read compatibility, migration
upgrade/downgrade/re-upgrade, PostgreSQL constraints, and offline SQL generation.
Exact command results belong in the implementation handoff and must not be represented
as independent certification.

Excluded from WP-2.06A: WP-2.TI, observability, asynchronous workers, rate limiting,
commercial behavior, new analytical methods, Reliability orchestration registration,
and unrelated Phase 2A remediation.
