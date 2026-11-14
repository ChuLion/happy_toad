"""Parsing OpenRouter responses and building requests; no network (SPEC, M3 provider)."""

from types import SimpleNamespace

import pytest

from happy_toad.agent.client import OpenRouterClient, parse_completion
from happy_toad.agent.config import BAKEOFF, DEMO, SMOKE


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
        "require_parameters": True,
    }
    assert seen["extra_body"]["reasoning"] == {"enabled": False}
    assert seen["extra_body"]["usage"] == {"include": True}
    seen.clear()
    OpenRouterClient(SMOKE, sdk=Fake).complete([], [])
    assert seen["extra_body"]["provider"] == {"allow_fallbacks": True, "require_parameters": True}


def test_missing_key_is_a_clear_error_that_never_prints_a_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        OpenRouterClient(SMOKE)


def test_bakeoff_profiles_pin_exact_ids_and_switch_reasoning_off() -> None:
    assert [p.model for p in BAKEOFF.values()] == [
        "google/gemini-2.5-flash-lite",
        "google/gemma-4-31b-it",
        "deepseek/deepseek-v4-flash-0731",
        "deepseek/deepseek-v4-pro",
    ]
    assert all(p.reasoning_off for p in BAKEOFF.values())
    seen = {}

    class Fake:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    seen.update(kwargs)
                    return response()

    OpenRouterClient(BAKEOFF["gemma_31b"], sdk=Fake).complete([], [])
    assert seen["extra_body"]["reasoning"] == {"enabled": False}


def test_a_response_without_usage_counts_zero_tokens_and_no_cost() -> None:
    """Found in the bake-off: one Gemini response had usage=None and crashed the parser."""
    resp = response(provider="Google AI Studio")
    resp.usage = None
    done = parse_completion(resp)
    assert (done.prompt_tokens, done.completion_tokens, done.cost) == (0, 0, None)


def test_gemma_is_pinned_to_the_two_bf16_hosts_with_no_fallbacks() -> None:
    gemma = BAKEOFF["gemma_31b"]
    assert gemma.provider_order == ("crusoe/bf16", "novita/bf16") and not gemma.allow_fallbacks
    assert all(not p.provider_order for n, p in BAKEOFF.items() if n != "gemma_31b")


def test_quantizations_are_read_from_the_endpoint_listing() -> None:
    from happy_toad.agent.client import quantization_by_provider

    listing = {"data": {"endpoints": [
        {"provider_name": "Crusoe", "quantization": "bf16"},
        {"provider_name": "KT", "quantization": "unknown"},
        {"provider_name": "DeepInfra", "quantization": "fp4"},
        {"provider_name": "DeepInfra", "quantization": "fp8"},
        {"provider_name": "Anon", "quantization": None},
    ]}}  # fmt: skip
    assert quantization_by_provider(listing) == {
        "Crusoe": "bf16", "KT": "unknown", "DeepInfra": "fp4|fp8", "Anon": "unknown",
    }  # fmt: skip


def test_the_serving_providers_quantization_is_on_every_completion() -> None:
    class Fake:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return response(provider=Fake.host)

    client = OpenRouterClient(BAKEOFF["gemma_31b"], sdk=Fake, quantizations={"Crusoe": "bf16"})
    Fake.host = "Crusoe"
    assert client.complete([], []).quantization == "bf16"
    Fake.host = "Elsewhere"
    assert client.complete([], []).quantization == "unknown"


def test_a_provider_status_error_keeps_the_status_and_the_whole_body() -> None:
    import httpx2 as httpx
    import openai

    from happy_toad.agent.client import ProviderError

    body = {
        "error": {"message": "Provider returned error", "metadata": {"provider_name": "Crusoe"}}
    }
    http = httpx.Response(400, json=body, request=httpx.Request("POST", "https://x"))

    class Fake:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    raise openai.BadRequestError(
                        "Provider returned error", response=http, body=body
                    )

    with pytest.raises(ProviderError) as caught:
        OpenRouterClient(SMOKE, sdk=Fake).complete([], [])
    assert caught.value.status == 400
    assert "Crusoe" in caught.value.body and "Provider returned error" in caught.value.body


def test_reasoning_tokens_are_read_from_usage_details() -> None:
    done = parse_completion(
        response(usage={"completion_tokens_details": SimpleNamespace(reasoning_tokens=33)})
    )
    assert done.reasoning_tokens == 33
    assert parse_completion(response()).reasoning_tokens == 0


def test_round_profiles_pin_hosts_and_set_reasoning() -> None:
    from happy_toad.agent.config import ROUND

    assert list(ROUND) == [
        "gemma_31b",
        "gemini_flash_lite",
        "deepseek_flash_0731",
        "glm_flash",
        "sonnet_reference",
    ]
    deepseek, glm, sonnet = (
        ROUND["deepseek_flash_0731"],
        ROUND["glm_flash"],
        ROUND["sonnet_reference"],
    )
    assert deepseek.provider_order == ("baseten/fp8", "baidu/fp8") and deepseek.reasoning_off
    assert glm.model == "z-ai/glm-5.3-flash" and glm.provider_order == ("z-ai/fp8", "novita/fp8")
    assert glm.reasoning_effort == "low" and not glm.reasoning_off
    assert sonnet.model == "anthropic/claude-sonnet-5.5" and sonnet.provider_order == ("anthropic",)
    assert sonnet.reasoning_effort == "low"
    assert not any(p.allow_fallbacks for n, p in ROUND.items() if p.provider_order)
    assert ROUND["gemini_flash_lite"].provider_order == ()


def test_an_effort_profile_sends_the_effort_not_enabled_false() -> None:
    from happy_toad.agent.config import ROUND

    seen = {}

    class Fake:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    seen.update(kwargs)
                    return response()

    OpenRouterClient(ROUND["glm_flash"], sdk=Fake).complete([], [])
    assert seen["extra_body"]["reasoning"] == {"effort": "low"}
    assert seen["extra_body"]["provider"]["order"] == ["z-ai/fp8", "novita/fp8"]


def test_the_demo_profile_is_the_approved_deepseek_pin() -> None:
    from dataclasses import replace

    from happy_toad.agent.config import ROUND

    assert DEMO == replace(ROUND["deepseek_flash_0731"], name="demo")
    assert DEMO.model == "deepseek/deepseek-v4-flash-0731"
    assert DEMO.provider_order == ("baseten/fp8", "baidu/fp8") and not DEMO.allow_fallbacks
    assert DEMO.reasoning_off and DEMO.reasoning_effort is None
