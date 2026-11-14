"""Profiles, pinned model IDs and loop limits (SPEC, M3 provider)."""

from dataclasses import dataclass

BASE_URL = "https://openrouter.ai/api/v1"
KEY_ENV = "OPENROUTER_API_KEY"
MAX_STEPS = 10


@dataclass(frozen=True)
class Profile:
    """A model and how OpenRouter may route it. Empty provider_order means no pin."""

    name: str
    model: str
    provider_order: tuple[str, ...] = ()
    allow_fallbacks: bool = True


SMOKE = Profile("smoke", "google/gemma-4-31b-it:free")
DEMO = Profile("demo", "anthropic/claude-sonnet-5.5", ("anthropic",), allow_fallbacks=False)
PROFILES = {p.name: p for p in (SMOKE, DEMO)}
