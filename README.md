# hyperliquid-strategy

I built a low-frequency trend-following strategy for Hyperliquid perpetual futures.
The signal blends time-series momentum across several lookbacks, positions are long/flat
and sized by inverse volatility, and I check every result with walk-forward and
out-of-sample tests.

**Status: work in progress.** I've finished the research and backtesting; I haven't started
paper trading yet. This is not financial advice.

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

- `backtest.py`: the core engine (signal, sizing, backtest, stats)
- `holdout.py`, `v2_study.py`, `v3_sizing.py`, `universe_study.py`: individual studies
- `results/`: text reports and charts

## Research log

I record every experiment in [JOURNAL.md](JOURNAL.md): what I tested, the key numbers, the
decisions I made and what went wrong. I also keep count of how many strategy variants I've
tried, so the overfitting risk can be judged.
