#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import glob
import importlib.util
import json
import math
import os
import re
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Iterable, Sequence

import requests


METRICS = [
    "avg_logprob",
    "min_logprob",
    "bottom10_logprob",
    "lowest_window_logprob",
    "tail_logprob",
]


@dataclass(frozen=True)
class ProofAttempt:
    theorem_name: str
    row_index: int | None
    solved_theorem: bool
    samples_requested: int | None
    samples_generated: int | None
    candidate_index: int
    proof_file: Path | None
    status: str
    lean_success: bool
    error: str | None
    result_path: Path


@dataclass(frozen=True)
class LeanSplit:
    full_text: str
    prefix: str
    body: str
    body_start: int


@dataclass(frozen=True)
class Tokenization:
    input_ids: list[int]
    offsets: list[tuple[int, int]]


def discover_result_paths(patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        paths.extend(Path(p) for p in glob.glob(pattern))
    return sorted(set(path.resolve() for path in paths))


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def verification_status(record: dict[str, Any]) -> tuple[str, bool]:
    verification = record.get("verification")
    if isinstance(verification, dict):
        passed = bool(verification.get("passed"))
        return ("passed" if passed else "failed_verification"), passed
    return "error", False


def collect_attempts(
    result_paths: Sequence[Path],
    theorem_filter: set[str] | None = None,
    limit_theorems: int | None = None,
    limit_attempts: int | None = None,
) -> list[ProofAttempt]:
    attempts: list[ProofAttempt] = []
    seen_theorems: set[str] = set()
    for result_path in result_paths:
        for row in iter_jsonl(result_path):
            theorem_name = str(row["name"])
            if theorem_filter is not None and theorem_name not in theorem_filter:
                continue
            if theorem_name not in seen_theorems:
                if limit_theorems is not None and len(seen_theorems) >= limit_theorems:
                    continue
                seen_theorems.add(theorem_name)

            for record in row.get("verification_records", []):
                proof_file = record.get("file")
                status, passed = verification_status(record)
                attempts.append(
                    ProofAttempt(
                        theorem_name=theorem_name,
                        row_index=row.get("row_index"),
                        solved_theorem=bool(row.get("solved")),
                        samples_requested=row.get("samples_requested"),
                        samples_generated=row.get("samples_generated"),
                        candidate_index=int(record["index"]),
                        proof_file=Path(proof_file) if proof_file else None,
                        status=status,
                        lean_success=passed,
                        error=record.get("error"),
                        result_path=result_path,
                    )
                )
                if limit_attempts is not None and len(attempts) >= limit_attempts:
                    return attempts
    return attempts


def split_lean_prefix_body(text: str) -> LeanSplit:
    theorem_match = re.search(r"(?m)^\s*theorem\b", text)
    if theorem_match is None:
        raise ValueError("Could not find a theorem declaration.")
    by_match = re.search(r":=\s*by\b", text[theorem_match.start() :])
    if by_match is None:
        raise ValueError("Could not find theorem proof boundary ':= by'.")
    body_start = theorem_match.start() + by_match.end()
    return LeanSplit(
        full_text=text,
        prefix=text[:body_start],
        body=text[body_start:],
        body_start=body_start,
    )


def load_tokenizer(tokenizer_path: str, trust_remote_code: bool):
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        tokenizer_path,
        trust_remote_code=trust_remote_code,
        use_fast=True,
    )
    if not getattr(tokenizer, "is_fast", False):
        raise RuntimeError("A fast tokenizer is required for offset mapping.")
    return tokenizer


def tokenize_with_offsets(tokenizer: Any, text: str) -> Tokenization:
    encoded = tokenizer(
        text,
        add_special_tokens=False,
        return_offsets_mapping=True,
    )
    return Tokenization(
        input_ids=[int(x) for x in encoded["input_ids"]],
        offsets=[(int(start), int(end)) for start, end in encoded["offset_mapping"]],
    )


def body_token_indices(offsets: Sequence[tuple[int, int]], body_start: int) -> tuple[list[int], int]:
    indices: list[int] = []
    boundary_crossing = 0
    for idx, (start, end) in enumerate(offsets):
        if end <= start:
            continue
        if start >= body_start:
            indices.append(idx)
        elif start < body_start < end:
            boundary_crossing += 1
    return indices, boundary_crossing


def build_completions_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        return normalized + "/completions"
    return normalized + "/v1/completions"


def request_prompt_logprobs(
    *,
    base_url: str,
    api_key: str,
    model: str,
    text: str,
    prompt_logprobs: int,
    timeout: int,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "prompt": text,
        "echo": True,
        "max_tokens": 0,
        "temperature": 0.0,
        "logprobs": 0,
        "prompt_logprobs": prompt_logprobs,
        "add_special_tokens": False,
        "return_tokens_as_token_ids": False,
    }
    response = requests.post(
        build_completions_url(base_url),
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def extract_echo_prompt_logprobs(response: dict[str, Any]) -> tuple[list[float | None], int, bool]:
    choices = response.get("choices") or []
    if not choices:
        raise ValueError("Response did not contain choices.")
    choice = choices[0]
    logprobs = choice.get("logprobs") or {}
    token_logprobs = logprobs.get("token_logprobs")
    if not isinstance(token_logprobs, list):
        raise ValueError("Response choice did not contain echo token_logprobs.")
    prompt_logprobs_present = choice.get("prompt_logprobs") is not None or response.get(
        "prompt_logprobs"
    ) is not None
    return [
        None if value is None else float(value)
        for value in token_logprobs
    ], len(logprobs.get("tokens") or []), prompt_logprobs_present


def response_tokenization_from_echo(response: dict[str, Any], text: str) -> Tokenization:
    choices = response.get("choices") or []
    if not choices:
        raise ValueError("Response did not contain choices.")
    logprobs = (choices[0].get("logprobs") or {})
    offsets = logprobs.get("text_offset")
    tokens = logprobs.get("tokens")
    if not isinstance(offsets, list) or not isinstance(tokens, list):
        raise ValueError("Response echo logprobs did not include tokens/text_offset.")
    if len(offsets) != len(tokens):
        raise ValueError(
            f"Response token/text_offset length mismatch: tokens={len(tokens)}, "
            f"text_offset={len(offsets)}."
        )
    spans: list[tuple[int, int]] = []
    for idx, start_value in enumerate(offsets):
        start = int(start_value)
        if idx + 1 < len(offsets):
            end = int(offsets[idx + 1])
        else:
            end = min(len(text), start + len(str(tokens[idx])))
            if end < len(text):
                end = len(text)
        spans.append((start, end))
    return Tokenization(input_ids=list(range(len(spans))), offsets=spans)


def aligned_logprobs_for_tokenization(
    token_logprobs: Sequence[float | None],
    token_count: int,
) -> tuple[list[float | None], int]:
    if len(token_logprobs) == token_count:
        return list(token_logprobs), 0
    if len(token_logprobs) == token_count + 1 and token_logprobs[0] is None:
        return list(token_logprobs[1:]), 1
    raise ValueError(
        f"Prompt logprob/tokenizer length mismatch: response={len(token_logprobs)}, "
        f"tokenizer={token_count}."
    )


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


def average(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else float("nan")


def bottom_fraction_mean(values: Sequence[float], fraction: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    n = max(1, int(len(ordered) * max(0.0, min(1.0, fraction))))
    return average(ordered[:n])


def tail_mean(values: Sequence[float], tail_tokens: int) -> float:
    if not values:
        return float("nan")
    n = min(len(values), max(1, tail_tokens))
    return average(list(values)[-n:])


def score_token_logprobs(
    token_logprobs: Sequence[float | None],
    body_indices: Sequence[int],
    window_size: int,
    stride: int,
    tail_tokens: int,
    bottom_fraction: float,
) -> dict[str, Any]:
    scored = [
        float(token_logprobs[idx])
        for idx in body_indices
        if idx < len(token_logprobs) and token_logprobs[idx] is not None
    ]
    if not scored:
        return {
            "avg_logprob": float("nan"),
            "sum_logprob": float("nan"),
            "min_logprob": float("nan"),
            "bottom10_logprob": float("nan"),
            "lowest_window_logprob": float("nan"),
            "tail_logprob": float("nan"),
            "body_token_count": len(body_indices),
            "scored_token_count": 0,
            "missing_token_logprobs": len(body_indices),
            "window_count": 0,
        }

    windows = [
        average(scored[start:end])
        for start, end in sliding_window_ranges(len(scored), window_size, stride)
    ]
    return {
        "avg_logprob": average(scored),
        "sum_logprob": sum(scored),
        "min_logprob": min(scored),
        "bottom10_logprob": bottom_fraction_mean(scored, bottom_fraction),
        "lowest_window_logprob": min(windows) if windows else float("nan"),
        "tail_logprob": tail_mean(scored, tail_tokens),
        "body_token_count": len(body_indices),
        "scored_token_count": len(scored),
        "missing_token_logprobs": len(body_indices) - len(scored),
        "window_count": len(windows),
    }


def score_response_for_body(
    *,
    response: dict[str, Any],
    tokenization: Tokenization,
    body_start: int,
    window_size: int,
    stride: int,
    tail_tokens: int,
    bottom_fraction: float,
) -> dict[str, Any]:
    raw_logprobs, response_token_count, prompt_logprobs_present = extract_echo_prompt_logprobs(response)
    aligned_logprobs, bos_shift = aligned_logprobs_for_tokenization(
        raw_logprobs,
        token_count=len(tokenization.input_ids),
    )
    indices, boundary_crossing = body_token_indices(tokenization.offsets, body_start)
    metrics = score_token_logprobs(
        aligned_logprobs,
        indices,
        window_size=window_size,
        stride=stride,
        tail_tokens=tail_tokens,
        bottom_fraction=bottom_fraction,
    )
    metrics.update(
        {
            "prompt_logprobs_present": prompt_logprobs_present,
            "response_token_count": response_token_count,
            "tokenizer_token_count": len(tokenization.input_ids),
            "bos_shift": bos_shift,
            "boundary_crossing_tokens": boundary_crossing,
        }
    )
    return metrics


def safe_std(values: list[float]) -> float:
    clean = [v for v in values if not math.isnan(v)]
    n = len(clean)
    if n <= 1:
        return float("nan")
    mean = sum(clean) / n
    var = sum((v - mean) ** 2 for v in clean) / n
    return math.sqrt(var)


def point_biserial(x_values: list[float], y_binary: list[int]) -> float:
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


def theorem_solved_rate(rows: Sequence[dict[str, Any]]) -> float:
    by_theorem: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_theorem[row["theorem_name"]].append(row)
    if not by_theorem:
        return float("nan")
    solved = sum(1 for group in by_theorem.values() if any(bool(r["lean_success"]) for r in group))
    return solved / len(by_theorem)


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


def nan_safe_row(row: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for key, value in row.items():
        if isinstance(value, float) and math.isnan(value):
            out[key] = "nan"
        else:
            out[key] = value
    return out


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, allow_nan=True) + "\n")


def load_existing_keys(path: Path) -> set[tuple[str, int]]:
    if not path.exists():
        return set()
    keys: set[tuple[str, int]] = set()
    for row in iter_jsonl(path):
        if row.get("scoring_error"):
            continue
        keys.add((str(row["theorem_name"]), int(row["candidate_index"])))
    return keys


def score_attempt(
    attempt: ProofAttempt,
    *,
    tokenizer: Any,
    offset_source: str,
    base_url: str,
    api_key: str,
    model: str,
    prompt_logprobs: int,
    timeout: int,
    window_size: int,
    stride: int,
    tail_tokens: int,
    bottom_fraction: float,
) -> dict[str, Any]:
    started_at = time.time()
    base_row: dict[str, Any] = {
        "theorem_name": attempt.theorem_name,
        "row_index": attempt.row_index,
        "solved_theorem": attempt.solved_theorem,
        "samples_requested": attempt.samples_requested,
        "samples_generated": attempt.samples_generated,
        "candidate_index": attempt.candidate_index,
        "proof_file": str(attempt.proof_file) if attempt.proof_file is not None else None,
        "status": attempt.status,
        "lean_success": attempt.lean_success,
        "error": attempt.error,
        "result_path": str(attempt.result_path),
    }
    try:
        if attempt.proof_file is None:
            raise ValueError("Verification record does not contain a proof file.")
        text = attempt.proof_file.read_text(encoding="utf-8")
        split = split_lean_prefix_body(text)
        response = request_prompt_logprobs(
            base_url=base_url,
            api_key=api_key,
            model=model,
            text=split.full_text,
            prompt_logprobs=prompt_logprobs,
            timeout=timeout,
        )
        if offset_source == "tokenizer":
            tokenization = tokenize_with_offsets(tokenizer, split.full_text)
        else:
            tokenization = response_tokenization_from_echo(response, split.full_text)
        metrics = score_response_for_body(
            response=response,
            tokenization=tokenization,
            body_start=split.body_start,
            window_size=window_size,
            stride=stride,
            tail_tokens=tail_tokens,
            bottom_fraction=bottom_fraction,
        )
        return {
            **base_row,
            **metrics,
            "prefix_chars": len(split.prefix),
            "body_chars": len(split.body),
            "full_chars": len(split.full_text),
            "scoring_error": None,
            "elapsed_seconds": time.time() - started_at,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            **base_row,
            "avg_logprob": float("nan"),
            "sum_logprob": float("nan"),
            "min_logprob": float("nan"),
            "bottom10_logprob": float("nan"),
            "lowest_window_logprob": float("nan"),
            "tail_logprob": float("nan"),
            "body_token_count": 0,
            "scored_token_count": 0,
            "missing_token_logprobs": 0,
            "window_count": 0,
            "prompt_logprobs_present": False,
            "response_token_count": 0,
            "tokenizer_token_count": 0,
            "bos_shift": 0,
            "boundary_crossing_tokens": 0,
            "prefix_chars": 0,
            "body_chars": 0,
            "full_chars": 0,
            "scoring_error": repr(exc),
            "elapsed_seconds": time.time() - started_at,
        }


def summarize_rows(
    rows: list[dict[str, Any]],
    *,
    result_paths: Sequence[Path],
    keep_percents: list[int],
    args: argparse.Namespace,
) -> dict[str, Any]:
    status_counts = Counter(row["status"] for row in rows)
    scoring_errors = [row for row in rows if row.get("scoring_error")]
    scored_rows = [row for row in rows if not row.get("scoring_error")]
    passed_rows = [row for row in rows if row["lean_success"]]
    failed_rows = [row for row in rows if not row["lean_success"]]

    global_corr: dict[str, dict[str, float]] = {}
    within_theorem: dict[str, dict[str, Any]] = {}
    filtering: dict[str, dict[str, Any]] = {}
    for metric in METRICS:
        xs = [float(row[metric]) for row in scored_rows]
        ys = [1 if row["lean_success"] else 0 for row in scored_rows]
        global_corr[metric] = {
            "point_biserial": point_biserial(xs, ys),
            "auc": auc_score(xs, ys),
        }
        within_theorem[metric] = per_theorem_auc(scored_rows, metric)
        filtering[metric] = confidence_filtering_stats(scored_rows, metric, keep_percents)

    baseline_attempt_rate = (
        sum(1 for row in rows if row["lean_success"]) / len(rows)
        if rows
        else float("nan")
    )
    return {
        "source_result_files": [str(path) for path in result_paths],
        "base_url": args.base_url,
        "model": args.model,
        "tokenizer": args.tokenizer,
        "offset_source": args.effective_offset_source,
        "prompt_logprobs": args.prompt_logprobs,
        "endpoint": "/v1/completions",
        "request_shape": {
            "echo": True,
            "max_tokens": 0,
            "logprobs": 0,
            "prompt_logprobs": args.prompt_logprobs,
            "add_special_tokens": False,
        },
        "window_size": args.window_size,
        "stride": args.stride,
        "tail_tokens": args.tail_tokens,
        "bottom_fraction": args.bottom_fraction,
        "workers": args.workers,
        "keep_percents": keep_percents,
        "unique_theorems": len({row["theorem_name"] for row in rows}),
        "attempt_rows_analyzed": len(rows),
        "attempt_rows_scored": len(scored_rows),
        "correct_attempts": len(passed_rows),
        "wrong_attempts": len(failed_rows),
        "scoring_errors": len(scoring_errors),
        "missing_metrics": sum(1 for row in scored_rows if int(row["scored_token_count"]) <= 0),
        "status_counts": dict(status_counts),
        "baseline_attempt_success_rate": baseline_attempt_rate,
        "baseline_theorem_solved_rate": theorem_solved_rate(rows),
        "global_correlation": global_corr,
        "within_theorem_auc": within_theorem,
        "confidence_filtering": filtering,
        "baseline_generated_token_proofconf_summary": str(
            Path(__file__).resolve().parents[2]
            / "goedel-confidence/results/2026-04-26-fixed32/summary.json"
        ),
    }


def write_summary_md(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# Prompt-Logprob Proof-Body Scoring",
        "",
        f"- Unique theorems: `{summary['unique_theorems']}`",
        f"- Attempt rows analyzed: `{summary['attempt_rows_analyzed']}`",
        f"- Attempt rows scored: `{summary['attempt_rows_scored']}`",
        f"- Correct attempts: `{summary['correct_attempts']}`",
        f"- Wrong attempts: `{summary['wrong_attempts']}`",
        f"- Scoring errors: `{summary['scoring_errors']}`",
        f"- Missing metrics: `{summary['missing_metrics']}`",
        "",
        "## Configuration",
        f"- Endpoint: `{summary['endpoint']}`",
        f"- Model: `{summary['model']}`",
        f"- Tokenizer: `{summary['tokenizer']}`",
        f"- Offset source: `{summary['offset_source']}`",
        f"- Request: `echo=true`, `max_tokens=0`, `logprobs=0`, "
        f"`prompt_logprobs={summary['prompt_logprobs']}`",
        f"- Body mask: `{summary['offset_source']}` token offsets with `add_special_tokens=false`",
        f"- Window: `size={summary['window_size']}`, `stride={summary['stride']}`",
        f"- Tail tokens: `{summary['tail_tokens']}`",
        "",
        "## Baseline Labels",
        f"- Attempt pass rate: `{summary['baseline_attempt_success_rate']:.6f}`",
        f"- Theorem solved rate: `{summary['baseline_theorem_solved_rate']:.6f}`",
        "",
        "## Global Correlation",
    ]
    for metric in METRICS:
        row = summary["global_correlation"][metric]
        lines.append(
            f"- `{metric}`: point_biserial=`{row['point_biserial']:.6f}`, "
            f"AUC=`{row['auc']:.6f}`"
        )
    lines.extend(["", "## Within-Theorem AUC"])
    for metric in METRICS:
        row = summary["within_theorem_auc"][metric]
        lines.append(
            f"- `{metric}`: mean_per_theorem_auc=`{row['mean_per_theorem_auc']:.6f}`, "
            f"below_0.5=`{row['theorems_below_0_5']}/{row['valid_theorems']}`"
        )
    lines.extend(["", "## Filtering (Top-k% by score within theorem)"])
    for metric in METRICS:
        lines.append(f"- `{metric}`:")
        filt = summary["confidence_filtering"][metric]
        if not filt:
            lines.append("  - no valid rows")
            continue
        lines.append(
            f"  - baseline attempt/theorem: `{filt['baseline_attempt_success_rate']:.6f}` / "
            f"`{filt['baseline_theorem_solved_rate']:.6f}`"
        )
        for pct, item in filt["top_percent"].items():
            lines.append(
                f"  - top {pct}%: attempts=`{item['kept_attempts']}`, "
                f"attempt_success=`{item['attempt_success_rate']:.6f}`, "
                f"theorem_solved=`{item['theorem_solved_rate']:.6f}`"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_manifest_summary(
    path: Path,
    attempts: Sequence[ProofAttempt],
    result_paths: Sequence[Path],
) -> None:
    payload = {
        "source_result_files": [str(path) for path in result_paths],
        "unique_theorems": len({attempt.theorem_name for attempt in attempts}),
        "attempt_rows": len(attempts),
        "correct_attempts": sum(1 for attempt in attempts if attempt.lean_success),
        "wrong_attempts": sum(1 for attempt in attempts if not attempt.lean_success),
        "status_counts": dict(Counter(attempt.status for attempt in attempts)),
        "missing_proof_files": sum(
            1
            for attempt in attempts
            if attempt.proof_file is None or not attempt.proof_file.exists()
        ),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-glob", action="append", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-key", default="dummy")
    parser.add_argument("--model", default="Goedel-Prover-V2-8B")
    parser.add_argument("--tokenizer", default="Goedel-LM/Goedel-Prover-V2-8B")
    parser.add_argument("--offset-source", choices=("auto", "response", "tokenizer"), default="auto")
    parser.add_argument("--trust-remote-code", action="store_true", default=True)
    parser.add_argument("--no-trust-remote-code", action="store_false", dest="trust_remote_code")
    parser.add_argument("--prompt-logprobs", type=int, default=0)
    parser.add_argument("--request-timeout", type=int, default=7200)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--window-size", type=int, default=24)
    parser.add_argument("--stride", type=int, default=6)
    parser.add_argument("--tail-tokens", type=int, default=256)
    parser.add_argument("--bottom-fraction", type=float, default=0.1)
    parser.add_argument("--keep-percents", default="10,25,50")
    parser.add_argument("--theorem", action="append", default=[])
    parser.add_argument("--limit-theorems", type=int)
    parser.add_argument("--limit-attempts", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    result_paths = discover_result_paths(args.results_glob)
    if not result_paths:
        raise SystemExit("No result files matched.")

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    theorem_filter = set(args.theorem) if args.theorem else None
    attempts = collect_attempts(
        result_paths,
        theorem_filter=theorem_filter,
        limit_theorems=args.limit_theorems,
        limit_attempts=args.limit_attempts,
    )
    if not attempts:
        raise SystemExit("No proof attempts matched.")

    manifest_path = output_dir / "manifest_summary.json"
    write_manifest_summary(manifest_path, attempts, result_paths)
    if args.dry_run:
        print(json.dumps({"manifest_summary": str(manifest_path)}, ensure_ascii=False))
        return 0

    trace_jsonl = output_dir / "trace_metrics.jsonl"
    existing_keys = load_existing_keys(trace_jsonl) if args.resume else set()
    pending = [
        attempt
        for attempt in attempts
        if (attempt.theorem_name, attempt.candidate_index) not in existing_keys
    ]

    tokenizer = None
    if args.offset_source == "tokenizer" or (
        args.offset_source == "auto" and importlib.util.find_spec("transformers") is not None
    ):
        tokenizer = load_tokenizer(args.tokenizer, trust_remote_code=args.trust_remote_code)
        args.effective_offset_source = "tokenizer"
    else:
        args.effective_offset_source = "response"
    progress_path = output_dir / "progress.jsonl"
    if not args.resume:
        trace_jsonl.write_text("", encoding="utf-8")
        progress_path.write_text("", encoding="utf-8")

    rows: list[dict[str, Any]] = []
    if args.resume and trace_jsonl.exists():
        rows.extend(iter_jsonl(trace_jsonl))

    write_lock = Lock()
    started_at = time.time()
    completed = 0
    with trace_jsonl.open("a", encoding="utf-8") as trace_handle, progress_path.open(
        "a", encoding="utf-8"
    ) as progress_handle:
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            future_map = {
                executor.submit(
                    score_attempt,
                    attempt,
                    tokenizer=tokenizer,
                    offset_source=args.effective_offset_source,
                    base_url=args.base_url,
                    api_key=args.api_key,
                    model=args.model,
                    prompt_logprobs=args.prompt_logprobs,
                    timeout=args.request_timeout,
                    window_size=args.window_size,
                    stride=args.stride,
                    tail_tokens=args.tail_tokens,
                    bottom_fraction=args.bottom_fraction,
                ): attempt
                for attempt in pending
            }
            for future in as_completed(future_map):
                row = future.result()
                completed += 1
                rows.append(row)
                with write_lock:
                    trace_handle.write(json.dumps(row, ensure_ascii=False, allow_nan=True) + "\n")
                    trace_handle.flush()
                    progress_handle.write(
                        json.dumps(
                            {
                                "completed": completed,
                                "pending": len(pending),
                                "total_attempts": len(attempts),
                                "theorem_name": row["theorem_name"],
                                "candidate_index": row["candidate_index"],
                                "scoring_error": row.get("scoring_error"),
                                "elapsed_seconds": row["elapsed_seconds"],
                                "wall_elapsed_seconds": time.time() - started_at,
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    progress_handle.flush()

    rows = sorted(rows, key=lambda row: (str(row["theorem_name"]), int(row["candidate_index"])))
    keep_percents = [int(x) for x in args.keep_percents.split(",") if x.strip()]
    summary = summarize_rows(rows, result_paths=result_paths, keep_percents=keep_percents, args=args)

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
            "sum_logprob",
            "min_logprob",
            "bottom10_logprob",
            "lowest_window_logprob",
            "tail_logprob",
            "body_token_count",
            "scored_token_count",
            "missing_token_logprobs",
            "window_count",
            "prompt_logprobs_present",
            "response_token_count",
            "tokenizer_token_count",
            "bos_shift",
            "boundary_crossing_tokens",
            "prefix_chars",
            "body_chars",
            "full_chars",
            "scoring_error",
            "elapsed_seconds",
            "result_path",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(nan_safe_row({key: row.get(key) for key in fieldnames}))

    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_summary_md(output_dir / "summary.md", summary)

    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "manifest_summary": str(manifest_path),
                "summary_json": str(summary_path),
                "trace_csv": str(csv_path),
                "trace_jsonl": str(trace_jsonl),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
