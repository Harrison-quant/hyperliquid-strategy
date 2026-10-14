"""
backtest.py - v1 trend-following backtest with walk-forward validation.

Plain-English summary
---------------------
1. Signal: for each coin, look back over several windows (e.g. 20/60/120 days).
   Each window votes +1 if price is up over that window, -1 if down. The signal
   is the average vote, so it ranges from -1 (all windows down) to +1 (all up).
   Long/flat mode turns negative votes into 0 (sit in cash instead of shorting).
2. Sizing: volatility targeting. Each coin gets weight inversely proportional
   to its recent volatility, then the whole basket is scaled so the fully
   invested portfolio would run at ~30%/yr volatility, using recent correlations.
   Per-coin exposure is capped at 2x.
3. Trading: decide at the daily close, hold from the next day. Only trade a coin
   if its target weight moves more than 10% of capital (saves fees).
4. Costs: Hyperliquid taker fee + slippage on every trade, and funding every day.
   Real HL funding is used from May 2023; before that, longs are charged a flat
   13%/yr (HL's average) and shorts receive nothing (conservative).
5. Walk-forward: for each test year, choose settings using ONLY data before that
   year, then record how those settings did in the unseen year. Stitching the
   unseen years together gives the out-of-sample (OOS) result.
6. Holdout: everything from HOLDOUT_START onward is never touched here.

Run: python backtest.py            (expects a data/ folder next to this file)
"""
import sys
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

DATA = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "data"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent / "results"

COINS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}
HOLDOUT_START = pd.Timestamp("2025-10-14", tz="UTC")   # locked, do not test on this
TEST_YEARS = range(2019, 2026)                         # walk-forward test years

TARGET_VOL = 0.30
MAX_LEV = 2.0
FEE = 0.00045            # HL base-tier taker fee per side
SLIP = 0.0003            # assumed slippage per side for majors
THRESH = 0.10            # minimum weight change before trading
PRE_HL_FUNDING = 0.13 / 365
COV_WIN = 60

LOOKBACK_SETS = {
    "fast (10,20,40)": (10, 20, 40),
    "med (20,60,120)": (20, 60, 120),
    "slow (60,120,240)": (60, 120, 240),
    "all (10..240)": (10, 20, 40, 60, 120, 240),
}
VOL_WINS = (20, 60)


# ---------------------------------------------------------------- data
def load():
    closes, funding = {}, {}
    for coin, sym in COINS.items():
        px = pd.read_csv(DATA / f"binance_{sym}_1d.csv")
        px["time"] = pd.to_datetime(px["time"], format="mixed", utc=True)
        closes[coin] = px.set_index("time")["close"]

        f = pd.read_csv(DATA / f"{coin}_funding.csv")
        f["time"] = pd.to_datetime(f["time"], format="mixed", utc=True)
        funding[coin] = f.set_index("time")["funding_rate"].resample("1D").sum()

    closes = pd.DataFrame(closes)
    closes = closes[closes.index < HOLDOUT_START]
    funding = pd.DataFrame(funding).reindex(closes.index)
    hl_start = funding.first_valid_index()
    funding.loc[funding.index >= hl_start] = funding.loc[funding.index >= hl_start].fillna(0)
    return closes, closes.pct_change(), funding


# ---------------------------------------------------------------- strategy
def base_weights(rets, vol_win):
    """Fully-invested risk-parity weights scaled to TARGET_VOL using rolling covariance."""
    vol = rets.rolling(vol_win, min_periods=vol_win).std() * np.sqrt(365)
    inv = 1 / vol
    cov = rets.rolling(COV_WIN, min_periods=COV_WIN).cov()
    out = pd.DataFrame(np.nan, index=rets.index, columns=rets.columns)
    for t in rets.index:
        w = inv.loc[t].dropna()
        if w.empty or t not in cov.index.get_level_values(0):
            continue
        c = cov.loc[t].loc[w.index, w.index]
        if c.isna().any().any():
            continue
        w = w / len(w)
        pvol = np.sqrt(w.values @ c.values @ w.values * 365)
        out.loc[t, w.index] = w * TARGET_VOL / pvol
    return out


def signal(closes, lookbacks):
    votes = [np.sign(closes / closes.shift(L) - 1) for L in lookbacks]
    return sum(votes) / len(votes)


def make_target(closes, lookbacks, base, long_only):
    sig = signal(closes, lookbacks)
    if long_only:
        sig = sig.clip(lower=0)
    return (sig * base).clip(-MAX_LEV, MAX_LEV).fillna(0)


def run(closes, rets, funding, lookbacks, base, long_only, band=None):
    return run_target(rets, funding, make_target(closes, lookbacks, base, long_only), band)


def scale_to_target(rets, funding, target, band, win=365, cap=3.0):
    """v3 sizing: measure the strategy's own realised vol over the past `win` days
    and scale all positions so it runs at TARGET_VOL. Uses only past returns.
    The scaler is capped so a quiet patch can't lever up tiny leftover positions."""
    pnl0 = run_target(rets, funding, target, band)[0]
    rv = pnl0.rolling(win, min_periods=win // 2).std() * np.sqrt(365)
    k = (TARGET_VOL / rv).clip(upper=cap).fillna(1.0)
    return target.mul(k, axis=0).clip(-MAX_LEV, MAX_LEV), k


def run_target(rets, funding, target, band=None):
    """Simulate trading towards a target-weight table, day by day.

    band=None      -> v1 rule: trade only if the weight change exceeds THRESH (absolute).
    band=(rel, mn) -> v2 rule: trade if the change exceeds rel x current position size,
                      with a small floor mn so tiny dust trades are skipped.
    """
    idx, cols = rets.index, rets.columns
    pos = np.zeros(len(cols))
    pnl = np.zeros(len(idx))
    turnover = np.zeros(len(idx))
    held = np.zeros((len(idx), len(cols)))
    r = rets.fillna(0).values
    f = funding.values
    tgt = target.values
    for i in range(1, len(idx)):
        # 1) earn today's return and pay today's funding on yesterday's position
        fund = np.where(np.isnan(f[i]), np.maximum(pos, 0) * PRE_HL_FUNDING, pos * np.nan_to_num(f[i]))
        pnl[i] = pos @ r[i] - fund.sum()
        held[i] = pos
        # 2) at today's close, trade towards target if the change is big enough
        change = tgt[i] - pos
        limit = THRESH if band is None else np.maximum(band[1], band[0] * np.abs(pos))
        trade = np.where(np.abs(change) > limit, change, 0)
        pos = pos + trade
        cost = np.abs(trade).sum() * (FEE + SLIP)
        pnl[i] -= cost
        turnover[i] = np.abs(trade).sum()
    return pd.Series(pnl, idx), pd.Series(turnover, idx), pd.DataFrame(held, idx, cols)


# ---------------------------------------------------------------- metrics
def stats(r, turnover=None):
    r = r.dropna()
    eq = (1 + r).cumprod()
    yrs = len(r) / 365
    out = {
        "CAGR": eq.iloc[-1] ** (1 / yrs) - 1,
        "Vol": r.std() * np.sqrt(365),
        "Sharpe": r.mean() / r.std() * np.sqrt(365),
        "MaxDD": (eq / eq.cummax() - 1).min(),
    }
    out["Calmar"] = out["CAGR"] / -out["MaxDD"]
    if turnover is not None:
        out["Turnover/yr"] = turnover.loc[r.index].sum() / yrs
    return out


def deflated_sharpe(r, n_trials, sr_var):
    """Probability the true Sharpe > 0 after penalising for how many variants were tried."""
    r = r.dropna()
    sr = r.mean() / r.std()
    g = 0.5772156649
    sr0 = np.sqrt(sr_var) * ((1 - g) * norm.ppf(1 - 1 / n_trials) + g * norm.ppf(1 - 1 / (n_trials * np.e)))
    sk, ku = r.skew(), r.kurt() + 3
    z = (sr - sr0) * np.sqrt(len(r) - 1) / np.sqrt(1 - sk * sr + (ku - 1) / 4 * sr ** 2)
    return norm.cdf(z)


# ---------------------------------------------------------------- main
def main():
    OUT.mkdir(exist_ok=True)
    closes, rets, funding = load()
    bases = {v: base_weights(rets, v) for v in VOL_WINS}

    # every variant on the full pre-holdout period (used for selection + overfit checks)
    variants = {}
    for (name, lbs), vw, lo in product(LOOKBACK_SETS.items(), VOL_WINS, (False, True)):
        variants[(name, vw, lo)] = run(closes, rets, funding, lbs, bases[vw], lo)
    n_trials = len(variants)
    daily_sr = {k: v[0].loc["2018":].mean() / v[0].loc["2018":].std() for k, v in variants.items()}
    sr_var = np.var(list(daily_sr.values()))

    lines = [f"Data through {closes.index[-1]:%Y-%m-%d}. Holdout from {HOLDOUT_START:%Y-%m-%d} untouched.",
             f"Variants tried: {n_trials}\n"]
    curves = {}

    for lo in (False, True):
        mode = "LONG/FLAT" if lo else "LONG/SHORT"
        oos, picks = [], []
        for y in TEST_YEARS:
            start = pd.Timestamp(f"{y}-01-01", tz="UTC")
            end = min(pd.Timestamp(f"{y + 1}-01-01", tz="UTC"), HOLDOUT_START)
            train = {k: v for k, v in variants.items() if k[2] == lo}
            best = max(train, key=lambda k: stats(train[k][0].loc[:start - pd.Timedelta(days=1)].loc["2018":])["Sharpe"])
            is_sr = stats(train[best][0].loc[:start - pd.Timedelta(days=1)].loc["2018":])["Sharpe"]
            seg = variants[best][0].loc[start:end - pd.Timedelta(days=1)]
            oos.append(seg)
            picks.append(f"  {y}: picked {best[0]}, volwin {best[1]}  | train Sharpe {is_sr:5.2f}  test Sharpe {stats(seg)['Sharpe']:5.2f}")
        oos = pd.concat(oos)
        s = stats(oos)
        fixed = variants[("all (10..240)", 20, lo)]
        sf = stats(fixed[0].loc[oos.index], fixed[1])
        pos = fixed[2].loc[oos.index]
        cost_drag = (fixed[1].loc[oos.index].sum() * (FEE + SLIP)) / (len(oos) / 365)

        lines.append(f"=== {mode} ===")
        lines.append("Walk-forward picks (settings chosen on past data only):")
        lines += picks
        lines.append(f"\nOOS {oos.index[0]:%Y-%m-%d} to {oos.index[-1]:%Y-%m-%d}")
        lines.append(fmt("Walk-forward (selected)", s))
        lines.append(fmt("Fixed 'all' blend, no selection", sf))
        lines.append(f"  Fixed blend: avg gross exposure {pos.abs().sum(axis=1).mean():.2f}x, "
                     f"long {(pos.sum(axis=1) > 0.05).mean():.0%} / short {(pos.sum(axis=1) < -0.05).mean():.0%} of days, "
                     f"fee+slip drag {cost_drag:.1%}/yr")
        lines.append(f"  Deflated Sharpe prob (WF, {n_trials} trials): {deflated_sharpe(oos, n_trials, sr_var):.2f}\n")
        curves[f"Trend {mode.lower()} (walk-forward)"] = oos

    # benchmarks over the same OOS window
    idx = curves[list(curves)[0]].index
    btc = rets["BTC"].loc[idx]
    # always long every coin, same vol targeting: isolates what the trend signal adds
    bh_r = run_target(rets, funding, bases[20].clip(upper=MAX_LEV).fillna(0))[0]
    lines.append("=== BENCHMARKS (same OOS window) ===")
    lines.append(fmt("BTC buy & hold (no funding)", stats(btc)))
    lines.append(fmt("Always-long basket, same vol targeting", stats(bh_r.loc[idx])))
    curves["BTC buy & hold"] = btc
    curves["Always-long vol-targeted basket"] = bh_r.loc[idx]

    # parameter neighbourhood: single lookbacks
    lines.append("\n=== PARAMETER NEIGHBOURHOOD (single lookback, volwin 20, 2018 to holdout) ===")
    hood = {}
    for lo in (False, True):
        for L in range(10, 260, 10):
            pr = run(closes, rets, funding, (L,), bases[20], lo)[0].loc["2018":]
            hood[(L, lo)] = stats(pr)["Sharpe"]
    lines.append("Lookback  " + " ".join(f"{L:>5}" for L in range(10, 260, 10)))
    for lo in (False, True):
        lines.append(("L/F       " if lo else "L/S       ") + " ".join(f"{hood[(L, lo)]:5.2f}" for L in range(10, 260, 10)))

    report = "\n".join(lines)
    (OUT / "results.txt").write_text(report)
    print(report)
    plot(curves, hood, OUT / "results.png")


def fmt(name, s):
    t = f"  {name:38} CAGR {s['CAGR']:7.1%}  Vol {s['Vol']:5.1%}  Sharpe {s['Sharpe']:5.2f}  MaxDD {s['MaxDD']:7.1%}  Calmar {s['Calmar']:5.2f}"
    if "Turnover/yr" in s:
        t += f"  Turnover {s['Turnover/yr']:4.1f}x/yr"
    return t


def plot(curves, hood, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(2, 1, figsize=(11, 9), gridspec_kw={"height_ratios": [3, 2]})
    for name, r in curves.items():
        ax[0].plot((1 + r).cumprod(), label=name, lw=1.4 if "Trend" in name else 1)
    ax[0].set_yscale("log"); ax[0].set_title("Out-of-sample equity (log scale), costs and funding included")
    ax[0].legend(); ax[0].grid(alpha=0.3)
    Ls = sorted({k[0] for k in hood})
    ax[1].plot(Ls, [hood[(L, False)] for L in Ls], marker="o", label="Long/short")
    ax[1].plot(Ls, [hood[(L, True)] for L in Ls], marker="o", label="Long/flat")
    ax[1].axhline(0, color="k", lw=0.8)
    ax[1].set_xlabel("Single lookback (days)"); ax[1].set_ylabel("Sharpe")
    ax[1].set_title("Parameter neighbourhood: a real edge should be a smooth plateau, not a spike")
    ax[1].legend(); ax[1].grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(path, dpi=130)


if __name__ == "__main__":
    main()
