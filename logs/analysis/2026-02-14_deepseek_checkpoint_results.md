> [INVALIDATED on 2026-02-15]
> This report contains conclusions from verdicts affected by the batched Lean verifier path-resolution bug.
> Use `logs/analysis/2026-02-15_batch_verifier_diagnosis.md` and `logs/analysis/2026-02-15_three_model_run_diagnosis.md` for corrected diagnosis context.

# DeepSeek-Only Indicative Results

## Run Metadata

- Date (UTC): 2026-02-13
- Run ID: `2026-02-13_193447Z_deepseek_full`
- Config: `configs/deepseek_full_test.json`
- Model: `deepseek-chat` only
- Max output tokens: `8000`
- Notes:
  - This run was intentionally stopped at an indicative checkpoint after 12 completed attempts (instead of full planned budget) to obtain a faster intermediate read.
  - Summary artifact for this checkpoint: `runs/2026-02-13_193447Z_deepseek_full/summary.indicative.json`

## Data Collected (checkpoint)

- `samples.jsonl`: 12
- `verdicts.jsonl`: 12
- `metrics.jsonl`: 12
- `parts.jsonl`: 16

## Core Outcome

- Attempt pass rate: `5 / 12 = 0.417`
- Theorem solved rate (any attempt passes): `0.500`

This already confirms mixed pass/fail behavior (unlike tiny 6-attempt runs), so confidence-vs-correctness can be tested.

## Confidence vs Whole-Proof Correctness

From `summary.indicative.json`:

- Point-biserial correlation with `lean_success`
  - `lowest_group_confidence`: `+0.145`
  - `bottom10_group_confidence`: `+0.145`
  - `avg_logprob`: `-0.481`
  - `tail_confidence`: `-0.481`

Interpretation:
- Local low-confidence-aware metrics (LGC / Bottom10) are directionally aligned with correctness in this checkpoint.
- Global average/tail confidence are currently unstable (negative sign here), likely due small `n` and clustered short proofs.

## Confidence Filtering Check (DeepConf-style proxy)

Baseline attempt success rate: `0.417`

Ranking attempts within each theorem by confidence and keeping top traces gives:
- Top 10% kept: attempt success `0.500`
- Top 25% kept: attempt success `0.500`
- Top 50% kept: attempt success `0.500`

Indicative conclusion:
- Confidence filtering increased success density from `0.417` to `0.500` in this run.

## Proof-Part Result (Current Limitation)

- Part probes recorded: 16
- Part-valid count: 0
- Immediate cause: all probes returned timeout code `124` under the 10s probe timeout.

Implication:
- Part-level correlation is **inconclusive** for this checkpoint.
- Whole-proof correlation signal exists; part-level needs a longer-timeout or lighter-weight part-check method.

## Practical Conclusion So Far

1. DeepSeek-only pipeline with `max_tokens=8000` works and produces mixed pass/fail outcomes.
2. Confidence has an **indicative positive relationship** with correctness when using local low-confidence metrics (LGC/Bottom10).
3. Confidence filtering improves retained-attempt success rate in this checkpoint.
4. Part-level validity testing needs refinement (timeouts currently dominate).
