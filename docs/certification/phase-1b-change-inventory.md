# Phase 1B Change Inventory

Baseline is merge commit `3db1445abfb03afaff50a76d2967504e6c2dc6c0`. Phase 1B consists
of the seven commits below and does not include a push, pull request, merge, or tag.

## `ee17022` — Source lifecycle and administrator safety

Files:

- `app/models/source_system.py`
- `app/services/ingestion_service.py`
- `app/services/membership_service.py`
- `app/services/source_system_service.py`
- `docs/source-systems.md`
- lifecycle setup/regression updates in `tests/test_finding_platform.py`,
  `test_forecasting_service.py`, `test_ingestion_api.py`, `test_ingestion_service.py`,
  `test_intelligence_api.py`, `test_intelligence_service.py`,
  `test_membership_authorization_api.py`, `test_progressive_orchestrator.py`,
  `test_source_system_service.py`, and `test_statistical_service.py`

Purpose and effect: new downstream objects require an active source; tenant lookup precedes
lifecycle disclosure; historical reads remain available. Decommissioned sources retain only
description and owner-contact edits. Organization-row locking serializes final-admin changes.
The API now returns the existing domain conflict response when a prohibited source is used.

Compatibility: clients that created downstream records before activating a source must follow
the lifecycle first. Rollback restores permissive creation and the prior concurrency exposure.

## `a84ba17` — ProcessingRun lineage anchoring

Files:

- `app/models/raw_lineage.py`
- `app/schemas/raw_lineage.py`
- `app/services/raw_lineage_service.py`
- `docs/raw-storage-lineage.md`
- `tests/test_raw_lineage_api.py`
- `tests/test_raw_lineage_service.py`

Purpose and effect: transformation runs require a batch or dataset-version anchor; anchor
organization and consistency are checked; run and anchor nodes receive idempotent
`consumed_by` edges. Raw registration receives the source-lifecycle guard.

Compatibility: `custom` and `integrity_verification` remain valid without anchors. Rollback of
the migration removes database enforcement, while reverting this commit removes service and
schema enforcement.

## `fef9aa0` — Foundational database constraints

Files:

- `app/models/entities.py`
- `migrations/versions/20260728_0023_foundation_hardening.py`
- `tests/test_foundation_constraints.py`
- `tests/test_postgres_migrations.py`

Purpose and effect: installs database state checks, ProcessingRun anchor enforcement, and the
Trust idempotency schema. The migration rejects unexpected pre-existing state values rather
than rewriting data. PostgreSQL migration and concurrent-admin regression coverage were added.

Compatibility: valid current values are unchanged. A downgrade drops the added constraints
and Trust idempotency columns, losing idempotency metadata if executed after new keyed
assessments exist.

## `f9fd2af` — Trust idempotency and safe errors

Files:

- `app/api/trust_routes.py`
- `app/models/trust.py`
- `app/schemas/trust.py`
- `app/services/trust_service.py`
- `docs/trust-engine.md`
- `tests/test_trust_api.py`
- `tests/test_trust_service.py`

Purpose and effect: optional organization-scoped idempotency keys use a canonical SHA-256
request fingerprint. Identical retries return the existing result; different requests return
409. Database uniqueness handles races. Cross-tenant resources return generic 404 semantics.

Compatibility: the key is optional and existing clients remain valid. Rollback removes replay
protection and should not be performed without accepting possible duplicates.

## `5e1c32c` — Foundation integration

File: `tests/test_foundation_integration.py`.

Purpose: certifies the normal organization-to-readiness path and explicitly records that Trust
still consumes inline/manual input rather than governed stored records.

## `159ea21` — FR-015/FR-016 proposal

File: `docs/phase-1-governed-trust-input-proposal.md`.

Purpose: evaluates future governed input snapshots, schema versions, mapping versions,
materialization/projections, and reproducible Trust bindings. It changes no runtime behavior
and is neither implemented nor approved.

## `3235f43` — Trust concurrency test

File: `tests/test_postgres_migrations.py`.

Purpose: proves two concurrent identical keyed Trust requests create one assessment and one set
of rule results.

## Schema and security inventory

- Migration: `20260728_0023`, previous `20260728_0022`.
- New columns: `trust_assessments.idempotency_key`,
  `trust_assessments.request_fingerprint`.
- New checks: organization status, finding severity/status, recovery-action status,
  ProcessingRun data anchor, and Trust idempotency column pairing.
- New unique constraint: organization plus Trust idempotency key.
- No new table or index was introduced.
- Tenant isolation changed only to tighten tenant-first source and Trust lookups.
- Permissions were not broadened.
- Lineage creation gained automatic ProcessingRun anchor edges.
- No canonical mapping, source history, Trust override, or shared audit runtime was added.
