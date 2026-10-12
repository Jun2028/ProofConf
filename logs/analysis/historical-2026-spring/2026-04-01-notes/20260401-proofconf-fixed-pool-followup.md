## 2026-04-01 ProofConf Fixed-Pool Follow-up

- Goal: find an actually fairer fixed-pool corpus for `ProofConf`, instead of the adaptive early-stop `244`-theorem run.

### What I checked

- Old fixed-32 subset:
  - `SOURCE_ARTIFACTS/runs/minif2f-pass32-408057.hopper-m-02`
  - good: all `18` theorems have `samples_generated = 32`
  - bad:
    - only `104 / 576` verification records were written into `results.jsonl`
    - raw payloads do **not** contain token logprobs
    - therefore `ProofConf` confidence metrics are undefined (`NaN`) on this subset

- Later unsolved fixed-pool rerun:
  - `SOURCE_ARTIFACTS/runs/minif2f-pass32-20260331-unsolved52-40960-r3-shard*/`
  - good: all `52` theorems have `samples_generated = 32`
  - bad:
    - raw payloads also do **not** contain token logprobs
    - so this rerun is also unusable for `ProofConf`

### Best existing fair-ish artifact with logprobs

- In the top-20 logprob run, there are `53` theorems that happened to reach the full `32` attempts before stopping.
- Among those, exactly one theorem has a mixed correct/wrong pool:
  - `mathd_algebra_289`
  - `32` attempts total
  - `1` correct
  - `31` wrong

### Theorem-level ProofConf result

- Output root:
  - `SOURCE_ARTIFACTS/analysis/proofconf-confidence-20260401-mathd_algebra_289`
- Main artifacts:
  - `summary.json`
  - `summary.md`
  - `trace_metrics.csv`
- `ProofConf` configuration:
  - `paper_topk`
  - `top_k = 20`
  - `window_size = 24`
  - `stride = 6`
  - `tail_tokens = 256`

### Result on `mathd_algebra_289`

- `avg_logprob`: AUC `0.677419`
- `lowest_group_confidence`: AUC `0.870968`
- `bottom10_group_confidence`: AUC `0.838710`
- `tail_confidence`: AUC `0.580645`

- Ranking detail:
  - the single correct proof is candidate `31`
  - by `lowest_group_confidence`, that correct proof is inside the top `25%` confidence slice
  - by `avg_logprob` and `tail_confidence`, it is weaker

### Conclusion

- There is no currently stored corpus in this repo that is simultaneously:
  - fixed-pool,
  - fully verified,
  - and equipped with token logprobs
- The cleanest existing theorem-level fixed-budget evidence is `mathd_algebra_289`, and on that theorem `ProofConf` behaves sensibly, with `lowest_group_confidence` strongest.
