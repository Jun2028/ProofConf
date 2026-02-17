# DeepSeek-Only Confidence Scaling Test Plan

## Goal

Test whether confidence signals from `deepseek-chat` correlate with:
1. Whole-proof Lean correctness (pass/fail).
2. Intermediate proof-part validity (prefix probes).

This design drops Gemini entirely and uses `max_tokens=8000`.
The currently completed execution is an indicative checkpoint, not the full planned budget.

## References Used

- Confidence metrics design: `docs/2508.15260v1.pdf` (DeepConf)
  - Lowest Group Confidence (LGC)
  - Bottom-10% Group Confidence
  - Tail Confidence
  - Confidence filtering by top-eta% traces
- Dataset and benchmark context: `docs/2109.00110v2.pdf` (miniF2F)
- Difficulty grading and moderate-difficulty selection: `docs/2502.00855v1.pdf` + `docs/miniF2F-Graded.json`
- Project constraints:
  - `set-up.md`
  - `docs/dataset.md`
  - `docs/api-instructions.md`
  - `docs/api/log-prob-behaviour.md`

## Test Configuration

Config file: `configs/deepseek_full_test.json`

- Provider/model: `deepseek/deepseek-chat`
- Split: `valid`
- Difficulty levels: `Level 2`, `Level 3` (moderate region)
- Theorems: `12`
- Samples per theorem: `3`
- Total attempts: `36`
- `max_tokens`: `8000`
- `top_logprobs`: `20`
- Confidence windows: `window=24`, `stride=6`
- Tail confidence window: `last 256 tokens`
- Prefix probe timeout: `10s` per probe

## Evaluation Design

### A) Whole-Proof Correlation

Per attempt:
- Generate proof body
- Verify with Lean
- Compute confidence metrics: `avg_logprob`, `LGC`, `Bottom10`, `Tail`

Aggregate per model:
- Pass rate and theorem-solved rate
- Point-biserial correlation between each confidence metric and Lean success

### B) Confidence Filtering (DeepConf-style offline proxy)

Within each theorem’s attempts:
- Rank attempts by confidence score
- Keep top `eta%` where `eta in {10, 25, 50}`
- Report retained attempt success rate and retained theorem solved rate

Purpose:
- Check if high-confidence traces are enriched for correct proofs.

### C) Proof-Part Correlation (Prefix Probes)

For each generated proof:
- Take proof prefixes at quantiles `33%`, `66%` (line-based, with word-based fallback for one-line proofs)
- Append `admit` and run Lean check (tests whether prefix remains coherent up to that point)
- Compute per-part confidence and prefix confidence

Aggregate:
- Part valid rate
- Point-biserial correlation of `part_confidence` and `prefix_lgc` with part validity

## Expected Artifacts

- `runs/<run_id>/samples.jsonl`
- `runs/<run_id>/verdicts.jsonl`
- `runs/<run_id>/metrics.jsonl`
- `runs/<run_id>/parts.jsonl` (new; proof-part probes)
- `runs/<run_id>/summary.json`
- `runs/<run_id>/summary.md`
- `logs/run/<run_id>/driver.log`

## Indicative Result Criteria

Treat the run as indicative if:
1. There is a mix of pass/fail samples (not all one class).
2. At least one confidence metric shows non-trivial positive correlation with success.
3. Confidence filtering improves success density in retained traces vs baseline.
4. Part-level metrics show directional separation between valid vs invalid prefixes.
