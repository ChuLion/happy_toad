"""M4 fix group 2 (docs/SPEC.md, M4 part D): prompt, tool text, gate message, n_unresolved."""

from agent_helpers import make_run, toy_dirs

from happy_toad.agent.checker import check_report
from happy_toad.agent.prompt import SYSTEM_PROMPT
from happy_toad.agent.report import Report


def report(summary: str, *claims: dict) -> Report:
    return Report(summary=summary, claims=list(claims))


def status_claim(record) -> dict:
    status = record.result.status if record.result else record.outcome
    return dict(metric="status", value=status, run_id=record.run_id)


# --- (f) rejected against infeasible ---------------------------------------------------------


def test_the_prompt_separates_rejected_from_infeasible():
    assert "A request the gate refuses is rejected" in SYSTEM_PROMPT
    assert "Never call a rejected request infeasible" in SYSTEM_PROMPT


def test_infeasible_for_a_rejected_run_is_refused(tmp_path):
    toy_dirs(tmp_path)
    run = make_run(tmp_path, budget=12.0, force_in=["Z9"])  # rejected by the gate
    r = report("The scenario is infeasible.", status_claim(run))
    result = check_report(r, tmp_path / "runs", tmp_path / "inputs", [run.run_id])
    assert not result.ok and "rejected" in " ".join(result.errors())
    ok = report("The scenario was rejected.", status_claim(run))
    assert check_report(ok, tmp_path / "runs", tmp_path / "inputs", [run.run_id]).ok


def test_infeasible_is_fine_when_a_cited_run_is_infeasible(tmp_path):
    from happy_toad.services.request import SolveRequest
    from happy_toad.services.run import run_request

    inputs, runs = toy_dirs(tmp_path)
    infeasible = run_request(
        SolveRequest(input_version="test", budget=12.0, market_floor_mult=3.0), inputs, runs
    )
    assert infeasible.result.status == "Infeasible"
    r = report("The scenario is infeasible.", status_claim(infeasible))
    assert check_report(r, runs, inputs, [infeasible.run_id]).ok


# --- (g) rule 12 wording ---------------------------------------------------------------------


def test_rule_12_makes_the_caveat_its_own_sentence_and_requires_the_offer():
    rule = SYSTEM_PROMPT[SYSTEM_PROMPT.index("12. ") :]
    assert "as its own sentence, not as the conclusion of another" in rule
    assert 'End with the offer: "I can run the optimizer at other budgets you name."' in rule


# --- (h) decimals ----------------------------------------------------------------------------


def test_rule_7_gives_rounding_examples():
    rule = SYSTEM_PROMPT[SYSTEM_PROMPT.index("7. ") : SYSTEM_PROMPT.index("8. ")]
    assert "41.25% is written 41.3%" in rule
    assert "1573.567 is written 1573.57" in rule


# --- (i) target_pct_resolved is report-only ---------------------------------------------------


def test_run_scenario_describes_the_target_as_report_only():
    from happy_toad.agent.tools import TOOLS

    spec = next(t["function"] for t in TOOLS if t["function"]["name"] == "run_scenario")
    assert "target_pct_resolved only reports" in spec["description"]
    field = spec["parameters"]["properties"]["target_pct_resolved"]
    assert "does not change the plan" in field["description"]


def test_the_field_description_does_not_change_the_request_hash():
    from happy_toad.services.request import SolveRequest, request_hash

    r = SolveRequest(input_version="v1", budget=1400, target_pct_resolved=50)
    assert request_hash(r) == request_hash(SolveRequest.model_validate(r.model_dump()))
    assert "description" not in str(r.model_dump())


# --- (j) default version ---------------------------------------------------------------------


def test_the_prompt_defaults_to_v1_and_says_so():
    assert "If the user names no input version, use v1, the plan of record" in SYSTEM_PROMPT
    assert "say in the answer that you used v1" in SYSTEM_PROMPT


def test_case_10_now_expects_a_v1_run_at_1000():
    import json
    from pathlib import Path

    from happy_toad.evals.cases import load_cases

    case = next(c for c in load_cases() if c.id == 10)
    assert case.runs[0].input_version == "v1" and case.runs[0].budget == 1000
    assert [(c.tool, c.run) for c in case.required_calls] == [("run_scenario", 0)]
    assert case.allowed_labels == ["CHECKED"] and case.forbidden_calls == []
    truth = json.loads((Path(__file__).parents[1] / "evals/truth.json").read_text())
    assert truth["cases"]["10"]["runs"][0]["values"]["spend"] > 0


# --- (l) the gate names a change list --------------------------------------------------------


def test_the_gate_says_a_change_list_is_not_an_input_version(tmp_path):
    from happy_toad.reasons import ReasonCode
    from happy_toad.services.request import SolveRequest
    from happy_toad.services.run import run_request
    from happy_toad.services.target import TargetBudgetRequest, run_target

    inputs, runs = toy_dirs(tmp_path)
    for record in (
        run_request(SolveRequest(input_version="changes_v1_to_v2", budget=10.0), inputs, runs),
        run_target(
            TargetBudgetRequest(input_version="changes_v1_to_v2", target_pct_resolved=50),
            inputs,
            runs,
        ),
    ):
        assert [r.code for r in record.reasons] == [ReasonCode.VERSION_NOT_FOUND]
        assert (
            record.reasons[0].message == "changes_v1_to_v2 is a change list, not an input version"
        )


def test_an_unknown_version_keeps_its_message(tmp_path):
    from happy_toad.services.request import SolveRequest
    from happy_toad.services.run import run_request

    inputs, runs = toy_dirs(tmp_path)
    record = run_request(SolveRequest(input_version="v9", budget=10.0), inputs, runs)
    assert record.reasons[0].message == "no input version 'v9'"


# --- (m) n_unresolved and the sector count ----------------------------------------------------


def test_n_unresolved_is_claimable(tmp_path):
    toy_dirs(tmp_path)
    run = make_run(tmp_path, budget=12.0)
    left = run.result.total_sectors - run.result.resolved
    claim = dict(metric="n_unresolved", value=left, run_id=run.run_id)
    r = report(f"{left} sectors remained unresolved.", claim)
    assert check_report(r, tmp_path / "runs", tmp_path / "inputs", [run.run_id]).ok
    wrong = dict(metric="n_unresolved", value=left + 1, run_id=run.run_id)
    assert not check_report(report("", wrong), tmp_path / "runs", tmp_path / "inputs").ok


def test_the_prompt_asks_for_n_sectors_whenever_of_n_sectors_is_written():
    assert 'Whenever you write "of N sectors", also claim n_sectors for N' in SYSTEM_PROMPT
    assert "n_unresolved" in SYSTEM_PROMPT


def test_truth_has_the_unresolved_count_of_case_13():
    import json
    from pathlib import Path

    truth = json.loads((Path(__file__).parents[1] / "evals/truth.json").read_text())
    assert truth["cases"]["13"]["runs"][0]["values"]["n_unresolved"] == 38  # 80 - 42
