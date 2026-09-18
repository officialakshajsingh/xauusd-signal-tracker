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

**YouTube cookies.** YouTube asks GitHub's servers to sign in, so captures use the cookies of a
*throwaway* Google account, stored in the `YT_COOKIES` Actions secret. They expire every so often;
when captures fail for an hour the workflow opens a `capture-failing` issue. To refresh them:

1. Open a private/incognito window, sign in to YouTube with the throwaway account.
2. In that same tab go to `https://www.youtube.com/robots.txt` and export the youtube.com cookies in
   Netscape `cookies.txt` format (for example with the open-source "Get cookies.txt LOCALLY" extension).
3. Close the private window straight away, so YouTube doesn't rotate the exported session.
4. Paste the whole file into **Settings > Secrets and variables > Actions > YT_COOKIES**.

<!-- STATUS:START -->
<!-- STATUS:END -->
