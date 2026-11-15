"""The local server with a scripted fake client: bind, caps, streaming, no key in responses."""

import http.client
import json
import threading
import urllib.error
import urllib.request

import pytest

from happy_toad.agent.client import Completion, ToolCall
from web import server

KEY = "sk-or-v1-" + "f" * 64


def _completion(name: str, arguments: dict) -> Completion:
    call = ToolCall(id=f"call_{name}", name=name, arguments=json.dumps(arguments))
    return Completion(content=None, tool_calls=[call], cost=0.001, provider="Fake", model="fake")


class FakeClient:
    def __init__(self, gate: threading.Event | None = None) -> None:
        self.gate = gate
        self.script = [
            _completion("list_input_versions", {}),
            _completion("submit_report", {"summary": "No versions are stored.", "claims": []}),
        ]

    def complete(self, messages, tools) -> Completion:
        if self.gate and len(self.script) == 1:  # wait before the second turn
            self.gate.wait(5)
        return self.script.pop(0)


@pytest.fixture
def live(tmp_path, monkeypatch):
    """A running server on a free port; yields (base url, settings)."""
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)
    settings = server.Settings(
        inputs_dir=tmp_path / "inputs",
        runs_dir=tmp_path / "runs",
        transcripts_dir=tmp_path / "transcripts",
        make_client=lambda profile: FakeClient(),
        refusal_log=tmp_path / "refusals.log",
    )
    httpd = server.make_server(settings, port=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", settings, httpd
    httpd.shutdown()
    httpd.server_close()


def _post(url: str, question: str) -> tuple[int, str]:
    body = json.dumps({"question": question}).encode()
    request = urllib.request.Request(url + "/api/ask", data=body, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode()


def test_binds_to_loopback_only(live):
    _, _, httpd = live
    assert httpd.server_address[0] == "127.0.0.1"


def test_page_is_live_mode_without_the_key(live):
    url, _, _ = live
    page = urllib.request.urlopen(url + "/", timeout=5).read().decode()
    assert '"mode": "live"' in page
    assert "Local demo, uses a live model on synthetic data." in page
    assert KEY not in page


def test_streams_steps_then_the_view(live):
    url, _, _ = live
    status, text = _post(url, "Which versions exist?")
    lines = [json.loads(line) for line in text.splitlines()]
    assert status == 200
    assert [m["type"] for m in lines] == ["step", "step", "view"]
    assert lines[0]["step"]["tool"] == "list_input_versions"
    assert lines[-1]["view"]["schema_version"] == 2
    assert KEY not in text


def test_question_length_is_capped(live):
    url, _, _ = live
    status, text = _post(url, "x" * (server.MAX_CHARS + 1))
    assert status == 400
    assert "500" in json.loads(text)["error"]


def test_one_request_at_a_time(live):
    url, settings, _ = live
    gate = threading.Event()
    settings.make_client = lambda profile: FakeClient(gate)
    first = threading.Thread(target=_post, args=(url, "first"))
    first.start()
    while not server.BUSY.locked():
        pass
    status, text = _post(url, "second")
    gate.set()
    first.join()
    assert status == 429
    assert "one question at a time" in json.loads(text)["error"]


def _settle() -> None:
    """Wait for request threads: the server replies before it writes the log."""
    for thread in threading.enumerate():
        if "process_request" in thread.name:
            thread.join(5)


def _refusals(settings) -> list[dict]:
    _settle()
    return [json.loads(line) for line in settings.refusal_log.read_text().splitlines()]


def test_refusals_are_logged_without_the_question(live, monkeypatch):
    url, settings, _ = live
    _post(url, "x" * (server.MAX_CHARS + 1))
    _post(url, "   ")

    def no_key(profile):
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    settings.make_client = no_key
    status, _ = _post(url, "secret question text")
    assert status == 503
    logged = _refusals(settings)
    assert [r["reason"] for r in logged] == ["too_long", "empty", "no_key"]
    assert [r["question_length"] for r in logged] == [server.MAX_CHARS + 1, 3, 20]
    assert all(set(r) == {"time", "reason", "question_length"} for r in logged)
    assert "secret" not in settings.refusal_log.read_text()


def test_busy_refusal_is_logged(live):
    url, settings, _ = live
    gate = threading.Event()
    settings.make_client = lambda profile: FakeClient(gate)
    first = threading.Thread(target=_post, args=(url, "first"))
    first.start()
    while not server.BUSY.locked():
        pass
    _post(url, "second")
    gate.set()
    first.join()
    assert _refusals(settings) == [
        {"time": _refusals(settings)[0]["time"], "reason": "busy", "question_length": 6}
    ]


def test_closing_the_page_mid_answer_ends_quietly_and_saves(live, capfd):
    url, settings, _ = live
    gate = threading.Event()
    settings.make_client = lambda profile: FakeClient(gate)
    host, port = url.removeprefix("http://").split(":")
    conn = http.client.HTTPConnection(host, int(port), timeout=5)
    conn.request("POST", "/api/ask", json.dumps({"question": "Which versions exist?"}))
    response = conn.getresponse()
    assert json.loads(response.readline())["type"] == "step"
    response.close()
    conn.close()
    gate.set()
    _settle()
    saved = list(settings.transcripts_dir.glob("*.json"))
    assert len(saved) == 1
    assert json.loads(saved[0].read_text())["status"] == "checked"
    assert "Traceback" not in capfd.readouterr().err


def test_refusal_log_folder_is_created(live):
    url, settings, _ = live
    settings.refusal_log = settings.refusal_log.parent / "new" / "refusals.log"
    status, _ = _post(url, "   ")
    assert status == 400
    assert _refusals(settings)[0]["reason"] == "empty"
