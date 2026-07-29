# Phase 1B Independent Test Execution Guide

Use only a newly created disposable PostgreSQL database. Never use production, Mobility,
customer, shared, or long-lived development databases.

## Clean environment

PowerShell example:

```powershell
git clone <REPOSITORY_URL> intel4ops-core-platform
Set-Location intel4ops-core-platform
git checkout <PHASE_1B_HANDOFF_COMMIT>
git merge-base --is-ancestor 3235f4391c0573f9c1efbdd79bac67fe0c9940af HEAD

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Use Python 3.12 for parity with certification. Do not create or commit `.env`.

## Static and default gates

```powershell
python -m ruff format --check .
python -m ruff check .
python -m mypy app tests
python -m pytest -p no:cacheprovider
git diff --check 3db1445abfb03afaff50a76d2967504e6c2dc6c0...HEAD
```

## Disposable PostgreSQL setup

Docker example; replace placeholders and keep the password outside source control:

```powershell
docker run --name intel4ops-phase1b-postgres `
  -e POSTGRES_USER=<DISPOSABLE_USER> `
  -e POSTGRES_PASSWORD=<DISPOSABLE_PASSWORD> `
  -e POSTGRES_DB=intel4ops_phase1b_validation `
  -p <DISPOSABLE_PORT>:5432 `
  -d postgres:17

$env:TEST_POSTGRES_URL = "postgresql+psycopg://<DISPOSABLE_USER>:<DISPOSABLE_PASSWORD>@localhost:<DISPOSABLE_PORT>/intel4ops_phase1b_validation"
$env:CONFIRM_DISPOSABLE_POSTGRES = "1"
```

Confirm that the database name contains `test`, `testing`, `disposable`, or `validation`.
The tests reject a URL equal to `DATABASE_URL` and reject a missing confirmation flag.

## PostgreSQL and migration gates

```powershell
python -m pytest -m postgres -p no:cacheprovider

$env:DATABASE_URL = $env:TEST_POSTGRES_URL
python -m alembic upgrade head
python -m alembic current
python -m alembic downgrade 20260728_0022
python -m alembic upgrade 20260728_0023
python -m alembic check
python -m alembic upgrade head --sql | Out-Null
```

The complete lifecycle regression, including upgrade from base and downgrade verification, is:

```powershell
python -m pytest tests/test_postgres_migrations.py::test_migrations_on_disposable_postgres -vv -p no:cacheprovider
```

Concurrency tests can be isolated with:

```powershell
python -m pytest tests/test_postgres_migrations.py::test_concurrent_admin_changes_cannot_remove_all_active_admins -vv -p no:cacheprovider
python -m pytest tests/test_postgres_migrations.py::test_concurrent_trust_idempotency_creates_one_assessment -vv -p no:cacheprovider
```

After validation, destroy the container and its disposable volume:

```powershell
docker rm -f intel4ops-phase1b-postgres
Remove-Item Env:TEST_POSTGRES_URL -ErrorAction SilentlyContinue
Remove-Item Env:CONFIRM_DISPOSABLE_POSTGRES -ErrorAction SilentlyContinue
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
```

## Secret scan

This scan prints only paths and matched variable names, never assigned values:

```powershell
$pattern = '(?i)\b(TEST_POSTGRES_URL|DATABASE_URL|SUPABASE_[A-Z0-9_]*KEY|SUPABASE_SERVICE_ROLE_KEY|SERVICE_ROLE_KEY|JWT_[A-Z0-9_]*SECRET|JWT_SECRET|API_TOKEN|API_KEY|PASSWORD)\b\s*[:=]'
$paths = @(git ls-files) + @(git ls-files --others --exclude-standard)
foreach ($path in ($paths | Sort-Object -Unique)) {
  if (Test-Path -LiteralPath $path -PathType Leaf) {
    foreach ($result in (Select-String -LiteralPath $path -Pattern $pattern -AllMatches -ErrorAction SilentlyContinue)) {
      foreach ($match in $result.Matches) {
        "{0} :: {1}" -f $path, $match.Groups[1].Value.ToUpperInvariant()
      }
    }
  }
}
```

Review expected placeholders in `.env.example`, CI, documentation, configuration, and tests.
Fail certification if a real credential, `.env`, customer data, generated dataset, or large
artifact is present.

## Expected results

- Alembic head: `20260728_0023`
- Ruff format/check and Mypy: pass
- Default tests: pass; PostgreSQL-marked tests skip without the explicit variables
- PostgreSQL suite: pass on the disposable target
- Downgrade and re-upgrade: pass
- Drift: no new upgrade operations
- Offline SQL and whitespace: pass
