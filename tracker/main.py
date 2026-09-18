"""Capture one frame of the stream, extract it, and update data/ and README.md.

    python -m tracker.main                      # live capture
    python -m tracker.main --frame some.png     # re-process a saved frame
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from . import extract, report, store

VIDEO_URL = "https://www.youtube.com/watch?v=3H4IVQejlDE"
# 24/7 streams sometimes restart under a new video id; fall back to whatever the channel has live
CHANNEL_LIVE_URL = "https://www.youtube.com/@DTradingTips/live"


ATTEMPTS = 3  # YouTube's bot check is intermittent from cloud IPs; a retry usually gets through


def _stream_info() -> dict:
    from yt_dlp import YoutubeDL

    opts = {"quiet": True, "no_warnings": True,
            "format": "270/bestvideo[height<=1080][protocol^=m3u8]/best[height<=1080]",
            # YouTube's player challenges need a JS runtime; cloud images ship Node, deno is yt-dlp's default
            "js_runtimes": {"deno": {}, "node": {}}}
    errors = []
    for attempt in range(ATTEMPTS):
        for page in (VIDEO_URL, CHANNEL_LIVE_URL):
            try:
                with YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(page, download=False)
            except Exception as e:  # noqa: BLE001 - try the next source
                errors.append(f"{page}: {e}")
                continue
            title = info.get("title") or ""
            if info.get("is_live") and ("XAU" in title.upper() or "GOLD" in title.upper()):
                return info
            errors.append(f"{page}: not a live gold stream ({info.get('live_status')}: {title})")
        time.sleep(5 * (attempt + 1))
    raise RuntimeError("no live XAU/USD stream found:\n" + "\n".join(errors[-4:]))


def _fetch(url: str, headers: dict) -> bytes:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def grab_frame(dest: Path) -> str:
    """Download the newest HLS segment ourselves and decode it locally.

    Letting ffmpeg open the stream URL directly crashes the static ffmpeg build on some Linux
    images (its DNS lookups segfault), and a local file is all it needs anyway.
    """
    import imageio_ffmpeg

    info = _stream_info()
    headers = {k: v for k, v in (info.get("http_headers") or {}).items() if k.lower() != "accept-encoding"}
    playlist = _fetch(info["url"], headers).decode("utf-8", "replace")
    segments = [line for line in playlist.splitlines() if line and not line.startswith("#")]
    if not segments:
        raise RuntimeError("stream playlist has no segments")
    segment = dest.with_suffix(".ts")
    segment.write_bytes(_fetch(urllib.parse.urljoin(info["url"], segments[-1]), headers))
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
                    "-i", str(segment), "-frames:v", "1", "-y", str(dest)], check=True, timeout=60)
    return f"{info.get('id')} | {info.get('title')}"


def _set_status(data_dir: Path, now: datetime, error: str | None) -> None:
    """data/capture_status.json drives the workflow's "capture failing" issue."""
    path = data_dir / "capture_status.json"
    status = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    stamp = f"{now:%Y-%m-%dT%H:%M:%SZ}"
    if error:
        status["consecutive_failures"] = status.get("consecutive_failures", 0) + 1
        status["last_error"] = error
        status["last_error_utc"] = stamp
    else:
        status["consecutive_failures"] = 0
        status["last_ok_utc"] = stamp
    path.write_text(json.dumps(status, indent=1) + "\n", encoding="utf-8")


def _record_failure(args: argparse.Namespace, now: datetime, err: Exception) -> None:
    msg = f"{now:%Y-%m-%dT%H:%M:%SZ} {type(err).__name__}: {err}".replace("\n", " | ")[:600]
    print("capture failed:", msg, file=sys.stderr)
    args.data_dir.mkdir(parents=True, exist_ok=True)
    _set_status(args.data_dir, now, msg)
    log = args.data_dir / "capture_errors.log"
    lines = (log.read_text(encoding="utf-8").splitlines() if log.exists() else [])[-199:] + [msg]
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    latest = args.data_dir / "latest.json"
    if latest.exists():
        snap = json.loads(latest.read_text(encoding="utf-8"))
        snap["problems"] = snap.get("problems", []) + [
            f"newest capture failed at {now:%H:%M} UTC ({type(err).__name__}); showing the last good one"]
        report.write_readme(args.readme, snap, store.read_trades(args.data_dir))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", type=Path, help="process this image instead of capturing")
    ap.add_argument("--data-dir", type=Path, default=Path("data"))
    ap.add_argument("--readme", type=Path, default=Path("README.md"))
    ap.add_argument("--frame-out", type=Path, help="save a JPEG of the chart area here")
    args = ap.parse_args()

    now = datetime.now(timezone.utc).replace(microsecond=0)
    if args.frame:
        frame_path, source = args.frame, f"file {args.frame}"
    else:
        frame_path = Path(tempfile.mkdtemp()) / "frame.png"
        try:
            source = grab_frame(frame_path)
        except Exception as e:  # noqa: BLE001
            # log it and exit cleanly: a failing scheduled job would email every 10 minutes
            _record_failure(args, now, e)
            return 0

    frame = Image.open(frame_path).convert("RGB")
    snap = extract.extract(frame, now)
    snap["source"] = source
    trades, _ = store.update(args.data_dir, snap)
    report.write_readme(args.readme, snap, trades)
    if not args.frame:
        _set_status(args.data_dir, now, None)

    if args.frame_out:
        chart = frame.resize(extract.FRAME_SIZE).crop(extract.CHART_BOX)
        chart.save(args.frame_out, "JPEG", quality=80, optimize=True)

    print(json.dumps({k: snap.get(k) for k in ("captured_utc", "price", "position", "trade", "problems")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
