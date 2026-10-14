"""
paper_trade.py - daily paper trading of the frozen v3 strategy on Hyperliquid data.

What one run does
1. Downloads Hyperliquid daily candles (from 2023) and hourly funding for the 13 v3 coins.
   Funding is cached in data/paper_<COIN>_funding.csv and only new hours are downloaded.
2. Computes frozen v3 target weights (strategy_v3.py) from that history.
3. For every completed UTC day not yet in the log, in order:
   a) marks the paper positions to the day's close: price P&L and funding paid/received,
   b) compares each coin's current weight with its target and trades only where the
      v2 band says so (move > 25% of the current position, 2% floor),
   c) fills at the close +/- 0.03% slippage and pays the 0.045% taker fee.
4. Appends one row per day to paper/daily_log.csv and one row per fill to paper/fills.csv.
   The last row of daily_log.csv is the account state for the next run.

Positions are held as coin quantities, like a real account, so weights drift between
trades. The backtest instead held weights constant (free daily rebalancing), so paper
results will differ slightly from the backtest even on identical prices.
Fills below HL's ~$10 minimum order are flagged, not skipped.

Run once a day, any time after 00:00 UTC (10:00 Brisbane), when the daily candle closes:
    python paper_trade.py
Running it twice in a day does nothing; missed days are caught up in order.
"""
import time
from pathlib import Path

import numpy as np
import pandas as pd

import backtest as bt
import fetch_data as fd
import strategy_v3 as v3

ROOT = Path(__file__).parent
DATA = ROOT / "data"
LOG_DIR = ROOT / "paper"
DAILY_LOG = LOG_DIR / "daily_log.csv"
FILLS_LOG = LOG_DIR / "fills.csv"

START_EQUITY = 10_000.0                       # paper account size, USD
MIN_ORDER = 10.0                              # HL minimum order, USD
HIST_START = pd.Timestamp("2023-01-01", tz="UTC")
HOUR, DAY = pd.Timedelta(hours=1), pd.Timedelta(days=1)


# ---------------------------------------------------------------- data
def ms(ts):
    return int(ts.timestamp() * 1000)


def read_times(path):
    df = pd.read_csv(path)
    df["time"] = pd.to_datetime(df["time"], format="mixed", utc=True)
    return df


def update_funding(coin, now_ms):
    """Hourly funding since 2023. Starts from the cache (or the research file the first
    time) and downloads only hours after the last one already saved."""
    cache = DATA / f"paper_{coin}_funding.csv"
    seed = cache if cache.exists() else DATA / f"{coin}_funding.csv"
    old = read_times(seed) if seed.exists() else pd.DataFrame(columns=["time", "funding_rate", "premium"])
    start = ms(old["time"].max()) + 1 if len(old) else ms(HIST_START)
    new = fd.fetch_funding(coin, start, now_ms)
    df = pd.concat([old, new]) if len(new) else old
    df = df.drop_duplicates("time").sort_values("time")
    df.to_csv(cache, index=False)
    return df.set_index("time")["funding_rate"]


def load_hl():
    """Daily closes, daily funding (sum of the hourly rates in each UTC day) and the
    time of the last funding hour every coin has."""
    DATA.mkdir(exist_ok=True)
    now_ms = int(time.time() * 1000)
    closes, hourly = {}, {}
    for coin in v3.COINS:
        c = fd.fetch_candles(coin, "1d", ms(HIST_START), now_ms)   # completed days only
        c.to_csv(DATA / f"paper_{coin}_1d.csv", index=False)
        closes[coin] = c.set_index("time")["close"]
        hourly[coin] = update_funding(coin, now_ms)
    closes = pd.DataFrame(closes).sort_index()
    funding = pd.DataFrame({c: s.resample("1D").sum() for c, s in hourly.items()})
    funding = funding.reindex(closes.index).fillna(0)
    last_hour = min(s.index.max() for s in hourly.values())
    return closes, funding, last_hour


# ---------------------------------------------------------------- one day
def step(day, equity, qty, prev_close, close, fund_rate, target):
    """Mark yesterday's positions to today's close, then trade towards today's target.
    All inputs per coin are Series on the same index. Returns the day's log row,
    the fills and the new coin quantities."""
    price_pnl = qty * (close - prev_close)
    fund = qty * prev_close * fund_rate                  # positive rate: longs pay
    eq_pre = equity + price_pnl.sum() - fund.sum()       # equity at the close, before trading

    w = qty * close / eq_pre
    change = target - w
    limit = np.maximum(v3.BAND[1], v3.BAND[0] * w.abs())
    trade = change.where(change.abs() > limit, 0.0)
    new_w = w + trade

    notional = trade.abs() * eq_pre
    fee, slip = notional * bt.FEE, notional * bt.SLIP
    new_eq = eq_pre - fee.sum() - slip.sum()
    new_qty = new_w * eq_pre / close

    fills = pd.DataFrame({
        "date": day.date(), "coin": trade.index, "side": np.where(trade > 0, "buy", "sell"),
        "qty": (trade * eq_pre / close), "close": close,
        "fill_price": close * (1 + bt.SLIP * np.sign(trade)), "notional_usd": notional,
        "fee_usd": fee, "slippage_usd": slip, "w_before": w, "w_after": new_w, "target": target,
        "below_min": notional < MIN_ORDER,
    })[trade != 0]

    row = {"date": day.date(), "equity": new_eq, "ret": new_eq / equity - 1,
           "price_pnl": price_pnl.sum(), "funding": 0.0 - fund.sum(), "costs": 0.0 - (fee.sum() + slip.sum()),
           "gross": new_w.abs().sum(), "n_trades": len(fills), "small_orders": int(fills["below_min"].sum())}
    row |= {f"w_{c}": new_w[c] for c in close.index}
    row |= {f"qty_{c}": new_qty[c] for c in close.index}
    return row, fills, new_qty, new_eq


# ---------------------------------------------------------------- state and logs
def load_state():
    if not DAILY_LOG.exists():
        return None
    last = pd.read_csv(DAILY_LOG).iloc[-1]
    qty = pd.Series({c: float(last[f"qty_{c}"]) for c in v3.COINS})
    return pd.Timestamp(last["date"], tz="UTC"), float(last["equity"]), qty


def append(path, df):
    df.to_csv(path, mode="a", header=not path.exists(), index=False, float_format="%.10g")


def main():
    LOG_DIR.mkdir(exist_ok=True)
    closes, funding, last_hour = load_hl()
    target, scaler = v3.targets(closes, closes.pct_change(), funding)

    def ready(d):  # both closes known and all 24 funding hours of day d downloaded
        return (d - DAY in closes.index and closes.loc[[d - DAY, d]].notna().all().all()
                and last_hour >= d + 23 * HOUR)

    state = load_state()
    if state is None:   # first run: start flat on the latest completed day
        days = [d for d in closes.index if ready(d)][-1:]
        if not days:
            raise SystemExit("No completed day with full funding data yet; try again later.")
        last_day, equity, qty = None, START_EQUITY, pd.Series(0.0, index=v3.COINS)
    else:
        last_day, equity, qty = state
        days = list(closes.index[closes.index > last_day])

    done = 0
    for d in days:
        if last_day is not None and d != last_day + DAY:
            raise SystemExit(f"Gap in HL data: expected {last_day + DAY:%Y-%m-%d}, got {d:%Y-%m-%d}. Stopping.")
        if not ready(d):
            print(f"{d:%Y-%m-%d}: candle or funding not complete yet; will retry next run.")
            break
        row, fills, qty, new_eq = step(d, equity, qty, closes.loc[d - DAY], closes.loc[d],
                                       funding.loc[d], target.loc[d])
        row["scaler"] = scaler.loc[d]
        append(DAILY_LOG, pd.DataFrame([row]))
        if len(fills):
            append(FILLS_LOG, fills)
        print(f"{d:%Y-%m-%d}  equity ${new_eq:,.2f}  day {row['ret']:+.2%}  gross {row['gross']:.2f}x  "
              f"scaler {row['scaler']:.2f}  trades {row['n_trades']} ({row['small_orders']} below ${MIN_ORDER:.0f})")
        equity, last_day, done = new_eq, d, done + 1

    if done == 0 and state is not None:
        print(f"Up to date: last logged day {last_day:%Y-%m-%d}, equity ${equity:,.2f}.")
    else:
        held = (qty * closes.loc[last_day] / equity).round(3)
        print("Positions (weight of equity):", ", ".join(f"{c} {w:.3f}" for c, w in held.items() if w) or "flat")


if __name__ == "__main__":
    main()
