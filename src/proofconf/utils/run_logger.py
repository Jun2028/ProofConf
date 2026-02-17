from __future__ import annotations

import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from .io import ensure_dir, write_json


class RunLogger:
    def __init__(self, log_dir: Path):
        self.log_dir = ensure_dir(log_dir)
        self.log_path = self.log_dir / "driver.log"
        self.jsonl_path = self.log_dir / "driver.jsonl"

    def event(self, level: str, event: str, **kwargs: Any) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        payload: Dict[str, Any] = {"ts": ts, "level": level, "event": event, **kwargs}
        line = f"[{ts}] {level} {event}"
        if kwargs:
            details = ", ".join(f"{k}={v}" for k, v in kwargs.items())
            line += f" | {details}"

        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

        with self.jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def snapshot_env(log_dir: Path) -> None:
    try:
        pip_freeze = subprocess.run(
            [sys.executable, "-m", "pip", "freeze"],
            check=False,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
    except Exception:
        pip_freeze = []

    write_json(
        Path(log_dir) / "env.json",
        {
            "python": sys.version,
            "platform": platform.platform(),
            "packages": pip_freeze,
        },
    )


def snapshot_git(log_dir: Path, repo_root: Path) -> None:
    def run(*args: str) -> str:
        try:
            return subprocess.run(
                list(args), cwd=repo_root, check=False, capture_output=True, text=True
            ).stdout.strip()
        except FileNotFoundError:
            return ""

    write_json(
        Path(log_dir) / "git.json",
        {
            "commit": run("git", "rev-parse", "HEAD"),
            "branch": run("git", "rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": bool(run("git", "status", "--porcelain")),
        },
    )
