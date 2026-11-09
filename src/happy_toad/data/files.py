"""Write the generated input files to disk."""

import json
from pathlib import Path

from happy_toad.data.evolve import make_v2
from happy_toad.data.generator import make_v1
from happy_toad.data.loader import save_input_set


def write_inputs(seed: int, out_dir: Path) -> None:
    """Write v1.json, v2.json and changes_v1_to_v2.json to out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    v1 = make_v1(seed)
    v2, changes = make_v2(v1, seed)
    save_input_set(v1, out_dir / "v1.json")
    save_input_set(v2, out_dir / "v2.json")
    (out_dir / "changes_v1_to_v2.json").write_text(json.dumps(changes, indent=2, sort_keys=True))
