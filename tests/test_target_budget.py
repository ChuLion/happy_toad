"""M2B target-budget search on toy data (docs/SPEC.md, "M2B — Target-budget search")."""

import itertools
import json
import math

import pytest
from helpers import make_set
from pydantic import ValidationError

from happy_toad.agent.checker import check_report
from happy_toad.agent.report import Report
from happy_toad.constants import BASE_YEAR
from happy_toad.data.loader import save_input_set
from happy_toad.engine.relief import resolved_count
from happy_toad.engine.target import cheapest_plan, round_up_cent, target_sectors
from happy_toad.reasons import ReasonCode
from happy_toad.services.request import SolveRequest, request_hash
from happy_toad.services.run import RunRecord, run_request
from happy_toad.services.runs import read_run
from happy_toad.services.target import TargetBudgetRequest, run_target, target_hash


def toy(must_fund=()):
    """A resolves sA (cost 5); P relieves 9 of 10 in sP1 and sP2 (cost 5); B resolves sB late.

    Weighted relief: P 18, A 10, B 2 (trigger BASE_YEAR + 4, weight 1/5). So the normal optimizer
    at budget 5 picks P and resolves nothing, while the cheapest plan resolving 1 sector is A.
    """
    return make_set(
        [("sA", 10), ("sP1", 10), ("sP2", 10), ("sB", 10, BASE_YEAR + 4)],
        [("A", 5), ("P", 5), ("B", 5)],
        [("A", "sA", 10), ("P", "sP1", 9), ("P", "sP2", 9), ("B", "sB", 10)],
        must_fund,
    )


@pytest.fixture
def dirs(tmp_path):
    inputs, runs = tmp_path / "inputs", tmp_path / "runs"
    inputs.mkdir()
    save_input_set(toy(), inputs / "test.json")
    save_input_set(toy(must_fund=[1.005]), inputs / "mf.json")
    return inputs, runs


def search(dirs, version="test", **kwargs) -> RunRecord:
    request = TargetBudgetRequest(input_version=version, **kwargs)
    return run_target(request, *dirs)


def brute_force_min_cost(data, k: int, force_in=(), force_out=()) -> float | None:
    """Cheapest candidate set that resolves at least k sectors, by enumerating every subset."""
    free = [c for c in data.candidates if c.id not in force_in and c.id not in force_out]
    best = None
    for n in range(len(free) + 1):
        for subset in itertools.combinations(free, n):
            chosen = {c.id for c in subset} | set(force_in)
            if resolved_count(data, chosen) >= k:
                cost = sum(c.cost for c in data.candidates if c.id in chosen)
                best = cost if best is None else min(best, cost)
    return best


# --- the search itself -------------------------------------------------------------------------


def test_target_sectors_rounds_up():
    assert target_sectors(50, 80) == 40
    assert target_sectors(30, 4) == 2
    assert target_sectors(25, 4) == 1
    assert target_sectors(0, 80) == 0
    assert target_sectors(100, 80) == 80


def test_round_up_cent_ignores_float_noise():
    assert round_up_cent(1145.2100000001) == 1145.21
    assert round_up_cent(1145.211) == 1145.22
    assert round_up_cent(6.005) == 6.01
    assert round_up_cent(5.0) == 5.0


@pytest.mark.parametrize("k", [0, 1, 2])
def test_cheapest_plan_cost_matches_brute_force(k):
    data = toy()
    plan = cheapest_plan(data, k)
    assert plan.status == "Optimal"
    assert plan.cost == brute_force_min_cost(data, k)
    assert resolved_count(data, set(plan.selected)) >= k


def test_ties_at_the_minimum_cost_go_to_the_most_weighted_relief():
    plan = cheapest_plan(toy(), 1)
    assert plan.selected == ["A"]  # A and B both cost 5 and resolve 1; A weighs 1, B weighs 1/5


def test_the_cheapest_plan_differs_from_the_optimizer_plan_at_that_budget(dirs):
    record = search(dirs, target_pct_resolved=25)  # 1 of 4 sectors
    assert record.kind == "target_budget"
    assert record.result.target_sectors == 1
    assert record.result.target_budget == 5.0
    assert record.result.selected == ["A"] and record.result.resolved == 1
    follow_up = read_run(record.follow_up_run_id, dirs[1])
    assert follow_up.kind == "scenario"
    assert follow_up.request["budget"] == 5.0
    assert follow_up.result.selected == ["P"] and follow_up.result.resolved == 0


def test_the_same_request_twice_gives_the_same_plan_and_budget(dirs):
    a, b = (search(dirs, target_pct_resolved=50) for _ in range(2))
    assert (a.result.selected, a.result.target_budget) == (
        b.result.selected,
        b.result.target_budget,
    )
    assert a.run_id != b.run_id


# --- target_budget: total, rounded up to the cent ---------------------------------------------


def test_target_budget_is_rounded_up_and_the_plan_fits_within_it(dirs):
    record = search(dirs, version="mf", target_pct_resolved=25)
    must_fund, budget = 1.005, record.result.target_budget
    cheapest = record.result.spend
    assert budget == 6.01
    assert round(budget, 2) == budget
    assert 0 <= budget - (must_fund + cheapest) < 0.01
    assert cheapest <= budget - must_fund
    assert read_run(record.follow_up_run_id, dirs[1]).request["budget"] == budget


def test_target_zero_needs_only_must_fund_and_forced_cost(dirs):
    assert search(dirs, version="mf", target_pct_resolved=0).result.target_budget == 1.01
    forced = search(dirs, version="mf", target_pct_resolved=0, force_in=["B"])
    assert forced.result.target_budget == 6.01


def test_force_in_adds_its_cost_when_it_is_not_in_the_cheapest_plan(dirs):
    record = search(dirs, target_pct_resolved=25, force_in=["P"])
    assert sorted(record.result.selected) == ["A", "P"]
    assert record.result.target_budget == 10.0


# --- unreachable -------------------------------------------------------------------------------


def test_an_unreachable_target_gives_the_maximum_and_no_budget(dirs):
    record = search(dirs, target_pct_resolved=75)  # 3 of 4; at most 2 (sA, sB) can be resolved
    r = record.result
    assert record.outcome == "completed"
    assert r.status == "Infeasible"
    assert r.cause.code == ReasonCode.TARGET_UNREACHABLE
    assert "at most 2 of 4 sectors" in r.cause.message
    assert (r.target_sectors, r.max_resolvable, r.max_pct_resolvable) == (3, 2, 50.0)
    assert r.target_budget is None and r.selected is None
    assert record.follow_up_run_id is None


def test_force_out_alone_can_make_a_target_unreachable(dirs):
    assert search(dirs, target_pct_resolved=50).result.status == "Optimal"
    record = search(dirs, target_pct_resolved=50, force_out=["A"])
    assert record.result.cause.code == ReasonCode.TARGET_UNREACHABLE
    assert record.result.max_resolvable == 1


def test_a_reachable_search_also_reports_the_maximum(dirs):
    r = search(dirs, target_pct_resolved=25).result
    assert (r.max_resolvable, r.max_pct_resolvable) == (2, 50.0)


# --- request, gate and record ------------------------------------------------------------------


@pytest.mark.parametrize("field", ["market_floor_mult", "market_cap_mult", "budget"])
def test_multipliers_and_budget_are_refused_with_a_message_naming_the_field(field):
    with pytest.raises(ValidationError) as err:
        TargetBudgetRequest(input_version="v1", target_pct_resolved=50, **{field: 1.0})
    text = str(err.value)
    assert f"{field} is not supported in the target-budget search" in text
    if field != "budget":
        assert "scale with the budget being searched for" in text


@pytest.mark.parametrize("bad", [-1, 101])
def test_target_outside_0_to_100_is_refused(bad):
    with pytest.raises(ValidationError):
        TargetBudgetRequest(input_version="v1", target_pct_resolved=bad)


def test_missing_version_is_rejected_and_recorded(dirs):
    record = search(dirs, version="nope", target_pct_resolved=50)
    assert record.outcome == "rejected" and record.kind == "target_budget"
    assert [r.code for r in record.reasons] == [ReasonCode.VERSION_NOT_FOUND]
    assert record.follow_up_run_id is None
    assert read_run(record.run_id, dirs[1]) == record


def test_unknown_candidate_and_force_conflict_are_listed_together(dirs):
    record = search(dirs, target_pct_resolved=50, force_in=["A", "Z9"], force_out=["A"])
    assert record.outcome == "rejected"
    codes = {r.code for r in record.reasons}
    assert codes == {ReasonCode.UNKNOWN_CANDIDATE, ReasonCode.FORCE_CONFLICT}


def test_search_hash_never_equals_a_scenario_hash():
    search_request = TargetBudgetRequest(input_version="v1", target_pct_resolved=50)
    scenario = SolveRequest(input_version="v1", budget=1000, target_pct_resolved=50)
    assert target_hash(search_request) != request_hash(scenario)
    labelled = TargetBudgetRequest(input_version="v1", target_pct_resolved=50, label="x")
    assert target_hash(labelled) == target_hash(search_request)


def test_records_written_before_m2b_still_load(dirs):
    old = run_request(SolveRequest(input_version="test", budget=10), *dirs)
    raw = json.loads(old.model_dump_json())
    raw.pop("kind"), raw.pop("follow_up_run_id")
    for key in ("target_budget", "target_sectors", "max_resolvable", "max_pct_resolvable"):
        raw["result"].pop(key)
    loaded = RunRecord.model_validate(raw)
    assert loaded.kind == "scenario" and loaded.follow_up_run_id is None
    assert loaded.result.target_budget is None


# --- checker -----------------------------------------------------------------------------------

UNITS = dict(
    target_budget="cost_units", target_sectors="count", max_resolvable="count",
    max_pct_resolvable="percent",
)  # fmt: skip


def check(dirs, record, **values):
    claims = [
        dict(metric=m, value=v, unit=UNITS[m], run_id=record.run_id) for m, v in values.items()
    ]
    return check_report(Report(summary="", claims=claims), dirs[1], dirs[0])


def test_new_metrics_pass_when_they_match_the_stored_search(dirs):
    record = search(dirs, version="mf", target_pct_resolved=25)
    result = check(
        dirs, record, target_budget=6.01, target_sectors=1, max_resolvable=2,
        max_pct_resolvable=50.0,
    )  # fmt: skip
    assert result.ok, result


@pytest.mark.parametrize(
    "metric, value",
    [("target_budget", 6.02), ("target_sectors", 2), ("max_resolvable", 1),
     ("max_pct_resolvable", 50.1)],
)  # fmt: skip
def test_new_metrics_fail_when_they_do_not_match(dirs, metric, value):
    record = search(dirs, version="mf", target_pct_resolved=25)
    assert not check(dirs, record, **{metric: value}).ok


def test_target_budget_has_money_tolerance_and_max_pct_has_percent_tolerance(dirs):
    record = search(dirs, version="mf", target_pct_resolved=25)
    assert check(dirs, record, target_budget=6.014).ok
    assert check(dirs, record, max_pct_resolvable=50.05).ok


def test_an_unreachable_search_claims_its_maximum(dirs):
    record = search(dirs, target_pct_resolved=75)
    assert check(dirs, record, max_resolvable=2, max_pct_resolvable=50.0, target_sectors=3).ok
    assert not check(dirs, record, target_budget=5.0).ok  # there is no budget to claim


def test_math_ceil_matches_the_spec_formula():
    assert target_sectors(37.5, 80) == math.ceil(37.5 * 80 / 100 - 1e-9) == 30
