# P3.03D-A Tenant Mapping Memory Foundation

## Purpose

Operational Memory preserves tenant-specific, human-governed mapping knowledge so an earlier
confirmed mapping can be retrieved as a bounded suggestion in a compatible context.

The governing invariant is:

> Memory suggests. Canonical Mapping executes. Trust independently validates.

Operational Memory is not canonical truth, a Trust decision, a Finding, a rule, a formula, an
autonomous workflow, or a cross-customer knowledge base.

## D-A boundary

D-A supports only `FIELD_MAPPING`, `SCHEMA_PATTERN`, and `TERMINOLOGY`. It is tenant-only,
PostgreSQL-authoritative, deterministic, and exposed through the existing
`connect.canonical_mapping` entitlement. It introduces no role, entitlement, usage meter, AI
provider, embedding, vector, background-learning job, or automatic retention job.

Exactly three tables are managed:

- `operational_memory_items`: stable identity and current retrieval projection.
- `operational_memory_versions`: immutable observations and governance decisions.
- `operational_memory_reuse_events`: immutable, truthful retrieval or no-match records.

No existing table is changed and deployment performs no historical backfill.

## Identity and context

`memory_normalization_v1` applies NFKC normalization, camel-case splitting, separator
normalization, Unicode casefolding, whitespace collapse, and the fixed aliases `no`, `num`, and
`nbr` to `number`. It does not perform transliteration, fuzzy matching, synonym generation, or
semantic normalization.

`memory_context_v1` hashes canonical JSON containing source-system family, schema fingerprint,
canonical domain, table/entity context, sorted neighboring field signatures, and the tenant's
governed industry code. Missing values are explicit nulls.

`memory_identity_v1` hashes tenant, category, subject kind, normalized subject, source-system
family, canonical domain, and context signature with SHA-256. The interpreted target is excluded,
so conflicting interpretations become governed contradictions rather than duplicate identities.

## Lifecycle and versioning

New candidates are `OBSERVED`. An organization administrator may confirm or reject an observed
candidate, correct or deprecate a confirmed/corrected memory, and correct or reject an ambiguous
memory. Each operation appends a version. Historical versions are never rewritten or deleted.

Only a current `CONFIRMED` or `CORRECTED` memory that is non-stale, unexpired, and unambiguous is
reusable. `SUPERSEDED` is derived for a non-current historical version; it is not a mutable current
status.

Repeated matching observations may increase support through another immutable version but cannot
promote lifecycle state. Human confirmation remains mandatory.

## Contradictions and staleness

A conflicting interpretation for the same tenant identity creates an `AMBIGUOUS` version,
increments the contradiction count, and marks the item stale with
`CONTRADICTORY_EVIDENCE`. Retrieval excludes it until an authorized correction or rejection.

Other staleness reasons are schema change, source-system change, retired mapping version,
incompatible canonical definition, and expired validity. Staleness is re-evaluated during governed
candidate, decision, and retrieval operations. There is no time-decay score or background job.

## Provenance and payload limits

Candidate creation is an internal service operation. It requires tenant-valid source-schema or
mapping-result provenance. Mapping review, mapping-template version, and canonical definition
references are validated against existing governance scope. Generic source-type/source-ID pairs
are not accepted.

Payloads use category-specific schemas with unknown keys forbidden. JSON depth, key count, list
length, string length, and serialized size are bounded. Raw rows, documents, financial values,
contracts, identities, credentials, tokens, provider prompts/responses, and unbounded text are
prohibited. Prompt-like terminology remains inert data and is never interpreted as an instruction.

Security classifications are `TENANT_INTERNAL` and `TENANT_SENSITIVE`. `retention_until` records
policy metadata only: observed/rejected/ambiguous data uses a 180-day target; governed active or
deprecated data uses a two-year target. No deletion or legal-hold automation is included.

## Retrieval and explanation

The retrieval endpoint normalizes the subject, computes context and request fingerprints, evaluates
at most 20 indexed tenant candidates, and returns at most five suggestions. Ranking is deterministic:
exact context, source-system family, schema, canonical domain, recency of confirmation, confirmation
count, support count, then stable UUID.

Every suggestion identifies the immutable version and explains the matched dimensions. Successful
retrieval records one `RETRIEVED` event per suggestion. Zero results record one `NO_MATCH` event.
D-A does not claim that a suggestion was presented, accepted, applied, useful, or value-producing.

Idempotency keys are request-fingerprint bound. Reuse with a different request returns `409`.
Decisions lock the item and require the expected current version, so competing transitions have one
winner and controlled conflicts. The item projection and new version commit or roll back together.

## API and authorization

- `GET /api/v1/organizations/{organization_id}/operational-memories`
- `GET /api/v1/organizations/{organization_id}/operational-memories/{memory_id}`
- `POST /api/v1/organizations/{organization_id}/operational-memories/retrieve`
- `POST /api/v1/organizations/{organization_id}/operational-memories/{memory_id}/decisions`

Read and retrieval reuse `INGESTION_READ_ROLES`; decisions require an organization administrator.
Inactive, suspended, and revoked memberships are rejected. Foreign tenant identifiers return safe
not-found responses. There is no generic create, PATCH, DELETE, global, or cross-tenant endpoint.

## Authority boundaries

Operational Memory never publishes or applies a canonical mapping, changes a Trust readiness
decision, or mutates Findings, Value Scan, AI profiles, executive narratives, Economics, Recovery,
Knowledge Graph, OIKB, analytical engines, orchestration, or actions.

The future Mathematical Intelligence relationship remains: Operational Memory may suggest
applicability, the Mathematical Intelligence Registry authorizes the exact method/version, and only
then may a governed execution run.

## Roadmap

- P3.03D-B: governed feedback integration, including customer context and approved AI-profile input.
- P3.03D-C: mapping-workflow retrieval/reuse integration and measured acceptance/outcome evidence.
- P3.03D-D: future generalization governance; cross-tenant learning remains prohibited until an
  explicit architecture and privacy decision.

D-A metrics are limited to identities, active governed memories, retrievals, duplicates, stale or
ambiguous counts, latency, and suggestion count. Acceptance rate, time saved, productivity, and
economic value require D-C evidence.
