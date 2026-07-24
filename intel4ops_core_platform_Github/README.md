# Intel4Ops Core Platform — Phase 2 Starter

Executable Python foundation for:

- **Connect**: CSV/XLSX intake
- **Trust**: deterministic data profiling
- **Intelligence**: rule execution and governed findings
- **Command**: shared findings API
- **Recovery**: action assignment and value tracking

## First vertical slice

Maintenance event → repeated failure → downtime → value exposure → finding → recovery action.

## Run locally

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -e ".[dev]"
python scripts/generate_demo_data.py
uvicorn app.main:app --reload
```

Open:

- API docs: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/api/v1/health`

## Test

```bash
pytest
```

## Key endpoints

- `POST /api/v1/trust/profile`
- `POST /api/v1/intelligence/maintenance/analyze`
- `GET /api/v1/command/findings`
- `POST /api/v1/recovery/actions`

## Required maintenance file columns

```text
asset_id,failure_code,downtime_hours,repair_cost
```

## Next engineering increments

1. Replace SQLite with the isolated Mobility Next Supabase Postgres database.
2. Add ingestion batches, source systems, mapping templates, and lineage.
3. Add confidence components and evidence quality scoring.
4. Add causal-chain persistence and exposure calculators.
5. Connect the Lovable Mobility Next frontend to these APIs.
6. Add tenant-scoped authentication and RLS-compatible organization IDs.
7. Expand from maintenance to fleet availability and revenue impact.
