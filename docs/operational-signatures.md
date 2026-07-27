# Operational Signature Intelligence

## Purpose

Operational signatures are governed, versioned patterns that convert canonical
operational observations into explainable findings. They compose existing OIKB
algorithms, rules, statistical or predictive models, evidence contracts, and
industry-pack context. They do not replace those registries.

## Registry model

- `operational_feature_definitions` and `operational_feature_versions` form the
  governed feature registry.
- `operational_signature_definitions` owns identity, type, industry, lifecycle,
  owner, tags, documentation, and retirement.
- `operational_signature_versions` is immutable and owns applicability,
  dependencies, inputs, conditions, exclusions, confidence, economics,
  expected outcomes, monitoring, and limitations.
- validations and lifecycle events are immutable governance evidence.
- deployments and executions are tenant-bound by `organization_id`.
- execution evidence preserves source identifiers, integrity fingerprints, and
  optional lineage-node references.
- findings reference both the exact signature version and execution.
- performance and monitoring history are immutable time-series records.

The supported lifecycle is `hypothesis → candidate → observed → validated →
approved → production → deprecated → retired`. `suspended` is an operational
control state. Transitions are explicit, role-controlled, idempotent, audited,
and cannot skip governance stages. Production requires an approved validation.

## Seed library

WP-2.21 provides seven reusable feature definitions and two certified
signatures:

- `J2C.SIGNATURE.OILFIELD.BILLING_LEAKAGE`
- `MFG.SIGNATURE.SERVO.DEGRADATION`

The definitions are deterministic and scenario-backed. A match is blocked by
an exclusion, missing required evidence, inactive industry-pack assignment, or
missing commercial entitlement. Confidence is explainable and capped below the
match threshold for excluded results.

## API

Platform administrators can list features, feature versions, signatures, and
signature versions, and govern lifecycle transitions under:

`/api/v1/operational-intelligence`

Tenant deployments and executions are under:

`/api/v1/organizations/{organization_id}/operational-signatures`

All endpoints require a registered application client. Tenant operations also
require organization roles, an active `intelligence.operational_signatures`
entitlement, a production signature with approved validation, and an active
applicable industry pack.

Execution POSTs require an idempotency key, observations, and evidence. A retry
returns the original execution. Every tenant query filters by
`organization_id`.

## SDK contract

`app.signatures.sdk.SignatureExtension` is the stable Python extension
protocol. Extensions provide a namespaced uppercase code, semantic version,
and complete definition mapping. `validate_extension` rejects incomplete or
unversioned definitions and produces a deterministic definition hash. SDK
validation does not publish or deploy an extension; registry governance and
Alembic-managed promotion remain mandatory.

## Validation, monitoring, and revalidation

Validation links a version to certification scenarios and validation runs,
records false-positive/false-negative counts, limitations, evidence, reviewer,
and approval. Monitoring policy is versioned with the signature. Performance
history supports precision, recall, economic impact, and tenant/global
aggregation. Monitoring results preserve thresholds, samples, action, and
evidence. Material drift requires a new validation record and governed
transition; definitions and historical evidence are never edited in place.

## Security and limitations

The organization is the tenant boundary. Catalog mutation is platform-admin
only; tenant deployment and execution use least-privilege organization roles.
Evidence payloads store references and integrity fingerprints, not raw customer
records. Signature ownership does not imply proof of causation, fraud, or
misconduct. Initial evaluation is synchronous and intended for controlled
volumes; high-throughput event processing belongs to a future asynchronous
runtime.
