"""Read and write input sets as JSON, running the load-time checks on read."""

from pathlib import Path

from pydantic import ValidationError

from happy_toad.constants import BASE_YEAR
from happy_toad.data.checks import InputError, check_input_set
from happy_toad.data.schemas import InputSet


def save_input_set(data: InputSet, path: Path) -> None:
    """Write an input set to a JSON file."""
    path.write_text(data.model_dump_json(indent=2))


def load_input_set(path: Path, base_year: int = BASE_YEAR) -> InputSet:
    """Read an input set from JSON and validate it; raises InputError if it is malformed or fails
    any check."""
    try:
        data = InputSet.model_validate_json(path.read_text())
    except ValidationError as err:
        raise InputError([f"{path.name} is malformed: {err}"]) from err
    check_input_set(data, base_year)
    return data
