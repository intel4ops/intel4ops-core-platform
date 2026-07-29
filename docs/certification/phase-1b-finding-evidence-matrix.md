# Phase 1B Finding-to-Evidence Matrix

This matrix is an index for independent review. A reviewer should inspect the cited
implementation and execute the named tests rather than relying on the disposition label.

## FR-003 — Last active organization administrator

- Original issue: two concurrent changes could jointly remove every active organization admin.
- Disposition: **remediated**.
- Implementation: `app/services/membership_service.py`;
  `OrganizationMembershipService.update_role`, `suspend`, `revoke`,
  `_lock_organization`, and `_protect_last_active_admin`.
- Database/concurrency evidence: the organization row is locked with `FOR UPDATE`, providing
  a deterministic PostgreSQL serialization point.
- Tests: `tests/test_membership_service.py::test_last_active_admin_is_protected`;
  `tests/test_postgres_migrations.py::test_concurrent_admin_changes_cannot_remove_all_active_admins`.
- Tenant evidence: the lock and count are constrained by `organization_id`.
- Limitation: SQLite validates the rule but cannot reproduce PostgreSQL row-lock concurrency.
- Review: run the PostgreSQL concurrency test and verify one of two simultaneous demotions is
  rejected and one active admin remains.

## FR-005 — Identity-level platform administration

- Original issue: the intended scope of `is_platform_admin` lacked bounded explicit tests.
- Disposition: **remediated**.
- Implementation: unchanged authorization behavior in `app/auth/authorization.py`;
  evidence was added without widening privileges.
- Tests:
  `tests/test_membership_authorization_api.py::test_platform_admin_claim_manages_memberships_across_organizations`,
  `test_missing_identity_and_client_user_id_cannot_bypass_authentication`, and
  `test_platform_admin_membership_does_not_bypass_tenant_scope`.
- Tenant/permission evidence: only the authenticated identity claim activates the global path.
- Review: verify the identity fixture changes only the authenticated claim, not membership data.

## FR-006 — PLATFORM_ADMIN membership scoping

- Original issue: a membership row named `platform_admin` could be mistaken for a global bypass.
- Disposition: **remediated**.
- Implementation: existing `require_organization_roles` remains identity-claim based; no role
  broadening was introduced.
- Tests:
  `tests/test_membership_authorization_api.py::test_platform_admin_membership_does_not_bypass_tenant_scope`
  and `test_existing_tenant_endpoints_enforce_authenticated_membership`.
- Tenant evidence: the membership is denied in both its own and another tenant when the
  identity-level claim is false; the approved identity path is tested separately.
- Review: inspect `app/auth/authorization.py` and confirm membership role values never trigger
  the global branch.

## FR-010 — ProcessingRun anchoring and lineage

- Original issue: transformation runs could be unanchored and creation registered no anchor edge.
- Disposition: **remediated**.
- Implementation: `app/schemas/raw_lineage.py::ProcessingRunCreate.require_data_anchor`;
  `app/models/raw_lineage.py::ProcessingRun`; and
  `app/services/raw_lineage_service.py::ProcessingRunService.create`, `_tenant_entity`.
- Migration evidence: `20260728_0023`, constraint `ck_processing_runs_data_anchor`.
- Tests: `tests/test_raw_lineage_service.py::test_processing_run_lifecycle_counts_and_events`,
  `test_lineage_duplicate_edges_cycle_prevention_and_tenant_scope`;
  `tests/test_foundation_constraints.py::test_processing_run_data_anchor_is_database_enforced`;
  API coverage in `tests/test_raw_lineage_api.py`.
- Tenant/idempotency evidence: anchors are loaded by `id` and `organization_id`; lineage
  duplicate-edge protection remains active.
- Limitation: `integrity_verification` and `custom` are deliberately allowed without a data
  anchor as infrastructure-only modes.
- Review: attempt an unanchored `mapping` insert independently of Pydantic, then verify the
  database rejects it.

## FR-011 — Source lifecycle governs downstream creation

- Original issue: paused, failed, or decommissioned sources could create downstream data.
- Disposition: **remediated**.
- Implementation: `app/models/source_system.py::DOWNSTREAM_CREATION_SOURCE_STATUSES`;
  `app/services/ingestion_service.py::source_for_downstream_creation`; batch, dataset, and
  dataset-version creation; `app/services/raw_lineage_service.py::RawStorageObjectService.register`.
- Policy: only `active` permits new downstream creation. All statuses remain readable.
- Tests:
  `tests/test_ingestion_service.py::test_source_lifecycle_blocks_new_downstream_but_preserves_history`,
  `test_source_lifecycle_check_remains_tenant_first`;
  `tests/test_raw_lineage_service.py::test_raw_object_idempotency_tenant_context_and_automatic_lineage`;
  PostgreSQL ingestion/raw tests in `tests/test_postgres_migrations.py`.
- Tenant/idempotency evidence: tenant ownership is resolved before status details; an identical
  historical raw-registration retry remains replayable after a source pauses.
- Review: test active, paused, failed, decommissioned, and cross-tenant sources.

## FR-012 — Terminal source updates

- Original issue: a generic update could modify governance identity after decommissioning.
- Disposition: **remediated**.
- Implementation: `app/services/source_system_service.py::SourceSystemService.update` and
  `decommissioned_editable_fields`.
- Tests:
  `tests/test_source_system_service.py::test_lifecycle_connection_health_and_terminal_state`.
- Policy: only `description`, `owner_name`, and `owner_email` remain editable.
- Review: verify name, code, integration, credentials, and lifecycle fields are rejected while
  records-administration metadata remains writable.

## FR-013 — Source history/versioning

- Original issue: source configuration has no immutable version history.
- Disposition: **deferred**.
- Implementation/tests/migration: none in Phase 1B.
- Risk: historical configuration reconstruction remains limited.
- Review: confirm no `SourceSystemVersion` or equivalent was added.

## FR-014 — Foundational database state constraints

- Original issue: foundational string-backed states lacked database enforcement.
- Disposition: **remediated**.
- Implementation: ORM checks in `app/models/entities.py` and `app/models/raw_lineage.py`;
  migration `migrations/versions/20260728_0023_foundation_hardening.py`.
- Constraints: `ck_organizations_status`, `ck_findings_severity`, `ck_findings_status`,
  `ck_recovery_actions_status`, and `ck_processing_runs_data_anchor`.
- Tests: `tests/test_foundation_constraints.py`; schema and lifecycle inspection in
  `tests/test_postgres_migrations.py::test_migrations_on_disposable_postgres`.
- PostgreSQL evidence: upgrade, downgrade to `0022`, re-upgrade, drift, and offline SQL checks.
- Review: compare ORM expressions and migration expressions exactly.

## FR-015 — Governed stored-data Trust input

- Original issue: Trust consumes bounded inline records rather than immutable governed data.
- Disposition: **architecture proposal only**.
- Proposal: `docs/phase-1-governed-trust-input-proposal.md`.
- Implementation: none; current `TrustAssessmentCreate.records` remains inline/manual.
- Test boundary:
  `tests/test_foundation_integration.py::test_default_foundation_path_preserves_governance_and_inline_trust_boundary`.
- Limitation: raw lineage and Trust input are not represented as connected.
- Review: confirm no governed-input snapshot tables or references were added.

## FR-016 — Persistent canonical schema and mapping

- Original issue: exact canonical/source schema and mapping versions are not persisted.
- Disposition: **architecture proposal only**.
- Proposal: `docs/phase-1-governed-trust-input-proposal.md`.
- Implementation/tests/migration: none in Phase 1B.
- Limitation: assessments cannot bind to immutable canonical or mapping versions.
- Review: treat the proposal as unapproved future work.

## FR-017 — Trust correction, dispute, and override

- Original issue: no governed assessment dispute/override workflow.
- Disposition: **deferred**.
- Implementation/tests/migration: none in Phase 1B.
- Risk: corrections require external operational governance.
- Review: confirm no override state or route was introduced.

## FR-023 — Negative constraint enforcement

- Original issue: positive schema inspection did not prove invalid database writes fail.
- Disposition: **remediated**.
- Tests:
  `tests/test_foundation_constraints.py::test_foundation_state_checks_reject_invalid_values`,
  `test_processing_run_data_anchor_is_database_enforced`, plus PostgreSQL migration inspection.
- Database evidence: tests issue SQLAlchemy writes after validation layers and expect
  `IntegrityError`.
- Review: confirm tests do not rely on Pydantic rejection.

## FR-024 — Default foundation path integration

- Original issue: no single test covered the complete foundation path.
- Disposition: **remediated**.
- Test:
  `tests/test_foundation_integration.py::test_default_foundation_path_preserves_governance_and_inline_trust_boundary`.
- Path: organization → active membership → active source → batch → dataset → version → raw
  storage → lineage → Trust assessment → readiness.
- Limitation: Trust data is explicitly inline/manual; FR-015 is not claimed.
- Review: verify the comment and assertions do not imply the raw object supplied Trust records.

## FR-036 — TrustAssessment idempotency

- Original issue: retried assessment creation duplicated assessments, results, evidence, and
  readiness decisions.
- Disposition: **remediated**.
- Implementation: `app/schemas/trust.py::TrustAssessmentCreate.idempotency_key`;
  `app/models/trust.py::TrustAssessment`; and
  `app/services/trust_service.py::TrustAssessmentService._request_fingerprint`,
  `_idempotent_assessment`, `create_and_execute`; HTTP 409 translation in
  `app/api/trust_routes.py`.
- Migration evidence: nullable `idempotency_key`, nullable `request_fingerprint`,
  `uq_trust_assessments_organization_idempotency`, and
  `ck_trust_assessment_idempotency_pair`.
- Tests:
  `tests/test_trust_service.py::test_assessment_idempotency_replays_without_duplicate_children`,
  `test_assessment_idempotency_is_organization_scoped`;
  `tests/test_trust_api.py::test_trust_api_idempotency_replay_and_conflict`;
  `tests/test_postgres_migrations.py::test_concurrent_trust_idempotency_creates_one_assessment`.
- Compatibility: callers omitting a key retain prior behavior.
- Review: run concurrent identical requests, then reuse the key with a different fingerprint.

## FR-037 — Trust tenant-mismatch error consistency

- Original issue: semantically equivalent tenant mismatches used inconsistent details.
- Disposition: **remediated**.
- Implementation: `app/services/trust_service.py::_dataset` and batch lookup return the generic
  `Resource not found in organization` boundary; routes continue to return 404.
- Tests:
  `tests/test_trust_service.py::test_no_applicable_rules_and_cross_tenant_dataset_are_rejected`,
  `test_cross_tenant_ingestion_batch_is_rejected`,
  `test_assessment_resources_are_strictly_tenant_scoped`;
  `tests/test_trust_api.py::test_trust_api_tenant_isolation_and_role_authorization`.
- Review: compare cross-tenant and nonexistent-resource responses for leakage.

## FR-038 — Shared audit-history architecture

- Original issue: audit histories are domain-specific rather than governed through one shared
  architecture.
- Disposition: **deferred**.
- Implementation/tests/migration: none in Phase 1B.
- Risk: cross-domain audit querying remains heterogeneous.
- Review: do not interpret lineage events as a replacement for shared audit architecture.

## FR-039 — Repository/DAL normalization

- Original issue: persistence access patterns are inconsistent across services.
- Disposition: **deferred**.
- Implementation/tests/migration: no broad repository or DAL refactor.
- Risk: maintainability and transaction conventions remain heterogeneous.
- Review: verify changes stayed local to the bounded services.
