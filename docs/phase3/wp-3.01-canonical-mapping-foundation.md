# WP-3.01 Canonical Mapping and Causal-Ready Data Foundation

WP-3.01 introduces the governed boundary between immutable source records and
canonical operational entities, events, and metrics. It does not infer causal
claims. It preserves the identities, time semantics, mapping decisions,
confidence, and source lineage required by later causal analysis.

## Boundary

The package adds exactly 23 tables:

- governed metadata: `canonical_entity_types`,
  `canonical_field_definitions`, `canonical_event_types`,
  `canonical_metric_types`, `mapping_templates`,
  `mapping_template_versions`, `field_mappings`,
  `mapping_transformations`, `value_crosswalks`,
  `value_crosswalk_entries`, and `entity_match_rules`;
- tenant records: `source_schemas`, `source_fields`, `mapping_runs`,
  `mapping_record_results`, `mapping_exceptions`, `mapping_reviews`,
  `canonical_entities`, `canonical_events`, `canonical_metrics`,
  `source_canonical_links`, `entity_match_candidates`, and
  `mapping_audit_events`.

Canonical metadata uses the platform's governed mixed-scope convention.
Canonical business records are tenant-owned. Every tenant child-to-parent
relationship uses the organization's identifier with the referenced identifier
in a composite foreign key. The migration adds the missing
`(organization_id, id)` candidate key to `raw_record_references` so record-level
mapping evidence is database-enforced across tenants.

## Governance and lifecycle

Mapping templates are versioned:

`draft → candidate → validated → approved → published → deprecated → retired`

Published content is immutable. A database partial unique index permits at most
one published version per template. A changed definition requires a new
semantic version and content hash. Completed mapping runs are never rewritten;
replay creates or resolves an idempotent run against the exact dataset and
published template version.

Crosswalk entries are separate governed rows. They retain the original and
normalized source values, canonical target, confidence attribution, approval
status, effective interval, supersession pointer, and audit timestamps.
Organization-owned entries carry the same owner as their parent crosswalk.
Shared entries remain visible without weakening tenant-owned entries.

## Mapping execution

Mapping execution is a pre-analysis pipeline, not an Intelligence Orchestrator
engine. It:

1. verifies the tenant-owned dataset version and every raw record reference;
2. resolves a visible, published mapping-template version;
3. applies ordered field transformations;
4. records hard unresolved or missing-field states instead of hiding them in an
   aggregate confidence score;
5. materializes a stable canonical entity, event, or metric;
6. creates a source-to-canonical link and record-level result;
7. registers mapping nodes and edges in the existing lineage graph;
8. emits an immutable mapping audit event.

An idempotency key is bound to a request fingerprint. Reuse with a different
request returns a conflict. Confidence uses the minimum of supporting mapping
decisions and records its method code, version, components, interpretation, and
limitations.

Supported deterministic transformations are type casting, date parsing,
timezone normalization, governed unit factors, ISO-style currency-code
normalization, approved crosswalk lookup, bounded derivation, constants, and
text normalization. Custom executable functions remain unsupported without
separate governance.

## Temporal and causal readiness

Canonical events and metrics keep occurrence time separate from detection and
mapping time:

- `occurrence_start` and `occurrence_end`;
- `occurrence_precision`;
- `source_reported_timestamp`;
- `first_detected_at` and `last_detected_at`;
- mapping-run start, completion, and record mapping timestamps.

Every canonical record carries a content fingerprint. Events and metrics are
deduplicated per tenant by fingerprint. Canonical entities have durable UUIDs
and a tenant-scoped business key where one is available.

The package does not create `caused_by` relationships, causal confidence,
counterfactuals, optimization models, or root-cause claims.

## Trust and industry-pack integration

The shared rule registry includes additive mapping-quality codes for
completeness, unresolved and ambiguous ratios, conflicts, missing required
fields, and lineage completeness. Any unresolved, ambiguous, conflicting, or
missing-required-field result is a hard readiness blocker until governed policy
allows otherwise.

Canonical profiles define the initial Job-to-Cash and Oilfield Services entity,
event, metric, and mapping-template requirements. They use the existing
industry-pack `ontology_mapping` capability and do not create a parallel pack
governance system.

## API

Governed catalog endpoints are under `/api/v1/canonical-mapping`. Tenant
operations are under
`/api/v1/organizations/{organization_id}/canonical-mapping`.

The API covers canonical types and fields, schema discovery, template and
version lifecycle, field transformations, crosswalk entries, mapping
execution, exceptions and review, entity-match decisions, canonical record
queries, lineage, and mapping Trust signals. Routes perform dependency and
transport work only; domain behavior remains in services.

## Migration and rollback

Revision `20260804_0031` follows `20260802_0030`. It uses static Alembic table
definitions and does not import application models or live metadata. Upgrade
adds the raw-record parent candidate key, expands the existing lineage
vocabulary, and creates the 23 tables. Downgrade removes only WP-3.01 objects,
restores the prior lineage checks, and removes the candidate key. No historical
migration is modified.

Rollback is destructive for WP-3.01 data and therefore requires a backup or a
disposable validation database. Runtime rollback should first stop mapping
execution and preserve raw records; existing Connect, Trust, Intelligence,
Command, Recovery, and Knowledge Graph records remain unchanged.

## Known limitations

- Polymorphic canonical type and target pairs are checked by vocabulary and
  validated by services because a relational foreign key cannot target three
  tables.
- Currency normalization validates canonical currency codes but does not
  perform FX conversion.
- Unit conversion uses governed deterministic factors; dimensional analysis is
  deferred.
- Fuzzy matching produces candidates only and never auto-merges.
- Live ERP connectors, frontend mapping UX, Feature Store, causal inference,
  optimization, TI-D, and production authentication are outside this package.
