"""Scheduler wrapper — run the agent on a fixed interval or via cron.

Usage:
  python schedule.py              # run once immediately
  python schedule.py --every 1h  # run every hour
  python schedule.py --every 30m # run every 30 minutes
  python schedule.py --every 1d  # run once a day
"""

import argparse
import time
import subprocess
import sys
from datetime import datetime


def parse_interval(s: str) -> int:
    """Convert '1h', '30m', '1d' to seconds."""
    unit = s[-1].lower()
    value = int(s[:-1])
    return {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit] * value


def run_agent() -> None:
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Running agent...")
    result = subprocess.run([sys.executable, "agent.py"], capture_output=False)
    if result.returncode != 0:
        print(f"Agent exited with code {result.returncode}")


def main() -> None:
    parser = argparse.ArgumentParser(description="CSV analysis agent scheduler")
    parser.add_argument(
        "--every",
        metavar="INTERVAL",
        help="Repeat interval: e.g. 30m, 1h, 1d. Omit to run once.",
    )
    args = parser.parse_args()

    if args.every is None:
        run_agent()
        return

    interval = parse_interval(args.every)
    print(f"Scheduler started — running every {args.every} ({interval}s). Ctrl+C to stop.")
    while True:
        run_agent()
        print(f"Next run in {args.every}...")
        time.sleep(interval)


if __name__ == "__main__":
    main()
