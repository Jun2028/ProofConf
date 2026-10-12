# ProofConf-Style Confidence Analysis

- Unique theorems: `244`
- Attempt rows analyzed: `7808`
- Correct attempts: `5536`
- Wrong attempts: `2272`
- Missing metrics: `0`

## Configuration
- Token confidence method: `paper_topk`
- Token confidence top-k: `20`
- Token confidence require full top-k: `False`
- Token confidence fallback to chosen: `False`
- Confidence window: `size=24`, `stride=6`
- Tail confidence tokens: `256`

## Baseline
- Attempt pass rate: `0.709016` (5536/7808)
- Theorem solved rate: `0.840164`

## Global Correlation
- `avg_logprob`: point_biserial=`0.027942`, AUC=`0.522944`
- `lowest_group_confidence`: point_biserial=`0.337890`, AUC=`0.723530`
- `bottom10_group_confidence`: point_biserial=`0.070259`, AUC=`0.545052`
- `tail_confidence`: point_biserial=`-0.189766`, AUC=`0.383541`

## Within-Theorem AUC
- `avg_logprob`: mean_per_theorem_auc=`0.478904`, below_0.5=`70/126`
- `lowest_group_confidence`: mean_per_theorem_auc=`0.515053`, below_0.5=`54/126`
- `bottom10_group_confidence`: mean_per_theorem_auc=`0.466547`, below_0.5=`76/126`
- `tail_confidence`: mean_per_theorem_auc=`0.487626`, below_0.5=`56/126`

## Filtering (Top-k% by confidence within theorem)
- `avg_logprob`:
  - baseline attempt/theorem: `0.709016` / `0.840164`
  - top 10%: attempts=`976`, attempt_success=`0.680328`, theorem_solved=`0.786885`
  - top 25%: attempts=`1952`, attempt_success=`0.694672`, theorem_solved=`0.815574`
  - top 50%: attempts=`3904`, attempt_success=`0.706967`, theorem_solved=`0.831967`
- `lowest_group_confidence`:
  - baseline attempt/theorem: `0.709016` / `0.840164`
  - top 10%: attempts=`976`, attempt_success=`0.713115`, theorem_solved=`0.811475`
  - top 25%: attempts=`1952`, attempt_success=`0.710041`, theorem_solved=`0.827869`
  - top 50%: attempts=`3904`, attempt_success=`0.712602`, theorem_solved=`0.840164`
- `bottom10_group_confidence`:
  - baseline attempt/theorem: `0.709016` / `0.840164`
  - top 10%: attempts=`976`, attempt_success=`0.685451`, theorem_solved=`0.786885`
  - top 25%: attempts=`1952`, attempt_success=`0.697234`, theorem_solved=`0.815574`
  - top 50%: attempts=`3904`, attempt_success=`0.704150`, theorem_solved=`0.836066`
- `tail_confidence`:
  - baseline attempt/theorem: `0.709016` / `0.840164`
  - top 10%: attempts=`976`, attempt_success=`0.695697`, theorem_solved=`0.799180`
  - top 25%: attempts=`1952`, attempt_success=`0.708504`, theorem_solved=`0.815574`
  - top 50%: attempts=`3904`, attempt_success=`0.709529`, theorem_solved=`0.840164`
