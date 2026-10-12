#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import glob
import json
import math
import os
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Iterable, Sequence

import ijson


METRICS = [
    "avg_logprob",
    "lowest_group_confidence",
    "bottom10_group_confidence",
    "tail_confidence",
]


def discover_result_paths(patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        paths.extend(Path(p) for p in glob.glob(pattern))
    return sorted(set(path.resolve() for path in paths))


def iter_rows(result_paths: Iterable[Path]):
    for result_path in result_paths:
        with result_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    yield result_path, json.loads(line)


def safe_std(values: list[float]) -> float:
    clean = [v for v in values if not math.isnan(v)]
    n = len(clean)
    if n <= 1:
        return float("nan")
    mean = sum(clean) / n
    var = sum((v - mean) ** 2 for v in clean) / n
    return math.sqrt(var)


def point_biserial(x_values: list[float], y_binary: list[int]) -> float:
    if len(x_values) != len(y_binary) or len(x_values) < 2:
        return float("nan")
    pairs = [(x, y) for x, y in zip(x_values, y_binary) if not math.isnan(x)]
    if len(pairs) < 2:
        return float("nan")
    xs = [x for x, _ in pairs]
    ys = [y for _, y in pairs]
    p = sum(ys) / len(ys)
    q = 1.0 - p
    if p <= 0.0 or q <= 0.0:
        return float("nan")
    x1 = [x for x, y in pairs if y == 1]
    x0 = [x for x, y in pairs if y == 0]
    if not x1 or not x0:
        return float("nan")
    s = safe_std(xs)
    if math.isnan(s) or s == 0.0:
        return float("nan")
    return ((sum(x1) / len(x1)) - (sum(x0) / len(x0))) / s * math.sqrt(p * q)


def auc_score(x_values: list[float], y_binary: list[int]) -> float:
    pairs = [(x, y) for x, y in zip(x_values, y_binary) if not math.isnan(x)]
    pos = [x for x, y in pairs if y == 1]
    neg = [x for x, y in pairs if y == 0]
    if not pos or not neg:
        return float("nan")
    gt = 0
    eq = 0
    for p in pos:
        for n in neg:
            if p > n:
                gt += 1
            elif p == n:
                eq += 1
    return (gt + 0.5 * eq) / (len(pos) * len(neg))


def theorem_solved_rate(rows: list[dict[str, Any]]) -> float:
    by_theorem: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_theorem[row["theorem_name"]].append(row)
    if not by_theorem:
        return float("nan")
    solved = sum(1 for group in by_theorem.values() if any(bool(r["lean_success"]) for r in group))
    return solved / len(by_theorem)


def chosen_token_scores(logprobs: list[float]) -> list[float]:
    return [float(lp) for lp in logprobs]


def paper_token_confidence_at_t(
    candidate_logprobs: Sequence[float],
    top_k: int,
    require_full_topk: bool = False,
) -> float:
    k = max(1, int(top_k))
    ordered = sorted((float(x) for x in candidate_logprobs), reverse=True)
    use = ordered[:k]
    if not use:
        return float("nan")
    if require_full_topk and len(use) < k:
        return float("nan")
    return -(sum(use) / len(use))


def token_confidence_series(
    chosen_logprobs: Sequence[float],
    top_logprobs: Sequence[Sequence[float]],
    method: str = "paper_topk",
    top_k: int = 20,
    require_full_topk: bool = False,
    fallback_to_chosen: bool = False,
) -> list[float]:
    if method == "chosen_logprob":
        return chosen_token_scores(list(chosen_logprobs))
    if method != "paper_topk":
        raise ValueError(f"Unsupported token confidence method: {method}")

    aligned = min(len(chosen_logprobs), len(top_logprobs))
    if aligned <= 0:
        return []

    out: list[float] = []
    for idx in range(aligned):
        cands = list(top_logprobs[idx])
        score = paper_token_confidence_at_t(
            candidate_logprobs=cands,
            top_k=top_k,
            require_full_topk=require_full_topk,
        )
        if math.isnan(score):
            if fallback_to_chosen:
                out.append(-float(chosen_logprobs[idx]))
                continue
            return []
        out.append(score)
    return out


def sliding_window_ranges(length: int, window_size: int, stride: int) -> list[tuple[int, int]]:
    if length <= 0:
        return []

    size = max(1, window_size)
    step = max(1, stride)

    if length <= size:
        return [(0, length)]

    ranges: list[tuple[int, int]] = []
    idx = 0
    while idx + size <= length:
        ranges.append((idx, idx + size))
        idx += step

    if (length - size) % step != 0:
        ranges.append((length - size, length))

    return ranges


def sliding_window_means(values: list[float], window_size: int, stride: int) -> list[float]:
    if not values:
        return []
    windows: list[float] = []
    for start, end in sliding_window_ranges(len(values), window_size, stride):
        chunk = values[start:end]
        windows.append(sum(chunk) / len(chunk))
    return windows


def average_trace_confidence(values: Sequence[float]) -> float:
    if not values:
        return float("nan")
    return sum(values) / len(values)


def lowest_group_confidence(values: Sequence[float]) -> float:
    if not values:
        return float("nan")
    return min(values)


def bottom_percent_group_confidence(values: Sequence[float], fraction: float = 0.1) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    n = max(1, int(len(ordered) * max(0.0, min(1.0, fraction))))
    bottom = ordered[:n]
    return sum(bottom) / len(bottom)


def tail_confidence_score(values: Sequence[float], tail_tokens: int) -> float:
    if not values:
        return float("nan")
    tail_n = min(len(values), max(1, int(tail_tokens)))
    tail = list(values)[-tail_n:]
    return sum(tail) / len(tail)


def confidence_metrics(
    token_scores: list[float],
    window_size: int,
    stride: int,
    tail_tokens: int = 256,
) -> dict[str, float]:
    if not token_scores:
        return {
            "avg_logprob": float("nan"),
            "lowest_group_confidence": float("nan"),
            "bottom10_group_confidence": float("nan"),
            "tail_confidence": float("nan"),
            "token_count": 0,
            "window_count": 0,
        }

    windows = sliding_window_means(token_scores, window_size, stride)
    return {
        "avg_logprob": average_trace_confidence(token_scores),
        "lowest_group_confidence": lowest_group_confidence(windows),
        "bottom10_group_confidence": bottom_percent_group_confidence(windows, fraction=0.1),
        "tail_confidence": tail_confidence_score(token_scores, tail_tokens),
        "token_count": len(token_scores),
        "window_count": len(windows),
    }


def extract_top_logprob_values(item: Any) -> list[float]:
    if item is None:
        return []
    if isinstance(item, list):
        values = []
        for entry in item:
            if isinstance(entry, dict) and entry.get("logprob") is not None:
                values.append(float(entry["logprob"]))
        return values
    if isinstance(item, dict):
        values = []
        for value in item.values():
            try:
                values.append(float(value))
            except (TypeError, ValueError):
                continue
        return values
    return []


def compute_choice_metrics(
    choice: dict[str, Any],
    method: str,
    top_k: int,
    require_full_topk: bool,
    fallback_to_chosen: bool,
    window_size: int,
    stride: int,
    tail_tokens: int,
) -> dict[str, Any]:
    content = ((choice.get("logprobs") or {}).get("content")) or []
    chosen_logprobs: list[float] = []
    top_logprobs: list[list[float]] = []
    for token_entry in content:
        logprob = token_entry.get("logprob")
        if logprob is not None:
            chosen_logprobs.append(float(logprob))
        else:
            chosen_logprobs.append(float("nan"))
        top_logprobs.append(extract_top_logprob_values(token_entry.get("top_logprobs")))

    token_scores = token_confidence_series(
        chosen_logprobs=chosen_logprobs,
        top_logprobs=top_logprobs,
        method=method,
        top_k=top_k,
        require_full_topk=require_full_topk,
        fallback_to_chosen=fallback_to_chosen,
    )
    metrics = confidence_metrics(
        token_scores=token_scores,
        window_size=window_size,
        stride=stride,
        tail_tokens=tail_tokens,
    )
    metrics["raw_token_count"] = len(content)
    metrics["scored_token_count"] = len(token_scores)
    metrics["finish_reason"] = choice.get("finish_reason")
    metrics["stop_reason"] = choice.get("stop_reason")
    return metrics


def stream_needed_choice_metrics(
    raw_path: Path,
    needed_indices: set[int],
    method: str,
    top_k: int,
    require_full_topk: bool,
    fallback_to_chosen: bool,
    window_size: int,
    stride: int,
    tail_tokens: int,
) -> dict[int, dict[str, Any]]:
    if not needed_indices:
        return {}
    target_max = max(needed_indices)
    metrics_by_index: dict[int, dict[str, Any]] = {}
    with raw_path.open("rb") as handle:
        for global_index, choice in enumerate(ijson.items(handle, "item.choices.item")):
            if global_index in needed_indices:
                metrics_by_index[global_index] = compute_choice_metrics(
                    choice=choice,
                    method=method,
                    top_k=top_k,
                    require_full_topk=require_full_topk,
                    fallback_to_chosen=fallback_to_chosen,
                    window_size=window_size,
                    stride=stride,
                    tail_tokens=tail_tokens,
                )
                if len(metrics_by_index) == len(needed_indices):
                    break
            if global_index >= target_max and len(metrics_by_index) == len(needed_indices):
                break
    return metrics_by_index


def verification_status(record: dict[str, Any]) -> tuple[str, bool]:
    if "verification" in record:
        passed = bool(record["verification"].get("passed"))
        return ("passed" if passed else "failed_verification"), passed
    return "error", False


def process_theorem_task(task: dict[str, Any]) -> dict[str, Any]:
    theorem_name = task["theorem_name"]
    raw_path = Path(task["raw_path"])
    record_rows = task["record_rows"]
    started_at = time.time()

    needed_indices = {int(record["candidate_index"]) for record in record_rows}
    metrics_by_index = {}
    if raw_path.exists() and needed_indices:
        metrics_by_index = stream_needed_choice_metrics(
            raw_path=raw_path,
            needed_indices=needed_indices,
            method=task["method"],
            top_k=int(task["top_k"]),
            require_full_topk=bool(task["require_full_topk"]),
            fallback_to_chosen=bool(task["fallback_to_chosen"]),
            window_size=int(task["window_size"]),
            stride=int(task["stride"]),
            tail_tokens=int(task["tail_tokens"]),
        )

    trace_rows: list[dict[str, Any]] = []
    missing_metrics = 0
    for record in record_rows:
        metrics = metrics_by_index.get(int(record["candidate_index"]))
        if metrics is None:
            missing_metrics += 1
            metrics = {
                "avg_logprob": float("nan"),
                "lowest_group_confidence": float("nan"),
                "bottom10_group_confidence": float("nan"),
                "tail_confidence": float("nan"),
                "token_count": 0,
                "window_count": 0,
                "raw_token_count": 0,
                "scored_token_count": 0,
                "finish_reason": None,
                "stop_reason": None,
            }
        trace_rows.append({**record, **metrics})

    return {
        "theorem_name": theorem_name,
        "raw_path": str(raw_path),
        "raw_size_bytes": raw_path.stat().st_size if raw_path.exists() else None,
        "trace_rows": trace_rows,
        "missing_metrics": missing_metrics,
        "elapsed_seconds": time.time() - started_at,
    }


def confidence_filtering_stats(
    rows: list[dict[str, Any]],
    metric_key: str,
    keep_percents: list[int],
) -> dict[str, Any]:
    filtered = [row for row in rows if not math.isnan(float(row.get(metric_key, float("nan"))))]
    by_theorem: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in filtered:
        by_theorem[row["theorem_name"]].append(row)

    if not by_theorem:
        return {}

    baseline_attempt_rate = sum(1 for row in filtered if row["lean_success"]) / len(filtered)
    baseline_theorem_rate = theorem_solved_rate(filtered)
    out: dict[str, Any] = {
        "baseline_attempt_success_rate": baseline_attempt_rate,
        "baseline_theorem_solved_rate": baseline_theorem_rate,
        "top_percent": {},
    }

    for pct in keep_percents:
        kept_rows: list[dict[str, Any]] = []
        for theorem_rows in by_theorem.values():
            ordered = sorted(theorem_rows, key=lambda row: float(row[metric_key]), reverse=True)
            k = max(1, math.ceil(len(ordered) * (pct / 100.0)))
            kept_rows.extend(ordered[:k])

        attempt_rate = sum(1 for row in kept_rows if row["lean_success"]) / len(kept_rows)
        out["top_percent"][str(pct)] = {
            "kept_attempts": len(kept_rows),
            "attempt_success_rate": attempt_rate,
            "theorem_solved_rate": theorem_solved_rate(kept_rows),
        }
    return out


def per_theorem_auc(rows: list[dict[str, Any]], metric: str) -> dict[str, Any]:
    by_theorem: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_theorem[row["theorem_name"]].append(row)
    aucs = []
    below_half = 0
    valid = 0
    for theorem_rows in by_theorem.values():
        xs = [float(row[metric]) for row in theorem_rows]
        ys = [1 if row["lean_success"] else 0 for row in theorem_rows]
        auc = auc_score(xs, ys)
        if not math.isnan(auc):
            valid += 1
            aucs.append(auc)
            if auc < 0.5:
                below_half += 1
    return {
        "valid_theorems": valid,
        "mean_per_theorem_auc": (sum(aucs) / len(aucs)) if aucs else float("nan"),
        "theorems_below_0_5": below_half,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-glob", action="append", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--window-size", type=int, default=24)
    parser.add_argument("--stride", type=int, default=6)
    parser.add_argument("--tail-tokens", type=int, default=256)
    parser.add_argument("--method", default="paper_topk", choices=["paper_topk", "chosen_logprob"])
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--require-full-topk", action="store_true")
    parser.add_argument("--fallback-to-chosen", action="store_true")
    parser.add_argument("--workers", type=int, default=min(8, max(1, (os.cpu_count() or 4) // 2)))
    parser.add_argument("--keep-percents", default="10,25,50")
    args = parser.parse_args()

    patterns = args.results_glob
    result_paths = discover_result_paths(patterns)
    if not result_paths:
        raise SystemExit("No result files matched.")

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    theorem_tasks: dict[str, dict[str, Any]] = {}
    for result_path, row in iter_rows(result_paths):
        theorem_name = row["name"]
        eval_dir = result_path.parent
        raw_path = eval_dir / "raw" / f"{theorem_name}.json"
        task = theorem_tasks.setdefault(
            theorem_name,
            {
                "theorem_name": theorem_name,
                "raw_path": str(raw_path),
                "method": args.method,
                "top_k": args.top_k,
                "require_full_topk": args.require_full_topk,
                "fallback_to_chosen": args.fallback_to_chosen,
                "window_size": args.window_size,
                "stride": args.stride,
                "tail_tokens": args.tail_tokens,
                "record_rows": [],
            },
        )
        for record in row.get("verification_records", []):
            status, passed = verification_status(record)
            task["record_rows"].append(
                {
                    "theorem_name": theorem_name,
                    "row_index": row.get("row_index"),
                    "solved_theorem": bool(row.get("solved")),
                    "samples_requested": row.get("samples_requested"),
                    "samples_generated": row.get("samples_generated"),
                    "candidate_index": int(record["index"]),
                    "proof_file": record.get("file"),
                    "status": status,
                    "lean_success": passed,
                    "error": record.get("error"),
                }
            )

    progress_path = output_dir / "progress.jsonl"
    progress_path.write_text("", encoding="utf-8")

    tasks = sorted(
        theorem_tasks.values(),
        key=lambda task: Path(task["raw_path"]).stat().st_size if Path(task["raw_path"]).exists() else -1,
        reverse=True,
    )
    trace_rows: list[dict[str, Any]] = []
    missing_metrics = 0
    started_at = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        future_map = {executor.submit(process_theorem_task, task): task["theorem_name"] for task in tasks}
        processed_theorems = 0
        with progress_path.open("a", encoding="utf-8") as progress_handle:
            for future in as_completed(future_map):
                result = future.result()
                processed_theorems += 1
                trace_rows.extend(result["trace_rows"])
                missing_metrics += int(result["missing_metrics"])
                progress = {
                    "processed_theorems": processed_theorems,
                    "total_theorems": len(tasks),
                    "theorem_name": result["theorem_name"],
                    "raw_path": result["raw_path"],
                    "raw_size_bytes": result["raw_size_bytes"],
                    "trace_rows": len(result["trace_rows"]),
                    "missing_metrics": result["missing_metrics"],
                    "elapsed_seconds": result["elapsed_seconds"],
                    "wall_elapsed_seconds": time.time() - started_at,
                }
                progress_handle.write(json.dumps(progress, ensure_ascii=False) + "\n")
                progress_handle.flush()

    keep_percents = [int(x) for x in args.keep_percents.split(",") if x.strip()]

    status_counts = Counter(row["status"] for row in trace_rows)
    passed_rows = [row for row in trace_rows if row["lean_success"]]
    failed_rows = [row for row in trace_rows if not row["lean_success"]]

    global_corr: dict[str, dict[str, float]] = {}
    within_theorem: dict[str, dict[str, Any]] = {}
    filtering: dict[str, dict[str, Any]] = {}
    for metric in METRICS:
        xs = [float(row[metric]) for row in trace_rows]
        ys = [1 if row["lean_success"] else 0 for row in trace_rows]
        global_corr[metric] = {
            "point_biserial": point_biserial(xs, ys),
            "auc": auc_score(xs, ys),
        }
        within_theorem[metric] = per_theorem_auc(trace_rows, metric)
        filtering[metric] = confidence_filtering_stats(trace_rows, metric, keep_percents)

    baseline_attempt_rate = sum(1 for row in trace_rows if row["lean_success"]) / len(trace_rows)
    baseline_theorem_rate = theorem_solved_rate(trace_rows)

    csv_path = output_dir / "trace_metrics.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "theorem_name",
            "row_index",
            "solved_theorem",
            "samples_requested",
            "samples_generated",
            "candidate_index",
            "proof_file",
            "status",
            "lean_success",
            "error",
            "avg_logprob",
            "lowest_group_confidence",
            "bottom10_group_confidence",
            "tail_confidence",
            "token_count",
            "window_count",
            "raw_token_count",
            "scored_token_count",
            "finish_reason",
            "stop_reason",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(trace_rows)

    summary = {
        "source_result_files": [str(path) for path in result_paths],
        "method": args.method,
        "top_k": args.top_k,
        "require_full_topk": args.require_full_topk,
        "fallback_to_chosen": args.fallback_to_chosen,
        "window_size": args.window_size,
        "stride": args.stride,
        "tail_tokens": args.tail_tokens,
        "workers": args.workers,
        "keep_percents": keep_percents,
        "unique_theorems": len(theorem_tasks),
        "attempt_rows_analyzed": len(trace_rows),
        "correct_attempts": len(passed_rows),
        "wrong_attempts": len(failed_rows),
        "missing_metrics": missing_metrics,
        "status_counts": dict(status_counts),
        "baseline_attempt_success_rate": baseline_attempt_rate,
        "baseline_theorem_solved_rate": baseline_theorem_rate,
        "global_correlation": global_corr,
        "within_theorem_auc": within_theorem,
        "confidence_filtering": filtering,
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# ProofConf-Style Confidence Analysis",
        "",
        f"- Unique theorems: `{summary['unique_theorems']}`",
        f"- Attempt rows analyzed: `{summary['attempt_rows_analyzed']}`",
        f"- Correct attempts: `{summary['correct_attempts']}`",
        f"- Wrong attempts: `{summary['wrong_attempts']}`",
        f"- Missing metrics: `{summary['missing_metrics']}`",
        "",
        "## Configuration",
        f"- Token confidence method: `{args.method}`",
        f"- Token confidence top-k: `{args.top_k}`",
        f"- Token confidence require full top-k: `{args.require_full_topk}`",
        f"- Token confidence fallback to chosen: `{args.fallback_to_chosen}`",
        f"- Confidence window: `size={args.window_size}`, `stride={args.stride}`",
        f"- Tail confidence tokens: `{args.tail_tokens}`",
        "",
        "## Baseline",
        f"- Attempt pass rate: `{baseline_attempt_rate:.6f}` ({len(passed_rows)}/{len(trace_rows)})",
        f"- Theorem solved rate: `{baseline_theorem_rate:.6f}`",
        "",
        "## Global Correlation",
    ]
    for metric in METRICS:
        lines.append(
            f"- `{metric}`: point_biserial=`{global_corr[metric]['point_biserial']:.6f}`, "
            f"AUC=`{global_corr[metric]['auc']:.6f}`"
        )
    lines.extend(["", "## Within-Theorem AUC"])
    for metric in METRICS:
        row = within_theorem[metric]
        lines.append(
            f"- `{metric}`: mean_per_theorem_auc=`{row['mean_per_theorem_auc']:.6f}`, "
            f"below_0.5=`{row['theorems_below_0_5']}/{row['valid_theorems']}`"
        )
    lines.extend(["", "## Filtering (Top-k% by confidence within theorem)"])
    for metric in METRICS:
        lines.append(f"- `{metric}`:")
        filt = filtering[metric]
        if not filt:
            lines.append("  - no valid rows")
            continue
        lines.append(
            f"  - baseline attempt/theorem: `{filt['baseline_attempt_success_rate']:.6f}` / "
            f"`{filt['baseline_theorem_solved_rate']:.6f}`"
        )
        for pct in keep_percents:
            item = filt["top_percent"][str(pct)]
            lines.append(
                f"  - top {pct}%: attempts=`{item['kept_attempts']}`, "
                f"attempt_success=`{item['attempt_success_rate']:.6f}`, "
                f"theorem_solved=`{item['theorem_solved_rate']:.6f}`"
            )
    (output_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "summary_json": str(summary_path),
                "trace_csv": str(csv_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
