"""Ground truth for the M4 cases, computed from the SPEC without the engine's code.

Reads the input JSON files and cases.json as data and builds its own PuLP models. It must not
import happy_toad.engine or happy_toad.services (tests/test_evals_truth.py enforces this), so a
coding bug in the engine shows up as a disagreement. A SPEC error would be shared by both.

Usage: uv run python evals/truth.py --inputs data/inputs --out evals/truth.json
       uv run python evals/truth.py --inputs data/inputs --revision  (M5: evals/revision_truth.json)
"""

import argparse
import json
import math
import re
import subprocess
from pathlib import Path

import pulp
from pulp.constants import LpSolveStatus

BASE_YEAR = 2027  # SPEC: planning window 2027-2031, weight 1 / (trigger year - 2026)
CAP_FACTOR = 1.5  # SPEC: the gate rejects budgets above 1.5 x (candidate cost + must-fund)
RESOLVED_TOLERANCE = 1e-6  # SPEC: a sector is resolved when relief >= shortfall - 1e-6
RELIEF_SLACK = 1e-5  # SPEC: stage 2 keeps weighted relief within delta / 10, delta = 1e-4
COST_SLACK = 1e-6  # SPEC M2B: stage 2 of the search keeps the cheapest cost within 1e-6
BLEND = 0.5  # SPEC: fair share = half by shortfall share, half equal split
TIME_LIMIT = 30
VERSION_NAME = re.compile(r"[A-Za-z0-9_-]+")
CASES = Path(__file__).parents[1] / "src/happy_toad/evals/cases.json"
NOTE = (
    "Ground truth for the M4 cases. Computed by evals/truth.py from the input JSON files and "
    "cases.json with its own PuLP models (CBC, one thread, gaps 0), written from docs/SPEC.md "
    "without the engine's code; compared with the engine by tests/test_evals_truth.py. Values are "
    "unrounded; selected ids are in candidate order. Inputs: generated v1 and v2, seed 42."
)


# --- data --------------------------------------------------------------------------------------


def load_version(name: str, inputs: Path) -> dict | None:
    """The input set, or None when there is no such version (a change list is not a version)."""
    path = inputs / f"{name}.json"
    if not VERSION_NAME.fullmatch(name) or name.startswith("changes_") or not path.exists():
        return None
    return json.loads(path.read_text())


def must_fund(data: dict) -> float:
    return sum(m["cost"] for m in data["must_fund"])


def cost_of(data: dict, ids) -> float:
    return sum(c["cost"] for c in data["candidates"] if c["id"] in ids)


def supply(data: dict, chosen: set[str]) -> dict[str, float]:
    out = {s["id"]: 0.0 for s in data["sectors"]}
    for o in data["offloads"]:
        if o["candidate_id"] in chosen:
            out[o["sector_id"]] += o["amount"]
    return out


def weights(data: dict) -> dict[str, float]:
    return {s["id"]: 1 / (s["trigger_year"] - BASE_YEAR + 1) for s in data["sectors"]}


def plan_values(data: dict, chosen: list[str]) -> dict:
    """Spend, weighted relief, counts and percent of one plan, from the data alone."""
    have, weight = supply(data, set(chosen)), weights(data)
    relief = {s["id"]: min(s["shortfall"], have[s["id"]]) for s in data["sectors"]}
    resolved = sum(relief[s["id"]] >= s["shortfall"] - RESOLVED_TOLERANCE for s in data["sectors"])
    return {
        "spend": cost_of(data, set(chosen)),
        "weighted_relief": sum(weight[k] * v for k, v in relief.items()),
        "n_selected": len(chosen),
        "n_resolved": resolved,
        "n_unresolved": len(data["sectors"]) - resolved,
        "pct_resolved": 100 * resolved / len(data["sectors"]),
    }


# --- gate --------------------------------------------------------------------------------------


def gate(spec: dict, data: dict | None) -> list[str]:
    """Reason codes for a scenario request, sorted; empty when it may run."""
    if data is None:
        return ["VERSION_NOT_FOUND"]
    codes, budget = [], spec["budget"]
    if not budget > 0:
        codes.append("BUDGET_NOT_POSITIVE")
    elif budget > CAP_FACTOR * (
        cost_of(data, {c["id"] for c in data["candidates"]}) + must_fund(data)
    ):
        codes.append("BUDGET_ABOVE_CAP")
    known = {c["id"] for c in data["candidates"]}
    forced_in, forced_out = set(spec["force_in"]), set(spec["force_out"])
    if (forced_in | forced_out) - known:
        codes.append("UNKNOWN_CANDIDATE")
    if forced_in & forced_out:
        codes.append("FORCE_CONFLICT")
    if must_fund(data) + cost_of(data, forced_in) > budget:
        codes.append("FORCED_COST_EXCEEDS_BUDGET")
    return sorted(codes)


# --- market floors -----------------------------------------------------------------------------


def candidate_market(data: dict) -> dict[str, str]:
    """A candidate's market: that of its largest offload row, ties to the lowest sector id."""
    market = {s["id"]: s["market"] for s in data["sectors"]}
    best: dict[str, tuple] = {}
    for o in data["offloads"]:
        key = (-o["amount"], o["sector_id"])
        if o["candidate_id"] not in best or key < best[o["candidate_id"]]:
            best[o["candidate_id"]] = key
    return {cid: market[sid] for cid, (_, sid) in best.items()}


def floors(data: dict, avail: float, mult: float) -> dict[str, float]:
    """mult x fair share x available budget, clamped to what the market's candidates cost."""
    need: dict[str, float] = {}
    for s in data["sectors"]:
        need[s["market"]] = need.get(s["market"], 0.0) + s["shortfall"]
    total, n = sum(need.values()), len(need)
    of = candidate_market(data)
    market_cost: dict[str, float] = {}
    for c in data["candidates"]:
        if c["id"] in of:
            market_cost[of[c["id"]]] = market_cost.get(of[c["id"]], 0.0) + c["cost"]
    raw = {m: mult * (BLEND * v / total + (1 - BLEND) / n) * avail for m, v in need.items()}
    return {m: min(f, market_cost.get(m, 0.0)) for m, f in raw.items()}


# --- models ------------------------------------------------------------------------------------


def variables(prob, data: dict):
    x = prob.add_variable_dicts("x", [c["id"] for c in data["candidates"]], cat="Binary")
    r = prob.add_variable_dicts("r", [s["id"] for s in data["sectors"]], lowBound=0)
    for s in data["sectors"]:
        have = pulp.lpSum(
            o["amount"] * x[o["candidate_id"]]
            for o in data["offloads"]
            if o["sector_id"] == s["id"]
        )
        prob.add(r[s["id"]] <= s["shortfall"])
        prob.add(r[s["id"]] <= have)
    return x, r


def fix(prob, x, spec: dict, forced_in) -> None:
    for cid in forced_in:
        prob.add(x[cid] == 1)
    for cid in spec["force_out"]:
        prob.add(x[cid] == 0)


def solve(prob, limit: float) -> bool:
    """True when CBC proved an optimum (with gaps 0, a gap-limit stop is a proven optimum)."""
    stats = prob.solve(pulp.COIN_CMD(msg=False, threads=1, timeLimit=limit, gapRel=0, gapAbs=0))
    return stats.has_solution and stats.status in (LpSolveStatus.Optimal, LpSolveStatus.GapLimit)


def chosen(data: dict, x) -> list[str]:
    return [c["id"] for c in data["candidates"] if x[c["id"]].value() > 0.5]


def optimize(data: dict, spec: dict, forced_in: list[str]) -> tuple[str, list[str] | None]:
    """Stage 1 most weighted relief, stage 2 least spend keeping it; (status, selection)."""
    avail = spec["budget"] - must_fund(data)
    limits = floors(data, avail, spec["market_floor_mult"]) if spec.get("market_floor_mult") else {}
    weight, of = weights(data), candidate_market(data)

    def model(sense):
        prob = pulp.LpProblem("truth", sense)
        x, r = variables(prob, data)
        prob.add(pulp.lpSum(c["cost"] * x[c["id"]] for c in data["candidates"]) <= avail)
        for m, amount in limits.items():
            members = [c for c in data["candidates"] if of.get(c["id"]) == m]
            if members:
                prob.add(pulp.lpSum(c["cost"] * x[c["id"]] for c in members) >= amount)
        fix(prob, x, spec, forced_in)
        return prob, x, r

    prob1, x1, r1 = model(pulp.LpMaximize)
    prob1.objective = pulp.lpSum(weight[s] * r1[s] for s in r1)
    if not solve(prob1, TIME_LIMIT):
        return "Infeasible", None
    best = plan_values(data, chosen(data, x1))["weighted_relief"]
    prob2, x2, r2 = model(pulp.LpMinimize)
    prob2.objective = pulp.lpSum(c["cost"] * x2[c["id"]] for c in data["candidates"])
    prob2.add(pulp.lpSum(weight[s] * r2[s] for s in r2) >= best - RELIEF_SLACK)
    solve(prob2, TIME_LIMIT)
    return "Optimal", chosen(data, x2)


def cheapest(data: dict, spec: dict, k: int) -> list[str]:
    """M2B: least candidate cost resolving at least k sectors; ties to the most weighted relief."""
    weight = weights(data)

    def model(sense):
        prob = pulp.LpProblem("cheapest", sense)
        x, r = variables(prob, data)
        z = prob.add_variable_dicts("z", [s["id"] for s in data["sectors"]], cat="Binary")
        for s in data["sectors"]:
            have = pulp.lpSum(
                o["amount"] * x[o["candidate_id"]]
                for o in data["offloads"]
                if o["sector_id"] == s["id"]
            )
            prob.add(have >= (s["shortfall"] - RESOLVED_TOLERANCE) * z[s["id"]])
        prob.add(pulp.lpSum(z.values()) >= k)
        fix(prob, x, spec, spec["force_in"])
        return prob, x, r

    prob1, x1, _ = model(pulp.LpMinimize)
    prob1.objective = pulp.lpSum(c["cost"] * x1[c["id"]] for c in data["candidates"])
    solve(prob1, TIME_LIMIT)
    least = cost_of(data, set(chosen(data, x1)))
    prob2, x2, r2 = model(pulp.LpMaximize)
    prob2.objective = pulp.lpSum(weight[s] * r2[s] for s in r2)
    prob2.add(pulp.lpSum(c["cost"] * x2[c["id"]] for c in data["candidates"]) <= least + COST_SLACK)
    solve(prob2, TIME_LIMIT)
    return chosen(data, x2)


# --- runs --------------------------------------------------------------------------------------


def scenario(spec: dict, data: dict | None, forced_in: list[str]) -> dict:
    spec = {"force_out": [], "market_floor_mult": None, **spec, "force_in": forced_in}
    codes = gate(spec, data)
    if codes:
        minimum = None
        if "FORCED_COST_EXCEEDS_BUDGET" in codes:
            minimum = must_fund(data) + cost_of(data, set(forced_in))
        values = {"status": "rejected"} | ({"required_minimum_budget": minimum} if minimum else {})
        return {"outcome": "rejected", "reasons": codes, "selected": None, "values": values}
    status, selected = optimize(data, spec, forced_in)
    values = {"status": status}
    if selected is not None:
        values |= plan_values(data, selected)
        if spec.get("target_pct_resolved") is not None:
            values["target_met"] = values["pct_resolved"] >= spec["target_pct_resolved"]
    return {"outcome": "completed", "reasons": [], "selected": selected, "values": values}


def search(spec: dict, data: dict) -> dict:
    """M2B target-budget search with its follow-up optimizer run."""
    spec = {"force_in": [], "force_out": [], **spec}
    n = len(data["sectors"])
    k = math.ceil(spec["target_pct_resolved"] * n / 100 - 1e-9)
    open_ids = {c["id"] for c in data["candidates"]} - set(spec["force_out"])
    have = supply(data, open_ids)
    most = sum(have[s["id"]] >= s["shortfall"] - RESOLVED_TOLERANCE for s in data["sectors"])
    values = {
        "target_sectors": k,
        "max_resolvable": most,
        "max_pct_resolvable": 100 * most / n,
    }
    if k > most:
        values |= {"status": "Infeasible", "target_met": False}
        return {"outcome": "completed", "reasons": [], "selected": None, "values": values}
    selected = cheapest(data, spec, k)
    budget = math.ceil(round((must_fund(data) + cost_of(data, set(selected))) * 100, 6)) / 100
    values |= {"status": "Optimal", "target_budget": budget} | plan_values(data, selected)
    values["target_met"] = values["n_resolved"] >= k
    follow_spec = {"budget": budget, "force_out": spec["force_out"]}
    follow = scenario(follow_spec, data, spec["force_in"])
    return {"outcome": "completed", "reasons": [], "selected": selected, "values": values,
            "follow_up": follow}  # fmt: skip


DIFFS = ("spend", "weighted_relief", "n_selected", "n_resolved", "pct_resolved")


def case_truth(case: dict, inputs: Path) -> dict:
    runs = []
    for spec in case.get("runs", []):
        data = load_version(spec["input_version"], inputs)
        forced_in = spec.get("force_in", [])
        if isinstance(forced_in, dict):
            forced_in = runs[forced_in["selected_at"]]["selected"]
        kind = spec.get("kind", "scenario")
        runs.append(
            search(spec, data) if kind == "target_budget" else scenario(spec, data, forced_in)
        )
    pairs = [tuple(p) for p in case.get("extra_pairs", [])]
    if any(c["tool"] == "compare_runs" for c in case.get("required_calls", [])):
        pairs.insert(0, (0, 1))
    diffs = {}
    for a, b in pairs:
        first, second = runs[a]["values"], runs[b]["values"]
        diffs[f"{a},{b}"] = {f"diff_{m}": second[m] - first[m] for m in DIFFS}
        chosen_a, chosen_b = set(runs[a]["selected"]), set(runs[b]["selected"])
        diffs[f"{a},{b}"] |= {
            "n_added": len(chosen_b - chosen_a),
            "n_dropped": len(chosen_a - chosen_b),
        }
    return {"runs": runs} | ({"diffs": diffs} if diffs else {})


def compute(inputs: Path, cases_path: Path = CASES) -> dict:
    cases = json.loads(cases_path.read_text())["cases"]
    hashes = {
        v: json.loads((inputs / f"{v}.json").read_text())["content_hash"] for v in ("v1", "v2")
    }
    return {
        "note": NOTE,
        "inputs": hashes,
        "cases": {str(c["id"]): case_truth(c, inputs) for c in cases},
    }


# --- M5 revision -------------------------------------------------------------------------------

REVISION_CASES = Path(__file__).parents[1] / "src/happy_toad/evals/revision_cases.json"
KINDS = ("costs", "offloads", "triggers", "sectors")  # SPEC M5: the attribution order
REVISION_NOTE = (
    "Ground truth for the M5 revision cases, computed by evals/truth.py with its own step "
    "construction and PuLP models, from docs/SPEC.md without the engine's code; compared with "
    "the engine by tests/test_revision_evals.py. Inputs: generated v1 and v2, seed 42."
)


def _by_id(items: list[dict]) -> dict[str, dict]:
    return {x["id"]: x for x in items}


def changes(a: dict, b: dict) -> dict[str, list]:
    """SPEC 5.1 from the data: ids per change kind (rows only on shared sectors)."""
    sa, sb = _by_id(a["sectors"]), _by_id(b["sectors"])
    shared = sa.keys() & sb.keys()
    ca, cb = _by_id(a["candidates"]), _by_id(b["candidates"])

    def rows(d):
        return {(o["candidate_id"], o["sector_id"]): o["amount"] for o in d["offloads"]
                if o["sector_id"] in shared}  # fmt: skip

    ra, rb = rows(a), rows(b)
    return {
        "sectors_added": sorted(sb.keys() - sa.keys()),
        "sectors_removed": sorted(sa.keys() - sb.keys()),
        "triggers_moved": sorted(
            s for s in shared if sa[s]["trigger_year"] != sb[s]["trigger_year"]
        ),
        "costs_changed": sorted(c for c in ca if ca[c]["cost"] != cb[c]["cost"]),
        "offloads_changed": sorted(k for k in ra.keys() | rb.keys() if ra.get(k) != rb.get(k)),
    }


def step_data(a: dict, b: dict, kinds) -> dict:
    """SPEC 5.3: a with the named kinds taken from b."""
    sb = _by_id(b["sectors"])
    shared = {s["id"] for s in a["sectors"]} & sb.keys()
    cost = {c["id"]: c["cost"] for c in b["candidates"]}
    candidates = [c | {"cost": cost[c["id"]]} if "costs" in kinds else c for c in a["candidates"]]
    sectors = [
        s | {"trigger_year": sb[s["id"]]["trigger_year"]}
        if "triggers" in kinds and s["id"] in shared else s
        for s in a["sectors"]
    ]  # fmt: skip
    source = b if "offloads" in kinds else a
    offloads = [o for o in source["offloads"] if o["sector_id"] in shared]
    rest = b if "sectors" in kinds else a
    offloads += [o for o in rest["offloads"] if o["sector_id"] not in shared]
    if "sectors" in kinds:
        sectors = [s for s in sectors if s["id"] in shared]
        sectors += [s for s in b["sectors"] if s["id"] not in shared]
    return {"sectors": sectors, "candidates": candidates, "offloads": offloads,
            "must_fund": a["must_fund"]}  # fmt: skip


def _resolved_ids(data: dict, chosen: list[str]) -> set[str]:
    have = supply(data, set(chosen))
    return {
        s["id"] for s in data["sectors"] if have[s["id"]] >= s["shortfall"] - RESOLVED_TOLERANCE
    }


def revision(a: dict, b: dict, budget: float) -> dict:
    """The ordered attribution at one budget: selections, effects, totals and counts."""
    steps = []
    for i in range(len(KINDS) + 1):
        data = step_data(a, b, KINDS[:i])
        status, selected = optimize(data, {"budget": budget, "force_out": []}, [])
        steps.append((status, selected, plan_values(data, selected)))
    found = changes(a, b)
    complete = all(status == "Optimal" for status, _, _ in steps)
    values = {f"n_{k}": len(v) for k, v in found.items()}
    keys = {"relief": "weighted_relief", "spend": "spend", "n_resolved": "n_resolved"}
    for kind, (prev, step) in zip(KINDS, zip(steps, steps[1:], strict=False), strict=True):
        for name, key in keys.items():
            values[f"effect_{name}:{kind}"] = step[2][key] - prev[2][key]
    for name, key in keys.items():
        values[f"total_{name}"] = steps[-1][2][key] - steps[0][2][key]
    shared = {s["id"] for s in a["sectors"]} & {s["id"] for s in b["sectors"]}
    new = set(found["sectors_added"])
    values |= {
        "n_sectors_shared": len(shared),
        "n_resolved_shared_a": len(_resolved_ids(a, steps[0][1]) & shared),
        "n_resolved_shared_b": len(_resolved_ids(b, steps[-1][1]) & shared),
        "n_sectors_new": len(new),
        "n_resolved_new": len(_resolved_ids(b, steps[-1][1]) & new),
    }
    return {
        "complete": complete,
        "selected": [selected for _, selected, _ in steps],
        "effect_relief": [values[f"effect_relief:{k}"] for k in KINDS],
        "total_relief": values["total_relief"],
        "values": values,
    }


def compute_revision(inputs: Path, cases_path: Path = REVISION_CASES) -> dict:
    """Truth for the revision cases: one attribution per budget the cases use."""
    cases = json.loads(cases_path.read_text())["cases"]
    budgets = {}
    for case in cases:
        for spec in case.get("runs", []):
            a = load_version(spec.get("plan_of_record") or "v1", inputs)
            b = load_version(spec["input_version"], inputs)
            key = str(int(spec["budget"]))
            if key not in budgets:
                budgets[key] = revision(a, b, spec["budget"])
    hashes = {
        v: json.loads((inputs / f"{v}.json").read_text())["content_hash"] for v in ("v1", "v2")
    }
    return {
        "note": REVISION_NOTE,
        "inputs": hashes,
        "budgets": budgets,
        "cases": {
            str(c["id"]): {
                "runs": [
                    {"values": budgets[str(int(s["budget"]))]["values"]} for s in c.get("runs", [])
                ]
            }
            for c in cases
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=Path("data/inputs"))
    parser.add_argument("--out", type=Path, default=Path("evals/truth.json"))
    parser.add_argument("--revision", action="store_true", help="M5: write revision truth only")
    args = parser.parse_args()
    if args.revision:
        out = Path("evals/revision_truth.json")
        out.write_text(json.dumps(compute_revision(args.inputs), indent=1) + "\n")
        print(f"Wrote revision truth to {out}")
        return
    truth = compute(args.inputs)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    truth["commit"] = sha
    args.out.write_text(json.dumps(truth, indent=1) + "\n")
    print(f"Wrote {len(truth['cases'])} cases to {args.out}")


if __name__ == "__main__":
    main()
