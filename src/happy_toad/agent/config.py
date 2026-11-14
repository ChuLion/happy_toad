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
    reasoning_off: bool = False
    reasoning_effort: str | None = None  # for models whose reasoning cannot be switched off


SMOKE = Profile("smoke", "inclusionai/ling-3.2-flash:free")
DEMO = Profile("demo", "anthropic/claude-sonnet-5.5", ("anthropic",), allow_fallbacks=False)
PROFILES = {p.name: p for p in (SMOKE, DEMO)}

# Bake-off candidates (docs/SPEC.md, M3 model selection). Exact IDs from OpenRouter's endpoint.
# Reasoning is off. Only Gemma is pinned, to the two bf16 hosts; for the others OpenRouter picks
# the host and the transcript records it.
BAKEOFF = {
    p.name: p
    for p in (
        Profile("gemini_flash_lite", "google/gemini-2.5-flash-lite", reasoning_off=True),
        Profile(
            "gemma_31b",
            "google/gemma-4-31b-it",
            ("crusoe/bf16", "novita/bf16"),
            allow_fallbacks=False,
            reasoning_off=True,
        ),
        Profile("deepseek_flash_0731", "deepseek/deepseek-v4-flash-0731", reasoning_off=True),
        Profile("deepseek_pro_0423", "deepseek/deepseek-v4-pro", reasoning_off=True),  # fallback
    )
}
PROFILES |= BAKEOFF

# The round after the checker fixes (docs/DEVLOG.md). Hosts are pinned with a same-precision backup
# and no fallbacks outside the list; Gemini stays unpinned (one host serves it). GLM and Sonnet
# cannot switch reasoning off, so they run at the lowest effort: not equal terms.
ROUND = {
    p.name: p
    for p in (
        BAKEOFF["gemma_31b"],
        BAKEOFF["gemini_flash_lite"],
        Profile(
            "deepseek_flash_0731",
            "deepseek/deepseek-v4-flash-0731",
            ("baseten/fp8", "baidu/fp8"),
            allow_fallbacks=False,
            reasoning_off=True,
        ),
        Profile(
            "glm_flash",
            "z-ai/glm-5.3-flash",
            ("z-ai/fp8", "novita/fp8"),
            allow_fallbacks=False,
            reasoning_effort="low",
        ),
        Profile(
            "sonnet_reference",
            "anthropic/claude-sonnet-5.5",
            ("anthropic",),
            allow_fallbacks=False,
            reasoning_effort="low",
        ),
    )
}
PROFILES |= ROUND
