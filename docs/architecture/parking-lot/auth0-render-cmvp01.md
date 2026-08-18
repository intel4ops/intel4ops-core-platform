# Parking Lot: Auth0 + Render Implementation (CMVP-01)

**Status:** Frozen at SBASE-00 (GitHub + Vercel + Supabase migration program). This
document records the exact, working, certified state of the Auth0 + Render
Commercial MVP implementation at the moment the platform migration begins. It
is a restoration reference, not active documentation — see `docs/p3-01-customer-identity-access-onboarding.md`
for the still-current, provider-neutral authentication design that the
Supabase work builds on rather than replaces.

Nothing in this document is deleted, moved, or rewritten by the migration.
The tags below are immutable and are never repointed.

## Frozen baseline

| Repository | Branch | Commit SHA | Tree SHA | Tag |
|---|---|---|---|---|
| `intel4ops-core-platform` | `main` | `2570bf93b2eb81caa224fcb87c0a0b0633179e95` | `7a4287b12c666d12dfb928930c2d74b1f96837fa` | `cmvp01-auth0-render-final` |
| `intel4ops-app` | `main` | `6c88fb69ab2e5a6fde202915f619aae90f3e238f` | `48c1e81f7f93f4ca683178f5d027a9cdff2d70d4` | `cmvp01-auth0-render-final` |

Core Alembic head at freeze: `20260822_0048` (single head, no drift).

Both worktrees were clean at freeze except for pre-existing, untracked,
unrelated artifacts (`factory-m1-test-app/`, assorted permission-locked
`.pytest-*` scratch directories from earlier certification runs in the Core
worktree) — neither is part of any tracked commit and neither is addressed by
this document.

## Current working architecture

```
app.intel4ops.com (Vercel, React SPA)
        |
        | Auth0 Authorization Code + PKCE (Universal Login, email OTP)
        v
   Auth0 tenant
        |
        | signed RS256 access token, Bearer header
        v
Render (intel4ops-core-api, Python/FastAPI, "starter" plan)
        |
        | SQLAlchemy + psycopg3, Alembic-managed schema
        v
Render-managed PostgreSQL
```

Core is a **provider-neutral OIDC/JWT resource server** — it never issues
tokens, never runs an OAuth flow, and contains no Auth0-specific code. This
means the frontend (which does hold Auth0-specific code) is the only layer
this migration's SBASE-02 gate needs to touch on the authentication side;
Core's SBASE-03 gate is a configuration/adapter change, not a rewrite.

## Auth0 configuration (names only — no secrets)

- **Application type:** Single Page Application, configured for Authorization
  Code + PKCE via `@auth0/auth0-react`.
- **Login experience:** Auth0 Universal Login (hosted), with the `email`
  connection hint, so the SDK's standard redirect/callback/session-cache
  machinery is used unmodified. (An earlier embedded custom-OTP-UI approach
  was evaluated and rejected — see Known limitations below.)
- **Post-Login Action:** attached to the Login flow. Its job is to add two
  namespaced custom claims to the *access* token (not the ID token) before
  it is issued, because Auth0 rejects non-namespaced custom claims on access
  tokens and bare `email`/`email_verified` are ID-token-only under standard
  OIDC:
  - `<OIDC_AUDIENCE>/email` — the authenticated user's email address.
  - `<OIDC_AUDIENCE>/email_verified` — boolean; only the literal JSON `true`
    is treated as verified anywhere downstream (Core does not accept a
    string `"true"` or any other truthy-ish value — see
    `app/auth/identity.py`, `test_email_verified_string_true_not_treated_as_verified`).
  - Prose logic: on execution, read `event.user.email` and
    `event.user.email_verified` from the Auth0 user profile and set them on
    `api.accessToken.setCustomClaim(...)` under the two keys above. No other
    behavior. No secrets are embedded in the Action; it only reads fields
    already present on the authenticated user record.
- **API (audience):** a custom API resource whose identifier is the value
  configured as Core's `OIDC_AUDIENCE`. The namespace above is literally this
  audience string with `/email` and `/email_verified` appended.
- **Algorithm:** RS256 only (`OIDC_ALLOWED_ALGORITHMS=RS256`; Core rejects
  `alg: none` and any unlisted algorithm unconditionally).
- **Callback route:** frontend `/callback`, i.e.
  `https://app.intel4ops.com/callback` in production
  (`VITE_AUTH0_REDIRECT_URI`, defaulting to `${window.location.origin}/callback`
  if unset — see `src/auth/auth0Config.ts`).

## Core environment contract (`render.yaml`, `.env.example`)

Core requires exactly three OIDC values to authenticate at all; if any is
missing it fails closed with `authentication_unavailable` (503), never with
a silent bypass:

- `OIDC_ISSUER` — the Auth0 tenant's issuer URL.
- `OIDC_AUDIENCE` — the custom API identifier (also the claim namespace,
  above).
- `OIDC_JWKS_URL` — the Auth0 tenant's JWKS endpoint.
- `OIDC_ALLOWED_ALGORITHMS` — fixed at `RS256`.

None of these four values is a secret (issuer/audience/JWKS URL are public by
design; the algorithm allowlist is a constant) — consistent with why they
appear in `render.yaml` as either a literal `value:` or `sync: false`
(operator-entered at deploy time, not embedded in the blueprint) rather than
Render's separate secret storage.

`DATABASE_URL` is `sync: false` in `render.yaml` — never embedded, always
operator-entered at deploy time.

## Render service architecture

Full `render.yaml` at the frozen commit (reproduced verbatim; contains no
secret values):

```yaml
services:
  - type: web
    name: intel4ops-core-api
    runtime: python
    plan: starter
    buildCommand: pip install -e .
    startCommand: alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /api/v1/health
    envVars:
      - key: PYTHON_VERSION
        value: 3.12.13
      - key: APP_ENV
        value: production
      - key: DATABASE_URL
        sync: false
      - key: CORS_ORIGINS
        value: https://app.intel4ops.com
      - key: OIDC_ISSUER
        sync: false
      - key: OIDC_AUDIENCE
        sync: false
      - key: OIDC_JWKS_URL
        sync: false
      - key: OIDC_ALLOWED_ALGORITHMS
        value: RS256
```

Notes load-bearing for restoration:

- `PYTHON_VERSION` is pinned to `3.12.13` — the line the full certification
  suite (1132+ tests, mypy, Ruff) has actually been run under. Render
  defaults new Python services to a newer runtime that this codebase has
  never been certified against.
- Migrations run inline (`alembic upgrade head && uvicorn ...`) on every
  deploy — appropriate only for this single-instance `starter`-plan
  deployment. The blueprint's own header comment already flags that this
  must move to Render's `preDeployCommand` before ever scaling to multiple
  concurrent instances, to avoid concurrent migration races.
- `CORS_ORIGINS` is hardcoded to `https://app.intel4ops.com` — the only
  allowed frontend origin in production.

## Render PostgreSQL requirements

No PostgreSQL extensions are required beyond the default install (no
`CREATE EXTENSION` statements exist anywhere in `migrations/`). Schema is
entirely SQLAlchemy/Alembic-managed; standard managed Postgres on Render
satisfies every requirement. Connection is a direct (non-pooled) URL — Render
does not interpose a transaction pooler the way Supabase's Supavisor does, so
this is a genuine behavioral difference the SBASE-05 gate must account for,
not assume away.

## Frontend Vercel configuration

`vercel.json` (verbatim, contains no secrets):

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "rewrites": [
    {
      "source": "/(.*)",
      "destination": "/index.html"
    }
  ]
}
```

This is a pure SPA-fallback rewrite (all paths serve `index.html`, client-side
router takes over) — the fix from the earlier CMVP-01 Vercel SPA-routing
gate.

Frontend environment variable **names** (`.env.example`; no values are
secrets in the sense of needing redaction here since the example file already
ships empty):

- `VITE_INTEL4OPS_API_BASE_URL` — Core API base URL (`https://` Render
  hostname in production).
- `VITE_USE_DEMO_FIXTURES` — development-only flag, ignored by production
  builds.
- `VITE_AUTH0_DOMAIN`, `VITE_AUTH0_CLIENT_ID`, `VITE_AUTH0_AUDIENCE`,
  `VITE_AUTH0_REDIRECT_URI` — public Auth0 SPA identifiers (never a client
  secret; the SPA uses Authorization Code + PKCE, which requires none). Core
  independently validates the resulting JWT against its own
  `OIDC_ISSUER`/`OIDC_AUDIENCE`/`OIDC_JWKS_URL` and never trusts the
  frontend's copy of these values.

## Domains and DNS

Confirmed from repository state:

- `app.intel4ops.com` → Vercel-hosted frontend. This is the one production
  origin Core's `CORS_ORIGINS` allows.

Not confirmed from repository state (restoration must verify against the
live Render/DNS dashboards, not assume):

- Whether a custom `api.intel4ops.com` domain was ever attached to the
  Render service, or whether production traffic to Core still runs through
  Render's default `*.onrender.com` hostname. No reference to a custom API
  domain exists in `render.yaml`, `.env.example`, or frontend config —
  `VITE_INTEL4OPS_API_BASE_URL` is deployment-supplied and not committed.

## Live acceptance evidence (from prior CMVP-01 gates, summarized — no secrets)

- Render deployment: `GET /api/v1/health` verified healthy after the
  psycopg driver-scheme repair gate (bare `postgresql://` from Render's
  managed Postgres normalized to `postgresql+psycopg://` via a Pydantic
  validator in `app/core/config.py`).
- Auth0 Universal Login OTP flow verified end-to-end after the SDK
  compatibility correction (embedded custom-OTP UI was proven incompatible
  with `@auth0/auth0-spa-js`'s public API and replaced with the `email`
  connection-hint Universal Login redirect).
- A freshly issued Intel4Ops access token was locally decoded and confirmed
  to carry both `<audience>/email` and `<audience>/email_verified` (`true`)
  after the Post-Login Action was deployed, unblocking the CMVP-01
  Invitation Recipient Binding gate (Core PR #75, merged).

## Restoration procedure

If the Supabase migration must be rolled back, or run side-by-side for
comparison, at any point before SBASE-11 formally parks this stack:

1. **Core:** `git checkout cmvp01-auth0-render-final` (or branch from it) in
   `intel4ops-core-platform`. Re-import `render.yaml` as a Render Blueprint
   (or resume the existing Render service if it was only paused, not
   deleted). Re-enter the four `sync: false` values
   (`DATABASE_URL`, `OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_JWKS_URL`) from
   wherever they are held outside this repository (a password manager or the
   Render dashboard's existing environment — never from this document, which
   intentionally records no secret values).
2. **Auth0:** re-enable the tenant/application/API if disabled; confirm the
   Post-Login Action is still attached to the Login flow with the logic
   described above; confirm the API identifier still matches the restored
   `OIDC_AUDIENCE`.
3. **Frontend:** `git checkout cmvp01-auth0-render-final` (or branch from it)
   in `intel4ops-app`. Redeploy to Vercel with the four `VITE_AUTH0_*`
   variables and `VITE_INTEL4OPS_API_BASE_URL` pointed at the restored Render
   service.
4. **DNS:** re-point `app.intel4ops.com` at the restored Vercel deployment
   if it had been moved.
5. **Verify:** repeat the live acceptance checks above — anonymous
   `GET /api/v1/me` → 401, authenticated → real Core JSON, full magic-link
   round trip from `app.intel4ops.com`.

No step in this procedure requires any code change — the entire Auth0/Render
implementation is preserved exactly as tagged, and this restoration is a
configuration/redeploy exercise only.

## Known limitations of the frozen implementation (carried forward, not fixed here)

These are pre-existing, disclosed limitations of the Auth0/Render
implementation as of the freeze — not migration defects, and not addressed
by this document:

- Provider migration changes the derived `user_id` (issuer+subject-based);
  no cross-provider identity-continuity mapping exists. This is exactly the
  concern the migration program's SBASE-03/IDENTITY MIGRATION gate must
  resolve for the Auth0 → Supabase transition specifically.
- Platform-admin authentication is not wired to any OIDC claim; platform
  admins are provisioned out-of-band.
- Invitation expiry is enforced lazily (on read/accept), not by a background
  sweep job.
- Migrations run inline on Render's `startCommand`, acceptable only for a
  single-instance deployment (see Render service architecture above).
