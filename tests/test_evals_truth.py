"""M4 part B: the case file, the independence of evals/truth.py, and truth against the engine."""

import ast
import importlib.util
import json
from pathlib import Path
from typing import get_args

import pytest

from happy_toad.agent.checker import pair_value, stored_value
from happy_toad.agent.report import Metric
from happy_toad.agent.tools import TOOLS
from happy_toad.data.files import write_inputs
from happy_toad.data.loader import load_input_set
from happy_toad.evals.cases import load_cases
from happy_toad.services.request import SolveRequest
from happy_toad.services.run import run_request
from happy_toad.services.runs import read_run
from happy_toad.services.target import TargetBudgetRequest, run_target

ROOT = Path(__file__).parents[1]
TRUTH_PY = ROOT / "evals/truth.py"
TRUTH_JSON = ROOT / "evals/truth.json"
LABELS = {"CHECKED", "NOT CHECKED", "NO NUMBERS TO CHECK"}
TOLERANCE = 1e-6
RUN_METRICS = {
    "status", "spend", "weighted_relief", "n_selected", "n_resolved", "pct_resolved",
    "target_met", "required_minimum_budget", "target_budget", "target_sectors",
    "max_resolvable", "max_pct_resolvable",
}  # fmt: skip


def load_truth_module():
    spec = importlib.util.spec_from_file_location("truth", TRUTH_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def inputs(tmp_path_factory):
    folder = tmp_path_factory.mktemp("inputs")
    write_inputs(42, folder)
    return folder


@pytest.fixture(scope="module")
def truth():
    return json.loads(TRUTH_JSON.read_text())


# --- the case file -----------------------------------------------------------------------------


def test_there_are_19_cases_numbered_1_to_19():
    assert [c.id for c in load_cases()] == list(range(1, 20))


def test_cases_name_known_tools_labels_and_metrics():
    tools = {t["function"]["name"] for t in TOOLS}
    metrics = set(get_args(Metric))
    for case in load_cases():
        assert {c.tool for c in case.required_calls} <= tools, case.id
        assert set(case.forbidden_calls) <= tools, case.id
        assert set(case.allowed_labels) <= LABELS and case.allowed_labels, case.id
        assert {k.metric for k in case.key_numbers} <= metrics, case.id


def test_cases_refer_only_to_their_own_runs():
    for case in load_cases():
        n = len(case.runs)
        refs = [c.run for c in case.required_calls if c.run is not None]
        refs += [i for k in case.key_numbers for i in k.run_indexes()]
        refs += [r.force_in["selected_at"] for r in case.runs if isinstance(r.force_in, dict)]
        refs += [i for pair in case.extra_pairs for i in pair]
        assert all(0 <= i < n for i in refs), case.id


# --- independence ------------------------------------------------------------------------------


def banned_imports(source: str) -> list[str]:
    """Modules imported from happy_toad.engine or happy_toad.services."""
    found = []
    for node in ast.walk(ast.parse(source)):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        found += [n for n in names if n.startswith(("happy_toad.engine", "happy_toad.services"))]
    return found


def test_the_ban_detects_engine_and_services_imports():
    assert banned_imports("import happy_toad.engine.model") == ["happy_toad.engine.model"]
    assert banned_imports("from happy_toad.services.run import x") == ["happy_toad.services.run"]
    assert banned_imports("import json\nfrom happy_toad.data import x") == []


def test_truth_py_imports_nothing_from_the_engine_or_the_services():
    assert banned_imports(TRUTH_PY.read_text()) == []


# --- truth.json --------------------------------------------------------------------------------


def test_truth_json_is_for_generated_v1_and_v2_seed_42(inputs, truth):
    for version in ("v1", "v2"):
        data = load_input_set(inputs / f"{version}.json")
        assert truth["inputs"][version] == data.content_hash


def test_truth_py_reproduces_the_committed_truth_json(inputs, truth):
    computed = load_truth_module().compute(inputs, ROOT / "src/happy_toad/evals/cases.json")
    assert computed["cases"] == truth["cases"]


# --- truth against the engine ------------------------------------------------------------------


def engine_record(spec, earlier, inputs, runs):
    """Run one case run spec through the services, resolving selected_at from earlier runs."""
    fields = spec.model_dump(exclude={"kind"}, exclude_none=True)
    if isinstance(spec.force_in, dict):
        fields["force_in"] = earlier[spec.force_in["selected_at"]].result.selected
    if spec.kind == "target_budget":
        fields.pop("budget", None)
        return run_target(TargetBudgetRequest(**fields), inputs, runs)
    return run_request(SolveRequest(**fields), inputs, runs)


def same(engine, true) -> bool:
    if isinstance(true, float) and isinstance(engine, int | float) and not isinstance(engine, bool):
        return abs(engine - true) <= TOLERANCE
    return engine == true


def disagreements(case, case_truth, inputs, runs) -> list[str]:
    """Every engine value that differs from truth, as readable lines."""
    found, records = [], []
    for i, spec in enumerate(case.runs):
        record = engine_record(spec, records, inputs, runs)
        records.append(record)
        true = case_truth["runs"][i]
        sides = [(record, true, f"run {i}")]
        if record.follow_up_run_id:
            follow = read_run(record.follow_up_run_id, runs)
            sides.append((follow, true["follow_up"], f"run {i} follow-up"))
        for rec, tr, where in sides:
            if rec.outcome != tr["outcome"]:
                found.append(f"{where}: outcome {rec.outcome} != {tr['outcome']}")
            codes = sorted(r.code for r in rec.reasons)
            if codes != tr["reasons"]:
                found.append(f"{where}: reasons {codes} != {tr['reasons']}")
            selected = rec.result.selected if rec.result else None
            if selected != tr["selected"]:
                found.append(f"{where}: selected {selected} != {tr['selected']}")
            for metric, value in tr["values"].items():
                got = stored_value(rec, metric)
                if not same(got, value):
                    found.append(f"{where}: {metric} {got} != {value}")
            for metric in RUN_METRICS - set(tr["values"]):
                if stored_value(rec, metric) is not None:
                    found.append(f"{where}: {metric} {stored_value(rec, metric)} missing in truth")
    for pair, values in case_truth.get("diffs", {}).items():
        a, b = (int(x) for x in pair.split(","))
        for metric, value in values.items():
            got = pair_value(records[a], records[b].run_id, metric, runs)
            if not same(got, value):
                found.append(f"diff {pair}: {metric} {got} != {value}")
    return found


def test_the_engine_agrees_with_truth_on_every_case(inputs, truth, tmp_path):
    problems = []
    for case in load_cases():
        problems += [
            f"case {case.id}, {line}"
            for line in disagreements(case, truth["cases"][str(case.id)], inputs, tmp_path)
        ]
    assert problems == []
