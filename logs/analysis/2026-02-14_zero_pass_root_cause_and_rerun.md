> [INVALIDATED on 2026-02-15]
> This report contains conclusions from verdicts affected by the batched Lean verifier path-resolution bug.
> Use `logs/analysis/2026-02-15_batch_verifier_diagnosis.md` and `logs/analysis/2026-02-15_three_model_run_diagnosis.md` for corrected diagnosis context.

# Zero-Pass Root Cause and Rerun Notes

## Observed Issue

- Run: `runs/2026-02-14_015058Z_deepseek_scale_512`
- Result: `0/8192` passes

## Root Cause Analysis

- Failure text analysis on `verdicts.jsonl`:
  - `failed_open`: `8169`
  - `unsolved_goals`: `9`
  - other/tactic: small remainder
- Representative error:
  - `failed to open file ... Index.olean.private`

Conclusion:
- The run was dominated by Lean file-open/infrastructure errors under large parallel verification load.
- This is not explainable by theorem difficulty alone.

## Fixes Applied

1. Added explicit error class:
   - `file_open_error` in `classify_error`.
2. Added strict warmup gate:
   - abort run if warmup fails.
3. Added PBS preflight compile before launching run:
   - compile a tiny `import Mathlib` file to avoid lazy toolchain/object setup races.
4. Reduced default Lean verification concurrency for scale config:
   - `lean_parallel_workers = 8`.

## Rerun

- Old flawed rerun job `566298` was canceled.
- New job submitted: `566301.stdct-mgmt-02`
- Active run ID: `2026-02-14_072804Z_deepseek_scale_512_retry`
- Warmup status: success (`returncode=0`, ~26.7s).

## Additional Diagnosis

- During retry, Lean failures showed:
  - `Too many open files in system`
  - This is file-descriptor exhaustion (`ENFILE`), not theorem difficulty.

## Final Fix Set Before Full Run

1. Reduced parallelism further:
   - `llm_parallel_requests = 4`
   - `lean_parallel_workers = 2`
2. Added explicit classifier:
   - `fd_exhaustion`
3. Redirected heavy outputs to scratch in PBS job:
   - `PROOFCONF_RUNS_ROOT=/scratch/$USER/data/proofconf/output/runs`
   - `PROOFCONF_LOGS_ROOT=/scratch/$USER/data/proofconf/output/logs`
4. Relaunched full run:
   - Job: `568555.stdct-mgmt-02`
   - Run ID: `2026-02-14_103924Z_deepseek_scale_512_retry2`
   - Driver log: `/scratch/USER/data/proofconf/output/logs/run/2026-02-14_103924Z_deepseek_scale_512_retry2/driver.log`
