# DeepSeek 512x Scale Run

## Objective

- Run DeepSeek-only confidence study at substantially larger sampling scale.
- Measure confidence/correctness correlation with enough attempts to reduce small-sample noise.
- Prerequisite: theorem set must be screened first using `plan/theorem_prescreening.md` (pre-512 screening gate).

## Configuration

- Config file: `configs/deepseek_scale_512.json`
- Dataset: `docs/miniF2F-Graded.json`
- Split: `valid`
- Levels: `Level 2`, `Level 3`
- Theorems: `16`
- Attempts per theorem: `512`
- Total attempts: `8192`
- Max tokens: `8000`

## Parallel Execution

- LLM generation parallelism: `8` requests
- Lean verification parallelism: `8` workers
- Lean batch size: `16` attempts per Lean process
- Requested HPC CPU cores: `10`

Rationale:
- LLM calls are network-bound; moderate fan-out avoids API throttling.
- Batch verification reduces Lean process churn and file-open pressure.
- 8 LLM threads + 8 Lean workers run on a 10-core request without heavy oversubscription.

## HPC

- PBS script: `scripts/run_deepseek_scale_512.pbs`
- Project: personal credit by default (the `#PBS -P CFP01-SF-009` line is left commented for optional switch)
- Output roots redirected to scratch in batch job:
  - runs: `/scratch/$USER/data/proofconf/output/runs/`
  - logs: `/scratch/$USER/data/proofconf/output/logs/`

Submit from login node:

```bash
qsub scripts/run_deepseek_scale_512.pbs
```

## Expected Outputs

- `runs/<run_id>/samples.jsonl`
- `runs/<run_id>/verdicts.jsonl`
- `runs/<run_id>/metrics.jsonl`
- `runs/<run_id>/summary.json`
- `runs/<run_id>/summary.md`
- `logs/run/<run_id>/driver.log`
