# WP-2.08B Causal Links, Causal Chains and Root-Cause Intelligence

WP-2.08B introduces the platform's first governed causal-claims graph. It sits
downstream of canonical mapping (WP-2.05), Trust and Analytical Readiness, and
Findings, and upstream of the future WP-2.14B optimization layer, prioritization,
and Recovery. It does not infer causality automatically, does not perform
counterfactual simulation, and never presents an association as confirmed
causality.

## Boundary

The package adds exactly 11 tables:

- governed metadata: `causal_method_definitions`;
- tenant records: `causal_nodes`, `causal_hypotheses`, `causal_evidence_links`,
  `causal_reviews`, `causal_edges`, `causal_chains`, `causal_chain_versions`,
  `causal_interventions`, `causal_outcome_assessments`, `causal_audit_events`.

Every tenant table uses the platform's composite tenant-FK convention
(`UNIQUE(organization_id, id)` on every parent, `(organization_id, <ref>)`
composite foreign keys on every child). The migration adds the one missing
`(organization_id, id)` unique to `action_outcomes` (created in the WP-2.13/TI-C2
era without it), mirroring exactly how WP-2.05 added the same kind of retrofit
to `raw_record_references` — a dedicated, diagnostic-protected step in this
package's own migration, never an edit to the historical migration that created
the table.

## Architecture: a distinct graph, not a lineage extension

Lineage (`LineageNode`/`LineageEdge`) records objective data-provenance facts.
Causality is an interpretive, evidence-and-confidence-bearing *claim* that can
be wrong, contested, or revoked. WP-2.08B introduces its own `CausalNode`/
`CausalEdge` graph rather than adding causal relationship types to the lineage
vocabulary. `CausalEvidenceLink` rows point *at* existing lineage nodes/edges/
events, Findings evidence, calculation/rule traces, and canonical/source-
canonical-link records as evidence — no evidence storage is duplicated, and no
new `LineageNode`/`LineageEdge` type values were needed.

Hypothesis and edge are deliberately separate concepts. A `CausalHypothesis` is
a versioned, lifecycle-tracked, possibly-competing claim about a
`(source_node, target_node, proposed_edge_type)` triple. A `CausalEdge` is the
graph-structural fact that materializes only once a hypothesis reaches
`confirmed` or `probable` status. This is what makes competing hypotheses
representable: two hypotheses can target the same node pair with different
proposed edge types simultaneously; only one can become the governing edge for
that pair.

## Governance and lifecycle

`CausalHypothesis.lifecycle_status`:

`draft → proposed → evidence_pending → under_review → probable → confirmed | rejected`,
with `confirmed → superseded`, `confirmed → revoked`, and any terminal state
`→ archived`.

Terminal statuses (`confirmed`, `rejected`, `superseded`, `revoked`, `archived`)
are immutable except for a narrow, guarded set of forward-only transitions
(mirroring `MappingTemplateVersion`'s exact pattern) — only `lifecycle_status`,
`updated_at`, and `superseded_by_hypothesis_id` may change once a hypothesis is
terminal, and only along the allowed transition pairs. A database `CHECK`
constraint (`ck_causal_hypothesis_association_not_confirmed`) makes it
structurally impossible for `correlates_with`/`associated_with` hypotheses to
ever reach `confirmed` — this is enforced at the database level, not merely by
service-layer convention.

Approval is also an explicit service invariant rather than a call-order
convention. A `probable` decision is accepted only from `under_review`; a
`confirm` decision is accepted only from `under_review` or `probable`. Both
require a recorded evaluation time, `hard_gate_outcome = passed`, supporting
evidence, calculated confidence, and an empty blocking-reasons collection.
Confirmation additionally requires the governed minimum confidence threshold
and rejects association-only edge types before persistence. Direct review calls
therefore cannot bypass proposal, evidence attachment, evaluation, Trust/
readiness, temporal, or lineage gates.

Evidence links remain manageable during mutable working states (`draft`,
`proposed`, `evidence_pending`, and `under_review`). Once a hypothesis reaches
`probable` or any terminal evidentiary state, model event guards reject evidence
inserts, updates, and deletes. Additional evidence then requires a new
hypothesis version. This defense uses the existing lifecycle fields and mapper
events, so it requires no schema or migration change.

An evidence insert, update, delete, or re-parenting operation against an
`under_review` hypothesis atomically invalidates the earlier evaluation in the
same transaction. The hypothesis returns to `evidence_pending`; evidence and
contradiction counts are recomputed from the current links; evaluation time,
hard-gate outcome, confidence, mapping-confidence, interpretation, and review
outputs are cleared; and an immutable audit event records the invalidation.
Evaluation, review, and evidence mutation serialize on the hypothesis row, so a
review cannot commit against an evidence set that is changing concurrently.
Review also rejects a link timestamp newer than the recorded evaluation using
the structured `hypothesis_evaluation_stale` error.

No evidence fingerprint column is needed: the lifecycle reset is transactional,
the row lock orders competing mutation/evaluation/review operations, and the
timestamp freshness check is a second review-time defense. This bounded
approach preserves the certified schema and migration chain.

`CausalReview`, `CausalOutcomeAssessment`, `CausalChainVersion`,
`CausalIntervention`, and `CausalAuditEvent` are immutable once created.

## Confidence model

`CausalConfidenceMixin` (applied to `CausalHypothesis` and `CausalEdge`) mirrors
`MappingConfidenceMixin` field-for-field and adds
`minimum_supporting_mapping_confidence`, `evidence_count`, `contradiction_count`,
and `review_status`. Confidence is always capped by the *minimum* mapping
confidence across supporting evidence, never averaged, and is discounted (not
merely blocked) by contradicting evidence. `CausalEvaluationService` computes
this deterministically from the governed method's `default_confidence_weight`.

## Hard gates

A hypothesis is blocked from advancing past `evidence_pending` when: no
supporting evidence is attached; supporting canonical evidence carries a
blocking `mapping_status` (`unresolved`, `ambiguous`, `conflicting`,
`missing_required_field`, `rejected`, `superseded`); minimum supporting mapping
confidence falls below a governed threshold; temporal precedence is violated
for `causes`/`precedes` edges; the underlying records' occurrence precision
cannot support the claimed temporal lag; or the organization's most recent
Analytical Readiness decision is `blocked`. Each failure is recorded as a
structured `{code, message}` reason, never a single generic failure string.

## Temporal semantics

No occurrence timestamps are duplicated onto `CausalNode` — they are read from
the underlying `Finding`/`CanonicalEvent`/`CanonicalMetric` record via the
node's `target_kind`/`target_id`. `CausalHypothesis` adds exactly one new
temporal concept, `causal_evaluation_time` (when the hypothesis was evaluated),
plus `temporal_lag_seconds` and `evaluated_temporal_precision`.

## Root-cause ranking

`RootCauseRankingService` traverses only `confirmed`/`probable` edges.
`detect_cycles` performs a whole-graph DFS cycle check independent of any
specific root/terminal query (a cycle elsewhere in the organization's confirmed
graph must not be missed just because it lies off one queried path), and
`find_paths` refuses to traverse at all while any cycle exists rather than
silently resolving it. Path scoring is multiplicative (each edge's uncertainty
compounds), and the weakest single-edge confidence along the path is retained
separately on `CausalChainVersion` as `weakest_link_confidence`. Chain versions
are immutable, append-only snapshots; a chain's current state is simply its
highest `version_number` row, so no supersession pointer or mutation is ever
needed on a computed version. An edge whose persisted confidence is `NULL` is a
causal data-integrity failure: ranking raises the structured
`missing_edge_confidence` error and creates no chain version. The service never
invents or substitutes a plausible confidence value.

## Intervention and outcome learning

`CausalIntervention` links an `OperationalAction` to exactly one causal node or
edge (database-enforced XOR). `CausalOutcomeAssessment` records the observed
effect on the targeted hypothesis. A `weakened` or `refuted` outcome against a
`confirmed` hypothesis does not mutate that hypothesis (which remains
immutable) — it creates a new `draft`-lineage `under_review` hypothesis version,
sets `supersedes`-direction pointers, and marks the original `superseded`,
exactly mirroring the append-only-supersession pattern already used by
`ValueCrosswalkEntry`.

## Industry-pack integration

`app/registries/causal_method_registry.py` seeds the seven core method
definitions and two `CausalOntologyProfile` reference patterns (Job-to-Cash:
`incomplete_work_order → delayed_invoice → delayed_cash`; Oilfield Services:
`parts_shortage → repair_delay → asset_downtime → missed_service_revenue`) as
governed seed configuration, not runtime branching. These profiles are plain
Python reference data (mirroring `canonical_mapping_registry.py`'s existing,
established pattern) rather than `IndustryPackComponent` rows: the existing
`component_type` vocabulary on that table (`ontology_mapping`,
`canonical_extension`, `metric_definition`, `rule_binding`, `evidence_policy`,
`economic_mapping`, `recovery_playbook`, `command_capability`,
`usage_meter_binding`) has no `causal_ontology` value, and `industry_packs.py`
is outside this package's permitted files. Widening that CHECK constraint would
require touching an out-of-scope model and migration; reusing the registry
pattern already established for WP-2.05's own canonical mapping profiles keeps
this package fully bounded while still delivering governed, reusable seed
content.

## API

Governed catalog endpoints are under `/api/v1/causal`. Tenant operations are
under `/api/v1/organizations/{organization_id}/causal`: method listing, node
creation/retrieval, hypothesis create/propose/evaluate/review, evidence
attachment, edge and chain retrieval, chain-version computation, graph
traversal, root-cause ranking, intervention creation, and outcome assessment.

## Migration and rollback

Revision `20260806_0032` follows `20260804_0031`. It uses static Alembic table
definitions and does not import application models or live metadata. Upgrade
adds the `action_outcomes` parent candidate key and creates the 11 tables.
Downgrade removes only WP-2.08B objects and restores `action_outcomes` to its
prior state. No historical migration is modified.

## Known limitations

- Polymorphic node/evidence references (`CausalNode.target_kind`+`target_id`,
  `CausalEvidenceLink.evidence_kind`+`evidence_id`) are checked by vocabulary
  and validated by services, the same accepted limitation WP-2.05 documented
  for its own polymorphic canonical references.
- Cycle detection is application-layer (a DFS over the confirmed/probable
  edge graph at query time), not a database `CHECK`, since acyclicity cannot be
  expressed relationally.
- The Analytical Readiness hard gate checks the organization's most recent
  readiness decision rather than resolving a decision scoped to the specific
  canonical entity involved in each hypothesis — a bounded simplification.
- Statistical causal-discovery methods, Bayesian networks, structural causal
  models, and counterfactual simulation are explicitly out of scope for this
  package (see the bounded specification's causal-methods classification).
- WP-2.14B optimization, commercial frontend work, and production authentication
  remain outside this package.
- The Job-to-Cash and Oilfield Services causal-ontology profiles are static
  registry content rather than persisted, governed `IndustryPackComponent`
  rows. This is an interim substitute, not the end state: it has no tenant
  scoping, no `pack_version_id` versioning, and no `IndustryPackGovernanceEvent`
  audit trail, unlike every other pack capability. Persisting them is tracked
  as bounded follow-up debt for a future package — outside this package's
  authorized files — that widens `ck_pack_component_type` to add
  `causal_ontology` and migrates the two seed profiles into
  `IndustryPackComponent` rows.
