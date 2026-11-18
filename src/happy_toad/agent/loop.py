"""The agent loop: model turns and tool calls until a report is accepted (SPEC, M3 decision 3)."""

import json
import time
from collections.abc import Callable
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from happy_toad.agent.client import ChatClient, Completion, ProviderError
from happy_toad.agent.config import MAX_STEPS, Profile
from happy_toad.agent.mcp_client import mcp_tools
from happy_toad.agent.prompt import SYSTEM_PROMPT
from happy_toad.agent.provenance import provenance, redact_error
from happy_toad.agent.session import ToolSession
from happy_toad.agent.tools import TOOLS
from happy_toad.agent.transcript import Transcript, TurnRecord
from happy_toad.services.run import new_run_id

NUDGE = "Reply by calling submit_report with your answer."
ONE_SUBMIT = "only one submit_report per turn is checked; this one was not"
RAW_ECHO_LIMIT = 500  # characters of unparseable arguments kept in the history sent back


def _echo_arguments(raw: str) -> tuple[str, bool]:
    """Arguments safe to send back: valid JSON as written, else an object holding the raw text."""
    try:
        json.loads(raw)
    except json.JSONDecodeError:
        return json.dumps({"invalid_arguments_raw": raw[:RAW_ECHO_LIMIT]}), True
    return raw, False


def _assistant_message(done: Completion) -> tuple[dict, bool]:
    """The assistant message for the history, and whether any arguments had to be replaced."""
    message: dict = {"role": "assistant", "content": done.content}
    sanitized = False
    if done.tool_calls:
        message["tool_calls"] = []
        for c in done.tool_calls:
            arguments, replaced = _echo_arguments(c.arguments)
            sanitized |= replaced
            function = {"name": c.name, "arguments": arguments}
            message["tool_calls"].append({"id": c.id, "type": "function", "function": function})
    return message, sanitized


def direct_tools(inputs_dir: Path, runs_dir: Path, record: Transcript):
    """The tools in this process: a ToolSession, nothing to open or close."""
    return nullcontext(ToolSession(inputs_dir, runs_dir, record))


OPEN_TOOLS = {"direct": direct_tools, "mcp": mcp_tools}


def _sum_cost(turns: list[TurnRecord]) -> float | None:
    costs = [t.cost for t in turns]
    return None if not costs or any(c is None for c in costs) else sum(costs)


class Conversation:
    """State of one question: messages, transcript and its tool session."""

    def __init__(self, question, profile, on_event, source, tools, via) -> None:
        self.on_event = on_event
        self.transcript = Transcript(
            transcript_id=new_run_id(datetime.now(UTC)),
            question=question,
            profile=profile.name,
            model=profile.model,
            source=source,
            provenance=provenance(tools) | {"via": via},
            report_accepted=False,
        )
        self.session = None  # set by ask() while the tools are open
        self.messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]

    def take_turn(self, done: Completion, seconds: float) -> None:
        t = self.transcript
        calls = []
        message, sanitized = _assistant_message(done)
        self.messages.append(message)
        submitted = False
        for call in done.tool_calls:
            again = submitted and call.name == "submit_report"
            submitted |= call.name == "submit_report"
            result = (
                {"error": ONE_SUBMIT} if again else self.session.call(call.name, call.arguments)
            )
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
                reasoning_tokens=done.reasoning_tokens,
                cost=done.cost,
                provider=done.provider,
                quantization=done.quantization,
                model=done.model,
                seconds=seconds,
                history_sanitized=sanitized,
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
    tools: list[dict] = TOOLS,
    on_event: Callable[[str, dict], None] = lambda kind, payload: None,
    source: str | None = None,
    via: Literal["direct", "mcp"] = "direct",
) -> Transcript:
    """Answer one question. Every outcome, including failures, leaves a saved transcript.

    `via="mcp"` sends every tool call through a `happy-toad mcp` server process (SPEC, M6 Q5).
    """
    started = time.perf_counter()
    convo = Conversation(question, profile, on_event, source, tools, via)
    t = convo.transcript
    t.status = "step_cap"
    try:
        with OPEN_TOOLS[via](inputs_dir, runs_dir, t) as convo.session:
            for _ in range(MAX_STEPS):
                turn_start = time.perf_counter()
                done = client.complete(convo.messages, tools)
                convo.take_turn(done, time.perf_counter() - turn_start)
                if convo.finished:
                    break
    except ProviderError as err:
        t.status = "api_error"
        t.api_error = {"status": err.status, "body": err.body, "step": len(t.turns) + 1}
    except Exception as err:  # the transcript must exist whatever the provider did
        t.status, t.error = "error", redact_error(f"{type(err).__name__}: {err}")
    except KeyboardInterrupt:
        t.status = "interrupted"
        raise
    finally:
        t.total_tokens = {
            "prompt": sum(x.prompt_tokens for x in t.turns),
            "completion": sum(x.completion_tokens for x in t.turns),
            "reasoning": sum(x.reasoning_tokens for x in t.turns),
        }
        t.cost = _sum_cost(t.turns)
        t.elapsed_seconds = time.perf_counter() - started
        t.save(transcripts_dir)
    return t
