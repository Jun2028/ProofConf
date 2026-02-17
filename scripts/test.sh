#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

TEST_ID="$(date -u +%Y-%m-%d_%H%M%SZ)_smoke"
LOG_DIR="$ROOT_DIR/logs/test/$TEST_ID"
mkdir -p "$LOG_DIR"

{
  echo "[test] id=$TEST_ID"
  echo "[test] cmd=uv run python scripts/smoke_setup.py"
  uv run python scripts/smoke_setup.py
} >"$LOG_DIR/pytest.log" 2>&1

python3 - <<'PY' "$LOG_DIR"
import json, os, platform, subprocess, sys
from pathlib import Path
log_dir = Path(sys.argv[1])
(log_dir / "pytest.jsonl").write_text(
    json.dumps({"event": "test_run", "status": "completed"}) + "\n",
    encoding="utf-8",
)
(log_dir / "env.json").write_text(
    json.dumps({"python": sys.version, "platform": platform.platform()}, indent=2) + "\n",
    encoding="utf-8",
)
commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True).stdout.strip()
dirty = bool(subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout.strip())
(log_dir / "git.json").write_text(
    json.dumps({"commit": commit, "branch": branch, "dirty": dirty}, indent=2) + "\n",
    encoding="utf-8",
)
PY

cat "$LOG_DIR/pytest.log"
