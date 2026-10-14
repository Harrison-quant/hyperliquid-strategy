"""
fetch_data.py - pull historical candles and funding rates from Hyperliquid.

Run:     pip install requests pandas
         python fetch_data.py
Output:  data/<COIN>_<interval>.csv   (time, open, high, low, close, volume, trades)
         data/<COIN>_funding.csv      (time, funding_rate, premium)

Notes:
- Hyperliquid only serves the most recent 5000 candles per coin/interval.
  4h = about 2.3 years, 1d = everything since listing.
- Funding on Hyperliquid is paid hourly. funding_rate is the hourly rate.
"""
import os
import time
from datetime import datetime, timezone

import pandas as pd
import requests

URL = "https://api.hyperliquid.xyz/info"
COINS = ["BTC", "ETH", "SOL", "HYPE"]
INTERVALS = ["4h", "1d"]
START = "2023-01-01"
OUT = "data"

MS_PER = {"1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}


def post(payload):
    """Send one request to the info API, backing off if rate limited."""
    for attempt in range(6):
        r = requests.post(URL, json=payload, timeout=30)
        if r.status_code == 429:
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"Rate limited too many times: {payload}")


def fetch_candles(coin, interval, start_ms, end_ms):
    """Walk forward through time in 5000-candle windows and stitch the results."""
    step = MS_PER[interval] * 5000
    rows, t = [], start_ms
    while t < end_ms:
        req = {"coin": coin, "interval": interval,
               "startTime": t, "endTime": min(t + step, end_ms)}
        rows += post({"type": "candleSnapshot", "req": req})
        t += step
        time.sleep(0.25)
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df[df["T"] < end_ms]  # drop the still-forming candle
    df = df.rename(columns={"t": "time", "o": "open", "h": "high", "l": "low",
                            "c": "close", "v": "volume", "n": "trades"})
    df = df[["time", "open", "high", "low", "close", "volume", "trades"]]
    df[["open", "high", "low", "close", "volume"]] = df[
        ["open", "high", "low", "close", "volume"]].astype(float)
    df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
    return df.drop_duplicates("time").sort_values("time").reset_index(drop=True)


def fetch_funding(coin, start_ms, end_ms):
    """Funding history comes back max 500 rows per call; page by last timestamp."""
    rows, t = [], start_ms
    while t < end_ms:
        batch = post({"type": "fundingHistory", "coin": coin,
                      "startTime": t, "endTime": end_ms})
        if not batch:
            break
        rows += batch
        t = batch[-1]["time"] + 1
        time.sleep(0.25)
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).rename(columns={"fundingRate": "funding_rate"})
    df = df[["time", "funding_rate", "premium"]]
    df[["funding_rate", "premium"]] = df[["funding_rate", "premium"]].astype(float)
    df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
    return df.drop_duplicates("time").sort_values("time").reset_index(drop=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    start_ms = int(datetime.fromisoformat(START).replace(tzinfo=timezone.utc).timestamp() * 1000)
    end_ms = int(time.time() * 1000)

    for coin in COINS:
        for interval in INTERVALS:
            df = fetch_candles(coin, interval, start_ms, end_ms)
            path = f"{OUT}/{coin}_{interval}.csv"
            df.to_csv(path, index=False)
            span = f"{df['time'].iloc[0]:%Y-%m-%d} to {df['time'].iloc[-1]:%Y-%m-%d}" if len(df) else "no data"
            print(f"{coin:5} {interval:3} {len(df):6} candles  {span}")

        df = fetch_funding(coin, start_ms, end_ms)
        df.to_csv(f"{OUT}/{coin}_funding.csv", index=False)
        span = f"{df['time'].iloc[0]:%Y-%m-%d} to {df['time'].iloc[-1]:%Y-%m-%d}" if len(df) else "no data"
        print(f"{coin:5} fund {len(df):6} rows     {span}")


if __name__ == "__main__":
    main()
