"""Read and write input sets as JSON, running the load-time checks on read."""

from pathlib import Path

from happy_toad.data.checks import DEFAULT_BASE_YEAR, check_input_set
from happy_toad.data.schemas import InputSet


def save_input_set(data: InputSet, path: Path) -> None:
    """Write an input set to a JSON file."""
    path.write_text(data.model_dump_json(indent=2))


def load_input_set(path: Path, base_year: int = DEFAULT_BASE_YEAR) -> InputSet:
    """Read an input set from JSON and validate it; raises InputError if it fails any check."""
    data = InputSet.model_validate_json(path.read_text())
    check_input_set(data, base_year)
    return data
