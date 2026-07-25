# Security and tenancy

Every persisted operational forecast entity is reached through an organization-scoped
execution or carries `organization_id`. Existing membership roles control reading, execution,
scenario creation, revision, actual registration, accuracy, approval, and administration.
System method definitions are read-only to organization users. There is no arbitrary code,
SQL, dynamic import, model download, secret, or cross-tenant reconciliation path.
