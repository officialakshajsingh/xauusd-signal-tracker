"""The hourly capture the Claude cloud routine runs: capture once, then commit and push.

    python -m tracker.run

Saves the chart as latest.jpg (shown in the README) and in /tmp/frames for the analysis step,
commits data/, README.md and latest.jpg to the current branch and pushes. Prints one summary line.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

FRAMES = Path("/tmp/frames") if sys.platform != "win32" else Path("_frames")


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
    now = datetime.now(timezone.utc)
    FRAMES.mkdir(parents=True, exist_ok=True)
    frame = FRAMES / f"{now:%Y%m%d_%H%M}.jpg"
    run = subprocess.run([sys.executable, "-m", "tracker.main", "--frame-out", str(frame)],
                         capture_output=True, text=True, timeout=300)
    failed = "capture failed" in run.stderr
    summary = (run.stderr if failed else run.stdout).strip().splitlines() or ["(no output)"]

    paths = ["data", "README.md"]
    if frame.exists():
        shutil.copy(frame, "latest.jpg")
        paths.append("latest.jpg")
    pushed = _push(f"capture {now:%Y-%m-%dT%H:%MZ}", paths)
    print(f"{now:%H:%M}Z {'FAILED' if failed else 'ok'} | {pushed} | frame {frame if frame.exists() else '-'} "
          f"| {summary[-1][:400]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
