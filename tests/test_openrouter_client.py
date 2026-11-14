"""Parsing OpenRouter responses and building requests; no network (SPEC, M3 provider)."""

from types import SimpleNamespace

import pytest

from happy_toad.agent.client import OpenRouterClient, parse_completion
from happy_toad.agent.config import DEMO, SMOKE


def response(**extra):
    message = SimpleNamespace(
        content=None,
        tool_calls=[
            SimpleNamespace(
                id="c1", function=SimpleNamespace(name="get_run", arguments='{"run_id": "x"}')
            )
        ],
    )
    usage = SimpleNamespace(prompt_tokens=100, completion_tokens=20, **extra.pop("usage", {}))
    return SimpleNamespace(
        model="anthropic/claude-sonnet-5.5",
        choices=[SimpleNamespace(message=message)],
        usage=usage,
        **extra,
    )


def test_parse_reads_tool_calls_tokens_cost_and_provider() -> None:
    done = parse_completion(response(provider="Anthropic", usage={"cost": 0.0123}))
    assert (
        done.tool_calls[0].name == "get_run" and done.tool_calls[0].arguments == '{"run_id": "x"}'
    )
    assert (done.prompt_tokens, done.completion_tokens) == (100, 20)
    assert done.cost == pytest.approx(0.0123) and done.provider == "Anthropic"
    assert done.model == "anthropic/claude-sonnet-5.5"


def test_missing_cost_and_provider_are_none_not_invented() -> None:
    done = parse_completion(response())
    assert done.cost is None and done.provider is None


def test_request_pins_the_model_and_routing_and_asks_for_usage() -> None:
    seen = {}

    class Fake:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    seen.update(kwargs)
                    return response(provider="Anthropic")

    client = OpenRouterClient(DEMO, sdk=Fake)
    client.complete([{"role": "user", "content": "hi"}], [])
    assert seen["model"] == DEMO.model
    assert seen["extra_body"]["provider"] == {
        "order": list(DEMO.provider_order),
        "allow_fallbacks": False,
    }
    assert seen["extra_body"]["usage"] == {"include": True}
    seen.clear()
    OpenRouterClient(SMOKE, sdk=Fake).complete([], [])
    assert seen["extra_body"]["provider"] == {"allow_fallbacks": True}


def test_missing_key_is_a_clear_error_that_never_prints_a_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        OpenRouterClient(SMOKE)
