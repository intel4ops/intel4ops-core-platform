# Supabase OIDC Verification for IntelOps Navigator (P3.xxA.3B)

**Status:** Active. Confirms that `OIDCIdentityProvider`
(`app/auth/identity.py`) — already a provider-neutral OIDC/JWT resource
server, unchanged since the Auth0 pairing documented in
`docs/architecture/parking-lot/auth0-render-cmvp01.md` — verifies IntelOps
Navigator's Supabase Auth-issued tokens correctly, with **no code changes**,
purely via `OIDC_ALLOWED_ALGORITHMS=ES256`.

## Confirmed contract

| Setting | Value |
|---|---|
| `OIDC_ISSUER` | `https://ewdogwyowzqbjfyhkpxt.supabase.co/auth/v1` |
| `OIDC_AUDIENCE` | `authenticated` |
| `OIDC_JWKS_URL` | `https://ewdogwyowzqbjfyhkpxt.supabase.co/auth/v1/.well-known/jwks.json` |
| `OIDC_ALLOWED_ALGORITHMS` | `ES256` |
| `sub` claim | Stable Supabase Auth user UUID |

None of the first four values is a secret (issuer/audience/JWKS URL are
public by design, same reasoning as the Auth0 pairing) — `render.yaml`
still leaves them `sync: false` (operator-entered per deployment) because
a single blueprint may serve either pairing depending on which frontend
that instance is deployed for; it is not a secrecy measure.

## Why no code change was needed

`OIDCIdentityProvider.authenticate()` already:
- fetches signing keys generically via `PyJWKClient` (no key-type-specific
  code — `PyJWKClient.get_signing_key_from_jwt` returns whatever key type
  (RSA or EC) the matched JWK entry actually is),
- passes `algorithms=settings.oidc_allowed_algorithm_list` straight through
  to `jwt.decode()`, which PyJWT (with the `cryptography` backend, already
  a dependency via `PyJWT[crypto]`) uses to select ES256 (ECDSA/P-256)
  verification exactly the same way it selects RS256,
- derives `user_id` from `iss`+`sub` generically (`_derive_user_id`),
  unaffected by which algorithm signed the token,
- reads `is_platform_admin` from nowhere (always `False` for any OIDC
  identity, Supabase included) and the namespaced
  `<audience>/email`/`<audience>/email_verified` claims only if present —
  Supabase's default token shape doesn't emit those, so `email`/
  `email_verified` come back `None`/`False` for Navigator users exactly as
  they would for any other provider that doesn't set them. This only
  affects the optional CMVP-01 invitation recipient-binding evidence, not
  authentication or authorization.

Verified empirically with a locally generated P-256 EC key and a
Supabase-shaped payload (`iss`/`aud`/`sub` matching the table above, plus
harmless `role`/`aal` claims real Supabase tokens also carry) against an
unmodified `OIDCIdentityProvider` — see
`tests/test_supabase_oidc_verification.py` for the full suite (valid
token, stable `user_id` derivation, wrong issuer, wrong audience, expired,
tampered signature, wrong signing key, algorithm-allowlist mismatch, and a
live `GET /api/v1/me` round trip). All JWKS lookups are monkeypatched;
none of these tests make a live network call.

## Interaction with the pilot bridge (P3.xxA.2/P3.xxA.3)

`get_current_user()` checks, in order: pilot bearer token → pilot session
cookie → OIDC. Configuring real Supabase OIDC does not disable or bypass
the pilot bridge — it remains available as a development/emergency
fallback exactly as before (see `app/auth/pilot_bridge.py`). A real
Navigator user's Supabase-issued bearer token simply doesn't match either
pilot check (wrong scheme/token) and falls through to OIDC verification,
now able to succeed once these four values are configured. Confirmed by
`test_pilot_bridge_still_resolves_alongside_configured_supabase_oidc` and
`test_real_supabase_token_falls_through_pilot_checks_to_oidc`.

## What this does not do

- Does not require or grant platform-admin — every OIDC identity, Supabase
  included, still gets `is_platform_admin=False` unconditionally
  (`app/auth/identity.py`). Organization access still runs entirely
  through the existing `require_organization_roles`/membership machinery,
  unchanged.
- Does not add invitations, customer onboarding, or any multi-user UX.
- Does not modify Navigator or build a second login mechanism — Navigator
  keeps using its existing Supabase login exactly as-is; Core independently
  verifies the resulting token against its own configured
  issuer/audience/JWKS, the same trust model as the Auth0 pairing.

## Deployment

Set the four values in the table above on whichever deployment is meant to
serve Navigator (a separate deployment instance from any Auth0-paired
`app.intel4ops.com` service, since a single Core instance is paired with
one OIDC provider at a time). `DATABASE_URL` and `CORS_ORIGINS` (must
include the Navigator origin) are configured the same way as any other
Core deployment — see `render.yaml` and the main `README.md`. Not
deployed as part of this change.
