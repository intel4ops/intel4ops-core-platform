# Multi-application API gateway

WP-2.18 retains the existing `/api/v1` route tree and adds a stable application-facing
context endpoint. `X-Request-ID`, `X-Correlation-ID`, and `X-Intel4Ops-Client` identify
transport activity; client identity is descriptive and never replaces authentication.

The protected pipeline remains authentication, tenant membership, commercial subscription
and entitlement, validation, service execution, audit, metering, and response. Tenant IDs
come from the organization-scoped route and are verified by membership dependencies.

`GET /api/v1/organizations/{organization_id}/gateway/context` returns the resolved user,
roles, subscription, plan version, locale, reporting currency, client, and request IDs.
Unknown clients fail closed. Request and correlation IDs are returned as response headers.

External retryable operations use tenant-scoped idempotency keys. Pagination uses one-based
pages with bounded page sizes. Application clients are registry data, not credentials.
