#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


FENCE_RE = re.compile(r"```(?:lean[^\n]*|[^\n]*)?\n(?P<body>.*?)(?:\n```|```)\s*$", re.DOTALL)
THEOREM_RE = re.compile(r"(?m)^\s*theorem\s+([A-Za-z0-9_'.]+)\b")
BY_RE = re.compile(r":=\s*by\b")
ESCAPED_BYTE_RUN_RE = re.compile(r"(?:\\x[0-9A-Fa-f]{2})+")
LEAN_ENV_STDOUT_PATTERNS = (
    "too many open files",
    "failed to open file",
    "error: failed to open",
)


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield line_number, json.loads(line)
            except json.JSONDecodeError:
                yield line_number, None


def load_minif2f_sources(paths: list[Path]) -> dict[str, dict[str, str]]:
    sources: dict[str, dict[str, str]] = {}
    for path in paths:
        for _, obj in iter_jsonl(path):
            if not isinstance(obj, dict):
                continue
            name = obj.get("name")
            header = obj.get("header")
            statement = obj.get("formal_statement")
            if isinstance(name, str) and isinstance(header, str) and isinstance(statement, str):
                sources[name] = {"header": header, "formal_statement": statement}
    return sources


def trace_paths(patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        path = Path(pattern)
        if any(ch in pattern for ch in "*?[]"):
            paths.extend(Path().glob(pattern) if not path.is_absolute() else Path("/").glob(pattern[1:]))
        elif path.is_dir():
            paths.extend(path.glob("*/evolution_trace.jsonl"))
            if (path / "evolution_trace.jsonl").exists():
                paths.append(path / "evolution_trace.jsonl")
        elif path.exists():
            paths.append(path)
    return sorted(set(p.resolve() for p in paths if p.name == "evolution_trace.jsonl"))


def tokens_to_text(tokens: Any) -> str | None:
    if not isinstance(tokens, list):
        return None
    parts: list[str] = []
    for row in tokens:
        if not isinstance(row, dict):
            return None
        token = row.get("token")
        if not isinstance(token, str):
            return None
        parts.append(token)
    return decode_escaped_utf8_bytes("".join(parts))


def decode_escaped_utf8_bytes(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        raw = match.group(0)
        data = bytes(int(raw[idx + 2 : idx + 4], 16) for idx in range(0, len(raw), 4))
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return raw

    return ESCAPED_BYTE_RUN_RE.sub(replace, text)


def raw_generation_from_trace(obj: dict[str, Any]) -> tuple[str | None, str | None, int | None]:
    artifacts = obj.get("artifacts") or {}
    context = artifacts.get("evaluation_context") or {}
    generation = context.get("llm_generation") or {}
    text = tokens_to_text(generation.get("tokens"))
    model = generation.get("model") or context.get("llm_model") or artifacts.get("llm_model")
    token_count = context.get("llm_token_count")
    if not isinstance(token_count, int):
        metrics = obj.get("child_metrics") or {}
        metric_count = metrics.get("token_count")
        token_count = int(metric_count) if isinstance(metric_count, (int, float)) else None
    return text, str(model) if model else None, token_count


def strip_fence(text: str) -> str:
    stripped = text.strip()
    match = FENCE_RE.match(stripped)
    if match:
        return match.group("body").strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped


def infer_theorem_name(text: str, trace_path: Path, known_names: set[str]) -> str | None:
    match = THEOREM_RE.search(text)
    if match and match.group(1) in known_names:
        return match.group(1)

    haystack = trace_path.parent.name
    matches = [name for name in known_names if name in haystack]
    if matches:
        return max(matches, key=len)
    return match.group(1) if match else None


def extract_body(raw_text: str) -> tuple[str, str]:
    code = strip_fence(raw_text)
    theorem_match = THEOREM_RE.search(code)
    if theorem_match:
        by_match = BY_RE.search(code[theorem_match.end() :])
        if by_match:
            body_start = theorem_match.end() + by_match.end()
            body = code[body_start:]
            return normalize_body(body), "theorem_body"

    by_match = BY_RE.search(code)
    if by_match:
        return normalize_body(code[by_match.end() :]), "by_body"

    return normalize_body(code), "raw_body"


def normalize_body(body: str) -> str:
    body = body.strip()
    if not body:
        return ""
    lines = body.splitlines()
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    body = "\n".join(lines).rstrip()
    if not body.startswith("\n"):
        body = "\n" + body
    return body + "\n"


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value) != 0.0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "1.0", "true", "yes", "y"}
    return False


def floatish(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def label_from_trace(obj: dict[str, Any]) -> tuple[bool, float | None, str | None, bool | None]:
    metrics = obj.get("child_metrics") or {}
    artifacts = obj.get("artifacts") or {}
    score = floatish(metrics.get("base_score", artifacts.get("base_score")))
    passed = score is not None and score > 0.0
    failure_kind = artifacts.get("lean_failure_kind")
    contains_sorry = metrics.get("contains_sorry", artifacts.get("contains_sorry"))
    return (
        passed,
        score,
        str(failure_kind) if failure_kind is not None else None,
        boolish(contains_sorry) if contains_sorry is not None else None,
    )


def is_eval_env_error(obj: dict[str, Any]) -> tuple[bool, str | None]:
    metrics = obj.get("child_metrics") or {}
    artifacts = obj.get("artifacts") or {}

    metric_env_failure = floatish(metrics.get("lean_env_failure"))
    if metric_env_failure is not None and metric_env_failure > 0.0:
        return True, "child_metrics.lean_env_failure"

    if boolish(artifacts.get("lean_env_failure")):
        return True, "artifacts.lean_env_failure"

    returncode = str(artifacts.get("lean_returncode") or "").strip()
    if returncode in {"126", "127"}:
        return True, f"artifacts.lean_returncode_{returncode}"

    stdout = str(artifacts.get("lean_stdout") or "").lower()
    if any(pattern in stdout for pattern in LEAN_ENV_STDOUT_PATTERNS):
        return True, "artifacts.lean_stdout_open_failure"

    return False, None


def safe_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "unknown"


def build_manifest(
    *,
    traces: list[Path],
    sources: dict[str, dict[str, str]],
    lean_output_dir: Path,
    max_rows: int | None,
    drop_sorry: bool,
    drop_eval_env_errors: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_theorem: dict[str, dict[str, Any]] = {}
    candidate_counts: Counter[str] = Counter()
    summary: Counter[str] = Counter()
    examples: list[dict[str, Any]] = []
    known_names = set(sources)

    lean_output_dir.mkdir(parents=True, exist_ok=True)
    written = 0

    for trace_path in traces:
        for line_number, obj in iter_jsonl(trace_path):
            summary["trace_rows"] += 1
            if not isinstance(obj, dict):
                summary["bad_json_rows"] += 1
                continue

            raw_text, model, token_count = raw_generation_from_trace(obj)
            if not raw_text:
                summary["missing_generation_text"] += 1
                continue

            is_env_error, env_error_reason = is_eval_env_error(obj)
            if drop_eval_env_errors and is_env_error:
                summary["dropped_eval_env_error"] += 1
                if env_error_reason:
                    summary[f"dropped_eval_env_error_{env_error_reason}"] += 1
                continue

            clean_for_name = strip_fence(raw_text)
            theorem_name = infer_theorem_name(clean_for_name, trace_path, known_names)
            if theorem_name not in sources:
                summary["unknown_theorem"] += 1
                if len(examples) < 10:
                    examples.append(
                        {
                            "kind": "unknown_theorem",
                            "trace": str(trace_path),
                            "line": line_number,
                            "inferred": theorem_name,
                        }
                    )
                continue

            passed, base_score, failure_kind, contains_sorry = label_from_trace(obj)
            if drop_sorry and contains_sorry:
                summary["dropped_contains_sorry"] += 1
                continue

            body, extraction_mode = extract_body(raw_text)
            if not body.strip():
                summary["empty_body"] += 1
                continue

            source = sources[theorem_name]
            prefix = source["header"] + source["formal_statement"].rstrip()
            if not prefix.endswith(":= by"):
                if ":= by" not in prefix:
                    summary["source_without_by"] += 1
                    continue
            full_text = prefix + body

            candidate_index = candidate_counts[theorem_name]
            candidate_counts[theorem_name] += 1
            theorem_dir = lean_output_dir / safe_component(theorem_name)
            theorem_dir.mkdir(parents=True, exist_ok=True)
            proof_file = theorem_dir / f"{candidate_index:06d}.lean"
            proof_file.write_text(full_text, encoding="utf-8")

            trace_hash = hashlib.sha256(str(trace_path).encode("utf-8")).hexdigest()[:12]
            record = {
                "index": candidate_index,
                "file": str(proof_file),
                "verification": {"passed": passed},
                "error": None if passed else failure_kind,
                "source_trace": str(trace_path),
                "source_trace_line": line_number,
                "source_trace_hash": trace_hash,
                "model": model,
                "token_count": token_count,
                "base_score": base_score,
                "failure_kind": failure_kind,
                "contains_sorry": contains_sorry,
                "extraction_mode": extraction_mode,
                "raw_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            }
            theorem_row = by_theorem.setdefault(
                theorem_name,
                {
                    "name": theorem_name,
                    "row_index": len(by_theorem),
                    "samples_requested": None,
                    "samples_generated": 0,
                    "solved": False,
                    "verification_records": [],
                },
            )
            theorem_row["verification_records"].append(record)
            theorem_row["samples_generated"] = len(theorem_row["verification_records"])
            theorem_row["solved"] = bool(theorem_row["solved"] or passed)

            written += 1
            summary["written_attempts"] += 1
            summary["written_passed" if passed else "written_failed"] += 1
            summary[f"extraction_{extraction_mode}"] += 1
            if contains_sorry:
                summary["written_contains_sorry"] += 1

            if max_rows is not None and written >= max_rows:
                break
        if max_rows is not None and written >= max_rows:
            break

    rows = [by_theorem[name] for name in sorted(by_theorem)]
    summary_dict: dict[str, Any] = {
        **dict(summary),
        "source_trace_files": len(traces),
        "unique_theorems": len(rows),
        "examples": examples,
    }
    return rows, summary_dict


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-glob", action="append", required=True)
    parser.add_argument("--minif2f-jsonl", action="append", type=Path, required=True)
    parser.add_argument("--lean-output-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path)
    parser.add_argument("--max-rows", type=int)
    parser.add_argument("--drop-sorry", action="store_true")
    parser.add_argument("--drop-eval-env-errors", action="store_true")
    args = parser.parse_args()

    sources = load_minif2f_sources(args.minif2f_jsonl)
    traces = trace_paths(args.trace_glob)
    if not traces:
        raise SystemExit("No evolution_trace.jsonl files matched.")
    if not sources:
        raise SystemExit("No MiniF2F source rows loaded.")

    rows, summary = build_manifest(
        traces=traces,
        sources=sources,
        lean_output_dir=args.lean_output_dir,
        max_rows=args.max_rows,
        drop_sorry=args.drop_sorry,
        drop_eval_env_errors=args.drop_eval_env_errors,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    attempts = [record for row in rows for record in row["verification_records"]]
    summary.update(
        {
            "output": str(args.output),
            "lean_output_dir": str(args.lean_output_dir),
            "attempts": len(attempts),
            "correct_attempts": sum(1 for record in attempts if record["verification"]["passed"]),
            "wrong_attempts": sum(1 for record in attempts if not record["verification"]["passed"]),
        }
    )
    if args.summary_output:
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
