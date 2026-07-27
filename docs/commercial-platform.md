# Commercial platform

WP-2.17 turns the Product Catalog v2.0 and Platform Capability Matrix v1.0 into a
versioned commercial control plane. The source workbooks remain governing product
artifacts; their normalized codes are seeded by Alembic revision `20260726_0017`.

## Model

- Products, product versions, plans, and immutable plan versions are global catalog data.
- Subscriptions, contracts, overrides, entitlements, usage, limits, feature flags, pack
  assignments, and audit events are organization scoped.
- A subscription materializes a snapshot of its plan-version entitlements. Later catalog
  changes do not silently change an existing subscription.
- Contract overrides take precedence over plan entitlements for their effective interval.
- Usage events and commercial audit events are append-only and idempotent.
- Currency-bearing usage is grouped by ISO currency code. The service never implicitly
  aggregates unlike currencies.
- Authentication and organization membership are evaluated before commercial entitlement.
  A platform administrator may administer the catalog and bypass tenant entitlements.

Existing organizations with no subscription retain legacy access during commercial rollout.
Once any subscription is assigned, inactive subscriptions and missing entitlements fail
closed. Expired trials also fail closed.

## Limit semantics

Limits are Decimal-safe and return one of `available`, `warning`, `grace`, `read_only`,
`disabled`, or `expired`. Enforcement types are `hard`, `soft`, `warning`, and
`read_only`. Usage windows support daily, weekly, monthly, billing-period, and
subscription-period summaries.

## Main API groups

- `/api/v1/commercial/products`
- `/api/v1/commercial/features`
- `/api/v1/commercial/plans`
- `/api/v1/commercial/usage-meters`
- `/api/v1/commercial/industry-packs`
- `/api/v1/organizations/{organization_id}/commercial/subscriptions`
- `/api/v1/organizations/{organization_id}/commercial/entitlements`
- `/api/v1/organizations/{organization_id}/commercial/usage-events`
- `/api/v1/organizations/{organization_id}/commercial/usage-summary`
- `/api/v1/organizations/{organization_id}/commercial/limits/{entitlement_key}`
- `/api/v1/organizations/{organization_id}/commercial/contracts`
- `/api/v1/organizations/{organization_id}/commercial/industry-packs`
- `/api/v1/organizations/{organization_id}/commercial/feature-flags`

Catalog mutation requires platform administration. Tenant commercial reads and changes use
the existing membership role policy.

## Operational guidance

Run all schema changes through Alembic. Do not create commercial tables at application
startup. Production billing-provider integration, invoicing, payment collection, and the
external identity provider remain outside WP-2.17; this package provides the internal,
auditable entitlement and usage foundation those integrations consume.
