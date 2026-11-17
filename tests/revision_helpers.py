"""The M5 toy pair (docs/SPEC.md, M5 tests): plan of record "a", refreshed forecast "b"."""

from helpers import make_set

from happy_toad.constants import BASE_YEAR
from happy_toad.data.loader import save_input_set

BUDGET = 6.0


def toy_a():
    return make_set(
        [("s1", 10), ("s2", 10)],
        [("A", 6), ("B", 6)],
        [("A", "s1", 10), ("B", "s2", 8)],
    ).model_copy(update={"version_id": "a"})


def toy_b():
    return make_set(
        [("s1", 10), ("s2", 10, BASE_YEAR + 1), ("s3", 4)],
        [("A", 7), ("B", 6)],
        [("A", "s1", 10), ("B", "s2", 10), ("B", "s3", 4)],
    ).model_copy(update={"version_id": "b"})


def toy_dirs(tmp_path, a=None, b=None):
    """inputs/ holding a.json and b.json; returns (inputs_dir, runs_dir)."""
    inputs, runs = tmp_path / "inputs", tmp_path / "runs"
    inputs.mkdir(exist_ok=True)
    save_input_set(a or toy_a(), inputs / "a.json")
    save_input_set(b or toy_b(), inputs / "b.json")
    return inputs, runs
