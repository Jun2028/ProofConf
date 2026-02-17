from __future__ import annotations

import json
import subprocess
from pathlib import Path


def run(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
    p = subprocess.run(cmd, cwd=cwd, check=False, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    mini_f2f_root = root / "datasets/miniF2F/raw/miniF2F-lean4-main"

    checks = {}

    rc, out, err = run(["uv", "--version"], root)
    checks["uv"] = {"ok": rc == 0, "stdout": out.strip(), "stderr": err.strip()}

    rc, out, err = run(["lake", "--version"], root)
    checks["lake"] = {"ok": rc == 0, "stdout": out.strip(), "stderr": err.strip()}

    sample_file = mini_f2f_root / "MiniF2F/Valid/amc12a_2008_p8.lean"
    checks["dataset_file_exists"] = {"ok": sample_file.exists(), "path": str(sample_file)}

    if mini_f2f_root.exists():
        rc, out, err = run(["lake", "env", "lean", str(sample_file)], mini_f2f_root)
        checks["lean_env_smoke"] = {
            "ok": rc == 0,
            "stdout_tail": "\n".join(out.splitlines()[-5:]),
            "stderr_tail": "\n".join(err.splitlines()[-5:]),
        }
    else:
        checks["lean_env_smoke"] = {"ok": False, "reason": "miniF2F not extracted"}

    print(json.dumps(checks, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
