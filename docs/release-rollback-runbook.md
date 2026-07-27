# Release Rollback Runbook

On a disposable database, upgrade to head, downgrade to `20260727_0019`, verify all
WP-2.20 objects are removed and WP-2.19 data remains, then re-upgrade and verify stable
seed IDs and counts. In a real controlled deployment, stop traffic, preserve evidence,
follow the approved database backup and deployment rollback procedure, and re-certify
the restored commit. Never rehearse rollback against Mobility production or customer
databases.
