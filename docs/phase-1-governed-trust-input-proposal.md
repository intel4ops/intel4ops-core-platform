# Governed Trust Input and Canonical Mapping Proposal

## Decision status

This is the architecture proposal for FR-015 and FR-016. It does not authorize
or implement either capability. Inline/manual Trust input remains supported and
must be identified as such in evidence and integration tests.

The recommended delivery vehicle is a new WP-2.x foundation extension completed
before broader Phase 3 intelligence work. It is too large for a correction to
WP-2.05 or WP-2.06 because it introduces governed aggregates, version
lifecycles, materialization policy, and retention responsibilities.

## Governed Trust input

A Trust assessment should select one immutable input specification:

- `inline_manual`: the current bounded record payload;
- `dataset_version`: a complete immutable DatasetVersion;
- `raw_selection`: an ordered, bounded set of RawRecordReference identifiers;
- `raw_object`: a RawStorageObject plus an immutable selection predicate.

Every governed selection must belong to the assessment organization. Tenant
scope is resolved before lifecycle, selection, or existence details. Submission
persists selected object identifiers, checksums, ordered record identifiers,
selection criteria, record count, and a canonical SHA-256 snapshot digest.
Lineage connects the source objects, snapshot, anchored ProcessingRun, and
assessment.

DatasetVersion is the preferred default because it already binds a dataset,
batch, and source. RawRecordReference supports precise sampling. RawStorageObject
is appropriate only when its format and selection are deterministic. A digest
without retained identifiers is insufficient evidence.

Synchronous execution is bounded by byte and record limits. Larger selections
create an asynchronous ProcessingRun anchored to the DatasetVersion or raw
objects. Authorization is checked when accepted and again when a worker resolves
the snapshot. Prior assessments always use their persisted snapshot contract.

Idempotency fingerprints include organization, dataset, input mode, snapshot
digest, rule configuration, evaluation time, canonical schema version, and
mapping version. Existing inline clients remain compatible; responses identify
`inline_manual` and do not imply linkage to stored upstream records.

## Persistent canonical schema and mapping

The proposed aggregates are:

- `CanonicalSchemaDefinition`: stable code, ownership scope, industry pack,
  lifecycle, and governance identity;
- `CanonicalSchemaVersion`: immutable semantic version, fields, types, units,
  currency behavior, required/optional status, validation rules, compatibility,
  temporal validity, digest, and provenance;
- `SourceSchemaVersion`: source and DatasetVersion-bound observed schema,
  immutable field inventory, digest, and provenance;
- `MappingDefinition`: stable source-to-canonical mapping identity and ownership;
- `MappingVersion`: immutable field mappings, transformations, unit/currency
  conversions, defaults, validation policy, temporal validity, compatibility,
  digest, and approval evidence.

Ownership is exactly one of shared, industry-pack, or organization scope.
Organization-owned definitions never resolve outside their tenant. Shared and
industry-pack assets resolve only through applicable active assignments.

Mapping lifecycle is `draft -> validated -> published -> superseded -> retired`.
Published versions are immutable. Superseding or retiring affects new
resolution only; prior assessments retain exact version keys and digests.
Transformations use a bounded declarative registry, not executable user code.
Field provenance records source and target fields, operation code/version,
types, unit/currency policy, and validation result.

Compatibility is independently validated as backward, forward, full, or
breaking. Temporal overlap for published versions in the same scope is rejected
unless a governed priority rule exists.

## Incremental implementation path

1. Persist immutable governed-input snapshots and add DatasetVersion and bounded
   raw-selection Trust modes.
2. Persist canonical and source schema definitions and immutable versions.
3. Add governed mapping definitions, immutable versions, validation, and
   lifecycle transitions.
4. Materialize mapped records or a governed projection with digests and lineage.
5. Bind Trust to immutable input, schema, mapping, and processing versions.
6. Classify existing assessments as `inline_manual`, preserve nullable version
   references for compatibility, and certify downgrade/re-upgrade behavior.

Each step requires additive migrations, tenant-isolation and idempotency tests,
bounded evidence checks, and disposable PostgreSQL lifecycle validation.
FR-013 source history, FR-017 disputes/overrides, FR-038 shared audit history,
and FR-039 DAL normalization remain separate architecture decisions.
