# Ingestion control

WP-2.04 tracks and governs ingestion through batches, logical datasets, and dataset
versions. It records control metadata, counts, status, source periods, validation
outcomes, and opaque storage references.

It does not persist raw row-level records, parse files, execute connectors, perform
canonical mapping, calculate Trust scores, or implement full lineage. Raw storage and
lineage integration are planned for WP-2.05.

## Domain model

- An `ingestion_batch` is one governed submission from one organization-owned source
  system.
- A `dataset` is a reusable logical business data asset associated with one source
  system.
- A `dataset_version` is one delivery or snapshot of a dataset in a batch. A batch may
  contain many dataset versions, but one dataset can appear at most once in a batch.
  Version numbers increase per dataset.

All three resources carry `organization_id`. Services resolve every foreign identifier
through that organization and require the dataset and batch source systems to match.
Database foreign keys use `RESTRICT`; public APIs never physically delete these
records.

## Batch lifecycle

| Current | Allowed next states |
|---|---|
| `received` | `queued`, `validating`, `cancelled` |
| `queued` | `validating`, `cancelled` |
| `validating` | `processing`, `quarantined`, `failed` |
| `processing` | `completed`, `partially_completed`, `failed`, `quarantined` |
| `partially_completed` | `completed`, `failed` |
| `failed` | `queued` |
| `quarantined` | `queued`, `cancelled` |
| `completed`, `cancelled` | terminal |

The server assigns `started_at`, `completed_at`, and `failed_at`. Retrying a failed
batch clears `failed_at`. Completed or cancelled batches cannot be modified through
ordinary APIs.

## Dataset lifecycle

`draft` can become `active` or `decommissioned`. Active datasets can be paused,
deprecated, or decommissioned. Paused datasets can become active, deprecated, or
decommissioned. Deprecated datasets can only be decommissioned. Decommissioned is
terminal and records `deactivated_at`.

## Dataset-version lifecycle

`received` becomes `validating`. Validation can produce `accepted`,
`partially_accepted`, `rejected`, `quarantined`, or `failed`. Accepted and partially
accepted versions may be processed; partially accepted versions may also fail.
Quarantined and failed versions may return to validation. `processed` and `rejected`
are terminal through ordinary APIs.

## Idempotency

An idempotency key is scoped to an organization. The immutable request identity is:

- source-system ID
- batch number
- ingestion method
- trigger type
- external batch ID
- source-period start and end

Repeating the same key and identity returns the existing batch. Reusing the key with a
different identity returns HTTP 409. Idempotency keys do not authenticate or authorize
requests.

## Reconciliation

Dataset-version counts must satisfy:

`accepted_record_count + rejected_record_count <= record_count`

Batch counts have the equivalent invariant. The batch reconciliation service locks the
batch and derives:

- `actual_dataset_count` from the number of associated dataset versions
- `actual_record_count` from their record counts
- accepted and rejected counts from their corresponding totals

Creating a version or updating its counts invokes reconciliation. Clients cannot assign
`actual_dataset_count` or dataset `version_number`.

## Metadata and storage safety

Manifest and dataset metadata are JSON objects stored as JSONB on PostgreSQL and JSON
in isolated SQLite tests. Nested secret-like keys are rejected using the WP-2.03
policy, extended to authentication headers, service-account credentials, and signed
URLs.

Storage and raw-schema references are opaque identifiers. They reject embedded
usernames, passwords, whitespace, and query parameters. File content is never stored
in these tables, and filenames cannot contain paths.

## Authorization

| Role | Read | Create/manage batches and versions | Configure datasets | Release quarantine |
|---|---:|---:|---:|---:|
| Platform administrator claim | Yes | Yes | Yes | Yes |
| `organization_admin` | Yes | Yes | Yes | Yes |
| `operator` | Yes | Yes | No | No |
| `analyst` | Yes | No | No | No |
| `recovery_manager` | Yes | No | No | No |
| `viewer` | Yes | No | No | No |

Only an organization administrator or platform administrator may release quarantined
data. Analyst validation transitions are intentionally deferred until an audited
analytical-review workflow exists.

## Filtering

Batch lists filter by source system, status, method, trigger, received range,
correlation ID, and external batch ID. Dataset lists filter by source system, domain,
type, status, sensitivity, schema status, and name/code search. Version lists filter by
status, batch, and received range. All lists use bounded `offset`/`limit` pagination and
remain organization-scoped.

## API example

```http
POST /api/v1/organizations/{organization_id}/ingestion-batches
Content-Type: application/json

{
  "source_system_id": "00000000-0000-0000-0000-000000000010",
  "batch_number": "finance-2026-07-24",
  "ingestion_method": "file_upload",
  "trigger_type": "manual",
  "idempotency_key": "finance-upload-2026-07-24"
}
```

The authenticated identity supplies `submitted_by_user_id`; clients cannot set it.

## Known limitations

- Sequential version allocation is protected by row locks and unique constraints.
  Extremely high concurrency may require a dedicated database sequence per dataset.
- Reconciliation is synchronous; future large batches may use an audited background
  job.
- Storage references are registry metadata only; WP-2.04 does not verify that the
  referenced object exists.
