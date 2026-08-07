# P3.01 Customer Identity, Access & Organization Onboarding

P3.01 closes the self-service onboarding gap identified in the P3.01
architecture investigation: organization membership was already rich
(`OrganizationMembership` lifecycle, role-based authorization,
last-active-admin protection) but there was no way for a prospective
customer to create their own organization, invite teammates by email, or
accept an invitation without a platform administrator manually inserting
membership rows. This package adds email invitations, self-service
organization provisioning, a current-identity/access-context surface, and a
governed access-audit trail. It does not implement authentication.

## Boundary

The package adds exactly 2 tables:

- `organization_invitations` — a token-hashed, expiring, single-use
  invitation with a governed 7-day expiry, one pending invitation per
  `(organization_id, email)` at a time, and a database `CHECK` binding
  `accepted_at`/`accepted_by_user_id`/`resulting_membership_id` together.
- `access_audit_events` — an append-only audit trail mirroring the shape of
  `DecisionAuditEvent`/`CausalAuditEvent`, recording invitation and
  membership-lifecycle events.

The migration (`20260808_0034`) also retrofits the platform's composite
tenant-FK convention onto `organization_members`
(`UNIQUE(organization_id, id)`) — the oldest table in the platform
(`20260724_0002`), created before that convention existed, and needed here
because `organization_invitations.resulting_membership_id` takes a composite
foreign key into it.

## Authentication boundary (explicitly out of scope)

`app/auth/identity.py`'s `get_current_user()` remains a deliberate,
fail-closed stub that unconditionally raises 401. `pyproject.toml` and a
direct import check confirmed no JWT/OIDC dependency
(`PyJWT`/`python-jose`/`Authlib`/`jwcrypto`) is installed, so real token
verification is out of scope for this package by design rather than
oversight. Every new route depends on `get_current_user`/
`require_organization_roles` exactly like existing routes; nothing here
weakens or bypasses that boundary. First-party passwords, password hashes,
MFA storage, refresh-token issuance, and any first-party identity-provider
functionality are explicitly not built.

## Self-service organization creation and the pre-existing admin route

`app/api/routes.py` already exposed `POST /api/v1/organizations`, but it is
platform-admin-only (`require_platform_admin`) and provisions an
organization without granting any membership — a back-office tool, not
self-service signup. Discovering this mid-implementation (a keyword search
for "organ" across `app/api/` filenames had missed it, since the route lives
in the generically-named `routes.py`) ruled out reusing that path for
self-service creation without either colliding on it or modifying a file
outside this package's allowlist. `create_organization_with_owner()`
(`app/services/access_context_service.py`) is exposed instead at
`POST /api/v1/me/organizations`, scoped under the same `/api/v1/me` prefix as
the other self-service identity endpoints. It constructs the `Organization`
and its first `OrganizationMembership` (`organization_admin`, `active`)
directly rather than composing `OrganizationService.create()` and
`MembershipService.create()` — each of those commits independently, which
would leave a partially-provisioned organization if the second insert
failed. Both the organization insert and the final commit are wrapped in
their own `IntegrityError` handling, because a concurrent duplicate-slug
race can raise the constraint violation at either point depending on
statement timing, not only at commit — confirmed by a dedicated PostgreSQL
concurrency test that failed against the first implementation (which only
guarded the commit) and passed once the earlier flush was guarded too.

## Invitation lifecycle and security model

`InvitationService.create()` generates a raw token with
`secrets.token_urlsafe(32)`, persists only its SHA-256 hash
(`token_hash`), and returns the raw token exactly once in the creation
response (`InvitationCreateResult.token`) — it is never logged, never
re-derivable, and never stored in `access_audit_events`. `accept()` looks
the invitation up by hash under `SELECT ... FOR UPDATE`, so a concurrent
double-submit of the same token serializes rather than races; a PostgreSQL
concurrency test drives two threads through `accept()` for the same token
and same accepting user and asserts exactly one resulting membership.
Acceptance is idempotent for the same user (returns the existing
membership) and rejects a second, different user with a structured
`invitation_conflict` (409). Role assignment on accept always comes from
`invitation.role`, never from the caller: `InvitationAccept` has no `role`
field at all, so self-escalation is structurally impossible rather than
merely validated away — verified by an API test that supplies an
`organization_admin` role in the request body and confirms the resulting
membership keeps the invitation's original `viewer` role.

Statuses are `pending → accepted | expired | revoked`, all terminal.
`OrganizationInvitation` uses the same event-listener immutability pattern
as `CausalAuditEvent`/`DecisionAuditEvent`: any `before_update` on a
terminal-status row, or any `before_delete`, raises `ValueError`.
`AccessAuditEvent` is fully immutable (no updates or deletes at all). A
lazily-expired invitation flips to `expired` and records that transition on
the read/accept path rather than requiring a background sweep.

Expiry comparison originally used `invitation.expires_at <= utc_now()`
directly; on SQLite (the default test-suite database) `DateTime(timezone=True)`
columns round-trip as naive datetimes, so this raised
`TypeError: can't compare offset-naive and offset-aware datetimes` on every
`accept()` call, not only expired ones. Fixed with the same `_utc_datetime`
normalization helper already used by `causal_intelligence_service.py` and
`commercial_service.py` for the identical SQLite behavior.

## Access context and audit trail

`GET /api/v1/me` returns the caller's identity and active memberships.
`GET /api/v1/me/context` resolves a state machine —
`no_membership`, `multiple_organizations`, `pending_invitation`,
`revoked_membership`, `suspended_organization` (covering both a suspended
membership and a deactivated organization), and `active` (with role,
descriptive-only permitted actions, and entitlement summary). The
`permitted_actions` list is UI guidance only; it enforces nothing —
authorization continues to run entirely through
`require_organization_roles`/`require_commercial_entitlement`.
`GET /api/v1/organizations/{organization_id}/access-summary` aggregates
subscription/plan, enabled entitlements, and active industry-pack codes
behind `ORGANIZATION_READ_ROLES`.

`record_access_audit_event()` (`app/services/invitation_service.py`) is
shared by invitation mutations and by `membership_service.py`'s
`update_role`/`suspend`/`revoke`, which gained an optional
`actor_user_id: UUID | None = None` parameter rather than a required one —
`app/api/membership_routes.py` was outside this package's file allowlist,
so its existing calls remain valid and simply attribute `None` until that
route file is updated in a future package.

## API

- `POST /api/v1/me/organizations` — self-service organization creation
  (creator becomes `organization_admin`).
- `GET /api/v1/me`, `GET /api/v1/me/context`.
- `GET /api/v1/organizations/{organization_id}/access-summary`.
- `POST /api/v1/organizations/{organization_id}/invitations`,
  `GET /api/v1/organizations/{organization_id}/invitations`,
  `POST /api/v1/organizations/{organization_id}/invitations/{invitation_id}/revoke`.
- `POST /api/v1/invitations/accept`.

## Migration and rollback

Revision `20260808_0034` follows `20260807_0033`. It uses static Alembic
table definitions, adds a diagnostic-guarded parent-unique retrofit to
`organization_members`, and creates the two new tables. Downgrade removes
only WP-3.01 objects and reverts the retrofit. No historical migration is
modified.

## Known limitations

- No real authentication: every endpoint depends on the existing fail-closed
  `get_current_user()` stub. This package is not independently usable in
  production until a JWT/OIDC dependency and verifier are added in a
  dedicated follow-up.
- `app/api/routes.py`'s platform-admin `POST /api/v1/organizations` and this
  package's self-service `POST /api/v1/me/organizations` are two distinct,
  intentionally separate creation paths; no attempt was made to unify or
  deprecate either, since `app/api/routes.py` is outside this package's
  file allowlist.
- `app/api/membership_routes.py` was not updated to pass `actor_user_id`
  into `membership_service` calls, so audit events recorded via that
  pre-existing route attribute `actor_user_id = None` until a future
  package updates it.
- Invitation expiry is enforced lazily (on read/accept), not by a background
  sweep job.
- Platform-admin onboarding, billing/payment collection, and any commercial
  frontend work remain outside this package.
