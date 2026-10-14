# hyperliquid-strategy

I built a low-frequency trend-following strategy for Hyperliquid perpetual futures.
The signal blends time-series momentum across several lookbacks, positions are long/flat
and sized by inverse volatility, and I check every result with walk-forward and
out-of-sample tests.

**Status: paper trading.** I've finished the research and frozen the final version (v3 on
13 coins, `strategy_v3.py`). Paper trading on Hyperliquid data started on 2026-10-13. This is
not financial advice.

## Paper trading

```
python paper_trade.py
```

Run it once a day, any time after 00:00 UTC, when Hyperliquid's daily candle closes. Each run downloads the
latest HL prices and funding, computes the v3 targets, simulates fills at the close with fees
and slippage, and appends to `paper/daily_log.csv` (one row per day: equity, P&L, positions)
and `paper/fills.csv` (one row per trade). Missed days are caught up; running it twice in a
day does nothing. Each daily row records `run_time` (when it was computed, UTC) and
`catch_up` (True if the day was processed after a newer candle had already closed).

A Windows scheduled task runs `run_paper.py` every day at 10:30 Brisbane (00:30 UTC): it runs
the paper trader and commits and pushes the two log files as `paper: <date>`, so the paper
record is timestamped publicly as it happens.

## Rebuilding the data

I don't store the market data CSVs in the repo. To download them again:

```
pip install requests pandas numpy scipy matplotlib
python fetch_binance.py    # Binance spot BTC/ETH/SOL, daily + 4h (long history for signal research)
python fetch_data.py       # Hyperliquid candles + hourly funding for BTC/ETH/SOL/HYPE
python fetch_universe.py   # 10 extra coins for the out-of-universe test
```

The files are saved to `data/`. Hyperliquid only serves the most recent 5000 candles per
interval, so newly downloaded 4h data will cover a later window than my original run.

## Code

- `strategy_v3.py`: the frozen final strategy settings
- `paper_trade.py`: daily paper trader; logs in `paper/`
- `run_paper.py`: daily scheduled wrapper (run paper trader, commit and push logs)
- `backtest.py`: the core engine (signal, sizing, backtest, stats)
- `holdout.py`, `v2_study.py`, `v3_sizing.py`, `universe_study.py`: individual studies
- `results/`: text reports and charts

## Research log

I record every experiment in [JOURNAL.md](JOURNAL.md): what I tested, the key numbers, the
decisions I made and what went wrong. I also keep count of how many strategy variants I've
tried, so the overfitting risk can be judged.
