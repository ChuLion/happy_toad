"""The local server with a scripted fake client: bind, caps, streaming, no key in responses."""

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
        if self.gate:
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
    assert lines[-1]["view"]["schema_version"] == 1
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
