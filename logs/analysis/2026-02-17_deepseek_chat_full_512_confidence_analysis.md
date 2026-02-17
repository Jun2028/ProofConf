# DeepSeek-Chat Full Run (512) Confidence Analysis

> [SUPERSEDED on 2026-02-17]
> This report used the earlier chosen-token confidence proxy.
> For paper-faithful top-k token confidence (`paper_topk`), see:
> `logs/analysis/2026-02-17_deepseek_chat_full_512_paperconf_analysis.md`.

## Scope

- Run ID: `2026-02-17_100002Z_deepseek_chat_full_512_prescreen_0to1`
- Run dir: `/scratch/USER/data/proofconf/output/runs/2026-02-17_100002Z_deepseek_chat_full_512_prescreen_0to1`
- Model: `deepseek::deepseek-chat`
- Config intent: confidence-vs-correctness analysis on prescreened theorems (`0 < pass_rate < 1`), `512` samples/theorem, `max_tokens=8000`, logprobs enabled.

## Data Integrity Checks

Recomputed directly from raw artifacts (`samples.jsonl`, `metrics.jsonl`, `verdicts.jsonl`):

- Joined rows (same `sample_id` in all three files): `8192`
- `samples_only`: `0`
- `metrics_only`: `0`
- `verdicts_only`: `0`
- Per-theorem samples: all `16` theorems have exactly `512` rows
- Logprob coverage: `token_count <= 0` rows = `0` (also confirmed by `meta/logprobs_validation.json`)

## Intended Confidence Analysis (Whole-Proof)

Baseline:

- Attempt pass rate: `3076 / 8192 = 0.3755`
- Theorem solved rate (any pass among 512): `16 / 16 = 1.0000`

### A) Confidence vs Pass/Fail Correlation

Higher confidence means less-negative logprob values.

| Metric | Point-biserial r (vs `lean_success`) | AUC (pass ranked above fail) |
|---|---:|---:|
| `avg_logprob` | `-0.3300` | `0.3091` |
| `lowest_group_confidence` | `-0.2301` | `0.4550` |
| `bottom10_group_confidence` | `-0.2404` | `0.4483` |
| `tail_confidence` | `-0.3304` | `0.3097` |

Interpretation:

- All four metrics are negatively associated with correctness on this run.
- Ranking quality is below random (`AUC < 0.5`) for all metrics.

Within-theorem direction check (computed separately per theorem, then averaged over 16 theorems):

- Mean per-theorem AUC:
  - `avg_logprob`: `0.2787` (13/16 theorems below 0.5)
  - `lowest_group_confidence`: `0.3433` (10/16 below 0.5)
  - `bottom10_group_confidence`: `0.3351` (9/16 below 0.5)
  - `tail_confidence`: `0.2792` (13/16 below 0.5)

This shows the negative direction is not only a cross-theorem aggregation artifact.

### B) Confidence Filtering (Top-eta% Per Theorem)

From `summary.json` (same as recomputation logic):

- Baseline attempt success: `0.3755`

`lowest_group_confidence`:
- Top 10%: `0.2752` (delta `-0.1002`)
- Top 25%: `0.2734` (delta `-0.1021`)
- Top 50%: `0.3357` (delta `-0.0398`)

`bottom10_group_confidence`:
- Top 10%: `0.2668` (delta `-0.1087`)
- Top 25%: `0.2646` (delta `-0.1108`)
- Top 50%: `0.3333` (delta `-0.0422`)

`tail_confidence`:
- Top 10%: `0.2560` (delta `-0.1195`)
- Top 25%: `0.2393` (delta `-0.1362`)
- Top 50%: `0.3013` (delta `-0.0742`)

Interpretation:

- Confidence-based top-k selection decreases success rate instead of enriching correct proofs.

## Theorem-Level Behavior

Per-theorem pass rates are non-quantized and span a wide range (not only 0/0.5/1):

- Min: `0.0293` (`amc12a_2021_p7`)
- Max: `0.9473` (`mathd_numbertheory_102`)
- Mid examples: `0.2031`, `0.3066`, `0.4531`, `0.5801`

So this run has meaningful pass/fail variation at theorem level, suitable for correlation testing.

## Important Caveat

A targeted consistency check found a small number of same-text mixed outcomes:

- Mixed pass/fail `(theorem_name, exact text)` keys: `12 / 1042`
- All are on theorem `aime_1996_p5`
- Fail labels on these mixed keys are `unsolved_goals`

This is much smaller than earlier broken artifacts, but it is still a non-zero anomaly and should be tracked in future reruns.

## Conclusion

For this DeepSeek-chat full run (`16` theorems x `512` attempts), the intended confidence analysis is clear:

1. Confidence metrics are negatively correlated with Lean correctness.
2. Confidence filtering by top-scored attempts hurts, not helps, pass rate.
3. The dataset does have substantial non-trivial pass/fail variation, so this is not a trivial all-pass/all-fail artifact.

Net: under this setup, current confidence scores are not predictive in the intended direction for proof correctness.
