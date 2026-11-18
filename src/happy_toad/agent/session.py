"""The tool calls of one session: the seven tools, known runs and the report check (SPEC, M6).

Shared by the agent loop (one session per conversation) and the MCP server (one per process).
"""

from pathlib import Path

from pydantic import ValidationError

from happy_toad.agent.checker import check_report
from happy_toad.agent.report import Report, coercions, defaults
from happy_toad.agent.tools import ToolRunner
from happy_toad.agent.transcript import Transcript

RUN_ID_KEYS = ("run_id", "run_id_a", "run_id_b", "follow_up_run_id")


class ToolSession:
    """Runs tool calls and checks reports, recording both on `record`.

    A failed report leaves a correction pending; the next report's verdict is final (A1).
    """

    def __init__(self, inputs_dir: Path, runs_dir: Path, record: Transcript) -> None:
        self.inputs_dir, self.runs_dir, self.record = inputs_dir, runs_dir, record
        self.runner = ToolRunner(inputs_dir, runs_dir, record.transcript_id)
        self.runs: list[str] = []  # run ids executed, read or compared in this session
        self.correction_pending = False

    def call(self, name: str, arguments: str) -> dict:
        """One tool call with its JSON arguments; every outcome is a dict for the model."""
        if name == "submit_report":
            return self.submit(arguments)
        result = self.runner.call(name, arguments)
        self._track(result)
        return result

    def _track(self, result: dict) -> None:
        revision = result.get("revision") or {}  # M5: the two end runs are nested
        found = [result.get(k) for k in RUN_ID_KEYS]
        found += [revision.get(k) for k in ("run_id_a", "run_id_b")]
        for run_id in found:
            if isinstance(run_id, str) and run_id not in self.runs:
                self.runs.append(run_id)

    def submit(self, arguments: str) -> dict:
        """submit_report: schema, then the checker, with one chance to correct."""
        try:
            report = Report.model_validate_json(arguments)
        except ValidationError as err:
            return {"accepted": False, "error": f"report does not fit the schema: {err}"}
        t = self.record
        t.coercions += coercions(arguments, report)
        t.defaults += defaults(arguments, report)
        result = check_report(report, self.runs_dir, self.inputs_dir, self.runs)
        t.checks.append(result)
        t.report = report
        if result.ok:
            self.correction_pending = False
            t.status, t.report_accepted = "checked", True
            return {"accepted": True}
        t.report_accepted = False
        if not self.correction_pending:
            self.correction_pending = True
            return {
                "accepted": False,
                "errors": result.errors(),
                "instruction": "fix and resubmit once",
            }
        self.correction_pending = False
        t.status = "unverified"
        return {"accepted": False, "errors": result.errors()}
