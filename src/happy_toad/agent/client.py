"""Provider adapter: messages and tools in, one completion out (SPEC, M3 decision 1)."""

import os
from dataclasses import dataclass, field
from typing import Protocol

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
    model: str = ""


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


class OpenRouterClient:
    """The openai SDK pointed at OpenRouter. The key comes from the environment only."""

    def __init__(self, profile: Profile, sdk=None) -> None:
        self.profile = profile
        if sdk is None:
            key = os.environ.get(KEY_ENV)
            if not key:
                raise RuntimeError(f"{KEY_ENV} is not set")
            from openai import OpenAI

            sdk = OpenAI(base_url=BASE_URL, api_key=key)
        self.sdk = sdk

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
        response = self.sdk.chat.completions.create(
            model=self.profile.model, messages=messages, tools=tools, extra_body=extra
        )
        return parse_completion(response)
