# OIKB Resolution

Resolution is deterministic:

1. organization specialization;
2. regional specialization;
3. industry pack;
4. shared core.

Candidates must be active, effective at the requested time, visible to the requesting
organization, and match the requested specialization metadata. The response includes
definition and version UUIDs, stable code, semantic version, selected scope, complete
precedence path, fallback steps, warnings, effective dates, and fingerprint.

The resolver never infers an organization's industry. Callers provide an industry-pack
code only when a governed assignment is available. The current organization model has
an industry text field but no governed pack-assignment registry; that dependency is
deferred.

WP-2.09 uses dependency inversion. It queries OIKB first for stable governed codes and
then uses the code-backed WP-2.07 registry only when no governed equivalent exists. The
fallback adds `LEGACY_CODE_BACKED_DEFINITION` to resolution metadata. Governed packages
map their approved operation to a bounded WP-2.07 primitive, while persisted executions
retain the governed code, version, and fingerprint.
