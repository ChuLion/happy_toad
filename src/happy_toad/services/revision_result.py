"""The stored parts of a revision record (docs/SPEC.md, M5): input comparison, steps, totals."""

from pydantic import BaseModel


class InputComparison(BaseModel):
    """What differs between two versions, read from their data (ids sorted)."""

    sectors_added: list[str]
    sectors_removed: list[str]
    triggers_moved: list[str]
    costs_changed: list[str]
    offloads_changed: list[list[str]]
    unsupported: list[str]


class RevisionStep(BaseModel):
    """One step of the ordered attribution; effects are this step minus the previous one."""

    name: str
    applied: list[str]
    n_changes: int
    content_hash: str
    status: str
    objective: float | None
    spend: float | None
    resolved: int | None
    selected: list[str] | None
    effect_relief: float | None = None
    effect_spend: float | None = None
    effect_n_resolved: int | None = None


class RevisionResult(BaseModel):
    """Input changes, the ordered steps and the decision-level totals of one revision."""

    order: list[str]
    order_text: str
    run_id_a: str
    run_id_b: str
    inputs: InputComparison
    steps: list[RevisionStep]
    complete: bool
    total_relief: float | None
    total_spend: float | None
    total_n_resolved: int | None
    n_sectors_shared: int
    n_resolved_shared_a: int | None
    n_resolved_shared_b: int | None
    n_sectors_new: int
    n_resolved_new: int | None
