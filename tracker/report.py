"""Rewrite the live-status block in README.md after every capture."""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from pathlib import Path

START, END = "<!-- STATUS:START -->", "<!-- STATUS:END -->"
IST = timedelta(hours=5, minutes=30)


def _ist(utc: str | None) -> str:
    if not utc:
        return "?"
    fmt = "%Y-%m-%dT%H:%M:%SZ" if utc.count(":") == 2 else "%Y-%m-%dT%H:%MZ"
    return (datetime.strptime(utc, fmt) + IST).strftime("%d %b %H:%M IST")


def _dot(v: str) -> str:
    return "🟢" if v in ("Bullish", "Buy") else "🔴" if v in ("Bearish", "Sell") else "⚪"


def status_block(snap: dict, trades: list[dict]) -> str:
    repo = os.environ.get("GITHUB_REPOSITORY", "officialakshajsingh/xauusd-signal-tracker")
    lines = [START, "## 📡 Live status", ""]
    lines.append(f"Last capture **{_ist(snap['captured_utc'])}** ({snap['captured_utc']})"
                 + (f" · chart clock {snap['chart_clock']}" if snap.get("chart_clock") else ""))
    lines.append("")
    change = f" ({snap['day_change_pct']:+.2f}% today)" if "day_change_pct" in snap else ""
    lines.append(f"**Gold (XAU/USD): {snap.get('price', '?')}**{change} · "
                 f"Position **{snap.get('position') or '?'}** · Trend **{snap.get('trend') or '?'}**")
    lines.append("")

    t = snap.get("trade")
    if t:
        open_row = next((r for r in trades if r["status"] == "open"), {})
        def lvl(n):
            hit = " ✅" if open_row.get(f"tp{n}_hit") else ""
            return f"{t.get(f'tp{n}', '')}{hit}"
        lines += [f"**Active trade:** {t.get('signal', t['side'])} signalled {_ist(t.get('signal_time_utc'))}", "",
                  "| Side | Entry | SL | TP1 | TP2 | TP3 | Risk |", "|---|---|---|---|---|---|---|",
                  f"| {t['side']} | {t['entry']} | {t['sl']} | {lvl(1)} | {lvl(2)} | {lvl(3)} | {t['risk']} |", ""]
    if snap.get("mtf"):
        lines.append("**Trend table:** " + " · ".join(f"{k} {_dot(v)}" for k, v in snap["mtf"].items()))
        lines.append("")
    if snap.get("problems"):
        lines.append("⚠️ Extraction issues on this capture: " + "; ".join(snap["problems"]))
        lines.append("")

    closed = [r for r in trades if r["status"] == "closed"]
    lines += ["## 📒 Trade log (latest 15)", "",
              "| # | Signal | Signalled | Entry | SL | Result | R |", "|---|---|---|---|---|---|---|"]
    for r in reversed(trades[-15:]):
        result = r["result"] or "open"
        lines.append(f"| {r['id']} | {r['signal'] or r['side']} | {_ist(r['signal_time_utc'] or r['first_seen_utc'])} "
                     f"| {r['entry']} | {r['sl']} | {result} | {r['r']} |")
    lines.append("")
    if closed:
        n = len(closed)
        tp1 = sum(1 for r in closed if r["tp1_hit"])
        sl = sum(1 for r in closed if r["result"] == "SL")
        net = sum(float(r["r"] or 0) for r in closed)
        lines.append(f"**Scoreboard:** {n} closed trades · reached TP1 {tp1}/{n} ({tp1 / n:.0%}) · "
                     f"stopped out {sl}/{n} · net {net:+.2f}R (exit at best target reached)")
    else:
        lines.append("**Scoreboard:** no closed trades yet.")
    lines += ["", "Full analysis: [ANALYSIS.md](ANALYSIS.md) · data: [trades.csv](data/trades.csv), "
              "[events.csv](data/events.csv)", "",
              f"![Latest chart capture](https://raw.githubusercontent.com/{repo}/frames/latest.jpg)", END]
    return "\n".join(lines)


def write_readme(path: Path, snap: dict, trades: list[dict]) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else f"{START}\n{END}\n"
    block = status_block(snap, trades)
    pattern = re.compile(re.escape(START) + ".*?" + re.escape(END), re.S)
    text = pattern.sub(lambda _: block, text) if pattern.search(text) else text + "\n" + block + "\n"
    path.write_text(text, encoding="utf-8")
