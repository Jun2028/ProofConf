# Pre-512 Theorem Screening Plan (DeepSeek 3.2)

## Purpose

Before any expensive `512`-attempt run, identify miniF2F theorems that are solvable with non-zero but non-trivial probability under current model settings (`deepseek-chat`, DeepSeek 3.2 family).  
If a theorem has ~0 solve chance, it is not useful for confidence-vs-correctness analysis.

## Core Rule

Never run `512` attempts on a theorem unless it passes screening.

## Dataset Scope

- Source: `docs/miniF2F-Graded.json`
- Split: `valid`
- Difficulty focus: moderately difficult to easy (`Level 1`, `Level 2`, `Level 3`)

## Screening Workflow

### Phase 1: Single Screening Pass

- Sample size: `32` attempts/theorem
- Candidate pool: all `valid` theorems in `Level 1/2/3`
- Model settings: same as final study (`max_tokens=8000`, `top_logprobs=20`, same prompt)
- Parallel settings: `llm_parallel_requests=8`, `lean_parallel_workers=8`, `lean_batch_size=16`

Pass condition for Phase 1:
- theorem has `0 < solve_rate < 1.0`

Rationale:
- `solve_rate = 0` provides only failures.
- `solve_rate = 1.0` provides only successes.
- confidence-vs-correctness correlation needs both pass and fail samples per theorem.

Output:
- final usable theorem set for full study.

### Phase 2: Full Correlation Run

- Use only screened theorem list
- Run `512` attempts/theorem
- Keep same model/prompt/parallel settings as screening to preserve comparability

## Compute Policy

- Keep jobs on CPU nodes.
- Keep `LEAN_NUM_THREADS=1`.
- Use scratch output roots:
  - `/scratch/$USER/data/proofconf/output/runs`
  - `/scratch/$USER/data/proofconf/output/logs`
- Start with `ncpus=10` for `8+8` worker configuration.

## Required Artifacts

- `dataset_manifest.json`
- `verdicts.jsonl`
- `summary.json`
- analysis markdown in `logs/analysis/`:
  - screened theorem list
  - per-theorem solve rate
  - chosen final theorem IDs

## Go / No-Go Gate

Go to full run only if screened set has at least `10` theorems meeting inclusion criteria.  
If fewer than `10`, adjust prompt/model settings and rerun Phase 1 on the same candidate pool.

## Current Screening Counts (32-attempt prescreen, latest stable reverify)

- `deepseek-chat`: `16/195` theorems satisfy `0 < pass_rate < 1.0`
- `gemini-2.5-flash`: `99/195` theorems satisfy `0 < pass_rate < 1.0`
