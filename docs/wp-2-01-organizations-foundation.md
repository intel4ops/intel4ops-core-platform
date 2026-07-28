# WP-2.01 Organizations Foundation

## Retrospective status

This is a retrospective specification that ratifies the WP-2.01 behavior already
implemented on `main`. It is derived from the organization model, service, API
contracts, migration `20260724_0001`, tests, and repository engineering rules. It
does not introduce new requirements or describe unimplemented intent as complete.

## Responsibility and ownership

An organization is the platform tenant root. Its UUID is the authoritative tenant
boundary carried by persisted operational records and used by downstream
authorization and query filters. No tenant identifier is hard-coded.

Ownership is divided as follows:

- `Organization` in `app/models/entities.py` owns the SQLAlchemy persistence model.
- `OrganizationService` in `app/services/organization_service.py` owns create,
  retrieve, list, update, and deactivate business operations.
- `app/api/routes.py` owns the thin FastAPI transport and error mapping.
- `OrganizationCreate`, `OrganizationUpdate`, and `OrganizationRead` in
  `app/schemas/contracts.py` own request and response validation.
- Alembic revision `20260724_0001` owns the initial `organizations` table and its
  unique slug index. Application startup does not create managed tables.

## Persisted contract

The organization record contains:

- UUID primary key `id`;
- required `name`, unique `slug`, two-letter `country_code`, three-letter
  `default_currency`, `timezone`, and `status`;
- optional `legal_name`, `industry`, and `description`;
- `is_demo`, `created_at`, and `updated_at`.

Create and update contracts normalize country and currency codes to uppercase ASCII.
Slugs use lowercase letters, digits, and single hyphen separators. Duplicate slugs
produce a conflict. Required fields cannot be set to null through update.

## Lifecycle

The implemented lifecycle has two states:

- `active` is assigned on creation and permits services that require an active
  organization to operate.
- `inactive` is assigned by the deactivate operation.

Deactivation is a state transition, not physical deletion. WP-2.01 does not expose
reactivation, organization deletion, or additional organization lifecycle states.
Those capabilities remain future intent unless separately approved.

## API and authorization

| Method and path | Implemented behavior | Current authorization |
|---|---|---|
| `POST /api/v1/organizations` | Create an active organization | Platform administrator |
| `GET /api/v1/organizations` | List organizations by name and UUID | Platform administrator |
| `GET /api/v1/organizations/{organization_id}` | Retrieve one organization | Authorized organization reader |
| `PATCH /api/v1/organizations/{organization_id}` | Apply validated partial updates | Organization administrator |
| `POST /api/v1/organizations/{organization_id}/deactivate` | Set status to `inactive` | Organization administrator |

The membership authorization behavior was added after the initial WP-2.01 migration
and is documented here because it is the behavior currently present on `main`.
Supplying an organization UUID alone never authorizes access.

## Downstream dependencies

The organization UUID is referenced by organization memberships, source systems,
ingestion batches, datasets and versions, raw artifacts and lineage, Trust and
intelligence executions, findings and evidence, recommendations and actions,
recovery records, commercial assignments and usage, industry packs, signatures,
and knowledge-graph projections. Each downstream domain owns its own lifecycle and
tenant-safe queries; WP-2.01 owns only the tenant-root record.

Migration `20260724_0001` also created starter findings, finding-evidence, and
recovery-action tables. Later work packages govern their expanded behavior. Their
presence in the first migration does not make them organization-service concerns.

## Acceptance criteria ratified from the implementation

WP-2.01 is accepted when all of the following existing behaviors remain true:

1. Organizations use UUID primary keys and persist the documented fields.
2. Slugs are unique and duplicate create or update attempts return HTTP 409.
3. Slug, country-code, and currency validation rejects malformed values; country
   and currency values are normalized to uppercase.
4. Create, retrieve, list, partial update, and deactivate operations are available
   through thin routes backed by `OrganizationService`.
5. Missing organization retrieval, update, or deactivation returns HTTP 404.
6. Required organization fields cannot be set to null.
7. Deactivation retains the record and changes its status to `inactive`.
8. Organization-scoped downstream records use `organization_id` as their tenant
   boundary and tenant-specific queries filter by that identifier.
9. Alembic owns schema creation and the application does not call
   `Base.metadata.create_all` at startup.
10. Unit/API and migration tests pass on SQLite and the guarded disposable
    PostgreSQL strategy validates native behavior without production credentials.

## Explicitly not ratified

This retrospective specification does not add deletion, reactivation, billing,
identity-provider provisioning, new lifecycle states, new database constraints, or
changes to downstream work packages.
