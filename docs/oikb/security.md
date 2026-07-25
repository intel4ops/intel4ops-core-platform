# OIKB Security and Tenancy

Private definitions and sources carry `owner_organization_id`. All reads join or filter
through that owner, allowing only shared records or the authorized organization.
Resolution requires an explicit organization and excludes another tenant's candidates.
Organization IDs alone never grant access; membership authorization is checked first.

Shared system definitions require platform administration to create or change.
Organization administrators govern private knowledge, while analysts may author and
validate. OIKB reuses the existing identity and membership system.

OIKB stores evidence requirements and opaque references, not raw operational data.
Expression, validation, and context payloads are bounded. There is no `eval`, script
execution, unrestricted SQL, user-supplied function, or dynamic executable code.
Currency conversion and unit conversion fail closed unless a future governed conversion
facility is introduced.

Audit, approval, validation, activation, source provenance, and fingerprints provide
tamper-evident explanatory context. Database credentials and tokens are never stored in
OIKB content.
