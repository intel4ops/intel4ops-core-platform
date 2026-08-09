# P3.03C Grounded Executive Narrative

## Customer promise

The Grounded Executive Narrative turns an immutable Directional Value Scan into a concise,
traceable executive experience. It explains governed truth; it does not create new truth.

The first release supports one `EXECUTIVE` audience and structured sections for a headline,
executive summary, key messages, top opportunities, optional confirmed context, limitations,
data gaps, and the governed next investigation. Free-form reports, PDF, presentation, email,
scheduled generation, chat, and persona-specific variants are deferred.

## Truth boundary

The immutable P3.03A Directional Value Scan is the primary source. Its stored status, ranks,
finding projections, potential exposure, confidence, evidence references, limitations, data
gaps, and next investigation are authoritative. P3.03C does not re-query mutable analytical
domains, recalculate rank or exposure, or modify upstream records.

P3.03B context is optional. `CONFIRMED` and `CORRECTED` inferences may be labeled
`CUSTOMER_CONFIRMED_CONTEXT`. `INFERRED` items remain tentative `AI_INFERENCE` claims.
Rejected, deferred, and superseded context is excluded. Context never changes ranking,
confidence, or numerical truth.

## Claims and traceability

Allowed claim types are:

- `GOVERNED_SCAN_FACT`
- `GOVERNED_FINDING`
- `POTENTIAL_EXPOSURE`
- `AI_INFERENCE`
- `CUSTOMER_CONFIRMED_CONTEXT`
- `RECOMMENDATION`
- `LIMITATION`
- `UNKNOWN`, which is defensive only and cannot render

Every rendered claim has a claim ID, compatible source references, optional evidence
references, confidence, deterministic confidence language, limitations, and optional governed
value references. The service constructs the reference allowlist. Provider-created references
cause complete rejection of provider output and deterministic fallback.

## Numerical and currency safety

Provider wording cannot contain digits, percentages, currency codes or symbols, ranges, or
monetary amounts. The provider selects a governed value reference; the deterministic renderer
copies the potential-exposure value object from the stored scan. The model never owns the
number.

Expected recovery is excluded from this release even when present upstream. P3.03C does not
create or surface Verified Value or realized value.

Original currencies are preserved. There is no FX conversion, unlike-currency aggregation, or
consolidated multi-currency total. Existing scan limitations remain visible.

## Confidence and causal language

Confidence language is fixed by policy:

- `HIGH`: Supported with high confidence within the available governed evidence.
- `MEDIUM`: Supported with moderate confidence; review the stated limitations.
- `LOW`: Preliminary and supported with low confidence.
- `NOT_ASSESSED`: Confidence has not been assessed.

The first release consumes no causal tables. Root-cause statements, guaranteed outcomes,
intervention promises, and other causal assertions are prohibited.

## Scan-state behavior

Zero eligible opportunities never means that the operation is healthy or problem-free. The
fixed message explains that no governed eligible opportunity is currently supported and that
additional governed data or analysis may change the result.

A partial scan states that supported opportunities exist but coverage is incomplete. A refused
scan produces no opportunity narrative and foregrounds its governed gap or next investigation.
Data-gap wording derives from the stored gap snapshot and cannot hide, resolve, or replace a
gap. The scan's next investigation remains authoritative; provider wording cannot replace it.

## Provider and fallback

The service depends on the provider-neutral `GroundedExecutiveNarrativeProvider` protocol. The
existing OpenAI adapter implements strict structured parsing with no tools, `store=False`, a
bounded input, at most 1,800 output tokens, the existing timeout, and at most one retry.
Business strings are untrusted data and are never placed into provider instructions.

Provider output passes schema, reference, claim compatibility, numeric, currency, causal,
confidence, context-status, and bounds validation. Acceptance is all-or-nothing. Disabled AI,
missing credentials, provider failure, malformed output, or any semantic violation produces a
useful deterministic narrative which is persisted with a sanitized failure code.

## Idempotency, provenance, and immutability

Narratives are immutable snapshots. Organization-scoped idempotency keys reject different
requests with `409`, while equivalent execution fingerprints reuse the existing result. The
fingerprint covers the exact scan hash, optional profile fingerprint, audience, template,
schema, provider, model, and relevant deterministic configuration.

Stored provenance includes source hashes, request/input/execution/content hashes, provider and
model identity, template/schema versions, latency, token counts when available, retry count,
generation status, and sanitized failure classification. Raw prompts, unrestricted provider
responses, documents, credentials, and secrets are not stored.

## Tenant isolation and authorization

The organization is the tenant boundary. Scan and optional profile references use composite
`(organization_id, id)` foreign keys. Service reads, lists, and source validation always include
`organization_id`. Cross-tenant sources are rejected before provider invocation and persist
nothing.

Generation reuses `INTELLIGENCE_EXECUTION_ROLES`; read and list reuse `FINDING_READ_ROLES`.
The existing `intelligence.findings` entitlement is reused. P3.03C adds no role, permission,
entitlement, commercial catalog entry, or usage meter.

## API and frontend contract

The API exposes:

- `POST /api/v1/organizations/{organization_id}/executive-narratives`
- `GET /api/v1/organizations/{organization_id}/executive-narratives`
- `GET /api/v1/organizations/{organization_id}/executive-narratives/{narrative_id}`

There is no update or delete API. The backend returns structured JSON, not HTML or Markdown.
A frontend must escape text, render governed values separately, display claim classifications,
confidence, evidence and source references, show limitations and gaps, label fallback, and
avoid calculations or inference promotion.

## Known limitations and deferred capabilities

This package introduces no new mathematical calculation. Statistical, forecasting,
reliability, economic, and other quantitative truth can appear only through governed upstream
outputs already projected into the scan. Causal narrative, expected-recovery narrative,
Verified Value narrative, optimization, simulation, FX, persona templates, downloads,
distribution, scheduling, background regeneration, arbitrary prompting, additional providers,
frontend work, and usage metering are deferred.
