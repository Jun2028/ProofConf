from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import os
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

from proofconf.lean.verifier import LeanVerifier, VerifyRequest, normalize_proof_body
from proofconf.llm.deepseek_client import DeepSeekClient
from proofconf.llm.gemini_client import GeminiClient
from proofconf.llm.prompts import SYSTEM_PROMPT, build_user_prompt
from proofconf.metrics.token_confidence import (
    confidence_metrics,
    token_confidence_series,
    weakest_span_annotation,
)
from proofconf.pipeline.dataset import Problem, load_problems
from proofconf.utils.env import load_env_file
from proofconf.utils.io import append_jsonl, ensure_dir, write_json
from proofconf.utils.run_logger import RunLogger, snapshot_env, snapshot_git


@dataclass
class ModelConfig:
    provider: str
    model: str
    env_file: str
    temperature: float
    max_tokens: int
    top_logprobs: int


@dataclass
class RunConfig:
    dataset_json: str
    difficulty_levels: List[str]
    split: str
    theorem_offset: int
    num_theorems: int
    samples_per_theorem: int
    window_size_tokens: int
    window_stride_tokens: int
    llm_parallel_requests: int = 1
    lean_parallel_workers: int = 1
    lean_batch_size: int = 1
    tail_tokens: int = 256
    token_confidence_method: str = "paper_topk"
    token_confidence_topk: int = 20
    token_confidence_require_full_topk: bool = False
    token_confidence_fallback_to_chosen: bool = False
    probe_prefix_parts: bool = False
    prefix_probe_quantiles: List[float] = field(default_factory=lambda: [0.25, 0.5, 0.75])
    prefix_probe_timeout_s: int = 30
    filter_top_percents: List[int] = field(default_factory=lambda: [10, 25, 50])
    models: List[ModelConfig] = field(default_factory=list)


def load_config(path: Path) -> RunConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    models = [ModelConfig(**row) for row in payload["models"]]
    return RunConfig(
        dataset_json=payload["dataset_json"],
        difficulty_levels=payload["difficulty_levels"],
        split=payload["split"],
        theorem_offset=int(payload.get("theorem_offset", 0)),
        num_theorems=int(payload["num_theorems"]),
        samples_per_theorem=int(payload["samples_per_theorem"]),
        window_size_tokens=int(payload["window_size_tokens"]),
        window_stride_tokens=int(payload["window_stride_tokens"]),
        llm_parallel_requests=int(payload.get("llm_parallel_requests", 1)),
        lean_parallel_workers=int(payload.get("lean_parallel_workers", 1)),
        lean_batch_size=int(payload.get("lean_batch_size", 1)),
        tail_tokens=int(payload.get("tail_tokens", 256)),
        token_confidence_method=str(payload.get("token_confidence_method", "paper_topk")),
        token_confidence_topk=int(payload.get("token_confidence_topk", 20)),
        token_confidence_require_full_topk=bool(payload.get("token_confidence_require_full_topk", False)),
        token_confidence_fallback_to_chosen=bool(payload.get("token_confidence_fallback_to_chosen", False)),
        probe_prefix_parts=bool(payload.get("probe_prefix_parts", False)),
        prefix_probe_quantiles=[float(x) for x in payload.get("prefix_probe_quantiles", [0.25, 0.5, 0.75])],
        prefix_probe_timeout_s=int(payload.get("prefix_probe_timeout_s", 30)),
        filter_top_percents=[int(x) for x in payload.get("filter_top_percents", [10, 25, 50])],
        models=models,
    )


def create_run_id(tag: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%SZ")
    safe_tag = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in tag)
    return f"{ts}_{safe_tag}".strip("_")


def classify_error(stderr: str) -> str:
    text = stderr.lower()
    if "too many open files in system" in text or "too many open files" in text:
        return "fd_exhaustion"
    if "failed to open file" in text or "failed to open '" in text or "failed to open " in text:
        return "file_open_error"
    if "unknown option" in text:
        return "config_error"
    if "unknown constant" in text:
        return "unknown_constant"
    if "type mismatch" in text:
        return "type_mismatch"
    if "timeout" in text:
        return "timeout"
    if "tactic" in text:
        return "tactic_failure"
    if "no goals to be solved" in text:
        return "no_goals"
    if "unsolved goals" in text:
        return "unsolved_goals"
    if "application type mismatch" in text:
        return "type_mismatch"
    return "other"


def bounded_workers(requested: int, hard_limit: int) -> int:
    return max(1, min(max(1, requested), max(1, hard_limit)))


def available_cpu_count() -> int:
    local_count = os.cpu_count() or 1
    limits: List[int] = []
    for key in ("PBS_NCPUS", "NCPUS", "PBS_NP"):
        value = os.environ.get(key, "").strip()
        if value.isdigit():
            limits.append(int(value))
    if limits:
        return max(1, min(local_count, min(limits)))
    return max(1, local_count)


def chunked(items: List[Dict[str, Any]], size: int) -> Iterable[List[Dict[str, Any]]]:
    safe_size = max(1, size)
    for idx in range(0, len(items), safe_size):
        yield items[idx : idx + safe_size]


def safe_mean(values: List[float]) -> float:
    clean = [v for v in values if not math.isnan(v)]
    if not clean:
        return float("nan")
    return sum(clean) / len(clean)


def safe_std(values: List[float]) -> float:
    clean = [v for v in values if not math.isnan(v)]
    n = len(clean)
    if n <= 1:
        return float("nan")
    mean = sum(clean) / n
    var = sum((v - mean) ** 2 for v in clean) / n
    return math.sqrt(var)


def point_biserial(x_values: List[float], y_binary: List[int]) -> float:
    if len(x_values) != len(y_binary) or len(x_values) < 2:
        return float("nan")

    pairs = [(x, y) for x, y in zip(x_values, y_binary) if not math.isnan(x)]
    if len(pairs) < 2:
        return float("nan")

    xs = [x for x, _ in pairs]
    ys = [y for _, y in pairs]
    n = len(xs)
    p = sum(ys) / n
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


def theorem_solved_rate(rows: List[Dict[str, Any]]) -> float:
    by_theorem: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        by_theorem.setdefault(row["theorem_name"], []).append(row)
    if not by_theorem:
        return float("nan")
    solved = sum(1 for group in by_theorem.values() if any(r["lean_success"] for r in group))
    return solved / len(by_theorem)


def confidence_filtering_stats(
    rows: List[Dict[str, Any]],
    metric_key: str,
    keep_percents: List[int],
) -> Dict[str, Any]:
    filtered = [r for r in rows if not math.isnan(float(r.get(metric_key, float("nan"))))]
    by_theorem: Dict[str, List[Dict[str, Any]]] = {}
    for row in filtered:
        by_theorem.setdefault(row["theorem_name"], []).append(row)

    if not by_theorem:
        return {}

    baseline_attempt_rate = sum(1 for r in filtered if r["lean_success"]) / len(filtered)
    baseline_theorem_rate = theorem_solved_rate(filtered)
    out: Dict[str, Any] = {
        "baseline_attempt_success_rate": baseline_attempt_rate,
        "baseline_theorem_solved_rate": baseline_theorem_rate,
        "top_percent": {},
    }

    for pct in keep_percents:
        kept_rows: List[Dict[str, Any]] = []
        for theorem_rows in by_theorem.values():
            ordered = sorted(theorem_rows, key=lambda r: float(r[metric_key]), reverse=True)
            k = max(1, math.ceil(len(ordered) * (pct / 100.0)))
            kept_rows.extend(ordered[:k])

        attempt_rate = sum(1 for r in kept_rows if r["lean_success"]) / len(kept_rows)
        out["top_percent"][str(pct)] = {
            "kept_attempts": len(kept_rows),
            "attempt_success_rate": attempt_rate,
            "theorem_solved_rate": theorem_solved_rate(kept_rows),
        }
    return out


def choose_prefix_cuts(total_lines: int, quantiles: List[float]) -> List[int]:
    if total_lines < 2:
        return []
    cuts = set()
    for q in quantiles:
        if q <= 0.0 or q >= 1.0:
            continue
        cut = int(round(total_lines * q))
        cut = max(1, min(total_lines - 1, cut))
        cuts.add(cut)
    return sorted(cuts)


def build_prefix_part_rows(
    problem: Problem,
    sample_id: str,
    provider: str,
    model: str,
    sample_tag: str,
    proof_text: str,
    token_scores: List[float],
    verifier: LeanVerifier,
    config: RunConfig,
) -> List[Dict[str, Any]]:
    normalized = normalize_proof_body(proof_text)
    lines = normalized.splitlines()
    unit_kind = "line"
    units = lines
    joiner = "\n"

    if len(lines) < 2:
        words = normalized.split()
        if len(words) >= 2:
            unit_kind = "word"
            units = words
            joiner = " "

    cuts = choose_prefix_cuts(len(units), config.prefix_probe_quantiles)
    if not cuts:
        return []

    rows: List[Dict[str, Any]] = []
    prev_tok_cut = 0
    for part_index, cut in enumerate(cuts, start=1):
        prefix_text = joiner.join(units[:cut]).rstrip()
        if prefix_text:
            probe_body = f"{prefix_text}\nadmit"
        else:
            probe_body = "admit"

        tok_cut = 0
        if token_scores:
            tok_cut = max(1, min(len(token_scores), int(round((cut / len(units)) * len(token_scores)))))
            segment = token_scores[prev_tok_cut:tok_cut]
            part_confidence = safe_mean(segment)
            prefix_metric = confidence_metrics(
                token_scores=token_scores[:tok_cut],
                window_size=config.window_size_tokens,
                stride=config.window_stride_tokens,
                tail_tokens=config.tail_tokens,
            )
        else:
            part_confidence = float("nan")
            prefix_metric = {
                "avg_logprob": float("nan"),
                "lowest_group_confidence": float("nan"),
                "bottom10_group_confidence": float("nan"),
                "tail_confidence": float("nan"),
                "token_count": 0,
                "window_count": 0,
            }

        prev_tok_cut = tok_cut

        probe = verifier.verify(
            theorem_name=problem.theorem_name,
            header=problem.header,
            formal_statement=problem.formal_statement,
            proof_body=probe_body,
            sample_tag=f"{sample_tag}_p{part_index}_{cut}",
        )

        rows.append(
            {
                "sample_id": sample_id,
                "provider": provider,
                "model": model,
                "theorem_name": problem.theorem_name,
                "part_index": part_index,
                "part_unit": unit_kind,
                "line_cut": cut,
                "total_lines": len(units),
                "part_confidence": part_confidence,
                "prefix_avg_logprob": prefix_metric["avg_logprob"],
                "prefix_lgc": prefix_metric["lowest_group_confidence"],
                "prefix_bottom10": prefix_metric["bottom10_group_confidence"],
                "prefix_tail": prefix_metric["tail_confidence"],
                "prefix_token_count": prefix_metric["token_count"],
                "part_valid": probe.success,
                "part_lean_returncode": probe.returncode,
                "part_error_class": "none" if probe.success else classify_error(f"{probe.stderr}\n{probe.stdout}"),
                "part_lean_elapsed_ms": probe.elapsed_ms,
                "part_source_path": probe.source_path,
            }
        )
    return rows


def summarize(
    records: List[Dict[str, Any]],
    part_records: List[Dict[str, Any]],
    keep_percents: List[int],
) -> Dict[str, Any]:
    by_model: Dict[str, List[Dict[str, Any]]] = {}
    for row in records:
        key = f"{row['provider']}::{row['model']}"
        by_model.setdefault(key, []).append(row)

    by_model_parts: Dict[str, List[Dict[str, Any]]] = {}
    for row in part_records:
        key = f"{row['provider']}::{row['model']}"
        by_model_parts.setdefault(key, []).append(row)

    metric_keys = [
        "avg_logprob",
        "lowest_group_confidence",
        "bottom10_group_confidence",
        "tail_confidence",
    ]
    filter_metrics = ["lowest_group_confidence", "bottom10_group_confidence", "tail_confidence"]

    model_summary: Dict[str, Any] = {}
    for key, rows in by_model.items():
        passed = [r for r in rows if r["lean_success"]]
        failed = [r for r in rows if not r["lean_success"]]
        y = [1 if r["lean_success"] else 0 for r in rows]

        corr = {}
        for metric in metric_keys:
            corr[metric] = point_biserial([float(r.get(metric, float("nan"))) for r in rows], y)

        filtering = {
            metric: confidence_filtering_stats(rows, metric, keep_percents) for metric in filter_metrics
        }

        model_row: Dict[str, Any] = {
            "attempts": len(rows),
            "success_count": len(passed),
            "success_rate": (len(passed) / len(rows)) if rows else float("nan"),
            "theorem_solved_rate": theorem_solved_rate(rows),
            "mean_avg_logprob": safe_mean([r["avg_logprob"] for r in rows]),
            "mean_lgc": safe_mean([r["lowest_group_confidence"] for r in rows]),
            "mean_bottom10": safe_mean([r["bottom10_group_confidence"] for r in rows]),
            "mean_tail_confidence": safe_mean([r["tail_confidence"] for r in rows]),
            "pass_mean_lgc": safe_mean([r["lowest_group_confidence"] for r in passed]),
            "fail_mean_lgc": safe_mean([r["lowest_group_confidence"] for r in failed]),
            "pass_mean_bottom10": safe_mean([r["bottom10_group_confidence"] for r in passed]),
            "fail_mean_bottom10": safe_mean([r["bottom10_group_confidence"] for r in failed]),
            "point_biserial": corr,
            "confidence_filtering": filtering,
        }

        part_rows = by_model_parts.get(key, [])
        if part_rows:
            part_y = [1 if r["part_valid"] else 0 for r in part_rows]
            model_row["part_probes"] = {
                "parts_tested": len(part_rows),
                "parts_valid_count": sum(part_y),
                "parts_valid_rate": (sum(part_y) / len(part_rows)) if part_rows else float("nan"),
                "part_confidence_point_biserial": point_biserial(
                    [float(r["part_confidence"]) for r in part_rows],
                    part_y,
                ),
                "prefix_lgc_point_biserial": point_biserial(
                    [float(r["prefix_lgc"]) for r in part_rows],
                    part_y,
                ),
                "valid_mean_part_confidence": safe_mean(
                    [float(r["part_confidence"]) for r in part_rows if r["part_valid"]]
                ),
                "invalid_mean_part_confidence": safe_mean(
                    [float(r["part_confidence"]) for r in part_rows if not r["part_valid"]]
                ),
            }

        model_summary[key] = model_row

    return {
        "records": len(records),
        "part_records": len(part_records),
        "models": model_summary,
    }


def write_summary_md(path: Path, summary: Dict[str, Any], config: RunConfig, run_id: str) -> None:
    lines = [
        f"# Run Summary: {run_id}",
        "",
        "## Configuration",
        f"- Dataset: `{config.dataset_json}`",
        f"- Difficulty levels: {', '.join(config.difficulty_levels)}",
        f"- Split: `{config.split}`",
        f"- Theorem offset: {config.theorem_offset}",
        f"- Number of theorems: {config.num_theorems}",
        f"- Samples per theorem per model: {config.samples_per_theorem}",
        f"- Parallel LLM requests: {config.llm_parallel_requests}",
        f"- Parallel Lean workers: {config.lean_parallel_workers}",
        f"- Lean batch size per process: {config.lean_batch_size}",
        f"- Token confidence method: `{config.token_confidence_method}`",
        f"- Token confidence top-k: {config.token_confidence_topk}",
        f"- Token confidence require full top-k: {config.token_confidence_require_full_topk}",
        f"- Token confidence fallback to chosen: {config.token_confidence_fallback_to_chosen}",
        f"- Confidence window: size={config.window_size_tokens}, stride={config.window_stride_tokens}",
        f"- Tail confidence tokens: {config.tail_tokens}",
        f"- Prefix part probes enabled: {config.probe_prefix_parts}",
        (
            f"- Prefix part probe quantiles: {', '.join(str(x) for x in config.prefix_probe_quantiles)}"
            if config.probe_prefix_parts
            else ""
        ),
        (
            f"- Prefix part probe timeout (s): {config.prefix_probe_timeout_s}"
            if config.probe_prefix_parts
            else ""
        ),
        "",
        "## Model Comparison",
    ]

    avg_score_label = (
        "Mean avg token confidence (paper C_avg)"
        if config.token_confidence_method == "paper_topk"
        else "Mean avg token logprob"
    )

    for model_key, row in summary["models"].items():
        lines.extend(
            [
                f"### {model_key}",
                f"- Attempts: {row['attempts']}",
                f"- Lean pass count: {row['success_count']}",
                f"- Lean pass rate: {row['success_rate']:.3f}",
                f"- Theorem solved rate (any attempt passes): {row['theorem_solved_rate']:.3f}",
                f"- {avg_score_label}: {row['mean_avg_logprob']:.4f}",
                f"- Mean LGC: {row['mean_lgc']:.4f}",
                f"- Mean Bottom-10%: {row['mean_bottom10']:.4f}",
                f"- Mean tail confidence: {row['mean_tail_confidence']:.4f}",
                f"- Pass mean LGC: {row['pass_mean_lgc']:.4f}",
                f"- Fail mean LGC: {row['fail_mean_lgc']:.4f}",
                "",
                "- Point-biserial correlation with Lean success:",
                f"  - avg_logprob: {row['point_biserial']['avg_logprob']:.4f}",
                f"  - lowest_group_confidence: {row['point_biserial']['lowest_group_confidence']:.4f}",
                f"  - bottom10_group_confidence: {row['point_biserial']['bottom10_group_confidence']:.4f}",
                f"  - tail_confidence: {row['point_biserial']['tail_confidence']:.4f}",
                "",
            ]
        )

        filters = row["confidence_filtering"]
        for metric_name, metric_rows in filters.items():
            if not metric_rows:
                continue
            lines.append(f"- Confidence filtering by `{metric_name}`:")
            lines.append(
                "  - baseline attempt/theorem rates: "
                f"{metric_rows['baseline_attempt_success_rate']:.3f} / "
                f"{metric_rows['baseline_theorem_solved_rate']:.3f}"
            )
            for pct_key, pct_row in metric_rows["top_percent"].items():
                lines.append(
                    f"  - top {pct_key}% kept -> attempts={pct_row['kept_attempts']}, "
                    f"attempt success={pct_row['attempt_success_rate']:.3f}, "
                    f"theorem solved={pct_row['theorem_solved_rate']:.3f}"
                )
            lines.append("")

        part = row.get("part_probes")
        if part:
            lines.extend(
                [
                    "- Prefix part probes:",
                    f"  - parts tested: {part['parts_tested']}",
                    f"  - part valid rate: {part['parts_valid_rate']:.3f}",
                    f"  - part_confidence point-biserial: {part['part_confidence_point_biserial']:.4f}",
                    f"  - prefix_lgc point-biserial: {part['prefix_lgc_point_biserial']:.4f}",
                    "",
                ]
            )

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def make_client(model_cfg: ModelConfig):
    env = load_env_file(model_cfg.env_file)
    if model_cfg.provider == "deepseek":
        api_key = env.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            raise RuntimeError(f"Missing DEEPSEEK_API_KEY in {model_cfg.env_file}")
        return DeepSeekClient(api_key=api_key, model=model_cfg.model)

    if model_cfg.provider == "gemini":
        api_key = env.get("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError(f"Missing GEMINI_API_KEY in {model_cfg.env_file}")
        return GeminiClient(api_key=api_key, model=model_cfg.model)

    raise RuntimeError(f"Unsupported provider: {model_cfg.provider}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run confidence experiment on miniF2F.")
    parser.add_argument("--config", default="configs/initial_run.json")
    parser.add_argument("--tag", default="initial")
    parser.add_argument("--mini-f2f-root", default="datasets/miniF2F/raw/miniF2F-lean4-main")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    runs_root = Path(os.environ.get("PROOFCONF_RUNS_ROOT", str(repo_root / "runs"))).resolve()
    logs_root = Path(os.environ.get("PROOFCONF_LOGS_ROOT", str(repo_root / "logs"))).resolve()
    config_path = (repo_root / args.config).resolve()
    config = load_config(config_path)

    run_id = create_run_id(args.tag)
    run_dir = ensure_dir(runs_root / run_id)
    log_dir = ensure_dir(logs_root / "run" / run_id)
    meta_dir = ensure_dir(run_dir / "meta")

    logger = RunLogger(log_dir)
    snapshot_env(log_dir)
    snapshot_git(log_dir, repo_root)

    write_json(log_dir / "artifacts.json", {"run_dir": str(run_dir)})
    write_json(run_dir / "config.resolved.json", json.loads(config_path.read_text(encoding="utf-8")))

    start = datetime.now(timezone.utc)
    logger.event("INFO", "run_start", run_id=run_id, config=str(config_path))

    samples_path = run_dir / "samples.jsonl"
    verdicts_path = run_dir / "verdicts.jsonl"
    metrics_path = run_dir / "metrics.jsonl"
    parts_path = run_dir / "parts.jsonl"

    cpu_total = available_cpu_count()
    llm_workers = bounded_workers(config.llm_parallel_requests, cpu_total)
    lean_workers = bounded_workers(config.lean_parallel_workers, cpu_total)
    lean_batch_size = max(1, config.lean_batch_size)
    # Keep summary/config outputs aligned with effective bounded workers.
    config.llm_parallel_requests = llm_workers
    config.lean_parallel_workers = lean_workers
    config.lean_batch_size = lean_batch_size
    logger.event(
        "INFO",
        "parallel_plan",
        cpu_total=cpu_total,
        llm_workers=llm_workers,
        lean_workers=lean_workers,
        lean_batch_size=lean_batch_size,
    )

    pool_limit = config.theorem_offset + config.num_theorems
    selected = load_problems(
        dataset_json=repo_root / config.dataset_json,
        difficulty_levels=config.difficulty_levels,
        split=config.split,
        limit=pool_limit,
    )
    problems = selected[config.theorem_offset : pool_limit]
    if len(problems) < config.num_theorems:
        logger.event(
            "WARN",
            "dataset_shortfall",
            requested=config.num_theorems,
            available=len(problems),
            offset=config.theorem_offset,
        )
    write_json(run_dir / "dataset_manifest.json", {"theorems": [p.theorem_name for p in problems]})

    verifier = LeanVerifier(Path(repo_root / args.mini_f2f_root), timeout_s=180)
    probe_verifier = (
        LeanVerifier(Path(repo_root / args.mini_f2f_root), timeout_s=config.prefix_probe_timeout_s)
        if config.probe_prefix_parts
        else verifier
    )

    logger.event("INFO", "lean_warmup_start")
    warmup = verifier.verify(
        theorem_name="proofconf_warmup",
        header="import Mathlib\n",
        formal_statement="theorem proofconf_warmup : True := by\n",
        proof_body="trivial",
        sample_tag="warmup",
    )
    logger.event(
        "INFO",
        "lean_warmup_done",
        success=warmup.success,
        elapsed_ms=warmup.elapsed_ms,
        returncode=warmup.returncode,
    )
    if not warmup.success:
        logger.event(
            "ERROR",
            "lean_warmup_failed",
            stdout=warmup.stdout,
            stderr=warmup.stderr,
        )
        raise RuntimeError("Lean warmup failed; aborting run to avoid invalid large-scale results.")

    records: List[Dict[str, Any]] = []
    part_records: List[Dict[str, Any]] = []

    for model_cfg in config.models:
        client = make_client(model_cfg)
        logger.event("INFO", "model_start", provider=model_cfg.provider, model=model_cfg.model)

        for problem in problems:
            prompt = build_user_prompt(problem)
            gen_rows: List[Dict[str, Any]] = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=llm_workers) as gen_pool:
                gen_futures: Dict[concurrent.futures.Future[Any], Dict[str, Any]] = {}
                for sample_idx in range(config.samples_per_theorem):
                    sample_tag = f"{model_cfg.provider}_{sample_idx}"
                    sample_id = f"{problem.theorem_name}::{model_cfg.provider}::{sample_idx}"
                    future = gen_pool.submit(
                        client.generate,
                        system_prompt=SYSTEM_PROMPT,
                        user_prompt=prompt,
                        temperature=model_cfg.temperature,
                        max_tokens=model_cfg.max_tokens,
                        top_logprobs=model_cfg.top_logprobs,
                    )
                    gen_futures[future] = {
                        "sample_idx": sample_idx,
                        "sample_tag": sample_tag,
                        "sample_id": sample_id,
                    }

                for future in concurrent.futures.as_completed(gen_futures):
                    meta = gen_futures[future]
                    sample_id = meta["sample_id"]
                    sample_tag = meta["sample_tag"]
                    try:
                        llm_resp = future.result()
                        chosen_logprobs = [tok.logprob for tok in llm_resp.tokens]
                        top_logprobs = [[lp for _, lp in tok.top_logprobs] for tok in llm_resp.tokens]
                        token_scores = token_confidence_series(
                            chosen_logprobs=chosen_logprobs,
                            top_logprobs=top_logprobs,
                            method=config.token_confidence_method,
                            top_k=config.token_confidence_topk,
                            require_full_topk=config.token_confidence_require_full_topk,
                            fallback_to_chosen=config.token_confidence_fallback_to_chosen,
                        )
                        token_text = [tok.token for tok in llm_resp.tokens]
                        metric = confidence_metrics(
                            token_scores=token_scores,
                            window_size=config.window_size_tokens,
                            stride=config.window_stride_tokens,
                            tail_tokens=config.tail_tokens,
                        )
                        span_annotation = weakest_span_annotation(
                            tokens=token_text,
                            logprobs=token_scores,
                            window_size=config.window_size_tokens,
                            stride=config.window_stride_tokens,
                        )
                        sample_row = {
                            "sample_id": sample_id,
                            "provider": model_cfg.provider,
                            "model": model_cfg.model,
                            "theorem_name": problem.theorem_name,
                            "difficulty_level": problem.difficulty_level,
                            "difficulty": problem.difficulty,
                            "text": llm_resp.text,
                            "token_count": len(llm_resp.tokens),
                        }
                        metric_row = {
                            "sample_id": sample_id,
                            "provider": model_cfg.provider,
                            "model": model_cfg.model,
                            "theorem_name": problem.theorem_name,
                            **metric,
                            **span_annotation,
                        }
                        append_jsonl(samples_path, sample_row)
                        append_jsonl(metrics_path, metric_row)
                        gen_rows.append(
                            {
                                **sample_row,
                                "sample_tag": sample_tag,
                                "token_scores": token_scores,
                                "metric": metric,
                                "metric_row": metric_row,
                            }
                        )
                    except Exception as exc:
                        logger.event(
                            "ERROR",
                            "sample_error",
                            sample_id=sample_id,
                            stage="generate",
                            error=str(exc),
                            traceback=traceback.format_exc(),
                        )

            if not gen_rows:
                continue

            batches = list(chunked(gen_rows, lean_batch_size))
            logger.event(
                "INFO",
                "verify_dispatch",
                theorem_name=problem.theorem_name,
                attempts=len(gen_rows),
                batch_size=lean_batch_size,
                batch_count=len(batches),
                lean_workers=lean_workers,
            )

            def verify_batch_task(batch_index: int, batch_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
                requests = [
                    VerifyRequest(
                        theorem_name=problem.theorem_name,
                        header=problem.header,
                        formal_statement=problem.formal_statement,
                        proof_body=row["text"],
                        sample_tag=row["sample_tag"],
                    )
                    for row in batch_rows
                ]
                results = verifier.verify_many(
                    requests=requests,
                    batch_tag=f"{model_cfg.provider}_{problem.theorem_name}_b{batch_index}",
                )
                if len(results) != len(batch_rows):
                    raise RuntimeError(
                        f"Verifier returned {len(results)} results for {len(batch_rows)} rows "
                        f"(theorem={problem.theorem_name}, batch_index={batch_index})"
                    )

                out: List[Dict[str, Any]] = []
                for row, verify_result in zip(batch_rows, results):
                    part_rows: List[Dict[str, Any]] = []
                    if config.probe_prefix_parts:
                            part_rows = build_prefix_part_rows(
                            problem=problem,
                            sample_id=row["sample_id"],
                            provider=model_cfg.provider,
                            model=model_cfg.model,
                                sample_tag=row["sample_tag"],
                                proof_text=row["text"],
                                token_scores=row["token_scores"],
                                verifier=probe_verifier,
                                config=config,
                            )
                    out.append({"row": row, "verify": verify_result, "parts": part_rows})
                return out

            with concurrent.futures.ThreadPoolExecutor(max_workers=lean_workers) as verify_pool:
                verify_futures = {
                    verify_pool.submit(verify_batch_task, batch_index, batch_rows): (batch_index, batch_rows)
                    for batch_index, batch_rows in enumerate(batches)
                }
                for future in concurrent.futures.as_completed(verify_futures):
                    batch_index, batch_rows = verify_futures[future]
                    try:
                        batch_results = future.result()
                    except Exception as exc:
                        logger.event(
                            "ERROR",
                            "verify_batch_error",
                            theorem_name=problem.theorem_name,
                            batch_index=batch_index,
                            batch_size=len(batch_rows),
                            error=str(exc),
                            traceback=traceback.format_exc(),
                        )
                        for row in batch_rows:
                            logger.event(
                                "ERROR",
                                "sample_error",
                                sample_id=row["sample_id"],
                                stage="verify",
                                error=f"batch failure: {exc}",
                            )
                        continue

                    for result in batch_results:
                        row = result["row"]
                        sample_id = row["sample_id"]
                        metric = row["metric"]
                        verify_result = result["verify"]
                        part_rows = result["parts"]

                        verdict_row = {
                            "sample_id": sample_id,
                            "provider": model_cfg.provider,
                            "model": model_cfg.model,
                            "theorem_name": problem.theorem_name,
                            "lean_success": verify_result.success,
                            "lean_returncode": verify_result.returncode,
                            "error_class": "none"
                            if verify_result.success
                            else classify_error(f"{verify_result.stderr}\n{verify_result.stdout}"),
                            "lean_elapsed_ms": verify_result.elapsed_ms,
                            "lean_stdout": verify_result.stdout,
                            "lean_stderr": verify_result.stderr,
                            "source_path": verify_result.source_path,
                        }
                        append_jsonl(verdicts_path, verdict_row)

                        records.append(
                            {
                                **row["metric_row"],
                                "lean_success": verify_result.success,
                            }
                        )

                        for part_row in part_rows:
                            append_jsonl(parts_path, part_row)
                            part_records.append(part_row)

                        logger.event(
                            "INFO",
                            "sample_done",
                            sample_id=sample_id,
                            lean_success=verify_result.success,
                            lgc=metric["lowest_group_confidence"],
                            bottom10=metric["bottom10_group_confidence"],
                            tail=metric["tail_confidence"],
                            token_count=len(row["token_scores"]),
                            probed_parts=len(part_rows),
                        )

    summary = summarize(records, part_records, config.filter_top_percents)
    write_json(run_dir / "summary.json", summary)
    write_summary_md(run_dir / "summary.md", summary, config, run_id)

    end = datetime.now(timezone.utc)
    write_json(
        meta_dir / "execution.json",
        {
            "run_id": run_id,
            "command": " ".join(sys.argv),
            "log_dir": str(log_dir),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "exit_code": 0,
        },
    )
    logger.event("INFO", "run_end", run_id=run_id, elapsed_s=(end - start).total_seconds())


if __name__ == "__main__":
    main()
