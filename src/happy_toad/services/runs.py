"""Version lister, run reader and run comparer for the agent tools (SPEC, M3 decision 2)."""

import re
from pathlib import Path

from pydantic import BaseModel, ValidationError

from happy_toad.data.checks import InputError
from happy_toad.data.files import is_change_list
from happy_toad.services.run import RunRecord

RUN_ID = re.compile(r"\d{8}T\d{6}-[0-9a-f]{8}")
COMPARED = ("status", "spend", "weighted_relief", "n_selected", "n_resolved", "pct_resolved")


class CompareError(ValueError):
    """A run cannot be compared."""


class FieldDiff(BaseModel):
    """One compared field; `difference` is b - a for numbers and None otherwise."""

    a: float | int | str | None
    b: float | int | str | None
    difference: float | None


class RunComparison(BaseModel):
    """Differences between two runs that both have a plan."""

    run_id_a: str
    run_id_b: str
    fields: dict[str, FieldDiff]
    only_in_a: list[str]
    only_in_b: list[str]
    n_only_in_a: int  # dropped: chosen in a, not in b (claim as n_dropped)
    n_only_in_b: int  # added: chosen in b, not in a (claim as n_added)


def list_versions(inputs_dir: Path = Path("data/inputs")) -> list[str]:
    """Sorted names of the input versions: the stems of the .json files, except change lists."""
    return sorted(p.stem for p in inputs_dir.glob("*.json") if not is_change_list(p.stem))


def read_run(run_id: str, runs_dir: Path = Path("runs")) -> RunRecord | None:
    """The stored record for a run id, or None if the id is not a run id or has no file.

    Raises InputError if the file is malformed.
    """
    path = runs_dir / f"{run_id}.json"
    if not RUN_ID.fullmatch(run_id) or not path.exists():
        return None
    try:
        return RunRecord.model_validate_json(path.read_text())
    except ValidationError as err:
        raise InputError([f"run record {run_id} is malformed: {err}"]) from err


def metrics(record: RunRecord) -> dict:
    """The comparable values of a run that has a plan."""
    r = record.result
    return {
        "status": r.status,
        "spend": r.spend,
        "weighted_relief": r.objective,
        "n_selected": len(r.selected),
        "n_resolved": r.resolved,
        "pct_resolved": r.pct_resolved,
    }


def compare_runs(a: RunRecord, b: RunRecord) -> RunComparison:
    """Differences in status, spend, relief, resolved counts and selected candidates."""
    for r in (a, b):
        if r.result is None or r.result.selected is None:
            raise CompareError(f"run {r.run_id} has no plan to compare")
    ma, mb = metrics(a), metrics(b)
    fields = {}
    for name in COMPARED:
        numeric = name != "status"
        diff = mb[name] - ma[name] if numeric else None
        fields[name] = FieldDiff(a=ma[name], b=mb[name], difference=diff)
    chosen_a, chosen_b = set(a.result.selected), set(b.result.selected)
    return RunComparison(
        run_id_a=a.run_id,
        run_id_b=b.run_id,
        fields=fields,
        only_in_a=sorted(chosen_a - chosen_b),
        only_in_b=sorted(chosen_b - chosen_a),
        n_only_in_a=len(chosen_a - chosen_b),
        n_only_in_b=len(chosen_b - chosen_a),
    )
