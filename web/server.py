"""Local live page: http://127.0.0.1:8765, one question at a time, key kept server-side.

Usage: OPENROUTER_API_KEY=... uv run python -m web.server
"""

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass
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
PROFILE = "demo"
BUSY = threading.Lock()


@dataclass
class Settings:
    inputs_dir: Path = Path("data/inputs")
    runs_dir: Path = Path("runs")
    transcripts_dir: Path = Path("transcripts")
    make_client: Callable = cli.make_client


def _question(body: bytes) -> str:
    """The question from a JSON body; ValueError with a message for the page if unusable."""
    question = json.loads(body or b"{}").get("question")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("send a non-empty question")
    if len(question) > MAX_CHARS:
        raise ValueError(f"questions are limited to {MAX_CHARS} characters")
    return question


def make_handler(settings: Settings) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path != "/":
                return self._json(404, {"error": "not found"})
            boot = {"mode": "live", "examples": QUESTIONS, "max_chars": MAX_CHARS}
            self._send(200, "text/html; charset=utf-8", render_page(boot).encode())

        def do_POST(self) -> None:
            if self.path != "/api/ask":
                return self._json(404, {"error": "not found"})
            length = int(self.headers.get("Content-Length", 0))
            if length > MAX_CHARS * 8:
                return self._json(
                    400, {"error": f"questions are limited to {MAX_CHARS} characters"}
                )
            try:
                question = _question(self.rfile.read(length))
            except ValueError as err:
                return self._json(400, {"error": str(err)})
            if not BUSY.acquire(blocking=False):
                return self._json(429, {"error": "busy: one question at a time, try again shortly"})
            try:
                self._answer(question)
            finally:
                BUSY.release()

        def _answer(self, question: str) -> None:
            profile = PROFILES[PROFILE]
            try:
                client = settings.make_client(profile)
            except RuntimeError as err:
                return self._json(503, {"error": redact_text(str(err))})
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
            self.wfile.write(json.dumps(message).encode() + b"\n")
            self.wfile.flush()

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
