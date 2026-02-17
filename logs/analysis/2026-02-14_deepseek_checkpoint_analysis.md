> [INVALIDATED on 2026-02-15]
> This report contains conclusions from verdicts affected by the batched Lean verifier path-resolution bug.
> Use `logs/analysis/2026-02-15_batch_verifier_diagnosis.md` and `logs/analysis/2026-02-15_three_model_run_diagnosis.md` for corrected diagnosis context.

# DeepSeek Checkpoint Analysis (Not Full Run)

## Scope

- Date written: 2026-02-14 (UTC)
- Run analyzed: `runs/2026-02-13_193447Z_deepseek_full`
- Model: `deepseek-chat` only
- Config source: `configs/deepseek_full_test.json`
- Status: this is an **indicative checkpoint** and **not** a full-scale run.

## Collected Data

- Attempts completed: `12`
- Theorems covered: `4` (3 attempts per theorem)
- Files:
  - `runs/2026-02-13_193447Z_deepseek_full/samples.jsonl` (12 rows)
  - `runs/2026-02-13_193447Z_deepseek_full/verdicts.jsonl` (12 rows)
  - `runs/2026-02-13_193447Z_deepseek_full/metrics.jsonl` (12 rows)
  - `runs/2026-02-13_193447Z_deepseek_full/parts.jsonl` (16 rows)
  - `runs/2026-02-13_193447Z_deepseek_full/summary.indicative.json`
  - `runs/2026-02-13_193447Z_deepseek_full/summary.indicative.md`

## Results

- Attempt success rate: `5/12 = 0.417`
- Theorem solved rate (at least one pass): `0.500`

Correlation (point-biserial with pass/fail):
- `lowest_group_confidence`: `+0.145`
- `bottom10_group_confidence`: `+0.145`
- `avg_logprob`: `-0.481`
- `tail_confidence`: `-0.481`

Confidence filtering (within-theorem top-confidence keep):
- Baseline attempt success: `0.417`
- Top 10% keep: `0.500`
- Top 25% keep: `0.500`
- Top 50% keep: `0.500`

## Limitation

- Part-level probes are inconclusive in this checkpoint:
  - recorded part probes: `16`
  - valid parts: `0`
  - dominant issue: probe timeout settings caused return code `124`.

## Conclusion

- The checkpoint suggests a weak positive signal from local confidence metrics (LGC/Bottom10) versus correctness.
- This is **not** sufficient for a final claim; a larger run is required.
