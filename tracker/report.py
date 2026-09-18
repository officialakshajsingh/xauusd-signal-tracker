"""Rewrite the live-status block in README.md after every capture."""
from __future__ import annotations

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


def scoreboard(trades: list[dict]) -> str:
    closed = [t for t in trades if t["status"] == "closed"]
    if not closed:
        return "**Scoreboard:** no closed trades yet."
    n = len(closed)
    reached = {k: sum(1 for t in closed if f"TP{k}" in t["tp_hits"].split()) for k in (1, 2, 3)}
    net = sum(float(t["r"]) for t in closed)
    return (f"**Scoreboard ({n} closed trades):** reached TP1 {reached[1]}/{n} ({reached[1] / n:.0%}) · "
            f"TP2 {reached[2]}/{n} · TP3 {reached[3]}/{n} · no target {n - reached[1]}/{n} · "
            f"net {net:+.0f}R *(exit at the best TP reached; a trade with no TP counted as -1R)*")


def status_block(snap: dict, trades: list[dict]) -> str:
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
        live = trades[-1] if trades and trades[-1]["status"] == "open" else {}
        hits = live.get("tp_hits", "").split()
        lvl = lambda n: f"{t.get(f'tp{n}', '')}{' ✅' if f'TP{n}' in hits else ''}"  # noqa: E731
        lines += [f"**Active trade:** {t.get('signal', t['side'])} signalled {_ist(t.get('signal_time_utc'))}", "",
                  "| Side | Entry | SL | TP1 | TP2 | TP3 | Risk |", "|---|---|---|---|---|---|---|",
                  f"| {t['side']} | {t['entry']} | {t['sl']} | {lvl(1)} | {lvl(2)} | {lvl(3)} | {t['risk']} |", ""]
    if snap.get("mtf"):
        lines += ["**Trend table:** " + " · ".join(f"{k} {_dot(v)}" for k, v in snap["mtf"].items()), ""]
    if snap.get("problems"):
        lines += ["⚠️ Notes on this capture: " + "; ".join(snap["problems"]), ""]

    lines += ["## 📒 Trade log (latest 15)", "",
              "| # | Signal | Signalled | Entry | SL | Targets hit | Result | R |",
              "|---|---|---|---|---|---|---|---|"]
    for r in reversed(trades[-15:]):
        entry = r["entry"] or (f"~{r['price_est']}" if r["price_est"] else "")
        lines.append(f"| {r['id']} | {r['signal']} | {_ist(r['signal_time_utc'])} | {entry} | {r['sl']} "
                     f"| {r['tp_hits'] or '-'} | {r['result']} | {r['r']} |")
    lines += ["", scoreboard(trades), "",
              "Entries marked ~ are estimated from the chart; exact levels are only shown for the live trade.", "",
              "Full analysis: [ANALYSIS.md](ANALYSIS.md) · data: [trades.csv](data/trades.csv), "
              "[events.csv](data/events.csv), [levels.csv](data/levels.csv)", "",
              "![Latest chart capture](latest.jpg)", END]
    return "\n".join(lines)


def write_readme(path: Path, snap: dict, trades: list[dict]) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else f"{START}\n{END}\n"
    block = status_block(snap, trades)
    pattern = re.compile(re.escape(START) + ".*?" + re.escape(END), re.S)
    text = pattern.sub(lambda _: block, text) if pattern.search(text) else text + "\n" + block + "\n"
    path.write_text(text, encoding="utf-8")
