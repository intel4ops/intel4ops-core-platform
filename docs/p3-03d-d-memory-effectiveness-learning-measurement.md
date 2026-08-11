# P3.03D-D Memory Effectiveness & Learning Measurement

## Purpose

Answers, truthfully and tenant-scoped: **is Intel4Ops getting better for this
tenant over time?** D-D is measurement only — it computes deterministic
statistics from governed rows already written by D-A/D-B/D-C/D-C.1. It never
mutates memory, mapping, or Trust state, and it never claims time saved,
productivity gained, or dollar value.

## Endpoint

`GET /api/v1/organizations/{organization_id}/canonical-mapping/memory-effectiveness`

Query parameters (all optional): `source_schema_id`, `date_from`, `date_to`.
Read-only. Reuses the existing `connect.canonical_mapping` commercial
entitlement and `INGESTION_READ_ROLES`, exactly as
`GET .../operational-memories` and `POST .../operational-memories/retrieve`
already do — no new role, no new entitlement.

## Terminology (frozen)

- **OBSERVED METRIC**: a deterministic number computed directly from governed
  rows. Every number in this response is one.
- **INFERRED PRODUCT BENEFIT** (e.g. "mapping was faster"): not computed here.
- **VERIFIED BUSINESS VALUE** (e.g. "18 hours saved", "$X recovered"): not
  computed here; belongs to Recovery / Verified Value.
- **SUGGESTION RETRIEVED**: a candidate came back from `retrieve()` — proves
  nothing about whether it was used.
- **SUGGESTION USED**: a `FieldMapping` was authored with
  `origin_memory_version_id` set to that candidate's version.
- **SUGGESTION USED UNCHANGED** / **USED MODIFIED**: see below.

## KPI formula register

All seven are computed on demand against current governed state — nothing is
materialized, cached, or scheduled.

1. **Exact-Context Coverage %** — of `SourceField`s in scope, what share
   currently have at least one eligible (`CONFIRMED`/`CORRECTED`, not stale,
   not expired) `OperationalMemoryItem` with an exact `context_signature`
   match. `covered_field_count / source_field_count * 100`. `null` if
   `source_field_count == 0`.
2. **No-Match Rate %** — `100 − coverage`. `null` under the same condition.
3. **Memory Reuse Rate %** — `FieldMapping` rows with
   `origin_memory_version_id IS NOT NULL`, divided by all organization-scoped
   `FieldMapping` rows. `null` if the denominator is `0`.
4. **Unchanged Reuse %** — of *resolved* reused mappings (reused minus
   unresolved-origin), the share whose current `canonical_field_definition_id`
   matches the origin version's frozen `value_payload`. `null` if the resolved
   denominator is `0`.
5. **Modified Reuse %** — the complement of (4) over the same resolved
   denominator.
6. **Contradiction Rate %** — `OperationalMemoryItem` rows with
   `contradiction_count > 0`, over all `FIELD_MAPPING` items for the tenant.
   `null` if `0` items.
7. **Stale Memory Rate %** — `is_stale = true` rows over the same denominator.
   `null` if `0` items. An optional bounded `stale_reason_breakdown` (by the
   six fixed `STALE_REASONS` values) accompanies this, not as an opaque score.

None of these are combined into a single composite "learning score."

## Tenant scope and the shared-template exclusion (hard gate)

Every query filters `organization_id` directly (`OperationalMemoryItem`,
`SourceField`, `SourceSchema`) or, for `FieldMapping` (which carries no
`organization_id` of its own), through
`FieldMapping.template_version_id → MappingTemplateVersion.template_id →
MappingTemplate.owner_organization_id`, **with an explicit
`MappingTemplate.scope_type == "organization"` filter**. Omitting that second
condition would silently pull `shared_core`/`industry`/`regional` template
mappings into a tenant's own reuse rate — those are not this tenant's authored
outcome. This is enforced identically in coverage (via `SourceSchema`) and
reuse (via the template join).

## Current vs. historical coverage (measurement-integrity gate)

The trend/learning-curve series reports **current-state** coverage per
`SourceSchema`, ordered by `discovered_at` — it does **not** reconstruct
eligibility as it stood at each schema's discovery time, and is not labeled as
such. This was verified, not assumed: `OperationalMemoryItem.is_stale` (a
required eligibility gate) is computed lazily against *live* external state
(`SourceSchema.status`, `MappingTemplateVersion.lifecycle_status`) each time
`OperationalMemoryService.retrieve()` runs, and is stored only as a current
flag — no history of past staleness evaluations exists anywhere. True
point-in-time reconstruction is therefore not possible without fabricating
data D-A never recorded. Every trend point genuinely reflects "if we asked
right now," not "as of when this schema first appeared" — see
`test_trend_reflects_current_state_not_historical_discovery_time` for the
explicit proof (a schema discovered before any memory existed still reports
100% coverage once memory is confirmed later).

A second, related honesty note: `is_stale` is read exactly as currently
stored, never recomputed by D-D (recomputation is a `retrieve()`-only
side-effect that mutates the item, which D-D must never do). Coverage can
therefore be marginally optimistic for items that have not been retrieved
recently enough to trigger D-A's own lazy staleness refresh — an accepted,
documented characteristic of a strictly read-only measurement layer, not a
defect.

## Reuse classification: unresolved origin

A reused `FieldMapping` (`origin_memory_version_id IS NOT NULL`) is classified
into exactly one of three buckets: **unchanged**, **modified**, or
**unresolved** (the origin `OperationalMemoryVersion` cannot be resolved —
missing, cross-tenant, or a malformed `value_payload`). Unresolved mappings
still count toward `memory_derived_mapping_count` (the raw fact "lineage was
recorded" is unconditional) but are excluded from the unchanged/modified
percentage denominators, so those two percentages sum to 100% exactly when
every origin resolves, and never fabricate a classification for a row that
cannot honestly support one.

## Zero-denominator handling

Every percentage in this response is `null`, never a fabricated `0%`/`100%`,
whenever its denominator is zero. This applies uniformly to coverage, reuse,
unchanged/modified reuse, and quality rates.

## Auditability / drill-down

Every KPI resolves to real rows: Reuse Rate → `FieldMapping` →
`origin_memory_version_id` → `OperationalMemoryVersion` →
`OperationalMemoryItem`. Coverage → `SourceSchema` → `SourceField` → the
matching eligible `OperationalMemoryItem`. No metric depends on a model
output or hidden computation.

## Known limitations (documented, not fixed here)

- **Actor attribution**: `OperationalMemoryReuseEvent` has no actor field and
  `FieldMapping` has no `created_by_user_id` (unlike `MappingRun`, which
  does). D-D v1 does not expose "who retrieved" or "who authored" metrics, and
  does not attempt to infer this via `MappingRun.created_by_user_id`.
- **FINDING-CM-PRE01** (FieldMapping creation idempotency gap, pre-existing,
  open): existing unique constraints (`uq_field_mapping_version_sequence`,
  `uq_field_mapping_source_target`) narrowly bound the possibility of
  duplicate `FieldMapping` rows from a client retry, but do not eliminate it
  entirely. Such a duplicate would count as an extra data point in the reuse
  rate's denominator and numerator. Not remediated by D-D; documented here as
  a measurement-accuracy caveat.
- **FINDING-CM-PRE02** (entitlement-pattern asymmetry, pre-existing, open):
  unrelated to metric correctness — affects only which routes require which
  authorization mechanism. The new D-D route itself uses the correct, standard
  `require_commercial_entitlement` pattern (matching the operational-memory
  routes), not the weaker `require_organization_roles`-only pattern used by
  some existing Canonical Mapping routes; it does not remediate those other
  routes.

## What D-D does not do

No timing/effort/dollar-value metric of any kind (see Section Q of the prior
architecture investigation for the full reasoning — no timestamp in the
system isolates active human decision time from calendar elapsed time). No
cross-tenant or industry benchmark. No AI/ML/embedding/predictive scoring. No
new table, column, index, or migration. No mutation of memory, mapping,
Trust, Findings, or Recovery state.
