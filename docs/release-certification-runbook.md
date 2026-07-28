# Release Certification Runbook

Run Ruff formatting and lint, Mypy, the full SQLite suite, disposable PostgreSQL
migration tests, Alembic drift detection, and offline SQL generation. From a clean
tree, run:

```bash
mapfile -t heads < <(python -m alembic heads | awk '{print $1}')
test "${#heads[@]}" -eq 1

python -m app.cli.certify --commit <SHA> --branch <BRANCH> \
  --migration-head "${heads[0]}" --output build/certification
```

Review the JSON and Markdown reports, their exact commit, gate results, waivers, and
integrity hash. A non-zero exit code blocks release.
