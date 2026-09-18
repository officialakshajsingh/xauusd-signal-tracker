# Analysis

Study notes on the [Daily Trading Tips](https://www.youtube.com/watch?v=3H4IVQejlDE) gold signal
indicator, rebuilt hourly from chart captures. **Not financial advice.**

⚠️ **Sample size warning:** tracking started 2026-09-18. Everything below is 4 closed trades from a
few hours of one session (Asian session only, pre-London). Treat every number here as provisional —
this needs weeks of data across sessions before any pattern is meaningful.

## Scoreboard (4 closed trades)

| Metric | Value |
|---|---|
| Reached TP1 | 2/4 (50%) |
| Reached TP2 | 2/4 (50%) |
| Reached TP3 | 0/4 (0%) |
| No target (SL risk) | 2/4 (50%) |
| **Net R, exit at best TP reached** | **+2R** (avg +0.5R/trade) |
| **Net R, exit at TP1 else -1R** | **0R** (avg 0R/trade) |

One trade (#5, Buy+) is still open, having already run through TP1-TP3; excluded from the closed-trade
scoreboard above.

### By signal type

| Signal | Closed trades | TP hit | Net R (best TP) |
|---|---|---|---|
| Buy | 1 | TP2 | +2R |
| Buy+ | 1 (+1 open, past TP3) | TP2 | +2R |
| Sell | 2 | 0/2 | -2R |
| Sell+ | 0 | — | — |

All three losing/no-target legs so far are the two Sell signals, both closed in under 15 minutes —
too small a sample to call Sell signals unreliable, but worth watching.

### By trend-table alignment / session

Not enough data: the trend table was only captured for the one open trade (all intraday timeframes
Bullish, Daily Bearish), and every signal so far fired inside the same Asian session before the
07:00 UTC London open. No comparison across alignment or session is possible yet.

## Verdict

Too early to say anything reliable. The four closed trades split evenly — both Buy-side signals hit
TP2, both Sell signals hit nothing — but n=4 makes this noise, not signal. Revisit once trades span
multiple sessions and both trend directions.

## Last 20 trades

| # | Signal | Signalled (IST) | Entry | SL | Targets hit | Result | R |
|---|---|---|---|---|---|---|---|
| 5 | Buy+ | 18 Sep 11:07 | 4370.93 | 4362.9143 | TP1 TP2 TP3 | TP3 so far (open) | — |
| 4 | Sell | 18 Sep 11:00 | ~4367.53 | — | none | No TP | -1 |
| 3 | Buy+ | 18 Sep 09:59 | ~4353.07 | — | TP1 TP2 | TP2 | +2 |
| 2 | Sell | 18 Sep 09:46 | ~4359.65 | — | none | No TP | -1 |
| 1 | Buy | 18 Sep 09:02 | ~4340.14 | — | TP1 TP2 | TP2 | +2 |

Entries marked ~ are estimated from chart markers; exact levels are only recorded for the trade that
was live at a capture.

## Capture health

- Last good capture: **2026-09-18T07:53:31Z** (chart clock 11:53:32 UTC+4)
- Consecutive failures: 2 (both this hour, 08:13Z and 08:14Z, HTTP 403 — YouTube bot-check)
- Last error: `2026-09-18T08:14:35Z HTTPError: HTTP Error 403: Forbidden`

## Daily reports

- [2026-09-18](reports/2026-09-18.md)
