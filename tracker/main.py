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
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from . import extract, report, store

VIDEO_URL = "https://www.youtube.com/watch?v=3H4IVQejlDE"
# 24/7 streams sometimes restart under a new video id; fall back to whatever the channel has live
CHANNEL_LIVE_URL = "https://www.youtube.com/@DTradingTips/live"


def _stream_url() -> tuple[str, str]:
    from yt_dlp import YoutubeDL

    opts = {"quiet": True, "no_warnings": True,
            "format": "270/bestvideo[height<=1080][protocol^=m3u8]/best[height<=1080]",
            # YouTube's player challenges need a JS runtime; runners ship Node, deno is yt-dlp's default
            "js_runtimes": {"deno": {}, "node": {}}}
    errors = []
    for page in (VIDEO_URL, CHANNEL_LIVE_URL):
        try:
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(page, download=False)
        except Exception as e:  # noqa: BLE001 - try the next source
            errors.append(f"{page}: {e}")
            continue
        title = info.get("title") or ""
        if info.get("is_live") and ("XAU" in title.upper() or "GOLD" in title.upper()):
            return info["url"], f"{info.get('id')} | {title}"
        errors.append(f"{page}: not a live gold stream ({info.get('live_status')}: {title})")
    raise RuntimeError("no live XAU/USD stream found:\n" + "\n".join(errors))


def grab_frame(dest: Path) -> str:
    import imageio_ffmpeg

    url, source = _stream_url()
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
                    "-live_start_index", "-1", "-i", url, "-frames:v", "1", "-y", str(dest)],
                   check=True, timeout=120)
    return source


def _record_failure(args: argparse.Namespace, now: datetime, err: Exception) -> None:
    msg = f"{now:%Y-%m-%dT%H:%M:%SZ} {type(err).__name__}: {err}".replace("\n", " | ")[:600]
    print("capture failed:", msg, file=sys.stderr)
    args.data_dir.mkdir(parents=True, exist_ok=True)
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

    if args.frame_out:
        chart = frame.resize(extract.FRAME_SIZE).crop(extract.CHART_BOX)
        chart.save(args.frame_out, "JPEG", quality=80, optimize=True)

    print(json.dumps({k: snap.get(k) for k in ("captured_utc", "price", "position", "trade", "problems")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
