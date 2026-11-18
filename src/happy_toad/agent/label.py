"""The label of an answer: CHECKED, NOT CHECKED or NO NUMBERS TO CHECK (SPEC, M3 decision 10)."""

NO_FIGURES = "NO NUMBERS TO CHECK"


def verdict(t) -> str | None:
    """The label of a transcript's final report; None when there is no final report to show.

    CHECKED needs a verified claim or number; an answer with neither is NO NUMBERS TO CHECK.
    """
    if t.report is None or t.status not in ("checked", "unverified"):
        return None
    if t.status != "checked":
        return "NOT CHECKED"
    last = t.checks[-1]
    return NO_FIGURES if not last.claims and not last.numbers else "CHECKED"
