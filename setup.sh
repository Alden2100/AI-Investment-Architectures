#!/usr/bin/env bash
# Create the venv and install pinned dependencies.
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip >/dev/null
./.venv/bin/python -m pip install -r requirements.txt
echo "venv ready. Next: ./.venv/bin/python link.py && see SETUP.md"
