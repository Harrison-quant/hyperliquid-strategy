"""
v2_study.py - does fixing the trade threshold help? Pre-holdout data only.

The one change in v2: v1 only traded when a weight moved by 10% of capital,
which blocked most entries because positions are often smaller than that.
v2 trades when the change exceeds a fraction of the CURRENT position (rel),
with a small floor (mn) to skip dust trades.

Pre-registered choice (fixed BEFORE running): rel = 0.25, mn = 0.02.
The grid of other values is only a robustness check, not a menu to pick from.

Everything else is frozen from v1: long/flat, lookbacks (10..240), vol window 20,
30% vol target, 2x cap. The holdout is spent and is NOT used here.

Run: python v2_study.py
"""
import sys
from pathlib import Path

import pandas as pd

import backtest as bt

if len(sys.argv) > 1:
    bt.DATA = Path(sys.argv[1])
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent / "results"
LBS = (10, 20, 40, 60, 120, 240)
V2 = (0.25, 0.02)


def main():
    OUT.mkdir(exist_ok=True)
    closes, rets, funding = bt.load()
    base = bt.base_weights(rets, 20)
    period = slice("2019-01-01", None)

    def go(band):
        pnl, to, held = bt.run(closes, rets, funding, LBS, base, True, band)
        return pnl.loc[period], to.loc[period], held.loc[period]

    runs = {
        "v1 (absolute 10% threshold)": go(None),
        "v2 (25% of position, 2% floor)": go(V2),
        "No threshold (trade every day)": go((0.0, 0.0)),
    }
    always = bt.run_target(rets, funding, base.clip(upper=bt.MAX_LEV).fillna(0), V2)[0].loc[period]

    lines = ["PRE-HOLDOUT 2019-01-01 to 2025-10-13, Binance prices, costs + funding included", ""]
    for name, (pnl, to, held) in runs.items():
        lines.append(bt.fmt(name, bt.stats(pnl, to)))
        yrs = len(pnl) / 365
        lines.append(f"      gross exposure {held.abs().sum(axis=1).mean():.2f}x, "
                     f"invested {(held.abs().sum(axis=1) > 0.01).mean():.0%} of days, "
                     f"trades/yr {(to > 0).sum() / yrs:.0f}, "
                     f"fee+slip drag {to.sum() * (bt.FEE + bt.SLIP) / yrs:.2%}/yr")
    lines.append(bt.fmt("Always-long basket, same vol targeting", bt.stats(always)))

    lines.append("\nRobustness grid, v2 Sharpe (rows rel, cols floor). Want a flat plateau:")
    floors = (0.01, 0.02, 0.05)
    lines.append("   rel   " + "  ".join(f"mn={m:.2f}" for m in floors))
    for rel in (0.10, 0.25, 0.50):
        row = [bt.stats(go((rel, m))[0])["Sharpe"] for m in floors]
        lines.append(f"  {rel:4.2f}   " + "  ".join(f"{x:7.2f}" for x in row))

    lines.append("\nBy year (CAGR / Sharpe):   v1                v2                always-long")
    v1, v2 = runs["v1 (absolute 10% threshold)"][0], runs["v2 (25% of position, 2% floor)"][0]
    for y in range(2019, 2026):
        cells = [bt.stats(x.loc[str(y)]) for x in (v1, v2, always)]
        lines.append(f"  {y}                    " + "   ".join(f"{c['CAGR']:6.1%} / {c['Sharpe']:5.2f}" for c in cells))

    # spread of Sharpe across the v1 search variants, used to penalise for multiple testing
    from itertools import product
    srs = []
    for (lbs), vw, lo in product(bt.LOOKBACK_SETS.values(), bt.VOL_WINS, (False, True)):
        r = bt.run(closes, rets, funding, lbs, bt.base_weights(rets, vw), lo)[0].loc[period]
        srs.append(r.mean() / r.std())
    n_trials = 16 + 9 + 2  # v1 search + this grid + holdout/no-threshold runs
    lines.append(f"\nDeflated Sharpe prob for v2 (counting {n_trials} variants tried so far): "
                 f"{bt.deflated_sharpe(v2, n_trials, pd.Series(srs).var()):.2f}")

    report = "\n".join(lines)
    (OUT / "v2_study.txt").write_text(report)
    print(report)


if __name__ == "__main__":
    main()
