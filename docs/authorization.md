# Membership and authorization

## Authentication abstraction

`AuthenticatedUser` is the application identity contract. It contains a required UUID
`user_id` and an explicit `is_platform_admin` claim. `get_current_user` is the FastAPI
dependency boundary for a future identity provider.

The default provider always returns HTTP 401. This fail-closed behavior is intentional:
the API cannot authenticate production requests until a real provider is installed.
Tests override the dependency with an in-process identity object. That override is
test-only and is not a production authentication implementation.

Client request bodies and query parameters are never treated as proof of identity.

## Authorization flow

For an organization-scoped request:

1. The identity provider returns an authenticated user or HTTP 401.
2. A platform-level administrator claim may authorize the request explicitly.
3. Otherwise the application loads the user's membership using both `organization_id`
   and authenticated `user_id`.
4. The membership must be `active`.
5. The membership role must be allowed for the operation.

Failures return HTTP 403 without revealing memberships in another organization.
Tenant-bound membership retrieval uses both organization and membership IDs and returns
HTTP 404 when that pair does not exist.

## Roles and permissions

| Role | Read organization data | Manage memberships | Source configuration | Ingestion operations | Dataset configuration | Release quarantine | Maintenance analysis | Recovery writes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Platform administrator claim | Yes, all organizations | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| `organization_admin` | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| `analyst` | Yes | No | No | No | No | No | Yes | No |
| `operator` | Yes | No | No | Yes | No | No | Yes | Yes |
| `recovery_manager` | Yes | No | No | No | No | No | No | Yes |
| `viewer` | Yes | No | No | No | No | No | No | No |

`platform_admin` remains a controlled membership role so imported or future membership
records can represent it. In WP-2.02, cross-organization authority comes only from the
explicit platform-level identity claim. A `platform_admin` membership by itself does
not bypass organization scoping. This avoids granting global access from tenant-owned
data.

Organization creation and organization listing require the platform-level claim because
no organization membership can exist before the organization is created.

## Membership lifecycle

- `invited`: retained invitation record; never authorizes access.
- `active`: grants access according to role.
- `suspended`: retained but never authorizes access.
- `revoked`: retained permanently for audit; never authorizes access.

Activation sets `joined_at` once. Public APIs never physically delete memberships. The
last active `organization_admin` cannot be demoted, suspended, or revoked. Organization
deletion cascades membership deletion because the parent tenant no longer exists.

## API example

After a production identity provider authenticates the caller, an organization
administrator can invite a member:

```http
POST /api/v1/organizations/00000000-0000-0000-0000-000000000001/members
Content-Type: application/json

{
  "user_id": "00000000-0000-0000-0000-000000000002",
  "role": "analyst",
  "status": "invited"
}
```

The `user_id` above identifies the membership subject; it does not authenticate the
caller.

## Future Supabase Auth integration

A future Supabase adapter should:

1. Verify the bearer JWT signature, issuer, audience, expiry, and required subject.
2. Map the verified JWT subject to `AuthenticatedUser.user_id`.
3. Map a tightly governed platform-level claim to `is_platform_admin`.
4. Keep tenant authorization in this application's membership service.

`organization_members.user_id` deliberately has no database foreign key to
`auth.users`. Supabase Auth owns that schema, local SQLite tests do not provide it, and
cross-schema coupling would reduce portability. User lifecycle synchronization should
be handled by an explicit application integration or audited background process.

## Known limitations

- No production Supabase JWT adapter is included in WP-2.02.
- Platform-administrator claims depend on the future trusted identity adapter.
- Last-admin checks lock the target membership and query current active administrators;
  very high-concurrency administration may require organization-level serialization.
