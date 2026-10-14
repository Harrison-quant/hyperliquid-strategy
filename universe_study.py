"""
universe_study.py - out-of-universe test of the frozen v2 signal, then v3 portfolio.

Part A: run v2 UNCHANGED on 10 coins never used in development, one coin at a
        time and as a 10-coin portfolio. Compare with simply holding each coin
        at the same vol target. Pre-holdout period (Binance prices).
Part B: same 10 coins over the holdout year (HL prices + funding). These coins'
        holdout was never looked at, though the market regime was.
Part C: v3 = v2 signal + strategy-level sizing on all 13 coins vs 3 coins.

Caveat: survivorship bias. These are coins that are still large today; coins
that trended down to zero aren't in the list. Long/flat should be hurt less by
this than buy-and-hold, but it flatters both.

Run: python universe_study.py
"""
import sys
from pathlib import Path

import pandas as pd

import backtest as bt
import holdout as ho

if len(sys.argv) > 1:
    bt.DATA = ho.DATA = Path(sys.argv[1])
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent / "results"
LBS, BAND = (10, 20, 40, 60, 120, 240), (0.25, 0.02)
ORIG = ["BTC", "ETH", "SOL"]
NEW = ["XRP", "DOGE", "BNB", "ADA", "LINK", "AVAX", "LTC", "BCH", "DOT", "TRX"]


def set_coins(coins):
    bt.COINS = {c: f"{c}USDT" for c in coins}


def trend_and_hold(closes, rets, funding, band=BAND):
    base = bt.base_weights(rets, 20)
    tr = bt.run(closes, rets, funding, LBS, base, True, band)
    hold = bt.run_target(rets, funding, base.clip(upper=bt.MAX_LEV).fillna(0), band)
    return tr, hold


def main():
    OUT.mkdir(exist_ok=True)
    lines = []

    # ---- Part A: per coin, pre-holdout
    lines.append("PART A: frozen v2 on 10 new coins, pre-holdout (Binance), from 2019 or first full year")
    lines.append("coin   start        trend Sharpe  trend MaxDD   hold Sharpe  hold MaxDD")
    wins_sr, wins_dd, pos = 0, 0, 0
    for c in NEW:
        set_coins([c])
        closes, rets, funding = bt.load()
        tr, hold = trend_and_hold(closes, rets, funding)
        start = max(pd.Timestamp("2019-01-01", tz="UTC"), closes.index[0] + pd.Timedelta(days=365))
        a, b = bt.stats(tr[0].loc[start:]), bt.stats(hold[0].loc[start:])
        wins_sr += a["Sharpe"] > b["Sharpe"]; wins_dd += a["MaxDD"] > b["MaxDD"]; pos += a["Sharpe"] > 0
        lines.append(f"{c:5}  {start:%Y-%m-%d}   {a['Sharpe']:8.2f}    {a['MaxDD']:8.1%}    {b['Sharpe']:8.2f}   {b['MaxDD']:8.1%}")
    lines.append(f"Trend Sharpe > 0 on {pos}/10 coins; beats holding on Sharpe {wins_sr}/10, on drawdown {wins_dd}/10")

    set_coins(NEW)
    closes, rets, funding = bt.load()
    tr, hold = trend_and_hold(closes, rets, funding)
    per = slice("2019-01-01", None)
    lines.append("\n10-coin portfolio, 2019 to holdout:")
    lines.append(bt.fmt("Trend v2, new coins only", bt.stats(tr[0].loc[per], tr[1])))
    lines.append(bt.fmt("Always-long, new coins only", bt.stats(hold[0].loc[per])))

    # ---- Part B: holdout year on HL data
    ho.bt.COINS = bt.COINS
    hc, hr, hf = ho.load_hl()
    trh, holdh = trend_and_hold(hc, hr, hf)
    idx = hc.index[hc.index >= bt.HOLDOUT_START][1:]
    lines.append(f"\nPART B: same 10 coins, holdout {idx[0]:%Y-%m-%d} to {idx[-1]:%Y-%m-%d} (HL prices + funding)")
    lines.append(bt.fmt("Trend v2, new coins", bt.stats(trh[0].loc[idx])))
    lines.append(bt.fmt("Always-long, new coins", bt.stats(holdh[0].loc[idx])))

    # ---- Part C: v3 portfolios
    lines.append("\nPART C: v3 (v2 signal + strategy-level sizing, 30% target), 2019 to holdout")
    for name, coins in (("3 coins (BTC/ETH/SOL)", ORIG), ("13 coins", ORIG + NEW)):
        set_coins(coins)
        closes, rets, funding = bt.load()
        base = bt.base_weights(rets, 20)
        tgt = bt.make_target(closes, LBS, base, True)
        t3, k = bt.scale_to_target(rets, funding, tgt, BAND)
        pnl, to, held = bt.run_target(rets, funding, t3, BAND)
        lines.append(bt.fmt(f"v3 {name}", bt.stats(pnl.loc[per], to)))
        g = held.loc[per].abs().sum(axis=1)
        lines.append(f"      gross {g.mean():.2f}x avg / {g.max():.2f}x max, scaler {k.loc[per].mean():.2f} avg")
        for y in range(2019, 2026):
            s = bt.stats(pnl.loc[str(y)])
            lines.append(f"      {y}  {s['CAGR']:7.1%}  Sharpe {s['Sharpe']:5.2f}  MaxDD {s['MaxDD']:6.1%}")

    report = "\n".join(lines)
    (OUT / "universe_study.txt").write_text(report)
    print(report)


if __name__ == "__main__":
    main()
