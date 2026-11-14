"""The five tools: their descriptions (SPEC, M3) and the code behind four of them.

`submit_report` is handled by the loop, because accepting it ends the conversation.
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from happy_toad.agent.report import Report
from happy_toad.engine.result import DEFAULT_SETTINGS
from happy_toad.reasons import Reason, ReasonCode
from happy_toad.services.request import SolveRequest
from happy_toad.services.run import RunRecord, new_run_id, run_request, write_record
from happy_toad.services.runs import CompareError, compare_runs, list_versions, read_run

TOP_UNRESOLVED = 5


def _tool(name: str, description: str, parameters: dict) -> dict:
    spec = {"name": name, "description": description, "parameters": parameters}
    return {"type": "function", "function": spec}


def _object(properties: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": properties, "required": required}


_RUN_ID = {"type": "string", "description": "A run id returned by run_scenario."}

TOOLS = [
    _tool(
        "list_input_versions",
        "List the names of the available input versions (synthetic data sets). Call this when "
        "the user does not name a version or you are unsure what exists.",
        _object({}, []),
    ),
    _tool(
        "run_scenario",
        "Run the optimizer once for one scenario and record it. `budget` is the TOTAL budget "
        "including must-fund projects. `force_in` and `force_out` are candidate ids (for example "
        "C033). Returns the run id and a summary: status, weighted relief (`objective`), spend "
        "(candidates only), selected candidates, sectors resolved, percent resolved, unresolved "
        "sectors, and, when infeasible, the cause and `required_minimum_budget` (the budget must "
        "be at least that). Never guess a budget; ask the user.",
        SolveRequest.model_json_schema(),
    ),
    _tool(
        "get_run",
        "Return the stored summary of an earlier run by its run id.",
        _object({"run_id": _RUN_ID}, ["run_id"]),
    ),
    _tool(
        "compare_runs",
        "Compare two completed runs that both have a plan: status, spend, weighted relief, "
        "number selected, number resolved, percent resolved, and which candidates are only in "
        "one run. Use it for a comparison instead of computing differences yourself.",
        _object({"run_id_a": _RUN_ID, "run_id_b": _RUN_ID}, ["run_id_a", "run_id_b"]),
    ),
    _tool(
        "submit_report",
        "Submit the final answer. Every number in `summary` must also be a claim "
        "`{metric, value, unit, run_id, entity}` taken from a run you executed or read, or be a "
        "request value such as the budget. Values at displayed precision.",
        Report.model_json_schema(),
    ),
]


def run_view(record: RunRecord) -> dict:
    """What the model sees of a run: the summary without solver internals."""
    view = record.model_dump(
        mode="json",
        include={"run_id", "outcome", "reasons", "required_minimum_budget", "error", "warnings"},
    )
    r = record.result
    if r is not None:
        gaps = r.unresolved or []
        view["result"] = {
            **r.model_dump(mode="json", exclude={"solver_settings", "stage_times", "unresolved"}),
            "unresolved_count": len(gaps),
            "top_unresolved": [g.model_dump(mode="json") for g in gaps[:TOP_UNRESOLVED]],
        }
    else:
        view["result"] = None
    return view


def _fields_in(error: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(map(str, e['loc'])) or 'input'}: {e['msg']}" for e in error.errors()
    )


class ToolRunner:
    """Runs the four deterministic tools against the inputs and runs folders."""

    def __init__(self, inputs_dir: Path, runs_dir: Path) -> None:
        self.inputs_dir = inputs_dir
        self.runs_dir = runs_dir

    def call(self, name: str, arguments: str) -> dict:
        """Run a tool by name with its JSON arguments; every outcome is a dict for the model."""
        try:
            args = json.loads(arguments or "{}")
        except json.JSONDecodeError:
            args = None
        if name == "run_scenario":
            return self.run_scenario(
                args if isinstance(args, dict) else {"_raw_arguments": arguments}
            )
        if not isinstance(args, dict):
            return {"error": "arguments are not a JSON object"}
        if name == "list_input_versions":
            return {"versions": list_versions(self.inputs_dir)}
        if name == "get_run":
            return self.get_run(args.get("run_id", ""))
        if name == "compare_runs":
            return self.compare(args.get("run_id_a", ""), args.get("run_id_b", ""))
        return {"error": f"unknown tool {name!r}"}

    def run_scenario(self, args: dict) -> dict:
        try:
            request = SolveRequest.model_validate(args)
        except ValidationError as err:
            return run_view(self.record_schema_invalid(args, _fields_in(err)))
        return run_view(run_request(request, self.inputs_dir, self.runs_dir))

    def record_schema_invalid(self, raw: dict, message: str) -> RunRecord:
        """A rejected run record for an input that does not fit the request schema."""
        created = datetime.now(UTC)
        version = raw.get("input_version")
        record = RunRecord(
            run_id=new_run_id(created),
            created_at=created.isoformat(),
            outcome="rejected",
            request=raw,
            request_hash=hashlib.sha256(
                json.dumps(raw, sort_keys=True, default=str).encode()
            ).hexdigest(),
            input_version=version if isinstance(version, str) else "",
            content_hash=None,
            settings=DEFAULT_SETTINGS.as_dict(),
            reasons=[Reason(code=ReasonCode.SCHEMA_INVALID, message=message)],
            error=None,
            result=None,
            timing={},
            warnings=[],
        )
        write_record(record, self.runs_dir)
        return record

    def get_run(self, run_id: str) -> dict:
        record = read_run(run_id, self.runs_dir)
        return {"error": f"run {run_id!r} not found"} if record is None else run_view(record)

    def compare(self, run_id_a: str, run_id_b: str) -> dict:
        a, b = read_run(run_id_a, self.runs_dir), read_run(run_id_b, self.runs_dir)
        missing = [i for i, r in ((run_id_a, a), (run_id_b, b)) if r is None]
        if missing:
            return {"error": f"run {missing[0]!r} not found"}
        try:
            return compare_runs(a, b).model_dump(mode="json")
        except CompareError as err:
            return {"error": str(err)}
