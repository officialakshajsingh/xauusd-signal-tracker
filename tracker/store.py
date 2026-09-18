"""Turn each extracted snapshot into the running trade log.

data/snapshots/YYYY-MM.jsonl  every capture, as extracted (minus the marker list)
data/trades.csv               one row per trade the indicator opened, with its outcome
data/events.csv               every Buy/Sell/TP marker seen on the chart, de-duplicated
data/latest.json              the most recent snapshot in full
"""
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

TRADE_FIELDS = [
    "id", "side", "signal", "signal_time_utc", "entry", "sl", "tp1", "tp2", "tp3", "risk",
    "first_seen_utc", "last_seen_utc", "snapshots", "status", "max_price", "min_price",
    "tp1_hit", "tp2_hit", "tp3_hit", "sl_hit", "closed_utc", "exit_price", "result", "r",
    "trend_at_open", "mtf_at_open",
]
EVENT_FIELDS = ["label", "time_utc", "price_est", "first_seen_utc"]
SAME_EVENT_MINUTES = 3  # marker times are estimated from pixel position, so allow some drift


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


def _num(v) -> float | None:
    return None if v in ("", None) else float(v)


def _mtf_compact(snap: dict) -> str:
    return " ".join(f"{k}{'+' if v in ('Bullish', 'Buy') else '-'}" for k, v in snap.get("mtf", {}).items())


def _close(row: dict, now: str, exit_price: float | None) -> None:
    row["status"] = "closed"
    row["closed_utc"] = now
    entry, risk = float(row["entry"]), float(row["risk"])
    best = max((n for n in (1, 2, 3) if row[f"tp{n}_hit"]), default=0)
    if best:
        row["result"], r = f"TP{best}", float(best)
    elif row["sl_hit"]:
        row["result"], r = "SL", -1.0
    else:
        # the indicator flipped to a new signal before any target or the stop was reached
        row["result"] = "Reversed"
        r = 0.0
        if exit_price is not None and risk:
            move = exit_price - entry if row["side"] == "Buy" else entry - exit_price
            r = max(move / risk, -1.0)
    row["exit_price"] = "" if exit_price is None else exit_price
    row["r"] = round(r, 2)


def _update_trades(trades: list[dict], snap: dict) -> None:
    now, price, t = snap["captured_utc"], snap.get("price"), snap.get("trade")
    if not t:
        return
    current = next((r for r in trades if r["side"] == t["side"]
                    and abs(float(r["entry"]) - t["entry"]) < 0.005
                    and abs(float(r["sl"]) - t["sl"]) < 0.005), None)
    if current is None:
        for r in trades:
            if r["status"] == "open":
                _close(r, now, exit_price=t["entry"])
        current = dict.fromkeys(TRADE_FIELDS, "") | {
            "id": len(trades) + 1, "side": t["side"], "signal": t.get("signal", ""),
            "signal_time_utc": t.get("signal_time_utc") or "", "entry": t["entry"], "sl": t["sl"],
            "tp1": t["tp1"], "tp2": t.get("tp2", ""), "tp3": t.get("tp3", ""), "risk": t["risk"],
            "first_seen_utc": now, "snapshots": 0, "status": "open",
            "max_price": price or "", "min_price": price or "",
            "tp1_hit": "", "tp2_hit": "", "tp3_hit": "", "sl_hit": "",
            "trend_at_open": snap.get("trend") or "", "mtf_at_open": _mtf_compact(snap),
        }
        trades.append(current)

    current["last_seen_utc"] = now
    current["snapshots"] = int(current["snapshots"]) + 1
    if price:
        current["max_price"] = max(float(current["max_price"] or price), price)
        current["min_price"] = min(float(current["min_price"] or price), price)

    # targets reached: TP markers drawn after the signal, or a captured price beyond the level
    best_marker = max((int(m[2]) for m in t.get("tp_markers_since_signal", [])), default=0)
    buy = t["side"] == "Buy"
    best = _num(current["max_price"] if buy else current["min_price"])
    worst = _num(current["min_price"] if buy else current["max_price"])
    for n in (1, 2, 3):
        level = _num(current[f"tp{n}"])
        if level is None:
            continue
        crossed = best is not None and (best >= level if buy else best <= level)
        if n <= best_marker or crossed:
            current[f"tp{n}_hit"] = "yes"
    sl = float(current["sl"])
    if worst is not None and (worst <= sl if buy else worst >= sl):
        current["sl_hit"] = "yes"


def _merge_events(events: list[dict], snap: dict) -> None:
    fmt = "%Y-%m-%dT%H:%MZ"
    for mk in snap.get("markers", []):
        if not mk.get("time_utc"):
            continue
        t = datetime.strptime(mk["time_utc"], fmt)
        if any(e["label"] == mk["label"]
               and abs((datetime.strptime(e["time_utc"], fmt) - t).total_seconds()) <= SAME_EVENT_MINUTES * 60
               for e in events):
            continue
        events.append({"label": mk["label"], "time_utc": mk["time_utc"],
                       "price_est": mk.get("price_est", ""), "first_seen_utc": snap["captured_utc"]})
    events.sort(key=lambda e: e["time_utc"])


def read_trades(data_dir: Path) -> list[dict]:
    return _read(data_dir / "trades.csv")


def update(data_dir: Path, snap: dict) -> tuple[list[dict], list[dict]]:
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "snapshots").mkdir(exist_ok=True)
    month = snap["captured_utc"][:7]
    lean = {k: v for k, v in snap.items() if k != "markers"}
    with (data_dir / "snapshots" / f"{month}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(lean) + "\n")
    (data_dir / "latest.json").write_text(json.dumps(snap, indent=1), encoding="utf-8")

    trades = _read(data_dir / "trades.csv")
    _update_trades(trades, snap)
    _write(data_dir / "trades.csv", TRADE_FIELDS, trades)

    events = _read(data_dir / "events.csv")
    _merge_events(events, snap)
    _write(data_dir / "events.csv", EVENT_FIELDS, events)
    return trades, events
