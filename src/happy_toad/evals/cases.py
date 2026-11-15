"""The evaluation cases (docs/SPEC.md, M4 part B), loaded from cases.json."""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

CASES = Path(__file__).with_name("cases.json")
Label = Literal["CHECKED", "NOT CHECKED", "NO NUMBERS TO CHECK"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RunSpec(Strict):
    """One scenario or target-budget search; force_in may be {"selected_at": run index}."""

    kind: Literal["scenario", "target_budget"] = "scenario"
    input_version: str
    budget: float | None = None
    force_in: list[str] | dict[str, int] = []
    force_out: list[str] = []
    market_floor_mult: float | None = None
    target_pct_resolved: float | None = None


class CallSpec(Strict):
    """A required tool call; `run` points at the run spec its arguments must match."""

    tool: str
    run: int | None = None


class KeyNumber(Strict):
    """A metric the report must claim: of one run, of a pair (diff_ metrics), or a follow-up."""

    metric: str
    run: int | None = None
    runs: tuple[int, int] | None = None
    follow_up: bool = False

    def run_indexes(self) -> list[int]:
        return list(self.runs) if self.runs else [self.run]


class Case(Strict):
    id: int
    question: str
    runs: list[RunSpec] = []
    required_calls: list[CallSpec] = []
    forbidden_calls: list[str] = []
    allowed_labels: list[Label]
    key_numbers: list[KeyNumber] = []
    required_phrases: list[str] = []
    review_phrases: list[str] = []
    extra_pairs: list[tuple[int, int]] = []  # truth-only diffs (b minus a), e.g. forced vs unforced


def load_cases(path: Path = CASES) -> list[Case]:
    """All cases, in id order."""
    return [Case.model_validate(c) for c in json.loads(path.read_text())["cases"]]
