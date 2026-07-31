# WP-2.TI-A Core Tenant Referential Integrity

## Purpose and invariant

WP-2.TI-A adds database-enforced tenant consistency to the core ingestion, raw-data,
processing, and lineage domain. For each covered child-to-parent relationship:

`child.organization_id == parent.organization_id`

This is defense in depth. Existing application-service tenant validation remains
authoritative and unchanged.

## Parent identities

The migration adds these unique `(organization_id, id)` constraints:

- `uq_source_systems_org_id`
- `uq_datasets_org_id`
- `uq_ingestion_batches_org_id`
- `uq_dataset_versions_org_id`
- `uq_raw_storage_objects_org_id`
- `uq_processing_runs_org_id`
- `uq_lineage_nodes_org_id`

## Tenant-aware foreign keys

All use `(organization_id, parent_id)`, reference the parent
`(organization_id, id)`, and retain `ON DELETE RESTRICT`:

- `fk_ingestion_batches_org_source_system`
- `fk_datasets_org_source_system`
- `fk_dataset_versions_org_dataset`
- `fk_dataset_versions_org_ingestion_batch`
- `fk_raw_storage_objects_org_source_system`
- `fk_raw_storage_objects_org_ingestion_batch`
- `fk_raw_storage_objects_org_dataset_version`
- `fk_raw_storage_objects_org_supersedes`
- `fk_raw_record_references_org_raw_storage_object`
- `fk_raw_record_references_org_dataset_version`
- `fk_processing_runs_org_ingestion_batch`
- `fk_processing_runs_org_dataset_version`
- `fk_processing_runs_org_parent_run`
- `fk_lineage_edges_org_from_node`
- `fk_lineage_edges_org_to_node`
- `fk_lineage_edges_org_processing_run`
- `fk_lineage_events_org_processing_run`

Existing single-column foreign keys are intentionally retained. They continue to
enforce parent existence, while the additive composite keys enforce tenant agreement
without depending on engine-generated legacy constraint names.

## Supporting indexes

The corresponding `(organization_id, parent_id)` indexes are:

- `ix_ingestion_batches_org_source_system_id`
- `ix_datasets_org_source_system_id`
- `ix_dataset_versions_org_dataset_id`
- `ix_dataset_versions_org_ingestion_batch_id`
- `ix_raw_storage_objects_org_source_system_id`
- `ix_raw_storage_objects_org_ingestion_batch_id`
- `ix_raw_storage_objects_org_dataset_version_id`
- `ix_raw_storage_objects_org_supersedes_raw_object_id`
- `ix_raw_record_references_org_raw_storage_object_id`
- `ix_raw_record_references_org_dataset_version_id`
- `ix_processing_runs_org_ingestion_batch_id`
- `ix_processing_runs_org_dataset_version_id`
- `ix_processing_runs_org_parent_run_id`
- `ix_lineage_edges_org_from_node_id`
- `ix_lineage_edges_org_to_node_id`
- `ix_lineage_edges_org_processing_run_id`
- `ix_lineage_events_org_processing_run_id`

## ORM decision

The existing `IngestionBatch.source_system`, `Dataset.source_system`,
`DatasetVersion.dataset`, and `DatasetVersion.ingestion_batch` relationships and their
existing collection counterparts declare `foreign_keys=` explicitly. This resolves
the additional SQLAlchemy join paths without `primaryjoin`, `overlaps`, public
attribute changes, or relationship redesign.

## Migration and diagnostics

Revision `20260731_0025` follows `20260730_0024`. Upgrade first runs read-only
precondition queries for all 17 relationships. The checks detect null tenant IDs,
orphaned referenced IDs, cross-tenant references, and duplicate parent
`(organization_id, id)` targets. Any violation aborts the migration; WP-2.TI-A does
not repair or fabricate data.

Upgrade creates the seven parent constraints, 17 composite foreign keys, then 17
indexes. Downgrade removes those objects in reverse order and leaves the historical
single-column foreign keys and all data unchanged.

## PostgreSQL and SQLite behavior

PostgreSQL is the authoritative managed runtime. SQLite remains an isolated test
runtime with `PRAGMA foreign_keys=ON`. Both engines reject cross-tenant parent
updates, retain same-tenant references, and allow null values on the six pre-existing
nullable parent-reference columns.

Validation evidence must record the actual PostgreSQL version, diagnostic counts,
migration round trip, drift result, offline SQL generation, and full test results
before certification. Passing local metadata or SQLite checks alone is not production
validation.

The implementation validation used disposable PostgreSQL 17.10. All 17 relationship
diagnostics and seven duplicate-parent checks returned zero violations. The
PostgreSQL-marked suite passed 20 tests, the default suite passed 339 tests with 20
PostgreSQL-marker skips, and the migration upgrade/downgrade/re-upgrade, drift check,
and offline SQL generation all passed.

## Scope and limitations

WP-2.TI-A does not change services, APIs, schemas, organization-root references,
polymorphic `entity_id` fields, global/shared references, or public ORM attributes.
It covers only the core tables and 17 relationships listed above. Broader tenant
referential integrity remains sequenced into WP-2.TI-B, WP-2.TI-C, and WP-2.TI-D.
