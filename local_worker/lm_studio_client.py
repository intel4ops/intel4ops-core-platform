"""AGENTIC-CONTROL-001 Phase E/F: a thin, dependency-light client for
LM Studio's OpenAI-compatible REST API (http://localhost:1234 by
default). Runs on the owner's laptop, never in the cloud backend.

Empirically confirmed against a live LM Studio instance running
qwen/qwen3.5-9b (2026-09-06): the mission's documented "reasoning = off"
profile is NOT the model's default -- without an explicit
`reasoning_effort: "none"` request field, Qwen3.5 emits its full
`reasoning_content` and burns the entire max_output_tokens budget on it,
leaving `content` empty. Setting `reasoning_effort: "none"` reproduces
the mission's validated R0 numbers exactly (reasoning_tokens=0). This
module hard-codes that field for every request -- it is not optional.

Also empirically confirmed: the model sometimes wraps its JSON reply in
a ```json ... ``` markdown fence despite being told not to -- `extract_json`
strips that before parsing, since a worker must never crash on a cosmetic
formatting choice the model makes.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass


class LmStudioError(RuntimeError):
    pass


@dataclass(frozen=True)
class LmStudioResult:
    content: str
    parsed_json: dict | None
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    ttft_ms: int
    total_ms: int
    tokens_per_second: float
    model_identifier: str


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def extract_json(raw_content: str) -> dict | None:
    cleaned = _FENCE_RE.sub("", raw_content).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


class LmStudioClient:
    def __init__(
        self, base_url: str = "http://localhost:1234", timeout_seconds: float = 120.0
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def list_models(self) -> list[str]:
        req = urllib.request.Request(f"{self._base_url}/v1/models")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout_seconds) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as exc:
            raise LmStudioError(f"LM Studio is not reachable at {self._base_url}: {exc}") from exc
        return [item["id"] for item in body.get("data", [])]

    def health_check(self) -> bool:
        try:
            self.list_models()
            return True
        except LmStudioError:
            return False

    def chat_completion(
        self,
        model: str,
        prompt: str,
        max_output_tokens: int,
        temperature: float = 0,
        reasoning: bool = False,
    ) -> LmStudioResult:
        """Streams the completion so TTFT is measured against the first
        real content chunk (Phase E requirement: capture TTFT,
        tokens/sec, input/output/reasoning tokens, total elapsed time)."""
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_output_tokens,
            "temperature": temperature,
            "reasoning_effort": "none" if not reasoning else "medium",
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self._base_url}/v1/chat/completions",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        started = time.monotonic()
        first_token_at: float | None = None
        content_parts: list[str] = []
        usage: dict = {}

        try:
            with urllib.request.urlopen(req, timeout=self._timeout_seconds) as resp:
                for line in resp:
                    decoded = line.decode("utf-8").strip()
                    if not decoded or not decoded.startswith("data:"):
                        continue
                    data = decoded.removeprefix("data:").strip()
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    if chunk.get("usage"):
                        usage = chunk["usage"]
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {})
                    piece = delta.get("content") or ""
                    if piece:
                        if first_token_at is None:
                            first_token_at = time.monotonic()
                        content_parts.append(piece)
        except (urllib.error.URLError, TimeoutError) as exc:
            raise LmStudioError(f"LM Studio request failed: {exc}") from exc

        total_elapsed = time.monotonic() - started
        content = "".join(content_parts)
        ttft = (first_token_at - started) if first_token_at is not None else total_elapsed
        output_tokens = int(usage.get("completion_tokens", 0))
        reasoning_tokens = int(
            usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0)
        )
        generation_elapsed = max(total_elapsed - ttft, 0.001)
        tokens_per_second = output_tokens / generation_elapsed if output_tokens else 0.0

        return LmStudioResult(
            content=content,
            parsed_json=extract_json(content),
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            ttft_ms=int(ttft * 1000),
            total_ms=int(total_elapsed * 1000),
            tokens_per_second=round(tokens_per_second, 2),
            model_identifier=model,
        )
