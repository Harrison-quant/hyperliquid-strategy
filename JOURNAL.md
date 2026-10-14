# Journal

My research log for this project: every step, result, decision and mistake, in order.
New entries go at the bottom; earlier entries aren't edited.

All results are backtests unless marked otherwise. Fees, slippage and funding are included throughout.

---

## 2026-10-14 - Idea and data

- Goal: a low-frequency systematic strategy on Hyperliquid (HL) perps. I chose time-series trend
  following over funding-rate and cross-sectional ideas because it's the simplest to reason about
  and the hardest to fool myself with.
- I pulled daily and 4h candles for BTC, ETH, SOL and HYPE from HL's public API, plus hourly
  funding from May 2023.
- Problem: HL only serves the last 5000 candles, so 4h history is about 2.3 years. That's too short
  to validate a trend strategy across market regimes.
- Fix: research the signal on Binance spot history (BTC/ETH from 2017, SOL from 2020) and use HL data
  for funding costs and the final holdout check.
- Data checks: no missing values, a few small funding gaps (max 8h, forward-filled), a few 2018
  Binance outage gaps.
- Average HL funding was 12-14%/yr on BTC/ETH/SOL, paid by longs. That's a real cost for a strategy
  that is mostly long.

## 2026-10-14 - v1 design and walk-forward test

**Design**
- Signal: for each coin, a +1/-1 vote on whether price is up over 10, 20, 40, 60, 120 and 240 days,
  averaged. I used a blend instead of one "best" lookback to resist overfitting.
- Sizing: inverse-volatility risk parity, scaled to 30%/yr portfolio volatility using rolling
  correlations, max 2x per coin.
- Trading: decide at the daily close, hold from the next day, and only trade if a weight changes by
  more than 10% of capital.
- Costs: HL taker fee 0.045% plus 0.03% slippage per side; real HL funding from 2023, and a flat
  13%/yr charge on longs before that (conservative).

**Validation**
- Walk-forward: for each year 2019-2025, choose settings using only earlier data, then record
  performance on the unseen year. 16 variants in the search.
- I locked away the last 12 months (from 2025-10-14) as a holdout.

**Results, out-of-sample 2019 to Oct 2025**

| | CAGR | Vol | Sharpe | Max DD |
|---|---|---|---|---|
| Long/flat, fixed blend | 20.8% | 16.6% | 1.22 | -16.7% |
| Long/short, fixed blend | 17.1% | 20.0% | 0.89 | -24.1% |
| Long/flat, walk-forward selected | 18.7% | 19.1% | 1.00 | -24.6% |
| Always long, same vol targeting | 40.2% | 33.4% | 1.18 | -49.1% |
| BTC buy and hold | 65.9% | 63.4% | 1.12 | -76.6% |

**Findings and decisions**
- The edge is drawdown control, not extra return: Sharpe roughly ties holding, but max drawdown is
  about a third.
- Long/short was worse than long/flat at every lookback (crypto shorts get squeezed). I went long/flat.
- Key lesson: re-optimising settings each year made results worse (Sharpe 1.00 vs 1.22 for the fixed
  blend chosen upfront). Picking the in-sample winner chased noise. I kept the fixed blend and stopped tuning.
- Overfitting checks passed: Sharpe across single lookbacks from 10 to 250 days is a flat plateau
  (0.64-1.12, all positive), and the deflated Sharpe probability is 0.98 after 16 trials.
- Red flags: weak 2024-2025, and capital mostly idle (0.2x average exposure).

## 2026-10-14 - Holdout (run once)

- I ran frozen v1 (long/flat, fixed blend) on 2025-10-15 to 2026-10-13 using HL prices and HL
  funding, exactly once. The holdout is now spent.

| | Return | Vol | Sharpe | Max DD |
|---|---|---|---|---|
| Trend v1 | +0.3% | 5.5% | 0.09 | -3.5% |
| Always long, vol-targeted | -24.6% | 34.4% | -0.65 | -43.9% |
| BTC buy and hold | -26.5% | 44.1% | -0.48 | -48.9% |

- It was a bear year. The strategy sat in cash 82% of days, dodged the November, February and June
  crashes, and caught a small part of the August rally.
- Verdict: it passed the safety test, but showed no return edge. One bear year can't test the upside.
- Practical issue: HL's minimum order is about $10, so a $5-10 live test can't place this strategy's
  position sizes.

## 2026-10-14 - v2: trade band fix

- Change: trade when a position needs to move by more than 25% of its current size, with a 2% floor.
  I fixed these values before running; a grid of other values was a robustness check only.

| Pre-holdout 2019 to Oct 2025 | CAGR | Vol | Sharpe | Max DD | Trades/yr |
|---|---|---|---|---|---|
| v1 | 20.8% | 16.6% | 1.22 | -16.7% | 35 |
| v2 | 25.6% | 16.9% | 1.43 | -20.1% | 134 |
| No threshold | 26.1% | 16.8% | 1.46 | -20.0% | 251 |

- The robustness grid was flat (Sharpe 1.40-1.46 across 9 settings). v2 is close to trading daily at
  half the trades, so it removes damage v1 was doing rather than adding a tuned edge.
- A wrong diagnosis, caught by the data: the first explanation was that v1's threshold blocked
  entries. The numbers showed the opposite. v1 was invested 94% of days vs v2's 66%; the fixed
  threshold made v1 sticky, unable to exit small stale positions. The low exposure came from sizing,
  not the threshold.
- Caveat: much of the gain comes from one year (2021). Deflated Sharpe is 1.00 after 27 variants, but
  trend following was a published idea before I touched this data.

## 2026-10-14 - v3: strategy-level sizing

- Problem: the "30% vol target" actually delivered about 17%, because the signal is usually only
  partly on.
- Change: measure the strategy's own realised vol over the past 365 days and scale all positions to
  hit 30%, with the scaler capped at 3x. Fixed before running.
- v3 on BTC/ETH/SOL: CAGR 56.4%, vol 34.3%, Sharpe 1.48, max DD -32.3%.
- As expected, Sharpe barely changed. This is a risk choice, not new edge.
- Robust: 9 window/cap combinations all gave Sharpe 1.45-1.53.
- Weakness: it overshoots after calm periods (2019 and 2023 ran at 44-46% vol) because it levers up
  just before trends restart.

## 2026-10-14 - Out-of-universe test

**Did**
- Downloaded Binance daily, HL daily and HL funding for 10 coins never used in development: XRP, DOGE,
  BNB, ADA, LINK, AVAX, LTC, BCH, DOT, TRX. I fixed the list before seeing any results.
- Ran frozen v2, unchanged, on them (universe_study.py; report in results/universe_study.txt).

**Key numbers**
- Per coin (2019 to holdout): Sharpe positive on 9/10 (DOT -0.11), lower drawdown than holding on
  10/10, higher Sharpe than holding on only 4/10.
- 10-coin portfolio: Sharpe 1.32, CAGR 20.9%, vol 15.2%, max DD -13.5%, vs always-long 1.03 / 33.4% / -44.6%.
- Holdout year, new coins (HL prices and funding): trend -3.5%, max DD -4.9%; always-long -19.9%,
  max DD -40.5%. I'd already seen the holdout regime via v1, so this isn't fully independent, but I
  tuned nothing on it.
- v3 on all 13 coins: CAGR 45.8%, vol 32.1%, Sharpe 1.34, max DD -35.3% (vs 1.48 on 3 coins).

**Decisions**
- I changed no parameters; the variant count stays at about 36.
- The strategy generalises to coins it wasn't designed on. The story is consistent everywhere: trend
  cuts drawdowns on every coin, and combining coins lifts Sharpe above holding.
- I treat a Sharpe of about 1.3 as the honest estimate. The 3-coin 1.48 is flattered, because those
  coins were used in development.
- Open question: paper-trade 3 coins or 13? 13 is more diversified, and choosing 3 because it scored
  higher would repeat the v1 mistake of picking the in-sample winner. But with average gross exposure
  around 0.35x, many rebalances would fall below HL's ~$10 minimum on a small account.

**Caveats**
- Survivorship bias: all 13 coins are still large today, so results are flattered for both trend and holding.
- Data quirk (noticed, not fixed): HL daily candles start 2023-01-01 for every coin, but HL funding
  starts later for some (XRP 2023-06-18, TRX 2023-08-06, DOT 2023-09-12, ADA 2023-10-22). This doesn't
  affect the holdout, but funding is missing before those dates if HL data is used earlier.
- Re-downloading HL 4h data later gives a later 5000-bar window, so exact 4h results may not reproduce.

---

## Running totals
- Variants tested on 2017-2025 data: about 36 (v1 search 16, v2 band grid 9, sizing grid 9, misc 2).
  The out-of-universe test added none.
- Holdout: spent on v1. The next clean out-of-sample data comes from paper trading.

## Lessons so far
1. Optimising made it worse; a fixed, pre-committed design won.
2. The edge is drawdown control, not beating buy-and-hold.
3. A wrong diagnosis (v2 threshold) was caught by checking the data, not trusting the story.
4. Exchange history limits (5000 candles) forced a two-source data design.
5. Practical constraints like order minimums matter before going live.
6. Working on unseen coins was the strongest evidence against overfitting.
