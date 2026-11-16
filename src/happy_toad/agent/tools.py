"""The six tools: their descriptions (SPEC, M3 and M2B) and the code behind five of them.

`submit_report` is handled by the loop, because accepting it ends the conversation.
"""

import json
from pathlib import Path

from pydantic import ValidationError

from happy_toad.agent.report import Report
from happy_toad.services.request import SolveRequest
from happy_toad.services.run import RunRecord, record_invalid_request, run_request
from happy_toad.services.runs import (
    CompareError,
    compare_runs,
    list_change_lists,
    list_versions,
    read_run,
)
from happy_toad.services.target import TargetBudgetRequest, run_target

TOP_UNRESOLVED = 5
SEARCH_FIELDS = {"target_budget", "target_sectors", "max_resolvable", "max_pct_resolvable"}
CLARIFY_SENTENCE = (
    "To ask a clarifying question or decline, call submit_report with claims as an empty list "
    "and a summary that contains no numbers."
)


def _tool(name: str, description: str, parameters: dict) -> dict:
    spec = {"name": name, "description": description, "parameters": parameters}
    return {"type": "function", "function": spec}


def _object(properties: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": properties, "required": required}


_RUN_ID = {"type": "string", "description": "A run id returned by run_scenario."}

TOOLS = [
    _tool(
        "list_input_versions",
        "List the names of the available input versions (synthetic data sets) in `versions`, and "
        "the change lists in `change_lists`: a change list records the edits between two "
        "versions; it is not a version and cannot be run. Call this when the user does not name "
        "a version or you are unsure what exists.",
        _object({}, []),
    ),
    _tool(
        "run_scenario",
        "Run the optimizer once for one scenario and record it. `budget` is the TOTAL budget "
        "including must-fund projects. `force_in` and `force_out` are candidate ids (for example "
        "C033). Returns the run id and a summary: status, weighted relief (`objective`), spend "
        "(candidates only), selected candidates, sectors resolved, percent resolved, unresolved "
        "sectors, and, when infeasible, the cause and `required_minimum_budget` (the budget must "
        "be at least that). target_pct_resolved only reports whether the plan resolves at least "
        "that percent (target_met); it does not change the plan. Pass it when the user asks "
        "whether a plan reaches a percent. Never guess a budget; ask the user.",
        SolveRequest.model_json_schema(),
    ),
    _tool(
        "find_target_budget",
        "Find the cheapest plan that resolves at least `target_pct_resolved` percent of sectors "
        "and the total budget it needs, including must-fund projects (`target_budget`). Also runs "
        "the optimizer at that budget (`follow_up_run_id`, `follow_up`): its usual plan maximizes "
        "weighted relief and can resolve fewer sectors. Returns `target_sectors` (the target as a "
        "sector count) and `max_resolvable`; an unreachable target has no budget. No budget and "
        "no market multipliers in the request.",
        TargetBudgetRequest.model_json_schema(),
    ),
    _tool(
        "get_run",
        "Return the stored summary of an earlier run by its run id.",
        _object({"run_id": _RUN_ID}, ["run_id"]),
    ),
    _tool(
        "compare_runs",
        "Compare two completed runs that both have a plan: status, spend, weighted relief, "
        "number selected, number resolved, percent resolved, which candidates are only in one "
        "run, and how many (n_only_in_b added, claim as n_added; n_only_in_a dropped, claim as "
        "n_dropped). Use it for a comparison instead of computing differences yourself.",
        _object({"run_id_a": _RUN_ID, "run_id_b": _RUN_ID}, ["run_id_a", "run_id_b"]),
    ),
    _tool(
        "submit_report",
        "Submit the final answer. Every number in `summary` must also be a claim "
        "`{metric, value, unit, run_id, entity}` taken from a run you executed or read, or be a "
        "request value such as the budget. Values at displayed precision. " + CLARIFY_SENTENCE,
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
        hidden = {"solver_settings", "stage_times", "unresolved"}
        if record.kind == "scenario":
            hidden |= SEARCH_FIELDS
        view["result"] = {
            **r.model_dump(mode="json", exclude=hidden),
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
    """Runs the five deterministic tools against the inputs and runs folders."""

    def __init__(self, inputs_dir: Path, runs_dir: Path, transcript_id: str | None = None) -> None:
        self.inputs_dir = inputs_dir
        self.runs_dir = runs_dir
        self.transcript_id = transcript_id  # stored on every run record this runner makes

    def call(self, name: str, arguments: str) -> dict:
        """Run a tool by name with its JSON arguments; every outcome is a dict for the model."""
        try:
            args = json.loads(arguments or "{}")
        except json.JSONDecodeError:
            args = None
        if name in ("run_scenario", "find_target_budget"):
            run = self.run_scenario if name == "run_scenario" else self.find_target_budget
            return run(args if isinstance(args, dict) else {"_raw_arguments": arguments})
        if not isinstance(args, dict):
            return {"error": "arguments are not a JSON object"}
        if name == "list_input_versions":
            return {
                "versions": list_versions(self.inputs_dir),
                "change_lists": list_change_lists(self.inputs_dir),
            }
        if name == "get_run":
            return self.get_run(args.get("run_id", ""))
        if name == "compare_runs":
            return self.compare(args.get("run_id_a", ""), args.get("run_id_b", ""))
        return {"error": f"unknown tool {name!r}"}

    def run_scenario(self, args: dict) -> dict:
        try:
            request = SolveRequest.model_validate(args)
        except ValidationError as err:
            record = record_invalid_request(
                args, _fields_in(err), self.runs_dir, transcript_id=self.transcript_id
            )
            return run_view(record)
        return run_view(
            run_request(request, self.inputs_dir, self.runs_dir, transcript_id=self.transcript_id)
        )

    def find_target_budget(self, args: dict) -> dict:
        try:
            request = TargetBudgetRequest.model_validate(args)
        except ValidationError as err:
            record = record_invalid_request(
                args, _fields_in(err), self.runs_dir, "target_budget", self.transcript_id
            )
            return run_view(record) | {"follow_up_run_id": None}
        record = run_target(
            request, self.inputs_dir, self.runs_dir, transcript_id=self.transcript_id
        )
        view = run_view(record) | {"follow_up_run_id": record.follow_up_run_id}
        if record.follow_up_run_id:
            view["follow_up"] = run_view(read_run(record.follow_up_run_id, self.runs_dir))
        return view

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
