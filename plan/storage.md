# Storage Plan (HPC)

## Goal

Define where repo data, generated runs, and logs are stored on HPC so large outputs do not fill home/NFS.

## Storage Rules

- Large generated artifacts must go to scratch:
  - `/scratch/USER/data/proofconf`
- Repo source code stays in home/NFS workspace:
  - `/home/USER/FormalConf`
- Do not store large run outputs under repo-local `runs/` or `logs/` during HPC jobs.

## Directory Layout

- Scratch root:
  - `/scratch/USER/data/proofconf`
- Cache:
  - `/scratch/USER/data/proofconf/cache`
  - used as `XDG_CACHE_HOME` and miniF2F/lake cache area
- Experiment outputs:
  - `/scratch/USER/data/proofconf/output/runs`
  - `/scratch/USER/data/proofconf/output/logs`
- Verifier temp files (intended):
  - `/scratch/USER/data/proofconf/tmp`
- Repo-local (small/control files only):
  - `configs/`
  - `scripts/`
  - `plan/`
  - `logs/analysis/` (markdown summaries only)

## Runtime Environment Mapping

In PBS scripts, set:

- `XDG_CACHE_HOME=/scratch/${USER}/data/proofconf/cache`
- `PROOFCONF_OUTPUT_ROOT=/scratch/${USER}/data/proofconf/output`
- `PROOFCONF_RUNS_ROOT=${PROOFCONF_OUTPUT_ROOT}/runs`
- `PROOFCONF_LOGS_ROOT=${PROOFCONF_OUTPUT_ROOT}/logs`
- `PROOFCONF_TMP_ROOT=/scratch/${USER}/data/proofconf/tmp` (intended for verifier temp `.lean` files)

Pipeline behavior:

- `src/proofconf/pipeline/run_experiment.py` writes run artifacts to `PROOFCONF_RUNS_ROOT`.
- Driver/event logs are written to `PROOFCONF_LOGS_ROOT/run/<run_id>/driver.log`.
- `src/proofconf/lean/verifier.py` temp files should be written under `PROOFCONF_TMP_ROOT` (intended behavior).

## Data Produced Per Run

Under `.../output/runs/<run_id>/`:

- `samples.jsonl`
- `metrics.jsonl`
- `verdicts.jsonl`
- `summary.json`
- `summary.md`
- `dataset_manifest.json`
- `config.resolved.json`
- `meta/execution.json`

Under `.../output/logs/run/<run_id>/`:

- `driver.log`
- `env.snapshot`
- `git.snapshot`
- `artifacts.json`

Under `.../tmp/` (intended):

- transient Lean verifier source files generated during proof checking

## Operational Policy

- Before launching long runs, ensure scratch directories exist (`mkdir -p` in PBS scripts).
- Keep historical run payloads in scratch; only copy compact analysis artifacts to repo.
- If scratch usage grows too large, prune old run directories in scratch first, not repo source.
- Repo-local `datasets/.../.proofconf_tmp` is not intended as the long-term location for verifier temp files.
