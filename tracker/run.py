"""One capture, then commit and push. Used by the GitHub Actions job and the Windows scheduled task.

    python -m tracker.run

Updates data/<SYMBOL>/ and README.md, refreshes latest-<SYMBOL>.jpg (on the first capture of each
hour, to keep the repository small), keeps the frame in the frames folder for the analysis step,
commits to the current branch and pushes. Prints one summary line.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

FRAMES = Path("/tmp/frames") if sys.platform != "win32" else Path("_frames")
KEEP_FRAMES = 300
NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _run(*cmd: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW)


def _git(*args: str) -> subprocess.CompletedProcess:
    return _run("git", *args)


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
    run = _run(sys.executable, "-m", "tracker.main", "--frame-out", str(frame), timeout=300)
    failed = "capture failed" in run.stderr
    summary = (run.stderr if failed else run.stdout).strip().splitlines() or ["(no output)"]

    paths = ["data", "README.md"]
    status_file = Path("data/capture_status.json")
    symbol = json.loads(status_file.read_text(encoding="utf-8")).get("last_symbol") if status_file.exists() else None
    if frame.exists() and symbol and now.minute < 10:
        shutil.copy(frame, f"latest-{symbol}.jpg")
        paths.append(f"latest-{symbol}.jpg")
    for old in sorted(FRAMES.glob("*.jpg"))[:-KEEP_FRAMES]:
        old.unlink(missing_ok=True)

    pushed = _push(f"capture {symbol or ''} {now:%Y-%m-%dT%H:%MZ}".replace("  ", " "), paths)
    print(f"{now:%Y-%m-%d %H:%M}Z {'FAILED' if failed else 'ok'} {symbol or ''} | {pushed} | "
          f"{summary[-1][:400]}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
