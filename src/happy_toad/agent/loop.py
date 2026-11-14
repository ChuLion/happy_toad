"""The agent loop: model turns and tool calls until a report is accepted (SPEC, M3 decision 3)."""

import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from happy_toad.agent.checker import check_report
from happy_toad.agent.client import ChatClient, Completion, ToolCall
from happy_toad.agent.config import MAX_STEPS, Profile
from happy_toad.agent.prompt import SYSTEM_PROMPT
from happy_toad.agent.report import Report
from happy_toad.agent.tools import TOOLS, ToolRunner
from happy_toad.agent.transcript import Transcript, TurnRecord
from happy_toad.services.run import new_run_id

NUDGE = "Reply by calling submit_report with your answer."


def _assistant_message(done: Completion) -> dict:
    message: dict = {"role": "assistant", "content": done.content}
    if done.tool_calls:
        message["tool_calls"] = [
            {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
            for c in done.tool_calls
        ]
    return message


def _sum_cost(turns: list[TurnRecord]) -> float | None:
    costs = [t.cost for t in turns]
    return None if not costs or any(c is None for c in costs) else sum(costs)


class Conversation:
    """State of one question: messages, transcript, tool runner and the checker flow."""

    def __init__(self, question, profile, runner, runs_dir, inputs_dir, on_event) -> None:
        self.runner, self.runs_dir, self.on_event = runner, runs_dir, on_event
        self.inputs_dir = inputs_dir
        self.transcript = Transcript(
            transcript_id=new_run_id(datetime.now(UTC)),
            question=question,
            profile=profile.name,
            model=profile.model,
        )
        self.messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]

    def submit(self, call: ToolCall) -> dict:
        """Handle submit_report: schema, then the checker, with one chance to correct."""
        try:
            report = Report.model_validate_json(call.arguments)
        except ValidationError as err:
            return {"accepted": False, "error": f"report does not fit the schema: {err}"}
        t = self.transcript
        result = check_report(report, self.runs_dir, self.inputs_dir)
        t.checks.append(result)
        t.report = report
        if result.ok:
            t.status = "checked"
            return {"accepted": True}
        if len(t.checks) == 1:
            errors = result.errors()
            return {"accepted": False, "errors": errors, "instruction": "fix and resubmit once"}
        t.status = "unverified"
        return {"accepted": False, "errors": result.errors()}

    def run_call(self, call: ToolCall) -> dict:
        if call.name == "submit_report":
            return self.submit(call)
        return self.runner.call(call.name, call.arguments)

    def take_turn(self, done: Completion, seconds: float) -> None:
        t = self.transcript
        calls = []
        self.messages.append(_assistant_message(done))
        for call in done.tool_calls:
            result = self.run_call(call)
            calls.append({"name": call.name, "arguments": call.arguments, "result": result})
            self.on_event("tool_call", calls[-1])
            content = json.dumps(result, default=str)
            self.messages.append({"role": "tool", "tool_call_id": call.id, "content": content})
        if not done.tool_calls:
            self.messages.append({"role": "user", "content": NUDGE})
        t.turns.append(
            TurnRecord(
                index=len(t.turns) + 1,
                content=done.content,
                tool_calls=calls,
                prompt_tokens=done.prompt_tokens,
                completion_tokens=done.completion_tokens,
                cost=done.cost,
                provider=done.provider,
                model=done.model,
                seconds=seconds,
            )
        )

    @property
    def finished(self) -> bool:
        return self.transcript.status in ("checked", "unverified")


def ask(
    question: str,
    client: ChatClient,
    profile: Profile,
    *,
    inputs_dir: Path = Path("data/inputs"),
    runs_dir: Path = Path("runs"),
    transcripts_dir: Path = Path("transcripts"),
    on_event: Callable[[str, dict], None] = lambda kind, payload: None,
) -> Transcript:
    """Answer one question. Every outcome, including failures, leaves a saved transcript."""
    started = time.perf_counter()
    convo = Conversation(
        question, profile, ToolRunner(inputs_dir, runs_dir), runs_dir, inputs_dir, on_event
    )
    t = convo.transcript
    t.status = "step_cap"
    try:
        for _ in range(MAX_STEPS):
            turn_start = time.perf_counter()
            done = client.complete(convo.messages, TOOLS)
            convo.take_turn(done, time.perf_counter() - turn_start)
            if convo.finished:
                break
    except Exception as err:  # the transcript must exist whatever the provider did
        t.status, t.error = "error", f"{type(err).__name__}: {err}"
    t.total_tokens = {
        "prompt": sum(x.prompt_tokens for x in t.turns),
        "completion": sum(x.completion_tokens for x in t.turns),
    }
    t.cost = _sum_cost(t.turns)
    t.elapsed_seconds = time.perf_counter() - started
    t.save(transcripts_dir)
    return t
