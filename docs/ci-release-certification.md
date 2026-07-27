# CI Release Certification

GitHub Actions uses Python 3.12 and disposable PostgreSQL 17. It runs formatting,
linting, type checking, SQLite tests, PostgreSQL lifecycle tests, Alembic drift and
offline SQL, then generates certification reports for the checked-out commit. Reports
are uploaded as CI artifacts. Local and CI certification use the same Python modules,
scenario registry, oracle registry, and gate evaluator.
