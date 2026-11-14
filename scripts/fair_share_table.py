"""Fair share, floor and cap per market for generated v1 (SPEC "Market floors and caps").

Run: uv run python scripts/fair_share_table.py [seed]
Prints a markdown table at the 30% budget (avail = 30% of total candidate cost).
"""

import sys
from collections import defaultdict

from happy_toad.data.generator import make_v1

BLEND, FLOOR_MULT, CAP_MULT, SHARE = 0.5, 0.5, 1.5, 0.30


def main(seed: int) -> None:
    data = make_v1(seed)
    shortfall: dict[str, float] = defaultdict(float)
    for s in data.sectors:
        shortfall[s.market] += s.shortfall
    markets = sorted(shortfall)
    total = sum(shortfall.values())
    avail = SHARE * sum(c.cost for c in data.candidates)
    print(f"seed {seed}: avail at {SHARE:.0%} budget = {avail:.2f} cost units")
    print(
        "| market | total shortfall | share | fair share | floor % avail | cap % avail "
        "| floor (units) | cap (units) |"
    )
    print("|---|---|---|---|---|---|---|---|")
    for m in markets:
        share = shortfall[m] / total
        fair = BLEND * share + (1 - BLEND) / len(markets)
        floor, cap = FLOOR_MULT * fair, CAP_MULT * fair
        print(
            f"| {m} | {shortfall[m]:.2f} | {share:.1%} | {fair:.1%} | {floor:.1%} | {cap:.1%} "
            f"| {floor * avail:.2f} | {cap * avail:.2f} |"
        )


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 42)
