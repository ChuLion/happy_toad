"""Where a transcript came from: commit, uncommitted changes and prompt hash (SPEC, M4 part A)."""

import hashlib
import json
import subprocess

from happy_toad.agent.prompt import SYSTEM_PROMPT
from happy_toad.agent.redaction import redact_error
from happy_toad.agent.tools import TOOLS

__all__ = ["provenance", "redact_error"]


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()


def prompt_sha256(tools: list[dict]) -> str:
    """SHA-256 of the system prompt plus the sorted-key JSON of the tool definitions."""
    return hashlib.sha256((SYSTEM_PROMPT + json.dumps(tools, sort_keys=True)).encode()).hexdigest()


def provenance(tools: list[dict] | None = None) -> dict:
    """Commit, whether tracked files have uncommitted changes, and the prompt hash."""
    return {
        "git_sha": _git("rev-parse", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain", "--untracked-files=no")),
        "prompt_sha256": prompt_sha256(TOOLS if tools is None else tools),
    }
