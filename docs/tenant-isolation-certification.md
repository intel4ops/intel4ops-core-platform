# Tenant-Isolation Certification

Every operational validation record has `organization_id`. Tests use two unrelated
tenant UUIDs and prove read, write, execution, evidence, usage, audit, recovery, pack,
and external-identifier separation. Generated record identifiers incorporate the
tenant boundary. A cross-tenant record is a non-waivable certification failure.
