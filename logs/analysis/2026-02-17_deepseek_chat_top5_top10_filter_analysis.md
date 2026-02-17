# DeepSeek-Chat Full Run: Top-5% / Top-10% Confidence Re-Analysis

> [SUPERSEDED on 2026-02-17]
> This report used the earlier chosen-token confidence proxy.
> For paper-faithful top-k token confidence (`paper_topk`), see:
> `logs/analysis/2026-02-17_deepseek_chat_full_512_paperconf_analysis.md`.

## Scope

- Run ID: `2026-02-17_100002Z_deepseek_chat_full_512_prescreen_0to1`
- Artifacts: `samples.jsonl`, `metrics.jsonl`, `verdicts.jsonl`
- Rows analyzed: `8192`
- Baseline attempt pass rate: `0.375488`

## Clarification

This report interprets your request as **top 5% and top 10% confidence filtering**.

Reason: this run does not persist per-token alternative candidates (`top_logprobs` lists), only chosen-token-derived metrics. So we can recompute filtering/ranking analyses, but we cannot retroactively recompute a separate "API top_logprobs=10 vs 5" trace from this finished artifact.

## Results: Keep Top 5% / 10% per theorem

(keeping highest-confidence attempts within each theorem, then aggregating)

| Confidence metric | Top % kept | Kept attempts | Attempt success rate | Delta vs baseline | Theorem solved rate |
|---|---:|---:|---:|---:|---:|
| `avg_logprob` | 5 | 416 | 0.250000 | -0.125488 | 0.3125 |
| `avg_logprob` | 10 | 832 | 0.258413 | -0.117075 | 0.3125 |
| `lowest_group_confidence` | 5 | 416 | 0.281250 | -0.094238 | 0.3125 |
| `lowest_group_confidence` | 10 | 832 | 0.275240 | -0.100248 | 0.3125 |
| `bottom10_group_confidence` | 5 | 416 | 0.262019 | -0.113469 | 0.3125 |
| `bottom10_group_confidence` | 10 | 832 | 0.266827 | -0.108661 | 0.3125 |
| `tail_confidence` | 5 | 416 | 0.247596 | -0.127892 | 0.3125 |
| `tail_confidence` | 10 | 832 | 0.256010 | -0.119479 | 0.3125 |

## Conclusion

For this full run, using top-confidence slices at 5% or 10% still degrades correctness relative to baseline, consistent with the earlier AUC/point-biserial finding that the current confidence signal is inverted/misaligned for correctness under this setup.

## If you meant API `top_logprobs=10` and `top_logprobs=5`

That requires fresh generation runs (or storing full per-token alternative lists in artifacts). The current run data is insufficient to reconstruct those traces exactly.
