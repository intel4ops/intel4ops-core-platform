# Reliability Security

Organization membership remains the authorization boundary. Execution, result, review, health,
risk, and evidence queries include `organization_id`; supplying a UUID alone grants no access.
Shared OIKB definitions contain no tenant records. Cross-tenant peers expose aggregate benchmarks
only. Arbitrary method code, customer thresholds, raw sensor streams, work-order exports, and
credentials are not accepted or persisted.
