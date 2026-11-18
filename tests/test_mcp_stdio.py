"""`happy-toad mcp` over a real stdio connection (SPEC, M6 Q2, Q4, A2, A5)."""

import json
import subprocess
import sys
from pathlib import Path

import anyio
from agent_helpers import toy_dirs
from mcp import Client, StdioServerParameters

from happy_toad.agent.prompt import SYSTEM_PROMPT
from happy_toad.agent.provenance import prompt_sha256, provenance
from happy_toad.agent.tools import TOOLS
from happy_toad.mcp_server import META_KEY

CLI = str(Path(sys.executable).parent / "happy-toad")


def server(tmp_path) -> StdioServerParameters:
    inputs, runs = toy_dirs(tmp_path)
    folders = ["--inputs-dir", str(inputs), "--runs-dir", str(runs)]
    folders += ["--transcripts-dir", str(tmp_path / "transcripts")]
    return StdioServerParameters(command=CLI, args=["mcp", *folders])


def as_openai(tool) -> dict:
    spec = {"name": tool.name, "description": tool.description, "parameters": tool.input_schema}
    return {"type": "function", "function": spec}


def network_sockets(pid: int) -> str:
    out = subprocess.run(["lsof", "-a", "-p", str(pid), "-i"], capture_output=True, text=True)
    return out.stdout


def test_the_client_receives_the_same_prompt_and_tools(tmp_path) -> None:
    async def check():
        async with Client(server(tmp_path)) as c:
            tools = [as_openai(t) for t in (await c.list_tools()).tools]
            return c.instructions, tools

    instructions, tools = anyio.run(check)
    assert instructions == SYSTEM_PROMPT
    assert tools == TOOLS
    assert prompt_sha256(tools) == provenance()["prompt_sha256"]


def test_a_tool_call_returns_the_tool_result_as_json(tmp_path) -> None:
    async def call():
        async with Client(server(tmp_path)) as c:
            return await c.call_tool("list_input_versions", {})

    result = anyio.run(call)
    assert not result.is_error
    assert result.structured_content == {"versions": ["test"], "change_lists": []}
    assert json.loads(result.content[0].text) == result.structured_content


def test_submit_report_carries_the_check_record_in_meta(tmp_path) -> None:
    async def submit():
        async with Client(server(tmp_path)) as c:
            return await c.call_tool("submit_report", {"summary": "No numbers.", "claims": []})

    result = anyio.run(submit)
    assert result.structured_content["label"] == "NO NUMBERS TO CHECK"
    assert result.meta[META_KEY]["status"] == "checked"


def test_the_server_opens_no_network_socket(tmp_path) -> None:
    async def sockets():
        async with Client(server(tmp_path)) as c:
            await c.list_tools()
            pids = subprocess.run(["pgrep", "-f", str(tmp_path)], capture_output=True, text=True)
            return [network_sockets(int(p)) for p in pids.stdout.split()]

    found = anyio.run(sockets)
    assert found and all(s == "" for s in found)
