# hyperliquid-strategy

My quant portfolio project: a low-frequency trend-following strategy for Hyperliquid perps.
I bring the maths, market ideas and judgement; Claude writes and runs the code.

## Working rules
- Always validate with walk-forward / out-of-sample testing and flag overfitting.
- Pre-register parameter choices before running; extra values are robustness checks only.
- Explain what the code does in plain terms. Concise answers, no emojis.
- After every piece of strategy or research work, append a dated entry to JOURNAL.md: what was done,
  key numbers, decisions, anything that went wrong. Append only; never edit or rewrite earlier entries.
- Only journal strategy and research work (data, strategy versions, tests, results, decisions, lessons).
  Never journal setup, tooling or git admin.
- Write everything in first person, from my point of view ("I built", "I chose"), never third person.
- Variants tried so far on 2017-2025 data: ~36 (v1 search 16, v2 band grid 9, sizing grid 9, misc 2). Keep counting.

## Data (data/)
- Binance spot daily/4h: BTC, ETH (2017+), SOL (2020+). I use these for signal research.
- Hyperliquid daily/4h candles (4h capped at last 5000 bars) and hourly funding (2023+).
- Scripts: fetch_data.py (HL), fetch_binance.py, fetch_universe.py (10 new coins).

## Strategy history
- v1: time-series momentum, average of sign votes over lookbacks (10,20,40,60,120,240),
  inverse-vol risk parity scaled to 30% vol, 2x per-coin cap, absolute 10% trade threshold.
  Walk-forward: selecting settings each year HURT (Sharpe 1.00) vs fixed blend (1.22). Long/short
  was worse than long/flat at every lookback. I chose fixed blend, long/flat.
- Holdout (2025-10-14 to 2026-10-13, HL prices), run ONCE on v1: +0.3%, MaxDD -3.5% vs BTC -26.5%.
  The holdout is now SPENT; I never tune on it.
- v2: trade band relative to position (trade if change > 25% of current position, 2% floor).
  Pre-holdout Sharpe 1.43, robust across band grid (1.40-1.46). Gain concentrated in 2021.
- v3 (in progress): v2 + strategy-level vol scaling (365d realised vol of strategy, scaler capped 3x).
  Sharpe 1.48, vol 34%, MaxDD -32%. Overshoots vol after calm periods (2019, 2023).
- Universe study (2026-10-14, results/universe_study.txt; no new tuned variants): frozen v2 on 10
  unseen coins: Sharpe > 0 on 9/10, beats hold on Sharpe only 4/10 but on MaxDD 10/10. 10-coin
  portfolio Sharpe 1.32 (MaxDD -13.5%) vs always-long 1.03 (-44.6%). Holdout year: -3.5% vs -19.9%.
  v3 on 13 coins: Sharpe 1.34, vol 32%, MaxDD -35% (vs 1.48 on 3 coins). I treat ~1.3 as the honest estimate.
- FROZEN 2026-10-14: v3 on all 13 coins is the final research version (strategy_v3.py; asserts the
  inherited backtest.py settings). Any change is a new variant. Paper trading (paper_trade.py) started
  on day 2026-10-13 with $10,000 paper equity. Paper engine holds coin quantities (weights drift);
  pre-holdout replay vs backtest engine: daily return corr 0.997, Sharpe 1.13 both.

## Files
- strategy_v3.py: frozen v3 settings and targets(); paper_trade.py: daily paper trader, logs in paper/
  (daily_log.csv, fills.csv; HL caches in data/paper_*.csv)
- backtest.py: core engine (load, signal, base_weights, run, run_target, scale_to_target, stats, deflated_sharpe)
- holdout.py, v2_study.py, v3_sizing.py, universe_study.py
- results/: text reports and charts

## Next steps
1. DONE: fetch_universe.py and universe_study.py (see Strategy history).
2. DONE: froze v3 on 13 coins; built paper_trade.py.
3. Run paper_trade.py daily after 00:00 UTC (10:00 Brisbane). Review after ~3 months against the
   backtest's expectations; don't change anything based on short paper results.
   Live sizing note: HL minimum order ~$10, so small accounts can't place many rebalance trades.

Later projects: flash-loan arbitrage, then mempool watcher/sniper.
