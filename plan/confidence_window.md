# Confidence Window Choice

We use token-window confidence as the canonical metric, plus tactic-aware localization as an annotation layer.

Current default:
- window size `W = 24`
- stride `S = 6`

Rationale:
- small enough to localize weak segments,
- large enough to smooth single-token noise,
- stride overlap preserves local minima.
- tactic parsing can fail on real Lean formatting, so confidence scoring itself must not depend on segmentation quality.

## Execution Behavior (Current)

- Token-window confidence is always computed when token logprobs are available.
- Tactic-aware localization is always attempted as an annotation pass.
- If tactic segmentation is unreliable, the system falls back to line/excerpt localization automatically.
- Both canonical metrics and annotation outputs are recorded in `metrics.jsonl`.
- There is currently no separate config knob to disable only the tactic-aware annotation path.

## Metric (Canonical)

```text
input: token_logprobs L[0..n-1], window_size W, stride S

if n == 0:
  return NaN metrics

if n <= W:
  windows = [mean(L)]
else:
  windows = []
  i = 0
  while i + W <= n:
    windows.append(mean(L[i:i+W]))
    i += S
  if (n - W) mod S != 0:
    windows.append(mean(L[n-W:n]))

LGC = min(windows)
Bottom10 = mean(lowest max(1, floor(0.1 * len(windows))) windows)
AvgLogprob = mean(L)
```

## Tactic-Aware Annotation (Derived, Optional)

After computing token windows:

```text
1) Find weakest window index j* = argmin_j window_mean_j
2) Map token span of j* back to generated proof text (line range + excerpt)
3) Try tactic-like segmentation:
   - split on top-level newline / ';'
   - ignore separators inside comments, strings, (), [], {}
   - skip structure-only units ('by', '·', '|', 'case ...')
4) If segmentation succeeds, report overlapping tactic index range.
5) If segmentation fails, keep line/excerpt localization only.
```

Output includes:
- `weakest_window_start_token`, `weakest_window_end_token`
- `weakest_window_start_line`, `weakest_window_end_line`
- `weakest_context_start_line`, `weakest_context_end_line`
- `weakest_excerpt`
- `tactic_segmentation_used`
- `weakest_tactic_index_start`, `weakest_tactic_index_end`
