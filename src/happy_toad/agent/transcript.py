"""The transcript of one conversation, saved as JSON for review and for M4 (SPEC, M3 decision 8)."""

from pathlib import Path

from pydantic import BaseModel

from happy_toad.agent.checker import CheckResult
from happy_toad.agent.report import Report


class TurnRecord(BaseModel):
    """One model response with the tools it called and what they returned."""

    index: int
    content: str | None
    tool_calls: list[dict]
    prompt_tokens: int
    completion_tokens: int
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
    status: str = "error"  # checked, unverified, step_cap, api_error or error
    error: str | None = None
    api_error: dict | None = None  # {status, body, step} when the provider refused a request
    coercions: list[dict] = []  # claim values the schema turned from strings into numbers
    total_tokens: dict[str, int] = {"prompt": 0, "completion": 0}
    cost: float | None = None
    elapsed_seconds: float = 0.0

    def save(self, folder: Path) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{self.transcript_id}.json"
        path.write_text(self.model_dump_json(indent=2))
        return path
