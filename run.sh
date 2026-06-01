#!/usr/bin/env bash
# Quick launcher — sets up venv on first run, then executes the agent.
# Usage:
#   ./run.sh              → run once
#   ./run.sh --every 1h   → run every hour

set -euo pipefail
cd "$(dirname "$0")"

VENV=".venv"

if [ ! -d "$VENV" ]; then
  echo "Creating virtual environment..."
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip
  "$VENV/bin/pip" install --quiet -r requirements.txt
  echo "Dependencies installed."
fi

# Load .env if it exists
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

exec "$VENV/bin/python" schedule.py "$@"
