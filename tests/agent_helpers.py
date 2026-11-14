"""Shared builders for the M3 tests: a toy input dir, run records and a scripted fake client."""

import json
from dataclasses import dataclass, field

from helpers import make_set

from happy_toad.agent.client import Completion, ToolCall
from happy_toad.constants import BASE_YEAR
from happy_toad.data.loader import save_input_set
from happy_toad.services.request import SolveRequest
from happy_toad.services.run import run_request


def toy_dirs(tmp_path):
    """inputs/ holds version "test": X1 6, X2 5, Y1 6 (see tests/test_force_and_causes.py)."""
    inputs, runs = tmp_path / "inputs", tmp_path / "runs"
    inputs.mkdir()
    data = make_set(
        [("sX1", 10, BASE_YEAR, "X"), ("sX2", 10, BASE_YEAR, "X"), ("sY1", 10, BASE_YEAR + 4, "Y")],
        [("X1", 6), ("X2", 5), ("Y1", 6)],
        [("X1", "sX1", 10), ("X2", "sX2", 10), ("Y1", "sY1", 10)],
    )
    save_input_set(data, inputs / "test.json")
    return inputs, runs


def make_run(tmp_path, **kwargs):
    inputs, runs = (
        toy_dirs(tmp_path)
        if not (tmp_path / "inputs").exists()
        else (
            tmp_path / "inputs",
            tmp_path / "runs",
        )
    )
    request = SolveRequest(**{"input_version": "test", "budget": 12.0, **kwargs})
    return run_request(request, inputs, runs)


def call(name, **arguments) -> ToolCall:
    return ToolCall(id=f"call_{name}", name=name, arguments=json.dumps(arguments))


def turn(
    *calls, content=None, tokens=(10, 5), cost=0.001, provider="FakeProvider", quantization=None
) -> Completion:
    return Completion(
        content=content,
        tool_calls=list(calls),
        prompt_tokens=tokens[0],
        completion_tokens=tokens[1],
        cost=cost,
        provider=provider,
        quantization=quantization,
        model="fake/model",
    )


@dataclass
class FakeClient:
    """Returns the scripted completions in order and records the messages it was sent."""

    script: list[Completion]
    seen: list[list[dict]] = field(default_factory=list)

    def complete(self, messages, tools) -> Completion:
        self.seen.append([dict(m) for m in messages])
        return self.script.pop(0)
