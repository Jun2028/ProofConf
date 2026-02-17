> [INVALIDATED on 2026-02-15]
> This report contains conclusions from verdicts affected by the batched Lean verifier path-resolution bug.
> Use `logs/analysis/2026-02-15_batch_verifier_diagnosis.md` and `logs/analysis/2026-02-15_three_model_run_diagnosis.md` for corrected diagnosis context.

# DeepSeek Prescreen Analysis (L1-L3, 32 Attempts)

## Run

- Run ID: `2026-02-14_131222Z_deepseek_prescreen_l1_l3_32`
- Artifacts: `/scratch/USER/data/proofconf/output/runs/2026-02-14_131222Z_deepseek_prescreen_l1_l3_32`
- Driver log: `/scratch/USER/data/proofconf/output/logs/run/2026-02-14_131222Z_deepseek_prescreen_l1_l3_32/driver.log`

## Scope

- Dataset: `docs/miniF2F-Graded.json`
- Split: `valid`
- Difficulty: `Level 1`, `Level 2`, `Level 3`
- Target budget: `195 * 32 = 6240` attempts

## Results

- Completed attempts: `6238` (2 generation failures)
- Attempt pass count: `464`
- Attempt pass rate: `0.0744`
- Theorems with at least one pass: `15 / 195 = 0.0769`

Per-theorem distribution:
- `180` theorems at `0/32`
- `14` theorems at `32/32`
- `1` theorem at partial success (`16/32`)
- `2` theorems at `0/31` (missing one attempt each due generation failure)

Missing-attempt theorems:
- `mathd_algebra_13` (`31` attempts)
- `mathd_algebra_77` (`31` attempts)

## Screening Gate Outcome

Gate from `plan/theorem_prescreening.md`:
- keep theorem iff `0.10 <= solve_rate <= 0.80`

Qualified theorems:
- `mathd_numbertheory_132` with `16/32 = 0.500`

Qualified count: `1`

Go/No-Go check:
- Required to proceed: at least `10` qualified theorems
- Actual: `1`
- Decision: **No-Go** for the 512-attempt full correlation run with current setup.

## Confidence Signal Snapshot

From `summary.json`:
- Point-biserial:
  - `lowest_group_confidence`: `+0.0125` (near zero)
  - `bottom10_group_confidence`: `-0.0576` (weak negative)
  - `avg_logprob`: `-0.2592`
  - `tail_confidence`: `-0.2624`
- Confidence top-percent filtering did not improve pass rates materially.

Interpretation:
- For this screened pool, confidence metrics are not yet separating pass/fail in a useful way.
- Data are strongly bimodal (mostly always-fail or always-pass), which limits correlation usefulness.

