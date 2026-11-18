"""M4 part A: provenance, source, run-to-transcript link, accepted flag, redaction, S8/S10."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from agent_helpers import FakeClient, call, toy_dirs, turn
from typer.testing import CliRunner

import happy_toad.cli as cli
from happy_toad.agent.bakeoff import provenance as bakeoff_provenance
from happy_toad.agent.bakeoff import run_bakeoff
from happy_toad.agent.client import ProviderError
from happy_toad.agent.config import SMOKE, Profile
from happy_toad.agent.loop import ask
from happy_toad.agent.prompt import SYSTEM_PROMPT
from happy_toad.agent.provenance import provenance, redact_error
from happy_toad.agent.tools import TOOLS
from happy_toad.agent.transcript import Transcript, TurnRecord
from happy_toad.services.request import SolveRequest
from happy_toad.services.run import RunRecord, run_request
from happy_toad.services.runs import read_run

FIXTURE = Path(__file__).parent / "fixtures/transcript_demo_c.json"
KEY = "sk-or-v1-" + "a" * 64
ACCOUNT = "user_3FEB9A6yngm4bVylctIJkgAmiTJ"


@pytest.fixture
def dirs(tmp_path):
    inputs, runs = toy_dirs(tmp_path)
    return dict(inputs_dir=inputs, runs_dir=runs, transcripts_dir=tmp_path / "transcripts")


def run_then_report(claims=None):
    """Run budget 12, then a claimless report (accepted) or the given claims."""
    report = dict(summary="Done.", claims=claims or [])
    return [
        turn(call("run_scenario", input_version="test", budget=12)),
        turn(call("submit_report", **report)),
        turn(call("submit_report", **report)),
    ]


def git(*args) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()


# --- provenance --------------------------------------------------------------------------------


def test_provenance_has_the_commit_the_dirty_flag_and_the_prompt_hash():
    p = provenance()
    assert p["git_sha"] == git("rev-parse", "HEAD")
    assert p["git_dirty"] == bool(git("status", "--porcelain", "--untracked-files=no"))
    text = SYSTEM_PROMPT + json.dumps(TOOLS, sort_keys=True)
    assert p["prompt_sha256"] == hashlib.sha256(text.encode()).hexdigest()


def test_the_prompt_hash_changes_with_the_tool_definitions():
    changed = json.loads(json.dumps(TOOLS))
    changed[0]["function"]["description"] += " (changed)"
    assert provenance(changed)["prompt_sha256"] != provenance()["prompt_sha256"]


def test_the_bakeoff_provenance_adds_the_frozen_file_hashes():
    p = bakeoff_provenance()
    assert {k: p[k] for k in ("git_sha", "git_dirty", "prompt_sha256")} == provenance()
    assert set(p["frozen_files"]) == {"checker.py", "report.py", "tools.py", "prompt.py", "loop.py"}


def test_every_transcript_records_provenance_and_its_source(dirs):
    t = ask("q", FakeClient(run_then_report()), SMOKE, source="eval", **dirs)
    assert t.provenance == provenance() | {"via": "direct"}  # M6: the route of the tool calls
    assert t.source == "eval"
    saved = Transcript.model_validate_json(next(dirs["transcripts_dir"].glob("*.json")).read_text())
    assert saved.provenance == t.provenance and saved.source == "eval"


def test_the_cli_marks_its_transcripts_cli(dirs, monkeypatch):
    monkeypatch.setattr(cli, "make_client", lambda profile: FakeClient(run_then_report()))
    args = ["ask", "q", *(f"--{k.replace('_', '-')}={v}" for k, v in dirs.items())]
    assert CliRunner().invoke(cli.app, args).exit_code == 3  # claimless: NO NUMBERS TO CHECK
    saved = next(dirs["transcripts_dir"].glob("*.json")).read_text()
    assert Transcript.model_validate_json(saved).source == "cli"


def test_the_bakeoff_marks_its_transcripts_bakeoff(dirs):
    profiles = {"one": Profile("one", "fake/one")}
    run_bakeoff(profiles, lambda p: FakeClient(run_then_report()), {"q1": "q"}, **dirs)
    saved = next(dirs["transcripts_dir"].glob("*.json")).read_text()
    assert Transcript.model_validate_json(saved).source == "bakeoff"


# --- run to transcript link --------------------------------------------------------------------


def test_runs_made_by_the_agent_name_their_transcript(dirs):
    script = [
        turn(call("run_scenario", input_version="test", budget=12)),
        turn(call("find_target_budget", input_version="test", target_pct_resolved=30)),
        turn(call("run_scenario", input_version="test", budget="twelve")),
        turn(call("submit_report", summary="Done.", claims=[])),
    ]
    t = ask("q", FakeClient(script), SMOKE, **dirs)
    records = [read_run(p.stem, dirs["runs_dir"]) for p in dirs["runs_dir"].glob("*.json")]
    assert len(records) == 4  # scenario, search, its follow-up, schema-invalid
    assert {r.transcript_id for r in records} == {t.transcript_id}


def test_runs_made_outside_the_agent_have_no_transcript(dirs):
    record = run_request(
        SolveRequest(input_version="test", budget=12), dirs["inputs_dir"], dirs["runs_dir"]
    )
    assert record.transcript_id is None


# --- accepted-report flag ----------------------------------------------------------------------


def test_report_accepted_is_true_only_when_the_last_report_was_accepted(dirs):
    accepted = ask("q", FakeClient(run_then_report()), SMOKE, **dirs)
    assert accepted.status == "checked" and accepted.report_accepted is True
    wrong = [dict(metric="spend", value=999.0, unit="cost_units", run_id="nope")]
    refused = ask("q", FakeClient(run_then_report(wrong)), SMOKE, **dirs)
    assert refused.status == "unverified" and refused.report_accepted is False


def test_no_report_means_not_accepted(dirs):
    stuck = ask("q", FakeClient([turn(call("list_input_versions"))] * 10), SMOKE, **dirs)
    assert stuck.status == "step_cap" and stuck.report_accepted is False


# --- old files still load ----------------------------------------------------------------------


def test_transcripts_saved_before_m4_still_load():
    t = Transcript.model_validate(json.loads(FIXTURE.read_text()))
    assert t.provenance is None and t.source is None and t.report_accepted is None


def test_run_records_saved_before_m4_still_load(dirs):
    record = run_request(
        SolveRequest(input_version="test", budget=12), dirs["inputs_dir"], dirs["runs_dir"]
    )
    raw = json.loads(record.model_dump_json())
    raw.pop("transcript_id")
    assert RunRecord.model_validate(raw).transcript_id is None


# --- error redaction ---------------------------------------------------------------------------


def test_redact_error_cuts_to_500_characters_and_hides_keys_and_account_ids():
    text = f"key {KEY} account {ACCOUNT} " + "x" * 1000
    out = redact_error(text)
    assert len(out) <= 500
    assert KEY not in out and ACCOUNT not in out and "[redacted]" in out


def test_a_provider_error_body_is_redacted_and_cut():
    err = ProviderError(400, f'{{"user_id": "{ACCOUNT}", "key": "{KEY}"}}' + "y" * 2000)
    assert len(err.body) <= 500
    assert KEY not in err.body and ACCOUNT not in err.body
    assert KEY not in str(err)


def test_an_unexpected_client_error_is_redacted_in_the_transcript(dirs):
    class Broken:
        def complete(self, messages, tools):
            raise RuntimeError(f"bad header Authorization: Bearer {KEY}")

    t = ask("q", Broken(), SMOKE, **dirs)
    assert t.status == "error"
    assert KEY not in t.error and "[redacted]" in t.error


# --- S10 ---------------------------------------------------------------------------------------


def test_transcript_providers_are_sorted_unique_with_unknown_for_missing():
    def record(index, provider):
        return TurnRecord(
            index=index, content=None, tool_calls=[], prompt_tokens=0, completion_tokens=0,
            cost=None, provider=provider, model="m", seconds=0.0,
        )  # fmt: skip

    t = Transcript(transcript_id="t", question="q", profile="p", model="m")
    t.turns = [record(1, "B"), record(2, None), record(3, "A"), record(4, "B")]
    assert t.providers == ["A", "B", "unknown"]


def test_without_git_the_transcript_is_still_saved_with_unknown_commit(dirs, monkeypatch):
    import happy_toad.agent.provenance as module

    def no_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(module.subprocess, "run", no_git)
    t = ask("q", FakeClient(run_then_report()), SMOKE, **dirs)
    assert t.status == "checked"
    assert t.provenance["git_sha"] is None and t.provenance["git_dirty"] is None
    assert t.provenance["prompt_sha256"] == provenance()["prompt_sha256"]
    assert list(dirs["transcripts_dir"].glob("*.json"))


def test_outside_a_git_checkout_the_commit_is_unknown(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert provenance()["git_sha"] is None
