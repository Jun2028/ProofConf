> [INVALIDATED on 2026-02-15]
> This report contains conclusions from verdicts affected by the batched Lean verifier path-resolution bug.
> Use `logs/analysis/2026-02-15_batch_verifier_diagnosis.md` and `logs/analysis/2026-02-15_three_model_run_diagnosis.md` for corrected diagnosis context.

# DeepSeek Prescreen Final Evaluation (`temperature=0.7`)

## Run

- Run ID: `2026-02-14_174421Z_deepseek_prescreen_l1_l3_32`
- Run path: `/scratch/USER/data/proofconf/output/runs/2026-02-14_174421Z_deepseek_prescreen_l1_l3_32`
- Driver log: `/scratch/USER/data/proofconf/output/logs/run/2026-02-14_174421Z_deepseek_prescreen_l1_l3_32/driver.log`
- Status: completed (`run_end` logged)

## Coverage

- Target attempts: `195 * 32 = 6240`
- Completed attempts: `6239` (one generation failure)
- Missing theorem-attempt:
  - `amc12a_2017_p2` had `31` attempts

## Core Outcomes

- Attempt success count: `368`
- Attempt success rate: `0.05898`
- Theorem solved rate (>=1 pass): `0.06154` (`12/195`)

Theorem-level distribution:
- `183` theorems at `0` passes
- `11` theorems at `32/32`
- `1` theorem at `16/32`

Solved theorem list:
- `algebra_2rootsintpoly_am10tap11eqasqpam110` (`32/32`)
- `algebra_2rootspoly_apatapbeq2asqp2ab` (`32/32`)
- `algebra_3rootspoly_amdtamctambeqnasqmbpctapcbtdpasqmbpctapcbta` (`32/32`)
- `algebra_manipexpr_2erprsqpesqeqnrpnesq` (`32/32`)
- `algebra_sqineq_4bap1lt4bsqpap1sq` (`32/32`)
- `mathd_algebra_182` (`32/32`)
- `mathd_algebra_190` (`32/32`)
- `mathd_algebra_462` (`32/32`)
- `mathd_algebra_568` (`32/32`)
- `mathd_numbertheory_101` (`32/32`)
- `mathd_numbertheory_81` (`32/32`)
- `mathd_numbertheory_102` (`16/32`)

## Screening Gate Result

Gate criterion from `plan/theorem_prescreening.md`: keep theorem iff `0.10 <= solve_rate <= 0.80`.

- Qualified theorems: `1`
- Qualified theorem: `mathd_numbertheory_102` (`16/32 = 0.5`)
- Decision against Go/No-Go gate (`>=10` needed): **No-Go**

## Confidence Metrics Snapshot

From `summary.json`:
- `point_biserial(avg_logprob) = -0.3593`
- `point_biserial(lowest_group_confidence) = -0.1557`
- `point_biserial(bottom10_group_confidence) = -0.2169`
- `point_biserial(tail_confidence) = -0.3619`

Top-confidence filtering (`10/25/50%`) gave only marginal attempt-rate change (~`0.0615` vs baseline `0.0590`).

## Practical Conclusion

- Raising temperature to `0.7` did not improve prescreen usefulness for this model/dataset.
- The run remains highly bimodal (mostly unsolved or always solved one-line style).
- Current setup still fails the theorem-count gate needed for a robust 512-attempt confidence-correlation study.
