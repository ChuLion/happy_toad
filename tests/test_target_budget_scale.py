"""M2B target-budget search on generated v1 (seed 42), against the committed sweep fixture."""

import json
from pathlib import Path

import pytest

from happy_toad.data.generator import make_v1
from happy_toad.data.loader import save_input_set
from happy_toad.engine.target import target_sectors
from happy_toad.services.target import TargetBudgetRequest, run_target

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/v1_first_budget_per_target.json").read_text()
)
TARGETS = [int(p) for p in FIXTURE["first_budget_by_target_pct"]]


@pytest.fixture(scope="module")
def searches(tmp_path_factory):
    root = tmp_path_factory.mktemp("v1")
    (root / "inputs").mkdir()
    data = make_v1(seed=42)
    assert data.content_hash == FIXTURE["content_hash"]
    save_input_set(data, root / "inputs" / "v1.json")
    return {
        p: run_target(
            TargetBudgetRequest(input_version="v1", target_pct_resolved=p),
            root / "inputs",
            root / "runs",
        )
        for p in TARGETS
    }


def test_every_target_up_to_95_percent_is_found(searches):
    assert all(r.result.status == "Optimal" for r in searches.values())


def test_target_budget_never_decreases_as_the_target_rises(searches):
    budgets = [searches[p].result.target_budget for p in TARGETS]
    assert budgets == sorted(budgets)


def test_target_budget_is_never_above_the_optimizers_first_budget(searches):
    first = FIXTURE["first_budget_by_target_pct"]
    for p in TARGETS:
        assert searches[p].result.target_budget <= first[str(p)], p


def test_the_cheapest_plan_resolves_at_least_the_target(searches):
    for p in TARGETS:
        k = target_sectors(p, FIXTURE["n_sectors"])
        assert searches[p].result.target_sectors == k
        assert searches[p].result.resolved >= k
