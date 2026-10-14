"""
strategy_v3.py - FROZEN final research version (frozen 2026-10-14). Do not change.

v3 = v1 signal + v2 trade band + v3 strategy-level vol scaling, on 13 coins.
Every setting below was fixed during research; nothing here is tuned further.
Any change is a new variant and must be counted and validated as one.

  Signal   long/flat, average of +1/-1 votes over 10/20/40/60/120/240-day returns
  Sizing   inverse-vol risk parity (20-day vol, 60-day correlations) scaled to 30% vol,
           then scaled again by the strategy's own 365-day realised vol (scaler capped 3x),
           max 2x per coin
  Trading  trade a coin only if its weight must move by more than 25% of the current
           position, with a 2% floor
  Costs    HL taker fee 0.045% + slippage 0.03% per side, HL funding

Backtest (Binance prices, 2019 to 2025-10-13, 13 coins): CAGR 45.8%, vol 32.1%,
Sharpe 1.34, max DD -35.3%. Honest Sharpe estimate about 1.3.
"""
import backtest as bt

COINS = ["BTC", "ETH", "SOL",
         "XRP", "DOGE", "BNB", "ADA", "LINK", "AVAX", "LTC", "BCH", "DOT", "TRX"]
LOOKBACKS = (10, 20, 40, 60, 120, 240)
VOL_WIN = 20
LONG_ONLY = True
BAND = (0.25, 0.02)
SCALE_WIN, SCALE_CAP = 365, 3.0

# settings inherited from backtest.py; stop if any has been edited since the freeze
FROZEN_BT = {"TARGET_VOL": 0.30, "MAX_LEV": 2.0, "COV_WIN": 60, "FEE": 0.00045, "SLIP": 0.0003}
for _name, _val in FROZEN_BT.items():
    assert getattr(bt, _name) == _val, f"backtest.{_name} changed since v3 was frozen"


def targets(closes, rets, funding):
    """Target weight per coin per day (row t uses data up to day t's close only),
    plus the strategy-level scaler. Same calls as universe_study.py Part C."""
    base = bt.base_weights(rets, VOL_WIN)
    tgt = bt.make_target(closes, LOOKBACKS, base, LONG_ONLY)
    return bt.scale_to_target(rets, funding, tgt, BAND, SCALE_WIN, SCALE_CAP)
