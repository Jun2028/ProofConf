> [INVALIDATED on 2026-02-15]
> This report contains conclusions from verdicts affected by the batched Lean verifier path-resolution bug.
> Use `logs/analysis/2026-02-15_batch_verifier_diagnosis.md` and `logs/analysis/2026-02-15_three_model_run_diagnosis.md` for corrected diagnosis context.

# DeepSeek Prescreen Rerun Checkpoint (`temperature=0.7`)

## Config Change

- Updated config default temperature from `0.2` to `0.7` in:
  - `configs/deepseek_prescreen_l1_l3_32.json`
  - `configs/deepseek_scale_512.json`
  - `configs/deepseek_full_test.json`
  - `configs/deepseek_canary_batch.json`
  - `configs/initial_run.json`

## Active Rerun

- Job ID: `568615.stdct-mgmt-02`
- Run ID: `2026-02-14_174421Z_deepseek_prescreen_l1_l3_32`
- Run path: `/scratch/USER/data/proofconf/output/runs/2026-02-14_174421Z_deepseek_prescreen_l1_l3_32`
- Log path: `/scratch/USER/data/proofconf/output/logs/run/2026-02-14_174421Z_deepseek_prescreen_l1_l3_32/driver.log`

## 512-Verdict Checkpoint

- Attempts processed: `512`
- Passes: `80`
- Attempt pass rate: `0.15625`
- Theorems touched: `16`
- Theorems with >=1 pass: `3`
- Per-theorem buckets among these 16:
  - `2` at `32/32`
  - `1` at mixed (`16/32`)
  - `13` at `0/32`

## Comparison to Prior `temperature=0.2` Run (same first 512 verdicts)

- Prior pass rate: `176/512 = 0.34375`
- Current pass rate: `80/512 = 0.15625`
- Early checkpoint indicates worse solve behavior at `0.7` on this prefix.

## Note

- Full run is still in progress; checkpoint is not the final conclusion.
