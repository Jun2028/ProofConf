#!/usr/bin/env python3
"""Check archived April/May AUC tables from saved scores; no model or Lean calls."""

import csv
import gzip
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from analyze_confidence_run import auc_score, filtering, point_biserial


def same(actual, expected):
    if isinstance(expected, dict):
        assert actual.keys() == expected.keys()
        for key in expected:
            same(actual[key], expected[key])
    else:
        assert math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-10), (actual, expected)


def main():
    if not __debug__:
        raise SystemExit("Run without -O so validation assertions remain enabled.")
    root = Path(__file__).resolve().parents[1] / "logs/analysis/historical-2026-spring"
    provenance = json.loads((root / "provenance.json").read_text())
    for filename, entry in provenance["artifacts"].items():
        assert hashlib.sha256((root / filename).read_bytes()).hexdigest() == entry["sha256"], filename
    for dataset in provenance["datasets"]:
        directory = root / dataset["directory"]
        summary = json.loads((directory / "summary.json").read_text())
        with gzip.open(directory / "attempt_metrics.csv.gz", "rt", newline="") as handle:
            rows = list(csv.DictReader(handle))
        groups = defaultdict(list)
        for row in rows:
            assert row["lean_success"] in {"True", "False"}
            row["lean_success"] = row["lean_success"] == "True"
            for metric in dataset["metric_columns"]:
                row[metric] = float(row[metric])
                assert math.isfinite(row[metric])
            groups[row["theorem_name"]].append(row)
        assert len(rows) == dataset["rows"] == summary["attempt_rows_analyzed"]
        assert len({(r["theorem_name"], r["candidate_index"]) for r in rows}) == len(rows)
        assert len(groups) == summary["unique_theorems"]
        assert Counter(r["generator"] for r in rows) == dataset["generator_counts"]
        assert Counter(r["generator"] for r in rows if r["lean_success"]) == dataset["generator_pass_counts"]
        labels = [int(r["lean_success"]) for r in rows]
        assert sum(labels) == summary["correct_attempts"]
        assert len(rows) - sum(labels) == summary["wrong_attempts"]
        if "fixed_attempts_per_theorem" in dataset:
            assert all(len(g) == dataset["fixed_attempts_per_theorem"] for g in groups.values())
        if "status_counts" in summary:
            assert Counter(r["status"] for r in rows) == summary["status_counts"]
        for metric in dataset["metric_columns"]:
            values = [r[metric] for r in rows]
            same({"auc": auc_score(values, labels), "point_biserial": point_biserial(values, labels)},
                 summary["global_correlation"][metric])
            aucs = [auc_score([r[metric] for r in g], [int(r["lean_success"]) for r in g])
                    for g in groups.values()]
            aucs = [a for a in aucs if math.isfinite(a)]
            same({"valid_theorems": len(aucs), "mean_per_theorem_auc": sum(aucs) / len(aucs),
                  "theorems_below_0_5": sum(a < 0.5 for a in aucs)},
                 summary["within_theorem_auc"][metric])
            same(filtering(rows, metric, summary["keep_percents"]), summary["confidence_filtering"][metric])
        print(json.dumps({"dataset": dataset["directory"], "rows": len(rows),
                          "metrics_checked": len(dataset["metric_columns"]), "status": "matches"}))


if __name__ == "__main__":
    main()
