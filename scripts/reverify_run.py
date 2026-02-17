#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from proofconf.lean.verifier import LeanVerifier, VerifyRequest


@dataclass(frozen=True)
class TheoremResult:
    theorem_name: str
    sample_count: int
    old_verdict_count: int
    old_pass: int
    new_pass: int
    batch_reports: List[Dict]


def load_jsonl(path: Path) -> List[Dict]:
    rows: List[Dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def sample_index(sample_id: str) -> int:
    return int(sample_id.rsplit("::", 1)[1])


def provider_from_sample_id(sample_id: str) -> str:
    return sample_id.split("::", 2)[1]


def short_batch_tag(run_id: str, theorem_name: str, batch_idx: int) -> str:
    digest = hashlib.sha1(f"{run_id}|{theorem_name}|{batch_idx}".encode("utf-8")).hexdigest()[:12]
    return f"rv_{digest}"


def distribution(results: List[TheoremResult], *, old: bool) -> Dict[str, int]:
    dist = Counter()
    for row in results:
        if old:
            if row.old_verdict_count > 0:
                dist[f"{row.old_pass}/{row.old_verdict_count}"] += 1
        else:
            dist[f"{row.new_pass}/{row.sample_count}"] += 1
    return dict(sorted(dist.items()))


def quantized_fraction(results: List[TheoremResult], *, old: bool) -> float | None:
    quantized = 0
    total = 0
    for row in results:
        denom = row.old_verdict_count if old else row.sample_count
        num = row.old_pass if old else row.new_pass
        if denom <= 0 or denom % 2 != 0:
            continue
        total += 1
        if num in {0, denom // 2, denom}:
            quantized += 1
    if total == 0:
        return None
    return quantized / total


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Re-evaluate an existing run with patched verifier.")
    parser.add_argument("--run-path", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--model-label", required=True)
    parser.add_argument("--dataset-json", default=Path("docs/miniF2F-Graded.json"), type=Path)
    parser.add_argument("--mini-f2f-root", default=Path("datasets/miniF2F/raw/miniF2F-lean4-main"), type=Path)
    parser.add_argument("--lean-workers", default=8, type=int)
    parser.add_argument(
        "--lean-jobs",
        default=int(os.environ.get("PROOFCONF_LEAN_JOBS", os.environ.get("LEAN_NUM_THREADS", "1"))),
        type=int,
        help="Lean internal job count passed to `lean -j` in each verifier subprocess.",
    )
    parser.add_argument("--lean-batch-size", default=16, type=int)
    parser.add_argument(
        "--lean-procs",
        default=int(os.environ.get("PROOFCONF_LAKE_MAX_PROCS", "4")),
        type=int,
        help="Max concurrent `lake env lean` subprocesses across all worker threads.",
    )
    parser.add_argument("--timeout-s", default=45, type=int)
    parser.add_argument("--max-theorems", default=0, type=int, help="For smoke tests only; 0 means all.")
    parser.add_argument(
        "--theorem-name",
        action="append",
        default=[],
        help="Restrict re-verification to specific theorem name(s). Can be repeated.",
    )
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--output-md", required=True, type=Path)
    parser.add_argument(
        "--debug-errors",
        action="store_true",
        help="Include per-batch verifier return codes and stderr snippets in JSON output.",
    )
    parser.add_argument(
        "--debug-stderr-max-chars",
        default=600,
        type=int,
        help="Maximum stderr characters captured per batch when --debug-errors is enabled.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start = time.time()

    run_path = args.run_path.resolve()
    samples_path = run_path / "samples.jsonl"
    verdicts_path = run_path / "verdicts.jsonl"

    dataset_rows = json.loads(args.dataset_json.read_text(encoding="utf-8"))
    theorem_info = {row["Theorem Name"]: row for row in dataset_rows}

    samples = load_jsonl(samples_path)
    verdicts = load_jsonl(verdicts_path)
    sample_by_id = {row["sample_id"]: row for row in samples}
    verdict_by_id = {row["sample_id"]: row for row in verdicts}

    theorem_to_sample_ids: Dict[str, List[str]] = defaultdict(list)
    for sid, sample in sample_by_id.items():
        theorem_to_sample_ids[sample["theorem_name"]].append(sid)

    theorem_names = sorted(theorem_to_sample_ids.keys())
    if args.theorem_name:
        selected = set(args.theorem_name)
        theorem_names = [th for th in theorem_names if th in selected]
        missing = sorted(selected - set(theorem_names))
        if missing:
            print(f"[warn] requested theorem(s) not found in run samples: {missing}", flush=True)
    if args.max_theorems > 0:
        theorem_names = theorem_names[: args.max_theorems]

    verifier = LeanVerifier(
        mini_f2f_root=args.mini_f2f_root.resolve(),
        timeout_s=args.timeout_s,
        lean_jobs=args.lean_jobs,
        max_parallel_invocations=args.lean_procs,
    )

    print(
        f"[reverify_start] run_id={args.run_id} model={args.model_label} "
        f"theorems={len(theorem_names)} samples={len(samples)} verdicts={len(verdicts)} "
        f"lean_workers={args.lean_workers} lean_jobs={args.lean_jobs} "
        f"lean_procs={args.lean_procs} batch={args.lean_batch_size} "
        f"launch_gap_ms={int(verifier.launch_gap_s * 1000)} "
        f"direct_lean={int(verifier._lean_env is not None)} "
        f"prune_aesop={int(verifier.prune_aesop_import)} keep_tmp={int(verifier.keep_tmp)}",
        flush=True,
    )

    def verify_theorem(theorem_name: str) -> TheoremResult:
        if theorem_name not in theorem_info:
            return TheoremResult(
                theorem_name=theorem_name,
                sample_count=len(theorem_to_sample_ids[theorem_name]),
                old_verdict_count=0,
                old_pass=0,
                new_pass=0,
                batch_reports=[],
            )

        info = theorem_info[theorem_name]
        sample_ids = sorted(theorem_to_sample_ids[theorem_name], key=sample_index)

        requests: List[VerifyRequest] = []
        for sid in sample_ids:
            sample = sample_by_id[sid]
            idx = sample_index(sid)
            provider = provider_from_sample_id(sid)
            requests.append(
                VerifyRequest(
                    theorem_name=theorem_name,
                    header=info["Header"],
                    formal_statement=info["Formal Statement"],
                    proof_body=sample["text"],
                    sample_tag=f"{provider}_{idx}",
                )
            )

        new_pass = 0
        batch_reports: List[Dict] = []
        for bstart in range(0, len(requests), args.lean_batch_size):
            batch_idx = bstart // args.lean_batch_size
            batch = requests[bstart : bstart + args.lean_batch_size]
            results = verifier.verify_many(batch, batch_tag=short_batch_tag(args.run_id, theorem_name, batch_idx))
            success_count = sum(1 for row in results if row.success)
            new_pass += success_count

            if args.debug_errors:
                rc_counts = Counter(int(row.returncode) for row in results)
                first_failed = next((row for row in results if not row.success), None)
                stderr_snippet = ""
                if first_failed is not None:
                    stderr_snippet = (first_failed.stderr or "").strip()
                    if len(stderr_snippet) > args.debug_stderr_max_chars:
                        stderr_snippet = stderr_snippet[: args.debug_stderr_max_chars] + "...[truncated]"
                batch_reports.append(
                    {
                        "batch_idx": batch_idx,
                        "batch_size": len(batch),
                        "success_count": success_count,
                        "returncodes": dict(sorted(rc_counts.items())),
                        "elapsed_ms": max((int(row.elapsed_ms) for row in results), default=0),
                        "source_path": results[0].source_path if results else "",
                        "stderr_snippet": stderr_snippet,
                    }
                )

        old_rows = [verdict_by_id[sid] for sid in sample_ids if sid in verdict_by_id]
        old_pass = sum(1 for row in old_rows if bool(row.get("lean_success", False)))

        return TheoremResult(
            theorem_name=theorem_name,
            sample_count=len(sample_ids),
            old_verdict_count=len(old_rows),
            old_pass=old_pass,
            new_pass=new_pass,
            batch_reports=batch_reports,
        )

    results: List[TheoremResult] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.lean_workers) as pool:
        futures = {pool.submit(verify_theorem, th): th for th in theorem_names}
        done = 0
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
            done += 1
            if done % 10 == 0 or done == len(theorem_names):
                print(f"[reverify_progress] run_id={args.run_id} done={done}/{len(theorem_names)}", flush=True)

    results.sort(key=lambda row: row.theorem_name)
    elapsed_s = time.time() - start

    old_dist = distribution(results, old=True)
    new_dist = distribution(results, old=False)
    old_q = quantized_fraction(results, old=True)
    new_q = quantized_fraction(results, old=False)

    debug_returncodes = Counter()
    debug_failed_batches = 0
    debug_total_batches = 0
    debug_timeout_batches = 0
    if args.debug_errors:
        for row in results:
            for batch in row.batch_reports:
                debug_total_batches += 1
                rc_map = batch.get("returncodes", {})
                for key, val in rc_map.items():
                    debug_returncodes[str(key)] += int(val)
                if batch.get("success_count", 0) < batch.get("batch_size", 0):
                    debug_failed_batches += 1
                if 124 in rc_map or "124" in rc_map:
                    debug_timeout_batches += 1

    output = {
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "run_id": args.run_id,
        "model_label": args.model_label,
        "run_path": str(run_path),
        "dataset_json": str(args.dataset_json),
        "mini_f2f_root": str(args.mini_f2f_root.resolve()),
        "lean_workers": args.lean_workers,
        "lean_jobs": args.lean_jobs,
        "lean_procs": args.lean_procs,
        "lean_batch_size": args.lean_batch_size,
        "launch_gap_ms": int(verifier.launch_gap_s * 1000),
        "direct_lean": verifier._lean_env is not None,
        "prune_aesop_import": verifier.prune_aesop_import,
        "keep_tmp": verifier.keep_tmp,
        "timeout_s": args.timeout_s,
        "elapsed_s": round(elapsed_s, 2),
        "theorem_count": len(results),
        "old_distribution": old_dist,
        "new_distribution": new_dist,
        "old_quantized_fraction": old_q,
        "new_quantized_fraction": new_q,
        "debug_errors": args.debug_errors,
        "debug_summary": {
            "total_batches": debug_total_batches,
            "failed_batches": debug_failed_batches,
            "timeout_batches": debug_timeout_batches,
            "returncode_totals": dict(sorted(debug_returncodes.items())),
        }
        if args.debug_errors
        else {},
        "results": [
            {
                "theorem_name": row.theorem_name,
                "sample_count": row.sample_count,
                "old_verdict_count": row.old_verdict_count,
                "old_pass": row.old_pass,
                "new_pass": row.new_pass,
                "batch_reports": row.batch_reports if args.debug_errors else [],
            }
            for row in results
        ],
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2), encoding="utf-8")

    md_lines = [
        f"# Re-evaluation Summary: {args.run_id}",
        "",
        f"- Model: `{args.model_label}`",
        f"- Run path: `{run_path}`",
        f"- Elapsed seconds: `{round(elapsed_s, 2)}`",
        f"- Theorems re-evaluated: `{len(results)}`",
        f"- Lean workers: `{args.lean_workers}`",
        f"- Lean jobs per process: `{args.lean_jobs}`",
        f"- Max Lean subprocesses: `{args.lean_procs}`",
        f"- Lean batch size: `{args.lean_batch_size}`",
        f"- Lean launch gap ms: `{int(verifier.launch_gap_s * 1000)}`",
        f"- Use direct `lean` command (resolved via `lake env printenv`): `{verifier._lean_env is not None}`",
        f"- Prune `import Aesop` when unused: `{verifier.prune_aesop_import}`",
        f"- Keep verifier temp files: `{verifier.keep_tmp}`",
        "",
        "## Old Distribution",
    ]
    for key, count in old_dist.items():
        md_lines.append(f"- `{key}`: `{count}`")
    md_lines.extend(["", "## New Distribution"])
    for key, count in new_dist.items():
        md_lines.append(f"- `{key}`: `{count}`")
    md_lines.extend(
        [
            "",
            "## Quantized Fraction",
            f"- Old: `{old_q}`",
            f"- New: `{new_q}`",
        ]
    )
    if args.debug_errors:
        md_lines.extend(
            [
                "",
                "## Debug Summary",
                f"- Total batches: `{debug_total_batches}`",
                f"- Failed batches: `{debug_failed_batches}`",
                f"- Timeout batches: `{debug_timeout_batches}`",
                f"- Return codes: `{dict(sorted(debug_returncodes.items()))}`",
            ]
        )
    md_lines.extend(
        [
            "",
            f"- JSON output: `{args.output_json}`",
        ]
    )

    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(
        f"[reverify_done] run_id={args.run_id} elapsed_s={elapsed_s:.1f} "
        f"output_json={args.output_json} output_md={args.output_md}",
        flush=True,
    )


if __name__ == "__main__":
    main()
