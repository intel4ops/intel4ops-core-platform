# Intel4Ops Core Platform Engineering Instructions

## Product

Intel4Ops is an Operations Intelligence platform organized into:

1. Connect
2. Trust
3. Intelligence
4. Command
5. Recovery

The current development phase is Phase 2 – Core Platform.

## Technology

- Python 3.12+
- FastAPI
- SQLAlchemy 2.x
- Alembic
- Pydantic 2
- PostgreSQL through Supabase
- Pytest
- Ruff
- Mypy

## Architecture rules

- Keep business logic out of FastAPI route functions.
- Routes call application services.
- Application services coordinate domain logic.
- Domain rules must be independently testable.
- All persisted operational entities require organization_id.
- Never hard-code tenant or organization identifiers.
- Never store secrets in source code.
- Preserve raw source records and lineage.
- Findings must reference evidence.
- Findings must include confidence and exposure.
- Recovery actions must reference findings.
- Shared Trust rules must remain industry-neutral and register through the Trust rule
  registry.
- Analytical methods must honor persisted readiness decisions; critical Trust defects
  must not be hidden by aggregate scores.
- Trust evidence must be bounded or sampled.
- Use Alembic for every database schema change.
- Do not use Base.metadata.create_all for managed environments.
- Do not modify production infrastructure.
- Do not connect to the existing Mobility production database.

## Multi-tenancy

The organization is the tenant boundary.

Every tenant-specific query must be filtered by organization_id.

Initial tenant entities:

- organizations
- organization_members
- source_systems
- ingestion_batches
- datasets
- mapping_templates
- trust_assessments
- findings
- finding_evidence
- causal_links
- recommendations
- recovery_actions
- recovery_measurements

## Quality requirements

For every work package:

1. Inspect the current implementation.
2. Present a brief implementation plan.
3. Modify the smallest necessary scope.
4. Add or update migrations.
5. Add tests.
6. Run formatting.
7. Run linting.
8. Run type checking.
9. Run the complete test suite.
10. Report changed files and unresolved risks.

Do not claim completion unless tests pass.

## Git workflow

- Never commit directly to main.
- Create a feature branch for each work package.
- Use branch names such as feature/wp-2-01-organizations.
- Keep commits focused.
- Prepare a pull-request summary.
