"""docs/GUIDE.md's glossary defines every report metric and every gate or infeasibility code."""

from typing import get_args

from happy_toad.agent.report import Metric
from happy_toad.reasons import ReasonCode
from web.glossary import definitions
from web.page import render_page


def test_every_metric_has_a_glossary_entry():
    assert set(get_args(Metric)) - definitions().keys() == set()


def test_every_reason_code_has_a_glossary_entry():
    assert {c.value for c in ReasonCode} - definitions().keys() == set()


def test_definitions_are_plain_text_with_wrapped_lines_joined():
    spend = definitions()["spend"]
    assert spend.startswith("What the plan spends on candidate solutions, in cost units.")
    assert spend.endswith("though the budget you give does include them.")
    assert "`" not in definitions()["diff_spend"]


def test_the_page_carries_the_definitions():
    assert '"glossary": {"spend": "What the plan spends' in render_page({"mode": "live"})
