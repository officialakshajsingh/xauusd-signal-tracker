"""Read the trade data off one frame of the stream with OCR.

The stream is a 1920x1080 layout with a TradingView chart on the left. We OCR
the chart area and pick out, by pattern and position:

- price-axis labels  -> a y->price fit (and the live price label with its countdown)
- time-axis labels   -> an x->time fit
- level labels       -> "TP1 (4378.9457)", "Entry (4370.93)", "SL (4362.9143)"
- chart markers      -> "Buy", "Buy+", "Sell", "Sell+", "TP1".."TP3"
- the trend table    -> "Current Position: Buy", "1 min: Bullish", ...
- header / clock     -> "XAUUSD 4,385.85 +1.03%", "10:07:46 UTC+4"
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
from PIL import Image

FRAME_SIZE = (1920, 1080)
CHART_BOX = (0, 80, 1580, 1010)  # chart widget inside the 1920x1080 stream layout
SCALE = 2  # upscale before OCR; small chart text reads far better at 2x

# price formats differ by instrument: gold "4,396.00", bitcoin "81,320.00"
NUM_AXIS = re.compile(r"^\d{1,3}(?:,\d{3})*\.\d{2}$")
HHMM = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
LEVEL = re.compile(r"^(TP[123]|Entry|SL)\s*\(?\s*(\d{2,7}\.\d+)\s*\)?$", re.I)
CLOCK = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})\s*UTC\s*([+-]\d{1,2})(?::?(\d{2}))?", re.I)
HEADER = re.compile(r"[A-Z]{3,12}\D*?(\d{1,3}(?:,\d{3})*\.\d{2})\D*?(\d+\.\d{2})%")
HEADER_BOX = (10, 84, 300, 108)  # "XAUUSD 4,385.85 +1.03%" in the chart's top-left corner
ROW = re.compile(r"^(current\s*position|current\s*trend|\d+\s*min|\d+\s*h|daily)\s*:?\s*"
                 r"(buy|sell|bullish|bearish|neutral)?$", re.I)
VALUE = re.compile(r"^(buy|sell|bullish|bearish|neutral)$", re.I)

_engine = None


def _ocr():
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _engine = RapidOCR()
    return _engine


@dataclass
class Item:
    text: str
    x: float   # centre, in 1920x1080 frame pixels
    y: float
    x0: float
    x1: float
    conf: float


def ocr_items(frame: Image.Image) -> list[Item]:
    if frame.size != FRAME_SIZE:
        frame = frame.resize(FRAME_SIZE, Image.LANCZOS)
    region = frame.convert("RGB").crop(CHART_BOX)
    big = region.resize((region.width * SCALE, region.height * SCALE), Image.LANCZOS)
    result, _ = _ocr()(np.array(big))
    items = []
    for box, text, conf in result or []:
        xs = [p[0] / SCALE + CHART_BOX[0] for p in box]
        ys = [p[1] / SCALE + CHART_BOX[1] for p in box]
        items.append(Item(text.strip(), (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2,
                          min(xs), max(xs), float(conf)))
    return items


def read_header(frame: Image.Image) -> tuple[float, float] | None:
    """Price and day change from the tiny header. OCR drops the +/- sign, so take it from the text colour."""
    crop = frame.convert("RGB").crop(HEADER_BOX)
    big = crop.resize((crop.width * 4, crop.height * 4), Image.LANCZOS)
    result, _ = _ocr()(np.array(big))
    m = HEADER.search("".join(r[1] for r in result or []).replace(" ", ""))
    if not m:
        return None
    px = np.array(crop).astype(int)
    r, g = px[..., 0], px[..., 1]
    green = ((g - r > 40) & (g > 100)).sum()
    red = ((r - g > 60) & (r > 150)).sum()
    sign = -1 if red > green else 1
    return float(m.group(1).replace(",", "")), sign * float(m.group(2))


def _colour_markers(frame: Image.Image, axis_x: float) -> tuple[list[dict], list[tuple[float, float]]]:
    """Signal label boxes (cyan Buy, pink Sell) and the small green TP-hit dots on the chart."""
    import cv2

    rgb = np.array(frame.convert("RGB"))
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)  # OpenCV hue runs 0-179
    h, s, v = (hsv[..., i].astype(int) for i in range(3))
    area = np.zeros(h.shape, bool)
    area[110:940, 15:int(min(axis_x, 1500))] = True  # chart plot area, left of the price axis

    def components(mask):
        n, _, stats, centres = cv2.connectedComponentsWithStats((mask & area).astype(np.uint8), 8)
        return [(float(centres[i][0]), float(centres[i][1]), int(stats[i][2]), int(stats[i][3]), int(stats[i][4]))
                for i in range(1, n)]

    boxes = []
    for side, hue in (("Buy", (85, 100)), ("Sell", (160, 174))):
        mask = (h >= hue[0]) & (h <= hue[1]) & (s > 120) & (v > 150)
        for x, y, w, ht, px in components(mask):
            if 24 <= w <= 45 and 24 <= ht <= 36 and 450 <= px <= 1100:  # label box incl. its pointer
                boxes.append({"side": side, "x": x, "y": y, "w": w})

    green = (h >= 40) & (h <= 70) & (s > 120) & (v > 120)
    comps = components(green)
    big = [(x, y, w, ht) for x, y, w, ht, px in comps if px > 300]  # TP level labels, not dots
    dots = [(x, y) for x, y, w, ht, px in comps if 6 <= px <= 20 and w <= 5 and ht <= 5
            and not any(abs(x - bx) <= bw / 2 + 12 and abs(y - by) <= bh / 2 + 6 for bx, by, bw, bh in big)]
    return boxes, dots


def _largest_group(values: list[float], width: float) -> list[int]:
    """Indices of the biggest cluster of values that sit within `width` of each other."""
    best: list[int] = []
    for v in values:
        group = [i for i, w in enumerate(values) if abs(w - v) <= width]
        if len(group) > len(best):
            best = group
    return best


def _robust_fit(xs: list[float], ys: list[float]) -> tuple[float, float] | None:
    xs, ys = np.array(xs, float), np.array(ys, float)
    keep = np.ones(len(xs), bool)
    for _ in range(3):
        if keep.sum() < 2:
            return None
        a, b = np.polyfit(xs[keep], ys[keep], 1)
        resid = np.abs(ys - (a * xs + b))
        tol = max(np.median(resid[keep]) * 4, 1e-6)
        new_keep = resid <= tol
        if (new_keep == keep).all():
            break
        keep = new_keep
    return float(a), float(b)


def _norm_row(label: str) -> str:
    s = re.sub(r"\s+", "", label.lower()).rstrip(":")
    if s == "currentposition":
        return "position"
    if s == "currenttrend":
        return "trend"
    if s == "daily":
        return "D"
    m = re.match(r"(\d+)min", s)
    if m:
        return f"{m.group(1)}m"
    m = re.match(r"(\d+)h", s)
    return f"{m.group(1)}H" if m else s


def extract(frame: Image.Image, captured_utc: datetime) -> dict:
    if frame.size != FRAME_SIZE:
        frame = frame.resize(FRAME_SIZE, Image.LANCZOS)
    items = ocr_items(frame)
    used: set[int] = set()
    out: dict = {"captured_utc": captured_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), "problems": []}

    # --- header price and clock -------------------------------------------------
    if header := read_header(frame):
        out["header_price"], out["day_change_pct"] = header
    for it in items:
        if m := CLOCK.search(it.text):
            sign = -1 if m.group(4).startswith("-") else 1
            out["chart_tz_minutes"] = sign * (abs(int(m.group(4))) * 60 + int(m.group(5) or 0))
            out["chart_clock"] = f"{int(m.group(1)):02d}:{m.group(2)}:{m.group(3)}"
    tz_min = out.get("chart_tz_minutes", 240)

    # --- price axis -------------------------------------------------------------
    axis = [i for i, it in enumerate(items) if NUM_AXIS.match(it.text)]
    col = [axis[j] for j in _largest_group([items[i].x for i in axis], 25)]
    live = None
    for i in col:
        below = [it for it in items if HHMM.match(it.text) and 6 < it.y - items[i].y < 26
                 and abs(it.x - items[i].x) < 25]
        if below:
            live = i
            out["price"] = float(items[i].text.replace(",", ""))
            out["candle_countdown"] = below[0].text
    fit_pts = [i for i in col if i != live]
    price_fit = _robust_fit([items[i].y for i in fit_pts],
                            [float(items[i].text.replace(",", "")) for i in fit_pts]) if len(fit_pts) >= 3 else None
    axis_x = min((items[i].x0 for i in col), default=CHART_BOX[2])
    used.update(col)
    if "price" not in out and "header_price" in out:
        out["price"] = out["header_price"]
    if "price" not in out:
        out["problems"].append("no live price found")
    if price_fit is None:
        out["problems"].append("price axis not readable")

    # --- time axis --------------------------------------------------------------
    times = [i for i, it in enumerate(items) if HHMM.match(it.text) and it.x < axis_x]
    row = [times[j] for j in _largest_group([items[i].y for i in times], 8)]
    row.sort(key=lambda i: items[i].x)
    xs, mins, offset, prev = [], [], 0, -1
    for i in row:
        h, m = map(int, items[i].text.split(":"))
        v = h * 60 + m + offset
        if v < prev:  # crossed midnight
            offset += 1440
            v += 1440
        xs.append(items[i].x)
        mins.append(v)
        prev = v
    time_fit = _robust_fit(xs, mins) if len(xs) >= 3 else None
    used.update(row)
    if time_fit is None:
        out["problems"].append("time axis not readable")

    chart_now = captured_utc + timedelta(minutes=tz_min)

    def to_utc(x: float) -> str | None:
        if time_fit is None:
            return None
        m = time_fit[0] * x + time_fit[1]
        # axis minutes are relative to the chart-local day of the first label; anchor them to "now"
        day0 = chart_now.replace(hour=0, minute=0, second=0, microsecond=0)
        t = day0 + timedelta(minutes=m)
        while t > chart_now + timedelta(minutes=10):
            t -= timedelta(days=1)
        return (t - timedelta(minutes=tz_min)).strftime("%Y-%m-%dT%H:%MZ")

    def to_price(y: float) -> float | None:
        return round(price_fit[0] * y + price_fit[1], 2) if price_fit else None

    # --- trend table ------------------------------------------------------------
    mtf: dict[str, str] = {}
    for i, it in enumerate(items):
        m = ROW.match(it.text)
        if not m or it.x >= axis_x:
            continue
        key = _norm_row(m.group(1))
        value = m.group(2)
        if not value:
            cands = [j for j, v in enumerate(items) if j not in used and VALUE.match(v.text)
                     and abs(v.y - it.y) < 10 and 0 <= v.x0 - it.x1 < 200]
            if cands:
                j = min(cands, key=lambda j: items[j].x0 - it.x1)
                value = items[j].text
                used.add(j)
        if value:
            mtf[key] = value.capitalize()
            used.add(i)
    out["position"] = mtf.pop("position", None)
    out["trend"] = mtf.pop("trend", None)
    out["mtf"] = mtf
    if len(mtf) < 8:
        out["problems"].append(f"trend table only partly read ({len(mtf)} rows)")

    # --- trade levels -----------------------------------------------------------
    levels: dict[str, float] = {}
    for i, it in enumerate(items):
        if m := LEVEL.match(it.text.replace(" ", "")):
            name = m.group(1).upper() if m.group(1).lower() != "entry" else "ENTRY"
            levels[name.lower()] = float(m.group(2))
            used.add(i)
    if {"entry", "sl"} <= levels.keys():
        risk = abs(levels["entry"] - levels["sl"])
        side = "Buy" if levels["entry"] > levels["sl"] else "Sell"
        # candles sometimes cover a TP label; the indicator always sets TPn at exactly n x risk
        for n in (1, 2, 3):
            if f"tp{n}" not in levels and risk:
                levels[f"tp{n}"] = round(levels["entry"] + (n if side == "Buy" else -n) * risk, 4)
                out["problems"].append(f"TP{n} label hidden; derived from entry and SL")
        out["trade"] = {"side": side, **levels, "risk": round(risk, 4)}
    else:
        out["trade"] = None
        out["problems"].append("trade levels not found")

    # --- chart markers ----------------------------------------------------------
    # Signal labels are found by colour (cyan Buy, pink Sell boxes): candles often cover their text.
    # OCR only decides the "+". TP hits are the union of OCR'd "TP" labels and the green dot the
    # indicator draws on the hit candle, numbered in order after their signal (targets hit in order).
    boxes, dots = _colour_markers(frame, axis_x)
    signals = []
    for b in boxes:
        texts = [it.text for it in items if abs(it.x - b["x"]) <= b["w"] / 2 + 4 and abs(it.y - b["y"]) <= 14]
        plus = any("+" in t for t in texts) or (not texts and b["side"] == "Buy" and b["w"] >= 33)
        signals.append({"label": b["side"] + ("+" if plus else ""), "x": b["x"], "y": b["y"]})
    signals.sort(key=lambda s: s["x"])

    tp_points = [(it.x, it.y) for i, it in enumerate(items) if i not in used and it.x < axis_x
                 and re.fullmatch(r"TP[123]?", it.text.replace(" ", ""), re.I)]
    for dx, dy in dots:  # a dot belongs to a TP label a few pixels above or below it
        if not any(abs(dx - x) <= 10 and abs(dy - y) <= 26 for x, y in tp_points):
            tp_points.append((dx, dy))
    tps_by_signal: dict[int, list] = {}
    for x, y in sorted(tp_points):
        owner = max((i for i, s in enumerate(signals) if s["x"] < x), default=None)
        if owner is not None:  # TPs left of the first visible signal belong to an off-screen trade
            tps_by_signal.setdefault(owner, []).append((x, y))

    markers = [{"label": s["label"], "x": round(s["x"]), "time_utc": to_utc(s["x"]), "price_est": to_price(s["y"])}
               for s in signals]
    for owner, pts in tps_by_signal.items():
        for n, (x, y) in enumerate(pts[:3], start=1):
            markers.append({"label": f"TP{n}", "x": round(x), "time_utc": to_utc(x), "price_est": to_price(y)})
    markers.sort(key=lambda mk: mk["x"])
    out["markers"] = markers

    signals = [mk for mk in markers if mk["label"].startswith(("Buy", "Sell"))]
    if out["trade"] and signals:
        last = signals[-1]
        out["trade"]["signal"] = last["label"]
        out["trade"]["signal_time_utc"] = last["time_utc"]
        out["trade"]["tp_markers_since_signal"] = sorted(
            {mk["label"] for mk in markers if mk["label"].startswith("TP") and mk["x"] > last["x"]})
    return out
