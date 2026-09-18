# XAU/USD Signal Tracker

Records every trade the [Daily Trading Tips gold livestream](https://www.youtube.com/watch?v=3H4IVQejlDE)
signals on its 1-minute chart, tracks whether each one reaches its targets or its stop, and keeps a
running professional analysis of the signals.

**How it works**

1. **Every 10 minutes** a GitHub Actions job ([capture.yml](.github/workflows/capture.yml)) grabs a 1080p
   frame from the stream, reads it with OCR (entry, stop loss, TP1-TP3, the Buy/Sell/TP markers, the
   multi-timeframe trend table and the live price) and updates the files in [`data/`](data) and this page.
2. **Every few hours** a Claude Code cloud routine reviews the new captures against the chart images,
   corrects anything the OCR got wrong, and writes the analysis to [ANALYSIS.md](ANALYSIS.md) and
   [`reports/`](reports).

Chart times on the stream are UTC+4; everything here is stored in UTC and shown in IST.
This is a record of someone else's signals for study, not trading advice.

<!-- STATUS:START -->
<!-- STATUS:END -->
