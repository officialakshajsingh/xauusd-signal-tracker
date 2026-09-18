# XAU/USD Signal Tracker

Records every trade the [Daily Trading Tips gold livestream](https://www.youtube.com/watch?v=3H4IVQejlDE)
signals on its 1-minute chart, tracks whether each one reaches its targets or its stop, and keeps a
running professional analysis of the signals.

**How it works.** One Claude Code cloud routine does everything on Anthropic's cloud, every 4 hours
on weekdays:

1. **Capture, about every 10 minutes for 3 h 40 min.** [`tracker.loop`](tracker/loop.py) grabs a
   1080p frame of the stream, reads it with OCR (entry, stop loss, TP1-TP3, the Buy/Sell/TP markers,
   the multi-timeframe trend table and the live price), updates [`data/`](data) and this page, and
   pushes.
2. **Analysis at the end of each run.** Claude checks that run's trades against the chart images,
   corrects anything the OCR misread, and writes the breakdown and scoreboard to
   [ANALYSIS.md](ANALYSIS.md) and [`reports/`](reports).

GitHub Actions can't do the capture: YouTube answers GitHub's servers with "Sign in to confirm you're
not a bot", while Anthropic's cloud gets through.

Chart times on the stream are UTC+4; everything here is stored in UTC and shown in IST.
This is a record of someone else's signals for study, not trading advice.

Re-process a saved frame locally: `python -m tracker.main --frame some.png --data-dir /tmp/d`.

<!-- STATUS:START -->
## 📡 Live status

Last capture **18 Sep 13:15 IST** (2026-09-18T07:45:45Z) · chart clock 11:45:46

**Gold (XAU/USD): 4395.38** (+1.25% today) · Position **Buy** · Trend **Bullish**

**Active trade:** Buy+ signalled 18 Sep 11:07 IST

| Side | Entry | SL | TP1 | TP2 | TP3 | Risk |
|---|---|---|---|---|---|---|
| Buy | 4370.93 | 4362.9143 | 4378.9457 ✅ | 4386.9614 ✅ |  | 8.0157 |

**Trend table:** 1m 🟢 · 3m 🟢 · 5m 🟢 · 15m 🟢 · 30m 🟢 · 1H 🟢 · 2H 🟢 · 4H 🟢 · 8H 🟢 · D 🔴

## 📒 Trade log (latest 15)

| # | Signal | Signalled | Entry | SL | Result | R |
|---|---|---|---|---|---|---|
| 1 | Buy+ | 18 Sep 11:07 IST | 4370.93 | 4362.9143 | open |  |

**Scoreboard:** no closed trades yet.

Full analysis: [ANALYSIS.md](ANALYSIS.md) · data: [trades.csv](data/trades.csv), [events.csv](data/events.csv)

![Latest chart capture (refreshed hourly)](latest.jpg)
<!-- STATUS:END -->
