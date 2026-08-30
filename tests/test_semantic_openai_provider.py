"""P3.xxE.2 section 7: OpenAISemanticReasoningProvider contract tests.
Mocks the SDK boundary directly (a fake `client.responses.parse`) --
never a real network call in CI, matching app/ai/openai_adapter.py's own
test precedent."""

from types import SimpleNamespace

import pytest

from app.ai.provider import ProviderResponseError, ProviderUnavailableError
from app.core.config import Settings
from app.semantic.openai_provider import (
    OpenAISemanticReasoningProvider,
    SemanticInterpretationStructuredResponse,
)
from app.semantic.provider import FieldInterpretationContext, SemanticInterpretationRequest


def _settings(*, semantic_ai_enabled: bool = True, ai_api_key: str | None = "test-key") -> Settings:
    return Settings(
        semantic_ai_enabled=semantic_ai_enabled, ai_api_key=ai_api_key, ai_model="gpt-test"
    )


def _request() -> SemanticInterpretationRequest:
    return SemanticInterpretationRequest(
        dataset_label="ds.csv",
        dataset_role_hint="work_order",
        known_concept_codes=["work_order_id", "technician_id"],
        fields=[
            FieldInterpretationContext(
                source_field="svc_ord",
                physical_type="object",
                sample_values=["A1", "A2"],
                value_patterns=["alpha_dash_digits"],
                null_rate=0.0,
                uniqueness_ratio=1.0,
                neighbor_field_names=["technician_ref"],
            )
        ],
    )


class _FakeResponses:
    def __init__(self, parsed: object | None, usage: object | None = None) -> None:
        self._parsed = parsed
        self._usage = usage

    def parse(self, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(output_parsed=self._parsed, usage=self._usage, model="gpt-test")


class _FakeClient:
    def __init__(self, parsed: object | None, usage: object | None = None) -> None:
        self.responses = _FakeResponses(parsed, usage)


def test_provider_disabled_raises_unavailable_without_any_client_call() -> None:
    provider = OpenAISemanticReasoningProvider(_settings(semantic_ai_enabled=False))
    with pytest.raises(ProviderUnavailableError):
        provider.propose(_request())


def test_provider_missing_api_key_raises_unavailable() -> None:
    provider = OpenAISemanticReasoningProvider(_settings(ai_api_key=None))
    with pytest.raises(ProviderUnavailableError):
        provider.propose(_request())


# K/multi-hypothesis: multiple candidate concepts per field are flattened
# into multiple SemanticFieldProposal entries.
def test_multi_hypothesis_response_flattens_into_multiple_proposals() -> None:
    parsed = SemanticInterpretationStructuredResponse(
        fields=[
            {
                "field_name": "svc_ord",
                "candidate_concepts": [
                    {
                        "concept_code": "work_order_id",
                        "provider_confidence": 0.6,
                        "rationale": "looks like a work order",
                    },
                    {
                        "concept_code": "technician_id",
                        "provider_confidence": 0.3,
                        "rationale": "could be a technician reference",
                    },
                ],
            }
        ]
    )
    fake_client = _FakeClient(parsed)
    provider = OpenAISemanticReasoningProvider(_settings(), client=fake_client)
    response = provider.propose(_request())
    assert len(response.proposals) == 2
    assert {p.proposed_concept for p in response.proposals} == {"work_order_id", "technician_id"}
    assert response.provider_name == "openai"
    assert response.provider_version == "gpt-test"


def test_unresolved_field_produces_no_proposals_for_that_field() -> None:
    parsed = SemanticInterpretationStructuredResponse(
        fields=[
            {
                "field_name": "svc_ord",
                "candidate_concepts": [],
                "unresolved_reason": "no plausible concept matched",
            }
        ]
    )
    fake_client = _FakeClient(parsed)
    provider = OpenAISemanticReasoningProvider(_settings(), client=fake_client)
    response = provider.propose(_request())
    assert response.proposals == []


# I. Malformed provider output does not propagate an unhandled exception.
def test_malformed_output_raises_provider_response_error() -> None:
    fake_client = _FakeClient(parsed={"not": "a valid schema"})
    provider = OpenAISemanticReasoningProvider(_settings(), client=fake_client)
    with pytest.raises(ProviderResponseError):
        provider.propose(_request())


def test_client_exception_raises_provider_unavailable_error() -> None:
    class _BoomResponses:
        def parse(self, **kwargs: object) -> None:
            raise RuntimeError("connection reset")

    class _BoomClient:
        responses = _BoomResponses()

    provider = OpenAISemanticReasoningProvider(_settings(), client=_BoomClient())
    with pytest.raises(ProviderUnavailableError):
        provider.propose(_request())


def test_client_is_cached_across_calls() -> None:
    parsed = SemanticInterpretationStructuredResponse(fields=[])
    fake_client = _FakeClient(parsed)
    provider = OpenAISemanticReasoningProvider(_settings(), client=fake_client)
    provider.propose(_request())
    assert provider._client is fake_client
