"""
fetch_universe.py - download data for the out-of-universe test.

These 10 coins were fixed BEFORE looking at any results: large, liquid coins
that trade on both Binance spot (for long history) and Hyperliquid perps.
None of them were used to build v1 or v2.

Run:     python fetch_universe.py
Output:  data/binance_<SYM>USDT_1d.csv, data/<COIN>_1d.csv, data/<COIN>_funding.csv
"""
import os
import time
from datetime import datetime, timezone

import fetch_binance as fb
import fetch_data as fd

NEW_COINS = ["XRP", "DOGE", "BNB", "ADA", "LINK", "AVAX", "LTC", "BCH", "DOT", "TRX"]


def ms(date):
    return int(datetime.fromisoformat(date).replace(tzinfo=timezone.utc).timestamp() * 1000)


def main():
    os.makedirs("data", exist_ok=True)
    now = int(time.time() * 1000)
    for coin in NEW_COINS:
        try:
            b = fb.fetch(f"{coin}USDT", "1d", ms("2017-08-01"), now)
            b.to_csv(f"data/binance_{coin}USDT_1d.csv", index=False)
            h = fd.fetch_candles(coin, "1d", ms("2023-01-01"), now)
            h.to_csv(f"data/{coin}_1d.csv", index=False)
            f = fd.fetch_funding(coin, ms("2023-01-01"), now)
            f.to_csv(f"data/{coin}_funding.csv", index=False)
            print(f"{coin:5} binance {len(b):5} days from {b['time'].iloc[0]:%Y-%m-%d} | "
                  f"HL {len(h):4} days | funding {len(f):6} rows")
        except Exception as e:  # keep going if one coin fails
            print(f"{coin:5} FAILED: {e}")


if __name__ == "__main__":
    main()
