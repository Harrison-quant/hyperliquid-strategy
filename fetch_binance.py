"""
fetch_binance.py - pull long daily and 4h price history from Binance spot.

Why: Hyperliquid only has ~2 years of 4h data. Trend signals need many years
and several market regimes to validate, so we design the signal on Binance
history and use Hyperliquid data for costs/funding and the final check.

Run:     python fetch_binance.py
Output:  data/binance_<SYMBOL>_<interval>.csv  (time, open, high, low, close, volume)
"""
import os
import time
from datetime import datetime, timezone

import pandas as pd
import requests

URL = "https://api.binance.com/api/v3/klines"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
INTERVALS = ["4h", "1d"]
START = "2017-08-01"
OUT = "data"


def fetch(symbol, interval, start_ms, end_ms):
    """Binance returns max 1000 bars per call; page forward from the last close time."""
    rows, t = [], start_ms
    while t < end_ms:
        r = requests.get(URL, params={"symbol": symbol, "interval": interval,
                                      "startTime": t, "endTime": end_ms,
                                      "limit": 1000}, timeout=30)
        if r.status_code == 429:
            time.sleep(5)
            continue
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        rows += batch
        t = batch[-1][6] + 1  # close time of last bar + 1ms
        time.sleep(0.2)

    df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume",
                                     "close_time", "qv", "n", "tb", "tq", "ignore"])
    df = df[df["close_time"] < end_ms]  # drop the still-forming bar
    df = df[["time", "open", "high", "low", "close", "volume"]]
    df[["open", "high", "low", "close", "volume"]] = df[
        ["open", "high", "low", "close", "volume"]].astype(float)
    df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
    return df.drop_duplicates("time").sort_values("time").reset_index(drop=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    start_ms = int(datetime.fromisoformat(START).replace(tzinfo=timezone.utc).timestamp() * 1000)
    end_ms = int(time.time() * 1000)
    for sym in SYMBOLS:
        for interval in INTERVALS:
            df = fetch(sym, interval, start_ms, end_ms)
            df.to_csv(f"{OUT}/binance_{sym}_{interval}.csv", index=False)
            print(f"{sym:8} {interval:3} {len(df):6} bars  "
                  f"{df['time'].iloc[0]:%Y-%m-%d} to {df['time'].iloc[-1]:%Y-%m-%d}")


if __name__ == "__main__":
    main()
