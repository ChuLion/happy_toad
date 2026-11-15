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


def call_args(name: str, raw: str) -> str:
    try:
        args = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return "(unreadable arguments)"
    if not isinstance(args, dict):
        return "(unreadable arguments)"
    if name == "run_scenario":
        return _scenario_args(args)
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
        problems = len(result.get("errors") or []) or 1
        return "accepted" if result.get("accepted") else f"refused ({problems} problems)"
    if name in ("run_scenario", "get_run") and "run_id" in result:
        return _run_outcome(result)
    if result.get("error"):
        return f"error: {result['error']}"
    if name == "list_input_versions":
        return ", ".join(result.get("versions", []))
    if name == "compare_runs":
        return _compare_outcome(result)
    return "ok"


def correction(t) -> str | None:
    """What the first submit_report got wrong, when it was refused and a later one accepted."""
    submits = [c for turn in t.turns for c in turn.tool_calls if c["name"] == "submit_report"]
    if t.status != "checked" or len(submits) < 2 or submits[0]["result"].get("accepted"):
        return None
    if "errors" not in submits[0]["result"]:
        return "First report refused, then corrected: it did not fit the report schema"
    first = t.checks[0]
    parts = []
    if numbers := [n.text for n in first.numbers if not n.ok]:
        parts.append("unmatched numbers " + ", ".join(numbers))
    if claims := [f"{c.claim.metric} {c.claim.value}" for c in first.claims if not c.ok]:
        parts.append("mismatched claims " + ", ".join(claims))
    if first.missing:
        parts.append(f"{len(first.missing)} missing minimum-budget claims")
    return "First report refused, then corrected: " + "; ".join(parts)


def check_line(check) -> str:
    """The CLI's count line."""
    errors = len(check.errors())
    matched = sum(n.ok for n in check.numbers)
    mismatches = "1 mismatch" if errors == 1 else f"{errors} mismatches"
    return (
        f"{len(check.claims)} claims, {matched} numbers matched against stored runs, {mismatches}"
    )


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
