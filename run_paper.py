"""
run_paper.py - what the daily scheduled task runs.

1. Runs paper_trade.py. A scheduled run has no window, so its output is appended to
   paper/run_log.txt (local only, not committed).
2. If new days were logged, commits only paper/daily_log.csv and paper/fills.csv with the
   message "paper: <date>" ("paper: <first> to <last>" after a catch-up), then pushes.
   Nothing else in the repo is committed, even if other changes are staged.
If paper_trade.py fails, nothing is committed. If the push fails, the commit stays local
and goes up with the next successful push.

Scheduled as the Windows task "HL paper trade": daily at 10:30 Brisbane (00:30 UTC), run with
pythonw.exe so no window opens. Run by hand: python run_paper.py
"""
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
LOGS = ["paper/daily_log.csv", "paper/fills.csv"]
RUN_LOG = ROOT / "paper" / "run_log.txt"


def logged_dates():
    path = ROOT / LOGS[0]
    return list(pd.read_csv(path, usecols=["date"])["date"]) if path.exists() else []


def run(cmd, log):
    try:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    except OSError as e:
        log.write(f"could not run {cmd[0]}: {e}\n")
        return 1
    log.write(r.stdout + r.stderr)
    return r.returncode


def main():
    RUN_LOG.parent.mkdir(exist_ok=True)
    with open(RUN_LOG, "a", encoding="utf-8") as log:
        log.write(f"\n=== {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC\n")
        before = logged_dates()
        if run([sys.executable, "paper_trade.py"], log) != 0:
            log.write("paper_trade.py failed; nothing committed.\n")
            sys.exit(1)

        new = logged_dates()[len(before):]
        if not new:
            log.write("No new days; nothing to commit.\n")
            return
        msg = f"paper: {new[0]}" if len(new) == 1 else f"paper: {new[0]} to {new[-1]}"
        if run(["git", "commit", "-m", msg, "--", *LOGS], log) != 0:
            log.write("git commit failed.\n")
            sys.exit(1)
        if run(["git", "push"], log) != 0:
            log.write("git push failed; the commit is saved locally and goes up with the next push.\n")
            sys.exit(1)
        log.write(f"Committed and pushed: {msg}\n")


if __name__ == "__main__":
    main()
