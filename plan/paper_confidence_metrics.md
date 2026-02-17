# Paper-Faithful Confidence Metrics Plan

## Goal

Align confidence computation with DeepConf (`docs/2508.15260v1.pdf`) rather than chosen-token-only proxy scoring.

## Definitions (DeepConf-aligned)

Let token position be `t` and top-k candidate token logprobs at that position be `log P_t(j)`.

1. Token confidence (`C_t`)

```text
C_t = - (1/k) * sum_{j=1..k} log P_t(j)
```

2. Average trace confidence (`C_avg`)

```text
C_avg = mean_t(C_t)
```

3. Group confidence (windowed)

For window size `W` and stride `S`, compute window means over `C_t`.

4. Lowest Group Confidence (LGC)

```text
LGC = min(window_means)
```

5. Bottom-10% Group Confidence

```text
Bottom10 = mean(lowest 10% of window_means)
```

6. Tail Confidence

```text
Tail = mean(last T token confidences)
```

## Implementation Mapping

Implemented in `src/proofconf/metrics/token_confidence.py`:

- `paper_token_confidence_at_t(...)`
- `token_confidence_series(...)`
- `average_trace_confidence(...)`
- `group_confidence_scores(...)`
- `lowest_group_confidence(...)`
- `bottom_percent_group_confidence(...)`
- `tail_confidence_score(...)`
- `confidence_metrics(...)` (aggregate wrapper used by pipeline)

Pipeline wiring in `src/proofconf/pipeline/run_experiment.py`:

- API token candidates are parsed by client layer.
- Token confidence series is built via `token_confidence_series(...)`.
- Aggregate metrics (LGC/Bottom10/Tail) are computed from that series.

## Knobs

Added run-config knobs:

- `token_confidence_method`: `"paper_topk" | "chosen_logprob"`
- `token_confidence_topk`: integer `k` (default `20`)
- `token_confidence_require_full_topk`: bool
- `token_confidence_fallback_to_chosen`: bool

Recommended faithful setting:

```json
{
  "token_confidence_method": "paper_topk",
  "token_confidence_topk": 20,
  "token_confidence_require_full_topk": false,
  "token_confidence_fallback_to_chosen": false
}
```

## Notes

- `chosen_logprob` mode is kept only as a legacy baseline.
- Summary field names in artifacts remain backward-compatible; when `paper_topk` is enabled, the `avg_logprob` slot corresponds to `C_avg` (average token confidence).
