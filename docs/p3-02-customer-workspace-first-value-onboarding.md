# P3.02 Customer Operational Workspace & First-Value Onboarding

P3.02 turns the authenticated organization context P3.01 delivers into a
workspace the customer can actually use: a company profile, an industry,
business objectives, operational challenges, systems in use, a team
summary, and a truthful readiness signal for when they're ready for their
first Value Scan. It does not implement Connect ingestion, document
parsing, or any analytical engine — it prepares the operational context
those packages will later consume.

Customer-facing language calls this the **Operational Profile**. The
backend entity remains `Organization` throughout — the rename is UX
language only, applied in schema field labels and documentation, never in
the model, table, or service names.

## Boundary

Exactly 3 new tables, all direct children of `Organization` (simple
`organization_id` FK, `ON DELETE CASCADE` — no composite-key retrofit is
needed since none of them has a further downstream child referencing them):

- `organization_objectives` — business priorities the org has selected.
- `organization_challenges` — operational challenges the org has explicitly
  stated (never inferred from objective selections).
- `organization_systems` — systems the org says it uses. Metadata only: no
  credentials, no endpoints, no connection health. Connect owns all of
  that later.

All three share the same shape (`id`, `organization_id`, `<x>_code`,
`selected_by_user_id`, `selected_at`, `created_at`) and the same mutable
lifecycle: selecting adds a row, deselecting removes it. No append-only
history or supersession — these are live customer preferences, not
governance/audit objects.

`Organization` gains exactly 4 new nullable columns: `sub_industry`,
`employee_count_range`, `annual_revenue_range`, `operating_site_count`. The
6 fields P3.02 originally wanted that already existed on `Organization`
(name, industry, country_code, default_currency, timezone, description)
were reused as-is, not duplicated.

Migration `20260809_0035` follows `20260808_0034`. Static DDL, no
historical migration modified.

## Governed registries

`app/registries/{industry,objective,challenge,system}_registry.py` are
plain Python constant data — no backing table, mirroring the
`causal_method_registry.py` pattern already established in this repo. None
of them is tied to the paid, entitlement-gated `IndustryPackDefinition`
catalog (`app/models/commercial.py`): that catalog's "industries" are
actually product capability packs (`job_to_cash`, `manufacturing`, `ports`,
`mobility` — note `job_to_cash` isn't even an industry), a different
concept from a customer's free self-reported industry. Conflating the two
would tie onboarding UX to billing state. Selecting an industry here never
grants, implies, or requires an industry pack.

- **Industries** (11 + Other): oil_and_gas, oilfield_services,
  manufacturing, mining, ports_and_logistics, public_transportation,
  utilities, retail, construction, healthcare, other. Each carries
  declarative-only metadata (`operational_archetype`,
  `typical_system_categories`, `recommended_objective_codes`,
  `recommended_challenge_codes`) — hints for future UX, never platform
  branching logic.
- **Objectives** (12): increase_revenue, improve_job_to_cash,
  reduce_downtime, improve_maintenance, improve_asset_utilization,
  reduce_fuel_loss, reduce_inventory_leakage, improve_procurement,
  improve_reliability, improve_cash_flow, reduce_operational_risk,
  improve_service_delivery. Distinct from Decision Intelligence's
  `DecisionObjective` (mathematical solver objectives) — no code or table
  is shared between the two; they live at different API paths
  (`/objectives` vs. `.../decisions/problem-versions/{id}/objectives`) and
  were confirmed to register with zero collision.
- **Challenges** (15): revenue_leakage, late_invoicing, downtime,
  maintenance_backlog, poor_asset_utilization, fuel_loss,
  inventory_leakage, procurement_delay, cash_flow, scheduling,
  workforce_constraints, quality_or_rework, reliability, service_delivery,
  operational_risk.
- **Systems** (20 codes across 12 categories): SAP, Oracle, Microsoft
  Dynamics, Odoo, ERPNext, QuickBooks, Sage, NetSuite, Maximo, IFS, Infor,
  Salesforce, CMMS, MES, SCADA, WMS, TMS, Excel, Custom ERP, Custom
  Database, Other. `custom_erp`/`custom_database`/`other` are the only
  codes with `allows_custom_label = True`; every other code rejects a
  supplied `custom_label`. This is distinct from Connect's
  `source_systems` registry (registered, connectable systems) — no
  collision, confirmed via the generated OpenAPI schema.

The two new range-code fields (`employee_count_range`,
`annual_revenue_range`) are validated at the Pydantic schema layer in
`app/schemas/contracts.py` against their governed value lists, not a
database `CHECK` constraint — per the approved decision, this keeps the
registries easy to extend without a migration.

`industry` itself is **not** schema-enforced against the registry, despite
being a governed catalog. `OrganizationBase`/`OrganizationUpdate` back both
the pre-existing platform-admin `POST /api/v1/organizations` route and the
profile-update `PATCH` route this package reuses; a pre-existing,
out-of-allowlist test (`tests/test_organizations_api.py`) creates
organizations with an industry value (`"transportation"`) that predates and
isn't in the P3.02 registry. Since neither that test file nor
`app/api/routes.py` is authorized for modification in this package, adding
a strict validator there would have broken existing, unrelated behavior to
enforce a P3.02-only rule. `GET /api/v1/industries` remains the intended
source of truth for the frontend's industry picker; the backend accepts
whatever string is supplied, exactly as it did before this package.

## Company profile

| Field | Source |
|---|---|
| name, industry, country, timezone, currency, description | existing `Organization` columns, reused |
| sub_industry | new, optional |
| employee_count_range | new, optional, governed range code (`1_10` … `5001_PLUS`) |
| annual_revenue_range | new, optional, governed range code (`under_1m` … `over_1b`) |
| operating_site_count | new, optional, non-negative integer — no location/address model |
| logo | **not built** — no file/blob storage capability exists anywhere in this repo |

Profile updates reuse the existing `PATCH /api/v1/organizations/{id}` route
(`app/api/routes.py`, already gated by `ORGANIZATION_ADMIN_ROLES`) rather
than a new endpoint — its request/response schemas were extended with the
4 new fields instead of standing up a parallel profile API.

## Team and persona labels

Persona labels are presentation-only, computed at read time, never
persisted, never used for authorization:

| Persona | `MembershipRole` |
|---|---|
| Admin | `organization_admin` |
| Operations | `operator` |
| Finance | `recovery_manager` |
| Analyst | `analyst` |
| Viewer | `viewer` |

No "Owner" distinction is inferred or stored — per the approved decision,
`organization_admin` always displays as **Admin**. `platform_admin` has no
persona label; it is not a customer-facing organization role.
`GET /api/v1/organizations/{id}/team-summary` aggregates existing P3.01
membership/invitation data (active count, pending invitations, counts by
role and by persona) via new read-only queries — it does not duplicate any
membership/invitation write logic.

## Readiness — three separate, never-averaged concepts

**Workspace setup readiness** (P3.02-owned, a percentage): six components
— `profile`, `industry`, `objectives`, `challenges`, `systems`, `team` —
of which only `profile`, `industry`, and `objectives` (≥1 selected) are
*required*; the other three count toward the displayed percentage but never
block readiness. A workspace cannot reach `missing_required == []` just by
filling in challenges/systems/team while skipping industry or objectives.

**Data readiness** (v1, minimally derived): `NOT_STARTED` or `HAS_DATA`,
based purely on whether any `IngestionBatch`/`Dataset` row exists for the
organization. Deliberately not a full derivation of Connect/Trust's real
lifecycle states (`IngestionBatchStatus`, `DatasetVersionStatus`,
`TrustAssessmentStatus`, `ReadinessStatus` all exist and are richer) — that
coupling is deferred until Connect itself is upgraded, to avoid this
package taking on a dependency it doesn't own.

**AI readiness** (derived only, never stored): `NOT_READY` (workspace not
ready) → `PENDING_DATA` (workspace ready, no data) → `PENDING_TRUST` (data
exists, no `AnalyticalReadinessDecision` evidence supports it yet) →
`READY` (the organization's most recent `AnalyticalReadinessDecision.readiness_status`
is `ready` or `ready_with_warnings`). If no readiness decision exists yet,
the truthful answer is `PENDING_TRUST`, never a faked `READY`.

## First-value handoff

`SETUP_IN_PROGRESS → DATA_PENDING → TRUST_PENDING → READY_FOR_VALUE_SCAN`.

A standalone `WORKSPACE_READY` handoff value was deliberately **not**
exposed: with data readiness limited to two states in this v1, there is no
truthful way to distinguish "workspace just became ready" from "workspace
ready, still no data" — they're the same observable state. That signal is
still available as `setup_progress.missing_required == []`, just not as a
separate `handoff_state` enum value. `READY_FOR_VALUE_SCAN` requires real
`AnalyticalReadinessDecision` evidence, not merely the presence of ingested
rows — verified by an adversarial test that reaches 100% required setup
plus real ingested data and confirms the state still reads `TRUST_PENDING`
until a readiness decision is added.

## Concurrency

`replace_objectives`/`replace_challenges`/`replace_systems` all row-lock
the `Organization` (`SELECT ... FOR UPDATE`, the same
`_lock_organization` pattern `membership_service.py` uses) before reading
the existing selection set. Without it, two concurrent `PUT` calls for the
same organization could each read an empty "existing" set and both insert,
leaving a stale selection that should have been replaced. A PostgreSQL
concurrency test drives two threads through `replace_objectives` with
disjoint codes and asserts exactly one row survives.

## API

- `GET /api/v1/industries`, `/objectives`, `/challenges`, `/systems` —
  catalogs, authenticated-only (no organization scope).
- `GET /api/v1/organizations/{id}/workspace-summary` — the single
  aggregator: profile, industry, objectives, challenges, systems, team
  summary, setup progress, data/AI readiness, handoff state, next step.
- `GET`/`PUT /api/v1/organizations/{id}/objectives`, `/challenges`,
  `/systems`.
- `GET /api/v1/organizations/{id}/team-summary`.
- `PATCH /api/v1/organizations/{id}` — reused, extended.

Reads: `ORGANIZATION_READ_ROLES`. Writes: `ORGANIZATION_ADMIN_ROLES`. No
new role tuples were added to `app/auth/permissions.py` — every gate
reuses the existing pair directly, the same way over a dozen other domains
in this platform already do.

## Frontend contract (not implemented in this repository)

This repository remains backend-only. Screens: Workspace Home, Operational
Profile, Industry & Objectives, Operational Challenges, Systems In Use,
Team, Onboarding Progress, Data Sources (placeholder), Settings. Each
screen's states are loading / empty / partial / complete; errors map to
401 (re-authenticate), 403 (render read-only), 404 (return to organization
picker). Permissions: `ORGANIZATION_READ_ROLES` can view every screen;
`ORGANIZATION_ADMIN_ROLES` can edit profile/industry/objectives/challenges/systems.
Customer-facing copy should say "Your Company," "Your Team," "Your
Priorities," "Your Data," "What Intel4Ops Is Ready To Analyze," "Next
Step" — never canonical mapping, tenant FK, dataset version, entitlement
row, Alembic, or registry.

## Telemetry (semantics only, no vendor introduced)

`workspace_opened`, `operational_profile_updated`, `industry_selected`,
`objective_selected`, `challenge_selected`, `system_selected`,
`workspace_ready`, `data_detected`, `trust_pending`, `ready_for_value_scan`.
No event carries secrets, tokens, or PII beyond governed identifiers. No
telemetry mechanism exists in this repository (confirmed during
investigation) and none was added — emission is left to the frontend or a
future dedicated package.

## Migration and rollback

Revision `20260809_0035` follows `20260808_0034`. Adds the 4 `Organization`
columns (plus a `CHECK` on `operating_site_count >= 0`) and the 3 new
tables via static DDL. Downgrade removes exactly what upgrade added. No
historical migration modified. Verified via a full disposable-PostgreSQL
upgrade → downgrade → re-upgrade cycle and offline SQL generation.

## Known limitations

- Data readiness is a minimal existence check (`NOT_STARTED`/`HAS_DATA`),
  not a full derivation of Connect/Trust's real lifecycle states — an
  intentional, documented scope boundary, not an oversight.
- No `WORKSPACE_READY` handoff state is exposed as its own enum value, for
  the reason described above; only `DATA_PENDING`, `TRUST_PENDING`,
  `SETUP_IN_PROGRESS`, and `READY_FOR_VALUE_SCAN` appear.
- Persona mapping is a best-available fit for two labels: Executive →
  Analyst and Finance → Recovery Manager map onto existing roles that
  weren't designed with those exact personas in mind.
- No "Owner" distinction exists at the data layer; the organization
  creator is indistinguishable from any later-added `organization_admin`.
- Logo/branding is entirely deferred — no file storage capability exists
  in this repository to support it.
- Employee count and annual revenue are governed ranges, never exact
  figures, by design.
