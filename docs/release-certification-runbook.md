# Release Certification Runbook

Run Ruff formatting and lint, Mypy, the full SQLite suite, disposable PostgreSQL
migration tests, Alembic drift detection, and offline SQL generation. From a clean
tree, run:

```text
python -m app.cli.certify --commit <SHA> --branch <BRANCH> \
  --migration-head 20260727_0020 --output build/certification
```

Review the JSON and Markdown reports, their exact commit, gate results, waivers, and
integrity hash. A non-zero exit code blocks release.
