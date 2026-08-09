# P3.03B — AI Operational Profiler

## Purpose and truth boundary

The AI Operational Profiler learns bounded operational context from governed,
tenant-scoped metadata and proposes customer-context inferences. AI output is an
`INFERRED` suggestion, never operational truth. Trust, Findings, evidence,
economics, Directional Value Scan, Decision Intelligence, Recovery, and Verified
Value remain deterministic and authoritative. None of those records are mutated by
profiling.

Explicit customer confirmation is required before a supported inference is
reconciled into the P3.02 workspace. Confirmations and corrections use the existing
workspace registries and validation rules. Rejection and deferral remain auditable
on the inference row.

## Architecture

`OperationalProfileInferenceProvider` is the narrow provider-neutral contract. The
initial `OpenAIOperationalProfileAdapter` is the only provider-specific component.
The application service constructs the governed request, enforces tenancy and
policy, validates structured output, normalizes confidence, persists provenance,
and coordinates confirmation. Tests use deterministic fakes and never call a paid
provider.

The two-table persistence model is:

- `ai_operational_profiles`: one immutable terminal execution with provider/model,
  template, input/request/response fingerprints, bounded provenance, limitations,
  and observability.
- `ai_profile_inferences`: tenant-bound suggestions, evidence references, bounded
  reasoning, qualitative confidence, and customer-decision history.

The composite `(organization_id, profile_id)` foreign key prevents a profile from
owning another tenant's inference. Every read and mutation filters by
`organization_id`.

## V1 inference vocabulary

Primary categories are industry, sub-industry, operational archetype, business
model, operating process, system in use, business objective, operational challenge,
and clarification question. Bounded operational characteristics are supported by
the local inference vocabulary. Registry-backed fields must use existing P3.02
codes before they can enter governed context. Unknown codes remain low-confidence
historical suggestions and cannot be confirmed.

Confidence is `HIGH`, `MEDIUM`, or `LOW`, calculated by Intel4Ops from evidence
source diversity and registry validity. Provider token probabilities are retained
only as non-authoritative provider metadata.

Legal inference outcomes are `INFERRED`, `CONFIRMED`, `CORRECTED`, `REJECTED`,
`DEFERRED`, and `SUPERSEDED`. Confirmed/corrected industry, sub-industry,
objectives, challenges, and systems reconcile through the workspace service.
AI-only context remains historical and does not create a shadow organization
profile.

## Input minimization and injection defense

The service builds its own input from tenant-scoped structured metadata: workspace
codes, source and dataset metadata, canonical schema/mapping metadata, Trust and
readiness summaries, Finding summaries, evidence identifiers/metadata, and the
latest stored Directional Value Scan snapshot. Raw records, unrestricted evidence,
documents, emails, credentials, connection strings, and financial values are not
sent. Excerpts are disabled in v1 (`AI_MAX_EXCERPT_CHARS=0`).

Secret-like strings are redacted before invocation. Customer/source values are
serialized as untrusted data and are never concatenated into system instructions.
The adapter's fixed system policy says that embedded instructions are data, grants
no tools, and allows no database, shell, file, or tenant-switch action. Structured
Pydantic schemas forbid unexpected fields, foreign organization identifiers,
unsupported inference types, foreign evidence references, and questions seeking
passwords, tokens, API keys, or bank credentials.

## APIs, authorization, and entitlement

- `POST /api/v1/organizations/{organization_id}/operational-profiles`
- `GET /api/v1/organizations/{organization_id}/operational-profiles/{profile_id}`
- `POST /api/v1/organizations/{organization_id}/operational-profiles/{profile_id}/inferences/{inference_id}/confirm`
- `POST /api/v1/organizations/{organization_id}/operational-profiles/{profile_id}/inferences/{inference_id}/reject`

Generation reuses existing intelligence execution roles; reads reuse Finding read
roles; confirmation, correction, deferral, and rejection use the existing
organization-admin mutation authority. Invited, suspended, revoked, and non-members
are denied. The existing `intelligence.findings` entitlement is reused. P3.03B adds
no role, permission tuple, catalog entry, plan, subscription migration, or usage
meter.

## Idempotency, failure, observability, and cost controls

The execution fingerprint covers governed context, template version, provider, and
model. Identical input/configuration reuses an existing profile even with a new
idempotency key. Reusing an idempotency key after a material input change returns
409. Material context or model/template change allows a new run and supersedes only
older undecided inferences. A database uniqueness claim is committed before the
provider call to prevent concurrent duplicate execution.

Disabled AI, missing credentials, timeout, provider failure, malformed output, and
foreign-tenant output produce controlled terminal profile states without affecting
deterministic capabilities. Observability stores provider/model, template version,
latency, token counts when available, retry count, hashes, and failure category. It
does not store unrestricted prompts or responses.

Configuration bounds input characters, output tokens, inference items,
clarification questions, timeout, and retries. There is no recursive execution,
background loop, commercial meter, or automatic page-refresh profiling.

## Operations and rollback

AI is disabled by default. Enable only with an approved secret injected as
`AI_API_KEY`; never commit the key. Migration `20260811_0037` creates exactly the two
AI audit tables with static SQLite/PostgreSQL-compatible DDL and a symmetric
downgrade. Downgrading removes AI profile history, so export required audit evidence
before rollback.

Operational Memory promotion, cross-tenant learning, self-training, fine-tuning,
shared vector stores, registry expansion, commercial usage metering, raw document
parsing, and P3.03C executive narrative are explicitly deferred.
