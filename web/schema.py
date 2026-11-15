"""The view-model schema: the only shape the page and the server see."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

SCHEMA_VERSION = 1


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Step(Strict):
    tool: str
    args: str
    outcome: str


class Claim(Strict):
    metric: str
    value: float | int | str | bool
    run_id: str
    run_id_b: str | None


class Checks(Strict):
    claims: int
    claims_ok: int
    numbers: int
    numbers_matched: int
    mismatches: list[str]


class Correction(Strict):
    happened: bool
    note: str | None


class Run(Strict):
    run_id: str
    input_version: str
    outcome: str
    values: dict[str, float | int | str | bool | None]


class Footer(Strict):
    model: str
    provider: str
    turns: int
    cost: float | None
    seconds: float


class View(Strict):
    schema_version: Literal[1]
    transcript_id: str
    question: str
    steps: list[Step]
    summary: str | None
    status: Literal["CHECKED", "NOT CHECKED"]
    detail: str
    checks: Checks | None
    claims: list[Claim]
    correction: Correction
    runs: list[Run]
    footer: Footer
