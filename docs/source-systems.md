# Source systems registry

WP-2.03 provides a governed, organization-scoped registry for systems that may later
participate in Connect workflows. It does not implement connectors, credential
retrieval, connection execution, ingestion, or synchronization.

## Tenant and authorization boundary

Every query uses both `organization_id` and the source-system identifier. Cross-tenant
lookups return 404. The platform administrator claim and active organization roles have
these permissions:

| Role | Read | Configure | Connection and health | Decommission |
|---|---:|---:|---:|---:|
| Platform administrator claim | Yes | Yes | Yes | Yes |
| `organization_admin` | Yes | Yes | Yes | Yes |
| `operator` | Yes | No | Yes | No |
| `analyst` | Yes | No | No | No |
| `recovery_manager` | Yes | No | No | No |
| `viewer` | Yes | No | No | No |

## Lifecycle

Allowed transitions are:

- `draft` to `configured` or `decommissioned`
- `configured` to `validating` or `decommissioned`
- `validating` to `active` or `failed`
- `active` to `paused`, `failed`, or `decommissioned`
- `paused` to `active` or `decommissioned`
- `failed` to `validating`, `paused`, or `decommissioned`

`decommissioned` is terminal. Decommissioning also clears `is_active` and records
`deactivated_at`. Invalid transitions return HTTP 409.

A successful connection attempt resets `failure_count`, marks health `healthy`, and
records attempt, success, and health-check timestamps. It promotes a `validating` or
`paused` source to `active` only through a valid transition. Failed attempts increment
the counter, mark the first two failures `degraded`, and mark the third and subsequent
failures `unhealthy`.

## Metadata and secret boundary

`provider` is an extensible normalized identifier rather than a connector enum. Example
values include `sap`, `oracle`, `salesforce`, `quickbooks`, and `custom_vendor`.

`capabilities` is a unique list of non-empty capability identifiers, for example
`["invoices", "vendors"]`. `configuration_metadata` is a JSON object for nonsecret
configuration and lineage hints.

Credentials are never stored in configuration metadata. A write may contain only an
opaque `credential_reference` such as `vault://intel4ops/finance-erp`; normal API
responses never include that reference. Metadata is recursively rejected when any
object key case-insensitively matches:

`password`, `passwd`, `secret`, `token`, `api_key`, `apikey`, `private_key`,
`client_secret`, `access_token`, `refresh_token`, `authorization`,
`connection_string`, or `database_url`.

## Portability

JSON fields use PostgreSQL JSONB in PostgreSQL and standard JSON in isolated SQLite
unit tests. All managed schema changes are owned by Alembic revision
`20260724_0003`.
