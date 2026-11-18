"""The transcript of one conversation, saved as JSON for review and for M4 (SPEC, M3 decision 8)."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from happy_toad.agent.checker import CheckResult
from happy_toad.agent.redaction import ACCOUNT_ID
from happy_toad.agent.report import Report


def redact(text: str) -> str:
    """Text safe to print or export: OpenRouter account ids replaced."""
    return ACCOUNT_ID.sub("[redacted]", text)


class TurnRecord(BaseModel):
    """One model response with the tools it called and what they returned."""

    index: int
    content: str | None
    tool_calls: list[dict]
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int = 0  # part of completion_tokens, when the provider reports it
    cost: float | None
    provider: str | None
    quantization: str | None = None
    model: str
    seconds: float
    history_sanitized: bool = False  # unparseable tool arguments were replaced in the history


class Transcript(BaseModel):
    transcript_id: str
    question: str
    profile: str
    model: str
    turns: list[TurnRecord] = []
    checks: list[CheckResult] = []
    report: Report | None = None
    status: str = "error"  # checked, unverified, step_cap, api_error, error or interrupted
    error: str | None = None
    api_error: dict | None = None  # {status, body, step} when the provider refused a request
    coercions: list[dict] = []  # claim values the schema turned from strings into numbers
    defaults: list[dict] = []  # claim units and entities the schema set or replaced
    total_tokens: dict[str, int] = {"prompt": 0, "completion": 0, "reasoning": 0}
    cost: float | None = None
    elapsed_seconds: float = 0.0
    source: Literal["cli", "web", "eval", "bakeoff", "mcp", "eval-mcp"] | None = (
        None  # None: pre-M4
    )
    provenance: dict | None = None  # git_sha, git_dirty, prompt_sha256 (agent/provenance.py)
    report_accepted: bool | None = None  # None: saved before M4

    @property
    def providers(self) -> list[str]:
        """The providers that served the turns, sorted, "unknown" when a turn did not say."""
        return sorted({x.provider or "unknown" for x in self.turns})

    def save(self, folder: Path) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{self.transcript_id}.json"
        path.write_text(self.model_dump_json(indent=2))
        return path
