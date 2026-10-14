"""
v3_sizing.py - does strategy-level vol targeting deliver the risk we ask for?

Pre-registered (fixed before running): 365-day window, scaler capped at 3x,
per-coin cap 2x. Other windows/caps shown only as a robustness check.
Pre-holdout data only, original 3 coins, v2 signal and trade band unchanged.

Run: python v3_sizing.py
"""
import sys
from pathlib import Path

import backtest as bt

if len(sys.argv) > 1:
    bt.DATA = Path(sys.argv[1])
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent / "results"
LBS, BAND = (10, 20, 40, 60, 120, 240), (0.25, 0.02)


def main():
    OUT.mkdir(exist_ok=True)
    closes, rets, funding = bt.load()
    base = bt.base_weights(rets, 20)
    tgt = bt.make_target(closes, LBS, base, True)
    per = slice("2019-01-01", None)

    lines = ["PRE-HOLDOUT 2019-01-01 to 2025-10-13, BTC/ETH/SOL, target vol 30%", ""]
    v2, to2, h2 = bt.run_target(rets, funding, tgt, BAND)
    lines.append(bt.fmt("v2 (no strategy-level scaling)", bt.stats(v2.loc[per], to2)))
    lines.append(f"      gross exposure {h2.loc[per].abs().sum(axis=1).mean():.2f}x avg, "
                 f"{h2.loc[per].abs().sum(axis=1).max():.2f}x max")

    tgt3, k = bt.scale_to_target(rets, funding, tgt, BAND)
    v3, to3, h3 = bt.run_target(rets, funding, tgt3, BAND)
    lines.append(bt.fmt("v3 (365d window, 3x cap)", bt.stats(v3.loc[per], to3)))
    g = h3.loc[per].abs().sum(axis=1)
    lines.append(f"      gross exposure {g.mean():.2f}x avg, {g.max():.2f}x max, "
                 f"scaler {k.loc[per].mean():.2f} avg, at cap {(k.loc[per] >= 2.999).mean():.0%} of days, "
                 f"per-coin cap hit {(h3.loc[per].abs() >= bt.MAX_LEV - 1e-9).any(axis=1).mean():.0%} of days")
    rv = v3.loc[per].rolling(365).std() * 365 ** 0.5
    lines.append(f"      rolling 1y realised vol: min {rv.min():.0%}, median {rv.median():.0%}, max {rv.max():.0%}")

    lines.append("\nRobustness (Sharpe / Vol / MaxDD):")
    for win in (180, 365, 730):
        for cap in (2.0, 3.0, 4.0):
            t, _ = bt.scale_to_target(rets, funding, tgt, BAND, win, cap)
            s = bt.stats(bt.run_target(rets, funding, t, BAND)[0].loc[per])
            lines.append(f"  window {win:3}d cap {cap:.0f}x   {s['Sharpe']:5.2f} / {s['Vol']:5.1%} / {s['MaxDD']:6.1%}")

    lines.append("\nBy year (CAGR / Vol / MaxDD), v3:")
    for y in range(2019, 2026):
        s = bt.stats(v3.loc[str(y)])
        lines.append(f"  {y}   {s['CAGR']:7.1%} / {s['Vol']:5.1%} / {s['MaxDD']:6.1%}")

    report = "\n".join(lines)
    (OUT / "v3_sizing.txt").write_text(report)
    print(report)


if __name__ == "__main__":
    main()
