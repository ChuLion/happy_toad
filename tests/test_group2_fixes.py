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
