"""Display wording copied from happy_toad/cli.py so the view does not import the CLI.

Wording is identical to the CLI.
web/tests/test_format.py compares these functions with the CLI's.
"""

import json

NO_FIGURES = "NO NUMBERS TO CHECK"
NO_FIGURES_LINE = "No checkable figures in this answer"


def _scenario_args(args: dict) -> str:
    parts = [str(args.get("input_version", "?")), f"budget {args.get('budget')}"]
    for key, value in args.items():
        if key in ("input_version", "budget", "label") or value in (None, []):
            continue
        shown = ", ".join(map(str, value)) if isinstance(value, list) else value
        parts.append(f"{key.replace('_', ' ')} {shown}")
    return ", ".join(parts)


def _target_args(args: dict) -> str:
    pct = args.get("target_pct_resolved")
    shown = f"{pct:g}" if isinstance(pct, int | float) else pct
    parts = [str(args.get("input_version", "?")), f"target {shown}%"]
    for key in ("force_in", "force_out"):
        if args.get(key):
            parts.append(f"{key.replace('_', ' ')} {', '.join(map(str, args[key]))}")
    return ", ".join(parts)


def _target_outcome(result: dict) -> str:
    r, run_id = result.get("result") or {}, result.get("run_id")
    if result.get("follow_up_run_id"):
        budget, follow = r["target_budget"], result["follow_up"]
        head = f"target budget {budget:.2f} [{run_id}]; optimizer at {budget:.2f}"
        if (follow.get("result") or {}).get("resolved") is None:  # rejected or no plan
            return f"{head}: {_run_outcome(follow)}"
        plan = follow["result"]
        return (
            f"{head} resolves {plan['resolved']} of {plan['total_sectors']} "
            f"[{result['follow_up_run_id']}]"
        )
    if r.get("status") == "Infeasible" and r.get("max_resolvable") is not None:
        return (
            f"unreachable: at most {r['max_resolvable']} of {r['total_sectors']} sectors "
            f"({r['max_pct_resolvable']:.1f}%) [{run_id}]"
        )
    return _run_outcome(result)


def _revision_args(args: dict) -> str:
    a, b = args.get("plan_of_record", "v1"), args.get("refreshed_forecast", "v2")
    return f"{a} -> {b}, budget {args.get('budget')}"


def _revision_outcome(result: dict) -> str:
    rev, run_id = result.get("revision"), result.get("run_id")
    if rev is None:
        return _run_outcome(result)
    head = f"order {rev['order_text']}"
    if not rev["complete"]:
        return f"{head}: attribution incomplete [{run_id}]"
    effects = ", ".join(
        f"{s['name']} {s['effect_relief']:+.2f}"
        for s in rev["steps"]
        if s["name"] != "plan_of_record"
    )
    return f"{head}: relief effects {effects}; total {rev['total_relief']:+.2f} [{run_id}]"


def call_args(name: str, raw: str) -> str:
    try:
        args = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return "(unreadable arguments)"
    if not isinstance(args, dict):
        return "(unreadable arguments)"
    if name == "run_scenario":
        return _scenario_args(args)
    if name == "find_target_budget":
        return _target_args(args)
    if name == "explain_revision":
        return _revision_args(args)
    if name == "submit_report":
        return f"{len(args.get('claims') or [])} claims"
    return " ".join(f"{v}" for v in args.values())


def _run_outcome(result: dict) -> str:
    r = result.get("result")
    if result.get("outcome") == "completed" and r is not None and r.get("spend") is not None:
        text = f"{r['status']}, spend {r['spend']:.2f}, weighted relief {r['objective']:.2f}"
    else:
        codes = " ".join(x["code"] for x in result.get("reasons") or [])
        status = r["status"] if r else result.get("outcome")
        text = " ".join(filter(None, [status, codes, result.get("error")]))
    if result.get("required_minimum_budget") is not None:
        text += f", minimum budget {result['required_minimum_budget']}"
    return f"{text} [{result.get('run_id')}]"


def _compare_outcome(result: dict) -> str:
    fields = result.get("fields", {})
    diffs = [
        f"{name.replace('_', ' ')} {f['difference']:+.2f}"
        for name, f in fields.items()
        if name in ("spend", "weighted_relief") and f.get("difference") is not None
    ]
    return "compared: " + (", ".join(diffs) or "no plan differences")


def call_outcome(name: str, result: dict) -> str:
    if name == "submit_report":
        n = len(result.get("errors") or []) or 1
        problems = "1 problem" if n == 1 else f"{n} problems"
        return "accepted" if result.get("accepted") else f"refused ({problems})"
    if name == "find_target_budget" and "run_id" in result:
        return _target_outcome(result)
    if name == "explain_revision" and "run_id" in result:
        return _revision_outcome(result)
    if name in ("run_scenario", "get_run") and "run_id" in result:
        return _run_outcome(result)
    if result.get("error"):
        return f"error: {result['error']}"
    if name == "list_input_versions":
        text = ", ".join(result.get("versions", []))
        lists = result.get("change_lists")
        return f"{text}; change lists: {', '.join(lists)}" if lists else text
    if name == "compare_runs":
        return _compare_outcome(result)
    return "ok"


def correction(t) -> str | None:
    """How a checked answer got there when earlier reports were refused.

    A failed check uses the one correction; a report that did not fit the schema does not.
    """
    submits = [c for turn in t.turns for c in turn.tool_calls if c["name"] == "submit_report"]
    if t.status != "checked" or len(submits) < 2 or submits[0]["result"].get("accepted"):
        return None
    parts = []
    if len(t.checks) > 1:
        first = t.checks[0]
        problems = []
        if numbers := [n.text for n in first.numbers if not n.ok]:
            problems.append("unmatched numbers " + ", ".join(numbers))
        if claims := [f"{c.claim.metric} {c.claim.value}" for c in first.claims if not c.ok]:
            problems.append("mismatched claims " + ", ".join(claims))
        if first.missing:
            problems.append(f"{len(first.missing)} missing minimum-budget claims")
        parts.append("Failed the check once, then corrected: " + "; ".join(problems))
    schema = sum(
        str(c["result"].get("error", "")).startswith("report does not fit the schema")
        for c in submits
    )
    if schema:
        reports = "1 report" if schema == 1 else f"{schema} reports"
        parts.append(
            f"{reports} did not fit the schema and {'was' if schema == 1 else 'were'} "
            "resent (no correction used)"
        )
    return "; ".join(parts) or None


def check_line(check) -> str:
    """The CLI's count line."""
    errors = len(check.errors())
    matched = sum(n.ok for n in check.numbers)
    mismatches = "1 mismatch" if errors == 1 else f"{errors} mismatches"
    claims = "1 claim" if len(check.claims) == 1 else f"{len(check.claims)} claims"
    return f"{claims} | {matched} numbers checked | {mismatches}"


def verdict(t) -> str | None:
    """The one verdict for both outputs and the exit code; None when there is no report to show.

    CHECKED needs a verified claim or number; an answer with neither is NO NUMBERS TO CHECK.
    """
    if t.report is None or t.status not in ("checked", "unverified"):
        return None
    if t.status != "checked":
        return "NOT CHECKED"
    last = t.checks[-1]
    return NO_FIGURES if not last.claims and not last.numbers else "CHECKED"


def no_report_line(t) -> str:
    """The CLI's line when there is no report: status and detail."""
    detail = t.error or (f"HTTP {t.api_error['status']}" if t.api_error else None)
    return f"Status: {t.status}" + (f" ({detail})" if detail else "")
