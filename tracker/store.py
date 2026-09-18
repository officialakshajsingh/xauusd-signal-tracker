"""Turn each capture into the running trade log.

The chart keeps about 4 hours of history, so an hourly capture sees every Buy/Sell/TP marker since
the previous one. Markers are merged into events.csv, and trades.csv is rebuilt from them each time:
a trade runs from one Buy/Sell signal to the next, and its result is the best TP marker printed in
between. The exact entry/SL/TP levels are only drawn for the live trade, so levels.csv keeps every
set seen and the rebuild attaches them to the matching signal.

data/snapshots/YYYY-MM.jsonl  every capture, as extracted (minus the marker list)
data/events.csv               every Buy/Sell/TP marker seen on the chart, de-duplicated
data/levels.csv               exact levels of the live trade at each capture, one row per trade
data/trades.csv               rebuilt trade list with results
data/latest.json              the most recent snapshot in full
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta
from pathlib import Path

EVENT_FIELDS = ["label", "time_utc", "price_est", "first_seen_utc"]
LEVEL_FIELDS = ["signal", "signal_time_utc", "side", "entry", "sl", "tp1", "tp2", "tp3", "risk",
                "first_seen_utc", "last_seen_utc", "captures", "max_price", "min_price",
                "trend_at_first_seen", "mtf_at_first_seen"]
TRADE_FIELDS = ["id", "signal", "side", "signal_time_utc", "price_est", "entry", "sl", "tp1", "tp2", "tp3",
                "risk", "tp_hits", "status", "result", "r", "closed_by_utc", "trend", "mtf"]
FMT = "%Y-%m-%dT%H:%MZ"
SAME_EVENT = timedelta(minutes=3)      # marker times are estimated from pixel positions
DUPLICATE_SIGNAL = timedelta(minutes=8)  # signals alternate; two same-side ones this close are one marker


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _t(s: str) -> datetime:
    return datetime.strptime(s, FMT)


def _mtf_compact(snap: dict) -> str:
    return " ".join(f"{k}{'+' if v in ('Bullish', 'Buy') else '-'}" for k, v in snap.get("mtf", {}).items())


def _merge_events(events: list[dict], snap: dict) -> None:
    for mk in snap.get("markers", []):
        if not mk.get("time_utc"):
            continue
        t = _t(mk["time_utc"])
        if any(e["label"] == mk["label"] and abs(_t(e["time_utc"]) - t) <= SAME_EVENT for e in events):
            continue
        events.append({"label": mk["label"], "time_utc": mk["time_utc"],
                       "price_est": mk.get("price_est", ""), "first_seen_utc": snap["captured_utc"]})
    events.sort(key=lambda e: e["time_utc"])


def _merge_levels(levels: list[dict], snap: dict) -> None:
    t, price, now = snap.get("trade"), snap.get("price"), snap["captured_utc"]
    if not t:
        return
    row = next((r for r in levels if r["side"] == t["side"] and abs(float(r["entry"]) - t["entry"]) < 0.005
                and abs(float(r["sl"]) - t["sl"]) < 0.005), None)
    if row is None:
        row = dict.fromkeys(LEVEL_FIELDS, "") | {
            "side": t["side"], "entry": t["entry"], "sl": t["sl"], "risk": t["risk"], "first_seen_utc": now,
            "captures": 0, "trend_at_first_seen": snap.get("trend") or "", "mtf_at_first_seen": _mtf_compact(snap)}
        levels.append(row)
    for key in ("signal", "signal_time_utc", "tp1", "tp2", "tp3"):
        if not row.get(key) and t.get(key):  # OCR can miss a label on one capture and read it on the next
            row[key] = t[key]
    row["last_seen_utc"] = now
    row["captures"] = int(row["captures"] or 0) + 1
    if price:
        row["max_price"] = max(float(row["max_price"] or price), price)
        row["min_price"] = min(float(row["min_price"] or price), price)


def _rebuild_trades(events: list[dict], levels: list[dict]) -> list[dict]:
    signals: list[dict] = []
    for e in events:
        if not e["label"].startswith(("Buy", "Sell")):
            continue
        side = "Buy" if e["label"].startswith("Buy") else "Sell"
        if signals and signals[-1]["side"] == side and _t(e["time_utc"]) - _t(signals[-1]["time_utc"]) <= DUPLICATE_SIGNAL:
            continue
        signals.append({**e, "side": side})

    trades = []
    for i, s in enumerate(signals):
        start = _t(s["time_utc"])
        end = _t(signals[i + 1]["time_utc"]) if i + 1 < len(signals) else None
        hits = sorted({e["label"] for e in events if e["label"].startswith("TP")
                       and start < _t(e["time_utc"]) and (end is None or _t(e["time_utc"]) < end)})
        best = max((int(h[2]) for h in hits), default=0)
        lv = next((r for r in levels if r["side"] == s["side"] and r["signal_time_utc"]
                   and abs(_t(r["signal_time_utc"]) - start) <= SAME_EVENT), {})
        if end is None:
            status, result, r = "open", (f"TP{best} so far" if best else "running"), ""
        elif best:
            status, result, r = "closed", f"TP{best}", best
        else:
            # reversed before TP1; the stop may or may not have been hit first, so count the worst case
            status, result, r = "closed", "No TP", -1
        trades.append({
            "id": i + 1, "signal": s["label"], "side": s["side"], "signal_time_utc": s["time_utc"],
            "price_est": s["price_est"], "entry": lv.get("entry", ""), "sl": lv.get("sl", ""),
            "tp1": lv.get("tp1", ""), "tp2": lv.get("tp2", ""), "tp3": lv.get("tp3", ""), "risk": lv.get("risk", ""),
            "tp_hits": " ".join(f"TP{n}" for n in range(1, best + 1)), "status": status, "result": result, "r": r,
            "closed_by_utc": signals[i + 1]["time_utc"] if end else "",
            "trend": lv.get("trend_at_first_seen", ""), "mtf": lv.get("mtf_at_first_seen", ""),
        })
    return trades


def read_trades(data_dir: Path) -> list[dict]:
    return _read(data_dir / "trades.csv")


def update(data_dir: Path, snap: dict) -> list[dict]:
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "snapshots").mkdir(exist_ok=True)
    lean = {k: v for k, v in snap.items() if k != "markers"}
    with (data_dir / "snapshots" / f"{snap['captured_utc'][:7]}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(lean) + "\n")
    (data_dir / "latest.json").write_text(json.dumps(snap, indent=1), encoding="utf-8")

    events = _read(data_dir / "events.csv")
    _merge_events(events, snap)
    _write(data_dir / "events.csv", EVENT_FIELDS, events)

    levels = _read(data_dir / "levels.csv")
    _merge_levels(levels, snap)
    _write(data_dir / "levels.csv", LEVEL_FIELDS, levels)

    trades = _rebuild_trades(events, levels)
    _write(data_dir / "trades.csv", TRADE_FIELDS, trades)
    return trades
