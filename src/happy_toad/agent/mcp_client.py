"""The loop's tool calls sent through `happy-toad mcp` over stdio (SPEC, M6 Q5).

One server process per conversation. The SDK is async and the loop is sync, so the client
session runs in an anyio blocking portal.
"""

import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from anyio.from_thread import BlockingPortal, start_blocking_portal
from mcp import Client, StdioServerParameters

from happy_toad.agent.transcript import Transcript
from happy_toad.mcp_server import META_KEY, RAW

SERVER = str(Path(sys.executable).parent / "happy-toad")
FINAL = ("checked", "unverified")


def server_parameters(
    inputs_dir: Path, runs_dir: Path, transcript_id: str
) -> StdioServerParameters:
    args = ["mcp", "--inputs-dir", str(inputs_dir), "--runs-dir", str(runs_dir)]
    return StdioServerParameters(command=SERVER, args=[*args, "--transcript-id", transcript_id])


def as_arguments(text: str) -> dict:
    """The model's arguments as an object; anything else is passed on as written (A4)."""
    try:
        value = json.loads(text or "{}")
    except json.JSONDecodeError:
        return {RAW: text}
    return value if isinstance(value, dict) else {RAW: text}


class McpTools:
    """Same interface as ToolSession: call(name, arguments) returns the tool result dict."""

    def __init__(self, portal: BlockingPortal, client: Client, record: Transcript) -> None:
        self.portal, self.client, self.record = portal, client, record

    def call(self, name: str, arguments: str) -> dict:
        result = self.portal.call(self.client.call_tool, name, as_arguments(arguments))
        if name == "submit_report":
            self._copy_record(result.meta[META_KEY])
        return result.structured_content

    def _copy_record(self, fields: dict) -> None:
        """The server's check record, copied into this conversation's transcript.

        The status is copied only when final: before that the server's is its default, and the
        loop keeps its own ("step_cap" until a verdict).
        """
        if fields["status"] not in FINAL:
            fields = {k: v for k, v in fields.items() if k != "status"}
        fresh = Transcript.model_validate(self.record.model_dump() | fields)
        for name in fields:
            setattr(self.record, name, getattr(fresh, name))


@contextmanager
def mcp_tools(inputs_dir: Path, runs_dir: Path, record: Transcript) -> Iterator[McpTools]:
    """A server process for one conversation; stopped when the conversation ends."""
    params = server_parameters(inputs_dir, runs_dir, record.transcript_id)
    with start_blocking_portal() as portal:
        with portal.wrap_async_context_manager(Client(params)) as client:
            yield McpTools(portal, client, record)
