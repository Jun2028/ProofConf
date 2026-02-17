# Run Plan

## Initial Baseline Run

- Config: `configs/initial_run.json`
- Dataset: `docs/miniF2F-Graded.json`
- Split: `valid`
- Levels: `Level 2`, `Level 3`
- Theorems: 3
- Samples per theorem per model: 2
- Models:
  - `deepseek-chat`
  - `gemini-2.5-flash`

## Outputs

- Artifacts: `runs/<run_id>/`
  - `samples.jsonl`
  - `verdicts.jsonl`
  - `metrics.jsonl`
  - `summary.md`
- Driver logs: `logs/run/<run_id>/driver.log`

## DeepSeek-Only Scale Test (Planned + Checkpoint)

- Plan doc: `plan/deepseek_full_test.md`
- Config: `configs/deepseek_full_test.json`
- Tag: `deepseek_full`
- Models:
  - `deepseek-chat` only
- Core changes:
  - `max_tokens=8000`
  - proof-part prefix probes enabled
  - confidence filtering analysis (top 10/25/50%)

## DeepSeek High-Throughput Run (Planned)

- Config: `configs/deepseek_scale_512.json`
- Scale:
  - theorems: `16`
  - attempts per theorem: `512`
  - total attempts: `8192`
- Parallelization:
  - parallel LLM requests: `4`
  - parallel Lean workers: `2`
- HPC job script: `scripts/run_deepseek_scale_512.pbs`
  - project credit: `CFP01-SF-009`
  - requested CPU: `24` cores on one socket
  - run/log outputs redirected to scratch

## Reporting Location

- Run logs and analysis reports are stored outside `plan/`:
  - raw run logs: `logs/run/`
  - markdown analyses: `logs/analysis/`
