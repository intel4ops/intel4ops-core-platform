# Raw Storage and Lineage Foundation

WP-2.05 adds the governed traceability layer between dataset versions and future
canonical mapping:

```text
source system -> ingestion batch -> dataset version -> raw storage object
                                                     -> record reference
                                                     -> processing run
```

Arrows always mean upstream source to downstream derived object. PostgreSQL stores
metadata, integrity facts, opaque storage references, processing history, and lineage.
It does not upload, download, parse, or store large file bodies.

## Records and automatic lineage

- A raw storage object identifies one received artifact. Its source, ingestion,
  storage, checksum, size, media, and receipt identity become immutable once sealed.
- A raw record reference identifies a row, page, message, event, or segment without
  storing the complete payload.
- A processing run records execution metadata and counts.
- Lineage nodes bind existing tenant entities to the graph. Edges and events are
  append-only.

Raw-object registration creates nodes for its source system, batch, dataset, version,
and raw object. It adds source → batch, batch → version, dataset → version, and version
→ raw-object edges. Record registration adds raw-object → record-reference.

## Integrity and lifecycle

SHA-256 requires 64 hexadecimal characters, SHA-512 requires 128, and MD5 requires 32.
SHA-256 is the default. MD5 is supported only for source compatibility.

| State | Allowed next states |
| --- | --- |
| registered | receiving, received |
| receiving | received, quarantined |
| received | verifying, quarantined |
| verifying | sealed, quarantined, received |
| sealed | superseded, archived, deletion_requested |
| quarantined | verifying, archived |
| superseded | archived |
| archived | deletion_requested |
| deletion_requested | deleted_reference, archived |
| deleted_reference | none |

Sealing requires verified integrity. `deleted_reference` reports physical unavailability;
metadata, audit events, and lineage remain. Processing runs move from created through
queued/running to completed, partially completed, failed, cancelled, or quarantined.
Failed and quarantined runs may retry to queued.

## Retention, security, and authorization

Retention expiry never triggers deletion. Legal hold requires a reason, is audited, and
blocks deletion requests. WP-2.05 does not delete cloud objects.

Storage references must be opaque and credential-free. Validation rejects embedded
credentials, connection strings, bearer/service-role material, known signature/token
parameters, presigning parameters, and nested secret keys. Validation responses exclude
rejected input. Normal API responses omit storage/container and executor references.

Platform and organization administrators have full governed access. Operators may
register raw objects and records, verify integrity, quarantine, and manage operational
runs. Analysts may read and create analytical runs/edges. Recovery managers and viewers
are read-only. Legal hold, deletion, and governed supersession require an organization
administrator. Every query and traversal is scoped by `organization_id`.

## Endpoints and limits

All paths start with `/api/v1/organizations/{organization_id}`:

- `/raw-storage-objects` plus integrity, lifecycle, retention, and deletion actions;
- `/raw-storage-objects/{id}/record-references` including bounded batch registration;
- `/processing-runs` plus lifecycle actions;
- `/lineage/nodes`, `/lineage/edges`, `/lineage/events`, and bounded traversal.

Pagination defaults to 50 and is capped at 200. Record batches are capped at 500.
Traversal defaults to depth 3 and 100 nodes, capped at depth 10 and 500 nodes. Portable
iterative traversal avoids unbounded recursive SQL. Cycle detection is also bounded, so
cycles beyond that search horizon are a documented limitation.

## Validation workflow

SQLite uses the normal `pytest` suite and Alembic lifecycle test. Disposable PostgreSQL
requires an explicit `TEST_POSTGRES_URL`, a database name containing `test`, `testing`,
`disposable`, or `validation`, and `CONFIRM_DISPOSABLE_POSTGRES=1`. The migration test
upgrades to head, verifies UUID/JSONB/index/constraint behavior, downgrades WP-2.05 to
`20260724_0004`, re-upgrades, and validates the full base lifecycle. Never use
production, customer, or Mobility Next databases.

WP-2.05 does not upload or parse files, map canonical records, calculate Trust scores,
generate findings, or delete physical storage. WP-2.06 may consume this immutable
identity and lineage foundation.
