"""
holdout.py - one-shot test of the frozen v1 strategy on the locked holdout.

Frozen v1: long/flat, lookbacks (10,20,40,60,120,240), 20-day vol window,
30% vol target, 2x cap per coin, 10% trade threshold. Nothing here is tuned.

Uses Hyperliquid's own daily prices and hourly funding (the venue we'd trade),
with HL history before the holdout used only to warm up the indicators.
Results are only counted from HOLDOUT_START onward.

Run: python holdout.py
"""
import sys
from pathlib import Path

import pandas as pd

import backtest as bt

DATA = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "data"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent / "results"
LOOKBACKS = (10, 20, 40, 60, 120, 240)
VOL_WIN = 20


def load_hl():
    closes, funding = {}, {}
    for coin in bt.COINS:
        px = pd.read_csv(DATA / f"{coin}_1d.csv")
        px["time"] = pd.to_datetime(px["time"], format="mixed", utc=True)
        closes[coin] = px.set_index("time")["close"]
        f = pd.read_csv(DATA / f"{coin}_funding.csv")
        f["time"] = pd.to_datetime(f["time"], format="mixed", utc=True)
        funding[coin] = f.set_index("time")["funding_rate"].resample("1D").sum()
    closes = pd.DataFrame(closes)
    funding = pd.DataFrame(funding).reindex(closes.index).fillna(0)
    return closes, closes.pct_change(), funding


def main():
    OUT.mkdir(exist_ok=True)
    closes, rets, funding = load_hl()
    base = bt.base_weights(rets, VOL_WIN)
    h = closes.index >= bt.HOLDOUT_START

    trend, turnover, held = bt.run(closes, rets, funding, LOOKBACKS, base, long_only=True)
    always = bt.run_target(rets, funding, base.clip(upper=bt.MAX_LEV).fillna(0))[0]
    btc = rets["BTC"]

    idx = closes.index[h][1:]  # first holdout day earns on the position set the day before
    lines = [f"HOLDOUT {idx[0]:%Y-%m-%d} to {idx[-1]:%Y-%m-%d} ({len(idx)} days), HL prices + HL funding",
             bt.fmt("Trend v1 long/flat (frozen)", bt.stats(trend.loc[idx], turnover)),
             bt.fmt("Always-long basket, same vol targeting", bt.stats(always.loc[idx])),
             bt.fmt("BTC buy & hold (no funding)", bt.stats(btc.loc[idx])),
             ""]
    pos = held.loc[idx]
    lines.append(f"Avg gross exposure {pos.abs().sum(axis=1).mean():.2f}x, "
                 f"invested {(pos.abs().sum(axis=1) > 0.05).mean():.0%} of days, "
                 f"funding paid {(pos * funding.loc[idx]).sum().sum():.2%}, "
                 f"trades {(turnover.loc[idx] > 0).sum()}")
    lines.append("\nMonthly returns (trend / always-long / BTC):")
    m = pd.DataFrame({"trend": trend.loc[idx], "always": always.loc[idx], "btc": btc.loc[idx]})
    m = (1 + m).resample("ME").prod() - 1
    for t, row in m.iterrows():
        lines.append(f"  {t:%Y-%m}  {row.trend:7.1%}  {row.always:7.1%}  {row.btc:7.1%}")

    report = "\n".join(lines)
    (OUT / "holdout.txt").write_text(report)
    print(report)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(11, 5))
    for name, r in {"Trend v1 long/flat": trend, "Always-long vol-targeted": always, "BTC buy & hold": btc}.items():
        ax.plot((1 + r.loc[idx]).cumprod(), label=name, lw=1.6 if "Trend" in name else 1)
    ax.axhline(1, color="k", lw=0.6)
    ax.set_title("Holdout (never seen during development), HL prices, costs and funding included")
    ax.legend(); ax.grid(alpha=0.3); fig.tight_layout(); fig.savefig(OUT / "holdout.png", dpi=130)


if __name__ == "__main__":
    main()
