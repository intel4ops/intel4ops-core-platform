"""AGENTIC-CONTROL-001 Phase E: the Local Worker Bridge.

Runs on the owner's Windows laptop. Never accepts an inbound connection
from the internet -- it only ever makes outbound HTTPS calls to the
Intel4Ops backend (poll/claim/heartbeat/submit-result) and to LM Studio
on localhost. This is the pull/claim model the mission specifies:

    Intel4Ops cloud -> Agent Job Queue -> [this process polls] ->
    claims an eligible LOCAL job -> calls LM Studio (localhost:1234) ->
    returns a structured result -> cloud validates/persists ->
    router accepts/escalates.

Usage:
    python agent_worker.py

Configuration is environment-variable only (Phase N: "no secrets in
source"):
    AGENT_API_BASE_URL      e.g. https://intel4ops-core-api.onrender.com/api/v1
                             (or http://127.0.0.1:8000/api/v1 for local dev)
    AGENT_ORGANIZATION_ID   the organization UUID this worker serves
    AGENT_WORKER_TOKEN      the bearer token issued via
                             POST /agent-jobs/worker-credentials (never
                             hard-coded, never logged)
    AGENT_POLL_INTERVAL_SECONDS      default 3
    AGENT_HEARTBEAT_INTERVAL_SECONDS default 8
    LM_STUDIO_BASE_URL      default http://localhost:1234
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from types import FrameType
from uuid import UUID

from lm_studio_client import LmStudioClient, LmStudioError

logger = logging.getLogger("intel4ops.agent_worker")


@dataclass(frozen=True)
class ModelProfile:
    model: str
    reasoning: bool
    max_output_tokens: int
    temperature: float


# Frozen model-profile parameters -- mirrors
# app.services.agent_routing_service.MODEL_PROFILE_PARAMETERS exactly
# (see tests/test_agent_routing_service.py on the backend side for the
# authoritative test coverage of those values). This script has no
# import path back into the backend package, so the constants are
# restated here rather than shared -- a local worker process never
# imports backend application code.
PROFILE_PARAMETERS: dict[str, ModelProfile] = {
    "QWEN_R0": ModelProfile(
        model="qwen/qwen3.5-9b", reasoning=False, max_output_tokens=180, temperature=0
    ),
    "QWEN_R1": ModelProfile(
        model="qwen/qwen3.5-9b", reasoning=False, max_output_tokens=500, temperature=0
    ),
    "DEVSTRAL_SPECIALIST": ModelProfile(
        model="mistralai/devstral-small-2-2512",
        reasoning=True,
        max_output_tokens=2000,
        temperature=0,
    ),
}


class BackendClient:
    def __init__(self, base_url: str, organization_id: str, token: str) -> None:
        self._base = f"{base_url.rstrip('/')}/organizations/{organization_id}/agent-jobs"
        self._token = token

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict | None:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            f"{self._base}{path}",
            data=body,
            method=method,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self._token}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"backend {method} {path} failed: {exc.code} {detail}") from exc

    def claim(self) -> dict | None:
        return self._request("POST", "/claim")

    def heartbeat(self, job_id: str, lease_id: str) -> None:
        self._request("POST", f"/{job_id}/heartbeat", {"lease_id": lease_id})

    def submit_result(self, job_id: str, payload: dict) -> dict:
        result = self._request("POST", f"/{job_id}/result", payload)
        assert result is not None  # the /result endpoint always returns the updated job
        return result

    def submit_failure(self, job_id: str, payload: dict) -> dict:
        result = self._request("POST", f"/{job_id}/failure", payload)
        assert result is not None  # the /failure endpoint always returns the updated job
        return result


class HeartbeatPump:
    """Mirrors app/workers/mapping_execution.py's HeartbeatPump exactly
    -- a background thread pinging the backend while inference runs, so
    a job that is genuinely still executing is never mistaken for dead."""

    def __init__(
        self, backend: BackendClient, job_id: str, lease_id: str, interval_seconds: float
    ) -> None:
        self._backend = backend
        self._job_id = job_id
        self._lease_id = lease_id
        self._interval = interval_seconds
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=self._interval + 1)

    def _run(self) -> None:
        while not self._stop_event.wait(self._interval):
            try:
                self._backend.heartbeat(self._job_id, self._lease_id)
            except Exception:  # noqa: BLE001 -- a missed heartbeat is not fatal, just logged
                logger.warning("heartbeat_failed", exc_info=True)


class AgentWorker:
    def __init__(
        self,
        backend: BackendClient,
        lm_studio: LmStudioClient,
        poll_interval_seconds: float,
        heartbeat_interval_seconds: float,
        stop_event: threading.Event | None = None,
    ) -> None:
        self._backend = backend
        self._lm_studio = lm_studio
        self._poll_interval = poll_interval_seconds
        self._heartbeat_interval = heartbeat_interval_seconds
        self._stop_event = stop_event or threading.Event()

    def process_one(self) -> bool:
        claim_response = self._backend.claim()
        if claim_response is None:
            return False

        job = claim_response["job"]
        job_id = job["id"]
        lease_id = claim_response["lease_id"]
        profile_name = claim_response["model_profile"]
        params = PROFILE_PARAMETERS.get(profile_name)
        if params is None:
            self._backend.submit_failure(
                job_id,
                {
                    "lease_id": lease_id,
                    "error_code": "UNKNOWN_MODEL_PROFILE",
                    "error_detail": f"worker has no local parameters for profile {profile_name!r}",
                    "retryable": False,
                },
            )
            return True

        logger.info("job_claimed", extra={"job_id": job_id, "profile": profile_name})
        heartbeat = HeartbeatPump(self._backend, job_id, lease_id, self._heartbeat_interval)
        heartbeat.start()
        try:
            prompt = self._build_prompt(claim_response["evidence_package"])
            result = self._lm_studio.chat_completion(
                model=params.model,
                prompt=prompt,
                max_output_tokens=params.max_output_tokens,
                temperature=params.temperature,
                reasoning=params.reasoning,
            )
            if result.parsed_json is None:
                self._backend.submit_failure(
                    job_id,
                    {
                        "lease_id": lease_id,
                        "error_code": "UNPARSEABLE_MODEL_OUTPUT",
                        "error_detail": result.content[:2000],
                        "retryable": True,
                    },
                )
                return True
            self._backend.submit_result(
                job_id,
                {
                    "lease_id": lease_id,
                    "structured_result": result.parsed_json,
                    "execution_time_ms": result.total_ms,
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "reasoning_tokens": result.reasoning_tokens,
                    "ttft_ms": result.ttft_ms,
                    "tokens_per_second": result.tokens_per_second,
                    "model_identifier": result.model_identifier,
                },
            )
            logger.info(
                "job_succeeded",
                extra={
                    "job_id": job_id,
                    "ttft_ms": result.ttft_ms,
                    "tokens_per_second": result.tokens_per_second,
                    "output_tokens": result.output_tokens,
                },
            )
        except LmStudioError as exc:
            self._backend.submit_failure(
                job_id,
                {
                    "lease_id": lease_id,
                    "error_code": "LM_STUDIO_UNAVAILABLE",
                    "error_detail": str(exc),
                    "retryable": True,
                },
            )
        finally:
            heartbeat.stop()
        return True

    def _build_prompt(self, evidence_package: dict) -> str:
        # The EvidencePackage IS the prompt payload -- a worker never
        # receives a conversation history (Phase C).
        return (
            "You are a fast routine-classification worker for the Intel4Ops learning program.\n"
            "Given the EVIDENCE PACKAGE below, answer the QUESTION with ONLY a single JSON object "
            "matching this exact shape, no markdown fences, no explanation before or after:\n"
            '{"primary_gap_class": "...", "secondary_gap_classes": [], "confidence": 0-100, '
            '"summary": "...", "evidence_refs": [], "fp_risk": "low|medium|high", '
            '"architecture_impact": false, "policy_dependency": false, '
            '"data_contract_dependency": false, "recommended_action": "...", '
            '"escalate": false, "escalation_reason": null}\n\n'
            f"EVIDENCE PACKAGE:\n{json.dumps(evidence_package, indent=2)}\n\n"
            f"QUESTION: {evidence_package.get('question', '')}"
        )

    def run(self) -> None:
        logger.info("agent_worker_started")
        while not self._stop_event.is_set():
            try:
                processed = self.process_one()
                delay = 0 if processed else self._poll_interval
            except Exception:  # noqa: BLE001 -- one bad poll must not kill the worker process
                logger.exception("worker_poll_error")
                delay = self._poll_interval
            self._stop_event.wait(delay)
        logger.info("agent_worker_stopped")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    base_url = os.environ.get("AGENT_API_BASE_URL")
    organization_id = os.environ.get("AGENT_ORGANIZATION_ID")
    token = os.environ.get("AGENT_WORKER_TOKEN")
    if not base_url or not organization_id or not token:
        logger.error(
            "missing_required_env",
            extra={
                "required": ["AGENT_API_BASE_URL", "AGENT_ORGANIZATION_ID", "AGENT_WORKER_TOKEN"]
            },
        )
        return 2
    UUID(organization_id)  # fail fast on a malformed id rather than on the first HTTP call

    backend = BackendClient(base_url, organization_id, token)
    lm_studio = LmStudioClient(os.environ.get("LM_STUDIO_BASE_URL", "http://localhost:1234"))
    if not lm_studio.health_check():
        logger.error("lm_studio_unreachable", extra={"base_url": lm_studio._base_url})  # noqa: SLF001
        return 3

    stop_event = threading.Event()

    def _shutdown(_signum: int, _frame: FrameType | None) -> None:
        logger.info("shutdown_requested")
        stop_event.set()

    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)

    worker = AgentWorker(
        backend,
        lm_studio,
        poll_interval_seconds=float(os.environ.get("AGENT_POLL_INTERVAL_SECONDS", "3")),
        heartbeat_interval_seconds=float(os.environ.get("AGENT_HEARTBEAT_INTERVAL_SECONDS", "8")),
        stop_event=stop_event,
    )
    worker.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
