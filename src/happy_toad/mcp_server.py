"""MCP server: the seven tools over stdio, translated to one ToolSession (SPEC, M6).

No business logic: tool definitions come from TOOLS, calls go to ToolSession, the label from
agent/label.py. One process is one session (A1).
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import mcp_types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from happy_toad.agent.label import verdict
from happy_toad.agent.prompt import SYSTEM_PROMPT
from happy_toad.agent.provenance import provenance
from happy_toad.agent.session import ToolSession
from happy_toad.agent.tools import TOOLS
from happy_toad.agent.transcript import Transcript
from happy_toad.services.run import new_run_id

SERVER_NAME = "happy-toad"
RAW = "_raw_arguments"  # unparseable arguments from our own client, passed on as written (A4)
META_KEY = "happy_toad/record"
RECORD_FIELDS = {"checks", "report", "status", "report_accepted", "coercions", "defaults"}


def tool_list() -> list[types.Tool]:
    """The seven tool definitions, name, description and schema unchanged (Q4)."""
    return [
        types.Tool(
            name=t["function"]["name"],
            description=t["function"]["description"],
            input_schema=t["function"]["parameters"],
        )
        for t in TOOLS
    ]


def arguments_text(arguments: dict | None) -> str:
    """The JSON text ToolSession expects; the raw text when our client could not parse it."""
    if arguments is not None and set(arguments) == {RAW}:
        return arguments[RAW]
    return json.dumps(arguments or {})


class SessionLog(Transcript):
    """A Desktop session: every tool call of one server process, with its checks."""

    tool_calls: list[dict] = []
    client: dict | None = None  # name and version the client sent in the handshake


class McpSession:
    """One server process. With a transcript id (eval path), runs carry it and no log is written."""

    def __init__(
        self,
        inputs_dir: Path,
        runs_dir: Path,
        transcripts_dir: Path,
        transcript_id: str | None = None,
    ) -> None:
        self.log_dir = None if transcript_id else transcripts_dir / "mcp"
        self.record = SessionLog(
            transcript_id=transcript_id or new_run_id(datetime.now(UTC)),
            question="",
            profile="mcp",
            model="chosen by the client",
            source="eval-mcp" if transcript_id else "mcp",
            provenance=provenance(),
            report_accepted=False,
        )
        self.tools = ToolSession(inputs_dir, runs_dir, self.record)

    def handle(self, name: str, arguments: dict | None) -> dict:
        """One tool call; a final report also returns its label and summary (Q3)."""
        before = len(self.record.checks)
        result = self.tools.call(name, arguments_text(arguments))
        checked = len(self.record.checks) > before
        if name == "submit_report" and checked and not self.tools.correction_pending:
            result |= {"label": verdict(self.record), "summary": self.record.report.summary}
        self.record.tool_calls.append({"name": name, "arguments": arguments, "result": result})
        if self.log_dir:
            self.record.save(self.log_dir)
        return result

    def record_meta(self) -> dict:
        """The check record, for our own client to copy into its transcript (eval path)."""
        return self.record.model_dump(mode="json", include=RECORD_FIELDS)

    def note_client(self, client_params) -> None:
        if client_params is not None and self.record.client is None:
            self.record.client = client_params.client_info.model_dump(mode="json")


def build_server(session: McpSession) -> Server:
    """A low-level server whose handlers only translate."""

    async def list_tools(ctx, params) -> types.ListToolsResult:
        return types.ListToolsResult(tools=tool_list())

    async def call_tool(ctx, params) -> types.CallToolResult:
        session.note_client(ctx.session.client_params)
        text = json.dumps(session.handle(params.name, params.arguments), default=str)
        meta = {META_KEY: session.record_meta()} if params.name == "submit_report" else None
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=text)],
            structured_content=json.loads(text),
            _meta=meta,
        )

    return Server(
        SERVER_NAME, instructions=SYSTEM_PROMPT, on_list_tools=list_tools, on_call_tool=call_tool
    )


async def serve(session: McpSession) -> None:
    """Serve one session over this process's stdin and stdout."""
    server = build_server(session)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())
