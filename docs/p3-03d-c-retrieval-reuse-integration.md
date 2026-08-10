# P3.03D-C Retrieval & Reuse Integration

## Purpose

D-C surfaces governed, reusable Tenant Operational Memory back into the Canonical
Mapping authoring workflow as an advisory suggestion. It reuses D-A's `retrieve()`
unchanged and adds exactly one durable field so a later authoring action can record,
if the caller chooses to say so, which exact immutable memory version influenced it.

The governing invariant is unchanged:

> Memory suggests. Canonical Mapping executes. Trust independently validates.

D-C never creates or modifies a `FieldMapping`, `MappingTemplateVersion`, or memory
decision on its own. Every write remains the existing, unchanged
`POST .../field-mappings` call, made by a human.

## Suggestions endpoint

`GET /api/v1/organizations/{organization_id}/canonical-mapping/source-schemas/{source_schema_id}/field-mapping-suggestions`

Tenant-scoped, read-only, `INGESTION_READ_ROLES`-gated (matching every other GET in
this router). For each `SourceField` under the given `SourceSchema`, it constructs a
`MemoryRetrieveRequest` (`category=FIELD_MAPPING`, `subject_kind=SOURCE_FIELD`,
`subject=field.field_path`, `context.schema_fingerprint=schema.schema_fingerprint`)
and calls `operational_memory_service.retrieve()` — D-A's existing deterministic
ranking and staleness logic, untouched.

`source_system_family` and `canonical_domain` are resolved, where available, from
`SourceSchema.dataset_id → Dataset.source_system_id → SourceSystem.system_type` and
`Dataset.domain`. When either cannot be resolved they are left `None` — never
fabricated.

## The hard context filter (release-blocking)

D-A's `retrieve()` does not hard-filter candidates by context — it filters only on
`(organization_id, category, normalized_subject, status ∈ {CONFIRMED, CORRECTED})`
and uses context match purely as a ranking tie-break and reason tag. A candidate
sharing a field name but recorded under a different schema fingerprint, source
system, or canonical domain can still be returned by `retrieve()` if fewer than
`max_suggestions` better-matching candidates exist for that subject.

D-C therefore applies its own filter on top of D-A's response: a candidate is only
surfaced as a mapping suggestion when `"exact_context_signature"` is present in its
`match_reasons`. Anything else — including a same-subject, wrong-context candidate —
is treated as no suggestion. This is implemented entirely from data D-A's response
already provides; no change to D-A was made or is required.

## Response contract

One `FieldMappingSuggestion` per `SourceField`: `source_field_path`,
`suggested_canonical_field_definition_id` / `suggested_canonical_field_code` (both
`None` when nothing passes the hard filter), `confidence_status`
(`CONFIRMED`/`CORRECTED`/`None`), `last_confirmed_at`, `matched_context_dimensions`,
`memory_id`, `memory_version_id`, and `evaluated` (always `True` unless the D-A call
itself failed, distinguishing "checked, no match" from "not evaluated"). At most one
suggestion per field; no secondary or fuzzy alternative.

## Origin lineage

One new nullable column: `FieldMapping.origin_memory_version_id: UUID | None`. `NULL`
means no memory-origin lineage was recorded — it does **not** prove independent
authorship, since a caller can simply omit it. Non-`NULL` means the authoring action
that created this `FieldMapping` declared it was influenced by that exact, immutable
`OperationalMemoryVersion`.

The identifier is a **version** ID, not an item ID, deliberately: an item's current
version can move (further confirmation, correction, deprecation) after a suggestion
was shown, but the version that actually influenced the decision remains permanently
resolvable via D-A's immutability guarantee. If the memory is later `CORRECT`ed, the
`FieldMapping`'s lineage keeps pointing at the original version — it is never
rewritten.

Whether the accepted suggestion was used unchanged or the canonical target was
changed before submission is derivable on read — compare the `FieldMapping`'s
current `canonical_field_definition_id` against the origin version's
`value_payload["canonical_field_definition_id"]` — rather than stored redundantly.

## Organization-scope hard gate

`FieldMapping` carries no `organization_id` of its own: templates may be
`shared_core`, `industry`, `regional`, or `organization` scoped, and only
`organization` scope has a single tenant owner. Persisting a tenant-scoped memory
reference on a `FieldMapping` belonging to a shared template would leak that
reference to every other tenant using the same template. D-C v1 therefore only
accepts `origin_memory_version_id` when the target `MappingTemplateVersion`'s
template has `scope_type == "organization"` and `owner_organization_id` equals the
caller's organization. Any other scope rejects the lineage deterministically
(`ORIGIN_LINEAGE_TEMPLATE_SCOPE_INVALID`) rather than silently dropping it.

## Memory version validation (never trust the client)

When `origin_memory_version_id` is supplied, `add_field_mapping()` re-validates,
server-side, against currently-stored state — never against whatever the client
claims:

- the version exists and belongs to the caller's organization
  (`ORIGIN_MEMORY_VERSION_NOT_FOUND` otherwise, matching D-A's safe not-found
  convention rather than leaking cross-tenant existence);
- the version's item exists, is in the caller's organization, and is
  `category == FIELD_MAPPING`;
- the item's **current** status is `CONFIRMED` or `CORRECTED`, is not `is_stale`, and
  has not expired (`ORIGIN_MEMORY_NOT_REUSABLE` otherwise).

Validation checks the item's current state, not the historical version's own label —
this is what makes stale-browser replay safe: a version that was legitimately
`CONFIRMED` when a suggestion was shown, but whose item has since moved to
`DEPRECATED` (or any other non-reusable state), is correctly rejected if a client
replays it later.

## No new API for acceptance

There is no "use suggestion" write endpoint. The frontend pre-fills the authoring
form from the suggestions response; the user still explicitly submits the existing
`POST .../field-mappings`, now carrying `origin_memory_version_id` only if they chose
to keep the suggestion. Rejection/dismissal is UI/session-local only — no backend
call, no automatic memory `REJECT`, no new reuse-event type.

## Boundaries unchanged by this package

D-A's models, schemas, service, and routes are untouched. D-B's evidence-registration
semantics (`support_count`, `confirmation_count`, actor semantics, replay safety) are
untouched — a future package may teach D-B to read `origin_memory_version_id` and
distinguish memory-derived from independent execution evidence, but that is
explicitly out of scope here. No new entitlement, role, table, or AI/vector
dependency of any kind.

## Deferred

- D-B evidence-origin classification (memory-derived vs. independent).
- Dismissal-as-reuse-event, or any new `OperationalMemoryReuseEvent` type.
- Suggestions/lineage for `shared_core`/`industry`/`regional` templates.
- `neighboring_field_signatures` context enrichment.
- D-D effectiveness/acceptance-rate measurement.
