# Executive Command

Executive Command is a read-only governed summary layer. It does not recalculate economics
or verified value. Economic calculations supply exposure, addressable exposure, and expected
recoverable value; recovery measurements supply realized value; the verified-value ledger
alone supplies verified value, adjustments, and reversals.

Endpoints under `/api/v1/organizations/{organization_id}/command`:

- `GET /executive-summary`
- `GET /attention`
- `GET /value-portfolio`
- `GET /recovery-portfolio`

Every endpoint requires `command.executive_kpis`. Totals are grouped by ISO currency and
unlike currencies are never summed. Drill-down responses retain authoritative entity IDs.
The reporting period is explicit. Foreign-exchange conversion and persisted dashboard
snapshots are deferred.
