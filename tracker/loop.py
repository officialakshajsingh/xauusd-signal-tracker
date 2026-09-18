"""One step of the capture loop that runs inside the Claude cloud routine.

    python -m tracker.loop --until 2026-09-18T11:58Z

Each call captures a frame, commits data/ and README.md (plus the chart image once an hour) to the
current branch and pushes it, keeps the frame in /tmp/frames for the end-of-run analysis, then
waits so the next call lands about 9.5 minutes later. A call stays under the Bash tool's
10-minute limit. The last line printed is CONTINUE (call again) or DONE (deadline reached).
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

FRAMES = Path("/tmp/frames") if sys.platform != "win32" else Path("_frames")
CALL_SECONDS = 560  # capture + push + wait, per call


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True)


def _push(message: str, paths: list[str]) -> str:
    if not _git("config", "user.email").stdout.strip():
        _git("config", "user.name", "Claude")
        _git("config", "user.email", "noreply@anthropic.com")
    _git("add", *paths)
    if _git("diff", "--cached", "--quiet").returncode == 0:
        return "nothing to commit"
    _git("commit", "-q", "-m", message)
    branch = _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    for attempt in range(3):
        result = _git("push", "-q", "origin", "HEAD")
        if result.returncode == 0:
            return "pushed"
        time.sleep(5 * (attempt + 1))
        _git("pull", "-q", "--rebase", "origin", branch)  # someone else pushed first
    return "push failed: " + result.stderr.strip()[-300:]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--until", required=True, help="UTC deadline, e.g. 2026-09-18T11:58Z")
    args = ap.parse_args()
    deadline = datetime.strptime(args.until, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)

    started = time.monotonic()
    now = datetime.now(timezone.utc)
    FRAMES.mkdir(parents=True, exist_ok=True)
    frame = FRAMES / f"{now:%Y%m%d_%H%M}.jpg"
    run = subprocess.run([sys.executable, "-m", "tracker.main", "--frame-out", str(frame)],
                         capture_output=True, text=True, timeout=300)
    summary = (run.stdout.strip().splitlines() or ["(no output)"])[-1][:300]
    failed = "capture failed" in run.stderr
    if failed:
        summary = run.stderr.strip().splitlines()[-1][:300]

    paths = ["data", "README.md"]
    if frame.exists() and now.minute < 10:  # refresh the README chart image once an hour
        shutil.copy(frame, "latest.jpg")
        paths.append("latest.jpg")
    pushed = _push(f"capture {now:%Y-%m-%dT%H:%MZ}", paths)
    print(f"{now:%H:%M}Z {'FAILED' if failed else 'ok'} | {pushed} | {summary}")

    next_call = now + timedelta(seconds=CALL_SECONDS + 30)
    if next_call >= deadline:
        print("DONE")
        return 0
    time.sleep(max(0, CALL_SECONDS - (time.monotonic() - started)))
    print("CONTINUE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
