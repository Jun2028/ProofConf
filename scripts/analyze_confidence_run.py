#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

METRICS = [
    "avg_logprob",
    "lowest_group_confidence",
    "bottom10_group_confidence",
    "tail_confidence",
]


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


def auc_score(x_values: List[float], y_binary: List[int]) -> float:
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


def theorem_solved_rate(rows: List[Dict[str, object]]) -> float:
    by_th: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_th[str(row["theorem_name"])].append(row)
    if not by_th:
        return float("nan")
    solved = sum(1 for group in by_th.values() if any(bool(r["lean_success"]) for r in group))
    return solved / len(by_th)


def filtering(rows: List[Dict[str, object]], metric: str, keep_percents: List[int]) -> Dict[str, object]:
    valid = [r for r in rows if not math.isnan(float(r[metric]))]
    by_th: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for row in valid:
        by_th[str(row["theorem_name"])].append(row)
    baseline = sum(1 for r in valid if bool(r["lean_success"])) / len(valid)
    out: Dict[str, object] = {
        "baseline_attempt_success_rate": baseline,
        "baseline_theorem_solved_rate": theorem_solved_rate(valid),
        "top_percent": {},
    }
    for pct in keep_percents:
        kept: List[Dict[str, object]] = []
        for group in by_th.values():
            ordered = sorted(group, key=lambda r: float(r[metric]), reverse=True)
            k = max(1, math.ceil(len(ordered) * (pct / 100.0)))
            kept.extend(ordered[:k])
        out["top_percent"][str(pct)] = {
            "kept_attempts": len(kept),
            "attempt_success_rate": sum(1 for r in kept if bool(r["lean_success"])) / len(kept),
            "theorem_solved_rate": theorem_solved_rate(kept),
        }
    return out


def load_jsonl(path: Path) -> List[Dict[str, object]]:
    out: List[Dict[str, object]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--keep-percents", default="10,25,50")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    output = Path(args.output)
    keep_percents = [int(x) for x in args.keep_percents.split(",") if x.strip()]

    samples = load_jsonl(run_dir / "samples.jsonl")
    metrics = load_jsonl(run_dir / "metrics.jsonl")
    verdicts = load_jsonl(run_dir / "verdicts.jsonl")
    cfg = json.loads((run_dir / "config.resolved.json").read_text(encoding="utf-8"))

    s_by = {str(r["sample_id"]): r for r in samples}
    m_by = {str(r["sample_id"]): r for r in metrics}
    v_by = {str(r["sample_id"]): r for r in verdicts}

    common = sorted(set(s_by) & set(m_by) & set(v_by))
    rows: List[Dict[str, object]] = []
    for sid in common:
        s = s_by[sid]
        m = m_by[sid]
        v = v_by[sid]
        rows.append(
            {
                "sample_id": sid,
                "theorem_name": s["theorem_name"],
                "text": s.get("text", ""),
                "lean_success": bool(v["lean_success"]),
                "error_class": v.get("error_class", ""),
                "token_count": int(m.get("token_count", 0)),
                **{k: float(m.get(k, float("nan"))) for k in METRICS},
            }
        )

    y = [1 if bool(r["lean_success"]) else 0 for r in rows]
    global_corr = {}
    for k in METRICS:
        xs = [float(r[k]) for r in rows]
        global_corr[k] = {"point_biserial": point_biserial(xs, y), "auc": auc_score(xs, y)}

    pass_rows = [r for r in rows if bool(r["lean_success"])]
    fail_rows = [r for r in rows if not bool(r["lean_success"])]

    by_th: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for r in rows:
        by_th[str(r["theorem_name"])].append(r)

    theorem_stats: List[Tuple[str, int, int, float, int]] = []
    for th, group in by_th.items():
        succ = sum(1 for r in group if bool(r["lean_success"]))
        total = len(group)
        uniq_text = len({str(r.get("text", "")) for r in group})
        theorem_stats.append((th, succ, total, succ / total, uniq_text))
    theorem_stats.sort(key=lambda x: x[3])

    by_key: Dict[Tuple[str, str], List[Dict[str, object]]] = defaultdict(list)
    for r in rows:
        by_key[(str(r["theorem_name"]), str(r.get("text", "")))].append(r)
    mixed = []
    for (th, txt), group in by_key.items():
        oks = [bool(r["lean_success"]) for r in group]
        if any(oks) and not all(oks):
            mixed.append((th, len(group), sum(1 for x in oks if x), Counter(str(r["error_class"]) for r in group if not bool(r["lean_success"]))))

    lines: List[str] = []
    lines.append(f"# Corrected Confidence Analysis: {run_dir.name}")
    lines.append("")
    lines.append("## Configuration")
    lines.append(f"- Token confidence method: `{cfg.get('token_confidence_method')}`")
    lines.append(f"- Token confidence top-k: {cfg.get('token_confidence_topk')}")
    lines.append(f"- Token confidence require full top-k: {cfg.get('token_confidence_require_full_topk')}")
    lines.append(f"- Token confidence fallback to chosen: {cfg.get('token_confidence_fallback_to_chosen')}")
    lines.append("")
    lines.append("## Integrity")
    lines.append(f"- Joined rows: {len(common)}")
    lines.append(f"- samples_only: {len(set(s_by) - set(common))}")
    lines.append(f"- metrics_only: {len(set(m_by) - set(common))}")
    lines.append(f"- verdicts_only: {len(set(v_by) - set(common))}")
    lines.append("")
    lines.append("## Baseline")
    baseline = sum(y) / len(y)
    lines.append(f"- Attempt pass rate: {baseline:.6f} ({sum(y)}/{len(y)})")
    lines.append(f"- Theorem solved rate: {theorem_solved_rate(rows):.6f}")
    lines.append("")
    lines.append("## Global Correlation")
    for k in METRICS:
        pb = global_corr[k]["point_biserial"]
        auc = global_corr[k]["auc"]
        lines.append(f"- {k}: point_biserial={pb:.6f}, AUC={auc:.6f}")
    lines.append("")
    lines.append("## Filtering (Top-k% by confidence within theorem)")
    for metric in ["lowest_group_confidence", "bottom10_group_confidence", "tail_confidence"]:
        stats = filtering(rows, metric, keep_percents)
        lines.append(f"- {metric}:")
        lines.append(
            f"  - baseline attempt/theorem: {stats['baseline_attempt_success_rate']:.6f} / {stats['baseline_theorem_solved_rate']:.6f}"
        )
        top = stats["top_percent"]
        for pct in keep_percents:
            row = top[str(pct)]
            lines.append(
                f"  - top {pct}%: attempts={row['kept_attempts']}, attempt_success={row['attempt_success_rate']:.6f}, theorem_solved={row['theorem_solved_rate']:.6f}"
            )
    lines.append("")
    lines.append("## Theorem Pass Rates")
    for th, succ, total, rate, uniq_text in theorem_stats:
        lines.append(f"- {th}: {succ}/{total} ({rate:.6f}), unique_texts={uniq_text}")
    lines.append("")
    lines.append("## Mixed Same-Text Outcomes")
    lines.append(f"- Mixed keys count: {len(mixed)}")
    for th, total, succ, fail_counter in mixed[:10]:
        lines.append(f"- {th}: {succ}/{total} pass, fail_error_classes={dict(fail_counter)}")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
