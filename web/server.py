"""Local live page: http://127.0.0.1:8765, one question at a time, key kept server-side.

Usage: OPENROUTER_API_KEY=... uv run python -m web.server
"""

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from happy_toad import cli
from happy_toad.agent.config import PROFILES
from happy_toad.agent.demo import QUESTIONS
from happy_toad.agent.loop import ask
from web.page import render_page
from web.redact import redact_text
from web.view import build_view, referenced_runs, step

HOST = "127.0.0.1"  # loopback only, never 0.0.0.0
PORT = 8765
MAX_CHARS = 500
TOO_LONG = f"questions are limited to {MAX_CHARS} characters"
PROFILE = "demo"
BUSY = threading.Lock()


@dataclass
class Settings:
    inputs_dir: Path = Path("data/inputs")
    runs_dir: Path = Path("runs")
    transcripts_dir: Path = Path("transcripts")
    make_client: Callable = cli.make_client
    refusal_log: Path = Path("web/refusals.log")  # gitignored by *.log


class Refused(Exception):
    """A request the server turns away: HTTP status, log reason, message for the page."""

    def __init__(self, status: int, reason: str, message: str, length: int | None) -> None:
        super().__init__(message)
        self.status, self.reason, self.length = status, reason, length


def log_refusal(path: Path, refused: Refused) -> None:
    """One JSON line: time, reason and question length, never the question text."""
    entry = {"time": datetime.now(UTC).isoformat(timespec="seconds"), "reason": refused.reason}
    entry["question_length"] = refused.length
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as log:
        log.write(json.dumps(entry) + "\n")


def _question(body: bytes) -> str:
    """The question from a JSON body; Refused if it is missing, empty or too long."""
    try:
        question = json.loads(body or b"{}").get("question")
    except (ValueError, AttributeError) as err:
        raise Refused(400, "bad_request", "send JSON with a question", None) from err
    length = len(question) if isinstance(question, str) else None
    if not isinstance(question, str) or not question.strip():
        raise Refused(400, "empty", "send a non-empty question", length)
    if length > MAX_CHARS:
        raise Refused(400, "too_long", TOO_LONG, length)
    return question


def make_handler(settings: Settings) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        page_closed = False

        def do_GET(self) -> None:
            if self.path != "/":
                return self._json(404, {"error": "not found"})
            boot = {"mode": "live", "examples": QUESTIONS, "max_chars": MAX_CHARS}
            self._send(200, "text/html; charset=utf-8", render_page(boot).encode())

        def do_POST(self) -> None:
            if self.path != "/api/ask":
                return self._json(404, {"error": "not found"})
            try:
                self._ask(self._body())
            except Refused as refused:
                self._json(refused.status, {"error": redact_text(str(refused))})
                log_refusal(settings.refusal_log, refused)

        def _body(self) -> bytes:
            length = int(self.headers.get("Content-Length", 0))
            if length > MAX_CHARS * 8:  # too big to be a capped question; not read
                raise Refused(400, "too_long", TOO_LONG, None)
            return self.rfile.read(length)

        def _ask(self, body: bytes) -> None:
            question = _question(body)
            if not BUSY.acquire(blocking=False):
                busy = "busy: one question at a time, try again shortly"
                raise Refused(429, "busy", busy, len(question))
            try:
                self._answer(question)
            finally:
                BUSY.release()

        def _answer(self, question: str) -> None:
            profile = PROFILES[PROFILE]
            try:
                client = settings.make_client(profile)
            except RuntimeError as err:
                raise Refused(503, "no_key", str(err), len(question)) from err
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            t = ask(
                question,
                client,
                profile,
                inputs_dir=settings.inputs_dir,
                runs_dir=settings.runs_dir,
                transcripts_dir=settings.transcripts_dir,
                on_event=lambda _kind, call: self._line({"type": "step", "step": step(call)}),
            )
            self._line(
                {"type": "view", "view": build_view(t, referenced_runs(t, settings.runs_dir))}
            )

        def _line(self, message: dict) -> None:
            """Stream one message; once the page has gone, stop writing and let the answer
            finish so the transcript is saved complete."""
            if self.page_closed:
                return
            try:
                self.wfile.write(json.dumps(message).encode() + b"\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                self.page_closed = True

        def _json(self, status: int, payload: dict) -> None:
            self._send(status, "application/json", json.dumps(payload).encode())

        def _send(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def make_server(settings: Settings, port: int = PORT) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((HOST, port), make_handler(settings))


def main() -> None:
    httpd = make_server(Settings())
    print(f"Local demo on http://{HOST}:{httpd.server_address[1]} (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.server_close()


if __name__ == "__main__":
    main()
