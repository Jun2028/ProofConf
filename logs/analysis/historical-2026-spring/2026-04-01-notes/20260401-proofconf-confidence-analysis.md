# 2026-04-01 ProofConf-Style Confidence Analysis

- Replaced the earlier DeepConf detour with a repo-faithful analysis based on `Jun2028/ProofConf`.
- Repo-faithful settings used:
  - `paper_topk`
  - `top_k = 20`
  - `require_full_topk = false`
  - `fallback_to_chosen = false`
  - `window_size = 24`
  - `stride = 6`
  - `tail_tokens = 256`
  - higher confidence = higher score
- Source corpus:
  - completed `244`-theorem top-20 run from:
    - `20260328-top20-rs16`
    - `20260329-top20-rs16-resume35`
- Output root:
  - `SOURCE_ARTIFACTS/analysis/proofconf-confidence-20260401`

## Result

- Unique theorems: `244`
- Attempt rows analyzed: `2176`
- Correct attempts: `192`
- Wrong attempts: `1984`
- Missing metrics: `0`

Baseline:
- attempt pass rate: `192 / 2176 = 0.088235`
- theorem solved rate: `192 / 244 = 0.786885`

Global correlation:
- `avg_logprob`: point_biserial=`-0.002587`, AUC=`0.489384`
- `lowest_group_confidence`: point_biserial=`0.218359`, AUC=`0.703403`
- `bottom10_group_confidence`: point_biserial=`0.006441`, AUC=`0.504439`
- `tail_confidence`: point_biserial=`-0.150032`, AUC=`0.365141`

Top-confidence filtering within theorem:
- `lowest_group_confidence`
  - top `10%`: attempt_success=`0.381862`, theorem_solved=`0.655738`
  - top `25%`: attempt_success=`0.246637`, theorem_solved=`0.676230`
  - top `50%`: attempt_success=`0.143959`, theorem_solved=`0.688525`
- `bottom10_group_confidence`
  - top `10%`: attempt_success=`0.379475`, theorem_solved=`0.651639`
- `tail_confidence`
  - top `10%`: attempt_success=`0.381862`, theorem_solved=`0.655738`

Interpretation:
- Under the `ProofConf` metric family, `lowest_group_confidence` is the strongest proof-level discriminator on this corpus.
- It improves attempt precision strongly when keeping only the top-confidence attempts within each theorem.
- But theorem solved rate drops relative to the full `pass@32` pool, which is expected when discarding attempts.

Main artifacts:
- `SOURCE_ARTIFACTS/analysis/proofconf-confidence-20260401/summary.json`
- `SOURCE_ARTIFACTS/analysis/proofconf-confidence-20260401/summary.md`
- `SOURCE_ARTIFACTS/analysis/proofconf-confidence-20260401/trace_metrics.csv`
