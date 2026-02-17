> [INVALIDATED on 2026-02-15]
> This report contains conclusions from verdicts affected by the batched Lean verifier path-resolution bug.
> Use `logs/analysis/2026-02-15_batch_verifier_diagnosis.md` and `logs/analysis/2026-02-15_three_model_run_diagnosis.md` for corrected diagnosis context.

# Scale 512 Submission Log

## Request Applied

- Attempts per theorem set to `512`.
- Number of theorems increased to `16`.
- Parallel sampling and verification enabled.

## Key Config

- File: `configs/deepseek_scale_512.json`
- `samples_per_theorem`: `512`
- `num_theorems`: `16`
- `llm_parallel_requests`: `6`
- `lean_parallel_workers`: `24`
- `max_tokens`: `8000`
- `probe_prefix_parts`: `false` (disabled for throughput)

## Parallel Pipeline Update

- File: `src/proofconf/pipeline/run_experiment.py`
- Added concurrent generation (`ThreadPoolExecutor`)
- Added concurrent Lean verification (`ThreadPoolExecutor`)
- Added worker caps based on allocated CPU (`PBS_NCPUS`, `NCPUS`, `PBS_NP`)

## HPC Submission

- Script: `scripts/run_deepseek_scale_512.pbs`
- Project: `CFP01-SF-009`
- Request: `select=1:ncpus=24:mpiprocs=1:ompthreads=24:mem=170gb`
- Walltime: `06:00:00`
- Job ID: `563989.stdct-mgmt-02`
- Run ID: `2026-02-14_015058Z_deepseek_scale_512`
- Driver log: `logs/run/2026-02-14_015058Z_deepseek_scale_512/driver.log`

## Note

- A prior submission with a larger resource request was rejected for project budget constraints.
- Current submission uses reduced resources to stay within available budget while preserving parallel execution.
