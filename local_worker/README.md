# Local Worker Bridge

Runs the Intel4Ops Agent Job Queue's local worker on this machine
against LM Studio (`http://localhost:1234`). See
`docs/local-worker-bridge.md` in the main repo for the full
architecture, verified LM Studio behavior, and the end-to-end demo.

## Quick start

```
set AGENT_API_BASE_URL=https://intel4ops-core-api.onrender.com/api/v1
set AGENT_ORGANIZATION_ID=<your organization UUID>
set AGENT_WORKER_TOKEN=<issued via POST /agent-jobs/worker-credentials>
python agent_worker.py
```

No third-party packages required -- `agent_worker.py` and
`lm_studio_client.py` use only the Python standard library
(`urllib`, `json`, `threading`), so no `pip install` step or virtualenv
is needed on the laptop this runs on.

Requires LM Studio running locally with `qwen/qwen3.5-9b` (and, for
R1-escalated Devstral review, `mistralai/devstral-small-2-2512`) loaded.
