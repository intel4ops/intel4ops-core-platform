# AGENTIC-CONTROL-001 Phase D: one-command local worker launch.
#
# Usage (from this directory):
#   .\start.ps1
#
# Reads local_worker\.env.production automatically (agent_worker.py's
# built-in loader) -- no environment variables need to be set by hand.
# Requires LM Studio running locally at http://localhost:1234 with
# qwen/qwen3.5-9b loaded (and mistralai/devstral-small-2-2512 loaded too
# if you want R1-escalation review to succeed locally rather than
# escalate further to Claude).

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".env.production")) {
    Write-Error "local_worker\.env.production not found. Issue a worker credential first (see docs\local-worker-bridge.md) and create this file with AGENT_API_BASE_URL, AGENT_ORGANIZATION_ID, and AGENT_WORKER_TOKEN."
    exit 1
}

Write-Host "Starting Intel4Ops local agent worker (Ctrl+C to stop)..."
python agent_worker.py
