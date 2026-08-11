# P3.03E.1 Finding Governance Tier

## Decision and scope

The shared `findings` table previously made no explicit, durable distinction
between a Finding published through the fully governed publication contract
and a Finding created by any other producer. P3.03E.1 makes that distinction
explicit, persisted, and database-enforced via `Finding.governance_tier`.

Exactly two values are allowed, matching the frozen product decision:

- `GOVERNED` — created through `FindingPublicationService.publish_candidate_finding`,
  carrying the complete governed lineage/publication contract.
- `LIGHTWEIGHT` — created through any other path. This does **not** mean
  incorrect or low quality; it means the Finding does not carry the complete
  governed publication guarantees (evidence bundle, calculation/rule traces,
  full lineage FKs).

No third tier exists at any layer (model, migration, schema, or API filter).

## Classification by creation path

| Producer | File | Tier |
|---|---|---|
| Governed publication | `app/services/finding_platform_service.py` (`FindingPublicationService.publish_candidate_finding`) | `GOVERNED` |
| Legacy Finding API / Job-to-Cash | `app/services/finding_service.py` (`FindingService.create`) | `LIGHTWEIGHT` |
| Industry Pack rule execution | `app/services/industry_pack_service.py` | `LIGHTWEIGHT` |
| Operational Signature execution | `app/services/signature_service.py` | `LIGHTWEIGHT` |
| Maintenance demo (`POST /api/v1/intelligence/maintenance/analyze`) | routes through `FindingService.create` | `LIGHTWEIGHT` |

Every creation site sets `governance_tier` explicitly in application code.
There is no ORM-level or database `DEFAULT` for the column — a creation path
that fails to set it explicitly fails the `NOT NULL` constraint at insert
time rather than silently defaulting to a tier.

Job-to-Cash was not migrated to the governed publication path in this
package (frozen decision); its Findings remain `LIGHTWEIGHT`. Industry Pack
and Operational Signature rule/detection/economics/entitlement behavior is
unchanged — only the explicit tier assignment was added.

## Migration

Alembic revision `20260816_0042` (`migrations/versions/20260816_0042_finding_governance_tier.py`):

1. Adds `governance_tier` as a nullable `VARCHAR(20)` column.
2. Backfills every existing row deterministically:
   `GOVERNED` when `source_execution_id`, `trust_assessment_id`,
   `analytical_readiness_id`, and `dataset_id` are **all** non-null;
   `LIGHTWEIGHT` otherwise. No other column (finding_code, deduplication_key,
   oikb_definition_id, content_fingerprint, title, description, producer
   identity) is consulted, and no row is left `NULL` or classified `UNKNOWN`.
3. Validates zero remaining `NULL` values before proceeding.
4. Enforces `NOT NULL`.
5. Adds `ck_findings_governance_tier` (`GOVERNED` / `LIGHTWEIGHT` only).
6. Adds `ix_findings_organization_governance_tier` on
   `(organization_id, governance_tier)`, following the existing
   `ix_findings_organization_<field>` convention.

Downgrade removes the index, constraint, and column in that order. The
upgrade → downgrade → re-upgrade lifecycle was verified against a full
migration-chain replay on SQLite (see certification report); PostgreSQL
certification is the authoritative target and is tracked separately (see
Known limitations).

## API contract

`GET /api/v1/organizations/{organization_id}/findings` gained a
`governance_tier` query parameter:

- Omitted (default): only `GOVERNED` rows are returned. A frontend making a
  normal, untiered request cannot accidentally receive `LIGHTWEIGHT` rows.
- `governance_tier=LIGHTWEIGHT`: only `LIGHTWEIGHT` rows are returned.

No `ALL` value is accepted or persisted; `ALL` is not part of this contract.
Every query remains explicitly `organization_id`-scoped; the tier filter adds
no cross-tenant surface.

`governance_tier` is exposed on the governed `FindingRead` schema
(`app/schemas/findings.py`) and on the legacy `FindingRead` schema
(`app/schemas/contracts.py`).

To support real `LIGHTWEIGHT` rows (Industry Pack / Operational Signature
shape) round-tripping through the same governed `FindingRead` response model
under an explicit `governance_tier=LIGHTWEIGHT` query, several `FindingRead`
fields that only governed publications always populate were widened from
required to optional, and `finding_type`/`confidence_level`/
`measured_value_type`/`exposure_value_type` accept either their governed
enum or a free-form string (lightweight producers use vocabularies —
`"deterministic_rule"`, `"operational_signature"`, `"observed"`,
`"estimated"`, `"medium"` confidence — that fall outside the governed enums).
`FindingStatusValue` was also extended with `open`/`accepted`/
`in_recovery`/`verified`, matching the values already allowed by the
model-level `ck_findings_status` constraint. Governed responses are
byte-for-byte unaffected: every field a governed publication populates
still round-trips exactly as before.

## Legacy route isolation

Three legacy/demo routes in `app/api/routes.py` are hidden from the
generated OpenAPI schema (`include_in_schema=False`) without any change to
authorization or entitlement behavior:

- `POST /api/v1/intelligence/maintenance/analyze`
- `GET /api/v1/command/findings`
- `POST /api/v1/recovery/actions`

They remain callable. This is documentation/API-surface isolation only; it
is not the CM-04 entitlement-hardening work, which is out of scope here.

## Known limitations

- **PostgreSQL certification not executed in this session.** No disposable
  PostgreSQL credentials were available (see the final report). The
  migration was verified end-to-end — full chain upgrade from base,
  upgrade → downgrade → re-upgrade, resulting schema (column, `NOT NULL`,
  check constraint, index) — against SQLite, and the PostgreSQL-specific
  certification tests (`tests/test_postgres_migrations.py::test_p3_03e1_*`)
  are authored and collect cleanly but have not been executed against a
  live PostgreSQL instance. This should be run before independent
  certification is granted.
- **Pre-existing, unrelated defect discovered during testing (not fixed):**
  `IndustryPackService.execute` mutates the `result_json` dict in place
  after the row has already been flushed once; because the object identity
  does not change, SQLAlchemy's change tracking does not detect the later
  `finding_id` / `opportunity_id` / `recovery_action_id` additions as
  dirty, and they are silently absent from the persisted `result_json` for
  any non-Job-to-Cash pack execution. This predates P3.03E.1, is unrelated
  to governance tiering, and touching it would exceed the "no change to
  rules, detection, economics, entitlements, or output" boundary in section
  10 of the work order. Recorded here as known/deferred, not silently
  fixed.
- Legacy route entitlement gap discovered during P3.03E (pre-existing):
  known/deferred, not fixed here, consistent with the work order.
