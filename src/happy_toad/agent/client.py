"""Provider adapter: messages and tools in, one completion out (SPEC, M3 decision 1)."""

import json
import os
import re
import urllib.request
from dataclasses import dataclass, field, replace
from typing import Protocol

from openai import APIStatusError

from happy_toad.agent.config import BASE_URL, KEY_ENV, Profile


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # JSON text, exactly as the model wrote it


@dataclass(frozen=True)
class Completion:
    """One model response. cost and provider are None when the response does not say."""

    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: float | None = None
    provider: str | None = None
    quantization: str | None = None
    model: str = ""


ACCOUNT_ID = re.compile(r"user_[A-Za-z0-9]+")


class ProviderError(Exception):
    """The provider answered with an error status; its body is kept, minus the account id."""

    def __init__(self, status: int, body: str) -> None:
        body = ACCOUNT_ID.sub("[redacted]", body)
        super().__init__(f"HTTP {status}: {body}")
        self.status, self.body = status, body


class ChatClient(Protocol):
    def complete(self, messages: list[dict], tools: list[dict]) -> Completion: ...


def _extra(obj, name):
    """A field the SDK did not declare (OpenRouter additions), or None."""
    value = getattr(obj, name, None)
    if value is None and getattr(obj, "model_extra", None):
        value = obj.model_extra.get(name)
    return value


def parse_completion(response) -> Completion:
    """Turn an OpenAI-compatible chat response into a Completion."""
    message = response.choices[0].message
    calls = [
        ToolCall(c.id, c.function.name, c.function.arguments) for c in message.tool_calls or []
    ]
    usage = response.usage
    tokens = (usage.prompt_tokens, usage.completion_tokens) if usage else (0, 0)
    return Completion(
        content=message.content,
        tool_calls=calls,
        prompt_tokens=tokens[0],
        completion_tokens=tokens[1],
        cost=_extra(usage, "cost") if usage else None,
        provider=_extra(response, "provider"),
        model=response.model,
    )


def quantization_by_provider(listing: dict) -> dict[str, str]:
    """Provider name to quantization from an OpenRouter endpoint listing; "a|b" if it varies."""
    found: dict[str, set[str]] = {}
    for e in listing["data"]["endpoints"]:
        found.setdefault(e["provider_name"], set()).add(e.get("quantization") or "unknown")
    return {name: "|".join(sorted(q)) for name, q in found.items()}


def fetch_quantizations(model: str) -> dict[str, str]:
    """The public endpoint listing for a model; empty if it cannot be read (recorded as unknown)."""
    try:
        with urllib.request.urlopen(f"{BASE_URL}/models/{model}/endpoints") as response:
            return quantization_by_provider(json.load(response))
    except OSError:
        return {}


class OpenRouterClient:
    """The openai SDK pointed at OpenRouter. The key comes from the environment only."""

    def __init__(self, profile: Profile, sdk=None, quantizations: dict | None = None) -> None:
        self.profile = profile
        if sdk is None:
            key = os.environ.get(KEY_ENV)
            if not key:
                raise RuntimeError(f"{KEY_ENV} is not set")
            from openai import OpenAI

            sdk = OpenAI(base_url=BASE_URL, api_key=key)
            quantizations = (
                fetch_quantizations(profile.model) if quantizations is None else quantizations
            )
        self.sdk = sdk
        self.quantizations = quantizations or {}

    def routing(self) -> dict:
        # require_parameters: only route to hosts that support every parameter we send (tools)
        provider: dict = {
            "allow_fallbacks": self.profile.allow_fallbacks,
            "require_parameters": True,
        }
        if self.profile.provider_order:
            provider["order"] = list(self.profile.provider_order)
        return provider

    def complete(self, messages: list[dict], tools: list[dict]) -> Completion:
        extra = {"provider": self.routing(), "usage": {"include": True}}
        if self.profile.reasoning_off:
            extra["reasoning"] = {"enabled": False}
        try:
            response = self.sdk.chat.completions.create(
                model=self.profile.model, messages=messages, tools=tools, extra_body=extra
            )
        except APIStatusError as err:
            raise ProviderError(err.status_code, err.response.text) from err
        done = parse_completion(response)
        known = self.quantizations.get(done.provider, "unknown")
        return replace(done, quantization=known)
